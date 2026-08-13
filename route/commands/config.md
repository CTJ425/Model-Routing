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

Print the current `models` mapping, plus `review.policy` and any non-default `guard`
values. Do not dump the whole file.

## Changing

Parse `$ARGUMENTS` as `key=value` pairs and update just those keys:

- A bare role name is shorthand for the model tier: `builder=opus` sets
  `models.builder`. Valid roles: `scout`, `builder`, `reviewer`, `scribe`. Any model
  alias or full model id is accepted — this file records the choice, it does not
  validate it against a live model list.
- A dotted key sets that path directly: `review.policy=always`, `guard.readKB=64`,
  `guard.mainSeverity=deny`, `bookkeeping.enabled=false`, `audit.charsPerToken=1.6`.
  Coerce `true`/`false` and numeric values to their JSON types, not strings.
- Reject a dotted key that is not in `${CLAUDE_PLUGIN_ROOT}/schema/route.config.schema.json`
  and say which keys are valid, rather than writing a key nothing reads.

With no arguments, ask which setting to change and to what.

Write the file back with every other key unchanged and the same formatting, then show the
new values. Model changes take effect on the next dispatch of that role; guard and
review changes take effect immediately, since the hooks re-read the file on every call.
