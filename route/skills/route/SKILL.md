---
name: route
description: Run a task through the model-routing loop — classify it into a lane, dispatch scout/architect/builder/reviewer/scribe at their own model tiers, and verify. Use when starting a feature, fixing a bug, working through a tracking doc's open items, or when the user says "route this", "run the next task", or asks why everything is running on the most expensive model.
---

# Routing loop

You are the Boss. The main session holds the plan and spends as few of its own tokens
as possible doing it. Everything verbose happens in a subagent and comes back small.

Delegation here is **pre-authorized** — dispatching these agents is the requested
behaviour, not something to ask permission for each time.

## Step 0 — classify the lane

Answer three questions about the task: how much inference does it need, what does being
wrong cost, and how much subjective judgement is involved.

| Lane | Use when | Path |
| --- | --- | --- |
| **0 — inline** | The edit is **surgical** — a typo, a version bump, a one-line fix, a few hunks you can name in one sentence — **and** it lands in one file you have read the relevant region of — scout's map tells you *where* to edit, never *what the text is*, so a map alone is not enough. Trips none of the Step 4 review triggers, and you can name the verification command *before* editing | main session -> verify -> record (Step 6) |
| **1 — bounded** (default) | A clear fix or feature inside known modules | `route:scout` (if the area is unmapped) -> brief -> `route:builder` -> `route:reviewer` (per Step 4 policy) -> `route:scribe` |
| **2 — elevated risk** | Unknown-cause bug, cross-module change, or any of the Step 4 triggers known up front: persisted state, authorization, a boundary, a silent calculation, control-flow behaviour, or a builder blocker | `route:scout` -> `route:architect` (spec + failing tests) -> `route:builder` -> `route:reviewer` (always) -> adjudicate -> `route:scribe` |

State the lane in one line before you act. If you pick Lane 0 for a tracked task,
record why in the project's progress log.

A Lane 0 edit is still a main-session write to production code, so `guard.mainSeverity`
applies to it — through `Write`/`Edit` and through the shell alike. Confirming that prompt
is how a Lane 0 call gets recorded; routing around it with `sed -i` is not.

## Step 0.25 — weigh the job against the dispatch floor

Every dispatch pays a cold start: the subagent's system prompt, tool definitions and
project instructions all load before it reads one line of your task. That floor is flat,
so on a small job it *is* the bill.

One illustrative measurement on a bounded single-file task (2026-08-13, opus Boss, haiku
subagents) was:

| Dispatch | What it did | Cost |
| --- | --- | --- |
| `route:scout` | mapped icon usage across a 469-line file | $0.032 |
| `route:scribe` | appended a few lines to two tracking docs | $0.036 |

The append cost more than the mapping. Nothing about the work explains that — the floor
does. That run came to **$0.77 routed against $0.74 for the same task done entirely by the
Boss**, for a byte-identical diff. These are environment- and price-table-specific
examples, not a universal dollar threshold.

So before each dispatch, ask: **is this job bigger than the floor?** A dispatch earns its
place when it keeps bulk out of your context — a large file to read, a long log to
compress, a multi-file edit. It loses when the whole job would fit inside the prompt you
are writing to describe it. When the work is genuinely small and low-risk, Lane 0 is
usually cheaper; use `/route:delta` to calibrate this decision for the project rather than
treating the example above as a fixed threshold.

This is a sizing question, not a risk question. It never overrides Step 4 — a change that
trips a review trigger gets reviewed however small it is.

## Step 0.5 — model overrides and the live roster

Before every dispatch in Steps 1, 2.5, 3, 4 and 6, check the project root for
`.claude/route.config.json`:

```json
{
  "version": 2,
  "paths": { "prod": ["src/"] },
  "models": { "scout": "haiku", "architect": "opus", "builder": "sonnet", "reviewer": "sonnet", "scribe": "haiku" },
  "roles": { "scout": { "enabled": true }, "architect": { "enabled": true }, "builder": { "enabled": true },
             "reviewer": { "enabled": true }, "scribe": { "enabled": true } },
  "review": { "policy": "risk" },
  "bookkeeping": { "enabled": true }
}
```

`roles.<role>.enabled` decides whether a role exists for this project at all. A role set
to `false` is denied by the guard, so do not dispatch it: skip that step and do its work
in this session, then say in one line which step you absorbed and why. Every role
defaults to `true`, and `scout.enabled` is a legacy alias that still works.

