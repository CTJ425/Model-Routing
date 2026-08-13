#!/usr/bin/env python3
"""PreToolUse guard that makes role boundaries real instead of prompt etiquette.

Three jobs, selected by tool_name.

On Read it polices *what gets pulled into context*. Replaying context dominates a
routed session's spend, and a large file read once is re-billed on every remaining turn
of the session. Bounded reads (`limit` set) are always allowed. `scribe` is denied the
archives outright — it writes them but never needs to read them.

On Agent|Task it polices *who gets dispatched*. The built-in discovery agents inherit
the caller's model, so `Explore` does scout's job at the caller's price.

On Write|Edit|NotebookEdit it polices *what a role may write*, and rejects any
future-dated timestamp written into a tracking record — a record logs what already
happened, so a future stamp is fabricated. Every hook payload carries `agent_type`, so
one script can police both the main session and each subagent:

  main session  -> writing production code or a tracking record is the exact leak
                   that turns this project into a single-model session. Escalate to
                   the user (ask) instead of letting it happen silently.
  builder       -> production code only; tests and docs belong to other roles.
  scribe        -> docs/agent/ only.
  scout         -> read-only.

Unknown agent types are not policed: this guard owns the routing roles, not every
agent that may run in the repo.

Which paths count as "production code" is project-specific, so it is read from
`.claude/route.config.json` (`paths.prod`, a list of repo-relative prefixes) instead of
being hardcoded. `/route:init` writes this file; a missing or unreadable config falls
back to `["src/"]`.

Env overrides:
  ROUTING_GUARD=off   disable entirely
  ROUTING_MAIN=deny|ask|off   main-session severity (default ask)
  ROUTING_READ_KB=<n> main-session large-read threshold in KB (default 32; 0 disables)
"""
import datetime
import json
import os
import re
import sys

MAIN_ALIASES = {"", "main", "default", "root", "none"}
RECORDS = {
    "TASK.md", "TASK_ARCHIVE.md", "PROGRESS.md", "PROGRESS_ARCHIVE.md",
    "BUG_FIX.md", "FIXED_BUG.md", "CHANGELOG.md",
}
TEST_RE = re.compile(r"\.(test|spec)\.[tj]sx?$")

# A file this big read unbounded costs more than the read: it is re-billed as cache
# read on every later turn.
READ_KB_DEFAULT = 32
READ_REASON = (
    "Reading {name} ({kb}KB) into the main session's context re-bills it on every "
    "remaining turn — context replay is most of a routed session's cost. Two cheaper "
    "paths: dispatch `scout` with a specific question, or re-issue this Read with "
    "`offset`/`limit` for just the part you need."
)

# scribe writes these but never needs to read them; each is far larger than its context.
ARCHIVES = {"PROGRESS_ARCHIVE.md", "TASK_ARCHIVE.md", "FIXED_BUG.md", "CHANGELOG.md"}
ARCHIVE_REASON = (
    "`scribe` must not read {name} — it is far larger than this role's context and there "
    "is never a need. Prepend with `Edit` anchored on the file's `---` header line, append "
    "with a Bash heredoc, locate with `grep -n`, inspect with `sed -n '<range>p'`."
)

# A record is a log of what already happened, so a future timestamp in one is always a
# fabrication.
TS_RE = re.compile(r"\b\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\b")
TS_TOLERANCE_S = 120
TS_REASON = (
    "{stamps} is in the future; it is now {now}. A record logs what already happened, so "
    "a future timestamp is fabricated. Run `date '+%Y-%m-%d %H:%M:%S'` and write what it "
    "returns — never estimate, and never carry a stamp over from an earlier draft."
)

# Built-in agents that inherit the caller's model, i.e. do cheap work at the caller's price.
DISCOVERY_AGENTS = {"explore", "general-purpose"}
DISCOVERY_REASON = (
    "`{name}` inherits this session's model, so it maps the codebase at the highest rate "
    "in the system. `scout` is the same job on a cheap tier with a 40-line output ceiling: "
    "dispatch it with a specific question instead. Confirm only if you need a tool scout "
    "lacks (Write/Edit/Task)."
)

# role -> {path class: decision}. "*" applies to every class.
RULES = {
    "main": {"prod": "@main", "record": "@main"},
    "builder": {"test": "deny", "doc": "deny", "record": "deny", "spec": "deny"},
    "scribe": {"prod": "deny", "test": "deny", "spec": "deny", "config": "deny"},
    "scout": {"*": "deny"},
    "reviewer": {"*": "deny"},
}

REASONS = {
    ("main", "prod"): (
        "Main session is editing production code. That is expensive-model-priced "
        "implementation: dispatch `builder` with a spec path (see the `route` skill), or "
        "confirm this is a Lane 0 edit small enough that a dispatch would cost more than "
        "the edit."
    ),
    ("main", "record"): (
        "Main session is editing a tracking record. Bookkeeping is mechanical work at the "
        "most expensive rate in the system: dispatch `scribe` with the facts, or confirm "
        "this edit is too small to hand off."
    ),
    ("builder", "test"): (
        "Builder may not change test files. Tests come with the spec; a test that looks "
        "wrong is a spec conflict to report, not to edit."
    ),
    ("builder", "doc"): "Builder writes production code only. Records belong to scribe.",
    ("builder", "record"): "Builder writes production code only. Records belong to scribe.",
    ("builder", "spec"): "Builder implements the spec; it does not amend it. Report the conflict.",
}

