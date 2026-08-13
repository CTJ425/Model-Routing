# `route` plugin — 通用化重構規格

**執行對象**：Claude Code（在 `Model-Routing` repo 根目錄執行）
**格式**：每個 Task 用 `Contract` / `Files` / `Verify` / `Non-goals` 五段式，與本 plugin 自身
`SKILL.md` Step 2 的 Lane 1 brief 格式一致。
**執行順序**：Phase 依序做；Phase 內只有沒有檔案或驗證相依的 Task 可以平行。同一檔案、
同一測試入口或明確依賴前一 Task 的工作必須依序完成。每個 Phase 結束後跑一次該 Phase
的 `Verify`，全綠才進下一個 Phase。

## 實作邊界（執行前先接受）

- Lane 1 的 Builder 輸入可以是 inline brief；「spec file 必須存在」只適用於 Lane 2。
- `Files` 清單是 Builder 的 task-level contract；PreToolUse hook 只能 enforce role-level
  path categories，無法從工具 payload 讀回 prompt 內任意的清單。Builder 與 Reviewer 必須
  明確回報並檢查它。
- `review.nudge` 是可見性提醒，不是阻擋器。若要 mandatory review，必須另加 state check；
  否則文件只能使用 advisory／提醒的措辭。
- Builder 報告必須包含 `VERIFY:`、`TESTS:`、`LINT:`；Reviewer 不執行 command，Boss 在
  最終修正後重新執行 Verify。
- `bookkeeping.timezone` 同時適用於 Scribe 產生的 timestamp 與 guard 的 future check；
  `language.artifacts` 必須由 Boss 傳給每個需要輸出的 agent。

---

## 執行前必讀：三個貫穿全案的事實

1. **plugin subagent 的 `agent_type` 是 namespaced 的。**
   `agents/builder.md` 在 plugin `route` 中註冊為 `route:builder`；若放在子資料夾
   `agents/x/builder.md` 則是 `route:x:builder`。所有比對 role 名稱的程式碼都必須先正規化。

2. **plugin agent frontmatter 支援** `name` / `description` / `model` / `effort` /
   `maxTurns` / `tools` / `disallowedTools` / `skills` / `memory` / `background` /
   `isolation`；**不支援** `hooks` / `mcpServers` / `permissionMode`。不要在 agent 檔案裡
   寫這三個欄位。

3. **model 解析優先序**：`CLAUDE_CODE_SUBAGENT_MODEL` 環境變數 > Agent 工具的
   per-invocation `model` 參數 > agent frontmatter `model:`。
   若使用者設了那個環境變數，`route.config.json` 的 `models` 會被完全蓋掉。

---

# Phase 0 — 建立測試骨架

沒有測試的話，Phase 1 修好的東西會在 Phase 4 重構時再壞一次。先做這個。

## Task 0.1 — 建立 pytest 骨架

```
Contract:
  - 專案根目錄可執行 `python3 -m pytest tests/ -q` 並通過
  - tests/conftest.py 提供 fixture：一個 tmp_path 上的假專案，含
    src/、tests/、docs/agent/、.claude/route.config.json
  - tests/helpers.py 提供 run_guard(payload: dict) -> dict|None
    以 subprocess 呼叫 hooks/routing_guard.py，餵 stdin，回傳 parse 後的 stdout JSON
    （無輸出時回 None），並斷言 returncode == 0
Files:
  tests/__init__.py
  tests/conftest.py
  tests/helpers.py
  pytest.ini
Verify:
  python3 -m pytest tests/ -q
Non-goals:
  - 不要寫任何實際測試案例，那是 Task 1.5 的事
  - 不要引入 pytest 以外的相依套件
```

`tests/helpers.py` 的 `run_guard` 必須以 `env={"CLAUDE_PROJECT_DIR": str(project)}` 傳入
專案路徑，不要依賴 cwd。

---

# Phase 1 — P0 修復（決定 plugin 是否有作用）

## Task 1.1 — 抽出 `hooks/_config.py` 共用模組

目前 role 正規化、路徑正規化、config 讀取三件事散在 `routing_guard.py` 與
`routing_observe.py` 各寫一份，P0 的 namespace bug 就是這樣漏掉的。先集中。

```
Contract:
  建立 hooks/_config.py，匯出以下 API：
    MAIN_ALIASES: set[str]
    normalize_role(raw: str|None) -> str
    project_dir(payload: dict|None = None) -> str
    load_config(project: str) -> dict          # 與 DEFAULTS deep-merge
    rel_path(abs_or_rel: str, project: str) -> str|None   # POSIX 分隔符；越界回 None
    matches_any(rel: str, patterns: list[str]) -> bool     # 支援 ** / * / ?，及結尾 / 的 prefix
    record_paths(cfg: dict) -> set[str]        # bookkeeping 的 hot + archive 的 repo 相對路徑
    archive_paths(cfg: dict) -> set[str]
  不得 import 除標準函式庫以外的任何東西
Files:
  hooks/_config.py
Verify:
  python3 -c "import sys; sys.path.insert(0,'hooks'); import _config; print(_config.normalize_role('route:x:builder'))"
  # 必須輸出 builder
Non-goals:
  - 不要在這個 Task 改動 routing_guard.py / routing_observe.py
```

完整實作：

```python
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
        "scout": "haiku", "builder": "sonnet",
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
        "openTaskPattern": r"^- \*\*Status\*\*:\s*(?!\u2705)",
    },
    "language": {"artifacts": "en"},
    "guard": {
        "mainSeverity": "ask",
        "readKB": 32,
        "scoutAt": 12,
        "bashWriteDetection": True,
    },
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


def load_config(project: str) -> dict:
    path = os.path.join(project, ".claude", "route.config.json")
    try:
        with open(path, encoding="utf-8") as fh:
            user = json.load(fh)
    except Exception:
        user = {}
    if not isinstance(user, dict):
        user = {}
    return _merge(DEFAULTS, user)


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


def _glob_re(pattern: str) -> "re.Pattern":
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
                out.add(f"{docs}/{name}" if docs else name)
    return out


def record_paths(cfg: dict) -> set:
    return _bk_files(cfg, ("hot", "archive"))


def archive_paths(cfg: dict) -> set:
    return _bk_files(cfg, ("archive",))
```