If `models.<role>` is set for the role you are about to dispatch, pass it explicitly as
the `model` parameter on the Agent call — this takes precedence over the agent file's own
frontmatter `model:` and lets a project change tiers without editing plugin files that a
plugin update would overwrite. If the file or the key is missing, dispatch with no
`model` override and let the agent's frontmatter default apply. `/route:config` is how a
user edits this file; never hand-edit an agent's frontmatter to change its tier.

One override sits above both: the `CLAUDE_CODE_SUBAGENT_MODEL` environment variable
outranks the per-invocation `model` parameter. If it is set in the user's environment,
this step has no effect and every subagent runs on that model — say so rather than
reporting a tier that is not in force. `/route:config` reports it when present.

Also read `language.artifacts` and pass it explicitly to every dispatched agent. It controls
prose in reports and records; code, paths, identifiers, and commit messages remain English.

## Step 1 — scout (haiku by default)

Skip this step entirely when `roles.scout.enabled` is `false` in
`.claude/route.config.json` — go straight to the next step with what you already know. Otherwise: only when the
affected area is not already mapped. Ask a specific question — never "look at the report
pipeline", always "where is X chosen, who calls it, which tests cover it". You get back
~40 lines. This is the single largest token saving in the system.

If you have made a dozen Read/Grep calls yourself, you are doing scout's work at several
times the price; a hook will tell you so.

Dispatch it as `route:scout`. Do not reach for the built-in `Explore` or
`general-purpose` instead — they inherit the caller's model, so they do scout's job at
the caller's price. A PreToolUse guard asks before letting one through; confirm only
when you need a tool scout lacks.

Scout has no Bash. If the material to compress is command output, put the text in the
dispatch prompt or write it to a file and give scout the path.

**Size the dispatch to scout's turn budget: 30, and it cannot be raised per project.**
`maxTurns` lives in the agent frontmatter and the config schema has no such key. Because
scout has no Bash, it cannot chain `grep -n X -A 20` in one shell call — every
locate-then-read is two turns. Measured on a stock-pnl-web session: two dispatches asking
**two** focused questions each finished in 13 and 12 tool calls; one asking **four**
questions against a 4,095-line file was cut off at 36 and returned nothing usable, so the
caller paid for the reading twice.

- **One question per dispatch.** Split a multi-part trace into parallel scouts, one
  question each, rather than stacking them into one prompt.
- **Give line ranges when you already know them.** Turning a search into a read is the
  difference between ~30 turns and ~4. An earlier scout's answer usually hands you the
  range for the next one.
- **A scout cut off at the budget keeps its state.** Resume it with `SendMessage` instead
  of re-dispatching from cold. A scout that stopped itself hands you a `NOT ANSWERED:` line
  to resume against; one that was cut hard returns nothing at all, so resume it with the
  same question plus any line ranges you now know. If a second resume also returns nothing,
  the question is too broad — split it. Do not resume a third time.

## Step 2 — the builder's input, sized by lane

The main session owns the **Lane 1 brief** and all **adjudication** (Steps 4–5). It does
not delegate those: judging a reviewer finding or a Verify result needs loop state a
subagent does not hold. A **Lane 2 spec plus failing tests** is a bigger job — it is a
dispatch to `route:architect` (Step 2.5), on the expensive tier, because a wrong contract
is not caught by review, it is implemented and then reviewed as correct.

> **If this session is not itself on the expensive tier** — an `opusplan` main session
> drops to the cheaper tier once planning ends, and a session started on a mid tier never
> had it — then no model sits above the builder in the execution loop unless
> `route:architect` is dispatched. Under that setup:
>
> - Route the Lane 2 spec through `route:architect` even when you could just about write
>   it here, and set `review.policy` to `always` so the review gate is never a judgement
>   call this session gets wrong silently. `/route:config review.policy=always`.
> - For an **open architecture question** — the shape of the change is not yet decided —
>   dispatch `route:architect` in **consult mode** (Step 2.5): it returns options and a
>   recommendation as a design note the human reads directly, and is resumed with their
>   decisions. The alternative, when the human wants a live back-and-forth rather than a
>   relayed one, is for them to switch this session to the expensive tier for that phase
>   (`/model`) and switch back after — the relay through this session is lossy.

