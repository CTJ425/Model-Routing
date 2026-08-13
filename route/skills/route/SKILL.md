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
| **0 — inline** | The content is **already in context** and the edit is surgical — a typo, a version bump, a one-line fix. Touches no money/auth/schema/API/deploy behaviour, and you can name the verification command *before* editing | main session -> verify -> `scribe` if a record is owed |
| **1 — bounded** (default) | A clear fix or feature inside known modules | `scout` (if the area is unmapped) -> spec -> `builder` -> `reviewer` -> `scribe` |
| **2 — elevated risk** | Unknown-cause bug, cross-module change, money/auth/schema-touching maths, RLS, a migration, an external API, a cron/background job, or anything deployed | `scout` -> spec + failing tests -> `builder` -> `reviewer` -> adjudicate -> `scribe` |

State the lane in one line before you act. If you pick Lane 0 for a tracked task,
record why in the project's progress log.

## Step 0.5 — model overrides

Before every dispatch in Steps 1, 3, 4 and 6, check the project root for
`.claude/route.config.json`:

```json
{
  "paths": { "prod": ["src/"] },
  "models": { "scout": "haiku", "builder": "sonnet", "reviewer": "sonnet", "scribe": "haiku" }
}
```

If `models.<role>` is set for the role you are about to dispatch, pass it explicitly as
the `model` parameter on the Agent call — this takes precedence over the agent file's own
frontmatter `model:` and lets a project change tiers without editing plugin files that a
plugin update would overwrite. If the file or the key is missing, dispatch with no
`model` override and let the agent's frontmatter default apply. `/route:config` is how a
user edits this file; never hand-edit an agent's frontmatter to change its tier.

## Step 1 — scout (haiku by default)

Only when the affected area is not already mapped. Ask a specific question — never
"look at the report pipeline", always "where is X chosen, who calls it, which tests cover
it". You get back ~40 lines. This is the single largest token saving in the system.

If you have made a dozen Read/Grep calls yourself, you are doing scout's work at several
times the price; a hook will tell you so.

Do not reach for the built-in `Explore` or `general-purpose` instead. They inherit the
caller's model, so they do scout's job at the caller's price. A PreToolUse guard asks
before letting one through; confirm only when you need a tool scout lacks.

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

Either way the `Files` list is what makes builder's scope enforceable — a PreToolUse
guard already blocks builder from tests, specs, and records, but only this list bounds
which production files it may touch.

## Step 3 — build (sonnet by default)

Dispatch `builder` with **only** its Step 2 input: the Lane 1 brief, or the Lane 2 spec
path plus test path. Never paste a spec file's contents — builder reads the file. Do not
add advice or context; anything extra you say competes with the spec.

Independent tasks go out as parallel `builder` calls in one turn, not sequential rounds.

## Step 4 — review (sonnet by default)

**The gate for ordinary work is the test passing**, not a second opinion — it is
verifiable, costs nothing extra, and builder is required to report the command and its
output. Take that as the pass and go to step 6.

**Dispatch `reviewer` when the change touches money, positions, fees, prices, auth/RLS,
persistence, schema, API contracts, background jobs, or a user-visible calculation** —
there a green test only proves the test agreed with the bug. Pass it the brief or spec
path and builder's reported file list; it returns `PASS`/`FAIL` and findings, never
fixes.

## Step 5 — adjudicate (main session only)

| Reviewer says | You do |
| --- | --- |
| PASS, no findings | go to step 6 |
| PASS with RISK | record the risk in the project's bug-tracking doc, go to step 6 |
| FAIL, 1st time | write a fix instruction naming file + line + required post-condition; re-dispatch `builder` |
| FAIL, 2nd time | **stop dispatching.** The defect is in the spec ~80% of the time. Fix the spec, restart from step 3 |
| FAIL, 3rd time | stop and ask the user. Do not loop |

Never forward reviewer's raw text to builder. Translate it into an instruction.

## Step 6 — record (haiku by default)

Dispatch `scribe` with the outcome: task id, files changed, test counts, reviewer
verdict, accepted risks, version. Do not update the tracking docs yourself — it is
mechanical work at the most expensive rate in the system, and a hook will ask you to
reconsider if you try.

## Escalate to the main session when

- scout finds multiple plausible owners or an unresolved boundary;
- the requirement conflicts with existing behaviour or a durable project decision;
- a test cannot express the contract without choosing a design;
- builder needs a file outside the spec's `## Files`;
- a reviewer blocker is real but the right resolution is unclear.

## Verify the routing actually happened

This plugin ships `routing_audit.py` and `dispatch_delta.py` under its own `hooks/`
directory. They read the transcripts Claude Code already writes and report **cost** per
model and per role — main thread and sidechain — plus whether a dispatch actually removed
net tokens from the main session's context. Find the installed copy under this plugin's
directory (list plugins, or look under `~/.claude/plugins/`) and run it with `python3`.
Read the per-role split, not the token columns: one model and zero sidechain traffic
means nothing was routed, whatever the plan said.
