# Changelog

All notable changes to the `route` plugin. This file is the source of truth from 0.9.1
onward; releases 0.9.0 and earlier live in the git tags and their GitHub Releases, and
the fuller narrative for every version is in `docs/agent/PROGRESS.md` and its archive.

## [0.9.4] - 2026-09-17

### Changed

- `builder` and `reviewer` now default to `model: opus`, `effort: medium` (were
  `sonnet` at `high`). On Claude Code 2.1.280 the `opus` alias resolves to
  `claude-opus-5-5`, whose cache reads cost the same per token as Sonnet 5's; cache reads
  are about two thirds of a builder run's cost, so the stronger model costs less extra
  than its list price suggests. `/route:init` writes `opus` for both roles. Existing
  projects keep their pinned `models.<role>`, and a project that pins `sonnet` now runs
  Sonnet at `medium`: the agent frontmatter is the only place a role's effort is set,
  because the Agent tool has no `effort` parameter. `/route:doctor` warns about this
  case with a new `effort` check. `scout` and `scribe` keep `low`, which Claude Code drops
  on Haiku 4.5 because that model has no effort support.
- `pricing.json` prices `claude-opus-5-5` at $4/$20 with 0.05x cache reads, and
  `claude-sonnet-5` at $2/$10 (its introductory price became the standard price). An
  entry can now carry its own `cacheRead` multiplier. Before this, the audit priced Opus
  5.5 cache reads at 2.5x and Sonnet 5 at 1.5x their list price. `/route:audit` names the
  pricing key behind each model's cost, so a model priced by a family fallback is
  visible.

### Fixed

- The subagent model precedence now matches Claude Code 2.1.251+: the per-invocation
  `model` parameter outranks the agent frontmatter, which outranks
  `CLAUDE_CODE_SUBAGENT_MODEL`. Only `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1` (2.1.257+) puts
  one model above every tier. `SKILL.md` Step 0.5, `/route:config`, `/route:init`, the
  config schema and the README said the plain variable outranked everything.
- `/route:doctor` no longer warns that the tiers are not in force when only
  `CLAUDE_CODE_SUBAGENT_MODEL` is set on 2.1.251+. It reads `claude --version`, warns on
  `_FORCE`, keeps the warning for older or unknown versions, and treats `inherit` as unset.
- `models.<role>` is documented as a model alias (`haiku`, `sonnet`, `opus`): the Agent
  tool's `model` parameter does not take a full model id.
- The README role table shows the 0.9.3 turn budgets (80 / 240 / 80 / 90). 0.9.3 updated
  only the scout budget in the README body.
- The review nudge no longer tells the main session a background `builder` has returned.
  Since Claude Code 2.1.198 a dispatch runs in the background by default and its tool
  response carries `status: "async_launched"` with no launch wording, so every launch read
  as a finished builder and the nudge said to dispatch `reviewer` now. The status now
  decides, ahead of any text in the response.
- A guard `ask` now also sends its reason as `additionalContext`. Claude Code shows an
  ask's `permissionDecisionReason` to the user only, so the cheaper path each reason names
  never reached the main session.
- The discovery-agent ask covers more built-in types that run on the session's model:
  `Plan` and the `claude` catch-all join `Explore` and `general-purpose`, and an Agent
  call with no `subagent_type` counts as `general-purpose`, the type Claude Code runs for
  it. Matching is now exact, so a plugin agent such as `other:claude` passes. A `fork` is
  deliberately not asked about: fork mode, on by default in interactive sessions, spawns
  forks routinely, and a prompt on each one stalls unattended workflows.
- `/route:delta` measures a background dispatch's report from the subagent's own
  transcript: the text after its last tool result, or its `SubagentHandback` message
  (auto mode, 2.1.271+). The main transcript holds only the launch notice or a hand-back
  note there. Background launches are left out of `--validate`, since the launch turn
  grows the context by the prompt alone.
- `SKILL.md` Step 1 and `scout.md` no longer say a subagent cut at `maxTurns` returns
  nothing: since 2.1.246 its output comes back marked partial.
- Turning a role off no longer blocks another plugin's agent that shares the name.
  `roles.builder.enabled=false` denied `other:builder` too, because the namespace was
  stripped whatever it was. Only `route:<role>`, `route:<dir>:<role>` and the bare name
  count now. The review nudge uses the same rule, so `other:builder` returning is silent.
- `/route:doctor` fails the `roles` check on a switch the hooks cannot read as written:
  a non-boolean `enabled` (`"false"` leaves the role on), a role entry or `roles` block
  that is not an object, an unknown key inside a role entry, an unknown role name, and a
  non-boolean legacy `scout.enabled`. Each line says whether the role is actually on or
  off. It used to report "all four roles may be dispatched" while the file read as off.
