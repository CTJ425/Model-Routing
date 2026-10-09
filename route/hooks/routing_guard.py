#!/usr/bin/env python3
"""PreToolUse guard that makes role boundaries real instead of prompt etiquette.

Four jobs, selected by tool_name.

  Read              — tells the main session what a large unbounded read will cost
                      (a hint, never a prompt: whether to read it here or hand it to
                      scout is the main session's call). Bounded reads (`limit` set)
                      pass silently.
  Agent|Task        — polices who gets dispatched. A role turned off in
                      `roles.<role>.enabled` is denied outright, and so is a
                      route role that would run on a tier other than
                      `models.<role>`. The built-in discovery agents inherit the
                      caller's model, so they do scout's job at the caller's price:
                      that gets a hint, and the dispatch goes through. A `builder`
                      dispatch must carry a brief or a spec (`guard.builderNeedsSpec`),
                      and the builder may then write only the files that names.
  Write|Edit|...    — polices what a role may write, and rejects a future-dated
                      timestamp in a tracking record.
  Bash              — best-effort detection of writes that route around the file
                      tools. Where the command's literal write targets can be resolved,
                      each role gets the same scope through Bash that it gets through
                      Write/Edit; an unresolvable shape is denied for a role with a
                      write scope, and allowed for the main session. This is a backstop,
                      not a gate: the real enforcement for a read-only role is not
                      giving it Bash at all.

The main session decides what to delegate. By default (`guard.mainSeverity: off`) the
guard does not ask about its production-code or tracking-record writes; `ask` or `deny`
there is a project's choice to push that work to builder or scribe.

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
  ROUTING_BUILDER_AT_K=<n>    main-session context (k tokens) from which production
                              writes ask (0 = always ask)
"""
import datetime
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _config import (  # noqa: E402
    archive_paths, load_config, matches_any, normalize_role, project_dir,
    record_paths, rel_path, role_enabled, route_role, strip_worktree,
)

READ_ONLY_ROLES = {"scout", "reviewer"}

READ_HINT = (
    "{name} is {kb}KB, roughly {ktok}k tokens. Read whole, it stays in this context and "
    "is re-billed on every later turn. Your call: keep it here if you will edit it or "
    "need most of it; take a part with `offset`/`limit` or `grep` if you know where to "
    "look; dispatch `route:scout` if you only need a fact, a count or a summary from it."
)

