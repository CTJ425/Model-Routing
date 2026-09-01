#!/usr/bin/env python3
"""Self-check: is this plugin actually live, and is it configured so the roles can work.

Answers the question a fresh install or a moved project raises before any other command
is trustworthy: are the hooks wired up, does the config parse, do the configured paths
actually match anything in this repo. Reports only -- it never modifies the project.

Usage (run from the project being checked, or set CLAUDE_PROJECT_DIR):
  python3 routing_doctor.py
"""
import json
import os
import platform
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hooks"))
from _config import (  # noqa: E402
    DEFAULTS, ROUTE_ROLES, load_config, matches_any, project_dir, record_paths,
    role_enabled,
)

PROJECT = project_dir()
PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

COUNTS = {"PASS": 0, "WARN": 0, "FAIL": 0}


def check(status: str, name: str, message: str) -> None:
    COUNTS[status] += 1
    print("[%s] %s %s" % (status, name, message))


def check_interpreter():
    """-> the resolved python3 path, or None. `hooks` reuses this rather than
    re-resolving, so the two checks never disagree about which interpreter exists.
    """
    path = shutil.which("python3")
    if not path:
        check("FAIL", "interpreter",
              "python3 not found on PATH; hooks.json declares every hook as the "
              "literal command python3, so nothing runs without it.")
        return None
    check("PASS", "interpreter", "python3 resolves to %s (Python %s)."
          % (path, platform.python_version()))
    return path


def check_hooks(python3_path) -> None:
    guard = os.path.join(PLUGIN_ROOT, "hooks", "routing_guard.py")
    observe = os.path.join(PLUGIN_ROOT, "hooks", "routing_observe.py")
    missing = [name for name, path in (("routing_guard.py", guard),
                                       ("routing_observe.py", observe))
               if not os.path.isfile(path)]
    if missing:
        check("FAIL", "hooks", "missing: %s." % ", ".join(missing))
        return
    if not python3_path:
        check("FAIL", "hooks", "cannot execute the guard: the interpreter check "
              "already failed to resolve python3.")
        return
    payload = json.dumps({"tool_name": "Read",
                          "tool_input": {"file_path": "README.md"},
                          "agent_type": "main"})
    # hooks.json bounds the real invocation to 10s; this diagnostic must not be less
    # bounded than the thing it diagnoses, or a hanging guard hangs the doctor forever.
    try:
        result = subprocess.run([python3_path, guard], input=payload,
                                capture_output=True, text=True, cwd=PROJECT,
                                env=dict(os.environ, CLAUDE_PROJECT_DIR=PROJECT),
                                timeout=10)
    except subprocess.TimeoutExpired:
        check("FAIL", "hooks", "routing_guard.py did not exit within 10s on a benign "
              "read (hooks.json bounds the same invocation to 10s).")
        return
    except Exception as exc:
        check("FAIL", "hooks", "routing_guard.py failed to execute: %s." % exc)
        return
    if result.returncode != 0:
        check("FAIL", "hooks", "routing_guard.py exited %d on a benign read "
              "(expected 0)." % result.returncode)
        return
    check("PASS", "hooks", "routing_guard.py and routing_observe.py are present, and "
          "the guard exits 0 on a benign read.")


def check_config() -> dict:
    """-> a usable merged config for the remaining checks, even when this file's own
    verdict is WARN or FAIL: paths.prod/docs/models must still evaluate against
    something rather than crash the whole run.
    """
    path = os.path.join(PROJECT, ".claude", "route.config.json")
    if not os.path.isfile(path):
        check("WARN", "config", "no .claude/route.config.json; defaults apply.")
        return DEFAULTS
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except Exception as exc:
        check("FAIL", "config", ".claude/route.config.json does not parse: %s." % exc)
        return DEFAULTS
    if not isinstance(doc, dict):
        check("FAIL", "config", ".claude/route.config.json is a %s, expected an "
              "object." % type(doc).__name__)
        return DEFAULTS
    if "paths" in doc and not isinstance(doc["paths"], dict):
        check("FAIL", "config", "paths is a %s, expected an object."
              % type(doc["paths"]).__name__)
        return DEFAULTS
    cfg = load_config(PROJECT)
    check("PASS", "config", ".claude/route.config.json parses, version %s."
          % cfg.get("version"))
    return cfg


def _tracked_files():
    try:
        result = subprocess.run(["git", "ls-files"], cwd=PROJECT,
                                capture_output=True, text=True)
    except OSError:
        result = None
    if result is not None and result.returncode == 0:
        return [line for line in result.stdout.splitlines() if line]
    out = []
    for root, dirs, files in os.walk(PROJECT):
        dirs[:] = [d for d in dirs if d != ".git"]
        for name in files:
            rel = os.path.relpath(os.path.join(root, name), PROJECT)
            out.append(rel.replace(os.sep, "/"))
    return out


