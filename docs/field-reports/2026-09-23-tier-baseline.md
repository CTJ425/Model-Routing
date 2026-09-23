# Field report — 2026-09-23, route plugin, tier baseline (spec T5)

The Sonnet baseline for builder and reviewer, taken from history, and the first Opus 5.5
runs beside it. Spec: `docs/20260923.md` T5. No tier was changed for this report.

## Conclusion

The baseline is **one Sonnet builder task**. It is not a statistical baseline. It shows only
that a large Lane 2 task cost $1.76 in subagents on Sonnet 5 / high. The Opus 5.5 / medium
tasks so far are 3–10x smaller, so no cost-per-task comparison between tiers is valid yet.
T7's paired run is the first valid comparison.

## Source

- `routing_audit.py` over all 8 transcripts that still exist for this project (the oldest is
  from 2026-09-22; older sessions are gone). Every route-role run in them is listed below.
- Outcome (accepted, FAIL count) from `docs/agent/PROGRESS.md` and
  `docs/agent/PROGRESS_ARCHIVE.md`. Size from `git show --stat` of each task's commit.
- USD is list price from `route/scripts/pricing.json` (Opus 5.5 $4/$20, cache read 0.05x;
  Sonnet 5 $2/$10, cache read 0.1x).
- Sonnet-era runs have no `Task:` line. They appear as `(untagged)` in `--by-task`; the
  task names below come from the brief text.

## Per task

| Task | Tier | Lane | Prod lines ± | Builder turns / cacheR / USD | Reviewer turns / cacheR / USD | Subagent USD | FAIL | Accepted |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S1 route-role-off-main-writes (`9475ccf`) | sonnet-5 / high | 2 | ~100 in 6 files, +113 test lines | 91 / 4,536,187 / 1.35 | 26 / 551,271 / 0.41 | 1.76 | 0 | yes |
| S2 delta return cost (`0eee40a`) | sonnet-5 / high | 1 | ~53 in 2 files | — (main session wrote it) | 17 / 303,373 / 0.28 | 0.28 | 0 | yes |
| T4 task-id rule (`79e5d79`) | opus-5-5 / medium | 1 | 6 in 1 file | 11 / 114,621 / 0.13 ¹ | 11 / 105,650 / 0.21 | 0.34 | 0 | yes |
| T2 task identity (`71045cb`) | opus-5-5 / medium | 2 | 32 in 1 file | 10 / 105,424 / 0.10 | 18 / 208,675 / 0.29 | 0.39 | 0 | yes |
| T3 --by-task (`9d20ad8`) | opus-5-5 / medium | 2 | ~71 in 2 files | 12 / 212,410 / 0.25 | 12 / 174,922 / 0.35 | 0.60 | 0 | yes |

¹ Includes one probe resume (a no-op `SendMessage` to confirm the resume format for T2).

Scout and scribe runs (Haiku) are left out: they are not part of the tier change.

## What the numbers do and do not show

- **Turns drive cost, as the spec predicted.** S1's builder spent 67% of its cost on cache
  reads (91 turns replaying a growing context). The Opus builders ran 10–12 turns.
- **The task sizes differ too much to compare.** S1 was the largest task (6 production
  files, 17 new tests, Lane 2). T3 is the closest Opus task in size and cost $0.60 against
  S1's $1.76, but it is roughly half the size. This is not evidence that Opus is cheaper.
- **Reviewer cost did not fall.** Opus reviewers cost $0.21–0.35 against $0.28–0.41 on
  Sonnet, for smaller diffs. That matches the spec's estimate (+73–79% per review at equal
  tokens).
- **No FAILs on either tier.** Five of five tasks were accepted first time, so these runs
  give no information about the FAIL rate.
- **Main session dominates.** Over all 8 sessions the main session is $112.40 of $116.18
  (97%); builder and reviewer together are $3.02. The tier choice changes the smaller
  share.

## For T7

- Use one fixed task set for all arms. History cannot supply a matched baseline.
- Record the same columns as the table above, per arm, from `routing_audit.py --by-task`.
- Tag every brief with `Task: <id>` so runs group without manual matching.
