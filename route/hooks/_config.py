#!/usr/bin/env python3
"""Shared helpers for route's hooks and scripts.

Single source of truth for the three things that were previously duplicated across
routing_guard.py and routing_observe.py, and diverged:

  role normalization — a plugin subagent's `agent_type` arrives namespaced
      ("route:builder", or "route:sub:builder" for a nested agent file). Matching a
      bare "builder" against it silently fails, which is how every subagent rule in
      this guard came to be a no-op under `/plugin install`.
  path normalization — os.path.relpath returns "\\" separators on Windows, so any
      rule written as rel.startswith("docs/") is dead there. Everything downstream
      of rel_path() is POSIX-shaped.
  config loading — one DEFAULTS table, one deep merge, so a partial user config
      never leaves a key undefined.
"""
import json
import os
import re

MAIN_ALIASES = {"", "main", "default", "root", "none"}

# The roles this plugin owns. Any other agent in the repo is not ours to police.
ROUTE_ROLES = ("scout", "architect", "builder", "reviewer", "scribe")

# Stable names let the skill, the review nudge, and project configuration refer to
# the same policy without copying prose into three different files.
DEFAULT_REVIEW_TRIGGERS = (
    "no_red_green",
    "persistent_state",
    "authorization",
    "boundary",
    "silent_calculation",
    "control_flow",
    "builder_blocker",
)

DEFAULTS = {
    "version": 2,
    "paths": {
        "prod": ["src/"],
        "test": [
            "**/tests/**", "**/test/**", "**/e2e/**",
            "**/*.test.*", "**/*.spec.*",
            "**/*_test.go", "**/test_*.py", "**/*_test.py",
            "**/*_spec.rb", "**/*Test.java", "**/*Tests.cs",
        ],
        "docs": "docs/agent",
        "specs": "docs/agent/specs",
    },
    "models": {
        "scout": "haiku", "architect": "opus", "builder": "sonnet",
        "reviewer": "sonnet", "scribe": "haiku",
    },
    "bookkeeping": {
        "enabled": True,
        "timezone": "UTC",
        "records": {
            "tasks":    {"hot": "TASK.md",     "archive": "TASK_ARCHIVE.md"},
            "bugs":     {"hot": "BUG_FIX.md",  "archive": "FIXED_BUG.md"},
            "progress": {"hot": "PROGRESS.md", "archive": "PROGRESS_ARCHIVE.md", "keep": 2},
        },
        # The lookahead must swallow the whitespace itself: with `\s*(?!✅)` the star
        # backtracks to zero width and the negative lookahead then passes on a space,
        # so every entry reads as open.
        "openTaskPattern": r"^- \*\*Status\*\*:(?![ \t]*✅)",
    },
    "language": {"artifacts": "en"},
    "guard": {
        "mainSeverity": "ask",
        "readKB": 32,
        "scoutAt": 12,
        "bashWriteDetection": True,
    },
    "scout": {"enabled": True},
    "roles": {r: {"enabled": True} for r in ROUTE_ROLES},
    "review": {"policy": "risk", "nudge": True},
    "audit": {"charsPerToken": 4.0},
}


def normalize_role(raw) -> str:
    """-> 'main', or the bare role name with any plugin namespace stripped."""
    role = (raw or "").strip()
    if role.lower() in MAIN_ALIASES:
        return "main"
    # "route:builder" and "route:sub:builder" both resolve to "builder".
    return role.split(":")[-1].strip().lower()


def project_dir(payload=None) -> str:
    cwd = (payload or {}).get("cwd") if isinstance(payload, dict) else None
    return os.path.abspath(os.environ.get("CLAUDE_PROJECT_DIR") or cwd or os.getcwd())


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def _fold_legacy_scout(user: dict) -> dict:
    """`scout.enabled` predates `roles.scout.enabled`. Fold it in before the merge.

    After the merge every role carries an explicit `enabled`, so a v1 file's
    `scout.enabled: false` would be overwritten by the default and read as true.
    An explicit `roles.scout.enabled` wins: it is the current key.
    """
    legacy = (user.get("scout") or {}) if isinstance(user.get("scout"), dict) else {}
    if "enabled" not in legacy:
        return user
    roles = user.get("roles")
    roles = dict(roles) if isinstance(roles, dict) else {}
    entry = roles.get("scout")
    entry = dict(entry) if isinstance(entry, dict) else {}
    if "enabled" in entry:
        return user
    entry["enabled"] = legacy["enabled"]
    roles["scout"] = entry
    user = dict(user)
    user["roles"] = roles
    return user


def load_config(project: str) -> dict:
    path = os.path.join(project, ".claude", "route.config.json")
    try:
        with open(path, encoding="utf-8") as fh:
            user = json.load(fh)
    except Exception:
        user = {}
    if not isinstance(user, dict):
        user = {}
    return _merge(DEFAULTS, _fold_legacy_scout(user))


def role_enabled(cfg: dict, role) -> bool:
    """-> whether `role` may be dispatched. A role this plugin does not own is never
    blocked here."""
    name = normalize_role(role)
    if name not in ROUTE_ROLES:
        return True
    entry = (cfg.get("roles") or {}).get(name)
    if not isinstance(entry, dict):
        return True
    return bool(entry.get("enabled", True))


def rel_path(target: str, project: str):
    """-> repo-relative POSIX path, or None when the target is outside the project."""
    if not target:
        return None
    try:
        project_real = os.path.realpath(os.path.abspath(project))
        target_text = os.fspath(target)
        target_abs = (target_text if os.path.isabs(target_text)
                      else os.path.join(project_real, target_text))
        rel = os.path.relpath(os.path.realpath(target_abs), project_real)
    except ValueError:  # different drive on Windows
        return None
    rel = rel.replace(os.sep, "/")
    if rel.startswith("../") or rel == "..":
        return None
    return rel


def _glob_re(pattern: str):
    i, out = 0, []
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("^" + "".join(out) + "$")


_GLOB_CACHE = {}


def matches_any(rel: str, patterns) -> bool:
    """A pattern ending in '/' is a directory prefix; anything else is a glob."""
    for p in patterns or []:
        if not p:
            continue
        if p.endswith("/"):
            if rel == p.rstrip("/") or rel.startswith(p):
                return True
            continue
        rx = _GLOB_CACHE.get(p)
        if rx is None:
            rx = _GLOB_CACHE[p] = _glob_re(p)
        if rx.match(rel):
            return True
    return False


def _bk_files(cfg: dict, which):
    bk = cfg.get("bookkeeping") or {}
    if not bk.get("enabled"):
        return set()
    docs = (cfg["paths"]["docs"] or "").strip("/")
    out = set()
    for rec in (bk.get("records") or {}).values():
        for key in which:
            name = rec.get(key)
            if name:
                out.add("%s/%s" % (docs, name) if docs else name)
    return out


def record_paths(cfg: dict) -> set:
    return _bk_files(cfg, ("hot", "archive"))


def archive_paths(cfg: dict) -> set:
    return _bk_files(cfg, ("archive",))
