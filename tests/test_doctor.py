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


def test_models_check_reports_every_tier(project):
    """The architect tier must appear alongside the original four."""
    out = run_doctor(project).stdout
    assert "[PASS] models" in out
    for role in ("scout", "architect", "builder", "reviewer", "scribe"):
        assert "%s=" % role in out


def test_roles_check_warns_about_a_role_that_is_off(project):
    cfg = json.loads(json.dumps(BASE_CONFIG))
    cfg["roles"] = {"scribe": {"enabled": False}}
    write_config(project, cfg)
    out = run_doctor(project).stdout
    assert "[WARN] roles" in out
    assert "scribe" in out


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


def test_subagent_model_override_is_reported(project):
    """CLAUDE_CODE_SUBAGENT_MODEL outranks every per-role tier; silence about it is a lie."""
    p = run_doctor(project, {"CLAUDE_CODE_SUBAGENT_MODEL": "opus"})
    assert "[WARN] models" in p.stdout
    assert "CLAUDE_CODE_SUBAGENT_MODEL" in p.stdout


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
