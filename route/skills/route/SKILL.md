---
name: route
description: Run a task through the model-routing loop — classify it into a lane, dispatch scout/builder/reviewer/scribe at their own model tiers, and verify. Use when starting a feature, fixing a bug, working through a tracking doc's open items, or when the user says "route this", "run the next task", or asks why everything is running on the most expensive model.
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
| **2 — elevated risk** | Unknown-cause bug, cross-module change, or any of the Step 4 triggers known up front: persisted state, authorization, a boundary, a silent calculation, control-flow behaviour, or a builder blocker | `route:scout` -> spec + failing tests -> `route:builder` -> `route:reviewer` (always) -> adjudicate -> `route:scribe` |

State the lane in one line before you act. If you pick Lane 0 for a tracked task,
record why in the project's progress log.

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

## Step 0.5 — model overrides

Before every dispatch in Steps 1, 3, 4 and 6, check the project root for
`.claude/route.config.json`:

```json
{
  "version": 2,
  "paths": { "prod": ["src/"] },
  "models": { "scout": "haiku", "builder": "sonnet", "reviewer": "sonnet", "scribe": "haiku" },
  "scout": { "enabled": true },
  "review": { "policy": "risk" },
  "bookkeeping": { "enabled": true }
}
```

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

Skip this step entirely when `scout.enabled` is `false` in `.claude/route.config.json`
— go straight to the next step with what you already know. Otherwise: only when the
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

## Step 2 — the builder's input, sized by lane

The main session owns this. Specs, failing tests, and adjudication do not get delegated —
they are the reason this session runs on the expensive model.

**Lane 1 — a brief, in the dispatch prompt. No file.** A spec file for a bounded fix is
overhead that does not pay for itself. Five headings, inline:

```
Task: <id> — <one line>
Contract: <inputs / outputs / error cases; what must NOT change>
Files: src/...   <- exhaustive; you may touch nothing else
Verify: <the exact command> — not done until this passes
Non-goals: <what not to do>
```

**Lane 2 — a spec file plus failing tests.** Write the spec with the same five sections
expanded, add a `## Test charter` table (`| Case | Expected outcome | Layer / file |`),
and write the failing tests **before** dispatching. Pass builder the spec path and the
test path only.

The `Files` list is the builder's task-level contract. The PreToolUse guard blocks role-level
categories, but it cannot inspect the inline prompt or spec to enforce an arbitrary per-task
file list. The builder and reviewer must therefore report and check that list explicitly.

## Step 3 — build (sonnet by default)

Dispatch `route:builder` with **only** its Step 2 input: the Lane 1 brief, or the Lane 2 spec
path plus test path. Never paste a spec file's contents — builder reads the file. Do not
add advice or context; anything extra you say competes with the spec.

Independent tasks may go out as parallel `route:builder` calls only when their `Files` lists
are disjoint and they do not share generated state. Otherwise dispatch them sequentially;
parallel builders share a worktree and can overwrite one another.

## Step 4 — review (sonnet by default)

Check `review.policy` in `.claude/route.config.json`:

| policy | behaviour |
| --- | --- |
| `always` | dispatch `route:reviewer` on every builder round |
| `risk` (default) | dispatch when any trigger below fires |
| `never` | never dispatch; the test is the only gate |

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

If you skip review, say so in one line and name which trigger you checked. A silent
skip is how this step stopped happening.

## Step 5 — adjudicate (main session only)

| Reviewer says | You do |
| --- | --- |
| PASS, no findings | go to step 6 |
| PASS with RISK | record the risk in the project's bug-tracking doc when bookkeeping is enabled; otherwise carry it into the final outcome, then go to step 6 |
| FAIL, 1st time | write a fix instruction naming file + line + required post-condition; re-dispatch `route:builder` |
| FAIL, 2nd time | **stop dispatching.** The defect is in the spec ~80% of the time. Fix the spec, restart from step 3 |
| FAIL, 3rd time | stop and ask the user. Do not loop |

Never forward reviewer's raw text to builder. Translate it into an instruction.

## Step 6 — record (haiku by default)

Skip this step entirely when `bookkeeping.enabled` is `false` — that project keeps no
tracking docs and there is nothing for scribe to write.

Otherwise dispatch `route:scribe` with the outcome: task id (or `?`), files changed,
Verify result, test counts when applicable, lint result, reviewer verdict, accepted risks,
the language from `language.artifacts`, and the timezone from `bookkeeping.timezone`.
There is no implicit `version` field; pass one only when the task explicitly defines it.
Do not update the tracking docs yourself — it is mechanical work at the most expensive rate
in the system, and a hook will ask you to reconsider if you try.

**Lane 0 is the exception.** A one-line record for work you did inline sits below the
dispatch floor (Step 0.25) — a scribe cold start costs several times what the line is
worth. Append it yourself and confirm the guard's `ask`. Two projects will behave
differently: one that set `guard.mainSeverity` to `deny` has decided the Boss never writes
records, so dispatch scribe there instead; one that set it to `off` gets no prompt at all,
so write the line and move on. From Lane 1 and Lane 2, always dispatch scribe — there is a
real outcome to write up.

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