**Lane 1 — a brief, in the dispatch prompt. No file.** A spec file for a bounded fix is
overhead that does not pay for itself. Five headings, inline:

```
Task: <id> — <one line>
Contract: <inputs / outputs / error cases; what must NOT change>
Files: src/...   <- exhaustive; you may touch nothing else
Verify: <the exact command> — not done until this passes
Non-goals: <what not to do>
```

**Lane 2 — a spec file plus failing tests, written by `route:architect`.** See Step 2.5.
The spec has the same five sections expanded, plus a `## Test charter` table
(`| Case | Expected outcome | Layer / file |`), and the failing tests exist before the
builder is dispatched. The builder gets the spec path and the test path only.

The `Files` list is the builder's task-level contract. The PreToolUse guard blocks role-level
categories, but it cannot inspect the inline prompt or spec to enforce an arbitrary per-task
file list. The builder and reviewer must therefore report and check that list explicitly.

### Prove the input before you dispatch

A wrong contract is not caught by review — it is *implemented*, then reviewed as correct, and
the rework lands two rounds later. Four checks, each cheap, each having caught a real defect:

- **The `Verify` command must be the one that actually gates, and you must have watched it
  fail.** A verify line that already passes cannot detect anything, and a command that skips
  part of the tree reports a false green. Run it yourself before writing it into the brief.
- **Lane 2: type-check the failing test against the signature the spec proposes.** A test you
  cannot even write against the proposed contract *is* the spec error, surfacing for free
  before a builder spends a round on it.
- **Validate any classification or matching rule against real data first, and record the
  counts in the spec.** A rule that reads as obvious in prose can be wrong on the actual rows;
  the count is the evidence, and it belongs where the next reader will see it.
- **State the negative case.** A `Contract` that says only what the code must do produces code
  that is right in the happy path. Write what it must *not* do, and why — that sentence is
  what stops a later change from reintroducing the defect the spec exists to prevent.

## Step 2.5 — architect (opus by default)

Skip this step entirely when `roles.architect.enabled` is `false` — the guard denies the
dispatch, so write the Lane 2 spec and failing tests in this session instead and say so
in one line.

Otherwise dispatch `route:architect`, telling it which **mode** it is in:

- **spec** (the Lane 2 default) — it writes the spec under `paths.specs`, writes the
  failing tests, and runs the `Verify` command to confirm they fail for the stated
  reason. It never writes production code — the guard denies that. You get back the spec
  path, the test paths, and the `Verify` line; pass those to the builder in Step 3.
- **consult** — the shape of the change is not yet decided and the caller (relaying a
  human) wants options first. It writes a `<task>-design.md` under `paths.specs` —
  options, a recommendation, open questions — and stops. Surface the note and its
  `DECISIONS-NEEDED` list to the human; relay their answers back with `SendMessage` to
  the same dispatch. When the design is settled, tell it so and it produces the spec and
  failing tests in that same run. Use this whenever architecture discussion is needed and
  this session is not on the expensive tier; the direct alternative is the human
  switching this session's model for that phase.
- **root-cause** — a bug whose cause is unknown, or a builder that returned `BLOCKERS` on
  two consecutive rounds. It finds the cause, states it, then produces the spec.
- **adjudication** — Step 4/5 left you a reviewer `FAIL` you cannot rule on. See Step 5.

**Do not** dispatch `route:architect` for Lane 0 or a Lane 1 brief. The Step 0.25 dispatch
floor applies to it at the most expensive cold-start cost in the system; a five-line brief
straight to the builder wins every time. Architect writes contracts and design notes, not
briefs.

## Step 3 — build (sonnet by default)

When `roles.builder.enabled` is `false` the guard denies the dispatch and this session
writes the code itself, still against the Step 2 input and the same Verify command.

Otherwise dispatch `route:builder` with **only** its Step 2 input: the Lane 1 brief, or the Lane 2 spec
path plus test path. Never paste a spec file's contents — builder reads the file. Do not
add advice or context; anything extra you say competes with the spec.

Builder's Bash write scope is the same as its `Write`/`Edit` scope: `paths.prod`, or
anything outside the repository. `mkdir`, `mv` and `rm` inside the production paths are
allowed, because no file tool expresses them; a write-shaped command the guard cannot
resolve to a literal path is denied. If builder reports a Bash denial as a blocker, check
the target against `paths.prod` before assuming the spec is at fault.

