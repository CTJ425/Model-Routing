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

  PostToolUse(Agent|Task)       -> on a `builder` dispatch, restate the review policy.
      Every other failure mode in this system announces itself; a skipped review was
      the one that was completely silent. A background dispatch returns its launch,
      not its result, so the wording says "plan the review" there and "review now"
      only when the tool result really is the agent's.

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
    DEFAULT_REVIEW_TRIGGERS, load_config, normalize_role, project_dir,
)

REPEAT_EVERY = 8
DISPATCH_MAX_BYTES = 5 * 1024 * 1024


def routing_dir(payload) -> str:
    d = os.path.join(project_dir(payload), ".claude", "routing")
    os.makedirs(os.path.join(d, "state"), exist_ok=True)
    return d


def dispatch_max_bytes() -> int:
    raw = os.environ.get("ROUTING_DISPATCH_MAX_BYTES")
    if raw:
        try:
            n = int(raw)
            if n > 0:
                return n
        except (TypeError, ValueError):
            pass
    return DISPATCH_MAX_BYTES


def log_dispatch(payload, d: str) -> None:
    effort = payload.get("effort")
    effort_level = effort.get("level") if isinstance(effort, dict) else effort
    row = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "event": payload.get("hook_event_name"),
        "agent_type": payload.get("agent_type"),
        "agent_id": payload.get("agent_id"),
        "effort": effort_level,
        "session": payload.get("session_id"),
        # Recorded so the audit scripts read a path instead of reconstructing one.
        "transcript_path": payload.get("transcript_path"),
        "agent_transcript_path": payload.get("agent_transcript_path"),
    }
    path = os.path.join(d, "dispatch.jsonl")
    try:
        if os.path.getsize(path) > dispatch_max_bytes():
            try:
                archive_size = os.path.getsize(path + ".1")
            except OSError:
                archive_size = 0
            if os.path.getsize(path) > archive_size:
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
- **Roster.** This session plans, writes specs, and adjudicates.{scout_clause} `builder`
  implements; `reviewer` checks risk work{scribe_clause}.
  Delegation is pre-authorized — dispatch without asking. Dispatch by scoped name
  (`route:scout`, `route:builder`, ...). Per-role model tiers live in
  `.claude/route.config.json` (see `/route:config`).
- **Guards will ask** before this session edits production code{record_clause},
  dispatches `Explore`/`general-purpose`, or issues an unbounded Read over {read_kb}KB.
  An `ask` is policy, not an obstacle: take the cheaper path it names."""

REVIEW_TRIGGER_TEXT = {
    "no_red_green": "the change lacks a test that failed before and passes now",
    "persistent_state": "it touches state that outlives the process",
    "authorization": "it touches an authorization or access-control decision",
    "boundary": "it touches a boundary another system depends on",
    "silent_calculation": "it touches a calculation whose wrong answer is silent",
    "control_flow": "it changes control flow, error handling, concurrency, retry, or timeout behaviour",
    "builder_blocker": "builder reported a blocker",
}


def review_nudge(cfg, launched: bool = False) -> str:
    """`launched` means the tool result was the async launch, not the agent's result."""
    review = cfg.get("review") or {}
    policy = review.get("policy", "risk")
    if launched:
        lead = ("[routing] `builder` dispatched \u2014 this is the launch result, not the "
                "agent's. ")
        when = "When its completion notification arrives, apply"
        act = ("Do not dispatch `route:reviewer` until you hold builder's file list and "
               "builder's VERIFY line.")
    else:
        lead = "[routing] `builder` just returned. "
        when = "Before moving on, apply"
        act = ("If you are not skipping, dispatch `route:reviewer` now with the brief, "
               "builder's file list, and builder's VERIFY line.")
    if policy == "always":
        condition = "every builder round"
    else:
        configured = review.get("triggers")
        trigger_ids = (DEFAULT_REVIEW_TRIGGERS if configured is None else configured)
        if isinstance(trigger_ids, list):
            clauses = [REVIEW_TRIGGER_TEXT.get(str(item),
                       "the configured trigger `%s`" % item) for item in trigger_ids]
        else:
            clauses = list(REVIEW_TRIGGER_TEXT.values())
        if not clauses:
            return (
                lead + "`review.policy` is `risk`, but no automatic risk triggers are "
                "configured. Record that review was skipped, or dispatch `route:reviewer` "
                "if your task needs an explicit review."
            )
        condition = " or ".join(clauses)

    return (
        "%s%s the Step 4 review policy: review is required for %s. If you are skipping "
        "review, name in one line which trigger you checked. %s"
    ) % (lead, when, condition, act)


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
    scout_enabled = (cfg.get("scout") or {}).get("enabled", True)

    text = BRIEF_HEAD.format(
        read_kb=cfg["guard"].get("readKB", 32),
        scout_clause=" `scout` reads and compresses;" if scout_enabled else "",
        scribe_clause="; `scribe` records" if bookkeeping else "",
        record_clause=" or a tracking record" if bookkeeping else "",
    )
    if bookkeeping:
        tasks, bugs = open_counts(project, cfg)
        # Never turn an unreadable file into a fabricated zero. Omit only the unavailable
        # count; if both are unavailable, omit the whole line.
        counts = []
        if tasks is not None:
            counts.append("%d task(s)" % tasks)
        if bugs is not None:
            counts.append("%d open bug(s)" % bugs)
        if counts:
            text += "\n- **Open now:** " + ", ".join(counts) + "."

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
    if not (cfg.get("scout") or {}).get("enabled", True):
        return
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


ASYNC_LAUNCH_RE = re.compile(
    r"async\s+agent\s+launched|launched\s+successfully|started\s+in\s+background|task\s+id\s+.*running",
    re.I,
)


def is_async_launch(payload: dict) -> bool:
    for k in ("tool_result", "tool_response", "result", "tool_output"):
        val = payload.get(k)
        if not val:
            continue
        text = json.dumps(val) if isinstance(val, (dict, list)) else str(val)
        if ASYNC_LAUNCH_RE.search(text):
            return True
    return False


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
        "additionalContext": review_nudge(cfg, launched=is_async_launch(payload)),
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
