# Progress

Newest entry at the top, immediately after this header block. Older entries roll into
`PROGRESS_ARCHIVE.md`, prepended so newest-first order holds there too.

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
