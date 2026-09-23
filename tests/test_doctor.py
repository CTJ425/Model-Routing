"""Tests for routing_doctor.py — the self-check that answers "is this plugin actually live".

Run as a subprocess, like the other hook tests: the contract is the printed report and the
exit code, and only a subprocess checks both.
"""
import json
import os
import subprocess
import sys

import pytest

from conftest import BASE_CONFIG, write_config

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCTOR = os.path.join(REPO, "route", "scripts", "routing_doctor.py")


def run_doctor(project, env_extra=None):
    env = dict(os.environ)
    env.pop("CLAUDE_CODE_SUBAGENT_MODEL", None)
    env.pop("CLAUDE_CODE_SUBAGENT_MODEL_FORCE", None)
    env["CLAUDE_PROJECT_DIR"] = str(project)
    env.update(env_extra or {})
    return subprocess.run([sys.executable, DOCTOR], capture_output=True, text=True,
                          env=env, cwd=str(project))


def test_healthy_project_passes(project):
    p = run_doctor(project)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "[PASS] config" in p.stdout
    assert "[PASS] paths.prod" in p.stdout


def test_hooks_check_executes_the_real_guard(project):
    """The single question this command exists to answer."""
    assert "[PASS] hooks" in run_doctor(project).stdout


def test_roles_check_reports_a_healthy_roster(project):
    assert "[PASS] roles" in run_doctor(project).stdout


def test_roles_check_warns_about_a_role_that_is_off(project):
    cfg = json.loads(json.dumps(BASE_CONFIG))
    cfg["roles"] = {"scribe": {"enabled": False}}
    write_config(project, cfg)
    out = run_doctor(project).stdout
    assert "[WARN] roles" in out
    assert "scribe" in out


@pytest.mark.parametrize("roles,named", [
    ({"builder": {"enabled": "false"}}, 'roles.builder.enabled is "false" (a string)'),
    ({"builder": {"enabled": 0}}, "roles.builder.enabled is 0 (a number)"),
    ({"builder": False}, "roles.builder is false (a boolean)"),
    ({"builder": {"enable": False}}, "roles.builder.enable is not a known key"),
    ({"buidler": {"enabled": False}}, "roles.buidler is not a route role"),
    (["builder"], 'roles is ["builder"] (an array)'),
])
def test_roles_check_fails_on_a_switch_the_hooks_cannot_read(roles, named, project):
    """The file says off; the guard lets the role through. Nothing else would show it."""
    cfg = json.loads(json.dumps(BASE_CONFIG))
    cfg["roles"] = roles
    write_config(project, cfg)
    p = run_doctor(project)
    assert "[FAIL] roles " + named in p.stdout, p.stdout + p.stderr
    assert p.returncode == 1


def test_roles_check_names_the_state_the_hooks_actually_use(project):
    cfg = json.loads(json.dumps(BASE_CONFIG))
    cfg["roles"] = {"builder": {"enabled": "false"}, "scribe": {"enabled": False}}
    write_config(project, cfg)
    out = run_doctor(project).stdout
    assert "so builder is on" in out
    assert "Off now: scribe." in out


def test_roles_check_fails_on_a_malformed_legacy_scout_switch(project):
    cfg = json.loads(json.dumps(BASE_CONFIG))
    cfg["scout"] = {"enabled": "no"}
    write_config(project, cfg)
    out = run_doctor(project).stdout
    assert '[FAIL] roles scout.enabled is "no" (a string)' in out
    assert "so scout is on" in out


def test_prod_paths_matching_nothing_is_a_failure(project):
    """The monorepo trap: builder is denied every write and nothing says why."""
    cfg = json.loads(json.dumps(BASE_CONFIG))
    cfg["paths"]["prod"] = ["packages/*/src/**"]
    write_config(project, cfg)
    p = run_doctor(project)
    assert "[FAIL] paths.prod" in p.stdout
    assert p.returncode == 1


def test_missing_config_warns_but_does_not_fail(project):
    os.remove(os.path.join(str(project), ".claude", "route.config.json"))
    p = run_doctor(project)
    assert "[WARN] config" in p.stdout
    assert p.returncode == 0


@pytest.fixture
def claude_on_path(tmp_path_factory):
    """-> fn(version) giving a PATH whose `claude --version` prints `version`, or fails
    when `version` is None. The model check's verdict depends on the running version."""
    def make(version):
        bindir = tmp_path_factory.mktemp("bin")
        exe = bindir / "claude"
        body = 'echo "%s (Claude Code)"' % version if version else "exit 1"
        exe.write_text("#!/bin/sh\n%s\n" % body)
        exe.chmod(0o755)
        return str(bindir) + os.pathsep + os.environ.get("PATH", "")
    return make


