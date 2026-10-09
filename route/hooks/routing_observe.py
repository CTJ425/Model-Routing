#!/usr/bin/env python3
"""Makes routing observable, so "we delegate" is a measurable claim and not a belief.

Six jobs, selected by hook_event_name. Every one of them informs the main session; none
blocks it. Whether to delegate is the main session's call.

  SessionStart                  -> put the roster and the cost model in context. `route`
      is a skill, so it only runs if the main session decides to load it, and nothing
      else tells it the skill exists or what it holds. A few hundred tokens once per
      session is the cheapest way to let it decide with the facts.

  SubagentStart / SubagentStop  -> append one line to .claude/routing/dispatch.jsonl.
      This is the audit trail: which roles actually ran, at what effort, when, and
      which transcript file holds the turns — so the audit scripts need not guess at
      the harness's on-disk layout.

  PostToolUse(Read|Grep|Glob)   -> count discovery calls made *in the main session*.
      Broad discovery is the single largest avoidable cost in the loop, and it leaks
      silently because each individual Read looks cheap. Past a threshold the hook says
      so, in context, while the leak is still happening.

  PostToolUse(Agent|Task)       -> on a `builder` dispatch, restate the review policy.
      A background dispatch returns its launch, not its result, so the wording says
      "plan the review" there and "review now" only when the tool result really is the
      agent's.

  PostToolUse(Write|Edit|NotebookEdit) -> remember the production files written since
      the last `reviewer` dispatch, and on the main session's first such write remind it
      of the review policy, once per round. Replays found the review skipped on a
      silent-calculation task in 2 of 3 sessions; the builder-return reminder cannot
      cover a session that implemented the change itself. A reminder, not a gate: it
      used to block the first Stop, and no longer does.

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
    DEFAULT_REVIEW_TRIGGERS, ROUTE_ROLES, load_config, matches_any, normalize_role,
    project_dir, rel_path, role_enabled, route_role, strip_worktree,
)

REPEAT_EVERY = 8
DISPATCH_MAX_BYTES = 5 * 1024 * 1024
# The harness does not always report a role on SubagentStop. See log_dispatch.
UNKNOWN_ROLE = "unknown"


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
        # An empty agent_type normalizes to "main", so a row left blank credits a
        # subagent's turns to the main thread in /route:audit. Record it as explicitly
        # unattributed instead: a role the audit cannot name must not read as a role it can.
        "agent_type": payload.get("agent_type") or UNKNOWN_ROLE,
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


BRIEF_HEAD = """[routing] The `route` subagents are available in this project. Whether to
delegate to them is your call; nothing here requires it.

- **Where the cost is.** Context replay, not output: whatever enters this session's
  context is re-billed on every remaining turn. A subagent keeps bulk (a large file, a
  long log, a multi-file edit) out of it and returns a short answer, but it pays a cold
  start of its own, so a job that fits inside the prompt you would write to hand it over
  is cheaper done here.
- **Roster.** This session plans, decides and adjudicates.{roster_clause}
  Per-role model tiers live in `.claude/route.config.json` (see `/route:config`).
- **The `route` skill** is a playbook, not a procedure: lanes, the brief and spec
  formats, the review triggers and the dispatch-floor arithmetic. Load it when you are
  about to delegate a build, a review or a record and want those rules; skip it for
  work you do here.
