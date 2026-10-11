---
description: Hand one bounded implementation task to route:builder — written up as a brief with an exhaustive Files list and a Verify command.
argument-hint: "<the task, plus the files it may touch and the command that proves it done>"
disable-model-invocation: true
---

The user asked for one `route:builder` dispatch:

$ARGUMENTS

Running this command is the user asking for builder by name. It authorizes this one
dispatch, not the rest of the session — that is what `/route:route` does. Reviewer and
scribe are not part of it; suggest them afterwards if the change calls for them.

1. If the request above is empty, ask the user for the task and stop.
2. Read `.claude/route.config.json`. If `roles.builder.enabled` is `false`, the guard
   denies the dispatch: say the role is off and do the work here against the same brief.
3. Write the brief. This session owns it; builder does not design. Five headings:

   ```
   Task: <id, or ?-<short slug>> — <one line>
   Contract: <inputs / outputs / error cases; what must NOT change>
   Files: <exhaustive list of every path builder creates or changes>
   Verify: <the exact command> — not done until this passes
   Non-goals: <what not to do>
   ```

   The guard denies a builder dispatch without a `Files:` line naming at least one path
   and a `Verify:` line, and afterwards denies builder any write outside that list. If
   the request does not let you fill `Files` or `Verify` with confidence, read the code
   or ask the user — do not guess. Run the Verify command yourself first: a command that
   already passes cannot detect anything. A task with a written spec file can pass the
   spec path (and the failing-test path) instead of an inline brief.
4. Dispatch with the Agent tool: `subagent_type: "route:builder"`, `model` set to
   `models.builder` from the config when that key is set (the guard denies a mismatch),
   and a `description` that begins with the Task id. Pass only the brief, plus the prose
   language from `language.artifacts` when it is set.
5. Report builder's `VERIFY:` line and changed files to the user. If the change touches
   persisted state, authorization, a public boundary, a silent calculation, or has no
   red-to-green test, say that it would merit `/route:reviewer`.
