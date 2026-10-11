---
description: Hand one bookkeeping job to route:scribe — record an outcome in the tracking docs or compose a commit message.
argument-hint: "<what to record, and where; or 'commit message' for the staged change>"
disable-model-invocation: true
---

The user asked for one `route:scribe` dispatch:

$ARGUMENTS

Running this command is the user asking for scribe by name. It authorizes this one
dispatch, not the rest of the session — that is what `/route:route` does.

1. If the request above is empty, ask the user what to record and stop.
2. Read `.claude/route.config.json`. If `roles.scribe.enabled` is `false`, the guard
   denies the dispatch: say the role is off and write the record here. If the job is a
   tracking-doc record and `bookkeeping.enabled` is `false`, the project keeps no
   records: say so and stop.
3. Write the prompt. Scribe places text and does not search:
   - Name every destination path and the exact heading or anchor line to write against
     (the hot files are under `paths.docs` as named in `bookkeeping.records`). For a move
     to an archive, name the entry headings and the `--keep` value for `roll_records.py`.
   - At most two tracking files per dispatch; split a larger job.
   - The outcome: task id (or `?`), files changed, Verify result, test counts, reviewer
     verdict, accepted risks — whatever applies.
   - Finished prose for anything a human will read later (a changelog entry, a commit
     body). Scribe on a cheap tier invents details when it composes from notes.
   - The language from `language.artifacts` and the timezone from
     `bookkeeping.timezone`, when they are set.
4. Dispatch with the Agent tool: `subagent_type: "route:scribe"`, and `model` set to
   `models.scribe` from the config when that key is set (the guard denies a mismatch).
5. Report what scribe wrote, file by file.
