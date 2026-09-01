---
description: View or change this project's route settings — which roles are on, per-role model tiers, review policy, guard thresholds.
argument-hint: "[builder=opus] [roles.scribe.enabled=false] [review.policy=always] [guard.readKB=64]"
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

Print which of the five roles are on (`roles.<role>.enabled`, default true), the current
`models` mapping, `review.policy`, bookkeeping enabled/disabled state,
`language.artifacts`, and any non-default `guard` values. Do not dump the whole file.

A role reported as off is denied by the guard, not merely discouraged: dispatching it
returns a `deny`. Say that when reporting an off role, so the state is not mistaken for a
suggestion.

## Changing

Parse `$ARGUMENTS` as `key=value` pairs and update just those keys:

- A bare role name is shorthand for the model tier: `builder=opus` sets
  `models.builder`. Valid roles: `scout`, `architect`, `builder`, `reviewer`, `scribe`.
  Any model alias or full model id is accepted — this file records the choice, it does
  not validate it against a live model list.
- A dotted key sets that path directly: `roles.scribe.enabled=false`,
  `review.policy=always`, `guard.readKB=64`, `guard.mainSeverity=deny`,
  `bookkeeping.enabled=false`, `audit.charsPerToken=1.6`. Coerce `true`/`false` and
  numeric values to their JSON types, not strings.
- `roles.<role>.enabled=false` turns a role off for this project. All five roles may be
  turned off, `builder` included. Write `roles.scout.enabled` rather than the legacy
  `scout.enabled`; the old key still loads, and the new one wins when both are present.
  When turning a role off, state in one line what the loop does instead — this session
  absorbs that step's work.
- For array values, accept a JSON array literal, for example
  `review.triggers=["boundary","control_flow"]`, and validate each trigger against the
  schema before writing it.
- Reject a dotted key that is not in `${CLAUDE_PLUGIN_ROOT}/schema/route.config.schema.json`
  and say which keys are valid, rather than writing a key nothing reads.

## Interactive (no arguments)

After showing the current values, drive the choice with `AskUserQuestion` instead of a
free-form question:

1. Ask which of the five roles to change, multi-select, one option per role:
   - `scout` — "reads and compresses"
   - `architect` — "discusses architecture, writes the Lane 2 spec, root-causes hard bugs"
   - `builder` — "implements"
   - `reviewer` — "checks risk work"
   - `scribe` — "records outcomes"
   Include a further option for settings that are not per-role: `guard.*` thresholds and
   `language.artifacts`.
2. For each role picked in step 1 (except when only the non-per-role option was picked),
   ask its model tier in one follow-up question per role (batch into calls of at most 4
   questions; make more than one call if the user picked more than 4 roles).
3. For each role picked, ask whether the role is on or off → writes
   `roles.<role>.enabled`. Off means the guard denies the dispatch, so name what absorbs
   the work: for `architect`, `builder` and `reviewer` that is this session; for
   `scribe`, this session writes the records unless the user also wants
   `bookkeeping.enabled=false`; for `scout`, discovery happens in this session under the
   `guard.readKB` ceiling.
   For `reviewer`, also ask its policy always/risk/never → writes `review.policy`. That
   is a separate axis: `never` means review is not required, while
   `roles.reviewer.enabled=false` means the reviewer cannot run at all.
4. If the non-per-role option was picked, ask for the specific `guard.*` key/value or
   `language.artifacts` value.

Write back only the keys the user actually changed; every other key stays byte-identical,
same as the `key=value` path. Report the new values the same way that path does.

Write the file back with every other key unchanged and the same formatting, then show the
new values. Model changes take effect on the next dispatch of that role; guard and
review changes take effect immediately, since the hooks re-read the file on every call.
