# Field report — 2026-09-23, stock-pnl-web replay: which roles, which models (Opus 5.5 main)

Question from the user: with an Opus 5.5 main session, which subagents are not needed, and
if builder and reviewer are needed, which model each should run on so that no tokens are
wasted and accuracy does not drop. Budget cap $25; spent $22.05.

## Conclusion

- **No arm lost measured accuracy, and the all-off arm (D) was the cheapest on every task**
  ($0.83 mean against $1.18 for scout + scribe and $1.55 for the full roster).
- **The reviewer's value is real but was not reliably collected.** On the backup task (R2)
  the reviewers named the defects that later reached production (no retry, raw error
  objects, PostgREST paging) between them. But the main session dispatched no reviewer on the P&L task in
  2 of 3 full-roster runs, although the silent-calculation trigger applied, and no run fixed
  the retry defect the reviewers flagged.
- **Builder: Opus 5.5 / medium, not Sonnet 5.** The Sonnet builder cost 25–36% more on R1 and
  3% more on R2, ran slower, and gave the same result.
- **Reviewer model: no data for Sonnet.** A Sonnet reviewer never ran: one session skipped
  review, and the other ignored `models.reviewer` (next point).
- **`models.<role>` is not enforced.** In 1 of 4 Sonnet-configured sessions the main session
  dispatched without the `model` parameter, so builder and reviewer ran on the frontmatter
  default (Opus). The config only works when the main session remembers to pass it.

## Method

- Repo: `CTJ425/stock-pnl-web` (TypeScript/React + Supabase edge functions, 382 source files,
  2,613 vitest tests in 64 s, `tsc -b`, `oxlint`; all offline).
- Four historical commits, each replayed from `<commit>^` with that commit's tests checked out
  failing. Brief: commit message, visible tests, Verify (`vitest` targeted + full, `tsc -b`,
  `oxlint`), **no file list**, and "record the outcome in docs/agent/PROGRESS.md".
