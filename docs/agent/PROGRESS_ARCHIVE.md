# Progress archive

Older progress entries, prepended from `PROGRESS.md` so newest-first order holds there too.

---

## 📅 Log: 2026-09-17 10:57:36 CST (0.9.4 — role switches: namespace scope, doctor type check)

- **Changed**: route/hooks/_config.py, route/hooks/routing_guard.py,
  route/hooks/routing_observe.py, route/scripts/routing_doctor.py, tests/test_guard.py,
  tests/test_observe.py, tests/test_doctor.py, docs/CHANGELOG.md
- **Why**: a check of the role on/off switches, run against the real hook scripts,
  found every documented path working and two gaps. Fixed by user decision.
  - `roles.<role>.enabled=false` also denied another plugin's agent of the same name
    (`other:builder`): `role_enabled` stripped any namespace, contrary to its own
    docstring.
  - A switch the hooks cannot read failed open with no sign. `"enabled": "false"`,
    `"roles": {"builder": false}` and a misspelled key or role all left the role on, and
    `/route:doctor` reported "all four roles may be dispatched".
- **What changed**: `_config.route_role` names a route role only for a bare name or the
  `route` namespace. The guard's dispatch check and the review nudge use it. The caller
  side (`agent_type`, which picks the write rules) still strips any namespace; out of
  scope here. `role_enabled` also returns true for a `roles` value that is not an object:
  the hooks crashed there, which cost the session its brief. The doctor's `roles` check
  reads the file as written and FAILs on each unreadable switch, naming the state the
  hooks actually use.
- **Not changed**: what a well-formed `false` does; the hooks still fail open on a
  malformed one, and the doctor is where that shows.
- **Housekeeping**: `roll_records.py --keep 2` moved the 0.9.3 entry into
  `PROGRESS_ARCHIVE.md`.
- **Tests**: 278 passed, 0 failed (was 254), also on Python 3.8. Against the previous
  code 20 of the new cases fail (8 doctor, 9 guard, 3 observe); the other 4 pin behaviour
  it already had.

---

## 📅 Log: 2026-09-17 10:12:22 CST (0.9.4 — catch up with Claude Code 2.1.198–2.1.271)

- **Changed**: route/skills/route/SKILL.md, route/agents/scout.md,
  route/commands/config.md, route/commands/init.md,
  route/schema/route.config.schema.json, route/hooks/routing_guard.py,
  route/hooks/routing_observe.py, route/scripts/routing_doctor.py,
  route/scripts/dispatch_delta.py, tests/test_doctor.py, tests/test_guard.py,
  tests/test_observe.py, tests/test_dispatch_delta.py (new), README.md,
  docs/MODEL_ROUTING_SPEC_ZH.md, docs/model-routing-guide.html,
  route/.claude-plugin/plugin.json, docs/CHANGELOG.md
- **Why**: Claude Code 2.1.251 demoted `CLAUDE_CODE_SUBAGENT_MODEL` below the
  per-invocation `model` parameter and the agent frontmatter, and 2.1.257 added
  `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1` as the way to force one model. The plugin still
  documented the variable as the top override, so `/route:config` and `/route:doctor`
  reported per-role tiers as not in force when they were (checked on 2.1.274).
- **What changed**: Step 0.5, `/route:config`, `/route:init`, the schema and the README
  describe the new order and `_FORCE`. The doctor reads `claude --version` and warns only
  when `_FORCE` is on, or when the plain variable is set on a version older than 2.1.251
  or an unknown version. `inherit` counts as unset. `models.<role>` is documented as an
  alias, because the Agent tool's `model` parameter takes aliases only. The README role
  table now shows the 0.9.3 turn budgets (80 / 240 / 80 / 90).