DEFAULT_PROD_PATHS = ["src/"]
_CONFIG_CACHE = {}


def load_config(project: str) -> dict:
    if project in _CONFIG_CACHE:
        return _CONFIG_CACHE[project]
    path = os.path.join(project, ".claude", "route.config.json")
    try:
        with open(path, encoding="utf-8") as fh:
            cfg = json.load(fh)
    except Exception:
        cfg = {}
    _CONFIG_CACHE[project] = cfg
    return cfg


def prod_paths(project: str) -> list:
    cfg = load_config(project)
    paths = (cfg.get("paths") or {}).get("prod")
    if not paths or not isinstance(paths, list):
        return DEFAULT_PROD_PATHS
    return [p if p.endswith("/") else p + "/" for p in paths]


def classify(path: str, project: str) -> str:
    try:
        rel = os.path.relpath(os.path.abspath(path), project)
    except ValueError:
        return "other"
    if rel.startswith(".."):
        return "outside"
    parts = rel.split(os.sep)
    if rel.startswith("docs/agent/specs/"):
        return "spec"
    if len(parts) == 3 and rel.startswith("docs/agent/") and parts[2] in RECORDS:
        return "record"
    if rel.startswith("docs/"):
        return "doc"
    if TEST_RE.search(rel) or "/tests/" in rel or "/e2e/" in rel:
        return "test"
    if any(rel.startswith(p) for p in prod_paths(project)):
        return "prod"
    if rel.startswith(".claude/"):
        return "config"
    return "other"


def respond(decision: str, reason: str) -> None:
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": decision,
        "permissionDecisionReason": reason,
    }}))
    sys.exit(0)


def main() -> None:
    if os.environ.get("ROUTING_GUARD", "").lower() == "off":
        sys.exit(0)
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)  # never break the session on a malformed payload

    role = (payload.get("agent_type") or "").strip()
    role = "main" if role.lower() in MAIN_ALIASES else role
    tool_input = payload.get("tool_input") or {}

    if payload.get("tool_name") in ("Agent", "Task"):
        spawned = (tool_input.get("subagent_type") or "").strip()
        if spawned.lower() in DISCOVERY_AGENTS:
            respond("ask", f"[routing/{role}] " + DISCOVERY_REASON.format(name=spawned))
        sys.exit(0)

    if payload.get("tool_name") == "Read":
        target = tool_input.get("file_path")
        if role == "scribe" and target and os.path.basename(target) in ARCHIVES:
            respond("deny", "[routing/scribe] " + ARCHIVE_REASON.format(
                name=os.path.basename(target)))
        # A subagent reading widely is the system working as designed, and a bounded
        # read is the retrieval pattern this guard is trying to encourage.
        if role != "main" or tool_input.get("limit"):
            sys.exit(0)
        try:
            limit_kb = int(os.environ.get("ROUTING_READ_KB", READ_KB_DEFAULT))
        except ValueError:
            limit_kb = READ_KB_DEFAULT
        target = tool_input.get("file_path")
        if limit_kb <= 0 or not target:
            sys.exit(0)
        try:
            size = os.path.getsize(target)
        except OSError:
            sys.exit(0)  # unreadable or missing: not this guard's problem
        if size > limit_kb * 1024:
            respond("ask", "[routing/main] " + READ_REASON.format(
                name=os.path.basename(target), kb=size // 1024))
        sys.exit(0)

    target = tool_input.get("file_path")
    if not target:
        sys.exit(0)

    project = os.path.abspath(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    cls = classify(target, project)

    if cls == "record":
        body = tool_input.get("new_string") or tool_input.get("content") or ""
        now = datetime.datetime.now()
        ahead = [s for s in TS_RE.findall(body)
                 if (datetime.datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
                     - now).total_seconds() > TS_TOLERANCE_S]
        if ahead:
            respond("deny", f"[routing/{role}] " + TS_REASON.format(
                stamps=", ".join(sorted(set(ahead))[:3]),
                now=now.strftime("%Y-%m-%d %H:%M:%S")))

    rules = RULES.get(role)
    if not rules:
        sys.exit(0)

    decision = rules.get(cls) or rules.get("*")
    if not decision:
        sys.exit(0)

    if decision == "@main":
        level = os.environ.get("ROUTING_MAIN", "ask").lower()
        if level == "off":
            sys.exit(0)
        decision = "deny" if level == "deny" else "ask"

    reason = REASONS.get((role, cls))
    if not reason:
        reason = f"Role `{role}` may not write {cls} files. See the `route` skill."
    respond(decision, f"[routing/{role}] {reason}")


if __name__ == "__main__":
    main()
