# Progress

Newest entry at the top, immediately after this header block. Older entries roll into
`PROGRESS_ARCHIVE.md`, prepended so newest-first order holds there too.

---

## 📅 Log: 2026-09-01 14:50:17 CST (0.10.0 — architect role: an opus tier above the builder)

- **Changed**: route/agents/architect.md, route/hooks/_config.py, route/hooks/routing_guard.py, route/hooks/routing_observe.py, route/scripts/routing_doctor.py, route/schema/route.config.schema.json, route/skills/route/SKILL.md, route/commands/config.md, route/commands/init.md, route/.claude-plugin/plugin.json, .claude-plugin/marketplace.json, README.md, tests/test_guard.py, tests/test_observe.py, tests/test_doctor.py
- **Why**: the loop assumed the main session runs on the expensive model. SKILL.md Step 2 keeps specs, failing tests, and adjudication in the main session because that is where the expensive model sits. An `opusplan` session breaks that the moment the loop starts — Opus in plan mode, Sonnet after — and a session started on a mid tier never had it. Lane classification, spec authoring, the seven risk triggers, and adjudication then all run at the builder's tier, with no model above the builder anywhere in the execution loop. Routing ROI also falls: the saving is context replay at the Boss's input rate, Sonnet input is 2.5x cheaper than Opus, and the Step 0.25 dispatch floor is unchanged.
- **What changed**: a fifth role, `architect`, on the `opus` tier (overridable via `models.architect`). It owns Lane 2 spec authoring plus the failing tests, root-cause analysis, review adjudication, and a `consult` mode: dispatched before any spec exists, it writes a `<task>-design.md` design note under `paths.specs` — options, a recommendation, open questions — that a human reads directly and answers through the caller with SendMessage, and only when the design is settled does it produce the spec. The guard scopes it to `spec` and `test` paths through Write/Edit and Bash alike; production code, records, and config are denied — the mirror of the rule the guard already applies to builder. `ROUTE_ROLES` widens to five, so `roles.architect.enabled`, the SessionStart roster, and `/route:doctor` pick it up with no further wiring.
- **What did not change**: scout/builder/reviewer/scribe guard behaviour, the main-session rules, and the config deep-merge — every architect rule is gated on the role name. Adjudication still runs in the main session; a Sonnet Boss cannot delegate the loop state a ruling needs, so Step 5 gains an escalation path that dispatches architect to rule on a reviewer FAIL the Boss cannot, and SKILL.md tells a downgraded Boss to set `review.policy=always`.
- **Deferred**: the pricing.json Sonnet 5 rate, a /route:doctor check on the session model, this repo's own review.policy, and a builder effort raise.
- **Verify**: PASS — `python3 -m pytest tests/ -q` — 231 passed, 0 failed (was 212)
- **Verify**: PASS — `python3 -m py_compile route/hooks/*.py route/scripts/*.py`
- **Tests**: 231 passed, 0 failed (was 212). New: architect write/Bash scope, dispatch enable/disable, doctor five-tier report, roster clause, consult-mode design note path.
- **Lint**: NOT RUN — project defines no lint command
- **Review**: `route:reviewer` (sonnet) — PASS, no findings. Verified guard completeness (all non-spec/test classes denied, including uncategorized `other`), no regression to the other four roles, config plumbing has no KeyError path, new tests exercise real boundaries.
- **Risks accepted**: none.

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