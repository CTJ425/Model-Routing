#!/usr/bin/env python3
"""PreToolUse guard that makes role boundaries real instead of prompt etiquette.

Four jobs, selected by tool_name.

  Read              — polices what gets pulled into the main session's context.
                      Replaying context dominates a routed session's spend: a large
                      file read once is re-billed on every remaining turn. Bounded
                      reads (`limit` set) always pass.
  Agent|Task        — polices who gets dispatched. A role turned off in
                      `roles.<role>.enabled` is denied outright; the built-in
                      discovery agents inherit the caller's model, so they do
                      scout's job at the caller's price.
  Write|Edit|...    — polices what a role may write, and rejects a future-dated
                      timestamp in a tracking record.
  Bash              — best-effort detection of writes that route around the file
                      tools. Where the command's literal write targets can be resolved,
                      each role gets the same scope through Bash that it gets through
                      Write/Edit; an unresolvable shape is denied for a role with a
                      write scope, and allowed for the main session. This is a backstop,
                      not a gate: the real enforcement for a read-only role is not
                      giving it Bash at all.

Every hook payload carries `agent_type`, so one script polices both the main session
and each subagent. Plugin subagents arrive namespaced ("route:builder"), which
_config.normalize_role strips.

Unknown roles are not policed: this guard owns the routing roles, not every agent
that may run in the repo.

Precedence for every tunable: environment variable > .claude/route.config.json > default.

Env overrides:
  ROUTING_GUARD=off           disable entirely
  ROUTING_MAIN=deny|ask|off   main-session severity
  ROUTING_READ_KB=<n>         main-session large-read threshold in KB (0 disables)
"""
import datetime
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _config import (  # noqa: E402
    ROUTE_ROLES, archive_paths, load_config, matches_any, normalize_role, project_dir,
    record_paths, rel_path, role_enabled,
)

READ_ONLY_ROLES = {"scout", "reviewer"}

READ_REASON = (
    "Reading {name} ({kb}KB) into the main session's context re-bills it on every "
    "remaining turn — context replay is most of a routed session's cost. Two cheaper "
    "paths: dispatch `scout` with a specific question, or re-issue this Read with "
    "`offset`/`limit` for just the part you need."
)

READ_REASON_NO_SCOUT = (
    "Reading {name} ({kb}KB) into the main session's context re-bills it on every "
    "remaining turn — context replay is most of a routed session's cost. Re-issue this "
    "Read with `offset`/`limit` for just the part you need."
)

ARCHIVE_REASON = (
    "`scribe` must not read {name} whole — an archive is larger than this role's context. "
    "Re-issue the Read with a `limit` to see the header, then prepend with `Edit` anchored "
    "on it; append with a Bash heredoc, locate with `grep -n`, inspect with "
    "`sed -n '<range>p'`."
)

TS_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}\b")
TS_TOLERANCE_S = 120
TS_REASON = (
    "{stamps} is not a valid past timestamp; it is now {now}. A record logs what already "
    "happened, so a future or malformed stamp is fabricated. Run "
    "`date '+%Y-%m-%d %H:%M:%S'` and write what it returns — never estimate, and never "
    "carry a stamp over from an earlier draft."
)

DISABLED_ROLE_REASON = (
    "`{name}` is turned off for this project: `roles.{role}.enabled` is false in "
    ".claude/route.config.json. Do this work another way, or re-enable the role with "
    "`/route:config roles.{role}.enabled=true`."
)

DISCOVERY_AGENTS = {"explore", "general-purpose"}
DISCOVERY_REASON = (
    "`{name}` inherits this session's model, so it maps the codebase at or near the "
    "highest rate in the system. `scout` is the same job on a cheap tier with a 40-line "
    "output ceiling: dispatch it with a specific question instead. Confirm only if you "
    "need a tool scout lacks."
)

DISCOVERY_REASON_NO_SCOUT = (
    "`{name}` inherits this session's model, so it maps the codebase at or near the "
    "highest rate in the system. Confirm only if a built-in discovery agent is "
    "genuinely required."
)