---

## Task 1.2 — 重寫 `hooks/routing_guard.py`

這支是 P0-1 / P0-2 / P0-3 三個問題的交集點，直接整檔替換比打補丁可靠。

```
Contract:
  1. role 一律經 _config.normalize_role() —— "route:builder" 必須命中 builder 的規則
  2. 所有路徑判斷經 _config.rel_path() —— 全程 POSIX 分隔符
 3. RECORDS / ARCHIVES / TEST / docs scope 樣式全部來自 config，不再硬編碼
  4. archive 讀取限制改用 repo 相對路徑比對，不再用 basename
     （現況：專案根目錄的 CHANGELOG.md 會被誤擋）
 5. 時間戳檢查：strptime 失敗不得拋例外；語法合法但語意非法的日期本身視為違規；
     future check 使用 bookkeeping.timezone，不使用 hook process 的本地 timezone
  6. main() 全域包 try/except，任何未預期例外一律 sys.exit(0)（fail-open 但不噴 error）
  7. 新增 Bash 寫入偵測（cfg.guard.bashWriteDetection，預設 true）：
     - 純唯讀角色（scout / reviewer）偵測到寫入樣式 -> deny
     - builder / scribe -> ask（無法可靠解析 bash 目標，交由使用者判斷）
     - main -> 不管
  8. bookkeeping.enabled = false 時，"record" 這個分類不存在，相關規則全部停用
  9. builder 只能透過 file tools 寫 production-code paths；scribe 只能寫 paths.docs
     之下的檔案。未知 role 不套用 timestamp 或其他 routing policy。
Files:
  hooks/routing_guard.py
Verify:
  python3 -m pytest tests/test_guard.py -q     # Task 1.5 會建立
  echo '{"tool_name":"Write","agent_type":"route:scout","tool_input":{"file_path":"src/a.ts"}}' \
    | CLAUDE_PROJECT_DIR=$PWD python3 hooks/routing_guard.py
  # 必須輸出 permissionDecision: deny
Non-goals:
  - 不要改變既有的環境變數介面（ROUTING_GUARD / ROUTING_MAIN / ROUTING_READ_KB 仍需可用，
    但優先序改為：環境變數 > config > 預設）
  - 不要在這一步處理 reviewer 缺席的偵測（那是 Task 3.3）
```

完整實作：

```python
#!/usr/bin/env python3
"""PreToolUse guard that makes role boundaries real instead of prompt etiquette.

Four jobs, selected by tool_name.

  Read              — polices what gets pulled into the main session's context.
                      Replaying context dominates a routed session's spend: a large
                      file read once is re-billed on every remaining turn. Bounded
                      reads (`limit` set) always pass.
  Agent|Task        — polices who gets dispatched. The built-in discovery agents
                      inherit the caller's model, so they do scout's job at the
                      caller's price.
  Write|Edit|...    — polices what a role may write, and rejects a future-dated
                      timestamp in a tracking record.
  Bash              — best-effort detection of writes that route around the file
                      tools. This is a backstop, not a gate: the real enforcement
                      for a read-only role is not giving it Bash at all.

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
    archive_paths, load_config, matches_any, normalize_role, project_dir,
    record_paths, rel_path,
)

READ_ONLY_ROLES = {"scout", "reviewer"}

READ_REASON = (
    "Reading {name} ({kb}KB) into the main session's context re-bills it on every "
    "remaining turn — context replay is most of a routed session's cost. Two cheaper "
    "paths: dispatch `scout` with a specific question, or re-issue this Read with "
    "`offset`/`limit` for just the part you need."
)

ARCHIVE_REASON = (
    "`scribe` must not read {name} — an archive is larger than this role's context and "
    "there is never a need. Prepend with `Edit` anchored on the file's header line, "
    "append with a Bash heredoc, locate with `grep -n`, inspect with `sed -n '<range>p'`."
)

TS_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}\b")
TS_TOLERANCE_S = 120
TS_REASON = (
    "{stamps} is not a valid past timestamp; it is now {now}. A record logs what already "
    "happened, so a future or malformed stamp is fabricated. Run "
    "`date '+%Y-%m-%d %H:%M:%S'` and write what it returns — never estimate, and never "
    "carry a stamp over from an earlier draft."
)

DISCOVERY_AGENTS = {"explore", "general-purpose"}
DISCOVERY_REASON = (
    "`{name}` inherits this session's model, so it maps the codebase at or near the "
    "highest rate in the system. `scout` is the same job on a cheap tier with a 40-line "
    "output ceiling: dispatch it with a specific question instead. Confirm only if you "
    "need a tool scout lacks."
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
BASH_REASON = (
    "This Bash command looks like it writes to the filesystem, and `{role}` may not write "
    "{scope}. Writing through Bash routes around the file-tool guard; that is out of role, "
    "not a workaround. Report the blocker instead."
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

RULES = {
    "main": {"prod": "@main", "record": "@main"},
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
    """Return a naive wall-clock value in the configured IANA timezone."""
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
        finally:
            if had_tz:
                os.environ["TZ"] = old_tz
            else:
                os.environ.pop("TZ", None)
            time.tzset()
    return datetime.datetime.now()


def handle_dispatch(role, tool_input) -> None:
    spawned = (tool_input.get("subagent_type") or "").strip()
    if normalize_role(spawned) in DISCOVERY_AGENTS or spawned.lower() in DISCOVERY_AGENTS:
        respond("ask", f"[routing/{role}] " + DISCOVERY_REASON.format(name=spawned))
    sys.exit(0)


def handle_read(role, tool_input, project, cfg) -> None:
    target = tool_input.get("file_path")
    rel = rel_path(target, project)
    if role == "scribe" and rel and rel in archive_paths(cfg):
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
        respond("ask", "[routing/main] " + READ_REASON.format(
            name=os.path.basename(target), kb=size // 1024))
    sys.exit(0)


def handle_bash(role, tool_input, cfg) -> None:
    if not cfg["guard"].get("bashWriteDetection", True):
        sys.exit(0)
    if role not in RULES or role == "main":
        sys.exit(0)
    command = tool_input.get("command") or ""
    if not BASH_WRITE_RE.search(command):
        sys.exit(0)
    if role in READ_ONLY_ROLES:
        respond("deny", f"[routing/{role}] " + BASH_REASON.format(
            role=role, scope="anything at all — it is read-only"))
    scope = {
        "builder": "outside the spec's Files list",
        "scribe": f"outside {cfg['paths']['docs']}/",
    }.get(role, "here")
    respond("ask", f"[routing/{role}] " + BASH_REASON.format(role=role, scope=scope))


def handle_write(role, tool_input, project, cfg) -> None:
    rel = rel_path(tool_input.get("file_path"), project)
    if rel is None:
        sys.exit(0)
    cls = classify(rel, cfg)

    if cls == "record":
        body = tool_input.get("new_string") or tool_input.get("content") or ""
        timezone = (cfg.get("bookkeeping") or {}).get("timezone") or "UTC"
        now = now_in_timezone(timezone)
        ahead = bad_stamps(body, now)
        if ahead:
            respond("deny", f"[routing/{role}] " + TS_REASON.format(
                stamps=", ".join(ahead[:3]), now=now.strftime("%Y-%m-%d %H:%M:%S")))

    rules = RULES.get(role)
    if not rules:
        sys.exit(0)
    decision = rules.get(cls) or rules.get("*")
    if not decision:
        sys.exit(0)

    if decision == "@main":
        level = (os.environ.get("ROUTING_MAIN")
                 or cfg["guard"].get("mainSeverity") or "ask").lower()
        if level == "off":
            sys.exit(0)
        decision = "deny" if level == "deny" else "ask"

    reason = REASONS.get((role, cls)) or (
        f"Role `{role}` may not write {cls} files. See the `route` skill.")
    respond(decision, f"[routing/{role}] {reason}")


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
        handle_dispatch(role, tool_input)
    if tool == "Read":
        handle_read(role, tool_input, project, cfg)
    if tool == "Bash":
        handle_bash(role, tool_input, cfg)
    handle_write(role, tool_input, project, cfg)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        # A guard that crashes must not also break the session. Fail open, quietly.
        sys.exit(0)
```

