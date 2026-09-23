# Progress

Newest entry at the top, immediately after this header block. Older entries roll into
`PROGRESS_ARCHIVE.md`, prepended so newest-first order holds there too.

---

## 📅 Log: 2026-09-23 17:01:05 CST (0.9.4 — builder off by default, model tiers enforced, review gate at Stop)

- **Changed**: route/hooks/_config.py, route/hooks/routing_guard.py, route/hooks/routing_observe.py, route/hooks/hooks.json, route/scripts/routing_doctor.py, route/schema/route.config.schema.json, route/skills/route/SKILL.md, route/commands/config.md, README.md, docs/CHANGELOG.md, tests/conftest.py, tests/test_guard.py, tests/test_observe.py, tests/test_doctor.py, .claude/route.config.json
- **Why**: replays under an Opus 5.5 main session (docs/field-reports/2026-09-23-*, stock-pnl-web replay $22.05) found a builder cost 40–50% more with no measured gain, `models.<role>` ignored in 1 of 4 sessions, review skipped on a silent-calculation task in 2 of 3, and a reviewer RISK that became production defect BUG-036 recorded and shipped 3 times.
- **Result**: `roles.builder.enabled` defaults to false (this project too). The guard denies a route-role dispatch that would run on a tier other than `models.<role>`. A Stop hook blocks the first Stop after unreviewed production writes. SKILL.md widens Lane 0 to three known files with tests written and requires a persistent-state / silent-calculation / authorization / boundary RISK to be fixed or named with a reason.
- **Verify**: PASS — `uvx --python python3 pytest -q` — 335 passed, 0 failed (was 314).
- **Review**: Lane 2, builder off (main session implemented). Reviewer FAIL: worktree paths did not arm the gate, stale state carried across Stops; fixed. Re-review PASS with two RISKs: CRLF/BOM agent files — fixed; writes made in the continuation after a block are not gated again — accepted, so the gate can never loop.
- **Commits**: 0cb442a

---

## 📅 Log: 2026-09-23 10:43:36 CST (0.9.4 — Opus 5.5 verification; T2–T4 task identity and --by-task)

- **Changed**: route/skills/route/SKILL.md, route/scripts/routing_audit.py, route/commands/audit.md, tests/test_audit.py, docs/20260923.md, docs/20260923-verification.md
- **Why**: verify builder and reviewer on Opus 5.5 / medium (docs/20260923-verification.md), then make cost per task measurable (spec T2–T4).
- **Result**: V1–V6 PASS: builder and reviewer transcripts show `claude-opus-5-5` at `effort=medium`. T4: SKILL.md Steps 3–4 require a leading `Task: <id>` line and the same id at the start of the Agent description. T2: `task_identity()` reads the id and counts resumes as user entries with `origin.kind == "coordinator"` (confirmed on a real resume; the spec's earlier rule over-counted harness nudges). T3: `routing_audit.py --by-task` groups subagent cost per task; default output byte-identical.
- **Verify**: PASS — `uvx --python python3 pytest -q` — 309 passed, 0 failed (was 301). pytest is no longer installed for the system python3 (3.14.7); CI still installs it.
- **Review**: T4 PASS (3 RISK), T2 PASS (3 RISK), T3 PASS (4 RISK). Open risks in BUG_FIX.md.
- **Commits**: 79e5d79, e8b3d05, 71045cb, 9d20ad8

---

## 📅 Log: 2026-09-22 20:16:37 CST (0.9.4 — Claude Code 2.1.278 check: delta return cost, SKILL `$0`)

- **Changed**: route/scripts/dispatch_delta.py, route/skills/route/SKILL.md,
  tests/test_dispatch_delta.py, docs/CHANGELOG.md
- **Why**: the user asked whether the previous session's subagent ran and whether the
  plugin works on Claude Code 2.1.278. The `route:scribe` dispatch of session 35476d16
  ran on haiku in the background, made 7 tool calls with no error, and handed back its
  report. No entry in the 2.1.275-2.1.278 changelog breaks a hook, the guard, the review
  nudge or the delta script; 295 tests passed and `/route:doctor` failed nothing. Two
  defects surfaced during the check.
- **What changed**: `/route:delta` adds to a dispatch's return every later main row that
  delivers for it (`origin.kind` `peer` from its agent id, or `task-notification` naming
  its tool_use_id). With no such row it keeps `max(tool_result, subagent report)`.
  Measured on 35476d16: 3,492 chars in main against 1,060 counted; net +69 -> -539
  tokens. `SKILL.md` Step 0.25 cost figures no longer start with `$`: `/route:route
  <args>` had put the arguments in place of `$0`.
- **Not changed**: the benefit side, `measured`, `--validate` and `scan_subagent`. The
  replay count of a late row still starts at the dispatch turn, not its delivery turn.
- **Note**: the user saw no subagent in `claude agents`. Not a 2.1.278 bug: every
  dispatch on 2.1.274-2.1.278 is `requestShape: background`, and the agent panel hides a
  completed subagent at once (2.1.232). A 142 s scout was visible while it ran.
- **Review**: (a) Lane 0. (b) Lane 1, implemented in the main session because the user
  had asked for no dispatch at that point; reviewer ran afterwards. Reviewer PASS with
  one RISK, accepted and not filed in BUG_FIX.md (every heading there counts as an open
  bug): a `task-notification` row is matched only when its content is a string, the only
  form seen on 2.1.278. If a later version sends a block list, that row stops being
  counted and the undercount returns silently.
- **Tests**: 296 passed, 0 failed (was 295). The new test failed before the change.

---

## 📅 Log: 2026-09-22 19:26:30 CST (0.9.4 — builder runs at effort xhigh)

- **Changed**: route/agents/builder.md, README.md, docs/CHANGELOG.md
- **Why**: the user asked whether `/route:config` can set a role's effort. It cannot: the
  Agent tool takes a per-call `model` override but has no `effort` parameter, so the agent
  frontmatter is the only place a role's effort is set, and it is plugin-wide. By user
  decision the plugin default changes instead.
- **What changed**: `builder` frontmatter `effort: high` -> `effort: xhigh`. The README
  role table and Step 3 line say xhigh. CHANGELOG 0.9.4 gains a `### Changed` entry.
- **Not changed**: `reviewer` stays at `high`. `scout` and `scribe` keep `low`, which
  Claude Code drops on Haiku 4.5 (the model has no effort support; SubagentStop reports
  no effort for `route:scribe`). No `effort` key in the config schema or `/route:config`.
- **Review**: Lane 0, reviewer not dispatched. `no_red_green` checked: a real
  `route:builder` dispatch of the repo copy (`claude -p --plugin-dir route`, installed
  plugin disabled) reported `CLAUDE_EFFORT=xhigh` and SubagentStop `effort: xhigh` on
  claude-sonnet-5; the installed 0.9.4 copy's builder dispatch in this project's
  `.claude/routing/dispatch.jsonl` reports `high`. No other trigger applies.
- **Note**: `claude -p --agent route:builder` reported `CLAUDE_EFFORT=high` before and
  after the change. A `--agent` main thread does not show the frontmatter effort, so it
  cannot verify this setting; use a real subagent dispatch.
- **Tests**: 295 passed, 0 failed (unchanged).
