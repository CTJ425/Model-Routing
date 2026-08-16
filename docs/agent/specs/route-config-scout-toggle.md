# Spec: interactive `/route:config` + `scout.enabled`

Approved plan: `/root/.claude/plans/shimmering-orbiting-pinwheel.md` (context and full
rationale live there — read it first).

Two changes, bundled because the second is meaningless without the first:

1. A new `scout.enabled` config key (default `true`) that actually disables scout
   everywhere the plugin currently recommends it.
2. `/route:config` gains an interactive, no-arguments flow that presents all four roles
   uniformly. `reviewer` maps to existing `review.policy`; `scribe` maps to existing
   `bookkeeping.enabled`; `scout` maps to the new `scout.enabled`; `builder` has no
   on/off (state that plainly in the option text). The existing `key=value` argument
   path is unchanged except for adding `scout.enabled` to the accepted dotted keys.

Do not touch `models.<role>` behavior. Do not add any other new keys.

## 1. `route/schema/route.config.schema.json`

Add a top-level `scout` property, sibling to `review` and `bookkeeping` (after
`bookkeeping`, before `language`, to match the plan's key ordering):

```json
"scout": {
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "enabled": {
      "type": "boolean",
      "description": "Whether scout may be dispatched. false removes it from the guard's recommendations and the session brief's roster, and Step 1 of the route skill is skipped."
    }
  }
}
```

## 2. `route/hooks/_config.py`

In the `DEFAULTS` dict, add a `"scout"` entry. Put it near the `"review"` key (it is
currently around line 72, right before `"review": {"policy": "risk", "nudge": True},`):

```python
    "scout": {"enabled": True},
```

No other change in this file — `load_config`'s existing deep-merge already makes a
partial project file work.

## 3. `route/hooks/routing_observe.py`

### `handle_discovery` (around line 208–227)

Read `scout.enabled` from `cfg` and return before printing the nudge when it is `false`.
Keep the existing `scoutAt <= 0` early-return — the two conditions are independent
(a project can silence the *nudge* via `scoutAt` while scout stays dispatchable, or
disable scout entirely while `scoutAt` stays a positive number that now does nothing).

```python
def handle_discovery(payload, d: str) -> None:
    n = count_discovery(payload, d)
    cfg = load_config(project_dir(payload))
    if not (cfg.get("scout") or {}).get("enabled", True):
        return
    try:
        threshold = int(os.environ.get("ROUTING_SCOUT_AT")
                        or cfg["guard"].get("scoutAt", 12))
    except (TypeError, ValueError):
        threshold = 12
    if threshold <= 0 or n < threshold or (n - threshold) % REPEAT_EVERY != 0:
        return
    ...
```

(`count_discovery` still runs first — the counter itself is not scout-specific
bookkeeping, and cheap to keep accurate even when the nudge is suppressed.)

### `BRIEF_HEAD` and `emit_brief` (around line 77–90 and 170–195)

Current roster sentence:

```python
BRIEF_HEAD = """... 
- **Roster.** This session plans, writes specs, and adjudicates. `scout` reads and
  compresses; `builder` implements; `reviewer` checks risk work{scribe_clause}.
  ...
```

Change the two roster lines to take a `{scout_clause}` slot right after "adjudicates.":

```python
- **Roster.** This session plans, writes specs, and adjudicates.{scout_clause} `builder`
  implements; `reviewer` checks risk work{scribe_clause}.
```

In `emit_brief`, compute and pass it:

```python
scout_enabled = (cfg.get("scout") or {}).get("enabled", True)
text = BRIEF_HEAD.format(
    read_kb=cfg["guard"].get("readKB", 32),
    scout_clause=" `scout` reads and compresses;" if scout_enabled else "",
    scribe_clause="; `scribe` records" if bookkeeping else "",
    record_clause=" or a tracking record" if bookkeeping else "",
)
```

Check the exact concatenation reads correctly both ways once you make the edit:
enabled → byte-identical to today's text; disabled → "adjudicates. `builder` implements;
`reviewer` checks risk work...".

## 4. `route/hooks/routing_guard.py`

### Two new reason variants, no-scout versions of the existing ones

Add these next to the existing `READ_REASON` and `DISCOVERY_REASON` constants:

```python
READ_REASON_NO_SCOUT = (
    "Reading {name} ({kb}KB) into the main session's context re-bills it on every "
    "remaining turn — context replay is most of a routed session's cost. Re-issue this "
    "Read with `offset`/`limit` for just the part you need."
)

DISCOVERY_REASON_NO_SCOUT = (
    "`{name}` inherits this session's model, so it maps the codebase at or near the "
    "highest rate in the system. Confirm only if a built-in discovery agent is "
    "genuinely required."
)
```

Keep the existing `READ_REASON` / `DISCOVERY_REASON` untouched — they are the
scout-enabled wording and must stay byte-identical to today.

### `handle_dispatch` (around line 263–267)

Give it `cfg` so it can choose the reason text. Update its signature and its one call
site (around line 403, `handle_dispatch(role, tool_input)` -> `handle_dispatch(role,
tool_input, cfg)`):

```python
def handle_dispatch(role, tool_input, cfg) -> None:
    spawned = (tool_input.get("subagent_type") or "").strip()
    if normalize_role(spawned) in DISCOVERY_AGENTS or spawned.lower() in DISCOVERY_AGENTS:
        scout_enabled = (cfg.get("scout") or {}).get("enabled", True)
        template = DISCOVERY_REASON if scout_enabled else DISCOVERY_REASON_NO_SCOUT
        respond("ask", "[routing/%s] " % role + template.format(name=spawned))
    sys.exit(0)
```

### `handle_read` (around line 270–290)

`cfg` is already a parameter. Pick the template the same way:

```python
    if size > limit_kb * 1024:
        scout_enabled = (cfg.get("scout") or {}).get("enabled", True)
        template = READ_REASON if scout_enabled else READ_REASON_NO_SCOUT
        respond("ask", "[routing/main] " + template.format(
            name=os.path.basename(target), kb=size // 1024))
```

`RULES["scout"]` (scout's own write-ban rule, around line 170) is unrelated — leave it
alone.

## 5. `route/skills/route/SKILL.md`

### Step 1 (around line 87–91)

Currently:

```
Only when the affected area is not already mapped. Ask a specific question — never
"look at the report pipeline", always "where is X chosen, who calls it, which tests cover
it". You get back ~40 lines. This is the single largest token saving in the system.
```

Add a leading sentence naming the new skip condition, before "Only when...":

```
Skip this step entirely when `scout.enabled` is `false` in `.claude/route.config.json`
— go straight to the next step with what you already know. Otherwise: only when the
affected area is not already mapped. Ask a specific question — never "look at the report
pipeline", always "where is X chosen, who calls it, which tests cover it". You get back
~40 lines. This is the single largest token saving in the system.
```

### Step 0.5 example JSON (around line 62–70)

Add the new key to the illustrative config block so it's discoverable there too:

```json
{
  "version": 2,
  "paths": { "prod": ["src/"] },
  "models": { "scout": "haiku", "builder": "sonnet", "reviewer": "sonnet", "scribe": "haiku" },
  "scout": { "enabled": true },
  "review": { "policy": "risk" },
  "bookkeeping": { "enabled": true }
}
```

## 6. `route/commands/config.md`

### Frontmatter

No change needed to `description`/`argument-hint`.

### `## Changing` section

Add `scout.enabled=true|false` to the list of dotted-key examples in the bullet that
currently reads:

```
- A dotted key sets that path directly: `review.policy=always`, `guard.readKB=64`,
  `guard.mainSeverity=deny`, `bookkeeping.enabled=false`, `audit.charsPerToken=1.6`.
  Coerce `true`/`false` and numeric values to their JSON types, not strings.
```

becomes:

```
- A dotted key sets that path directly: `review.policy=always`, `guard.readKB=64`,
  `guard.mainSeverity=deny`, `bookkeeping.enabled=false`, `scout.enabled=false`,
  `audit.charsPerToken=1.6`. Coerce `true`/`false` and numeric values to their JSON
  types, not strings.
```

### New `## Interactive (no arguments)` section

Replace the current line:

```
With no arguments, ask which setting to change and to what.
```

with a section that gives the main session (which reads this file as instructions, not
code — there is nothing to "implement" here beyond prose) a concrete flow to follow:

```markdown
## Interactive (no arguments)

After showing the current values, drive the choice with `AskUserQuestion` instead of a
free-form question:

1. Ask which of the four roles to change, multi-select, one option per role:
   - `scout` — "reads and compresses; can be turned off"
   - `builder` — "implements; cannot be turned off, it is the plugin itself" — offer it
     only for a model-tier change, never an on/off choice
   - `reviewer` — "checks risk work; off = review.policy=never"
   - `scribe` — "records outcomes; off = bookkeeping.enabled=false"
   Include a fifth option for settings that are not per-role: `guard.*` thresholds and
   `language.artifacts`.
2. For each role picked in step 1 (except when only the fifth option was picked), ask
   its model tier in one follow-up question per role (or a single call with one question
   per role, up to the 4-question limit).
3. For each role picked, ask its second dimension:
   - `scout` → enabled true/false → writes `scout.enabled`
   - `reviewer` → policy always/risk/never → writes `review.policy`
   - `scribe` → enabled true/false → writes `bookkeeping.enabled`
   - `builder` → skip, it has no second dimension
4. If the fifth option was picked, ask for the specific `guard.*` key/value or
   `language.artifacts` value.

Write back only the keys the user actually changed; every other key stays byte-identical,
same as the `key=value` path. Report the new values the same way that path does.
```

## Files (exhaustive)

- `route/schema/route.config.schema.json`
- `route/hooks/_config.py`
- `route/hooks/routing_observe.py`
- `route/hooks/routing_guard.py`
- `route/skills/route/SKILL.md`
- `route/commands/config.md`
- `tests/test_observe.py` (new tests, see below)
- `tests/test_guard.py` (new tests, see below)

## Tests to add

### `tests/test_observe.py`

```python
def test_discovery_nudge_suppressed_when_scout_disabled(project):
    cfg = json.loads(json.dumps(BASE_CONFIG))
    cfg["scout"] = {"enabled": False}
    write_config(project, cfg)
    for _ in range(12):
        assert discovery(project) is None


def test_discovery_nudge_fires_when_scout_enabled_explicitly(project):
    cfg = json.loads(json.dumps(BASE_CONFIG))
    cfg["scout"] = {"enabled": True}
    write_config(project, cfg)
    for _ in range(11):
        assert discovery(project) is None
    assert "12 discovery calls" in discovery(project)


def test_brief_omits_scout_from_roster_when_disabled(project):
    cfg = json.loads(json.dumps(BASE_CONFIG))
    cfg["scout"] = {"enabled": False}
    write_config(project, cfg)
    text = brief(project)
    assert "scout" not in text


def test_brief_includes_scout_in_roster_by_default(project):
    assert "`scout` reads and compresses" in brief(project)
```

Place the discovery-counter ones near the existing `# --- discovery counter ---` tests
and the brief ones near the existing roster/brief tests. Reuse the `discovery()` and
`brief()` helpers already defined in the file — do not redefine them.

### `tests/test_guard.py`

```python
def test_read_reason_drops_scout_when_disabled(project):
    cfg = json.loads(json.dumps(BASE_CONFIG))
    cfg["scout"] = {"enabled": False}
    write_config(project, cfg)
    (project / "src" / "big.ts").write_text("x" * 40000)
    got = run_guard({"tool_name": "Read", "agent_type": "",
                     "tool_input": {"file_path": "src/big.ts"}}, project)
    assert decision(got) == "ask"
    assert "scout" not in reason(got)


def test_discovery_reason_drops_scout_when_disabled(project):
    cfg = json.loads(json.dumps(BASE_CONFIG))
    cfg["scout"] = {"enabled": False}
    write_config(project, cfg)
    got = run_guard({"tool_name": "Agent", "agent_type": "",
                     "tool_input": {"subagent_type": "Explore"}}, project)
    assert decision(got) == "ask"
    assert "scout" not in reason(got)
```

Check the existing large-read test (search for the readKB/`over {n}KB` test in
`test_guard.py`) for the exact payload shape and default threshold before writing
`test_read_reason_drops_scout_when_disabled` — match its file-size convention, don't
guess a size that lands under the KB threshold. `BASE_CONFIG` has no `guard.readKB`
override, so the default (32KB) applies; size the fixture file well past that.
`json` needs importing in `test_guard.py` if it is not already — check the top of the
file first.

## Verify

```
cd /root/dev/mode-routing && python3 -m pytest tests/ -q
```

All tests must pass, including the ones you added. Report the full pytest summary line
in your report.
