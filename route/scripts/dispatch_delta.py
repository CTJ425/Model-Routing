#!/usr/bin/env python3
"""Does one subagent dispatch add or remove net tokens from main's context?

Routing is usually adopted on a cost argument that is correlational at best. This
measures both sides of a single dispatch directly from the transcripts.

  cost side    = what the dispatch PUTS INTO main's context and leaves there:
                 the dispatch prompt + the returned report.
  benefit side = what the subagent read on main's behalf: every tool_result payload
                 inside the subagent's own transcript. Had main done the work itself,
                 that material would have landed in main's context instead.
  net          = benefit - cost, in tokens. Positive means the dispatch paid for itself
                 in context terms.

Both sides persist for the remainder of the session and are re-billed as cache read on
every later turn, so the dollar figure multiplies the net by the turns that followed it.

Two honest caveats, restated in the report footer:
  * The benefit side is an UPPER BOUND. Main might have answered the same question with
    narrower reads than the subagent chose to make.
  * Token counts are chars/N (`audit.charsPerToken`, default 4). That ratio is tuned
    for English; CJK text runs closer to 1.5 chars per token, so a Chinese/Japanese/
    Korean project underestimates badly until `--validate` is used to recalibrate it.

Usage (run from the project you want to measure, or set CLAUDE_PROJECT_DIR):
  python3 dispatch_delta.py            # every session, summary + per-role
  python3 dispatch_delta.py --detail   # one line per dispatch
  python3 dispatch_delta.py --validate # chars/N vs measured cache_read delta
"""
import argparse
import glob
import json
import os
import statistics
import sys
from collections import defaultdict

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "hooks"))
sys.path.insert(0, _HERE)
from _config import load_config, project_dir  # noqa: E402
from routing_audit import CACHE_READ, rate  # noqa: E402

PROJECT = project_dir()
CFG = load_config(PROJECT)
try:
    CHARS_PER_TOKEN = float((CFG.get("audit") or {}).get("charsPerToken") or 4.0)
except (TypeError, ValueError):
    CHARS_PER_TOKEN = 4.0

# Replay is billed as cache read: a multiple of the main model's input rate. Deriving
# it from the model that actually ran beats a constant, but the constant has to stay
# for the case where no priced model id appears in the transcripts.
FALLBACK_USD_PER_TOKEN_REPLAY = 5.0 * 0.1 / 1e6
PRICED_FROM = set()


def replay_rate(path: str) -> float:
    """-> USD per replayed token, from the model that did the most turns in `path`."""
    turns = defaultdict(int)
    for row in rows(path):
        msg = row.get("message")
        if isinstance(msg, dict) and msg.get("usage") and row.get("type") == "assistant":
            turns[msg.get("model") or ""] += 1
    for model, _ in sorted(turns.items(), key=lambda kv: -kv[1]):
        price = rate(model)
        if price:
            PRICED_FROM.add(model)
            return price[0] * CACHE_READ / 1e6
    return FALLBACK_USD_PER_TOKEN_REPLAY


def text_len(content) -> int:
    """Characters in a message `content`, which is a string or a list of blocks."""
    if isinstance(content, str):
        return len(content)
    if not isinstance(content, list):
        return 0
    n = 0
    for block in content:
        if isinstance(block, str):
            n += len(block)
        elif isinstance(block, dict):
            for key in ("text", "content", "thinking"):
                v = block.get(key)
                if isinstance(v, str):
                    n += len(v)
                elif isinstance(v, list):
                    n += text_len(v)
    return n


