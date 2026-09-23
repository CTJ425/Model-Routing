# Field report — 2026-09-23, route plugin, builder on vs builder off (T7, revised)

Seven historical commits replayed twice each: arm A with builder and reviewer on (current
config), arm D with both off, so the main session writes the code itself. The user
changed T7 from an effort experiment to this comparison and capped spend at $5.

## Conclusion

On small, test-specified tasks, **arm D cost 46% less ($0.32 against $0.59 per task) and
took less than half the time, with the same outcome: 7 of 7 accepted in both arms.** This
does not show that removing builder and reviewer is right in general: the task set, the
fresh sessions, and the missing quality check all favour D (see Limits).

## Method

- Each task: a `git worktree` at `<commit>^`, with the commit's test files (and spec, if
  any) checked out so they fail. One fresh headless session per arm:
  `claude -p --model opus --effort medium --max-budget-usd 1.2`, same brief text
  (`Task: Rn —` subject, commit body, Files list, Verify command).
- Arm A config: builder, reviewer, scout on (`review.policy: risk`). Arm D: builder and
  reviewer off, scout on. Scribe and bookkeeping off in both.
- Accepted = the full suite passes after the session and the diff touches only the brief's
  Files. Cost = `claude -p` `total_cost_usd`; the role split is `routing_audit.py` after
  the B1 fix (`d2ad296`), which matches that total.
- Runner: `run.sh` / `batch.sh` in the session scratchpad (not kept in the repo).

## Results

| Task | Commit | Prod files | A USD (main / builder / reviewer) | A s | D USD | D s | Accepted A / D |
| --- | --- | --- | --- | --- | --- | --- | --- |
| R1 task identity | `71045cb` | 1 | 0.59 (0.33 / 0.12 / 0.14) | 163 | 0.27 | 64 | yes / yes |
| R2 --by-task | `9d20ad8` | 2 | 0.65 (0.35 / 0.31 / —) | 171 | 0.53 | 109 | yes / yes |
| R3 delta return cost | `0eee40a` | 2 | 0.66 (0.33 / 0.18 / 0.15) | 162 | 0.41 | 82 | yes / yes |
| R4 Step 4 nudge | `f008c5f` | 1 | 0.57 (0.37 / 0.10 / 0.11) | 126 | 0.27 | 50 | yes / yes |
| R5 scribe archive read | `e0e7dad` | 2 | 0.64 (0.45 / 0.10 / 0.08) | 143 | 0.26 | 47 | yes / yes |
| R6 deny Bash writes | `b10b107` | 2 | 0.66 (0.45 / 0.11 / 0.11) | 159 | 0.26 | 53 | yes / yes |
| R7 fork dispatch | `d62ec9f` | 3 | 0.37 (0.27 / 0.10 / —) | 119 | 0.26 | 69 | yes / yes |
| **Mean** | | | **0.59** | **149** | **0.32** | **68** | **7 / 7** |

- **A's main session alone (mean $0.36) cost more than all of D ($0.32).** In A the main
  session still reads the brief, briefs the builder, re-runs Verify and adjudicates, so
  the builder and reviewer are added cost, not moved cost, on tasks this size.
- The two A runs without a reviewer (R2, R7) were the two closest to D.
- R6 had 44 failing tests before; both arms fixed all of them.

## Limits

- **Task size.** Every task is 1–3 production files with failing tests supplied. That is
  the case where the main session needs no exploration. Larger or unmapped tasks, where a
  builder keeps bulk reading out of the main context, are not in the set.
- **Fresh sessions favour D.** Each run started with an empty context. In a long session
  the main context is much larger (this project's main sessions average about 135k tokens
  of cache read per turn, against about 26k in these runs, measured over 136 main turns), so every turn the main
  session spends implementing costs several times more there.
- **Quality beyond the tests was not measured.** The reviewer's value is what tests do not
  catch. In this session reviewers found real defects the tests missed (T2: text blocks
  joined without a newline; B1: first-row usage instead of last-row). Arm D had no review.
- **One run per task and arm.** Seven pairs, no repeats.
- Only 7 tasks (the spec asked for 8). R8 was dropped for budget.

## Spend

$6.69 in total: $6.39 for the 14 runs plus $0.30 for a run cut off by the account usage
limit and repeated. The user's $5 cap arrived while the batch was running; the batch was
stopped after it had already passed the cap.

## Recommendation

- Keep builder and reviewer. Use Lane 0 (main session implements) more readily for tasks of
  this shape: known files, failing tests supplied, at most about 100 changed lines. That
  is what SKILL.md Step 0.25 already says; this run puts a number on it: about $0.27 per
  task saved, and half the wall time.
- Keep the reviewer on for silent calculations and boundaries whatever the lane.
- To test builder-off on large tasks, repeat this design on 3–4 multi-file tasks without
  supplied tests, in a long-context session.