needs_sh = pytest.mark.skipif(os.name == "nt", reason="fake claude is a POSIX shell script")


@needs_sh
@pytest.mark.parametrize("version, verdict", [
    ("2.1.274", "[PASS] models"),   # only a default since 2.1.251
    ("2.1.250", "[WARN] models"),   # still outranks the tiers
    (None, "[WARN] models"),        # version unknown: say what it would do
])
def test_subagent_model_alone_is_judged_by_version(project, claude_on_path,
                                                   version, verdict):
    """Silence about an override that is in force is a lie; so is a warning about one
    that is not."""
    p = run_doctor(project, {"CLAUDE_CODE_SUBAGENT_MODEL": "opus",
                             "PATH": claude_on_path(version)})
    assert verdict in p.stdout
    assert "CLAUDE_CODE_SUBAGENT_MODEL=opus" in p.stdout


@needs_sh
def test_force_puts_one_model_over_every_tier(project, claude_on_path):
    p = run_doctor(project, {"CLAUDE_CODE_SUBAGENT_MODEL": "opus",
                             "CLAUDE_CODE_SUBAGENT_MODEL_FORCE": "1",
                             "PATH": claude_on_path("2.1.274")})
    assert "[WARN] models" in p.stdout
    assert "runs on opus" in p.stdout


@needs_sh
def test_force_alone_runs_on_the_main_model(project, claude_on_path):
    p = run_doctor(project, {"CLAUDE_CODE_SUBAGENT_MODEL_FORCE": "1",
                             "PATH": claude_on_path("2.1.274")})
    assert "[WARN] models" in p.stdout
    assert "main session's model" in p.stdout


@needs_sh
def test_force_is_ignored_before_it_existed(project, claude_on_path):
    p = run_doctor(project, {"CLAUDE_CODE_SUBAGENT_MODEL_FORCE": "1",
                             "PATH": claude_on_path("2.1.255")})
    assert "[PASS] models" in p.stdout


@needs_sh
def test_subagent_model_inherit_is_unset(project, claude_on_path):
    p = run_doctor(project, {"CLAUDE_CODE_SUBAGENT_MODEL": "inherit",
                             "PATH": claude_on_path(None)})
    assert "[PASS] models" in p.stdout
    assert "CLAUDE_CODE_SUBAGENT_MODEL" not in p.stdout


def test_summary_line_counts_every_check(project):
    out = run_doctor(project).stdout
    assert "passed" in out.splitlines()[-1]


@pytest.mark.parametrize("paths", ["src/", ["src/"], 42, None])
def test_malformed_paths_shape_fails_instead_of_crashing(project, paths):
    """Valid JSON of the wrong shape must FAIL, not raise past the summary line. A
    diagnostic that aborts without a verdict is worse than one that reports a bad config."""
    write_config(project, {"version": 2, "paths": paths})
    p = run_doctor(project)
    assert "[FAIL] config" in p.stdout, p.stdout + p.stderr
    assert p.stdout.strip().splitlines()[-1].endswith("passed"), "summary line missing"
    assert p.returncode == 1


def test_every_check_reports_even_when_one_raises(project):
    """No single check may abort the run: the summary line is the contract."""
    write_config(project, {"version": 2, "paths": {"prod": "not-a-list"}})
    p = run_doctor(project)
    assert p.stdout.strip().splitlines()[-1].endswith("passed"), p.stdout + p.stderr


def test_effort_warns_when_a_pinned_model_differs_from_the_default(project):
    """A project that pins builder/reviewer to sonnet runs Sonnet at the effort tuned for
    the plugin's default model; the Agent tool cannot change that per project."""
    cfg = json.loads(json.dumps(BASE_CONFIG))
    cfg["models"].update(builder="sonnet", reviewer="sonnet")
    write_config(project, cfg)
    p = run_doctor(project)
    assert "[WARN] effort builder=sonnet at effort medium" in p.stdout
    assert "reviewer=sonnet at effort medium" in p.stdout


def test_effort_passes_on_the_default_models(project):
    write_config(project, dict(BASE_CONFIG, models={
        "scout": "haiku", "builder": "opus", "reviewer": "opus", "scribe": "haiku"}))
    p = run_doctor(project)
    assert "[PASS] effort" in p.stdout