# Best-effort: does this shell command look like it writes to the filesystem?
# Deliberately over-inclusive. A false positive costs one confirmation; a false
# negative silently defeats every rule below.
BASH_WRITE_RE = re.compile(
    r"(?:^|[\s|;&(`])(?:sudo\s+)?"
    r"(?:tee|dd|truncate|install|patch|touch|mkdir|rmdir|rm|mv|cp|ln|chmod|chown)\b"
    r"|(?:^|[\s|;&(`])(?:sed|perl|ruby)\b[^|;&]*?\s-i\b"
    r"|(?:^|[\s|;&(`])(?:python3?|node|deno|bun)\b[^|;&]*?(?:open\s*\([^)]*['\"][wax]|writeFile)"
    r"|(?<![0-9<>])>>?(?!\s*(?:/dev/null|&\s*\d))"
)
BASH_VCS_MUTATION_RE = re.compile(
    r"(?:^|[\s|;&(`])git\s+(?:add|commit|push|reset|checkout|switch|restore|clean|apply|"
    r"cherry-pick|rebase|mv|rm)\b"
)

# Matches a balanced single- or double-quoted span so it can be blanked out before the
# write-detection regexes run. An unterminated quote has no mate and is left alone by
# construction -- there is nothing here for it to match.
_QUOTED_SPAN_RE = re.compile(r"(?<!\\)'[^']*'|(?<!\\)\"[^\"]*\"")


def _strip_quoted_spans(command: str) -> str:
    """Blank every balanced quoted span, for write-detection only. Target-resolution
    paths (`_scribe_redirect_in_scope` and friends) must keep seeing the raw command.
    """
    return _QUOTED_SPAN_RE.sub(" ", command)

# The exact command shape scribe.md prescribes and nothing else: `cat >>`, one
# one literal path target, an optional heredoc. A heredoc is a whole multi-line command
# -- opener, body, terminator -- not something a single-line regex can capture, so the
# grammar is applied in three parts: first line, then (when an opener is present) the
# remainder as body + terminator. Any deviation -- a second redirect, a pipe, a chain,
# substitution, an unquoted delimiter, a missing or malformed terminator, a stray
# command after the terminator -- fails to match and falls through to `ask`. A positive
# grammar instead of a denylist over shell strings: nothing needs to be enumerated to
# be excluded.
# Scribe may append through Bash, but truncation is never an allowed bookkeeping
# operation. Prepending belongs to Edit, so the exception is deliberately `cat >>` only.
_CAT_TARGET = r"cat[ \t]+>>[ \t]*([A-Za-z0-9._/-]+)"
SCRIBE_CAT_PLAIN_RE = re.compile(_CAT_TARGET + r"[ \t]*")
SCRIBE_CAT_HEREDOC_OPENER_RE = re.compile(
    _CAT_TARGET + r"[ \t]*(<<-?)[ \t]*(?:'([^'\n]*)'|\"([^\"\n]*)\")[ \t]*"
)


def _scribe_redirect_target(command: str):
    """Match the command against the two allowed shapes -- plain redirect or redirect
    with a quoted heredoc -- and return the literal target path, or None if the whole
    command does not fit the grammar.
    """
    stripped = command.rstrip()
    first_line, _, remainder = stripped.partition("\n")

    m = SCRIBE_CAT_PLAIN_RE.fullmatch(first_line)
    if m and remainder == "":
        return m.group(1)

    mh = SCRIBE_CAT_HEREDOC_OPENER_RE.fullmatch(first_line)
    if not mh:
        return None
    dashed = mh.group(2) == "<<-"
    delimiter = mh.group(3) if mh.group(3) is not None else mh.group(4)

    body_lines = remainder.split("\n")
    terminator = body_lines[-1]
    if dashed:
        term_ok = re.fullmatch(r"\t*" + re.escape(delimiter), terminator) is not None
    else:
        term_ok = terminator == delimiter
    if not term_ok:
        return None
    return mh.group(1)