- **Also from the same version audit** (hooks and sub-agents reference, checked against
  2.1.274):
  - Background dispatch is the default since 2.1.198, and its tool response is
    `status: "async_launched"` with no launch wording. `is_async_launch` matched only
    wording, so the review nudge told the session to dispatch `reviewer` while `builder`
    was still running. The structured status now decides.
  - An `ask`'s `permissionDecisionReason` is shown to the user, not to Claude. The guard
    now repeats it as `additionalContext`; a `deny` is unchanged, since Claude already
    sees that reason.
  - The discovery ask now also covers `Plan`, `claude` and an untyped Agent call (which
    runs `general-purpose`), with exact matching. `fork` was in the first cut and is out
    by user decision: fork mode spawns forks routinely, and an ask on each one stalled
    automated workflows.
  - `dispatch_delta.py` took a background launch notice or a hand-back note as the report.
    It now reads the report size from the subagent transcript, and drops background
    launches from `--validate`. No local transcript had a background dispatch, so the
    tests use the documented shapes: `toolUseResult.status`, one content block per row
    (confirmed on this session's transcript), and `SubagentHandback`'s `message` input.
  - `maxTurns` output has been marked partial since 2.1.246; Step 1 and `scout.md` said
    a capped run returned nothing.
- **Not changed**: role scopes, write rules, Bash rules, model tiers, turn budgets.
- **Housekeeping**: `roll_records.py --keep 2` moved the 0.9.2 and 0.9.0 entries into
  `PROGRESS_ARCHIVE.md`; the hot file had been holding three.
- **Tests**: 254 passed, 0 failed (was 232). Each new case was also run against the 0.9.3
  file it covers: 4 doctor, 2 observe, 5 guard and 3 dispatch_delta cases fail there; the
  rest pin behaviour 0.9.3 already had.

---

## 📅 Log: 2026-09-07 16:58:14 CST (0.9.3 — turn budgets raised out of the working range)

- **Changed**: route/agents/scout.md, route/agents/reviewer.md, route/agents/scribe.md,
  route/agents/builder.md, route/skills/route/SKILL.md, README.md,
  route/.claude-plugin/plugin.json, .claude/version.config.json, docs/CHANGELOG.md
- **Why**: user decision. 0.9.2 raised every cap from measured data and stated the
  principle behind it — a cap is a stop, not a budget; unused headroom costs nothing,
  hitting one costs a re-dispatch that replays the whole brief. This release applies that
  principle further, so a capped run is an anomaly to investigate rather than a routine
  cost the caller absorbs silently.
- **What changed (budgets)**: scout 40 → 80, reviewer 40 → 80, scribe 45 → 90,
  builder 80 → 240. The hardcoded scout budget in scout.md, SKILL.md Step 1 and the
  README role table follow the new number.
- **Not changed**: guard behaviour, role scopes, model tiers, the degradation protocol
  (`NOT ANSWERED:`, `VERIFY: BLOCKED`), and scout's 40-line output ceiling — an output
  limit, not a turn budget.
- **Housekeeping**: `.claude/version.config.json` and `docs/CHANGELOG.md` were collateral
  losses of the b468865 architect rollback, which reverted the whole 0.10.0 commit pair.
  Both are restored; the CHANGELOG drops the reverted 0.10.0 section and gains the 0.9.2
  entry it never received. The `v0.10.0` tag pointed at that reverted work and had no
  Release; it is deleted from the local repo, from `origin`, and from its stale plugin
  install cache under `~/.claude/plugins/cache/`.
- **Tests**: 232 passed, 0 failed.

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

---

## 📅 Log: 2026-08-27 12:30:18 CST (0.8.1 — builder and reviewer default to high effort)

- **Changed**: route/agents/builder.md, route/agents/reviewer.md, route/.claude-plugin/plugin.json
- **Why**: both roles shipped at `effort: medium`. builder implements against a brief and
  reviewer is the only gate on risk work, so both are places where a shallower pass costs
  more than it saves — a missed defect is paid for by the main session at the top model
  tier. scout and scribe stay `low`: they map and transcribe, and neither benefits.
- **Verify**: PASS — `python3 -m pytest tests/ -q` — 177 passed, 0 failed
- **Verify**: PASS — `claude plugin validate ./route` — Validation passed
- **Tests**: 177 passed, 0 failed (no test changes; `effort` is frontmatter the suite does
  not assert on, and it is not settable per project — the schema has no `effort` key, so the
  agent frontmatter is the only place it lives)
- **Lint**: NOT RUN — project defines no lint command
- **Review**: not dispatched — two frontmatter values, validated by the plugin CLI
- **Accepted risk**: builder and reviewer dispatches get more expensive per run. Measured
  baseline to compare against: over one stock-pnl-web session at medium, 2 builder runs cost
  $1.29 and 2 reviewer runs $1.70, against $17.23 for the main session — so the headroom is
  real, but re-measure with /route:audit before assuming it stayed that way.

---

## 📅 Log: 2026-08-27 12:05:00 CST (0.8.0 — out-of-scope Bash writes deny instead of ask)

- **Changed**: route/hooks/routing_guard.py, route/.claude-plugin/plugin.json, tests/test_guard.py, README.md, docs/MODEL_ROUTING_SPEC_ZH.md
- **Why**: `handle_bash`'s final branch returned `ask` for `builder` and `scribe`. That was
  assumed to fail closed with no human present. It does not — under an auto-approving
  permission mode an `ask` a subagent cannot surface resolves to ALLOW, so the branch was
  advisory only and the role boundary was bypassable by switching tool. Observed in a
  2026-08-27 stock-pnl-web session: scribe hit the Edit deny on `sources/src/version.ts`,
  reasoned in its transcript that "the guard only affects the Write/Edit tools", and
  completed the identical write with `sed -i`. `BASH_REASON` already told it not to
  ("Report the blocker instead"); only the decision value was wrong.
- **Verify**: PASS — `python3 -m pytest tests/ -q` — 177 passed, 0 failed
- **Tests**: 177 passed, 0 failed (30 expectations flipped ask→deny across the builder and
  scribe Bash paths; every `None` allowance left intact, including scribe's in-scope
  `cat >> <literal-path>` append, which is what keeps the documented happy path human-free)
- **Lint**: NOT RUN — project defines no lint command
- **Review**: not dispatched — single-value change with the test suite as the contract
- **Accepted risk**: `builder` and `scribe` can no longer perform ANY detected Bash write
  outside their scope, with no config escape. `guard.bashWriteDetection: false` still turns
  detection off wholesale. Verified builder's normal verify commands (`npm test`,
  `npm test > /dev/null`, `npx tsc --noEmit`) do not match `BASH_WRITE_RE`.

