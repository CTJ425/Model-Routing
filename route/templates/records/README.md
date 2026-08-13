# Record templates

`/route:init` copies these into the target project's `docs/agent/` (dropping the `.tmpl`
suffix) when the user turns bookkeeping on. After that they belong to the project: edit
them freely, rename the headings, change the emoji, add fields. A plugin update never
touches a file that already exists.

The plugin reads only three things out of these files, all configurable in
`.claude/route.config.json`:

| What | Config key | Default |
| --- | --- | --- |
| Which directory holds them | `paths.docs` | `docs/agent` |
| Which file is hot and which is its archive | `bookkeeping.records` | see `_config.py` |
| Which task entries count as open | `bookkeeping.openTaskPattern` | a `- **Status**:` line not starting with ✅ |

If you change an entry format here in a way that breaks the open-task count — a different
status marker, a different heading level — update `bookkeeping.openTaskPattern` to match.
Entries are separated by `### ` headings; the counting logic assumes that much.

The archives (`TASK_ARCHIVE.md`, `FIXED_BUG.md`, `PROGRESS_ARCHIVE.md`) are created on
first use by `scribe`, not copied from here — they start empty and only ever grow.