# Best-effort resolution of the literal paths a shell command writes to. Deliberately
# narrow, and narrow in one direction only: every shape it cannot account for returns
# None, which callers read as "unknown", never as "safe". A chain operator, a command
# substitution, or a second line without a heredoc opener could each hide a target this
# grammar never sees, so any of them disqualifies the whole command.
_SHELL_CHAIN_RE = re.compile(r"[|;&`]|\$\(")
_REDIRECT_TARGET_RE = re.compile(r"(?<![0-9<>])>>?[ \t]*([^\s|;&<>()]+)")
# A target carrying a variable, a glob, or a brace is not the path that will be written.
# Resolving it as a literal would classify the wrong path and report the wrong reason.
_NON_LITERAL_RE = re.compile(r"[$*?~{}\[\]]")
# Verbs whose operands are paths, and which no file tool can express -- the reason a
# blanket Bash deny left builder unable to do in-scope work at all.
_WRITE_VERB_RE = re.compile(
    r"^(?:sudo[ \t]+)?(?:mkdir|rmdir|touch|rm|mv|cp|ln)\b(.*)$")
# `sed -i 's/a/b/' path`: the script is a quoted span, so it is already blank by the
# time the operands are split.
_INPLACE_EDIT_RE = re.compile(
    r"^(?:sudo[ \t]+)?(?:sed|perl|ruby)\b(?=.*[ \t]-i)(.*)$")


def _write_targets(command: str):
    """-> the literal paths this command appears to write, or None when the shape cannot
    be resolved. None means unknown, not safe."""
    scan = _strip_quoted_spans(command)
    head, _, body = scan.partition("\n")
    # A heredoc body is data. A second line with no heredoc opener above it is a second
    # command, which this single-command grammar does not cover.
    if body and "<<" not in head:
        return None
    if _SHELL_CHAIN_RE.search(head):
        return None
    targets = [m.group(1) for m in _REDIRECT_TARGET_RE.finditer(head)]
    stripped = head.strip()
    operands = _WRITE_VERB_RE.match(stripped) or _INPLACE_EDIT_RE.match(stripped)
    if operands:
        targets += [t for t in operands.group(1).split() if not t.startswith("-")]
    if any(_NON_LITERAL_RE.search(t) for t in targets):
        return None
    return targets or None


BASH_REASON = (
    "This Bash command looks like it writes to the filesystem, and `{role}` may not write "
    "{scope}. Writing through Bash routes around the file-tool guard; that is out of role, "
    "not a workaround. Report the blocker instead."
)

BUILDER_BASH_OUT_OF_SCOPE_REASON = (
    "This Bash command writes to {targets}, which is not a production path in "
    "`paths.prod`. Builder's write scope is the same through Bash as through "
    "`Write`/`Edit`. Report the blocker instead."
)

BUILDER_BASH_UNRESOLVED_REASON = (
    "This Bash command writes to the filesystem in a shape this guard cannot resolve to "
    "a target path, so it cannot be confirmed inside the production paths. Re-issue it as "
    "one simple command with literal paths, or use `Write`/`Edit`."
)

ARCHITECT_BASH_OUT_OF_SCOPE_REASON = (
    "This Bash command writes to {targets}, which is not a spec or test path. Architect "
    "owns the contract — the spec and the failing tests — and nothing else. It runs the "
    "failing test to read the trace; it does not implement. Report the blocker instead."
)

ARCHITECT_BASH_UNRESOLVED_REASON = (
    "This Bash command writes to the filesystem in a shape this guard cannot resolve to "
    "a target path, so it cannot be confirmed inside the spec and test paths. Re-issue it "
    "as one simple command with literal paths, or use `Write`/`Edit`."
)

REASONS = {
    ("main", "prod"): (
        "Main session is editing production code. That is expensive-model-priced "
        "implementation: dispatch `builder` with an inline brief or spec (see the `route` skill), or "
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
    ("architect", "prod"): (
        "Architect owns the contract, not the implementation: it writes the spec and the "
        "failing tests, then hands builder a path. Production code is builder's."
    ),
    ("architect", "doc"): "Architect writes the spec and failing tests only. Records belong to scribe.",
    ("architect", "record"): "Architect writes the spec and failing tests only. Records belong to scribe.",
    ("architect", "config"): "Architect writes the spec and failing tests only, not project config.",
}

RULES = {
    "main": {"prod": "@main", "record": "@main"},
    "architect": {"prod": "deny", "doc": "deny", "record": "deny", "config": "deny"},
    "builder": {"test": "deny", "doc": "deny", "record": "deny", "spec": "deny"},
    "scribe": {"prod": "deny", "test": "deny", "spec": "deny", "config": "deny"},
    "scout": {"*": "deny"},
    "reviewer": {"*": "deny"},
}


def respond(decision: str, reason: str) -> None:
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": decision,
        "permissionDecisionReason": reason,
    }}))
    sys.exit(0)


