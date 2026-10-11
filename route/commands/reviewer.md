---
description: Hand one change to route:reviewer for a findings-only review against its brief or spec.
argument-hint: "<what to review: the changed files or diff range, and the intent or spec path>"
disable-model-invocation: true
---

The user asked for one `route:reviewer` dispatch:

$ARGUMENTS

Running this command is the user asking for reviewer by name. It authorizes this one
dispatch, not the rest of the session — that is what `/route:route` does.

1. Read `.claude/route.config.json`. If `roles.reviewer.enabled` is `false`, the guard
   denies the dispatch: say the role is off and review the change here.
2. Gather reviewer's input:
   - **Changed files.** From the last builder report in this session, or from what the
     user named; failing both, from `git diff --name-only` against the range the user
     gave (default: the working tree against `HEAD`). If there is nothing to review,
     say so and stop.
   - **The diff.** Reviewer cannot run `git` or read its objects, so it sees only the
     files as they are now. Paste `git diff` for those files into the prompt; when it
     runs past a few hundred lines, give the changed line ranges per file instead.
   - **The contract.** The brief or spec path the change was built from. When there is
     none, write a short brief yourself from the user's request: what the change is
     meant to do and what it must not change.
   - **Evidence.** Reviewer has only `Read`, `Glob` and `Grep` and cannot run anything.
     Paste builder's `VERIFY:`, `TESTS:` and `LINT:` lines, or the output of the test
     command if you ran one; never ask reviewer to run tests.
3. Dispatch with the Agent tool: `subagent_type: "route:reviewer"`, and `model` set to
   `models.reviewer` from the config when that key is set (the guard denies a mismatch).
   Add the prose language from `language.artifacts` when it is set.
4. Relay the findings to the user as reviewer returned them. Adjudicating them — which to
   accept, which to fix — is this session's job, not reviewer's; give your verdict on
   each one in a line.
