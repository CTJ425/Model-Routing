---
description: Bootstrap the route plugin's per-project config, and its tracking docs if the project wants them.
argument-hint: "[notes about this project's layout]"
---

Initialize the `route` plugin for the current project. Ask before guessing; a wrong
`paths.prod` makes every guard rule wrong.

## 1. Existing config

If `.claude/route.config.json` exists, read it first.

- It has `"version": 2` — do not overwrite. Report its contents and stop.
- It has no `version` key — it is a v1 file (`paths.prod` + `models` only). **Upgrade it
  in place**: keep every value the user already set, add the v2 keys that are missing,
  and report a short diff of what you added. Never change a value that was already there.

## 2. Ask the two questions that cannot be detected

**Bookkeeping.** Ask: "要不要讓 plugin 幫你維護 `docs/agent/` 下的任務／bug／進度記錄？
不需要的話只保留 model routing。" (Or the same question in the user's language.)

- Yes -> `bookkeeping.enabled: true`, and do step 4.
- No -> `bookkeeping.enabled: false`, skip step 4. The `scribe` role, the record class in
  the guard, and the open-item counts in the session brief all switch off with it.

**Language.** Ask which language the agents should write records and reports in
(`en`, `zh-TW`, or another). Code, identifiers, and commit messages stay English
regardless — only prose follows this setting.

If bookkeeping is on, also ask for the timezone to stamp records with (IANA name, e.g.
`UTC`, `Asia/Taipei`). Default to `UTC` only if the user declines to choose.

## 3. Determine the production-code paths

These are the directories `builder` may write and the main session gets asked about.
Look for signals: a `src/`, `lib/`, `app/`, or `cmd/` directory; a monorepo package
layout; an app-root note in an existing `CLAUDE.md` / `AGENTS.md`.

**If no signal is clear, ask.** Do not guess and do not fall back to `src/` silently.
Show the user what you found and have them confirm or correct it.

**If the repo root contains `packages/`, `apps/`, or `services/`, ask instead of
defaulting.** A default of `["src/"]` denies every builder write in a monorepo. Tell the
user that `paths.prod` entries ending in `/` are directory prefixes, and anything else is
a glob — so `packages/*/src/**` is a valid entry — then have them confirm the paths.

## 4. Tracking docs (only when bookkeeping is on)

Copy the three templates from `${CLAUDE_PLUGIN_ROOT}/templates/records/` into
`docs/agent/`, renaming each to the hot file it backs — the names must match
`bookkeeping.records` in the config, or the guard and the session brief will look in the
wrong place:

| Template | Becomes |
| --- | --- |
| `tasks.md.tmpl` | `docs/agent/TASK.md` |
| `bugs.md.tmpl` | `docs/agent/BUG_FIX.md` |
| `progress.md.tmpl` | `docs/agent/PROGRESS.md` |

Do not copy `templates/records/README.md` — it documents the templates for the plugin,
not for the project. Create `docs/agent/specs/` as well. The archives
(`TASK_ARCHIVE.md`, `FIXED_BUG.md`, `PROGRESS_ARCHIVE.md`) are not created here; `scribe`
creates each on first use.

If a target file already exists, leave it untouched and report that. The templates are
starting points the project then owns; a plugin update never rewrites them.

## 5. Write the config

Write `.claude/route.config.json` (create `.claude/` if needed). Include only the keys
this project actually needs — every unset key falls back to the plugin's default:

```json
{
  "$schema": "${CLAUDE_PLUGIN_ROOT}/schema/route.config.schema.json",
  "version": 2,
  "paths": { "prod": ["<confirmed-path>/"] },
  "models": { "scout": "haiku", "builder": "sonnet", "reviewer": "sonnet", "scribe": "haiku" },
  "bookkeeping": { "enabled": true, "timezone": "<confirmed-timezone>" },
  "language": { "artifacts": "<confirmed-language>" },
  "review": { "policy": "risk" }
}
```

## 6. Permissions allowlist (starter)

If the project uses `.claude/settings.json` or runs in automated/worktree harnesses, provide or suggest
starter permission rules allowing read-only `git` commands (`git status`, `git log`, `git diff`)
and memory directory writes, ensuring unattended runs are not interrupted by benign queries.

## 7. Ignore the runtime state directory

Add `.claude/routing/` to this project's `.gitignore` — it holds per-session counters and
the dispatch log, which are machine-local. If the line is already there, skip it and say
so. If there is no `.gitignore`, create one with that single line.

## 8. Report

State what was created, what already existed, and that `/route:config` changes the
per-role model tiers later. If `CLAUDE_CODE_SUBAGENT_MODEL` is set in the environment,
say that it outranks the `models` block and those tiers will not take effect until it is
unset.

$ARGUMENTS
