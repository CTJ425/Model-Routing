# route

A Claude Code plugin marketplace with one plugin, `route`: a model-routing loop that
keeps the expensive model out of mechanical work. The Boss runs in your main session;
four subagents do everything else.

| Role | Where it runs | Default model | Owns | Must never |
|---|---|---|---|---|
| **Boss** | the main thread | your session model | routing, sequencing, specs, adjudication | write production code or a tracking record |
| **scout** | subagent | haiku | mapping the codebase, compressing logs/stack traces | write anything, or run commands |
| **builder** | subagent | sonnet | implementing an existing spec | touch tests, specs, or tracking docs |
| **reviewer** | subagent | sonnet | reviewing a builder's diff against its spec | fix anything, propose a fix, or run commands |
| **scribe** | subagent | haiku | recording outcomes into the tracking docs | write production code |

Role boundaries are enforced by `PreToolUse` hooks where the path and role are
classifiable. The hook cannot inspect an inline brief's per-task `Files` list, Bash is
best-effort for roles that have Bash, and all hooks fail open on malformed input.

## Requirements

Python 3.8 or newer, with `python3` on `PATH`. No third-party packages — the hooks import
only the standard library.

## Install

```
/plugin marketplace add CTJ425/Model-Routing
/plugin install route@route
```

Then, in any target repo:

```
/route:init      # ask a few questions, write .claude/route.config.json
/route:config    # view or change which model each role uses in this project
```

## The loop

```
Boss classifies the lane -> scout (if unmapped) -> Boss writes spec/brief
  -> builder -> reviewer (per review policy) -> Boss adjudicates -> scribe records
```

Load the `route` skill (or just start a feature or bug — the SessionStart hook reminds
the session it delegates) and it walks this loop step by step, including when to skip a
step for a small change.

## Per-project configuration

Each project gets its own `.claude/route.config.json`. Every key is optional; the hooks
deep-merge it over their defaults, and `schema/route.config.schema.json` documents the
full shape.

```json
{
  "version": 2,
  "paths": { "prod": ["src/"] },
  "models": { "scout": "haiku", "builder": "sonnet", "reviewer": "sonnet", "scribe": "haiku" },
  "bookkeeping": { "enabled": true, "timezone": "UTC" },
  "review": { "policy": "risk" }
}
```

- `paths.prod` — repo-relative prefixes and globs the guard treats as production code.
- `models.<role>` — overrides that role's agent-file default for this project only,
  passed as a per-dispatch model override. Editing this file never touches the plugin's
  own `agents/*.md`, so a plugin update cannot silently undo a project's tuning. Note
  that the `CLAUDE_CODE_SUBAGENT_MODEL` environment variable, if set, outranks it.
- `bookkeeping.enabled` — set `false` for model routing only: no `scribe`, no tracking
  docs, no record rules in the guard.
- `review.policy` — the Boss's review-routing policy: `always`, `risk` (default), or
  `never`. The PostToolUse nudge makes a required review visible but does not itself block
  a user or model that ignores it.
- `review.triggers` — optional IDs replacing the default risk checks:
  `no_red_green`, `persistent_state`, `authorization`, `boundary`,
  `silent_calculation`, `control_flow`, and `builder_blocker`.

`/route:init` writes the initial file; `/route:config` edits it.

## Verifying it actually routed

```
/route:audit     # cost per model and per role, main thread and subagents
/route:delta     # whether each dispatch removed net tokens from main's context
```

Both read the transcripts Claude Code already writes. Read the per-role split, not the
token columns: one model and zero subagent transcripts means nothing was routed, whatever
the plan said. The USD columns come from `route/scripts/pricing.json`, which ships with
placeholder rates — check them against the official pricing page before quoting a number.

## What this does NOT enforce

- **Writes issued through Bash.** The guard's shell-command detection is a regex
  heuristic, deliberately over-inclusive, and it will never be complete. The real
  enforcement is the `tools:` allowlist: `scout` and `reviewer` have no Bash at all.
  For `builder` a suspected write raises an `ask`, because a shell command's target cannot
  be resolved reliably. Scribe's exact `cat >> <literal-path>` append inside `paths.docs`
  is allowed; other suspected writes ask.
- **Anything outside the project directory.** Paths that resolve outside the repo root
  are not classified and not policed.
- **Agents the plugin does not own.** An unrecognised `agent_type` passes every rule
  untouched; this guard governs the routing roles, not every agent in your repo.
- **Whether the model actually used its cheap tier.** The hooks record dispatches;
  `/route:audit` is what checks the bill.
- **The builder's inline `Files` list.** The guard enforces role-level path categories;
  the Builder and Reviewer must check the task-specific list.

Every guard is also fail-open by design: a malformed payload, an unreadable config, or a
crash in the hook exits silently rather than blocking your session.

## Language

Code, identifiers, and commit messages are English. Prose in records and agent reports
follows `language.artifacts` in the project config. This README is the documented
exception.

## License

MIT — see [LICENSE](LICENSE).
