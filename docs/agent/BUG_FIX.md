# Open bugs

Open bugs only. A fixed bug moves to `FIXED_BUG.md`; nothing is deleted here.

## 🐛 Open

<!--
The session brief counts every `### ` heading in this file as an open bug, so keep fixed
ones out of it.
-->

### SKILL.md Task-id rule has no source under Lane 2 or with builder off

Found 2026-09-23 (T4 review). Step 3 says the brief's first line is `Task: <id>`, but Lane 2 passes builder "only" the spec path and test path, so there is no brief line to carry it; the round records as `(untagged)`. Step 4 copies the id from "that round's builder brief", which does not exist when `roles.builder.enabled` is `false`. Fix: state where the id goes in both cases.

### by-task and by-role totals can count one agent transcript twice

Found 2026-09-23 (T3 review). `dispatch_log()` deduplicates by agent path, but nothing deduplicates between the log and the `subagents/` glob fallback, or across sessions. With `--all`, a session with no logged rows globs its `subagents/` directory, and a transcript the log already attributes to another main transcript (resumed or forked session) is counted again. Pre-existing in the by-role table; `--by-task` inherits it.

### by-task USD has no marker for unpriced models

Found 2026-09-23 (T3 review). A task whose subagents used an unpriced model shows USD `0.00` or an understated total; the per-session table prints `—` and the by-model footer lists exclusions, but the by-task row does not. No current model is unpriced.

### task_identity() aborts a transcript on a non-dict origin

Found 2026-09-23 (T2 review). `(row.get("origin") or {}).get("kind")` raises AttributeError if a user entry has a truthy non-dict `origin`; only `json.loads` is inside the try. All real `origin` values seen are dicts.