Independent tasks may go out as parallel `route:builder` calls only when their `Files` lists
are disjoint and they do not share generated state. Otherwise dispatch them sequentially;
parallel builders share a worktree and can overwrite one another.

## Step 4 — review (sonnet by default)

Skip this step entirely when `roles.reviewer.enabled` is `false` — the guard denies the
dispatch, so review it yourself here and say so in one line.

Check `review.policy` in `.claude/route.config.json`:

| policy | behaviour |
| --- | --- |
| `always` | dispatch `route:reviewer` on every builder round |
| `risk` (default) | dispatch when any trigger below fires |
| `never` | never dispatch; the test is the only gate |

**Reviewer has no Bash — it cannot run anything.** Its tools are `Read`, `Glob` and `Grep`
by design. A brief that tells it to run the tests earns a finding about the missing tool
instead of a finding about the code, and does so on every dispatch. **Paste builder's
reported `VERIFY:`, `TESTS:` and `LINT:` lines into the dispatch** and let reviewer judge
them as given.

Under `risk`, dispatch `route:reviewer` when **any** configured trigger is true. The default
trigger IDs are:

1. `no_red_green`: **the change is not fully covered by a test that failed before and passes now.**
   A green suite that never exercised the change proves nothing.
2. `persistent_state`: It touches state that outlives the process — database, filesystem, cache, queue,
   or anything persisted.
3. `authorization`: It touches an authorization or access-control decision.
4. `boundary`: It touches a boundary another system depends on — API shape, wire format, file
   format, CLI flags, public function signatures.
5. `silent_calculation`: It touches a calculation whose wrong answer is **silent**: no exception, just a
   wrong number.
6. `control_flow`: It changes control flow, error handling, concurrency, retry, or timeout behaviour.
7. `builder_blocker`: Builder reported anything under `BLOCKERS`.

**No test suite:** `no_red_green` is true unless the Verify command observes the changed
behaviour and the Boss records what output would have indicated a wrong result. A command
that merely exits successfully, such as a compile-only build, does not count as observed
behaviour.

Under the default trigger set, review is also required when the change touches control
flow, error handling, concurrency, or retry and timeout behaviour; a green run cannot
establish those properties by construction. When a project supplies a custom trigger set,
apply that set and state which configured checks justified a skipped review.

A project may replace this list with the seven trigger IDs in `review.triggers`; an empty list
means no automatic risk trigger. `review.policy=always` still reviews every builder round.

Pass reviewer the brief **or** the spec path, plus builder's reported file list and
`VERIFY:`, `TESTS:`, and `LINT:` lines. Reviewer has no Bash — it reads builder's reported
command and result rather than re-running anything. The Boss must run the final Verify
command again after any review fix before recording. Reviewer returns `PASS`/`FAIL` and
findings, never fixes.

The Boss also writes the change itself to a file **outside the repository** (a temp path — an
untracked diff inside the repo gets committed by accident) and passes reviewer that path.
For edits to tracked files that is `git diff`. For files that are new, say so instead: the
whole file is the change and a diff adds nothing.

On an eight-file change in this project, the changed files came to about 17,800 tokens read
in full against about 2,600 tokens as a diff — 6.8x. Reviewer has no Bash, so without the
diff it reconstructs the change boundary by reading whole files and comparing them against a
prose contract. That is both the larger read and the weaker signal.

If you skip review, say so in one line and name which trigger you checked. A silent
skip is how this step stopped happening.

## Step 5 — adjudicate

The ruling is the main session's — it holds the loop state. Where the call turns on a
design question this session is not sure of, or the spec needs re-deriving, `route:architect`
is the advisor it consults; the main session still decides what to do with the answer.

