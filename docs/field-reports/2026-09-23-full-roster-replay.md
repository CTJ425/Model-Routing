# Field report — 2026-09-23, route plugin, full roster vs scout + scribe only

Follow-up to `2026-09-23-builder-off-replay.md`. Two new arms on three of the same
historical commits, so all four arms can be compared on R3, R5 and R7. Cap: $5.

## Conclusion

- **Builder and reviewer off saves about 40% in both brief styles, with no lost
  acceptance.** Full roster (F) $0.72 per task against scout + scribe only (S) $0.43;
  earlier A $0.55 against D $0.31. 12 of 12 runs accepted.
- **Scribe ran in 6 of 6 runs and cost $0.02–0.04 each (about 5% of a task).** Its
  records were correct. Keep it.
- **Scout ran in 0 of 6 runs**, although the brief named no files. The main session chose
  to read the code itself every time. This experiment gives no evidence for or against
  scout; the one historical scout run ($0.16 for 450k tokens read) is still the only data.

## Method

Same as the builder-off replay (worktree at `<commit>^`, the commit's tests checked out
failing, one fresh `claude -p --model opus --effort medium` session per arm), with two
changes to the brief: **no Files list** ("find where the change belongs yourself"), and
**"record the outcome as a new top entry in docs/agent/PROGRESS.md"**.

- F: scout, builder, reviewer, scribe on; bookkeeping on; `review.policy: risk`.
- S: scout and scribe on; builder and reviewer off; bookkeeping on.
- Accepted = full suite passes and every touched file is one the original commit touched
  (plus `PROGRESS.md`, which the brief asked for).

## Results (USD per task; A and D from the earlier run, which had a Files list and no record step)

| Task | A | D | F (main / builder / reviewer / scribe) | S (main / scribe) | F s | S s |
| --- | --- | --- | --- | --- | --- | --- |
| R3 `0eee40a` | 0.66 | 0.41 | 0.79 (0.52 / 0.17 / 0.08 / 0.03) | 0.48 (0.44 / 0.04) | 198 | 123 |
| R5 `e0e7dad` | 0.64 | 0.26 | 0.52 (0.40 / 0.11 / — / 0.02) | 0.39 (0.35 / 0.04) | 128 | 116 |
| R7 `d62ec9f` | 0.37 | 0.26 | 0.83 (0.65 / 0.15 / — / 0.03) | 0.41 (0.38 / 0.03) | 246 | 134 |
| **Mean** | **0.55** | **0.31** | **0.72** | **0.43** | **191** | **124** |

Role use in F and S: scout 0/6, scribe 6/6, builder 3/3 (F), reviewer 1/3 (F; R5 and R7
were skipped under `risk`). In R5-S the authorization trigger fired with reviewer off, and
the main session recorded that it reviewed the diff itself.

- Taking away the Files list and adding a record step cost +$0.16 per task in the
  builder-on arms (A→F) and +$0.12 in the builder-off arms (D→S).
- F's main session alone ($0.52 mean) cost more than all of S ($0.43).

## Limits

Everything in `2026-09-23-builder-off-replay.md` § Limits applies: small tasks, fresh
short sessions, one run per arm, and no quality measure beyond the tests. Three tasks here.
Scribe was never switched off, so its saving against an inline record is not measured;
its direct cost is.

## Spend

$3.43 for six runs, under the $5 cap (batch cap $4.7 to absorb a run's overshoot).

## Recommendation

| Role | Keep? | When to dispatch |
| --- | --- | --- |
| builder | keep | large or unmapped work, or a long main context. For ≤3 known files with failing tests supplied, the main session implements (widen Lane 0 beyond one file). |
| reviewer | keep | whenever a Step 4 trigger fires, in every lane. |
| scribe | keep | any record with more than a line or two; it costs about $0.03. |
| scout | keep (free when unused) | bulk reading. Untested here: the Boss never chose it on these tasks. |
