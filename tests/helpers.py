"""Test helpers: run the hooks as the harness runs them — a subprocess fed JSON on stdin.

Calling the hook in-process would test the functions, not the contract. The contract is
"exit 0, print at most one JSON object", and only a subprocess can check it.
"""
import json
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = os.path.join(REPO, "route")
GUARD = os.path.join(PLUGIN, "hooks", "routing_guard.py")
OBSERVE = os.path.join(PLUGIN, "hooks", "routing_observe.py")


def _run(script: str, payload: dict, project, env_extra=None):
    env = dict(os.environ)
    env.pop("ROUTING_GUARD", None)
    env.pop("ROUTING_MAIN", None)
    env.pop("ROUTING_READ_KB", None)
    env.pop("ROUTING_OBSERVE", None)
    env.pop("ROUTING_SCOUT_AT", None)
    env["CLAUDE_PROJECT_DIR"] = str(project)
    env.update(env_extra or {})
    proc = subprocess.run(
        [sys.executable, script],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        cwd=str(project),
    )
    assert proc.returncode == 0, (
        f"{os.path.basename(script)} exited {proc.returncode}\n{proc.stderr}")
    out = proc.stdout.strip()
    return json.loads(out) if out else None


def run_guard(payload: dict, project=None, env_extra=None):
    """-> the guard's parsed stdout JSON, or None when it allowed the call silently."""
    return _run(GUARD, payload, project or payload.get("cwd") or REPO, env_extra)


def run_observe(payload: dict, project=None, env_extra=None):
    return _run(OBSERVE, payload, project or payload.get("cwd") or REPO, env_extra)


def decision(result):
    """-> 'deny' | 'ask' | None (allowed)."""
    if not result:
        return None
    return result.get("hookSpecificOutput", {}).get("permissionDecision")


def reason(result):
    if not result:
        return ""
    return result.get("hookSpecificOutput", {}).get("permissionDecisionReason", "")
