# Verification: builder and reviewer on Opus 5.5 / medium

Resume point for a restarted session. Run the checks in order, fill in each **Result**
line, and stop at the first FAIL. Spec: `docs/20260923.md`.

## What changed (commit on `main`, plugin 0.9.4 unreleased)

- `route/agents/builder.md`: `model: opus`, `effort: medium` (was `sonnet` / `xhigh`).
- `route/agents/reviewer.md`: `model: opus`, `effort: medium` (was `sonnet` / `high`).
- `.claude/route.config.json`: `models.builder` and `models.reviewer` = `"opus"`.
- `route/scripts/pricing.json`: `claude-opus-5-5` $4/$20 with cache read 0.05x;
  `claude-sonnet-5` $2/$10.
- `/route:doctor`: new `effort` check. `/route:audit`: prints `(priced as <key>)`.

Expected model id for `opus` on Claude Code 2.1.280: **`claude-opus-5-5`**.

---

## V1 — installed plugin is the new build

```bash
diff -rq -x __pycache__ -x .in_use ~/.claude/plugins/cache/route/route/0.9.4 \
  ~/.claude/plugins/marketplaces/route/route && echo SAME
grep -E '^(model|effort):' ~/.claude/plugins/cache/route/route/0.9.4/agents/{builder,reviewer}.md
```

- **Pass**: `SAME`; both files show `model: opus` and `effort: medium`.
- **If it fails**: `claude plugin uninstall route@route --keep-data && claude plugin install route@route`,
  then restart the session.
- **Result**: PASS (2026-09-23) — `SAME`; builder and reviewer both show `model: opus`, `effort: medium`.

## V2 — nothing overrides the alias

```bash
claude --version
env | grep -E 'ANTHROPIC_DEFAULT_OPUS_MODEL|CLAUDE_CODE_SUBAGENT_MODEL' || echo "no overrides"
```

- **Pass**: version is 2.1.280 or later; `no overrides`.
- **Result**: PASS — `2.1.280 (Claude Code)`; `no overrides`.

## V3 — doctor

Run `/route:doctor`.

- **Pass**: `[PASS] models scout=haiku builder=opus reviewer=opus scribe=haiku.` and
  `[PASS] effort builder and reviewer run their default model.` The `dispatch log`
  warning about rows with no role existed before this change and is expected.
- **Result**: PASS — 0 failed, 1 warning (the expected `dispatch log` no-role warning, 29 of 43 rows), 9 passed; `models` and `effort` lines as expected.

## V4 — a real builder and reviewer dispatch run Opus 5.5 at medium

Use a real, small task so the run is not wasted. Suggested task: spec **T4** in
`docs/20260923.md` (add the `Task: <id>` rule to SKILL.md Steps 3–4). Start the brief
with `Task: T4` and start the Agent `description` with `T4`. Dispatch `route:builder`,
then `route:reviewer` on its result. Wait until both finish; a background dispatch
writes its SubagentStop row only when it completes.

Then run:

```bash
cd /home/ivan/Documents/Model-Routing && python3 - <<'EOF'
import json, os, collections
rows = [json.loads(l) for l in open('.claude/routing/dispatch.jsonl')]
for r in rows[-40:]:
    if r.get('event') != 'SubagentStop' or not str(r.get('agent_type', '')).startswith('route:'):
        continue
    p, models = r.get('agent_transcript_path'), collections.Counter()
    if p and os.path.exists(p):
        for line in open(p):
            try:
                m = json.loads(line).get('message')
            except Exception:
                continue
            if isinstance(m, dict) and m.get('model'):
                models[m['model']] += 1
    print(r['ts'], r['agent_type'], 'effort=%s' % r.get('effort'), dict(models))
EOF
```

- **Pass**: the new `route:builder` and `route:reviewer` rows show `effort=medium` and
  `{'claude-opus-5-5': N}`.
- **Fail signals**:
  - `claude-opus-5` → the alias resolved to Opus 5; recheck V2.
  - `claude-sonnet-5` → the dispatch passed `model: sonnet`; check `.claude/route.config.json`.
  - `effort=xhigh` or `effort=high` → the old frontmatter is still loaded; recheck V1.
- **Result**: PASS — `2026-09-23T10:31:13+0800 route:builder effort=medium {'claude-opus-5-5': 7}`; `2026-09-23T10:31:55+0800 route:reviewer effort=medium {'claude-opus-5-5': 11}`. Task T4 done: Verify `step3=1 step4=1`, reviewer PASS with 3 RISK findings.

## V5 — audit prices Opus 5.5 by its own key

```bash
CLAUDE_PROJECT_DIR=$PWD python3 ~/.claude/plugins/cache/route/route/0.9.4/scripts/routing_audit.py --sessions 1
```

- **Pass**: the cost-by-model table shows
  `claude-opus-5-5 ... (priced as claude-opus-5-5)`. No model shows as unpriced.
- **Result**: PASS — `claude-opus-5-5 1.49 100.0% (priced as claude-opus-5-5)`; no unpriced model.

## V6 — record the first Opus run for the T7 comparison

From the V5 output, copy the builder and reviewer rows (turns, out, cacheW, cacheR,
USD) for the V4 task. Compare them with the Sonnet reference from 2026-09-22:

| Role | Model | Turns | Out | CacheR | USD (list price) |
| --- | --- | --- | --- | --- | --- |
| builder | claude-sonnet-5 / high | 54 | 10,200 | 2,768,163 | 0.84 |
| reviewer | claude-sonnet-5 / high | 11 | 6,805 | 255,253 | 0.20 |
| reviewer | claude-sonnet-5 / high | 9 | 6,974 | 166,792 | 0.18 |
| builder | claude-opus-5-5 / medium | 9 | 1,074 | 92,230 | 0.11 |
| reviewer | claude-opus-5-5 / medium | 7 | 1,819 | 70,116 | 0.14 |

One task is a single sample of a different task, so it shows only whether the numbers
are plausible. The real comparison is T7's paired run.

- **Result**: Recorded above. Opus/medium on T4 (a 6-line prose edit): builder 9 turns, $0.11 (includes a later probe resume); reviewer 7 turns, $0.14. Table recomputed after the B1 fix (`d2ad296`); the first figures counted each message once per transcript row. Plausible; T4 is much smaller than the 2026-09-22 reference task, so no cost conclusion.

---

## Done when

V1–V5 pass and V6 has one row per role. Then continue with T2 → T3 in `docs/20260923.md`.