上述 code block 是 P0 baseline；完成版還必須套用本節前的實作邊界：builder 對非 production
path default-deny、scribe 只允許 paths.docs、scribe 的 Bash 例外只接受 `cat >>` literal
append、scribe 不得執行 git mutation，且未知 role 不執行 timestamp check。不要把 baseline
block 原封不動覆蓋已完成的 scope／timezone 修正。

---

## Task 1.3 — `hooks/hooks.json`：加 Bash matcher、改用 exec form

```
Contract:
  1. PreToolUse matcher 加入 Bash（新增一個 matcher group，不要塞進現有那組，
     因為 Bash 的處理路徑不同且未來可能要加 `if` 條件）
  2. 全部 hook 改用 exec form：command 為 "python3"，路徑放進 args
     （官方建議：凡引用 ${CLAUDE_PLUGIN_ROOT} 的 hook 優先用 exec form，避免路徑含空白）
  3. 加上 top-level "description"
  4. 新增 PostToolUse 的 Agent|Task matcher group（給 Task 3.3 的 reviewer nudge 用）
  5. 新增 SessionEnd，清理本 session 的 state 檔（Task 2.4）
Files:
  hooks/hooks.json
Verify:
  python3 -c "import json;json.load(open('hooks/hooks.json'))"
  claude plugin validate . --strict      # 若環境有 claude CLI
Non-goals:
  - 不要改 timeout 值
```

完整內容：

```json
{
  "description": "Model-routing guards and observability for the route plugin",
  "hooks": {
    "SessionStart": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python3",
            "args": ["${CLAUDE_PLUGIN_ROOT}/hooks/routing_observe.py"],
            "timeout": 10
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Write|Edit|NotebookEdit|Agent|Task|Read",
        "hooks": [
          {
            "type": "command",
            "command": "python3",
            "args": ["${CLAUDE_PLUGIN_ROOT}/hooks/routing_guard.py"],
            "timeout": 10
          }
        ]
      },
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3",
            "args": ["${CLAUDE_PLUGIN_ROOT}/hooks/routing_guard.py"],
            "timeout": 10
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Read|Grep|Glob",
        "hooks": [
          {
            "type": "command",
            "command": "python3",
            "args": ["${CLAUDE_PLUGIN_ROOT}/hooks/routing_observe.py"],
            "timeout": 10
          }
        ]
      },
      {
        "matcher": "Agent|Task",
        "hooks": [
          {
            "type": "command",
            "command": "python3",
            "args": ["${CLAUDE_PLUGIN_ROOT}/hooks/routing_observe.py"],
            "timeout": 10
          }
        ]
      }
    ],
    "SubagentStart": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python3",
            "args": ["${CLAUDE_PLUGIN_ROOT}/hooks/routing_observe.py"],
            "timeout": 10
          }
        ]
      }
    ],
    "SubagentStop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python3",
            "args": ["${CLAUDE_PLUGIN_ROOT}/hooks/routing_observe.py"],
            "timeout": 10
          }
        ]
      }
    ],
    "SessionEnd": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python3",
            "args": ["${CLAUDE_PLUGIN_ROOT}/hooks/routing_observe.py"],
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

---

## Task 1.4 — 收緊 agent frontmatter 的 `tools`

Bash 偵測是啟發式的、永遠不完備。真正的強制是不給工具。

```
Contract:
  agents/scout.md      tools: Read, Glob, Grep            （移除 Bash）
  agents/reviewer.md   tools: Read, Glob, Grep            （移除 Bash）
  agents/builder.md    tools: Read, Glob, Grep, Write, Edit, Bash   （不變）
  agents/scribe.md     tools: Read, Glob, Grep, Write, Edit, Bash   （加入 Write/Glob/Grep）
  移除所有 agent 的 disallowedTools —— tools 已是白名單，disallowedTools 是多餘的，
  兩者並存只會讓讀者以為某個欄位有額外效果