def check_paths_prod(cfg: dict) -> None:
    patterns = cfg["paths"].get("prod") or []
    count = sum(1 for rel in _tracked_files() if matches_any(rel, patterns))
    if count > 0:
        check("PASS", "paths.prod", "%d file(s) match paths.prod." % count)
        return
    check("FAIL", "paths.prod",
          "0 files match paths.prod; builder is denied every write. Configured "
          "patterns: %s. An entry ending in '/' is a directory prefix; anything else "
          "is a glob (e.g. packages/*/src/**)." % ", ".join(patterns))


def check_paths_docs(cfg: dict) -> None:
    if not (cfg.get("bookkeeping") or {}).get("enabled"):
        check("PASS", "paths.docs", "bookkeeping disabled; no records expected.")
        return
    missing = [rel for rel in sorted(record_paths(cfg))
              if not os.path.isfile(os.path.join(PROJECT, rel))]
    if missing:
        check("WARN", "paths.docs", "missing: %s." % ", ".join(missing))
        return
    check("PASS", "paths.docs", "every hot record file exists.")


def check_models(cfg: dict) -> None:
    override = os.environ.get("CLAUDE_CODE_SUBAGENT_MODEL")
    if override:
        check("WARN", "models",
              "CLAUDE_CODE_SUBAGENT_MODEL=%s is set; it outranks every per-role tier, "
              "so the configured tiers below are not in force." % override)
        return
    models = cfg.get("models") or {}
    check("PASS", "models",
          "scout=%s architect=%s builder=%s reviewer=%s scribe=%s." % (
              models.get("scout"), models.get("architect"), models.get("builder"),
              models.get("reviewer"), models.get("scribe")))


def check_roles(cfg: dict) -> None:
    off = [r for r in ROUTE_ROLES if not role_enabled(cfg, r)]
    if not off:
        check("PASS", "roles", "all five roles may be dispatched.")
        return
    # Off is a valid configuration, not a fault: report it so a denied dispatch is
    # never a surprise.
    check("WARN", "roles",
          "%s turned off in roles.*.enabled; the guard denies those dispatches and the "
          "main session absorbs that work." % ", ".join(off))


def check_dispatch_log() -> None:
    path = os.path.join(PROJECT, ".claude", "routing", "dispatch.jsonl")
    if not os.path.isfile(path):
        check("WARN", "dispatch log",
              "no .claude/routing/dispatch.jsonl; nothing has been dispatched yet, "
              "or the observe hook is not running.")
        return
    total = 0
    blank = 0
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                row = json.loads(line)
            except Exception:
                continue
            total += 1
            if (row.get("agent_type") or "unknown") == "unknown":
                blank += 1
    if blank:
        check("WARN", "dispatch log",
              "%d of %d row(s) carry no role: the harness reported no agent_type. They "
              "are counted as `unknown` in the per-role split in /route:audit, not as "
              "main-thread turns." % (blank, total))
        return
    check("PASS", "dispatch log", "%d row(s) recorded." % total)


def check_transcripts() -> None:
    d = os.path.join(os.path.expanduser("~"), ".claude", "projects",
                     PROJECT.replace("/", "-"))
    count = 0
    if os.path.isdir(d):
        count = len([name for name in os.listdir(d) if name.endswith(".jsonl")])
    if count == 0:
        check("WARN", "transcripts",
              "no transcripts under %s; /route:audit and /route:delta have nothing "
              "to read." % d)
        return
    check("PASS", "transcripts", "%d transcript(s) under %s." % (count, d))


def run_check(name, fn, *args):
    """Run one check, turning an unexpected exception into a [FAIL] line for it
    instead of aborting the whole run. The summary line must always print.
    """
    try:
        return fn(*args)
    except Exception as exc:
        check("FAIL", name, "unexpected error: %s: %s" % (type(exc).__name__, exc))
        return None


def main() -> int:
    print("Checking routing setup for %s" % PROJECT)
    python3_path = run_check("interpreter", check_interpreter)
    run_check("hooks", check_hooks, python3_path)
    cfg = run_check("config", check_config) or DEFAULTS
    run_check("paths.prod", check_paths_prod, cfg)
    run_check("paths.docs", check_paths_docs, cfg)
    run_check("models", check_models, cfg)
    run_check("roles", check_roles, cfg)
    run_check("dispatch log", check_dispatch_log)
    run_check("transcripts", check_transcripts)
    print("%d failed, %d warnings, %d passed"
          % (COUNTS["FAIL"], COUNTS["WARN"], COUNTS["PASS"]))
    return 1 if COUNTS["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