- A `roles` value that is not an object no longer crashes the hooks. The session brief
  was lost with it; the guard failed open, as it still does.
- With `roles.builder.enabled=false` the main session is the only implementer, but the
  guard asked on every one of its production-code writes, through `Write`/`Edit` and
  Bash, and the reason said to dispatch `builder`, which the guard denies. A write whose
  owning role is off now passes with no ask, under every `guard.mainSeverity`:
  production code when builder is off, tracking records when scribe is off. The record
  timestamp check still applies. A Bash command skips such a target and still asks on a
  later one whose role is on. The session brief names only the edits the guard still
  asks about, and `SKILL.md` Step 4 has the main session produce builder's report lines
  for reviewer when builder is off.
- `/route:delta` counted a background dispatch's return as the larger of its launch
  notice and its report, so it left out most of what the main session keeps. Main holds
  the launch notice plus later rows of its own: the hand-back, which Claude Code 2.1.277+
  wraps in a subagent-output frame, and the task-notification. On one 2.1.278 scribe
  dispatch that came to 3,492 characters against 1,060 counted, and the net turned from
  +69 to -539 tokens. The cost side now adds every row whose `origin` is a `peer`
  message from the dispatch's agent or a `task-notification` for its tool_use_id.
  Without such rows it estimates as before.
- `SKILL.md` Step 0.25 wrote its cost example with a dollar sign before each figure.
  Claude Code replaces `$0` in a skill with the first invocation argument, so
  `/route:route <args>` put the arguments into the table. The figures now sit in a
  `Cost (USD)` column and read `USD 0.77`.

### Unchanged

Role scopes, subagent write rules, model tiers and turn budgets. Every Bash rule except
the main session's, which now skips a target whose owning role is off. The calling
role is still matched with the namespace stripped, so write rules are unchanged.

### Tests

296 passed (was 232).

## [0.9.3] - 2026-09-07

### Changed

- Turn budgets raised: `scout` 40 → 80, `reviewer` 40 → 80, `scribe` 45 → 90,
  `builder` 80 → 240.
- The hardcoded budget in `route/agents/scout.md`, `SKILL.md` Step 1 and the README role
  table follow the new scout number.

### Why

0.9.2 raised every cap from measured data and stated the principle it was applying: a cap
is a stop, not a budget — unused headroom costs nothing, while hitting one costs a
re-dispatch that replays the whole brief. This release applies that principle further and
takes the caps out of the working range entirely, so a capped run is an anomaly to
investigate rather than a routine cost the caller absorbs silently.

### Unchanged

Guard behaviour, role scopes, model tiers, the degradation protocol (`NOT ANSWERED:`,
`VERIFY: BLOCKED`), and scout's 40-line output ceiling, which is an output limit and not a
turn budget.

### Tests

232 passed, 0 failed.

## [0.9.2] - 2026-09-02

### Changed

- Turn budgets sized from 463 measured subagent runs: `scout` 30 → 40, `scribe` 30 → 45,
  `builder` 60 → 80, `reviewer` unchanged at 40. Every role's maximum equalled its cap
  exactly, so the distributions were censored rather than tight.
- `roll_records.py` is the required path for an archive move; scribe may not discover a
  destination it was not handed; builder runs the `Verify` command at most three times,
  then reports `VERIFY: BLOCKED`; Step 1 must bound scout's search space.

### Fixed

- The guard no longer denies the verify command. `_write_targets` resolved a single line
  and read the `&` inside `2>&1` as a chain operator, so a redirected test command came
  back as an unresolvable write. Resolution now runs segment by segment.
- Worktree sessions work again: `strip_worktree` normalises the
  `.claude/worktrees/<name>/` prefix before classification.

### Tests

232 passed (was 212).

## [0.9.1] - 2026-09-01

### Changed

- `scribe` no longer composes prose a human will read; the caller supplies the finished
  text and scribe places it. Step 6 adds a two-file cap per dispatch.
- Step 4 tells the caller to paste builder's `VERIFY`/`TESTS`/`LINT` lines into the
  reviewer dispatch; `reviewer` has no Bash and now says what to do when a brief tells it
  to run commands anyway.
- Step 2 gains four pre-dispatch checks on the builder's contract: watch the verify
  command fail, type-check the Lane 2 failing test against the proposed signature,
  validate any classification rule against real data with the counts recorded, and state
  the negative case.
- Step 5 adds the one place worth spending context on: where a wrong answer is silent —
  money arithmetic, authorization, migrations, retries — the main session reads the diff
  itself.

### Tests

212 passed.
