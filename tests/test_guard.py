"""Regression tests for routing_guard.py.

Every case here is either a bug the guard shipped with (role namespacing, basename
matching, strptime crashes) or a rule the guard exists to enforce.
"""
import datetime
import json

import pytest

from conftest import BASE_CONFIG, write_config
from helpers import decision, run_guard


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


def test_outside_the_project_is_not_policed(project):
    assert decision(write("route:scout", "/etc/hosts", project)) is None


# --- timestamps ---

def record(body, project, role="route:scribe"):
    return decision(write(role, "docs/agent/PROGRESS.md", project, content=body))


def test_malformed_timestamp_denied_without_crashing(project):
    # strptime raises on this; before the fix that crash propagated out of the hook.
    assert record("logged at 2026-13-45 99:99:99", project) == "deny"


def test_future_timestamp_denied(project):
    ahead = datetime.datetime.now() + datetime.timedelta(hours=1)
    assert record(ahead.strftime("## Log: %Y-%m-%d %H:%M:%S"), project) == "deny"


def test_present_timestamp_allowed(project):
    now = datetime.datetime.now().strftime("## Log: %Y-%m-%d %H:%M:%S")
    assert record(now, project) is None


def test_timestamp_check_applies_to_iso_separator(project):
    ahead = datetime.datetime.now() + datetime.timedelta(hours=1)
    assert record(ahead.strftime("%Y-%m-%dT%H:%M:%S"), project) == "deny"


# --- scribe reading archives: was matched by basename, so it hit any CHANGELOG.md ---

def test_scribe_may_read_a_root_changelog(project):
    (project / "CHANGELOG.md").write_text("# Changelog\n")
    assert decision(read("route:scribe", "CHANGELOG.md", project)) is None


def test_scribe_may_not_read_the_archive(project):
    assert decision(read("route:scribe", "docs/agent/TASK_ARCHIVE.md", project)) == "deny"


def test_main_large_unbounded_read_asks(project):
    big = project / "big.md"
    big.write_text("x" * 40 * 1024)
    assert decision(read("main", str(big), project)) == "ask"
    assert decision(read("main", str(big), project, limit=100)) is None


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
