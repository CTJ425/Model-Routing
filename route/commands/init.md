---
description: Bootstrap the route plugin's tracking docs and per-project config in this repo.
---

Initialize the `route` plugin for the current project.

1. Create `docs/agent/` if it does not already exist, with skeleton files:
   `PROGRESS.md`, `TASK.md`, `BUG_FIX.md`, `FIXED_BUG.md`, `CHANGELOG.md`. Each skeleton
   is just a one-line header stating the file's purpose — do not invent example content.
   If any of these files already exist, leave them untouched and report that.

2. Determine this project's production-code path(s) — the directories `builder` is
   allowed to write to and the main session is not. Look for signals first (a `src/`
   directory, an app-root note in an existing `CLAUDE.md`/`AGENTS.md`, a monorepo
   package layout). If it is not obvious, ask the user rather than guessing.

3. Write `.claude/route.config.json` (create the `.claude/` directory if needed):
   ```json
   {
     "paths": { "prod": ["<detected-or-confirmed-path>/"] },
     "models": { "scout": "haiku", "builder": "sonnet", "reviewer": "sonnet", "scribe": "haiku" }
   }
   ```
   If `.claude/route.config.json` already exists, do not overwrite it — report its
   current contents instead and stop.

4. Report what was created (or what already existed) and mention that `/route:config`
   changes the per-role model tiers later.

$ARGUMENTS
