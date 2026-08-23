"""Regression tests for routing_guard.py.

Every case here is either a bug the guard shipped with (role namespacing, basename
matching, strptime crashes) or a rule the guard exists to enforce.
"""
import datetime
import json

import pytest

from conftest import BASE_CONFIG, write_config
from helpers import decision, reason, run_guard
from _config import rel_path


def write(role, path, project, **tool_input):
    ti = {"file_path": path}
    ti.update(tool_input)
    return run_guard(
        {"tool_name": "Write", "agent_type": role, "tool_input": ti}, project)


def read(role, path, project, **tool_input):
    ti = {"file_path": path}
    ti.update(tool_input)
    return run_guard(
        {"tool_name": "Read", "agent_type": role, "tool_input": ti}, project)


def bash(role, command, project):
    return run_guard(
        {"tool_name": "Bash", "agent_type": role,
         "tool_input": {"command": command}}, project)


# --- role normalization: the P0 bug. A namespaced role matched no rule at all. ---

@pytest.mark.parametrize("role,path,want", [
    ("builder", "docs/x.md", "deny"),
    ("route:builder", "docs/x.md", "deny"),          # was silently allowed
    ("route:sub:builder", "docs/x.md", "deny"),      # nested agent file
    ("route:scout", "src/a.ts", "deny"),             # was silently allowed
    ("Explore", "src/a.ts", None),                   # unknown role: not ours to police
])
def test_role_normalization(role, path, want, project):
    assert decision(write(role, path, project)) == want


# --- path classification ---

@pytest.mark.parametrize("role,path,want", [
    ("builder", "src/a.ts", None),
    ("builder", "tests/a_test.go", "deny"),
    ("builder", "test_a.py", "deny"),
    ("builder", "a.spec.ts", "deny"),
    ("builder", "docs/agent/specs/task-1.md", "deny"),
    ("scribe", "docs/agent/TASK.md", None),
    ("scribe", "src/a.ts", "deny"),
    ("scribe", ".claude/route.config.json", "deny"),
    ("main", "src/a.ts", "ask"),
    ("main", "docs/agent/TASK.md", "ask"),
    ("main", "README.md", None),
])
def test_classification(role, path, want, project):
    assert decision(write(role, path, project)) == want


def test_absolute_and_relative_agree(project):
    rel = decision(write("route:builder", "tests/a_test.go", project))
    absolute = decision(write("route:builder", str(project / "tests/a_test.go"), project))
    assert rel == absolute == "deny"


def test_relative_helper_resolves_from_project_not_process_cwd(project):
    assert rel_path("src/a.ts", str(project)) == "src/a.ts"


def test_outside_the_project_is_not_policed(project):
    assert decision(write("route:scout", "/etc/hosts", project)) is None


# --- timestamps ---

def record(body, project, role="route:scribe"):
    return decision(write(role, "docs/agent/PROGRESS.md", project, content=body))


def test_malformed_timestamp_denied_without_crashing(project):
    # strptime raises on this; before the fix that crash propagated out of the hook.
    assert record("logged at 2026-13-45 99:99:99", project) == "deny"


def test_future_timestamp_denied(project):
    ahead = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)
    assert record(ahead.strftime("## Log: %Y-%m-%d %H:%M:%S"), project) == "deny"


def test_present_timestamp_allowed(project):
    # The default bookkeeping timezone is UTC; do not accidentally test the host's
    # local timezone instead.
    now = datetime.datetime.now(datetime.timezone.utc).strftime(
        "## Log: %Y-%m-%d %H:%M:%S")
    assert record(now, project) is None


def test_timestamp_check_applies_to_iso_separator(project):
    ahead = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)
    assert record(ahead.strftime("%Y-%m-%dT%H:%M:%S"), project) == "deny"


# --- scribe reading archives: was matched by basename, so it hit any CHANGELOG.md ---

def test_scribe_may_read_a_root_changelog(project):
    (project / "CHANGELOG.md").write_text("# Changelog\n")
    assert decision(read("route:scribe", "CHANGELOG.md", project)) is None


def test_scribe_may_not_read_the_archive(project):
    assert decision(read("route:scribe", "docs/agent/TASK_ARCHIVE.md", project)) == "deny"


