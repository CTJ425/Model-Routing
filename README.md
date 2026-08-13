# route

A Claude Code plugin marketplace with one plugin, `route`: a four-role model-routing
loop that keeps the expensive model out of mechanical work.

| Role | Where it runs | Default model | Owns | Must never |
|---|---|---|---|---|
| **Boss** | the main thread | your session model | routing, sequencing, specs, adjudication | write production code or a tracking record |
| **scout** | subagent | haiku | mapping the codebase, compressing logs/stack traces | write anything |
| **builder** | subagent | sonnet | implementing an existing spec | touch tests, specs, or tracking docs |
| **reviewer** | subagent | sonnet | reviewing a builder's diff against its spec | fix anything, or propose a fix |
| **scribe** | subagent | haiku | recording outcomes into `docs/agent/` | write production code |

Role boundaries are enforced by `PreToolUse` hooks, not prompt etiquette: ask a role to
write outside its lane and the tool call itself is denied.

## Install

```
/plugin marketplace add /root/dev/mode-routing
/plugin install route@route
```

Then, in any target repo:

```
/route:init      # scaffold docs/agent/ + .claude/route.config.json
/route:config    # view or change which model each role uses in this project
```

## The loop

```
Boss classifies the lane -> scout (if unmapped) -> Boss writes spec/brief
  -> builder -> reviewer (risk work only) -> Boss adjudicates -> scribe records
```

Load the `route` skill (or just start a feature/bug/tracking-doc item — the SessionStart
hook reminds the session it delegates) and it walks this loop step by step, including
when to skip a step for a small change.

## Per-project model tiers

Each project gets its own `.claude/route.config.json`:

```json
{
  "paths": { "prod": ["src/"] },
  "models": { "scout": "haiku", "builder": "sonnet", "reviewer": "sonnet", "scribe": "haiku" }
}
```

- `paths.prod` — repo-relative prefixes the guard treats as production code (what
  `builder` may write, what the main session gets asked about editing directly).
- `models.<role>` — overrides that role's agent-file default for this project only,
  passed as a per-dispatch model override. Editing this file never touches the plugin's
  own `agents/*.md`, so a plugin update cannot silently undo a project's tuning.

`/route:init` writes the initial file; `/route:config` edits it.

## Verifying it actually routed

```
python3 <installed-plugin-path>/hooks/routing_audit.py
python3 <installed-plugin-path>/hooks/dispatch_delta.py
```

Both read the transcripts Claude Code already writes. `routing_audit.py` reports cost
per model and per role; `dispatch_delta.py` checks whether a given dispatch actually
removed net tokens from the main session's context, not just moved cost to a cheaper
model. One model and zero subagent transcripts means nothing was routed, whatever the
plan said.

## Language

Everything an agent writes — code, identifiers, commit messages, and every file under
`docs/agent/` — is in English. This README is the documented exception.
