#!/usr/bin/env python3
"""Answers one question with evidence: did this session actually route, or did the
expensive model do it all?

Reads the transcripts Claude Code already writes and reports **cost** per model and per
role. Cost, not token volume, is the metric that matters: replaying context (cache read)
is typically the dominant share of a routed session's spend, output only a small share.
A report denominated in output tokens therefore ranks the cheap thing first.

Subagent turns are NOT in the session transcript — they live in
`<session-id>/subagents/agent-<id>.jsonl`, with the role in the sibling `.meta.json`.
Reading only the session file reports 100% main-model even when routing worked
perfectly, so this script reads both.

A healthy routed session shows the bulk of spend off the main session. One model and zero
subagent transcripts means nothing was routed, whatever the plan said.

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

PROJECT = os.path.abspath(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())

# USD per million tokens, (input, output). Update this table when rates change.
PRICES = {
    "claude-opus-5": (5.0, 25.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-opus-4-8": (5.0, 25.0),
}
CACHE_READ = 0.1   # x input rate
CACHE_W_5M = 1.25  # x input rate
CACHE_W_1H = 2.0   # x input rate
COMPONENTS = ("out", "cache_read", "cache_write", "in")


def rate(model: str):
    for prefix, price in PRICES.items():
        if (model or "").startswith(prefix):
            return price
    return None


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


def subagent_runs(session_path: str):
    """-> [(role, path)] for every subagent spawned by this session."""
    base = session_path[: -len(".jsonl")]
    runs = []
    for path in sorted(glob.glob(os.path.join(base, "subagents", "agent-*.jsonl"))):
        role = "?"
        try:
            with open(path[: -len(".jsonl")] + ".meta.json", encoding="utf-8") as fh:
                role = json.load(fh).get("agentType") or "?"
        except Exception:
            pass
        runs.append((role, path))
    return runs


def report(paths) -> int:
    by_model = defaultdict(float)
    by_role = defaultdict(lambda: {"runs": 0, "usd": 0.0, "out": 0})
    by_component = defaultdict(float)
    unpriced = set()
    main_turns = 0
    main_ctx = 0
    row = "{:<18}{:<20}{:>7}{:>11}{:>12}{:>14}{:>10}"

    def emit(role, model, s):
        nonlocal main_turns, main_ctx
        c = cost(model, s)
        usd = sum(c.values())
        print(row.format(role, model, s["turns"], f"{s['out']:,}",
                         f"{s['cw5'] + s['cw1h']:,}", f"{s['cache_read']:,}",
                         f"{usd:,.2f}" if c else "—"))
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
        print(f"\n=== session {os.path.basename(session)[:8]}")
        print(row.format("role", "model", "turns", "out", "cacheW", "cacheR", "USD"))
        for model, s in sorted(tally(session).items(), key=lambda kv: -kv[1]["out"]):
            emit("main", model, s)
        by_role["main"]["runs"] = 1

        runs = subagent_runs(session)
        for role, path in runs:
            for model, s in sorted(tally(path).items(), key=lambda kv: -kv[1]["out"]):
                emit(role, model, s)
            by_role[role]["runs"] += 1
        if not runs:
            print("  (no subagent transcripts — nothing was routed in this session)")

    grand = sum(by_model.values())
    if not grand:
        print("\nNo priced usage found in the selected transcripts.")
        return 1

    print("\n--- cost by component (what the money actually buys) ---")
    for name in COMPONENTS:
        usd = by_component[name]
        print(f"  {name:<28}{usd:>10,.2f}  {usd / grand:6.1%}")

    print("\n--- cost by model ---")
    for model, usd in sorted(by_model.items(), key=lambda kv: -kv[1]):
        print(f"  {model:<28}{usd:>10,.2f}  {usd / grand:6.1%}")
    if unpriced:
        print(f"  (unpriced, excluded: {', '.join(sorted(unpriced))} — add to PRICES)")

    print("\n--- cost by role (the routing verdict) ---")
    for role, s in sorted(by_role.items(), key=lambda kv: -kv[1]["usd"]):
        print(f"  {role:<28}{s['usd']:>10,.2f}  {s['usd'] / grand:6.1%}  ({s['runs']} run(s))")

    main_usd = by_role["main"]["usd"]
    print(f"\nTotal ${grand:,.2f}. Main session spent {main_usd / grand:.0%} of it.")
    if main_turns:
        print(f"Main ran {main_turns:,} turns at an average context of "
              f"{main_ctx // main_turns:,} tokens — ${main_usd / main_turns:.3f} per turn.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--sessions", type=int, default=1)
    args = ap.parse_args()

    d = os.path.join(os.path.expanduser("~"), ".claude", "projects",
                     PROJECT.replace("/", "-"))
    paths = sorted(glob.glob(os.path.join(d, "*.jsonl")), key=os.path.getmtime, reverse=True)
    if not paths:
        print(f"No transcripts under {d}", file=sys.stderr)
        return 1
    return report(paths if args.all else paths[: args.sessions])


if __name__ == "__main__":
    sys.exit(main())
