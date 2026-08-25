# Field report — 2026-08-25, stock-pnl-web, BUG-036 (daily backup lost an account)

A production defect that the routing loop shipped with a `PASS`. This report records which
role could have caught each half, and the change made to `reviewer.md` as a result.

## What happened

The nightly `backup-transactions` job backs up every account in a sequential loop. On
2026-08-25 it lost one account. The log row it wrote said, in full, `[object Object]`.

Gateway logs identified the cause: of the three PostgREST requests the function issues for
one account in a single `Promise.all`, one returned **401** and the other two returned 200 —
same client, same service-role key, same millisecond. A transient rejection. Nothing retried
it, so one rejected request cost that account its whole day's backup, and the field that
exists to explain the failure explained nothing.

Four defects, shipped across releases 0.9.11 and 0.9.12, both of which the reviewer passed.

## 1. Who could have caught each defect

| # | Defect | Spec said | Verdict |
| --- | --- | --- | --- |
| 1 | `err instanceof Error ? err.message : String(err)` records `[object Object]`, because PostgREST errors are plain objects | "write a row with `status='error'` **and the message**" | builder defect; reviewer miss |
| 2 | The insert that writes the log row never checks its own result | "insert one row" | builder defect; reviewer miss |
| 3 | No retry anywhere; one transient failure ends the account for 24 hours | *nothing* | **spec omission** |
| 4 | A prune failure writes `error` but keeps `status='ok'`, and the console renders only `status`, so the message is dropped | phase 1 defined the field; phase 2 listed the column; neither said how to render it | **spec omission, at a seam** |

Two of four were the main session's fault, not the subagents'.

## 2. A reviewer anchored to the spec cannot find a missing requirement

`reviewer.md`'s check order was: spec conformance, scope, correctness, test integrity. Three
of those four are defined relative to the spec. That makes every gap in the spec a shared
blind spot for builder *and* reviewer — the builder implements what is written, the reviewer
confirms that what is written was implemented, and the thing nobody wrote is invisible to
both. Defects 3 and 4 sit exactly there.

Defect 1 shows the same shape one level down. The spec said "and the message". The code
passes `err.message` when `err` is an `Error`. It satisfies the sentence. It fails for the
error class that dominates this call site — and knowing that requires knowing that a
dependency returns plain objects rather than `Error`s, which is a fact about the runtime, not
about the diff.

## 3. The green test proved only that the test agreed with the bug

Lane 2 says the main session writes the failing tests. The charter it wrote for this feature
was entirely happy-path: pure helpers over well-formed input. The Edge Function's `index.ts`
had **no** tests at all, so no error path in the pipeline was ever executed. "The gate for
ordinary work is the test passing" is only as strong as the charter behind it, and the
charter is the expensive session's own output — the cheap roles cannot compensate for it.

## 4. The reviewer that ran was not the reviewer in this repo

The project's installed `.claude/agents/reviewer.md` was several revisions behind
`route/agents/reviewer.md` — it predated the diff-path input, the large-file rule and the
changed-file coverage rule, and carried local frontmatter edits (`effort: high`, `Bash`
added). Field reports that name a role's behaviour are only meaningful against a known
revision of that role. Copies drift silently and nothing reports it.

## What changed

`route/agents/reviewer.md` gains a **`## The standing checks`** section: five checks the
reviewer runs on every dispatch regardless of what the spec says, reported as `RISK` unless
the code is wrong on its own terms. They are drawn from this incident and generalised:

1. an error value that cannot survive being turned into text;
2. a result that is never read;
3. a remote call with no retry inside work that will not be attempted again soon;
4. a field written but never read, or read but never shown;
5. a seam between two contracts, where neither spec owns the joint.

The section states explicitly that "the spec did not ask for it" is not grounds for silence.
That sentence is the actual fix — the checklist is the worked example.

## What this does not fix

- **The charter is still the main session's job.** A rule worth adding to the Lane 2
  instructions: every external call in the contract needs at least one failure-path case in
  the `## Test charter` table. Not added here; it belongs in the route skill, not in an agent
  file.
- **Copy drift is still silent.** Nothing checks an installed `.claude/agents/*.md` against
  the plugin source, and this session found the drift only by diffing by hand.
- **Cost.** These checks lengthen every review. They were added because the failure mode they
  catch survived two reviews and reached production, but the trade is real and should be
  measured against `/route:audit` before being treated as settled.