---

## 📅 Log: 2026-08-24 11:26:30 CST (fix 5 autonomy blockers from field report)

- **Changed**: route/scripts/roll_records.py, route/agents/scribe.md, route/agents/builder.md, route/agents/scout.md, route/commands/init.md, route/hooks/routing_observe.py, tests/test_observe.py, tests/test_roll_records.py, docs/agent/BUG_FIX.md, docs/agent/FIXED_BUG.md
- **Verify**: PASS — `python3 -m pytest tests/ -v` — 149 passed, 0 failed
- **Tests**: 149 passed, 0 failed (6 new tests added: 5 for roll_records, 1 for async launch observe)
- **Lint**: NOT RUN — project defines no lint command
- **Review**: PASS — verified insert-before-delete ordering, verbatim VERIFY mandate, and non-blocking async launch observe behavior
- **Accepted risk**: none outstanding

---

## 📅 Log: 2026-08-24 09:14:26 CST (route the loop's own overhead down)

- **Changed**: README.md, route/agents/builder.md, route/agents/reviewer.md, route/skills/route/SKILL.md
- **Verify**: PASS — `python3 -m pytest tests/ -q` — 143 passed, 0 failed
- **Tests**: 143 passed, 0 failed
- **Lint**: NOT RUN — project defines no lint command
- **Review**: FAIL on first round with one BLOCKER — new diff-first rule contradicted existing rule forbidding PASS without reading every changed file in full; defect was in brief, not implementation. Merged into one coverage rule and re-verified. Builder.md change adjudicated by main session reading directly rather than second reviewer dispatch.
- **Accepted risk**: none outstanding

---

## 📅 Log: 2026-08-23 19:18:07 CST (add /route:doctor self-check)

- **Changed**: route/scripts/routing_doctor.py, route/commands/doctor.md, tests/test_doctor.py, README.md
- **Verify**: PASS — `python3 -m pytest tests/ -q` — 143 passed, 0 failed (was 132; 11 new tests, all red before the change)
- **Tests**: 143 passed, 0 failed (11 new tests added)
- **Lint**: NOT RUN — project defines no lint command
- **Review**: PASS with three RISK findings, all three fixed in a follow-up round and re-verified: hooks subprocess had no timeout; used `sys.executable` instead of `python3` from hooks.json causing false `[PASS]` inside venv; config with non-object `paths` crashed before summary line printed
- **Accepted risk**: none outstanding

---

## 📅 Log: 2026-08-23 18:52:48 CST (harden subagent reliability)

- **Changed**: .claude/route.config.json, README.md, route/.claude-plugin/plugin.json, route/agents/builder.md, route/agents/reviewer.md, route/agents/scout.md, route/commands/init.md, route/hooks/routing_guard.py, route/hooks/routing_observe.py, route/scripts/dispatch_delta.py, route/skills/route/SKILL.md, route/templates/records/bugs.md.tmpl, route/templates/records/tasks.md.tmpl, tests/helpers.py, tests/test_guard.py, tests/test_observe.py, docs/agent/TASK.md, docs/agent/BUG_FIX.md
- **Verify**: PASS — `python3 -m pytest tests/ -q` — 132 passed, 0 failed
- **Tests**: 132 passed, 0 failed (11 new tests added, all were failing before this change)
- **Lint**: NOT RUN — project defines no lint command
- **Review**: FAIL (BLOCKER: escaped quote treated as span delimiter) → PASS after fix; prose PASS first round
- **Accepted risk**: write hidden entirely inside quoted string (e.g. `bash -c 'echo x > f'`) not detected; documented in README under "What this does NOT enforce"
