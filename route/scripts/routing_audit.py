#!/usr/bin/env python3
"""Answers one question with evidence: did this session actually route, or did the
expensive model do it all?

Reads the transcripts Claude Code already writes and reports **cost** per model and per
role. Cost, not token volume, is the metric that matters: replaying context (cache read)
is typically the dominant share of a routed session's spend, output only a small share.
A report denominated in output tokens therefore ranks the cheap thing first.

Subagent turns are NOT in the session transcript — they live in a sibling `subagents/`
directory. Reading only the session file reports 100% main-model even when routing
worked perfectly, so this script reads both, and prefers the paths `routing_observe.py`
recorded in `.claude/routing/dispatch.jsonl` over guessing at that layout.

Prices come from `pricing.json` next to this script (override with `audit.pricingFile`
in `.claude/route.config.json`). **Verify those numbers against the official pricing
page** — a stale table produces a confident wrong answer.

Usage (run from the project you want to audit, or set CLAUDE_PROJECT_DIR):
  python3 routing_audit.py            # latest session
  python3 routing_audit.py --all      # every session for this project
  python3 routing_audit.py --sessions 5
"""
import argparse
import glob
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hooks"))
from _config import load_config, normalize_role, project_dir  # noqa: E402

PROJECT = project_dir()
CFG = load_config(PROJECT)
COMPONENTS = ("out", "cache_read", "cache_write", "in")


def load_pricing() -> dict:
    override = (CFG.get("audit") or {}).get("pricingFile")
    candidates = []
    if override:
        candidates.append(override if os.path.isabs(override)
                          else os.path.join(PROJECT, override))
    candidates.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "pricing.json"))
    for path in candidates:
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            continue
        if isinstance(data.get("models"), dict):
            return data
    return {"models": {}, "cacheMultipliers": {}}


PRICING = load_pricing()
MULT = PRICING.get("cacheMultipliers") or {}
CACHE_READ = MULT.get("read", 0.1)
CACHE_W_5M = MULT.get("write5m", 1.25)
CACHE_W_1H = MULT.get("write1h", 2.0)


def rate(model: str):
    """-> (input, output) USD per million tokens, or None when unpriced."""
    best = None
    for prefix, price in (PRICING.get("models") or {}).items():
        if (model or "").startswith(prefix) and (best is None or len(prefix) > len(best[0])):
            best = (prefix, price)
    if best is None:
        return None
    return best[1].get("in", 0.0), best[1].get("out", 0.0)


def cost(model: str, s) -> dict:
    """-> {component: usd}. Empty when the model has no price entry."""
    price = rate(model)
    if not price:
        return {}
    inp, outp = price
    return {
        "out": s["out"] * outp / 1e6,
        "cache_read": s["cache_read"] * inp * CACHE_READ / 1e6,
        "cache_write": (s["cw5"] * CACHE_W_5M + s["cw1h"] * CACHE_W_1H) * inp / 1e6,
        "in": s["in"] * inp / 1e6,
    }


def tally(path: str):
    """-> (models -> {out, in, cache_read, cw5, cw1h, turns})"""
    stats = defaultdict(lambda: dict.fromkeys(
        ("out", "in", "cache_read", "cw5", "cw1h", "turns"), 0))
    for line in open(path, encoding="utf-8", errors="replace"):
        try:
            row = json.loads(line)
        except Exception:
            continue
        msg = row.get("message")
        if not isinstance(msg, dict) or not msg.get("usage"):
            continue
        u = msg["usage"]
        s = stats[msg.get("model") or "unknown"]
        s["out"] += u.get("output_tokens", 0)
        s["in"] += u.get("input_tokens", 0)
        s["cache_read"] += u.get("cache_read_input_tokens", 0)
        # Newer transcripts split the cache write by TTL, which is a 1.6x price
        # difference; older ones only carry the total, which we bill at the 5m rate.
        cc = u.get("cache_creation") or {}
        five, hour = cc.get("ephemeral_5m_input_tokens"), cc.get("ephemeral_1h_input_tokens")
        if five is None and hour is None:
            s["cw5"] += u.get("cache_creation_input_tokens", 0)
        else:
            s["cw5"] += five or 0
            s["cw1h"] += hour or 0
        s["turns"] += 1
    return stats


def dispatch_log() -> dict:
    """-> {main transcript path: [(role, agent transcript path)]} from the hook's log.

    The hook records the paths as the harness reported them, so this survives a change
    to the on-disk transcript layout that the glob below would not.
    """
    out = defaultdict(list)
    seen = set()
    path = os.path.join(PROJECT, ".claude", "routing", "dispatch.jsonl")
    for name in (path, path + ".1"):
        try:
            fh = open(name, encoding="utf-8", errors="replace")
        except OSError:
            continue
        with fh:
            for line in fh:
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                main, agent = row.get("transcript_path"), row.get("agent_transcript_path")
                if not main or not agent or agent in seen:
                    continue
                seen.add(agent)
                if os.path.exists(agent):
                    out[main].append((normalize_role(row.get("agent_type")) or "?", agent))
    return out


