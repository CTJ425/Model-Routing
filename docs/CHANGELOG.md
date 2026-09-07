# Changelog

All notable changes to the `route` plugin. This file is the source of truth from 0.9.1
onward; releases 0.9.0 and earlier live in the git tags and their GitHub Releases, and
the fuller narrative for every version is in `docs/agent/PROGRESS.md` and its archive.

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
