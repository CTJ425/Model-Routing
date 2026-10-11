---
description: Hand one question to route:scout — read-only codebase mapping or log compression on scout's own model tier.
argument-hint: "<one specific question, with the directories, globs, or line ranges to search>"
disable-model-invocation: true
---

The user asked for one `route:scout` dispatch:

$ARGUMENTS

Running this command is the user asking for scout by name. It authorizes this one
dispatch, not the rest of the session — that is what `/route:route` does.

1. If the request above is empty, ask the user for the question and stop.
2. Read `.claude/route.config.json`. If `roles.scout.enabled` (or the legacy
   `scout.enabled`) is `false`, the guard denies the dispatch: say the role is off and
   answer the question here instead.
3. Write the prompt. One question per dispatch; if the request holds several, send one
   scout per question in parallel. Name the directories or globs scout may search, and
   any line ranges already known — scout has 80 turns and no Bash. If the material to
   compress is command output, put it in the prompt or write it to a file and pass the
   path. Add the prose language from `language.artifacts` when it is set.
4. Dispatch with the Agent tool: `subagent_type: "route:scout"`, and `model` set to
   `models.scout` from the config when that key is set (the guard denies a mismatch).
5. Relay scout's answer to the user. If it comes back with `NOT ANSWERED:` or cut off,
   resume it once with `SendMessage` rather than re-dispatching cold.