Files:
  agents/scout.md
  agents/reviewer.md
  agents/builder.md
  agents/scribe.md
Verify:
  grep -c "disallowedTools" agents/*.md     # 全部為 0
  grep "^tools:" agents/*.md
Non-goals:
  - 不要在這個 Task 改 agent 的正文
```

**scout 拿掉 Bash 的連帶影響**：`scout.md` 的 Compress mode（壓縮測試輸出／堆疊追蹤）
原本可能靠 Bash 跑指令取得 log。改為：**呼叫端負責把 log 寫成檔案或貼進 prompt**，
scout 只負責 Read + 壓縮。在 `scout.md` 的 Compress mode 段落加一句：

> You do not run commands. Your caller gives you either the log text in the prompt or a
> path to read. If you were given neither, say so in one line and stop.

**reviewer 拿掉 Bash 的連帶影響**：`SKILL.md` Step 4 要註明「builder 已在報告中附上
verify 指令與結果，reviewer 讀那份報告，不自己跑測試」。

---

## Task 1.5 — 撰寫 guard 測試

```
Contract:
  tests/test_guard.py 至少涵蓋以下案例，全部必須通過：

  role 正規化（這是 P0-1 的回歸測試）
    ("builder", "docs/x.md", Write)        -> deny
    ("route:builder", "docs/x.md", Write)  -> deny     ← 修復前是放行
    ("route:sub:builder", "docs/x.md")     -> deny
    ("route:scout", "src/a.ts", Write)     -> deny     ← 修復前是放行
    ("Explore", "src/a.ts", Write)         -> 放行（未知 role 不受管）

  路徑
    ("builder", "src/a.ts", Write)         -> 放行
    ("builder", "tests/a_test.go", Write)  -> deny
    ("builder", "test_a.py", Write)        -> deny
    ("builder", "a.spec.ts", Write)        -> deny
    ("scribe", "docs/agent/TASK.md", Write)-> 放行
    ("scribe", "src/a.ts", Write)          -> deny
    絕對路徑與相對路徑必須得到相同結果

  時間戳（P0-3 回歸測試）
    scribe 寫 record 含 "2026-13-45 99:99:99" -> deny，且 returncode == 0
    scribe 寫 record 含 未來 1 小時的合法時間  -> deny
    scribe 寫 record 含 現在時間               -> 放行

  archive 讀取（P1-2.3 回歸測試）
    ("scribe", Read, "CHANGELOG.md")                     -> 放行  ← 修復前誤擋
    ("scribe", Read, "docs/agent/TASK_ARCHIVE.md")       -> deny

  Bash
    ("route:scout", Bash, "cat > src/a.ts")   -> deny
    ("route:scout", Bash, "grep -n foo src/") -> 放行
    ("route:builder", Bash, "sed -i s/a/b/ x")-> ask
    ("route:builder", Bash, "npm test")       -> 放行
    ("route:builder", Bash, "npm test > /dev/null") -> 放行
    scribe 的 `cat >> <path>` 只有 paths.docs 之下放行；`cat > <path>` 一律 ask

  scope 與 timezone
    scribe 寫 docs/agent/notes.md -> 放行
    scribe 寫 README.md -> deny
    builder 寫 README.md -> deny
    scribe 執行 git add / commit / push -> deny
    未知 role 在 record 內含 malformed timestamp -> 放行
    bookkeeping.timezone=Asia/Taipei 時，Asia/Taipei 的現在時間 -> 放行

  bookkeeping 關閉時
    cfg.bookkeeping.enabled = false 時，("builder", "docs/agent/TASK.md") 分類為 doc 而非 record

Files:
  tests/test_guard.py
Verify:
  python3 -m pytest tests/test_guard.py -q
Non-goals:
  - 不要測 routing_audit / dispatch_delta（那需要造假 transcript，另案）
```

---

# Phase 2 — 可攜性與正確性

## Task 2.1 — 重寫 `hooks/routing_observe.py`

```
Contract:
  1. 改用 _config（role 正規化、project_dir、load_config）
  2. SessionStart brief：
     - 32KB 改為讀 cfg.guard.readKB
     - bookkeeping.enabled=false 時，整份 brief 不提 task/bug 計數，也不提 scribe
     - TASK.md / BUG_FIX.md 兩者都讀不到時，省略該行，不要印 "? task(s)"
     - open task 判定改用 cfg.bookkeeping.openTaskPattern，不再硬編碼 "✅"
  3. discovery 計數改用 append-only：每次寫一行到
     .claude/routing/state/<session>.count，計數 = 檔案行數。消除 read-modify-write race
  4. 新增 SessionEnd 分支：刪除本 session 的 state 檔
  5. 新增 PostToolUse(Agent|Task) 分支 -> 交給 Task 3.3
  6. dispatch.jsonl 超過 5MB 時 rotate 成 dispatch.jsonl.1
  7. log_dispatch 額外記錄 payload 的 transcript_path 與 agent_transcript_path
     （若存在），讓稽核腳本不必猜測內部目錄結構
Files:
  hooks/routing_observe.py
Verify:
  echo '{"hook_event_name":"SessionStart","session_id":"t1"}' \
    | CLAUDE_PROJECT_DIR=$PWD python3 hooks/routing_observe.py | python3 -m json.tool
Non-goals:
  - 不要改變 ROUTING_OBSERVE / ROUTING_SCOUT_AT 環境變數介面
```

SessionStart brief 的新文案（`bookkeeping.enabled = true` 時的完整版；為 false 時刪除
第 2 點的 scribe 與最後一行）：

```
[routing] This project delegates. Before acting on a feature or a bug, load the
`route` skill and state the lane in one line.

- **Cost here is context replay, not output.** Replaying context into the main
  session's window is billed on every remaining turn of the session, so bulk content
  goes to a subagent even when the task looks trivial.
- **Roster.** This session plans, writes specs, and adjudicates. `scout` reads and
  compresses; `builder` implements; `reviewer` checks risk work; `scribe` records.
  Delegation is pre-authorized — dispatch without asking. Dispatch by scoped name
  (`route:scout`, `route:builder`, ...). Per-role model tiers live in
  `.claude/route.config.json` (see `/route:config`).
- **Guards will ask** before this session edits production code or a tracking record,
  dispatches `Explore`/`general-purpose`, or issues an unbounded Read over {read_kb}KB.
  An `ask` is policy, not an obstacle: take the cheaper path it names.
- **Open now:** {tasks} task(s), {bugs} open bug(s).
```

---

## Task 2.2 — `scripts/` 拆分與稽核工具修正

```
Contract:
  1. git mv hooks/routing_audit.py    scripts/routing_audit.py
     git mv hooks/dispatch_delta.py   scripts/dispatch_delta.py
     兩者都 sys.path 掛上 ../hooks 以取用 _config
  2. routing_audit.py：
     - PRICES 移出程式碼，改讀 scripts/pricing.json；
       cfg.audit.pricingFile 可覆寫為專案自有的路徑
     - 修 by_role["main"]["runs"] = 1 -> += 1（--all 時 main 的 run 數目前恆為 1）
     - transcript 目錄解析：優先讀 .claude/routing/dispatch.jsonl 記下的
       transcript_path；退而求其次才用 ~/.claude/projects/<munged> 猜測
     - 找不到 subagent transcript 時，區分兩種情況並輸出不同訊息：
         a. session 目錄不存在或無 subagents/ 子目錄
            -> "could not locate subagent transcripts under <path>; the transcript
                layout may have changed. This is NOT evidence that nothing was routed."
         b. 目錄存在但為空
            -> "(no subagent transcripts — nothing was routed in this session)"
  3. dispatch_delta.py：
     - CHARS_PER_TOKEN 改讀 cfg.audit.charsPerToken
     - USD_PER_TOKEN_REPLAY 改為依實際主 model 從 pricing.json 推算，
       推不出來時退回目前的常數並在 footer 註明
     - footer 加一句：chars/N 對 CJK 內容會顯著低估，中日韓專案請跑 --validate 校準
       cfg.audit.charsPerToken
Files:
  scripts/routing_audit.py
  scripts/dispatch_delta.py
  scripts/pricing.json
  hooks/routing_audit.py     (刪除)
  hooks/dispatch_delta.py    (刪除)
Verify:
  python3 scripts/routing_audit.py --help
  python3 scripts/dispatch_delta.py --help
Non-goals:
  - 不要改動兩支腳本的統計演算法本身，只改資料來源與輸出訊息
```

`scripts/pricing.json` 的形狀（**價格數字必須由使用者自行核對官方定價頁後填寫，
不要相信這份規格裡的數字**）：

```json
{
  "_comment": "USD per million tokens. Verify against the official pricing page before trusting the USD columns. Keys are matched by prefix against the model id in the transcript.",
  "cacheMultipliers": { "read": 0.1, "write5m": 1.25, "write1h": 2.0 },
  "models": {
    "claude-opus-":   { "in": 5.0, "out": 25.0 },
    "claude-sonnet-": { "in": 3.0, "out": 15.0 },
    "claude-haiku-":  { "in": 1.0, "out": 5.0 }
  }
}
```

---

## Task 2.3 — 新增 `/route:audit` 與 `/route:delta` 指令

現況 README 叫使用者自己去 `~/.claude/plugins/` 底下找腳本路徑，UX 不可接受。

```
Contract:
  commands/audit.md  —— 執行 python3 ${CLAUDE_PLUGIN_ROOT}/scripts/routing_audit.py $ARGUMENTS
                        並把輸出原樣呈現，附一段兩三句的解讀（哪個 role 花最多、
                        main 佔比是否過高）
  commands/delta.md  —— 同上，對 dispatch_delta.py
  兩者 frontmatter 都要有 description 與 argument-hint
Files:
  commands/audit.md
  commands/delta.md
Verify:
  ls commands/    # init.md config.md audit.md delta.md
Non-goals:
  - 指令本身不要重新實作統計邏輯，只負責呼叫腳本
```

---

## Task 2.4 — `.gitignore` 與狀態檔生命週期

```
Contract:
  1. plugin repo 自身的 .gitignore 加入：.pytest_cache/、.claude/routing/
  2. commands/init.md 增加一步：把 ".claude/routing/" 寫進「目標專案」的 .gitignore
     （若該行已存在則跳過並回報）
  3. routing_observe.py 的 SessionEnd 分支刪除 .claude/routing/state/<session>.*
Files:
  .gitignore
  commands/init.md
  hooks/routing_observe.py
Verify:
  grep -q "^\.claude/routing/$" .gitignore
Non-goals:
  - .claude/route.config.json 應該被 commit，不要加進 .gitignore
```

---

# Phase 3 — 修復 reviewer 從不被觸發

## 問題摘要（給執行者的背景）

reviewer 沒動作不是壞掉，是四個原因疊加：

1. `SKILL.md` Step 4 明說 ordinary work 跳過 reviewer，觸發清單
   （`money, positions, fees, prices, auth/RLS, ...`）是金融 + Supabase 專案的殘留，
   在其他技術棧上一個關鍵字都不會命中。
2. Step 0 的 Lane 1 路徑寫 `... -> builder -> reviewer -> scribe`，與 Step 4 矛盾。
   LLM 通常採信較具體、較晚出現的那條 -> 跳過。
3. `reviewer.md` 的 description 寫 `Requires both the spec path and the changed file
   list`，但 Lane 1 依設計就沒有 spec 檔 -> Boss 判定無法呼叫。
4. 沒有任何 hook 在 reviewer 缺席時出聲。scout 缺席有計數器、main 亂寫有 ask、
   時間戳造假有 deny —— 只有 reviewer 缺席是完全靜默的。

四個都要修，缺一個都還是不會跑。

## Task 3.1 — 改寫 `SKILL.md` Step 4 的觸發條件

```
Contract:
  1. 觸發清單改為 stack-agnostic 的風險判準，取代現行的 money/positions/fees/prices/RLS 清單
  2. 觸發條件本身可由 config 覆寫（cfg.review.policy 與 cfg.review.triggers）
  3. Step 0 的 Lane 1 路徑改寫為與 Step 4 一致，消除矛盾
  4. Step 4 加一句：builder 已在報告中附上 verify 指令與結果，reviewer 讀那份報告，
     不自己跑測試（配合 Task 1.4 拿掉 reviewer 的 Bash）
Files:
  skills/route/SKILL.md
Verify:
  人工閱讀：Step 0 表格的 Lane 1 路徑與 Step 4 的敘述不得互相矛盾
Non-goals:
  - 不要改 Step 5 的裁決表
```

Step 4 的新內文：

```markdown
## Step 4 — review (sonnet by default)

Check `review.policy` in `.claude/route.config.json`:

| policy | behaviour |
| --- | --- |
| `always` | dispatch `reviewer` on every builder round |
| `risk` (default) | dispatch when any trigger below fires |
| `never` | never dispatch; the test is the only gate |

Under `risk`, dispatch `reviewer` when **any** configured trigger is true. The default
trigger IDs are:

1. `no_red_green`: **The change is not fully covered by a test that failed before and passes now.**
   A green suite that never exercised the change proves nothing.
2. `persistent_state`: It touches state that outlives the process — database, filesystem, cache, queue,
   or anything persisted.
3. `authorization`: It touches an authorization or access-control decision.
4. `boundary`: It touches a boundary another system depends on — API shape, wire format, file
   format, CLI flags, public function signatures.
5. `silent_calculation`: It touches a calculation whose wrong answer is **silent**: no exception, just a
   wrong number.
6. `control_flow`: It changes control flow, error handling, concurrency, retry, or timeout behaviour.
7. `builder_blocker`: Builder reported anything under `BLOCKERS`.

No test suite does not automatically disable `no_red_green`: it is satisfied only when the
Verify command observes the changed behaviour and the Boss records what output would have
shown a wrong result. A compile-only command is not enough. A project may replace this list
with these seven trigger IDs in `review.triggers`; an empty list means no automatic risk
trigger. `review.policy=always` still reviews every builder round.

Pass reviewer the brief **or** the spec path, plus builder's reported file list and
`VERIFY:`, `TESTS:`, and `LINT:` lines. Reviewer has no Bash — it reads builder's reported
command and result rather than re-running anything. Boss reruns the final Verify after a
review fix. It returns `PASS`/`FAIL` and findings, never fixes.

If you skip review, say so in one line and name which trigger you checked. A silent
skip is how this step stopped happening.
```

Step 0 表格的 Lane 1 那一列改成：

```
| **1 — bounded** (default) | A clear fix or feature inside known modules | `scout` (if the area is unmapped) -> brief -> `builder` -> `reviewer` (per Step 4 policy) -> `scribe` |
```

## Task 3.2 — 改寫 `reviewer.md` 的 description

```
Contract:
  description 必須讓 Lane 1（無 spec 檔）也能合法呼叫
Files:
  agents/reviewer.md
Verify:
  grep "^description:" agents/reviewer.md
Non-goals:
  - 不要改正文的檢查清單與嚴重度分級 —— 那部分是通用且寫得好的，保留
```

新的 frontmatter：

```yaml
---
name: reviewer
description: Use to review code a builder has just produced. Requires the builder's changed-file list plus either the inline brief or a spec path — an inline brief is sufficient and is the normal case for bounded work. Returns findings only, never fixes.
model: sonnet
effort: medium
maxTurns: 25
tools: Read, Glob, Grep
---
```

正文開頭加一段（讓它在沒有 spec 檔時知道怎麼辦）：

```markdown
## Your input

You get one of two things as the contract to review against:

- an **inline brief** in your dispatch prompt (`Task` / `Contract` / `Files` / `Verify`
  / `Non-goals`), or
- a **spec file path**, which you read.

Either is sufficient. "The spec" below means whichever one you were given. You also get
builder's changed-file list and its reported `VERIFY:`, `TESTS:`, and `LINT:` lines. You do
not run commands — if builder's report does not say the verify command passed, that is a
finding.
```

## Task 3.3 — 新增 reviewer 缺席的可見性 hook

```
Contract:
  在 routing_observe.py 新增 PostToolUse(Agent|Task) 分支：
    - 只在主 session（normalize_role == "main"）觸發
    - 讀 tool_input.subagent_type，normalize 後判斷
    - 若為 builder，且 cfg.review.policy != "never"，且 cfg.review.nudge 為 true：
      回傳 additionalContext，提醒 Boss 對照 Step 4 的 trigger IDs，
      並要求「若決定跳過，在回覆中用一行說明檢查了哪一條」
    - 若為 reviewer：不輸出（正常路徑不該有噪音）
    - 每次 builder dispatch 提醒一次即可，不需累計狀態
Files:
  hooks/routing_observe.py
Verify:
  echo '{"hook_event_name":"PostToolUse","tool_name":"Agent","session_id":"t1","tool_input":{"subagent_type":"route:builder"}}' \
    | CLAUDE_PROJECT_DIR=$PWD python3 hooks/routing_observe.py
  # 必須輸出含 additionalContext 的 JSON
Non-goals:
  - 不要 block 任何東西。這是 PostToolUse，只能注入 context
  - 不要在 subagent 內觸發（subagent 不能再生 subagent）
```

additionalContext 文案：

```
[routing] `builder` just returned. Before recording, apply the Step 4 review policy:
review is required if the change is not covered by a test that failed before and passes
now, or if it touches persisted state, an authorization decision, a boundary another
system depends on, a silently-wrong calculation, or builder reported a blocker. If you
are skipping review, name in one line which of those you checked. If you are not
skipping, dispatch `route:reviewer` now with the brief, builder's file list, and
builder's VERIFY line.
```

---

# Phase 4 — config v2 與去專案化

## Task 4.1 — config schema 與 `/route:init` `/route:config` 升級

```
Contract:
  1. 建立 schema/route.config.schema.json（JSON Schema draft-07），涵蓋 _config.DEFAULTS
     的所有鍵，models 的值不做列舉限制（接受任何 alias 或完整 model id）
  2. commands/init.md 產生 version: 2 的完整 config，並且：
     - prod 路徑偵測不到時要問使用者，不要猜
     - 詢問使用者是否啟用 bookkeeping（預設問法：「要不要讓 plugin 幫你維護
       docs/agent/ 下的任務/bug/進度記錄？不需要的話只保留 model routing」）
     - 詢問 language.artifacts（en / zh-TW / 其他）
     - 偵測到已有 version 1 的 config（沒有 "version" 鍵）時，就地升級並回報差異，
       不要覆寫使用者已設定的值
  3. commands/config.md：
     - 支援 <role>=<model> 之外，也支援 review.policy=always 這種點記法
     - 每次輸出前偵測 CLAUDE_CODE_SUBAGENT_MODEL 環境變數；若有設定，
       明確警告「這個環境變數優先於本檔案，目前 models 設定不會生效」
     - 加 argument-hint frontmatter
Files:
  schema/route.config.schema.json
  commands/init.md
  commands/config.md
Verify:
  python3 -c "import json;json.load(open('schema/route.config.schema.json'))"
Non-goals:
  - 不要做 config 的 runtime schema 驗證（會引入 jsonschema 相依）；
    _config.load_config 的 deep-merge 已經保證每個鍵有值
```

## Task 4.2 — 重寫 `agents/scribe.md`（最大宗的去專案化）

目前 166 行裡約一半是某個實際專案的殘留。**規則留下，軼事與格式移出。**

```
Contract:
  移除以下全部項目：
    - "Asia/Taipei" 時區硬編碼           -> 改為「使用 config 指定的時區；由呼叫端在
                                            dispatch prompt 中給出時區名稱」
    - 引用 "CLAUDE.md § Work style"      -> 刪除（該檔案不存在於通用專案）
    - "Task 91 and Task 92 were destroyed"、"~50 minutes in the future"、
      "2.7% of token count" 等具體事故敘事 -> 改寫為原則（見下）
    - "PROGRESS_ARCHIVE.md (405KB), TASK_ARCHIVE.md (154KB)" 具體檔案大小
    - "cron.job.command"、"Edge Function"、RLS 等特定 stack 用語
    - "The repo is public and those channels have no secret-scanning gate" 的假設
      -> 改寫為條件句：「若你的呼叫端說這個 repo 是公開的，則 ...」
    - emoji 格式綁定（## 📅 Log:、📋 Active Tasks、✅、🔄、🐛）-> 移入 templates/
    - "0.6.44"、"Bug ID: BUG-023" 等版本與編號範例 -> 移入 templates/
    - "~~" + "⏳" 混合條目那條規則        -> 移入 templates/，因為它只對特定 TASK.md 格式成立
    - "Write in **English**, always."     -> 改為「Write in the language your caller
                                            specifies. Default to English if unspecified.」
  保留並改寫的核心規則（這些是通用且有價值的）：
    - 絕不寫入未被告知的值，不知道就寫 "?"
    - 時間戳一律來自以 caller timezone 執行的 date 指令（例如
      `TZ='<IANA timezone>' date '+%Y-%m-%d %H:%M:%S %Z'`）
    - 完成的項目是「移動」不是「刪除」
    - 先寫目的地、驗證、再刪來源
    - 不 Read archive，改用 anchored edit / heredoc / grep -n / sed -n
    - 收尾必須輸出 RECORDED / MOVED / VERIFY / UNFINISHED 四行區塊
    - 不執行 git add / commit / push；commit message 只以文字回傳
  目標長度：40–60 行
Files:
  agents/scribe.md
  templates/records/tasks.md.tmpl
  templates/records/bugs.md.tmpl
  templates/records/progress.md.tmpl
  templates/records/README.md
Verify:
  wc -l agents/scribe.md            # 應在 40–70 之間
  grep -c "Asia/Taipei\|Task 91\|405KB\|Edge Function\|cron.job" agents/scribe.md   # 0
Non-goals:
  - 不要把「先寫目的地再刪來源」這條刪掉。它是整份檔案裡最重要的規則
```

「先寫目的地」那段的改寫範本（原則化、去軼事化）：

```markdown
### Write the destination before you cut the source

A move is two edits, and you can be stopped between them: you have a hard turn ceiling
and a dispatch can be cut off mid-run, both without warning. The order decides what a
half-finished move leaves behind.

- **Destination first, source second.** Append or prepend the entry to the archive,
  confirm it landed with `grep -c`, and only then delete it from the hot file.
- Interrupted that way, the worst case is the entry existing **twice** — visible,
  harmless, fixable by anyone who greps. Interrupted the other way round, the entry
  exists **nowhere**, nothing errors, and the file is simply shorter.

Never do a move you cannot finish in this dispatch. If you are handed more than fits,
complete the moves you can do **whole**, and report what you did not start.
```

`templates/records/README.md` 要說明：這些模板由 `/route:init` 複製進目標專案的
`docs/agent/`，之後由專案自行維護；plugin 更新不會覆寫它們。

## Task 4.3 — 去專案化其餘 prompt 檔

```
Contract:
  agents/builder.md
    - description 必須同時接受 Lane 1 inline brief 與 Lane 2 spec file；不可寫成只接受
      spec path
    - 移除 "All code comments in **English**" -> 改為讀呼叫端指定的語言
    - 修正 "A PreToolUse guard blocks your writes to test files, specs, and docs/" 這句：
      在 Phase 1 之前它是假的。保留這句，但確認 Phase 1 完成後它才成立
    - "Lane 1 / Lane 2" 用語保留，但要在 SKILL.md 有定義（已有）
  agents/scout.md
    - "Output in **English**" -> 同上
    - Compress mode 加上「你不執行指令」的說明（Task 1.4 的連帶）
    - Map mode / Compress mode 的具體範例（TS / redis）保留 ——
      具體範例比抽象描述更能約束輸出格式，換成假想的技術棧只會變模糊
  agents/reviewer.md
    - "money, positions, fees, prices" 這類金融用語只出現在 SKILL.md Step 4，
      reviewer.md 本身的四項檢查清單是通用的，不用改
  skills/route/SKILL.md
    - Lane 2 的觸發條件清單移除 RLS / cron / Edge Function 等 stack 專屬用語，
      改為與 Step 4 相同的七條通用 trigger
    - Step 0.5 加註：CLAUDE_CODE_SUBAGENT_MODEL 環境變數優先於 per-invocation model，
      若使用者設了它，這一步不會生效
    - 全篇 dispatch 對象改寫為 scoped name（route:scout / route:builder / ...）
    - 最後一段「Verify the routing actually happened」改為指向 /route:audit 與 /route:delta
Files:
  agents/builder.md
  agents/scout.md
  skills/route/SKILL.md
Verify:
  grep -rn "English, always\|Asia/Taipei\|RLS\|Edge Function\|cron.job" agents/ skills/   # 應為空
Non-goals:
  - 不要改 builder 的既有 task/status/files/blockers 欄位與 reviewer 的 Severity 分級；
    允許補上 VERIFY / TESTS / LINT 的結果欄位
```

---

# Phase 5 — 打包與發佈

## Task 5.1 — 修正安裝說明與 metadata

```
Contract:
  1. README.md 的安裝指令改為：
       /plugin marketplace add CTJ425/Model-Routing
       /plugin install route@route
     （現況是 `/plugin marketplace add /root/dev/mode-routing` —— 本機絕對路徑，
       且 repo 名稱拼錯為 mode-routing）
  2. README 統一角色數量的講法（Boss + 4 個 subagent，不要一下 four-role 一下列五列）
  3. README 新增「Requirements」段：Python 3.8+ 且 python3 在 PATH 上
  4. README 新增「What this does NOT enforce」段，誠實說明 Bash 偵測是啟發式的
  5. .claude-plugin/plugin.json 補上 $schema、homepage、repository、license，version 升到 0.2.0
  6. .claude-plugin/marketplace.json 的 owner 與 repo 擁有者一致
  7. 新增 LICENSE（MIT）
Files:
  README.md
  .claude-plugin/plugin.json
  .claude-plugin/marketplace.json
  LICENSE
Verify:
  claude plugin validate . --strict
Non-goals:
  - 不要寫 CHANGELOG（1 個 commit 的專案還不需要）
```

## Task 5.2 — CI

```
Contract:
  .github/workflows/validate.yml，在 push 與 PR 時執行：
    - 至少在 Python 3.8 與 3.9 上執行（requirements 宣稱 Python 3.8+）
    - python3 -m py_compile 所有 hooks/*.py scripts/*.py
    - python3 -m pytest tests/ -q
    - 所有 .json 檔可被 json.load
    - grep 檢查：agents/ 與 skills/ 下不得出現去專案化清單裡的字串
      (Asia/Taipei, Task 91, 405KB, Edge Function, cron.job, "English, always")
Files:
  .github/workflows/validate.yml
Verify:
  第一次 push 後 workflow 綠燈
Non-goals:
  - 不要加 lint（ruff/black），這個專案還不需要
```

---

# 最終驗收

全部 Phase 完成後，在一個**全新的、非原作者的專案**（最好不是 TypeScript、不是
Supabase stack，例如一個 Python CLI 專案）跑完整流程：

```
Verify (end-to-end):
  1. /plugin marketplace add CTJ425/Model-Routing && /plugin install route@route
  2. cd <一個乾淨的 Python 專案> && claude
  3. /route:init                  -> 正確偵測或詢問 prod 路徑；詢問 bookkeeping 與語言
  4. SessionStart brief 出現，且不含 "? task(s)"
  5. 給一個需要改 src/ 的小需求，觀察：
     a. 主 session 直接改 src/*.py -> 出現 ask
     b. dispatch route:builder     -> 成功
     c. builder 嘗試改 test_*.py   -> 被 deny（P0-1 回歸驗證）
     d. builder 回來後             -> 出現 reviewer nudge（Task 3.3）
     e. dispatch route:reviewer 只帶 inline brief（無 spec 檔）-> 成功接受（Task 3.2）
  6. /route:audit                 -> 顯示至少兩個 model、非零 subagent 花費
  7. /route:delta                 -> 顯示每次 dispatch 的 net token
```

第 5c 步是整個重構最重要的單一驗收點：修復前它是靜默放行，修復後必須 deny。