def subagent_runs(session_path: str, logged: dict):
    """-> ([(role, path)], status) where status explains an empty list."""
    runs = list(logged.get(session_path) or [])
    if runs:
        return runs, "ok"
    base = session_path[: -len(".jsonl")]
    sub_dir = os.path.join(base, "subagents")
    if not os.path.isdir(sub_dir):
        return [], sub_dir
    for path in sorted(glob.glob(os.path.join(sub_dir, "agent-*.jsonl"))):
        role = "?"
        try:
            with open(path[: -len(".jsonl")] + ".meta.json", encoding="utf-8") as fh:
                role = normalize_role(json.load(fh).get("agentType")) or "?"
        except Exception:
            pass
        runs.append((role, path))
    return runs, "ok" if runs else "empty"


def report(paths) -> int:
    by_model = defaultdict(float)
    by_role = defaultdict(lambda: {"runs": 0, "usd": 0.0, "out": 0})
    by_component = defaultdict(float)
    unpriced = set()
    main_turns = 0
    main_ctx = 0
    row = "{:<18}{:<20}{:>7}{:>11}{:>12}{:>14}{:>10}"
    logged = dispatch_log()

    def emit(role, model, s):
        nonlocal main_turns, main_ctx
        c = cost(model, s)
        usd = sum(c.values())
        print(row.format(role, model, s["turns"], "{:,}".format(s["out"]),
                         "{:,}".format(s["cw5"] + s["cw1h"]),
                         "{:,}".format(s["cache_read"]),
                         "{:,.2f}".format(usd) if c else "—"))
        if c:
            by_model[model] += usd
        else:
            unpriced.add(model)
        by_role[role]["usd"] += usd
        by_role[role]["out"] += s["out"]
        for k, v in c.items():
            by_component[k] += v
        if role == "main":
            main_turns += s["turns"]
            main_ctx += s["cache_read"]

    for session in paths:
        print("\n=== session %s" % os.path.basename(session)[:8])
        print(row.format("role", "model", "turns", "out", "cacheW", "cacheR", "USD"))
        for model, s in sorted(tally(session).items(), key=lambda kv: -kv[1]["out"]):
            emit("main", model, s)
        by_role["main"]["runs"] += 1

        runs, status = subagent_runs(session, logged)
        for role, path in runs:
            for model, s in sorted(tally(path).items(), key=lambda kv: -kv[1]["out"]):
                emit(role, model, s)
            by_role[role]["runs"] += 1
        if status == "empty":
            print("  (no subagent transcripts — nothing was routed in this session)")
        elif status != "ok":
            print("  could not locate subagent transcripts under %s; the transcript "
                  "layout may have changed. This is NOT evidence that nothing was "
                  "routed." % status)

    grand = sum(by_model.values())
    if not grand:
        print("\nNo priced usage found in the selected transcripts.")
        return 1

    print("\n--- cost by component (what the money actually buys) ---")
    for name in COMPONENTS:
        usd = by_component[name]
        print("  {:<28}{:>10,.2f}  {:6.1%}".format(name, usd, usd / grand))

    print("\n--- cost by model ---")
    for model, usd in sorted(by_model.items(), key=lambda kv: -kv[1]):
        print("  {:<28}{:>10,.2f}  {:6.1%}".format(model, usd, usd / grand))
    if unpriced:
        print("  (unpriced, excluded: %s — add a prefix to pricing.json)"
              % ", ".join(sorted(unpriced)))

    print("\n--- cost by role (the routing verdict) ---")
    for role, s in sorted(by_role.items(), key=lambda kv: -kv[1]["usd"]):
        print("  {:<28}{:>10,.2f}  {:6.1%}  ({} run(s))".format(
            role, s["usd"], s["usd"] / grand, s["runs"]))

    main_usd = by_role["main"]["usd"]
    print("\nTotal ${:,.2f}. Main session spent {:.0%} of it.".format(
        grand, main_usd / grand))
    if main_turns:
        print("Main ran {:,} turns at an average context of {:,} tokens — ${:.3f} per "
              "turn.".format(main_turns, main_ctx // main_turns, main_usd / main_turns))
    print("\nUSD columns use pricing.json; verify it against the official pricing page.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--all", action="store_true", help="every session for this project")
    ap.add_argument("--sessions", type=int, default=1, help="how many recent sessions")
    args = ap.parse_args()

    d = os.path.join(os.path.expanduser("~"), ".claude", "projects",
                     PROJECT.replace("/", "-"))
    paths = sorted(glob.glob(os.path.join(d, "*.jsonl")), key=os.path.getmtime, reverse=True)
    if not paths:
        print("No transcripts under %s" % d, file=sys.stderr)
        return 1
    return report(paths if args.all else paths[: args.sessions])


if __name__ == "__main__":
    sys.exit(main())