# --- the archive denial used to advertise a path scribe could not take ---
#
# ARCHIVE_REASON tells scribe to "prepend with `Edit` anchored on the file's header line".
# The Edit tool refuses to touch a file that has not been read ("File has not been read
# yet"), and this guard denied every archive read, so prepending was mechanically
# impossible and the Bash heredoc append was the only route left. `>>` appends, while a
# newest-first archive needs a prepend — so the guard forced the wrong write. Observed
# 2026-08-18: a scribe dispatch appended a PROGRESS_ARCHIVE.md entry to the tail of the
# file while the same entry was prepended at the head, shipping it twice.
#
# A bounded read is the retrieval pattern this guard exists to encourage, and reading a
# header is what anchoring an Edit requires. Bounded reads of an archive are allowed;
# unbounded ones stay denied.

def test_scribe_may_read_the_archive_head_with_a_limit(project):
    assert decision(read("route:scribe", "docs/agent/TASK_ARCHIVE.md", project, limit=40)) is None


def test_scribe_bounded_archive_read_allows_every_archive(project):
    for name in ("TASK_ARCHIVE.md", "FIXED_BUG.md", "PROGRESS_ARCHIVE.md"):
        assert decision(read("route:scribe", "docs/agent/%s" % name, project, limit=5)) is None, name


def test_scribe_archive_read_with_offset_but_no_limit_is_still_denied(project):
    assert decision(read("route:scribe", "docs/agent/TASK_ARCHIVE.md", project, offset=200)) == "deny"


def test_archive_denial_points_at_the_bounded_read(project):
    text = reason(read("route:scribe", "docs/agent/TASK_ARCHIVE.md", project))
    assert "limit" in text, text


def test_main_large_unbounded_read_asks(project):
    big = project / "big.md"
    big.write_text("x" * 40 * 1024)
    assert decision(read("main", str(big), project)) == "ask"
    assert decision(read("main", str(big), project, limit=100)) is None


def test_read_reason_drops_scout_when_disabled(project):
    cfg = json.loads(json.dumps(BASE_CONFIG))
    cfg["scout"] = {"enabled": False}
    write_config(project, cfg)
    big = project / "big.md"
    big.write_text("x" * 40 * 1024)
    got = read("main", str(big), project)
    assert decision(got) == "ask"
    assert "scout" not in reason(got)


# --- Bash write detection ---

@pytest.mark.parametrize("role,command,want", [
    ("route:scout", "cat > src/a.ts", "deny"),
    ("route:scout", "grep -n foo src/", None),
    ("route:reviewer", "rm -rf build", "deny"),
    ("route:builder", "sed -i s/a/b/ x", "ask"),
    ("route:builder", "npm test", None),
    ("route:builder", "npm test > /dev/null", None),
    ("main", "rm -rf build", None),          # main is not policed on Bash
])
def test_bash(role, command, want, project):
    assert decision(bash(role, command, project)) == want


def test_bash_detection_can_be_disabled(project):
    cfg = json.loads(json.dumps(BASE_CONFIG))
    cfg["guard"] = {"bashWriteDetection": False}
    write_config(project, cfg)
    assert decision(bash("route:scout", "cat > src/a.ts", project)) is None


# --- bookkeeping off: the "record" class stops existing ---

def test_records_become_plain_docs_when_bookkeeping_is_off(project):
    cfg = json.loads(json.dumps(BASE_CONFIG))
    cfg["bookkeeping"] = {"enabled": False}
    write_config(project, cfg)
    # Still denied to builder, but as a doc — and scribe's timestamp rule no longer fires.
    assert decision(write("route:builder", "docs/agent/TASK.md", project)) == "deny"
    assert decision(write("route:scribe", "docs/agent/TASK.md", project,
                          content="2026-13-45 99:99:99")) is None


# --- dispatch ---

@pytest.mark.parametrize("spawned,want", [
    ("Explore", "ask"),
    ("general-purpose", "ask"),
    ("route:scout", None),
])
def test_discovery_dispatch(spawned, want, project):
    got = run_guard({"tool_name": "Agent", "agent_type": "",
                     "tool_input": {"subagent_type": spawned}}, project)
    assert decision(got) == want


