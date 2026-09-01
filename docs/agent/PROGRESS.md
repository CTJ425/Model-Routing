# Progress

Newest entry at the top, immediately after this header block. Older entries roll into
`PROGRESS_ARCHIVE.md`, prepended so newest-first order holds there too.

---

## 📅 Log: 2026-08-29 10:00:37 CST (0.9.0 — Bash writes get the same scope as file writes)

- **Changed**: route/hooks/routing_guard.py, route/hooks/routing_observe.py,
  route/scripts/routing_doctor.py, route/agents/builder.md, route/skills/route/SKILL.md,
  README.md, route/.claude-plugin/plugin.json, .claude/route.config.json,
  tests/test_guard.py, tests/test_observe.py
- **Why**: an audit of the subagent boundaries found three ways the loop stalled a
  subagent and sent the work back to the caller, plus two silent failures.
  (1) `handle_bash` denied every write-shaped command a role ran, without resolving the
  target: `mkdir -p src/x`, `mv`, `rm` and `cp` inside `paths.prod` were all refused, with
  a reason that said "outside the allowed production paths" — false, and none of them has
  a file-tool equivalent. builder.md tells builder to report a blocked write rather than
  route around it, so builder stopped and the caller redid the work at its own rate.
  (2) `handle_bash` exited immediately for the main session, so `guard.mainSeverity` was
  one `sed -i` away from silence; under a harness configured to prefer Bash for file
  edits, the Step 3 and Step 6 prompts never fired at all.
  (3) `log_dispatch` wrote the harness's empty `agent_type` verbatim, and
  `normalize_role("")` is `"main"` — so a subagent's turns were credited to the main
  thread in `/route:audit`, the one number that shows whether routing happened. 51 of 90
  rows in this repo's log are affected, and a row written by the 2026-08-29 session shows
  the harness still emits them.
- **What changed**: the guard now resolves a command's literal write targets and applies
  the same scope Write/Edit gets. builder may write `paths.prod` or anything outside the
  repository, through either path; a target carrying a variable, a glob or a brace is not
  literal, so the whole command reads as unresolved. Unresolved denies for a role with a
  write scope and allows for the main session — a guard that blocks the Boss on a parse
  failure is worse than one that misses a case. The main session's Bash writes to `prod`
  and `record` paths now take `guard.mainSeverity`. `log_dispatch` records a missing role
  as `unknown`, and `/route:doctor` reports the count as unattributed rather than blank.
- **Also**: this repo's own `paths.prod` was `route/` alone, so builder could not touch
  `README.md`, `pytest.ini` or `.github/` — every release-shaped task split across two
  roles by construction. `paths.docs` was `docs/agent`, so scribe could not write
  `docs/field-reports/` or a handover. Both are now widened in `.claude/route.config.json`;
  `docs/agent/specs/` stays outside scribe's reach as a spec.
- **Verify**: PASS — `python3 -m pytest tests/ -q` — 212 passed, 0 failed
- **Verify**: PASS — `claude plugin validate ./route` — Validation passed
- **Tests**: 212 passed, 0 failed (was 177). Three existing cases in
  `test_real_writes_survive_quote_stripping` and `test_escaped_quote_does_not_hide_a_redirect`
  targeted `src/a.ts`, which is inside builder's scope now that Bash follows the Write/Edit
  rule; they were retargeted to a path builder may not write either way, so each still
  asserts detection rather than scope.
- **Lint**: NOT RUN — project defines no lint command
- **Review**: not dispatched — the user directed every step of this round to the main
  session, builder and reviewer included
- **Accepted risk**: `effort` is still unmeasured. The dispatch log records `medium` for
  builder and reviewer on every run, all of them from before 0.8.1 set those roles to
  `high`; scout and scribe report no effort at all, consistent with haiku not taking a
  level. No dispatch since 0.8.1 has been logged, so the effect of that release on cost is
  unknown. Deferred pending a measured run rather than guessed at here.
- **Accepted risk**: scout's 30-turn ceiling is still inferred, not observed. The 0.8.2
  measurement counted 36 tool calls against a documented ceiling of 30, which reconciles
  only if a turn can carry several tool calls. Unchanged by this release; see A2 in
  docs/handover-2026-08-27-scout-budget.md.

---

## 📅 Log: 2026-08-27 14:29:18 CST (0.8.2 — size the scout dispatch to its 30-turn budget)

- **Changed**: route/agents/scout.md, route/skills/route/SKILL.md, README.md, route/.claude-plugin/plugin.json
- **Why**: `maxTurns: 30` was shipped in scout's frontmatter and documented nowhere, and the
  config schema has no such key, so no consumer could see the ceiling or raise it. Nothing
  told the caller how to size a dispatch against it, and scout itself had no instruction for
  what to do as the budget ran out. Measured in a 2026-08-27 stock-pnl-web session: two
  dispatches asking two focused questions each finished in 13 and 12 tool calls; one asking
  four questions against a 4,095-line / 172 KB file was cut off at 36 and returned nothing
  usable, so the caller paid for the reading and then did the trace itself. Scout has no
  Bash, so every locate-then-read is two turns — the budget goes faster than it looks.
- **What it now says**: SKILL.md Step 1 gets the caller-side rule (one question per dispatch,
  split multi-part traces into parallel scouts, pass line ranges when known, resume a cut-off
  scout with `SendMessage` rather than re-dispatching cold). scout.md gets the agent-side
  rule: answer several questions in order and, when the budget looks tight, stop and report
  with a `NOT ANSWERED:` line instead of spending the last turns still searching. README
  Step 1 states the ceiling so it is visible without opening the frontmatter.
- **Verify**: PASS — `python3 -m pytest tests/ -q` — 177 passed, 0 failed
- **Verify**: PASS — `claude plugin validate ./route` — Validation passed
- **Tests**: 177 passed, 0 failed (no test changes; the suite asserts on hook decisions, and
  this release changes only agent and skill prose plus one version string)
- **Lint**: NOT RUN — project defines no lint command
- **Review**: not dispatched — prose and one version string, both gates green
- **Accepted risk**: the ceiling itself is unchanged. A trace genuinely needing more than 30
  turns still has no per-project escape; the remedy on offer is splitting the dispatch, not
  raising the cap. If splitting proves insufficient in practice, the next step is exposing
  `maxTurns` in route.config.schema.json, which this release does not do.
