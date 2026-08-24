# Fixed bugs

Fixed bugs, archived from `BUG_FIX.md`. Newest entry at the top; nothing is deleted here.

### Bug ?: builder checkout of files outside Files list

- **Date**: 2026-08-24 09:13:07 CST
- **Symptom**: builder ran `git checkout -- README.md` on a file outside its Files list and destroyed deliberate caller work
- **Repro**: ?
- **Root Cause**: the "Modify only the files in its Files list" rule never said that reverting counts as modifying, so restoring a file to its committed state did not read as a violation
- **Status**: ✅ FIXED
