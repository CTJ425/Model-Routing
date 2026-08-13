---
description: Measure whether each subagent dispatch actually removed net tokens from the main session's context, per role.
argument-hint: "[--detail] [--validate]"
---

Run:

```
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/dispatch_delta.py $ARGUMENTS
```

Show the script's output verbatim, including its caveat footer.

Then add two or three sentences of reading, no more:

- Which roles show a positive median net (the dispatch paid for itself in context terms)
  and which do not. A role that is consistently negative is being dispatched for work
  too small to justify the prompt-plus-report it leaves behind.
- The `+net` column against `n`: a role that only sometimes pays off is a briefing
  problem, not a routing problem.
- Do not present `benefit` as a saving. It is an upper bound, as the footer says.

If the project's records or prompts are mostly Chinese, Japanese, or Korean, point out
that the chars-per-token estimate is tuned for English, and that `--validate` reports
the ratio to put in `audit.charsPerToken`.