READ_HINT_NO_SCOUT = (
    "{name} is {kb}KB, roughly {ktok}k tokens. Read whole, it stays in this context and "
    "is re-billed on every later turn. If you know where to look, take a part with "
    "`offset`/`limit` or `grep`."
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

# `models.<role>` only takes effect when the main session passes it as `model` on the
# Agent call; without it the agent's frontmatter tier runs. A replay found 1 session in 4
# omitting it, so a configured Sonnet role silently ran on Opus.
MODEL_ALIASES = {"haiku", "sonnet", "opus"}
AGENTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agents")
MODEL_REASON = (
    "`models.{role}` is `{want}` in .claude/route.config.json, but this dispatch would run "
    "`{got}` ({source}). Dispatch it again with `model: \"{want}\"`."
)


def frontmatter_model(role: str):
    """-> the `model:` alias in this plugin's agent file for `role`, or None."""
    try:
        with open(os.path.join(AGENTS_DIR, role + ".md"), encoding="utf-8") as fh:
            head = fh.read(2048).lstrip("\ufeff").replace("\r\n", "\n")
    except OSError:
        return None
    block = re.match(r"---\n(.*?)\n---", head, re.S)  # the frontmatter block only
    m = block and re.search(r"^model:\s*([A-Za-z0-9._-]+)\s*$", block.group(1), re.M)
    return m.group(1).lower() if m else None


# Built-in agent types that run on this session's model, or near it, with no tier of
# their own. Matched exactly: a plugin agent such as `other:claude` declares its own.
# `fork` is left out on purpose: fork mode, on by default in interactive sessions, spawns
# forks routinely, and asking on each one stalls unattended workflows.
DISCOVERY_AGENTS = {"explore", "plan", "general-purpose", "claude"}
# An Agent call that names no type gets this one.
DEFAULT_AGENT = "general-purpose"
DISCOVERY_HINT = (
    "`{name}` inherits this session's model, so it runs at or near the highest rate in "
    "the system. `route:scout` is read-only discovery on a cheap tier with a 40-line "
    "output ceiling. Use `{name}` when you need what scout lacks (Bash, writing, "
    "planning); otherwise `route:scout` with one specific question costs less."
)

DISCOVERY_HINT_NO_SCOUT = (
    "`{name}` inherits this session's model, so it runs at or near the highest rate in "
    "the system. Fine when the job needs it; for plain codebase mapping, reading the "
    "files here with `grep` and `offset`/`limit` may cost less."
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
_REDIRECT_TARGET_RE = re.compile(r"(?<![0-9<>])>>?[ \t]*([^\s|;&<>()]+)")
# A heredoc body is data, wherever in the command it opens. Parsing it for targets, or
# reading its lines as further commands, is what limited resolution to a single line.
_HEREDOC_OPENER_RE = re.compile(
    r"<<-?[ \t]*(?:'([^'\n]*)'|\"([^\"\n]*)\"|([A-Za-z_][A-Za-z0-9_]*))")
# `2>&1` and `>&2` duplicate a file descriptor. Neither writes to a path, and the `&` in
# them is not a chain operator -- read as one, it made `cmd > file 2>&1` unresolvable,
# which is the shape of every verify command builder runs.
_FD_DUP_RE = re.compile(r"\d*>&\d+")
# Separators this grammar resolves segment by segment.
_SEGMENT_SPLIT_RE = re.compile(r"&&|\|\||;|\n")
# What is left after splitting and still hides a target: a pipe (`tee`), a background
# `&`, a backtick or a command substitution. Any of them disqualifies the whole command.
_OPAQUE_RE = re.compile(r"[|`&]|\$\(")
_CD_RE = re.compile(r"^(?:sudo[ \t]+)?cd(?:[ \t]|$)")
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


def _strip_heredoc_bodies(command: str):
    """-> the command's code lines with every heredoc body dropped, or None when an
    opener has no terminator. Runs on the raw command: `_strip_quoted_spans` blanks a
    quoted delimiter, and the delimiter is what finds the end of the body."""
    lines = command.split("\n")
    out, i = [], 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        i += 1
        for m in _HEREDOC_OPENER_RE.finditer(line):
            delimiter = m.group(1) or m.group(2) or m.group(3)
            while i < len(lines) and lines[i].strip() != delimiter:
                i += 1
            if i >= len(lines):
                return None          # unterminated: the shape is not resolvable
            i += 1                   # the terminator line is not code either
    return out


def _write_targets(command: str):
    """-> the literal paths this command appears to write, or None when the shape cannot
    be resolved. None means unknown, not safe.

    Resolution is segment by segment. A chained command is not one target the guard
    cannot see; it is several it can, and denying the whole shape denied builder the
    scratchpad its own scope allows -- measured as 71% of its Bash denials.
    """
    lines = _strip_heredoc_bodies(command)
    if lines is None:
        return None
    scan = _strip_quoted_spans("\n".join(lines))
    scan = _FD_DUP_RE.sub(" ", scan).replace("&>", ">")
    targets, cwd_moved = [], False
    for segment in _SEGMENT_SPLIT_RE.split(scan):
        segment = segment.strip()
        if not segment:
            continue
        if _OPAQUE_RE.search(segment):
            return None
        if _CD_RE.match(segment):
            cwd_moved = True
            continue
        found = [m.group(1) for m in _REDIRECT_TARGET_RE.finditer(segment)]
        operands = _WRITE_VERB_RE.match(segment) or _INPLACE_EDIT_RE.match(segment)
        if operands:
            found += [t for t in operands.group(1).split() if not t.startswith("-")]
        # Past a `cd`, a relative path no longer resolves against the project root.
        if cwd_moved and any(not t.startswith("/") for t in found):
            return None
        targets += found
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
}

# Which role's write scope a main-session class falls into, when that role is off and
# the main session absorbs its work instead of being asked about it.
CLASS_OWNER = {"prod": "builder", "record": "scribe"}


# Set by main() from the payload: the main session's transcript, read for its context size.
TRANSCRIPT = None
AGENT_ID = None
SESSION = None
TAIL_BYTES = 512 * 1024


_CTX = {}


def main_context_tokens(path):
    """-> the context the main session's last API call carried (input + cache read +
    cache write), from the transcript's last real usage row, or None when unknown.
    Read once per hook call, so the decision and its reason see the same number."""
    if path in _CTX:
        return _CTX[path]
    _CTX[path] = _read_context(path)
    return _CTX[path]


def _read_context(path):
    if not path:
        return None
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            fh.seek(max(0, fh.tell() - TAIL_BYTES))
            lines = fh.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        try:
            row = json.loads(line)
            msg = row.get("message") or {}
            usage = msg.get("usage")
            if row.get("isSidechain") or msg.get("model") == "<synthetic>":
                continue  # a subagent's row, or a harness message with no real call
            total = sum(int(usage.get(k) or 0) for k in (
                "input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
        except Exception:
            continue
        if total > 0:
            return total
    return None


def builder_at(cfg) -> int:
    """-> guard.builderAtK in tokens. The default of 60k is an estimate, not a measurement.

    Measured (docs/field-reports/2026-09-23-*), fresh sessions of about 26k context: the
    builder alone (full-roster cost minus its reviewer, scout and scribe runs, against
    all roles off) added $0.19 per task on the route repo and $0.38 on stock-pnl-web
    ($0.24-0.69 per task). Tests passed either way; on one stock-pnl-web task the
    all-off arm kept two defects the other arms fixed.
    Estimated: implementing in a session of context C adds about 30 turns x (C - 26k) x
    $0.20/M (Opus 5.5 cache reads) over a fresh session, i.e. $0.06 per 10k. At the
    $0.38 premium that breaks even at C = 89k when the session ends after the task, and
    at 56k when ~50k tokens of reading stay for ~20 more turns (+$0.20). 60k is the
    default; no builder-vs-main replay has run in a long session yet."""
    raw = os.environ.get("ROUTING_BUILDER_AT_K")
    if raw is None:
        raw = cfg["guard"].get("builderAtK", 60)
    try:
        return max(0, int(raw)) * 1000
    except (TypeError, ValueError):
        return 60000


def _main_write_absorbed(cls, cfg) -> bool:
    """-> whether the main session makes this write with no ask. A class whose owning
    role is off is always absorbed (`deny` included: no cheaper path is left to name).
    Production code is also absorbed while the main session's context is under
    guard.builderAtK: there, implementing here costs less than a builder dispatch."""
    owner = CLASS_OWNER.get(cls)
    if not owner:
        return False
    if not role_enabled(cfg, owner):
        return True
    if cls == "prod" and main_severity(cfg) != "deny":
        # `deny` means the main session never writes production code: honoured as is.
        at = builder_at(cfg)
        ctx = main_context_tokens(TRANSCRIPT)
        return bool(at) and ctx is not None and ctx < at
    return False


def main_reason(cls, cfg) -> str:
    reason = REASONS[("main", cls)]
    ctx = main_context_tokens(TRANSCRIPT) if cls == "prod" else None
    if ctx is not None and builder_at(cfg):
        reason += (" This session's context is about %dk tokens, at or over the %dk "
                   "(`guard.builderAtK`) where each implementation turn here replays "
                   "more than a builder dispatch costs." % (ctx // 1000, builder_at(cfg) // 1000))
    return reason


RULES = {
    "main": {"prod": "@main", "record": "@main"},
    "builder": {"test": "deny", "doc": "deny", "record": "deny", "spec": "deny"},
    "scribe": {"prod": "deny", "test": "deny", "spec": "deny", "config": "deny"},
    "scout": {"*": "deny"},
    "reviewer": {"*": "deny"},
}


ASK_CONTEXT = "The route guard asked the user to confirm this call. Its reason: {reason}"


def hint(text: str) -> None:
    """Allow the call and hand Claude `text`. No permission decision is given, so the
    call goes through whatever the session's permission mode would do anyway."""
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "additionalContext": text,
    }}))
    sys.exit(0)


def respond(decision: str, reason: str) -> None:
    out = {
        "hookEventName": "PreToolUse",
        "permissionDecision": decision,
        "permissionDecisionReason": reason,
    }
    if decision == "ask":
        # Claude Code shows an ask's reason to the user only, and every reason here names
        # the cheaper path for Claude to take. additionalContext is what reaches Claude.
        out["additionalContext"] = ASK_CONTEXT.format(reason=reason)
    print(json.dumps({"hookSpecificOutput": out}))
    sys.exit(0)


def main_severity(cfg) -> str:
    """-> the decision for a main-session write: 'deny', 'ask', or '' when turned off."""
    level = (os.environ.get("ROUTING_MAIN")
             or cfg["guard"].get("mainSeverity") or "off").lower()
    if level == "off":
        return ""
    return "deny" if level == "deny" else "ask"


def classify(rel, cfg) -> str:
    if rel is None:
        return "outside"
    rel = strip_worktree(rel)
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


# --- a builder works from a spec -------------------------------------------------------
# The Files list is the builder's task-level contract. A dispatch with no brief and no
# spec gives it nothing to follow, so it is denied; a dispatch that has one is recorded
# here so the builder's own writes can be checked against the list. The hook payload of
# a builder's tool call carries `agent_id` but the Agent call that created it does not,
# so the first in-scope write binds the builder to the dispatch whose list names that file.
BUILDER_SPEC_REASON = (
    "A `builder` dispatch needs something to implement. Send an inline brief with a "
    "`Files:` line (every file it may touch) and a `Verify:` line (the exact command), "
    "or the path of a spec file with a `## Files` section — see Step 2 of the `route` "
    "skill. Without one the builder would be designing, and it is not allowed to."
)
BUILDER_SCOPE_REASON = (
    "{targets} is not in this task's Files list ({files}). The builder may change only "
    "the files its brief or spec names. If the task cannot be done without {targets}, "
    "stop and report the blocker; the caller decides whether to widen the list."
)
_BRIEF_HEADING_RE = re.compile(
    r"^\s*[*_#>\-\s]*(Task|Contract|Files|Verify|Non-?goals?)\s*[*_]*\s*:", re.I)
_FILES_LINE_RE = re.compile(r"^\s*[*_#>\-\s]*Files\s*[*_]*\s*:(.*)$", re.I)
_VERIFY_LINE_RE = re.compile(r"^\s*[*_#>\-\s]*Verify\s*[*_]*\s*:\s*\S", re.I)
_FILES_HEADING_RE = re.compile(r"^(#{1,6})\s*Files\b", re.I)
_PATH_TOKEN_RE = re.compile(r"[^\s,;`'\"()\[\]<>|]+")
SCOPE_TTL_S = 6 * 3600
SPEC_READ_BYTES = 64 * 1024


def _scope_tokens(text: str) -> list:
    """-> the path-like tokens in a Files section: `src/a.ts`, `src/mod/`, `src/*.py`,
    `src/a.ts:12-30` (the line range is dropped)."""
    out = []
    for raw in _PATH_TOKEN_RE.findall(text):
        tok = raw.strip("*_:").lstrip("-").strip()
        tok = re.sub(r":\d[\d,\-]*$", "", tok)
        if tok.startswith("./"):
            tok = tok[2:]
        if tok and ("/" in tok or re.search(r"\.\w+$", tok)):
            out.append(tok)
    return out


def _brief_files(prompt: str):
    """-> (tokens, has_verify) from an inline brief; tokens is [] when there is no
    `Files:` line."""
    lines = prompt.splitlines()
    tokens, has_verify, i = [], False, 0
    while i < len(lines):
        line = lines[i]
        if _VERIFY_LINE_RE.match(line):
            has_verify = True
        m = _FILES_LINE_RE.match(line)
        if m:
            chunk = [m.group(1)]
            i += 1
            while i < len(lines) and not _BRIEF_HEADING_RE.match(lines[i]):
                chunk.append(lines[i])
                i += 1
            tokens.extend(_scope_tokens("\n".join(chunk)))
            continue
        i += 1
    return tokens, has_verify


def _spec_files(prompt: str, project: str, cfg):
    """-> the Files tokens of the first spec file the prompt points at, or None when it
    points at none that can be read."""
    for raw in _PATH_TOKEN_RE.findall(prompt):
        tok = raw.strip("*_:.,")
        if not tok or "." not in os.path.basename(tok):
            continue
        path = tok if os.path.isabs(tok) else os.path.join(project, tok)
        if not os.path.isfile(path):
            continue
        rel = rel_path(path, project)
        if rel is None or classify(rel, cfg) != "spec":
            continue
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                body = fh.read(SPEC_READ_BYTES)
        except OSError:
            continue
        section, level = [], None
        for line in body.splitlines():
            h = _FILES_HEADING_RE.match(line)
            if h and level is None:
                level = len(h.group(1))
                continue
            if level is not None:
                if re.match(r"^#{1,%d}\s" % level, line):
                    break
                section.append(line)
        if level is None:
            for line in body.splitlines():
                m = _FILES_LINE_RE.match(line)
                if m:
                    section.append(m.group(1))
        return _scope_tokens("\n".join(section))
    return None


def builder_spec(prompt: str, project: str, cfg):
    """-> (ok, tokens): ok is whether the dispatch carries a brief (a Files list that
    names at least one path, and a Verify line) or a spec file whose Files section does;
    tokens is that list."""
    spec = _spec_files(prompt, project, cfg)
    if spec:
        return True, spec
    tokens, has_verify = _brief_files(prompt)
    return (bool(tokens) and has_verify), tokens


def _scope_path(project: str, session) -> str:
    return os.path.join(project, ".claude", "routing", "state", "%s.bscope" % session)


def _scope_load(path: str):
    """-> (pending, bound): dispatches not yet claimed by a builder, and agent_id -> tokens."""
    pushes, open_ids, bound = {}, [], {}
    try:
        with open(path, encoding="utf-8") as fh:
            rows = [json.loads(l) for l in fh if l.strip()]
    except (OSError, ValueError):
        return [], {}
    for row in rows:
        if row.get("op") == "push":
            pushes[row["id"]] = row
            open_ids.append(row["id"])
        elif row.get("op") == "bind" and row.get("id") in pushes:
            # Two builders can claim one dispatch at once; both get its list.
            bound[row["agent_id"]] = pushes[row["id"]]["tokens"]
            if row["id"] in open_ids:
                open_ids.remove(row["id"])
    now = time.time()
    pending = [pushes[i] for i in open_ids if now - pushes[i].get("ts", 0) < SCOPE_TTL_S]
    return pending, bound


def _scope_append(path: str, row: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")


def _in_scope(rel: str, tokens) -> bool:
    rel = strip_worktree(rel)
    for tok in tokens:
        if tok == rel or (tok.endswith("/") and rel.startswith(tok)):
            return True
        if tok.startswith(rel.rstrip("/") + "/"):
            return True  # `mkdir`/`rm -r` on a directory that holds a listed file
        if "*" in tok and matches_any(rel, [tok]):
            return True
    return False


def record_builder_dispatch(prompt, project, cfg, session) -> None:
    ok, tokens = builder_spec(prompt, project, cfg)
    if not ok:
        respond("deny", "[routing/main] " + BUILDER_SPEC_REASON)
    if tokens and session:
        try:
            _scope_append(_scope_path(project, session), {
                "op": "push", "id": "%x" % int(time.time() * 1e6), "ts": time.time(),
                "tokens": tokens})
        except OSError:
            pass  # no state, no enforcement: fail open


def check_builder_scope(rels, project, cfg) -> None:
    """Deny a builder write to a path its dispatch's Files list does not name."""
    if not cfg["guard"].get("builderNeedsSpec", True) or not AGENT_ID or not SESSION:
        return
    try:
        path = _scope_path(project, SESSION)
        pending, bound = _scope_load(path)
        if AGENT_ID in bound:
            tokens = bound[AGENT_ID]
        else:
            pick = next((p for p in pending if all(_in_scope(r, p["tokens"]) for r in rels)),
                        None)
            if pick is not None:
                _scope_append(path, {"op": "bind", "id": pick["id"], "agent_id": AGENT_ID})
                return
            if not pending:
                return  # nothing recorded for this builder: the role-level scope still applies
            tokens = pending[0]["tokens"]
        bad = [r for r in rels if not _in_scope(r, tokens)]
    except (OSError, ValueError, KeyError):
        return
    if bad:
        respond("deny", "[routing/builder] " + BUILDER_SCOPE_REASON.format(
            targets=", ".join(sorted(set(bad))[:3]), files=", ".join(tokens[:8])))


def handle_dispatch(role, tool_input, cfg, project) -> None:
    spawned = (tool_input.get("subagent_type") or "").strip()
    spawned_role = route_role(spawned)
    # A disabled role is a deny, not an ask: confirming cannot supply what is missing,
    # and a role nobody may dispatch is the whole point of turning one off.
    if spawned_role and not role_enabled(cfg, spawned_role):
        respond("deny", "[routing/%s] " % role + DISABLED_ROLE_REASON.format(
            name=spawned or spawned_role, role=spawned_role))
    if spawned_role and not os.environ.get("CLAUDE_CODE_SUBAGENT_MODEL_FORCE"):
        want = str((cfg.get("models") or {}).get(spawned_role) or "").strip().lower()
        given = str(tool_input.get("model") or "").strip().lower()
        got = given or frontmatter_model(spawned_role)
        # Only an alias can be compared: the Agent tool takes nothing else.
        if want in MODEL_ALIASES and got and got != want:
            source = ("the `model` parameter" if given
                      else "no `model` parameter, so the agent file's default")
            respond("deny", "[routing/%s] " % role + MODEL_REASON.format(
                role=spawned_role, want=want, got=got, source=source))
    if spawned_role == "builder" and cfg["guard"].get("builderNeedsSpec", True):
        record_builder_dispatch(tool_input.get("prompt") or "", project, cfg, SESSION)
    name = spawned or DEFAULT_AGENT
    if name.lower() in DISCOVERY_AGENTS:
        template = (DISCOVERY_HINT if role_enabled(cfg, "scout")
                    else DISCOVERY_HINT_NO_SCOUT)
        hint("[routing/%s] " % role + template.format(name=name))
    sys.exit(0)


def handle_read(role, tool_input, project, cfg) -> None:
    target = tool_input.get("file_path")
    rel = rel_path(target, project)
    # A bounded archive read is allowed. `Edit` refuses to touch a file that has not been
    # read, so denying every read left the prepend this message recommends mechanically
    # impossible and the Bash heredoc append as the only route — and `>>` appends, while a
    # newest-first archive needs a prepend. Reading a header to anchor an Edit is the
    # bounded retrieval this guard exists to encourage; only the whole-file read is refused.
    rel = strip_worktree(rel)
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
        template = (READ_HINT if role_enabled(cfg, "scout")
                    else READ_HINT_NO_SCOUT)
        hint("[routing/main] " + template.format(
            name=os.path.basename(target), kb=size // 1024,
            ktok=max(1, size // 4000)))
    sys.exit(0)


def _scribe_redirect_in_scope(command: str, project: str, cfg: dict) -> bool:
    """Scribe's documented append (`cat >> <archive> <<'EOF'`) needs no confirmation
    when the command matches that exact shape and the target resolves inside paths.docs.
    """
    target = _scribe_redirect_target(command)
    if target is None:
        return False
    docs = (cfg["paths"].get("docs") or "").strip("/")
    if not docs or docs == ".":
        return False
    # rel_path realpaths both ends and returns None for anything outside the project,
    # which covers the `..` escape; strip_worktree keeps a worktree's docs tree in scope.
    rel = strip_worktree(rel_path(target, project))
    if rel is None:
        return False
    return rel == docs or rel.startswith(docs + "/")


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
        if cls not in ("prod", "record"):
            continue
        if _main_write_absorbed(cls, cfg):
            continue
        decision = main_severity(cfg)
        if decision:
            respond(decision, "[routing/main] " + main_reason(cls, cfg))
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
    inside = [rel_path(t, project) for t in targets]
    check_builder_scope([r for r in inside if r is not None], project, cfg)
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
        rel_in_tree = strip_worktree(rel)
        in_docs = bool(docs and docs != "." and
                       (rel_in_tree == docs or rel_in_tree.startswith(docs + "/")))
        if not in_docs or cls in ("prod", "test", "spec", "config"):
            respond("deny", "[routing/scribe] Scribe may write only inside %s/." %
                    (docs or "the configured tracking directory"))

    if role == "builder" and cls != "prod":
        reason = REASONS.get((role, cls)) or (
            "Builder may write production-code paths only; the spec's Files list is "
            "the remaining task-level scope.")
        respond("deny", "[routing/builder] " + reason)
    if role == "builder":
        check_builder_scope([rel], project, cfg)

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
        if _main_write_absorbed(cls, cfg):
            sys.exit(0)
        decision = main_severity(cfg)
        if not decision:
            sys.exit(0)

    reason = (main_reason(cls, cfg) if role == "main" and ("main", cls) in REASONS
              else REASONS.get((role, cls)) or (
                  "Role `%s` may not write %s files. See the `route` skill." % (role, cls)))
    respond(decision, "[routing/%s] %s" % (role, reason))


def main() -> None:
    if os.environ.get("ROUTING_GUARD", "").lower() == "off":
        sys.exit(0)
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)  # never break the session on a malformed payload

    global TRANSCRIPT, AGENT_ID, SESSION
    TRANSCRIPT = payload.get("transcript_path")
    AGENT_ID = payload.get("agent_id")
    SESSION = payload.get("session_id")
    role = normalize_role(payload.get("agent_type"))
    tool_input = payload.get("tool_input") or {}
    tool = payload.get("tool_name")
    project = project_dir(payload)
    cfg = load_config(project)

    if tool in ("Agent", "Task"):
        handle_dispatch(role, tool_input, cfg, project)
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