| Reviewer says | You do |
| --- | --- |
| PASS, no findings | go to step 6 |
| PASS with RISK | record the risk in the project's bug-tracking doc when bookkeeping is enabled; otherwise carry it into the final outcome, then go to step 6 |
| FAIL, 1st time | write a fix instruction naming file + line + required post-condition; resume the builder you already dispatched (in Claude Code, `SendMessage` to that agent) and send only the fix instruction |
| FAIL, 2nd time | **stop dispatching.** The defect is in the spec ~80% of the time. Fix the spec, restart from step 3. If the spec came from `route:architect`, or this session is not on the expensive tier, hand the spec fix back to `route:architect` rather than doing it here |
| FAIL, 3rd time | stop and ask the user. Do not loop |
| FAIL you cannot rule on — the finding turns on a design call this session is not sure of | dispatch `route:architect` in adjudication mode: give it the brief, the reviewer findings, and the out-of-repo diff path, and ask only whether each finding is real and what the minimal fix is. It does not implement. Then act on its ruling |
| reviewer returned no `VERDICT`, or builder returned no report block | treat as truncated, never as PASS; re-dispatch with a narrower `Files` list or split the task |

One session of this project issued 11 subagent dispatches that produced only 6 transcripts,
because the repeat rounds were resumes; each resume skipped the system prompt, tool
definitions and project instructions that Step 0.25 identifies as the flat floor.

Never forward reviewer's raw text to builder. Translate it into an instruction.

**Where a wrong answer is silent, read the diff yourself.** Money arithmetic, tax and fee
splits, authorization decisions, schema migrations, retry logic: a green test only proves
the test agreed with the code, and reviewer sees what the contract told it to look for.
Two defects of exactly this shape survived both gates in one session and were caught by the
main session reading the diff — a retry wrapped around a non-idempotent write, which would
have duplicated records after a dropped response, and an optional parameter with a silent
default that would have applied the wrong rate to a whole class of inputs. Reading a diff
costs context replay on every later turn, so spend it here and nowhere else.

## Step 6 — record (haiku by default)

Skip this step entirely when `bookkeeping.enabled` is `false` — that project keeps no
tracking docs and there is nothing for scribe to write. Skip it too when
`roles.scribe.enabled` is `false`: the project keeps records but does not use scribe, so
write them here.

Otherwise dispatch `route:scribe` with the outcome: task id (or `?`), files changed,
Verify result, test counts when applicable, lint result, reviewer verdict, accepted risks,
the language from `language.artifacts`, and the timezone from `bookkeeping.timezone`.
There is no implicit `version` field; pass one only when the task explicitly defines it.
Do not update the tracking docs yourself — it is mechanical work at the most expensive rate
in the system, and a hook will ask you to reconsider if you try.

**Hand scribe finished prose for anything a human will read later** — a changelog entry, a
release note, a commit-message body. Scribe places text; composing it from notes is
inference, and on a haiku tier that is where it invents file paths, APIs and changes that
never happened. It keeps the file surgery either way, which is the part that actually
replaces main-session turns. The arithmetic favours writing it: a page of prose from this
session costs a fraction of one main turn, while one correction round-trip costs several
*and* the prose still has to be written.

**Cap a dispatch at two tracking files.** A brief spanning every record drives scribe into
its turn ceiling, and each resume replays the whole context again. Two smaller dispatches
cost less than one that has to be resumed.

**What decides is how much bookkeeping there is, not which lane produced it.** Dispatch
scribe when there is real work in the record — several files to list, a risk to write up,
entries to move into an archive, a commit message to compose. Append the line yourself when
the record is one or two lines, whatever the lane. Two projects will behave differently: one
that set `guard.mainSeverity` to `deny` has decided the Boss never writes records, so
dispatch scribe there regardless; one that set it to `off` gets no prompt at all, so write
the line and move on.

On one session of this project a scribe dispatch that appended a short outcome returned a
net context saving of about 260 tokens against a dispatch cost of about 1,230 — it did not
pay for itself, exactly as Step 0.25 predicts for work that fits inside the prompt describing
it.

## Escalate to the main session when

- scout finds multiple plausible owners or an unresolved boundary;
- the requirement conflicts with existing behaviour or a durable project decision;
- a test cannot express the contract without choosing a design;
- builder needs a file outside the spec's `## Files`;
- a reviewer blocker is real but the right resolution is unclear.

## Verify the routing actually happened

Two commands read the transcripts Claude Code already writes and answer it with numbers:

- `/route:audit` — cost per model and per role, main thread and subagents. Read the
  per-role split, not the token columns: one model and zero subagent transcripts means
  nothing was routed, whatever the plan said.
- `/route:delta` — whether each dispatch actually removed net tokens from the main
  session's context, rather than just moving cost to a cheaper model.