- One fresh `claude -p --model opus --effort medium` session per run. The installed plugin was
  route 0.9.4 as released (not today's unpushed commits).
- Arms (`roles` / `models` in the worktree's `.claude/route.config.json`):
  D all off · S scout + scribe · FO all on, builder and reviewer Opus · FS all on, both Sonnet ·
  FSO all on, builder Sonnet, reviewer Opus. Scout and scribe run Haiku 4.5.
- Graded after the session: visible tests, full suite, `tsc`, lint, files touched. R1 also ran
  the 7 tests that the later fix commits `b5d87d5`, `a34ec3d`, `caea550` added (fee-rate
  inference and same-day ordering); they fail on the original commit by assertion. R2's later
  tests fail only on a missing export, so R2 was graded against the known production defects
  instead (BUG-036 and the PostgREST paging fix in `2799991`).

## Tasks

| Id | Commit | What | Size |
| --- | --- | --- | --- |
| S1 | `bab795a` | watchlist search: two defects | 4 prod files, 62 lines |
| M1 | `859feca` | international indices tab (edge function + service + UI) | 6 files, 322 lines |
| R1 | `e120041` | lot-based unrealized P&L, day-trade tax split (silent calculation) | 8 files, 147 lines |
| R2 | `4c70ad6` | daily per-account backup to Storage (persistent state) | 4 files, 331 lines |

## Results

USD per run (main / scout / builder / reviewer / scribe where dispatched), seconds.

| Task | D | S | FO | FS | FSO |
| --- | --- | --- | --- | --- | --- |
| S1 | **0.79** · 322 | 1.01 (0.95 / – / – / – / 0.06) · 337 | 1.44 (0.46 / – / 0.58 / 0.32 / 0.08) · 370 | | |
| M1 | **0.73** · 206 | 1.34 (1.15 / 0.11 / – / – / 0.08) · 375 | 1.14 (0.59 / – / 0.50 / – / 0.05) · 351 | | |
| R1 | **1.21** · 296 | 1.40 (1.16 / 0.11 / – / – / 0.13) · 500 | 1.86 (0.48 / – / 0.94 / 0.33 / 0.08) · 511 | 1.98 (0.65 / – / 1.17 S / – / 0.16) · 713 | 1.95 (0.67 / – / 1.28 S / – / –) · 551 |
| R2 | **0.60** · 129 | 0.95 (0.78 / – / – / – / 0.17) · 319 | 1.76 (0.68 / 0.14 / 0.62 / 0.21 / 0.12) · 624 | 1.84 ¹ · 669 | 2.06 (0.87 / 0.19 / 0.64 S / 0.20 / 0.15) · 656 |
| **Mean (S1–R2)** | **0.83** · 238 | 1.18 · 383 | 1.55 · 464 | | |

S = Sonnet 5. ¹ R2-FS dispatched with no `model` parameter: builder and reviewer ran Opus 5.5
(0.61 / 0.17 / 0.67 / 0.23 / 0.17), so it counts as a second FO run, not a Sonnet run.

Accuracy:

- Visible tests, full suite and `tsc` passed in all 15 runs. Lint exited 1 in all three S1
  runs; the original commit `bab795a` also exits 1, so that is the baseline.
- No run modified an existing file outside the original commit's set (new files differ in
  name, which the brief allowed).
- **R1 hidden tests: 0/7 in all five arms**, the same as the original commit. The one R1
  reviewer (FO) returned FAIL with other findings (a fee effect in `TransactionForm`, 6-digit
  TDR codes, a zero-fee break-even edge) but not these two defects.
- **R2 production defects** in the final code:

| Defect (later found in production) | D | S | FO | FS ¹ | FSO |
| --- | --- | --- | --- | --- | --- |
| Table read without `.range()` paging: rows past 1000 silently dropped | kept | fixed | fixed | fixed | fixed |
| Raw Supabase error object logged as `[object Object]` | kept | fixed | fixed | fixed | fixed |
| No retry on a transient failure (the BUG-036 401) | kept | kept | kept | kept | kept |

  All three R2 reviewers (FO, FS, FSO) named the missing retry; FO and FS named missing
  paging as a BLOCKER (FSO's builder had already paged); FSO named the raw error object. The
  main session fixed paging and accepted "no retry" as a risk each time. S fixed the first two
  with no reviewer, so one run per arm cannot attribute that to review.

Role use: scout was dispatched in 5 of the 12 runs where it was on ($0.11–0.19); none of
those runs was cheaper than its D counterpart. Scribe ran in 11 of 12 ($0.05–0.17). The
reviewer ran in 5 of 8 full-roster runs.

## Answers

| Role | Verdict under an Opus 5.5 main session | Model |
| --- | --- | --- |
| builder | Not needed for tasks of this size (≤8 files, ≤330 lines, tests supplied): +$0.4–1.2 per task, no measured gain. | Opus 5.5 / medium when used. Sonnet 5 was not cheaper. |
| reviewer | Keep, for persistent state, boundaries and silent calculations. It found the real R2 defects; it missed R1's. | Opus 5.5 / medium. Sonnet untested. |
| scout | No measured benefit in a fresh session on a 4 MB repo. | Haiku 4.5. |
| scribe | Small cost ($0.05–0.17); D wrote its own record for less in total. Optional. | Haiku 4.5. |

## Plugin defects found

1. `models.<role>` depends on the main session passing `model` on the Agent call; 1 of 4
   sessions did not. The guard could deny a route-role dispatch whose `model` is missing or
   differs from the config.
2. Review policy `risk` was not applied on a silent-calculation task in 2 of 3 runs.
3. RISK findings on a persistent job (no retry) were accepted every time; nothing in Step 5
   asks for more than recording them.

## Limits

One run per task and arm; four tasks; fresh sessions (short main context), which favours D;
R1's hidden tests cover two defect classes only; R2 is graded against three known defects.