- **Hints, not gates.** A large unbounded read, or a built-in agent that runs on this
  session's model (`Explore`, `Plan`, `general-purpose`, `claude`), gets a cost hint
  in context and goes through. What each subagent may write is still enforced by the
  guard.{edit_clause}"""

ROSTER_CLAUSE = {
    "scout": "`scout` reads and compresses",
    "builder": "`builder` implements",
    "reviewer": "`reviewer` checks risk work",
    "scribe": "`scribe` records",
}


def roster_clause(cfg, bookkeeping: bool) -> str:
    """The roster names only roles that may actually be dispatched.

    Naming a role that `roles.<role>.enabled` turns off would send the session into a
    guard denial, which is a worse way to learn the roster than reading it.
    """
    live = [r for r in ROUTE_ROLES
            if role_enabled(cfg, r) and (r != "scribe" or bookkeeping)]
    if not live:
        return (" No route role is available for dispatch, so this session does the "
                "work itself.")
    return (
        " %s.\n  Delegation is pre-authorized — dispatch without asking. Dispatch by "
        "scoped name (%s)." % ("; ".join(ROSTER_CLAUSE[r] for r in live),
                               ", ".join("`route:%s`" % r for r in live))
    )


def edit_clause(cfg, bookkeeping: bool) -> str:
    """Names the main-session edits this project's guard still asks about or denies.
    Empty by default: `guard.mainSeverity` is off, and an off role is absorbed silently
    (see routing_guard._main_write_absorbed)."""
    level = (os.environ.get("ROUTING_MAIN") or (cfg.get("guard") or {}).get(
        "mainSeverity") or "off").lower()
    if level not in ("ask", "deny"):
        return ""
    try:
        at = int(os.environ.get("ROUTING_BUILDER_AT_K")
                 or (cfg.get("guard") or {}).get("builderAtK", 60))
    except (TypeError, ValueError):
        at = 60
    targets = []
    if role_enabled(cfg, "builder"):
        targets.append("production code with its context over %dk tokens or unknown" % at
                       if at > 0 and level == "ask" else "production code")
    if bookkeeping and role_enabled(cfg, "scribe"):
        targets.append("a tracking record")
    if not targets:
        return ""
    verb = "denies" if level == "deny" else "asks before"
    return "\n  This project's guard also %s this session editing %s." % (
        verb, " or ".join(targets))


REVIEW_TRIGGER_TEXT = {
    "no_red_green": "the change lacks a test that failed before and passes now",
    "persistent_state": "it touches state that outlives the process",
    "authorization": "it touches an authorization or access-control decision",
    "boundary": "it touches a boundary another system depends on",
    "silent_calculation": "it touches a calculation whose wrong answer is silent",
    "control_flow": "it changes control flow, error handling, concurrency, retry, or timeout behaviour",
    "builder_blocker": "builder reported a blocker",
}


def trigger_ids(cfg, skip=()) -> list:
    """-> the review trigger ids in force; empty when `review.triggers` is an empty list.
    `skip` drops ids that cannot apply to the caller."""
    configured = (cfg.get("review") or {}).get("triggers")
    ids = DEFAULT_REVIEW_TRIGGERS if configured is None else configured
    if not isinstance(ids, list):
        ids = list(REVIEW_TRIGGER_TEXT)
    return [str(i) for i in ids if i not in skip]


def trigger_clauses(cfg, skip=()) -> list:
    """-> the review triggers in force, as sentence fragments."""
    return [REVIEW_TRIGGER_TEXT.get(i, "the configured trigger `%s`" % i)
            for i in trigger_ids(cfg, skip)]


# Triggers where a wrong answer stays silent: green tests, a clean run and the absence of
# an error all look the same whether the change is right or wrong. These get a firm
# "dispatch" rather than a "consider".
STRONG_TRIGGER_PHRASE = {
    "persistent_state": "state that outlives the process",
    "authorization": "an authorization or access-control decision",
    "silent_calculation": "a calculation whose wrong answer is silent",
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
        clauses = trigger_clauses(cfg)
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

    text = BRIEF_HEAD.format(
        roster_clause=roster_clause(cfg, bookkeeping),
        edit_clause=edit_clause(cfg, bookkeeping),
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
    if not role_enabled(cfg, "scout"):
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
    """A background dispatch returns its launch, not the agent's result.

    Claude Code reports that as `status: "async_launched"`, and has run subagents in the
    background by default since 2.1.198 (always, in an interactive session with fork mode
    on). A structured status outranks the text: the same response carries the brief in
    its `prompt` field, and a brief can say anything. Older builds returned launch text.
    """
    for k in ("tool_result", "tool_response", "result", "tool_output"):
        val = payload.get(k)
        if not val:
            continue
        status = val.get("status") if isinstance(val, dict) else None
        if status in ("async_launched", "completed"):
            return status == "async_launched"
        text = json.dumps(val) if isinstance(val, (dict, list)) else str(val)
        if ASYNC_LAUNCH_RE.search(text):
            return True
    return False


def handle_dispatch_return(payload) -> None:
    cfg = load_config(project_dir(payload))
    review = cfg.get("review") or {}
    if review.get("policy") == "never" or not review.get("nudge", True):
        return
    if not role_enabled(cfg, "reviewer"):
        return  # the nudge's only action is to dispatch a role that cannot run
    spawned = route_role((payload.get("tool_input") or {}).get("subagent_type"))
    if spawned != "builder":
        return  # reviewer returning is the normal path; silence is correct there
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PostToolUse",
        "additionalContext": review_nudge(cfg, launched=is_async_launch(payload)),
    }}))


WRITE_TOOLS = ("Write", "Edit", "NotebookEdit")


def _pending_path(payload, d: str):
    session = payload.get("session_id")
    return os.path.join(d, "state", "%s.review" % session) if session else None


def note_write(payload, d: str):
    """Record a production-code write, from the main session or any subagent.

    -> the file's relative path when it opens a round (nothing was pending since the last
    reviewer dispatch), else None."""
    path = _pending_path(payload, d)
    tool_input = payload.get("tool_input") or {}
    target = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not path or not target:
        return None
    project = project_dir(payload)
    cfg = load_config(project)
    rel = strip_worktree(rel_path(target, project))
    paths = cfg.get("paths") or {}
    if not rel or not matches_any(rel, paths.get("prod")) or matches_any(rel, paths.get("test")):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            seen = [line for line in fh.read().split("\n") if line]
    except OSError:
        seen = []
    if rel in seen:
        return None
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(rel + "\n")
    return None if seen else rel


def clear_review(payload, d: str) -> None:
    path = _pending_path(payload, d)
    if path and os.path.exists(path):
        os.remove(path)


def review_hint(cfg, rel: str) -> str:
    policy = (cfg.get("review") or {}).get("policy", "risk")
    head = "[routing] Production code changed: %s. " % rel
    if not role_enabled(cfg, "reviewer"):
        return head + ("`roles.reviewer.enabled` is false, so when this round is done, "
                       "review the diff yourself against the Step 4 triggers and say so "
                       "in one line.")
    if policy == "always":
        return head + ("`review.policy` is `always`: when this round is done, dispatch "
                       "`route:reviewer` with the diff.")
    # `builder_blocker` is a builder's report; this session wrote the change.
    ids = trigger_ids(cfg, skip=("builder_blocker",))
    if not ids:
        return head + ("`review.policy` is `risk` and no automatic risk triggers are "
                       "configured: dispatch `route:reviewer` with the diff only if you "
                       "judge this round needs one. This reminder appears once per round.")
    strong = [STRONG_TRIGGER_PHRASE[i] for i in ids if i in STRONG_TRIGGER_PHRASE]
    rest = [REVIEW_TRIGGER_TEXT.get(i, "the configured trigger `%s`" % i)
            for i in ids if i not in STRONG_TRIGGER_PHRASE]
    text = head
    if strong:
        text += ("If this round touches %s, dispatch `route:reviewer` with the diff before "
                 "you finish: a green test only shows the test agreed with the code, and "
                 "these are the failures that stay silent. " % ", ".join(strong))
    if rest:
        lead = ("Also dispatch it" if strong else
                "When this round is done, dispatch `route:reviewer` with the diff")
        text += "%s if any of these holds: %s. " % (lead, "; ".join(rest))
    return text + ("Otherwise say in one line which you checked and why none does (the "
                   "`route` skill, Step 4, has the detail). This reminder appears once "
                   "per round.")


def handle_main_write(payload, rel: str) -> None:
    cfg = load_config(project_dir(payload))
    review = cfg.get("review") or {}
    if review.get("policy") == "never" or not review.get("nudge", True):
        return
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PostToolUse",
        "additionalContext": review_hint(cfg, rel),
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

    if payload.get("tool_name") in WRITE_TOOLS:
        opened = note_write(payload, d)
        if opened and normalize_role(payload.get("agent_type")) == "main":
            handle_main_write(payload, opened)
        sys.exit(0)

    # A subagent doing discovery, or spawning nothing, is the system working as designed.
    if normalize_role(payload.get("agent_type")) != "main":
        sys.exit(0)

    if payload.get("tool_name") in ("Agent", "Task"):
        if route_role((payload.get("tool_input") or {}).get("subagent_type")) == "reviewer":
            clear_review(payload, d)
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
