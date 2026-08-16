---
description: View or change this project's route settings — per-role model tiers, review policy, guard thresholds.
argument-hint: "[builder=opus] [review.policy=always] [guard.readKB=64]"
---

Read `.claude/route.config.json` in the project root. If it does not exist, tell the user
to run `/route:init` first — do not fabricate one here.

## Before showing anything

Check whether `CLAUDE_CODE_SUBAGENT_MODEL` is set in the environment (`echo
$CLAUDE_CODE_SUBAGENT_MODEL`). If it is, lead with this warning:

> `CLAUDE_CODE_SUBAGENT_MODEL=<value>` is set. It outranks the per-dispatch `model`
> parameter, so every subagent runs on that model and the `models` block below has no
> effect until the variable is unset.

Report it as fact, not as a suggestion to unset it.

## Showing

Print the current `models` mapping, `review.policy`, bookkeeping enabled/disabled state,
`language.artifacts`, and any non-default `guard` values. Do not dump the whole file.

## Changing

Parse `$ARGUMENTS` as `key=value` pairs and update just those keys:

- A bare role name is shorthand for the model tier: `builder=opus` sets
  `models.builder`. Valid roles: `scout`, `builder`, `reviewer`, `scribe`. Any model
  alias or full model id is accepted — this file records the choice, it does not
  validate it against a live model list.
- A dotted key sets that path directly: `review.policy=always`, `guard.readKB=64`,
  `guard.mainSeverity=deny`, `bookkeeping.enabled=false`, `scout.enabled=false`,
  `audit.charsPerToken=1.6`. Coerce `true`/`false` and numeric values to their JSON
  types, not strings.
- For array values, accept a JSON array literal, for example
  `review.triggers=["boundary","control_flow"]`, and validate each trigger against the
  schema before writing it.
- Reject a dotted key that is not in `${CLAUDE_PLUGIN_ROOT}/schema/route.config.schema.json`
  and say which keys are valid, rather than writing a key nothing reads.

## Interactive (no arguments)

After showing the current values, drive the choice with `AskUserQuestion` instead of a
free-form question:

1. Ask which of the four roles to change, multi-select, one option per role:
   - `scout` — "reads and compresses; can be turned off"
   - `builder` — "implements; cannot be turned off, it is the plugin itself" — offer it
     only for a model-tier change, never an on/off choice
   - `reviewer` — "checks risk work; off = review.policy=never"
   - `scribe` — "records outcomes; off = bookkeeping.enabled=false"
   Include a fifth option for settings that are not per-role: `guard.*` thresholds and
   `language.artifacts`.
2. For each role picked in step 1 (except when only the fifth option was picked), ask
   its model tier in one follow-up question per role (or a single call with one question
   per role, up to the 4-question limit).
3. For each role picked, ask its second dimension:
   - `scout` → enabled true/false → writes `scout.enabled`
   - `reviewer` → policy always/risk/never → writes `review.policy`
   - `scribe` → enabled true/false → writes `bookkeeping.enabled`
   - `builder` → skip, it has no second dimension
4. If the fifth option was picked, ask for the specific `guard.*` key/value or
   `language.artifacts` value.

Write back only the keys the user actually changed; every other key stays byte-identical,
same as the `key=value` path. Report the new values the same way that path does.

Write the file back with every other key unchanged and the same formatting, then show the
new values. Model changes take effect on the next dispatch of that role; guard and
review changes take effect immediately, since the hooks re-read the file on every call.
