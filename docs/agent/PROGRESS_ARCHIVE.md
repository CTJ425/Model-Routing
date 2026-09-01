# Progress archive

Older progress entries, prepended from `PROGRESS.md` so newest-first order holds there too.

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
