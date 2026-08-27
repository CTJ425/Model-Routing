# Progress archive

Older progress entries, prepended from `PROGRESS.md` so newest-first order holds there too.

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