def test_discovery_reason_drops_scout_when_disabled(project):
    cfg = json.loads(json.dumps(BASE_CONFIG))
    cfg["scout"] = {"enabled": False}
    write_config(project, cfg)
    got = run_guard({"tool_name": "Agent", "agent_type": "",
                     "tool_input": {"subagent_type": "Explore"}}, project)
    assert decision(got) == "ask"
    assert "scout" not in reason(got)


# --- fail-open ---

def test_malformed_payload_exits_clean(project):
    assert run_guard({"tool_name": "Write"}, project) is None


def test_env_kill_switch(project):
    got = run_guard({"tool_name": "Write", "agent_type": "route:scout",
                     "tool_input": {"file_path": "src/a.ts"}}, project,
                    env_extra={"ROUTING_GUARD": "off"})
    assert got is None


def test_env_main_severity_overrides_config(project):
    got = write("main", "src/a.ts", project)
    assert decision(got) == "ask"
    got = run_guard({"tool_name": "Write", "agent_type": "",
                     "tool_input": {"file_path": "src/a.ts"}}, project,
                    env_extra={"ROUTING_MAIN": "deny"})
    assert decision(got) == "deny"


# --- scribe redirecting into the tracking directory is its job, not a prompt ---
#
# scribe.md mandates `cat >> <archive> <<'EOF'` for appends (an archive is too large to
# Read, and a guard denies that Read outright). handle_bash asked on every scribe write
# regardless of target, so the agent's documented happy path always needed a human — and
# in a headless run, where nobody can answer, it failed outright.

@pytest.mark.parametrize("command,want", [
    ("cat >> docs/agent/TASK.md", None),                    # the documented append
    ("cat >> docs/agent/archive/2026.md <<'EOF'", "ask"),   # opener with no body or
                                                            # terminator is not a runnable
                                                            # heredoc — see the block below
    ("cat > docs/agent/TASK.md", "ask"),                   # truncation is never implicit
    ("cat >> ./docs/agent/TASK.md", None),                  # dotted relative path
    ("cat >> src/a.ts", "ask"),                             # plainly outside
    ("cat >> docs/agent/../../src/a.ts", "ask"),            # traversal escapes the docs dir
    ("cat >> /tmp/elsewhere.md", "ask"),                    # absolute, outside the project
    ("cat >> docs/agent/TASK.md; cat >> src/a.ts", "ask"),  # one target outside is enough
    ("rm -rf docs/agent/TASK.md", "ask"),                   # destructive verb, not a redirect
    ("mv docs/agent/a.md docs/agent/b.md", "ask"),          # a move is not a redirect either
])
def test_scribe_bash_redirect_scoped_to_docs(command, want, project):
    assert decision(bash("route:scribe", command, project)) == want


def test_scribe_bash_redirect_asks_when_target_is_unresolvable(project):
    """Fail closed: a target we cannot resolve is not evidence that it is in scope."""
    assert decision(bash("route:scribe", 'cat >> "$OUT"', project)) == "ask"


def test_docs_scope_follows_config(project):
    """The allowance tracks paths.docs, not a hardcoded directory."""
    cfg = json.loads(json.dumps(BASE_CONFIG))
    cfg["paths"]["docs"] = "records"
    write_config(project, cfg)
    assert decision(bash("route:scribe", "cat >> records/TASK.md", project)) is None
    assert decision(bash("route:scribe", "cat >> docs/agent/TASK.md", project)) == "ask"


def test_only_scribe_gets_the_docs_allowance(project):
    """builder still asks: the tracking directory is scribe's, not everyone's."""
    assert decision(bash("route:builder", "cat >> docs/agent/TASK.md", project)) == "ask"
    assert decision(bash("route:scout", "cat >> docs/agent/TASK.md", project)) == "deny"


def test_file_tools_enforce_role_scopes(project):
    assert decision(write("route:builder", "README.md", project)) == "deny"
    assert decision(write("route:scribe", "docs/agent/notes.md", project)) is None
    assert decision(write("route:scribe", "README.md", project)) == "deny"


