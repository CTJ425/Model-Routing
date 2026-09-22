# Progress

Newest entry at the top, immediately after this header block. Older entries roll into
`PROGRESS_ARCHIVE.md`, prepended so newest-first order holds there too.

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

---

## 📅 Log: 2026-09-22 18:51:06 CST (0.9.4 — a role turned off hands its writes to the main session)

- **Changed**: route/hooks/routing_guard.py, route/hooks/routing_observe.py,
  route/skills/route/SKILL.md, route/schema/route.config.schema.json,
  route/commands/config.md, README.md, tests/test_guard.py, tests/test_observe.py,
  docs/CHANGELOG.md; new spec docs/agent/specs/route-role-off-main-writes.md
- **Why**: a check of "builder off, the main session writes the code" found the guard
  still asked on every main-session production-code write, through `Write`/`Edit` and
  Bash, and named `builder` as the cheaper path, which the guard denies. Reproduced
  against the real hook scripts on a temp project. `roles.scribe.enabled=false` had the
  same defect for tracking records. Fixed by user decision.
- **What changed**: a main-session write whose owning role is off passes with no ask,
  under every `guard.mainSeverity` (`deny` included: with the role off, nobody else can
  write it). Bash skips such a target and keeps scanning, so a later target whose role
  is on still asks. The session brief's guard line drops the absorbed edit class.
  SKILL.md Steps 0/3/4/5/6, the schema, `/route:config` and the README say the same;
  Step 4 has the main session produce builder's report lines for reviewer.
- **Not changed**: the ask text, subagent write rules, the record timestamp check, and
  the review nudge (it still fires only when a `builder` dispatch returns).
- **Review**: Lane 2, reviewer PASS with no findings.
- **Housekeeping**: `roll_records.py --keep 2` moved the 2026-09-17 10:12:22 entry into
  `PROGRESS_ARCHIVE.md`.
- **Tests**: 295 passed, 0 failed (was 278). Against the previous code 12 of the 17 new
  cases fail (8 guard, 4 observe); the other 5 pin behaviour it already had.
