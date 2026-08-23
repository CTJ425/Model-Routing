---
description: Self-check whether the route plugin is actually live in this project — hooks wired up, config parses, configured paths match real files.
---

Run:

```
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/routing_doctor.py
```

Show the output verbatim. Do not recompute, summarise away, or re-order the checks.

Then add one or two sentences of reading, no more: a FAIL on `hooks` or `interpreter`
means no guard in this project is being enforced at all — routing is not happening
regardless of what any other check says, and everything else is secondary until that
line reads PASS. Every other WARN or FAIL is a configuration gap to close, not a sign
that enforcement itself is absent.
