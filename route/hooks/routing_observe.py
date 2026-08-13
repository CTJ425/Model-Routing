#!/usr/bin/env python3
"""Makes routing observable, so "we delegate" is a measurable claim and not a belief.

Five jobs, selected by hook_event_name:

  SessionStart                  -> put the routing rule in context. `route` is a skill,
      so it only runs if the main session decides to load it, and nothing else prompts
      that. A few hundred tokens once per session is the cheapest fix available.

  SubagentStart / SubagentStop  -> append one line to .claude/routing/dispatch.jsonl.
      This is the audit trail: which roles actually ran, at what effort, when, and
      which transcript file holds the turns — so the audit scripts need not guess at
      the harness's on-disk layout.

  PostToolUse(Read|Grep|Glob)   -> count discovery calls made *in the main session*.
      Broad discovery is the single largest avoidable cost in the loop, and it leaks
      silently because each individual Read looks cheap. Past a threshold the hook says
      so, in context, while the leak is still happening.

  PostToolUse(Agent|Task)       -> after a `builder` dispatch returns, restate the
      review policy. Every other failure mode in this system announces itself; a
      skipped review was the one that was completely silent.

  SessionEnd                    -> delete this session's state files.

Env overrides:
  ROUTING_OBSERVE=off      disable entirely
  ROUTING_SCOUT_AT=<n>     first nudge after n main-session discovery calls (default 12)
"""
import glob
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _config import (  # noqa: E402
    load_config, normalize_role, project_dir,
)

REPEAT_EVERY = 8
DISPATCH_MAX_BYTES = 5 * 1024 * 1024


def routing_dir(payload) -> str:
    d = os.path.join(project_dir(payload), ".claude", "routing")
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
        # Recorded so the audit scripts read a path instead of reconstructing one.
        "transcript_path": payload.get("transcript_path"),
        "agent_transcript_path": payload.get("agent_transcript_path"),
    }
    path = os.path.join(d, "dispatch.jsonl")
    try:
        if os.path.getsize(path) > DISPATCH_MAX_BYTES:
            os.replace(path, path + ".1")
    except OSError:
        pass
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({k: v for k, v in row.items() if v is not None},
                            ensure_ascii=False) + "\n")


BRIEF_HEAD = """[routing] This project delegates. Before acting on a feature or a bug, load the
`route` skill and state the lane in one line.

- **Cost here is context replay, not output.** Replaying context into the main
  session's window is billed on every remaining turn of the session, so bulk content
  goes to a subagent even when the task looks trivial.
- **Roster.** This session plans, writes specs, and adjudicates. `scout` reads and
  compresses; `builder` implements; `reviewer` checks risk work{scribe_clause}.
  Delegation is pre-authorized — dispatch without asking. Dispatch by scoped name
  (`route:scout`, `route:builder`, ...). Per-role model tiers live in
  `.claude/route.config.json` (see `/route:config`).
- **Guards will ask** before this session edits production code{record_clause},
  dispatches `Explore`/`general-purpose`, or issues an unbounded Read over {read_kb}KB.
  An `ask` is policy, not an obstacle: take the cheaper path it names."""

OPEN_LINE = "\n- **Open now:** {tasks} task(s), {bugs} open bug(s)."

REVIEW_NUDGE = (
    "[routing] `builder` just returned. Before recording, apply the Step 4 review policy: "
    "review is required if the change is not covered by a test that failed before and "
    "passes now, or if it touches persisted state, an authorization decision, a boundary "
    "another system depends on, a silently-wrong calculation, or builder reported a "
    "blocker. If you are skipping review, name in one line which of those you checked. If "
    "you are not skipping, dispatch `route:reviewer` now with the brief, builder's file "
    "list, and builder's TESTS line."
)


def _hot(cfg, key):
    rec = ((cfg.get("bookkeeping") or {}).get("records") or {}).get(key) or {}
    return rec.get("hot")