def main_severity(cfg) -> str:
    """-> the decision for a main-session write: 'deny', 'ask', or '' when turned off."""
    level = (os.environ.get("ROUTING_MAIN")
             or cfg["guard"].get("mainSeverity") or "ask").lower()
    if level == "off":
        return ""
    return "deny" if level == "deny" else "ask"


def classify(rel, cfg) -> str:
    if rel is None:
        return "outside"
    paths = cfg["paths"]
    specs = (paths.get("specs") or "").strip("/")
    docs = (paths.get("docs") or "").strip("/")
    if specs and (rel == specs or rel.startswith(specs + "/")):
        return "spec"
    if rel in record_paths(cfg):
        return "record"
    if docs and (rel == docs or rel.startswith(docs + "/")):
        return "doc"
    if matches_any(rel, paths.get("test")):
        return "test"
    if matches_any(rel, paths.get("prod")):
        return "prod"
    if rel.startswith(".claude/"):
        return "config"
    return "other"


def read_kb(cfg) -> int:
    raw = os.environ.get("ROUTING_READ_KB")
    if raw is None:
        raw = cfg["guard"].get("readKB", 32)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 32


def bad_stamps(body: str, now):
    out = []
    for s in sorted(set(TS_RE.findall(body or ""))):
        try:
            ts = datetime.datetime.strptime(s.replace("T", " "), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            out.append(s)          # syntactically fine, semantically impossible
            continue
        if (ts - now).total_seconds() > TS_TOLERANCE_S:
            out.append(s)
    return out


def now_in_timezone(name: str):
    """Return a naive wall-clock value in the configured IANA timezone.

    `zoneinfo` is available on Python 3.9+. The POSIX fallback keeps the plugin's
    Python 3.8 requirement without adding a dependency; each hook runs in its own
    process, so temporarily changing TZ cannot affect the parent session.
    """
    name = (name or "").strip()
    if not name or name.lower() in ("local", "system"):
        return datetime.datetime.now()

    try:
        from zoneinfo import ZoneInfo
        return datetime.datetime.now(ZoneInfo(name)).replace(tzinfo=None)
    except (ImportError, KeyError, OSError, ValueError):
        pass

    if hasattr(time, "tzset"):
        had_tz = "TZ" in os.environ
        old_tz = os.environ.get("TZ")
        try:
            os.environ["TZ"] = name
            time.tzset()
            return datetime.datetime.now()
        except (OSError, ValueError):
            pass
        finally:
            if had_tz:
                os.environ["TZ"] = old_tz
            else:
                os.environ.pop("TZ", None)
            time.tzset()
    return datetime.datetime.now()


def handle_dispatch(role, tool_input, cfg) -> None:
    spawned = (tool_input.get("subagent_type") or "").strip()
    spawned_role = normalize_role(spawned)
    # A disabled role is a deny, not an ask: confirming cannot supply what is missing,
    # and a role nobody may dispatch is the whole point of turning one off.
    if spawned_role in ROUTE_ROLES and not role_enabled(cfg, spawned_role):
        respond("deny", "[routing/%s] " % role + DISABLED_ROLE_REASON.format(
            name=spawned or spawned_role, role=spawned_role))
    if spawned_role in DISCOVERY_AGENTS or spawned.lower() in DISCOVERY_AGENTS:
        template = (DISCOVERY_REASON if role_enabled(cfg, "scout")
                    else DISCOVERY_REASON_NO_SCOUT)
        respond("ask", "[routing/%s] " % role + template.format(name=spawned))
    sys.exit(0)


def handle_read(role, tool_input, project, cfg) -> None:
    target = tool_input.get("file_path")
    rel = rel_path(target, project)
    # A bounded archive read is allowed. `Edit` refuses to touch a file that has not been
    # read, so denying every read left the prepend this message recommends mechanically
    # impossible and the Bash heredoc append as the only route — and `>>` appends, while a
    # newest-first archive needs a prepend. Reading a header to anchor an Edit is the
    # bounded retrieval this guard exists to encourage; only the whole-file read is refused.
    if (role == "scribe" and rel and rel in archive_paths(cfg)
            and not tool_input.get("limit")):
        respond("deny", "[routing/scribe] " + ARCHIVE_REASON.format(name=rel))
    # A subagent reading widely is the system working as designed, and a bounded read
    # is the retrieval pattern this guard exists to encourage.
    if role != "main" or tool_input.get("limit"):
        sys.exit(0)
    limit_kb = read_kb(cfg)
    if limit_kb <= 0 or not target:
        sys.exit(0)
    try:
        target_abs = target if os.path.isabs(target) else os.path.join(project, target)
        size = os.path.getsize(target_abs)
    except OSError:
        sys.exit(0)
    if size > limit_kb * 1024:
        template = (READ_REASON if role_enabled(cfg, "scout")
                    else READ_REASON_NO_SCOUT)
        respond("ask", "[routing/main] " + template.format(
            name=os.path.basename(target), kb=size // 1024))
    sys.exit(0)


def _scribe_redirect_in_scope(command: str, project: str, cfg: dict) -> bool:
    """Scribe's documented append (`cat >> <archive> <<'EOF'`) needs no confirmation
    when the command matches that exact shape and the target resolves inside paths.docs.
    """
    target = _scribe_redirect_target(command)
    if target is None:
        return False
    if any(part == ".." for part in target.split("/")):
        return False
    docs = (cfg["paths"].get("docs") or "").strip("/")
    if not docs or docs == ".":
        return False
    project_real = os.path.realpath(project)
    docs_real = os.path.realpath(os.path.join(project_real, docs))
    target_abs = target if os.path.isabs(target) else os.path.join(project, target)
    target_real = os.path.realpath(target_abs)
    return target_real == docs_real or target_real.startswith(docs_real + os.sep)


def handle_main_bash(command, project, cfg) -> None:
    """The Write/Edit nudge, applied to the same edit made through the shell.

    Without this the whole `@main` policy is one `sed -i` away from silence, and a
    session told to prefer Bash for file changes routes around it by construction.
    Resolution is best-effort, so an unresolved command falls through to allow: a guard
    that blocks the main session on a parse failure is worse than one that misses a case.
    """
    for target in _write_targets(command) or []:
        rel = rel_path(target, project)
        if rel is None:
            continue
        cls = classify(rel, cfg)
        if cls in ("prod", "record"):
            decision = main_severity(cfg)
            if decision:
                respond(decision, "[routing/main] " + REASONS[("main", cls)])
            sys.exit(0)
    sys.exit(0)


def handle_builder_bash(command, project, cfg) -> None:
    """Builder's Bash scope is its Write/Edit scope: a production path, or anything
    outside the repository.

    `mkdir`, `mv` and `rm` have no file-tool equivalent, so denying every write-shaped
    command made in-scope work impossible while reporting it as out of scope. Builder
    then stopped and reported a blocker, and the caller did the work at its own rate.
    """
    targets = _write_targets(command)
    if targets is None:
        respond("deny", "[routing/builder] " + BUILDER_BASH_UNRESOLVED_REASON)
    outside = []
    for target in targets:
        rel = rel_path(target, project)
        if rel is not None and classify(rel, cfg) != "prod":
            outside.append(rel)
    if outside:
        respond("deny", "[routing/builder] " + BUILDER_BASH_OUT_OF_SCOPE_REASON.format(
            targets=", ".join(sorted(set(outside))[:3])))
    sys.exit(0)


def handle_architect_bash(command, project, cfg) -> None:
    """Architect's Bash scope is its Write/Edit scope: a spec or test path, or anything
    outside the repository. It runs the failing test to read the trace; it does not
    implement, so a write to a production path is out of role."""
    targets = _write_targets(command)
    if targets is None:
        respond("deny", "[routing/architect] " + ARCHITECT_BASH_UNRESOLVED_REASON)
    outside = []
    for target in targets:
        rel = rel_path(target, project)
        if rel is not None and classify(rel, cfg) not in ("spec", "test"):
            outside.append(rel)
    if outside:
        respond("deny", "[routing/architect] " + ARCHITECT_BASH_OUT_OF_SCOPE_REASON.format(
            targets=", ".join(sorted(set(outside))[:3])))
    sys.exit(0)


def handle_bash(role, tool_input, project, cfg) -> None:
    if not cfg["guard"].get("bashWriteDetection", True):
        sys.exit(0)
    if role not in RULES:
        sys.exit(0)
    command = tool_input.get("command") or ""
    scan_command = _strip_quoted_spans(command)
    if role == "scribe" and BASH_VCS_MUTATION_RE.search(scan_command):
        respond("deny", "[routing/scribe] Scribe records outcomes but does not mutate "
                "version-control state.")
    if not BASH_WRITE_RE.search(scan_command):
        sys.exit(0)
    if role == "main":
        handle_main_bash(command, project, cfg)
    if role in READ_ONLY_ROLES:
        respond("deny", "[routing/%s] " % role + BASH_REASON.format(
            role=role, scope="anything at all — it is read-only"))
    if role == "builder":
        handle_builder_bash(command, project, cfg)
    if role == "architect":
        handle_architect_bash(command, project, cfg)
    if role == "scribe" and _scribe_redirect_in_scope(command, project, cfg):
        sys.exit(0)
    respond("deny", "[routing/%s] " % role + BASH_REASON.format(
        role=role, scope="outside %s/" % cfg["paths"]["docs"]))


def handle_write(role, tool_input, project, cfg) -> None:
    rel = rel_path(tool_input.get("file_path"), project)
    if rel is None:
        if role == "scribe":
            respond("deny", "[routing/scribe] Scribe may write only inside the configured "
                    "tracking directory.")
        sys.exit(0)
    cls = classify(rel, cfg)

    rules = RULES.get(role)
    if not rules:
        # Unknown roles are outside this plugin's policy, including timestamp policy.
        sys.exit(0)

    docs = (cfg["paths"].get("docs") or "").strip("/")
    if role == "scribe":
        in_docs = bool(docs and docs != "." and
                       (rel == docs or rel.startswith(docs + "/")))
        if not in_docs or cls in ("prod", "test", "spec", "config"):
            respond("deny", "[routing/scribe] Scribe may write only inside %s/." %
                    (docs or "the configured tracking directory"))

    if role == "builder" and cls != "prod":
        reason = REASONS.get((role, cls)) or (
            "Builder may write production-code paths only; the spec's Files list is "
            "the remaining task-level scope.")
        respond("deny", "[routing/builder] " + reason)

    if role == "architect" and cls not in ("spec", "test"):
        reason = REASONS.get((role, cls)) or (
            "Architect writes the spec and the failing tests only; everything else "
            "belongs to another role. Report the conflict instead.")
        respond("deny", "[routing/architect] " + reason)

    if cls == "record":
        body = tool_input.get("new_string") or tool_input.get("content") or ""
        timezone = (cfg.get("bookkeeping") or {}).get("timezone") or "UTC"
        now = now_in_timezone(timezone)
        ahead = bad_stamps(body, now)
        if ahead:
            respond("deny", "[routing/%s] " % role + TS_REASON.format(
                stamps=", ".join(ahead[:3]), now=now.strftime("%Y-%m-%d %H:%M:%S")))

    decision = rules.get(cls) or rules.get("*")
    if not decision:
        sys.exit(0)

    if decision == "@main":
        decision = main_severity(cfg)
        if not decision:
            sys.exit(0)

    reason = REASONS.get((role, cls)) or (
        "Role `%s` may not write %s files. See the `route` skill." % (role, cls))
    respond(decision, "[routing/%s] %s" % (role, reason))


def main() -> None:
    if os.environ.get("ROUTING_GUARD", "").lower() == "off":
        sys.exit(0)
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)  # never break the session on a malformed payload

    role = normalize_role(payload.get("agent_type"))
    tool_input = payload.get("tool_input") or {}
    tool = payload.get("tool_name")
    project = project_dir(payload)
    cfg = load_config(project)

    if tool in ("Agent", "Task"):
        handle_dispatch(role, tool_input, cfg)
    if tool == "Read":
        handle_read(role, tool_input, project, cfg)
    if tool == "Bash":
        handle_bash(role, tool_input, project, cfg)
    handle_write(role, tool_input, project, cfg)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        # A guard that crashes must not also break the session. Fail open, quietly.
        sys.exit(0)
