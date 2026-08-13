#!/usr/bin/env python3
"""Makes routing observable, so "we delegate" is a measurable claim and not a belief.

Three jobs, selected by hook_event_name:

  SessionStart                  -> put the routing rule in context. `route` is a skill,
      so it only runs if the main session decides to load it, and nothing else prompts
      that. A few hundred tokens once per session is the cheapest fix available.

  SubagentStart / SubagentStop  -> append one line to .claude/routing/dispatch.jsonl.
      This is the audit trail: which roles actually ran, at what effort, when.

  PostToolUse(Read|Grep|Glob)   -> count discovery calls made *in the main session*.
      Broad discovery is the single largest avoidable cost in the loop, and it leaks
      silently because each individual Read looks cheap. Past a threshold the hook says
      so, in context, while the leak is still happening.

Env overrides:
  ROUTING_OBSERVE=off      disable entirely
  ROUTING_SCOUT_AT=<n>     first nudge after n main-session discovery calls (default 12)
"""
import json
import os
import re
import sys
import time

MAIN_ALIASES = {"", "main", "default", "root", "none"}
REPEAT_EVERY = 8


def routing_dir(payload) -> str:
    project = os.path.abspath(os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd())
    d = os.path.join(project, ".claude", "routing")
    os.makedirs(os.path.join(d, "state"), exist_ok=True)
    return d


def log_dispatch(payload, d: str) -> None:
    row = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "event": payload.get("hook_event_name"),
        "agent_type": payload.get("agent_type"),
        "agent_id": payload.get("agent_id"),
        "effort": (payload.get("effort") or {}).get("level"),
        "session": payload.get("session_id"),
    }
    with open(os.path.join(d, "dispatch.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


BRIEF = """[routing] This project delegates. Before acting on a feature, a bug, or a
`docs/agent/TASK.md` item, load the `route` skill and state the lane in one line.

- **Cost here is context replay, not output.** Replaying context into the main session's
  window is billed on every remaining turn of the session, so bulk content goes to a
  subagent even when the task looks trivial.
- **Roster.** This session plans, writes specs, and adjudicates. `scout` reads and
  compresses; `builder` implements; `reviewer` checks risk work; `scribe` records.
  Delegation is pre-authorized — dispatch without asking. Per-role model tiers live in
  `.claude/route.config.json` (see `/route:config`).
- **Three PreToolUse guards will ask** before this session edits production code or a
  `docs/agent/` record, dispatches `Explore`/`general-purpose`, or issues an unbounded
  Read over 32KB. An `ask` is policy, not an obstacle: take the cheaper path it names.
- **Open now:** {tasks} task(s) in `TASK.md`, {bugs} entr(y/ies) in `BUG_FIX.md`."""


def open_counts(payload) -> tuple:
    """-> (open TASK.md entries, BUG_FIX.md entries); '?' when unreadable."""
    project = os.path.abspath(
        os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd())

    def read(name):
        try:
            with open(os.path.join(project, "docs", "agent", name), encoding="utf-8") as fh:
                return fh.read()
        except OSError:
            return None

    tasks = read("TASK.md")
    if tasks is None:
        n_tasks = "?"
    else:
        n_tasks = 0
        for block in re.split(r"^### ", tasks, flags=re.M)[1:]:
            status = re.search(r"^- \*\*Status\*\*:\s*(.*)$", block, re.M)
            if not status or not status.group(1).lstrip().startswith("✅"):
                n_tasks += 1

    bugs = read("BUG_FIX.md")
    # BUG_FIX.md holds only open bugs by construction — fixed ones move to FIXED_BUG.md.
    n_bugs = "?" if bugs is None else len(re.findall(r"^### ", bugs, flags=re.M))
    return n_tasks, n_bugs


def emit_brief(payload) -> None:
    tasks, bugs = open_counts(payload)
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": BRIEF.format(tasks=tasks, bugs=bugs),
    }}))


def count_discovery(payload, d: str) -> int:
    path = os.path.join(d, "state", f"{payload.get('session_id', 'unknown')}.json")
    try:
        with open(path, encoding="utf-8") as fh:
            state = json.load(fh)
    except Exception:
        state = {"discovery": 0}
    state["discovery"] = state.get("discovery", 0) + 1
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(state, fh)
    return state["discovery"]


def main() -> None:
    if os.environ.get("ROUTING_OBSERVE", "").lower() == "off":
        sys.exit(0)
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    event = payload.get("hook_event_name")

    if event == "SessionStart":
        emit_brief(payload)
        sys.exit(0)

    d = routing_dir(payload)

    if event in ("SubagentStart", "SubagentStop"):
        log_dispatch(payload, d)
        sys.exit(0)

    role = (payload.get("agent_type") or "").strip().lower()
    if role not in MAIN_ALIASES:
        sys.exit(0)  # a subagent doing discovery is the system working as designed

    n = count_discovery(payload, d)
    threshold = int(os.environ.get("ROUTING_SCOUT_AT", "12"))
    if n < threshold or (n - threshold) % REPEAT_EVERY != 0:
        sys.exit(0)

    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PostToolUse",
        "additionalContext": (
            f"[routing] {n} discovery calls (Read/Grep/Glob) so far in the main session, "
            "billed at the highest rate in the system. If you are still mapping the "
            "codebase, that is scout's job: dispatch `scout` with a specific question and "
            "read its ~40-line answer instead. If you are past discovery, ignore this."
        ),
    }}))


if __name__ == "__main__":
    main()
