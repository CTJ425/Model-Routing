# Progress archive

Older progress entries, prepended from `PROGRESS.md` so newest-first order holds there too.

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