@pytest.mark.parametrize("command", ["git add docs/agent/TASK.md", "git commit -m done",
                                      "git push origin main"])
def test_scribe_cannot_mutate_version_control(command, project):
    assert decision(bash("route:scribe", command, project)) == "deny"


def test_unknown_role_is_not_subject_to_record_timestamp_policy(project):
    assert decision(write("Explore", "docs/agent/PROGRESS.md", project,
                          content="2026-13-45 99:99:99")) is None


def test_timestamp_uses_the_configured_timezone(project):
    cfg = json.loads(json.dumps(BASE_CONFIG))
    cfg["bookkeeping"] = {"timezone": "Asia/Taipei"}
    write_config(project, cfg)
    taipei = datetime.timezone(datetime.timedelta(hours=8))
    now = datetime.datetime.now(taipei).strftime(
        "## Log: %Y-%m-%d %H:%M:%S")
    assert record(now, project) is None


# --- the allowance is a positive grammar, not a denylist ---
#
# A denylist over shell strings is unwinnable: every one of these reached a silent allow
# through an earlier "not destructive AND target in scope" formulation. The allowance now
# matches only the exact append shape scribe.md prescribes — `cat >>` one literal path,
# with an optional heredoc — so truncation and anything unusual fall through to ask.

@pytest.mark.parametrize("command", [
    r"cat >> docs/agent/\.\./\.\./etc/passwd",       # backslash escapes normpath cannot see
    r"\rm docs/agent/other.md > docs/agent/log.md",  # \rm bypasses the verb prefix class
    "find docs/agent -delete > docs/agent/log.md",   # destructive verb not on any list
    "shred docs/agent/a.md > docs/agent/log.md",
    "cat >> docs/agent/x.md > >(cat > /tmp/evil.md)",  # process substitution
    "cat >> docs/agent/x.md && rm -rf /",            # chained
    "cat >> docs/agent/x.md | tee /tmp/evil.md",     # pipe
    "cat >> $(echo docs/agent/x.md)",                # command substitution
    'cat >> "docs/agent/x.md"',                      # quoted: fail-safe, not covered
    "cat >>| docs/agent/x.md",                       # clobber form
    "cat &>> docs/agent/x.md",                       # fd-duplicating form
    "echo hi > docs/agent/a.md > docs/agent/b.md",   # two redirects
])
def test_scribe_bash_allowance_is_fail_closed(command, project):
    assert decision(bash("route:scribe", command, project)) == "ask"


def test_scribe_bash_redirect_through_symlink_asks(project):
    """normpath cannot see a symlink; the target must be resolved for real."""
    outside = project / "outside.md"
    outside.write_text("x\n")
    (project / "docs" / "agent" / "link.md").symlink_to(outside)
    assert decision(bash("route:scribe", "cat >> docs/agent/link.md", project)) == "ask"


def test_scribe_bash_allowance_survives_odd_docs_config(project):
    """An empty or root paths.docs must not turn into 'everything is in scope'."""
    for docs in ("", "/", "."):
        cfg = json.loads(json.dumps(BASE_CONFIG))
        cfg["paths"]["docs"] = docs
        write_config(project, cfg)
        assert decision(bash("route:scribe", "cat >> src/a.ts", project)) == "ask"


# --- the heredoc append, as a shell actually receives it ---
#
# `cat >> <archive> <<'EOF'` is a MULTI-LINE command: opener, body, terminator. Testing
# only the opener line proves nothing — a shell handed that alone would block waiting on
# stdin. These cases carry a real body and terminator, because this shape is the entire
# reason the allowance exists.

HEREDOC_OK = "cat >> docs/agent/archive/2026.md <<'EOF'\n### 2026-08-13 entry\nbody line\nEOF"
HEREDOC_DQ = 'cat >> docs/agent/archive/2026.md <<"EOF"\nbody\nEOF'
HEREDOC_TAB = "cat >> docs/agent/archive/2026.md <<-'EOF'\n\tbody\n\tEOF"


