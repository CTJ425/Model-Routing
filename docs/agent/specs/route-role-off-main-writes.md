# Spec: a role turned off hands its writes to the main session without an ask

## Task

With `roles.builder.enabled=false` the main session is the only implementer, but the
guard still asks on every main-session write to production code, through `Write`/`Edit`
and through Bash. The ask's reason tells the session to dispatch `builder`, and the guard
denies that dispatch. `roles.scribe.enabled=false` has the same defect for tracking
records. Measured on a temp project with `roles.builder.enabled=false`: `Edit src/a.py`
and `sed -i s/x/y/ src/a.py` both returned `ask` with the "dispatch `builder`" reason;
`Agent route:builder` returned `deny`.

## Contract

### C1 — guard, `Write`/`Edit` (`route/hooks/routing_guard.py`, `handle_write`)

- Main session, class `prod`, `role_enabled(cfg, "builder")` is false → allow silently
  (no output, exit 0).
- Main session, class `record`, `role_enabled(cfg, "scribe")` is false → allow silently.
- This holds for every `guard.mainSeverity` / `ROUTING_MAIN` value, `deny` included.
  Reason: `deny` means "the main session never writes this; the role does". With the role
  off, `deny` leaves nobody able to write production code.
- The record timestamp check (`bad_stamps`) still runs first and still denies a future
  stamp when scribe is off. Turning scribe off changes who writes a record, not what a
  record may contain.
- A malformed `roles` block makes `role_enabled` return true (fail-open), so the ask stays.

### C2 — guard, Bash (`handle_main_bash`)

- The same rule per resolved target: a `prod` target with builder off, or a `record`
  target with scribe off, is skipped, and scanning **continues** to the next target.
- The first target that is `prod` or `record` and not skipped decides, exactly as today.
- Example: builder off, `touch src/b.ts && touch docs/agent/TASK.md` → `ask` with the
  `("main", "record")` reason.

Suggested shape (not required): one table `{"prod": "builder", "record": "scribe"}` plus a
helper that answers "is the role that owns this class turned off", called from both paths.

### C3 — session brief (`route/hooks/routing_observe.py`, `BRIEF_HEAD` / `emit_brief`)

The `**Guards will ask**` bullet names only the edits the guard still asks about:

| builder | records live (bookkeeping on **and** scribe on) | edit clause |
| --- | --- | --- |
| on | yes | `edits production code or a tracking record,` (byte-identical to today) |
| on | no | `edits production code,` |
| off | yes | `edits a tracking record,` |
| off | no | *(empty)* — the bullet starts at `dispatches a built-in agent` |

With every role on, the whole brief is byte-identical to today's output.

### C4 — `route/skills/route/SKILL.md`

Keep every other line byte-identical. Five edits:

1. Step 0, after the paragraph ending "routing around it with `sed -i` is not." (line 30),
   append this sentence to that paragraph:
   `When \`roles.builder.enabled\` is \`false\`, this session is the implementer and the guard does not ask.`
2. Step 3, lines 194-195: append to that paragraph:
   `The guard does not ask on those writes: with no builder there is no cheaper path for it to name.`
3. Step 4, insert a new paragraph directly before the line starting "Pass reviewer the
   brief **or** the spec path" (line 262):

   ```
   When `roles.builder.enabled` is `false`, this session produces what builder would
   report: the changed-file list and the `VERIFY:`, `TESTS:` and `LINT:` lines, in
   builder's format, from commands this session ran. Every implementation round of this
   session counts as a builder round for `review.policy`. The review nudge fires only
   when a `builder` dispatch returns, so apply the policy here without it.
   ```
4. Step 5 table, row `FAIL, 1st time` (line 287): after "send only the fix instruction"
   append `; with builder off, apply the fix instruction in this session`.
5. Step 6, line 312: replace `write them here.` with
   `write them here; the guard does not ask.`

### C5 — `route/schema/route.config.schema.json`

- `roles.description` (line 97): after "not offered by the route skill." insert
  `The main session's writes in that role's scope no longer ask: production code when builder is off, tracking records when scribe is off.`
- `guard.mainSeverity.description` (line 132): append
  ` Does not apply to production code when roles.builder.enabled is false, or to records when roles.scribe.enabled is false.`

### C6 — `route/commands/config.md`

Step 3 of the interactive flow (line 81), after "Off means the guard denies the
dispatch," the text continues "so name what absorbs the work". Append one sentence at the
end of the `for \`scout\`, ...` clause (before "For `reviewer`, also ask"):
`When builder or scribe is off, the guard also stops asking on this session's writes in that role's scope.`

### C7 — `README.md` (user-facing, keep the existing Chinese style)

- Line 181 (`roles.<role>.enabled`): append
  `關閉 \`builder\` 時，主會話修改生產代碼不再詢問；關閉 \`scribe\` 時，主會話修改追蹤文檔不再詢問（時間戳檢查仍然生效）。`
- Line 186 (`guard.mainSeverity`): append
  `對應角色（生產代碼為 \`builder\`、追蹤文檔為 \`scribe\`）關閉時，此設定對該類寫入不生效。`

### Negative cases — must NOT change

- With every role on, every guard decision and the brief text are unchanged.
- `REASONS` text is unchanged. It is never shown for an absorbed write.
- Builder's, scribe's, scout's and reviewer's own write rules are unchanged.
- Read and discovery-agent asks are unchanged.
- `routing_observe.py` review nudge (`handle_dispatch_return`) is unchanged. No new nudge.
- `route/agents/*.md` are unchanged.

## Files

- `route/hooks/routing_guard.py`
- `route/hooks/routing_observe.py`
- `route/skills/route/SKILL.md`
- `route/schema/route.config.schema.json`
- `route/commands/config.md`
- `README.md`

Tests are already written and fail now: `tests/test_guard.py` (section "a role turned
off leaves its work to the main session") and `tests/test_observe.py` (section "the
brief's guard line"). Do not edit tests. `docs/CHANGELOG.md` is scribe's.

## Verify

```
uvx --from pytest pytest tests/ -q && python3 -m py_compile route/hooks/*.py route/scripts/*.py && python3 -c "import json; json.load(open('route/schema/route.config.schema.json'))"
```

Baseline before this task: 12 failed, 283 passed. Done: 0 failed, 295 passed.

## Non-goals

- No change to `guard.mainSeverity` semantics while the owning role is on.
- No new config key.
- No version bump; this ships in the untagged 0.9.4.
