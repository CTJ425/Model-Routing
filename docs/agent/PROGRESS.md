# Progress

Newest entry at the top, immediately after this header block. Older entries roll into
`PROGRESS_ARCHIVE.md`, prepended so newest-first order holds there too.

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