def open_counts(project, cfg):
    """-> (open task entries, open bug entries); None when the file is unreadable."""
    docs = (cfg["paths"]["docs"] or "").strip("/")

    def read(name):
        if not name:
            return None
        try:
            with open(os.path.join(project, *(docs.split("/") + [name])),
                      encoding="utf-8") as fh:
                return fh.read()
        except OSError:
            return None

    tasks = read(_hot(cfg, "tasks"))
    if tasks is None:
        n_tasks = None
    else:
        try:
            open_re = re.compile(
                (cfg.get("bookkeeping") or {}).get("openTaskPattern") or r"^", re.M)
        except re.error:
            open_re = re.compile(r"^- \*\*Status\*\*:(?![ \t]*✅)", re.M)
        n_tasks = sum(1 for block in re.split(r"^### ", tasks, flags=re.M)[1:]
                      if open_re.search(block))

    bugs = read(_hot(cfg, "bugs"))
    # The hot bug file holds only open bugs by construction — fixed ones move out.
    n_bugs = None if bugs is None else len(re.findall(r"^### ", bugs, flags=re.M))
    return n_tasks, n_bugs


def emit_brief(payload) -> None:
    project = project_dir(payload)
    cfg = load_config(project)
    bookkeeping = bool((cfg.get("bookkeeping") or {}).get("enabled"))

    text = BRIEF_HEAD.format(
        read_kb=cfg["guard"].get("readKB", 32),
        scribe_clause="; `scribe` records" if bookkeeping else "",
        record_clause=" or a tracking record" if bookkeeping else "",
    )
    if bookkeeping:
        tasks, bugs = open_counts(project, cfg)
        # Printing "? task(s)" teaches the session to distrust the whole brief.
        if tasks is not None or bugs is not None:
            text += OPEN_LINE.format(tasks=tasks if tasks is not None else 0,
                                     bugs=bugs if bugs is not None else 0)

    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": text,
    }}))


def count_discovery(payload, d: str) -> int:
    """Append-only tally. A read-modify-write counter loses increments whenever two
    hooks for the same session overlap, which is exactly when the count matters."""
    path = os.path.join(d, "state", "%s.count" % payload.get("session_id", "unknown"))
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("1\n")
    with open(path, encoding="utf-8") as fh:
        return sum(1 for _ in fh)


def handle_discovery(payload, d: str) -> None:
    n = count_discovery(payload, d)
    cfg = load_config(project_dir(payload))
    try:
        threshold = int(os.environ.get("ROUTING_SCOUT_AT")
                        or cfg["guard"].get("scoutAt", 12))
    except (TypeError, ValueError):
        threshold = 12
    if threshold <= 0 or n < threshold or (n - threshold) % REPEAT_EVERY != 0:
        return
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PostToolUse",
        "additionalContext": (
            "[routing] %d discovery calls (Read/Grep/Glob) so far in the main session, "
            "billed at the highest rate in the system. If you are still mapping the "
            "codebase, that is scout's job: dispatch `scout` with a specific question "
            "and read its ~40-line answer instead. If you are past discovery, ignore "
            "this." % n
        ),
    }}))


def handle_dispatch_return(payload) -> None:
    cfg = load_config(project_dir(payload))
    review = cfg.get("review") or {}
    if review.get("policy") == "never" or not review.get("nudge", True):
        return
    spawned = normalize_role((payload.get("tool_input") or {}).get("subagent_type"))
    if spawned != "builder":
        return  # reviewer returning is the normal path; silence is correct there
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PostToolUse",
        "additionalContext": REVIEW_NUDGE,
    }}))


def clear_state(payload, d: str) -> None:
    session = payload.get("session_id")
    if not session:
        return
    for path in glob.glob(os.path.join(d, "state", "%s.*" % session)):
        try:
            os.remove(path)
        except OSError:
            pass


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

    if event == "SessionEnd":
        clear_state(payload, d)
        sys.exit(0)

    if event in ("SubagentStart", "SubagentStop"):
        log_dispatch(payload, d)
        sys.exit(0)

    # A subagent doing discovery, or spawning nothing, is the system working as designed.
    if normalize_role(payload.get("agent_type")) != "main":
        sys.exit(0)

    if payload.get("tool_name") in ("Agent", "Task"):
        handle_dispatch_return(payload)
        sys.exit(0)

    handle_discovery(payload, d)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)
