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
- **Result**:

## V2 — nothing overrides the alias

```bash
claude --version
env | grep -E 'ANTHROPIC_DEFAULT_OPUS_MODEL|CLAUDE_CODE_SUBAGENT_MODEL' || echo "no overrides"
```

- **Pass**: version is 2.1.280 or later; `no overrides`.
- **Result**:

## V3 — doctor

Run `/route:doctor`.

- **Pass**: `[PASS] models scout=haiku builder=opus reviewer=opus scribe=haiku.` and
  `[PASS] effort builder and reviewer run their default model.` The `dispatch log`
  warning about rows with no role existed before this change and is expected.
- **Result**:

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
- **Result**:

## V5 — audit prices Opus 5.5 by its own key

```bash
CLAUDE_PROJECT_DIR=$PWD python3 ~/.claude/plugins/cache/route/route/0.9.4/scripts/routing_audit.py --sessions 1
```

- **Pass**: the cost-by-model table shows
  `claude-opus-5-5 ... (priced as claude-opus-5-5)`. No model shows as unpriced.
- **Result**:

## V6 — record the first Opus run for the T7 comparison

From the V5 output, copy the builder and reviewer rows (turns, out, cacheW, cacheR,
USD) for the V4 task. Compare them with the Sonnet reference from 2026-09-22:

| Role | Model | Turns | Out | CacheR | USD (list price) |
| --- | --- | --- | --- | --- | --- |
| builder | claude-sonnet-5 / high | 91 | 10,540 | 4,536,187 | 1.35 |
| reviewer | claude-sonnet-5 / high | 26 | 6,884 | 551,271 | 0.41 |
| reviewer | claude-sonnet-5 / high | 17 | 7,020 | 303,373 | 0.29 |
| builder | claude-opus-5-5 / medium | | | | |
| reviewer | claude-opus-5-5 / medium | | | | |

One task is a single sample of a different task, so it shows only whether the numbers
are plausible. The real comparison is T7's paired run.

- **Result**:

---

## Done when

V1–V5 pass and V6 has one row per role. Then continue with T2 → T3 in `docs/20260923.md`.
