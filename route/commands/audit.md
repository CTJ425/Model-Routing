---
description: Report what this project's Claude Code sessions actually cost, split by model and by role — the evidence for whether routing happened.
argument-hint: "[--all] [--sessions N]"
---

Run:

```
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/routing_audit.py $ARGUMENTS
```

Show the script's output verbatim. Do not recompute, summarise away, or re-format the
tables — the numbers are the point.

Then add two or three sentences of reading, no more:

- Which role spent the most, and whether the main session's share looks like a session
  that routed (bulk of spend off the main session) or one that did not.
- Any line that says subagent transcripts could not be located — that is a "we don't
  know", not a "nothing was routed", and it must not be reported as the latter.
- If models appear under "unpriced", say so: the USD columns exclude them, so the totals
  are a floor.

The USD figures come from `scripts/pricing.json`, which ships with placeholder rates. If
the user has not confirmed those against the official pricing page, say the dollar
columns are indicative and the token columns are exact.