def rows(path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                yield json.loads(line)
            except Exception:
                continue


def scan_main(path):
    """-> (dispatches, total_assistant_turns).

    dispatches: tool_use_id -> {role, prompt_chars, report_chars, turn_index,
                                ctx_before, ctx_after, solo}
    `solo` marks a dispatch that was the only tool call in its turn, so the measured
    cache_read delta across it is attributable to the dispatch alone.
    """
    disp, turn = {}, 0
    pending = []  # dispatches awaiting the assistant turn that follows their result
    for row in rows(path):
        msg = row.get("message")
        if not isinstance(msg, dict):
            continue

        if row.get("type") == "assistant" and msg.get("usage"):
            ctx = msg["usage"].get("cache_read_input_tokens", 0)
            for d in pending:
                d["ctx_after"] = ctx
            pending = []
            turn += 1
            calls = [b for b in msg.get("content") or []
                     if isinstance(b, dict) and b.get("type") == "tool_use"]
            agents = [b for b in calls if b.get("name") in ("Agent", "Task")]
            for b in agents:
                inp = b.get("input") or {}
                disp[b.get("id")] = {
                    "role": inp.get("subagent_type") or "?",
                    "prompt_chars": len(inp.get("prompt") or "") + len(inp.get("description") or ""),
                    "report_chars": 0,
                    "turn_index": turn,
                    "ctx_before": ctx,
                    "ctx_after": None,
                    "solo": len(calls) == 1,
                }

        for block in msg.get("content") or []:
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue
            d = disp.get(block.get("tool_use_id"))
            if d is not None:
                d["report_chars"] = text_len(block.get("content"))
                pending.append(d)
    return disp, turn


def scan_subagent(path):
    """-> (tool_result_chars, assistant_turns) for one subagent transcript."""
    consumed, turns = 0, 0
    for row in rows(path):
        msg = row.get("message")
        if not isinstance(msg, dict):
            continue
        if row.get("type") == "assistant" and msg.get("usage"):
            turns += 1
        for block in msg.get("content") or []:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                consumed += text_len(block.get("content"))
    return consumed, turns


def collect(session_path):
    """-> list of per-dispatch records for one session."""
    disp, total_turns = scan_main(session_path)
    if not disp:
        return []
    base = session_path[: -len(".jsonl")]
    usd_per_token = replay_rate(session_path)
    out = []
    for meta_path in sorted(glob.glob(os.path.join(base, "subagents", "agent-*.meta.json"))):
        try:
            with open(meta_path, encoding="utf-8") as fh:
                meta = json.load(fh)
        except Exception:
            continue
        d = disp.get(meta.get("toolUseId"))
        if d is None:
            continue
        jsonl = meta_path[: -len(".meta.json")] + ".jsonl"
        if not os.path.exists(jsonl):
            continue
        consumed, sub_turns = scan_subagent(jsonl)
        cost = (d["prompt_chars"] + d["report_chars"]) / CHARS_PER_TOKEN
        benefit = consumed / CHARS_PER_TOKEN
        remaining = max(total_turns - d["turn_index"], 0)
        measured = (d["ctx_after"] - d["ctx_before"]
                    if d["solo"] and d["ctx_after"] is not None else None)
        out.append({
            "session": os.path.basename(session_path)[:8],
            "role": meta.get("agentType") or d["role"],
            "cost": cost,
            "benefit": benefit,
            "net": benefit - cost,
            "remaining": remaining,
            "usd": (benefit - cost) * remaining * usd_per_token,
            "sub_turns": sub_turns,
            "measured": measured,
            "prompt": d["prompt_chars"] / CHARS_PER_TOKEN,
            "report": d["report_chars"] / CHARS_PER_TOKEN,
        })
    return out


def med(xs):
    return statistics.median(xs) if xs else 0.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--detail", action="store_true", help="one line per dispatch")
    ap.add_argument("--validate", action="store_true",
                    help="compare the chars/N estimate against measured cache_read growth")
    ap.add_argument("--all", action="store_true", help="every session for this project")
    ap.add_argument("--sessions", type=int, default=1, help="how many recent sessions")
    args = ap.parse_args()

    d = os.path.join(os.path.expanduser("~"), ".claude", "projects",
                     PROJECT.replace("/", "-"))
    paths = sorted(glob.glob(os.path.join(d, "*.jsonl")), key=os.path.getmtime, reverse=True)
    if not paths:
        print(f"No transcripts under {d}", file=sys.stderr)
        return 1

    recs = [r for p in (paths if args.all else paths[: args.sessions]) for r in collect(p)]
    if not recs:
        print("No dispatches with a matching subagent transcript were found.", file=sys.stderr)
        return 1

    if args.detail:
        print(f"{'session':<10}{'role':<10}{'cost':>9}{'benefit':>10}{'net':>10}"
              f"{'turnsL':>8}{'USD':>9}")
        for r in sorted(recs, key=lambda r: r["net"]):
            print(f"{r['session']:<10}{r['role']:<10}{r['cost']:>9,.0f}{r['benefit']:>10,.0f}"
                  f"{r['net']:>10,.0f}{r['remaining']:>8}{r['usd']:>9,.2f}")
        print()

    print(f"{'role':<12}{'n':>4}{'cost':>10}{'benefit':>10}{'net(mean)':>11}"
          f"{'net(med)':>10}{'+net':>6}{'USD':>10}")
    by_role = defaultdict(list)
    for r in recs:
        by_role[r["role"]].append(r)
    for role, rs in sorted(by_role.items(), key=lambda kv: -len(kv[1])):
        nets = [r["net"] for r in rs]
        print(f"{role:<12}{len(rs):>4}"
              f"{statistics.mean(r['cost'] for r in rs):>10,.0f}"
              f"{statistics.mean(r['benefit'] for r in rs):>10,.0f}"
              f"{statistics.mean(nets):>11,.0f}{med(nets):>10,.0f}"
              f"{sum(1 for n in nets if n > 0):>6}"
              f"{sum(r['usd'] for r in rs):>10,.2f}")

    nets = [r["net"] for r in recs]
    print(f"{'ALL':<12}{len(recs):>4}"
          f"{statistics.mean(r['cost'] for r in recs):>10,.0f}"
          f"{statistics.mean(r['benefit'] for r in recs):>10,.0f}"
          f"{statistics.mean(nets):>11,.0f}{med(nets):>10,.0f}"
          f"{sum(1 for n in nets if n > 0):>6}"
          f"{sum(r['usd'] for r in recs):>10,.2f}")

    print(f"\nMean dispatch: prompt {statistics.mean(r['prompt'] for r in recs):,.0f} tok"
          f" + report {statistics.mean(r['report'] for r in recs):,.0f} tok"
          f" into main; {statistics.mean(r['benefit'] for r in recs):,.0f} tok"
          f" read on main's behalf.")
    pos = sum(1 for n in nets if n > 0)
    print(f"{pos}/{len(nets)} dispatches ({pos / len(nets):.0%}) removed net tokens from main.")

    if args.validate:
        v = [r for r in recs if r["measured"] is not None]
        print(f"\n--- validate: chars/{CHARS_PER_TOKEN:g} estimate vs measured cache_read growth (n={len(v)}) ---")
        print(f"{'role':<12}{'estimated':>11}{'measured':>10}{'ratio':>8}")
        for r in sorted(v, key=lambda r: r["role"]):
            est = r["cost"]
            ratio = r["measured"] / est if est else 0
            print(f"{r['role']:<12}{est:>11,.0f}{r['measured']:>10,.0f}{ratio:>8.2f}")
        if v:
            ratios = [r["measured"] / r["cost"] for r in v if r["cost"]]
            print(f"median ratio {med(ratios):.2f} — >1 means the dispatch turn also grew "
                  f"main's context by more than the prompt+report alone")

    priced = (", ".join(sorted(PRICED_FROM)) if PRICED_FROM
              else "a default $5/Mtok input rate — no priced model id was found")
    print("\nCaveats: benefit is an UPPER BOUND (main might have read less than the "
          f"subagent chose to); tokens are chars/{CHARS_PER_TOKEN:g}; USD prices the net "
          f"at the cache-read rate of {priced} times the main turns that followed the "
          "dispatch.")
    print(f"chars/{CHARS_PER_TOKEN:g} is tuned for English and underestimates CJK text "
          "badly (roughly 1.5 chars per token). On a Chinese/Japanese/Korean project, run "
          "--validate and set audit.charsPerToken in .claude/route.config.json to the "
          "ratio it reports.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
