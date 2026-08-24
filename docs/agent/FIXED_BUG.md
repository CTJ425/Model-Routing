# Fixed bugs

Fixed bugs, archived from `BUG_FIX.md`. Newest entry at the top; nothing is deleted here.

### Bug: scribe loses a record when rolling it into a large archive

- **Date**: 2026-08-24 11:25:00 CST
- **Symptom**: `scribe` deleted a 14-line entry from `PROGRESS.md` without prepending it to `PROGRESS_ARCHIVE.md`, then stopped. The record existed in neither file.
- **Root Cause**: Delete-then-insert ordering and reasoning-based surgery against large archive files.
- **Fix**: Added `route/scripts/roll_records.py` with insert-before-delete verification, updated `scribe.md` to require `roll_records.py`, mandated insert-before-delete, and forbade whole-file rewrites.
- **Status**: ✅ FIXED

### Bug: Step-4 review hook fires on dispatch instead of on completion

- **Date**: 2026-08-24 11:25:00 CST
- **Symptom**: PostToolUse hook fired on async agent launch acknowledgement before the builder actually ran.
- **Root Cause**: Hook did not check for async launch acknowledgement in tool result.
- **Fix**: Added `is_async_launch` check in `routing_observe.py` to suppress review nudge on async launch responses.
- **Status**: ✅ FIXED

### Bug: builder reports PASS against a VERIFY command it modified

- **Date**: 2026-08-24 11:25:00 CST
- **Symptom**: builder ran modified VERIFY command with `--exclude` and reported PASS.
- **Root Cause**: `builder.md` did not mandate literal execution of VERIFY.
- **Fix**: Mandated in `builder.md` that VERIFY commands must be executed verbatim without modification, and forbidden reporting PASS against modified commands.
- **Status**: ✅ FIXED

### Bug: worktree guard refuses compound commands that never touch the repository

- **Date**: 2026-08-24 11:25:00 CST
- **Symptom**: Commands in worktrees rejected due to text complexity.
- **Root Cause**: Missing starter permissions and syntax-based rejection.
- **Fix**: Added starter permissions allowlist in `/route:init` for read-only git and safe project paths.
- **Status**: ✅ FIXED

### Bug: scout speculates about design in a read-only mapping dispatch

- **Date**: 2026-08-24 11:25:00 CST
- **Symptom**: scout opened mapping with `ASSUMPTIONS` proposing future architectures and data models.
- **Root Cause**: `scout.md` lacked explicit prohibition against design speculation.
- **Fix**: Added explicit rule in `scout.md` forbidding intent inference, feature extrapolation, or design proposals.
- **Status**: ✅ FIXED

### Bug ?: builder checkout of files outside Files list

- **Date**: 2026-08-24 09:13:07 CST
- **Symptom**: builder ran `git checkout -- README.md` on a file outside its Files list and destroyed deliberate caller work
- **Repro**: ?
- **Root Cause**: the "Modify only the files in its Files list" rule never said that reverting counts as modifying, so restoring a file to its committed state did not read as a violation
- **Status**: ✅ FIXED
