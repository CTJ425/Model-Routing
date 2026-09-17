# Progress

Newest entry at the top, immediately after this header block. Older entries roll into
`PROGRESS_ARCHIVE.md`, prepended so newest-first order holds there too.

---

## 📅 Log: 2026-09-17 10:57:36 CST (0.9.4 — role switches: namespace scope, doctor type check)

- **Changed**: route/hooks/_config.py, route/hooks/routing_guard.py,
  route/hooks/routing_observe.py, route/scripts/routing_doctor.py, tests/test_guard.py,
  tests/test_observe.py, tests/test_doctor.py, docs/CHANGELOG.md
- **Why**: a check of the role on/off switches, run against the real hook scripts,
  found every documented path working and two gaps. Fixed by user decision.
  - `roles.<role>.enabled=false` also denied another plugin's agent of the same name
    (`other:builder`): `role_enabled` stripped any namespace, contrary to its own
    docstring.
  - A switch the hooks cannot read failed open with no sign. `"enabled": "false"`,
    `"roles": {"builder": false}` and a misspelled key or role all left the role on, and
    `/route:doctor` reported "all four roles may be dispatched".
- **What changed**: `_config.route_role` names a route role only for a bare name or the
  `route` namespace. The guard's dispatch check and the review nudge use it. The caller
  side (`agent_type`, which picks the write rules) still strips any namespace; out of
  scope here. `role_enabled` also returns true for a `roles` value that is not an object:
  the hooks crashed there, which cost the session its brief. The doctor's `roles` check
  reads the file as written and FAILs on each unreadable switch, naming the state the
  hooks actually use.
- **Not changed**: what a well-formed `false` does; the hooks still fail open on a
  malformed one, and the doctor is where that shows.
- **Housekeeping**: `roll_records.py --keep 2` moved the 0.9.3 entry into
  `PROGRESS_ARCHIVE.md`.
- **Tests**: 278 passed, 0 failed (was 254), also on Python 3.8. Against the previous
  code 20 of the new cases fail (8 doctor, 9 guard, 3 observe); the other 4 pin behaviour
  it already had.

---

## 📅 Log: 2026-09-17 10:12:22 CST (0.9.4 — catch up with Claude Code 2.1.198–2.1.271)

- **Changed**: route/skills/route/SKILL.md, route/agents/scout.md,
  route/commands/config.md, route/commands/init.md,
  route/schema/route.config.schema.json, route/hooks/routing_guard.py,
  route/hooks/routing_observe.py, route/scripts/routing_doctor.py,
  route/scripts/dispatch_delta.py, tests/test_doctor.py, tests/test_guard.py,
  tests/test_observe.py, tests/test_dispatch_delta.py (new), README.md,
  docs/MODEL_ROUTING_SPEC_ZH.md, docs/model-routing-guide.html,
  route/.claude-plugin/plugin.json, docs/CHANGELOG.md
- **Why**: Claude Code 2.1.251 demoted `CLAUDE_CODE_SUBAGENT_MODEL` below the
  per-invocation `model` parameter and the agent frontmatter, and 2.1.257 added
  `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1` as the way to force one model. The plugin still
  documented the variable as the top override, so `/route:config` and `/route:doctor`
  reported per-role tiers as not in force when they were (checked on 2.1.274).
- **What changed**: Step 0.5, `/route:config`, `/route:init`, the schema and the README
  describe the new order and `_FORCE`. The doctor reads `claude --version` and warns only
  when `_FORCE` is on, or when the plain variable is set on a version older than 2.1.251
  or an unknown version. `inherit` counts as unset. `models.<role>` is documented as an
  alias, because the Agent tool's `model` parameter takes aliases only. The README role
  table now shows the 0.9.3 turn budgets (80 / 240 / 80 / 90).
- **Also from the same version audit** (hooks and sub-agents reference, checked against
  2.1.274):
  - Background dispatch is the default since 2.1.198, and its tool response is
    `status: "async_launched"` with no launch wording. `is_async_launch` matched only
    wording, so the review nudge told the session to dispatch `reviewer` while `builder`
    was still running. The structured status now decides.
  - An `ask`'s `permissionDecisionReason` is shown to the user, not to Claude. The guard
    now repeats it as `additionalContext`; a `deny` is unchanged, since Claude already
    sees that reason.
  - The discovery ask now also covers `Plan`, `claude` and an untyped Agent call (which
    runs `general-purpose`), with exact matching. `fork` was in the first cut and is out
    by user decision: fork mode spawns forks routinely, and an ask on each one stalled
    automated workflows.
  - `dispatch_delta.py` took a background launch notice or a hand-back note as the report.
    It now reads the report size from the subagent transcript, and drops background
    launches from `--validate`. No local transcript had a background dispatch, so the
    tests use the documented shapes: `toolUseResult.status`, one content block per row
    (confirmed on this session's transcript), and `SubagentHandback`'s `message` input.
  - `maxTurns` output has been marked partial since 2.1.246; Step 1 and `scout.md` said
    a capped run returned nothing.
- **Not changed**: role scopes, write rules, Bash rules, model tiers, turn budgets.
- **Housekeeping**: `roll_records.py --keep 2` moved the 0.9.2 and 0.9.0 entries into
  `PROGRESS_ARCHIVE.md`; the hot file had been holding three.
- **Tests**: 254 passed, 0 failed (was 232). Each new case was also run against the 0.9.3
  file it covers: 4 doctor, 2 observe, 5 guard and 3 dispatch_delta cases fail there; the
  rest pin behaviour 0.9.3 already had.
