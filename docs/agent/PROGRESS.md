# Progress

Newest entry at the top, immediately after this header block. Older entries roll into
`PROGRESS_ARCHIVE.md`, prepended so newest-first order holds there too.

---

## 📅 Log: 2026-09-02 22:28:43 CST (0.9.2 — turn budgets sized from measurement, and the guard stops denying the verify command)

- **Changed**: route/agents/scout.md, route/agents/builder.md, route/agents/scribe.md,
  route/skills/route/SKILL.md, route/hooks/routing_guard.py, route/hooks/_config.py,
  README.md, route/.claude-plugin/plugin.json, tests/test_guard.py
- **Why**: 463 subagent runs across five projects were measured from
  `.claude/routing/dispatch.jsonl` joined to the agent transcripts, counting one turn per
  distinct `requestId`. Every role's maximum equals its cap exactly and none exceeds it,
  so the distributions are censored, not merely tight: scribe hit 30 on 14 of 124 runs
  (11.3%, p90 and p95 both pinned at 30), builder hit 60 on 6 of 150, scout hit 30 on 4 of
  103. reviewer never reached 40 (max 38). Only about a third of capped runs were resumed;
  the rest returned a partial result the caller absorbed silently. A cap is a stop, not a
  budget — unused headroom costs nothing, while hitting one costs a re-dispatch that
  replays the whole brief.
- **What changed (budgets)**: scout 30 → 40, scribe 30 → 45, builder 60 → 80.
  reviewer stays at 40. The hardcoded budget in scout.md, SKILL.md Step 1 and the README
  role table are updated with them.
- **What changed (work shape)**: the numbers were the symptom. Capped scribe runs spent
  15.4 Bash + 8.7 Read + 7.5 Edit calls each on `grep -n` / `sed -n` / `wc -l` anchoring,
  so `roll_records.py` is now the required path for a move rather than an option, scribe is
  forbidden to discover a destination it was not given, and SKILL.md Step 6 must name every
  path, anchor and `--keep` value. Capped builder runs averaged 4.5 invocations of the
  Verify command, so builder now runs it at most three times and reports `VERIFY: BLOCKED`.
  Capped scout runs averaged 16 reads and 14 greps, so Step 1 must bound the search space.
- **What changed (guard)**: `_write_targets` resolved a single line only. `_SHELL_CHAIN_RE`
  matched the `&` inside `2>&1`, so `npx vitest run > <scratchpad>/out.log 2>&1` — the
  shape of every verify command builder runs — was denied as an unresolvable write. 17 of
  the 24 recoverable builder Bash denials (71%) were writes to `/tmp` or the session
  scratchpad, which builder's scope allows by the same rule as Write/Edit. Resolution is now
  segment by segment: heredoc bodies are dropped wherever they open, file-descriptor
  duplication is not read as a chain, and `;`/`&&`/`||`/newline split the command. A pipe, a
  background `&`, a backtick, a command substitution, a non-literal target, or a relative
  path past a `cd` still return unknown, which still denies.
- **Also (guard)**: a worktree session keeps `CLAUDE_PROJECT_DIR` on the main repo, so every
  path under `.claude/worktrees/<name>/` classified as `config` — scribe could not write a
  single tracking record and builder could not touch a source file, for the whole session
  (6 denials observed in one session). `strip_worktree` normalises the prefix away before
  classification, in `classify`, the scribe archive read, the scribe docs check and the
  scribe append grammar. The real `.claude/` tree is unaffected.
- **Verify**: PASS — `python3 -m pytest -q` — 232 passed, 0 failed (was 212)
- **Verify**: PASS — `claude plugin validate ./route` — Validation passed
- **Tests**: 232 passed (+20). Two existing cases moved from
  `test_builder_bash_unresolvable_target_is_denied` to
  `test_builder_bash_write_outside_prod_is_denied`: `echo a > src/a.ts; rm -rf tests` and
  `echo hi\nrm -rf tests` are still denied, now naming the out-of-scope target instead of
  reporting the shape as unresolvable.
- **Routing**: none. Handled entirely in the main session at the user's instruction.

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
