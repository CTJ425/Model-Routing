---
description: View or change which model each route role (scout/builder/reviewer/scribe) uses in this project.
---

Read `.claude/route.config.json` in the project root. If it does not exist, tell the
user to run `/route:init` first — do not fabricate one here.

Show the current `models` mapping.

If arguments were given (`$ARGUMENTS`), parse them as `<role>=<model>` pairs (e.g.
`builder=opus scout=haiku`) and update just those keys. Otherwise ask the user which
role(s) to change and to what model.

Valid roles: `scout`, `builder`, `reviewer`, `scribe`. Accept any model id or alias the
user gives (e.g. `haiku`, `sonnet`, `opus`, or a full model id) — this file only records
the choice, it does not validate it against a live model list.

Write the updated JSON back with the `paths` section unchanged, then show the new
mapping and remind the user the change takes effect on the next dispatch of that role
(the `route` skill reads this file before every dispatch).