@pytest.mark.parametrize("command,want", [
    (HEREDOC_OK, None),                                    # the shape scribe.md mandates
    (HEREDOC_DQ, None),                                    # double-quoted delimiter also
                                                           # suppresses expansion
    (HEREDOC_TAB, None),                                   # <<- allows a tab-indented
                                                           # terminator
    (HEREDOC_OK + "\n", None),                             # trailing newline is harmless
    # An UNQUOTED delimiter leaves the body subject to expansion, so `$(...)` in it is
    # executed by the shell. Never allowed.
    ("cat >> docs/agent/x.md <<EOF\n$(rm -rf /tmp/x)\nEOF", "ask"),
    ("cat >> docs/agent/x.md <<EOF\nplain body\nEOF", "ask"),
    # Anything after the terminator is a second command riding along.
    ("cat >> docs/agent/x.md <<'EOF'\nbody\nEOF\nrm -rf /tmp/x", "ask"),
    # No terminator: the body is unbounded, so its extent cannot be reasoned about.
    ("cat >> docs/agent/x.md <<'EOF'\nbody", "ask"),
    # A terminator that only looks like one.
    ("cat >> docs/agent/x.md <<'EOF'\nbody\nEOFX", "ask"),
    ("cat >> docs/agent/x.md <<'EOF'\nbody\n EOF", "ask"),  # leading space, not <<-
    # The target still has to be in scope, heredoc or not.
    ("cat >> src/a.ts <<'EOF'\nbody\nEOF", "ask"),
    # A newline may not smuggle a second command in when there is no heredoc at all.
    ("cat >> docs/agent/x.md\nrm -rf /tmp/x", "ask"),
])
def test_scribe_heredoc_append(command, want, project):
    assert decision(bash("route:scribe", command, project)) == want


# --- quoted '>' is not a redirect: the write heuristic must not fire on read-only
# --- commands that merely contain an angle bracket inside a quoted argument.

@pytest.mark.parametrize("command", [
    "grep -n 'foo -> bar' src/a.ts",
    'grep -n "foo -> bar" src/a.ts',
    "awk '{ if ($3 > 10) print }' bench.txt",
    "jq 'select(.count > 0)' out.json",
    "pytest -k 'a > b'",
    "grep -rn '=>' src/",
])
def test_quoted_angle_bracket_is_not_a_write(command, project):
    """A '>' inside a balanced quoted span is an argument, not a redirect."""
    assert decision(bash("route:builder", command, project)) is None


@pytest.mark.parametrize("command,want", [
    ("echo done > result.txt", "ask"),          # a real redirect, unquoted
    ("cat > src/a.ts", "ask"),
    ("sed -i 's/a/b/' src/a.ts", "ask"),        # -i is outside the quoted span
    ("rm -rf build", "ask"),                    # verb match, no redirect involved
    ("echo 'a > b' > out.txt", "ask"),          # quoted decoy plus a real redirect
])
def test_real_writes_survive_quote_stripping(command, want, project):
    assert decision(bash("route:builder", command, project)) == want


def test_quote_stripping_does_not_weaken_read_only_roles(project):
    assert decision(bash("route:scout", "echo x > src/a.ts", project)) == "deny"
    assert decision(bash("route:scout", "grep -n 'a -> b' src/a.ts", project)) is None


def test_unterminated_quote_is_not_treated_as_a_quoted_span(project):
    """Fail closed: an unbalanced quote must not swallow a real redirect."""
    assert decision(bash("route:builder", "echo it's fine > out.txt", project)) == "ask"


def test_scribe_in_scope_redirect_still_resolves_after_quote_stripping(project):
    """Quote stripping is for detection only; scribe's target resolution sees the raw text."""
    assert decision(bash("route:scribe", "cat >> docs/agent/TASK.md", project)) is None
    assert decision(bash("route:scribe", 'cat >> "$OUT"', project)) == "ask"


@pytest.mark.parametrize("command", [
    r"echo \'a > out.txt\'",       # \' is a literal quote; the '>' between them is live
    r"echo \"a > b\"",
    r"cat \"x\" > src/a.ts",
])
def test_escaped_quote_does_not_hide_a_redirect(command, project):
    """A backslash-escaped quote is not a span delimiter. Treating it as one blanks a real
    redirect out of the scanned text, which is the one direction this must never fail in."""
    assert decision(bash("route:builder", command, project)) == "ask"
