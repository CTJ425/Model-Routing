# Progress

Newest entry at the top, immediately after this header block. Older entries roll into
`PROGRESS_ARCHIVE.md`, prepended so newest-first order holds there too.

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

---

## 📅 Log: 2026-09-07 16:58:14 CST (0.9.3 — turn budgets raised out of the working range)

- **Changed**: route/agents/scout.md, route/agents/reviewer.md, route/agents/scribe.md,
  route/agents/builder.md, route/skills/route/SKILL.md, README.md,
  route/.claude-plugin/plugin.json, .claude/version.config.json, docs/CHANGELOG.md
- **Why**: user decision. 0.9.2 raised every cap from measured data and stated the
  principle behind it — a cap is a stop, not a budget; unused headroom costs nothing,
  hitting one costs a re-dispatch that replays the whole brief. This release applies that
  principle further, so a capped run is an anomaly to investigate rather than a routine
  cost the caller absorbs silently.
- **What changed (budgets)**: scout 40 → 80, reviewer 40 → 80, scribe 45 → 90,
  builder 80 → 240. The hardcoded scout budget in scout.md, SKILL.md Step 1 and the
  README role table follow the new number.
- **Not changed**: guard behaviour, role scopes, model tiers, the degradation protocol
  (`NOT ANSWERED:`, `VERIFY: BLOCKED`), and scout's 40-line output ceiling — an output
  limit, not a turn budget.
- **Housekeeping**: `.claude/version.config.json` and `docs/CHANGELOG.md` were collateral
  losses of the b468865 architect rollback, which reverted the whole 0.10.0 commit pair.
  Both are restored; the CHANGELOG drops the reverted 0.10.0 section and gains the 0.9.2
  entry it never received. The `v0.10.0` tag pointed at that reverted work and had no
  Release; it is deleted from the local repo, from `origin`, and from its stale plugin
  install cache under `~/.claude/plugins/cache/`.
- **Tests**: 232 passed, 0 failed.
