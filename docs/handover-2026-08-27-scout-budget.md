# Handover — 2026-08-27

Written at the end of a session that shipped `route` 0.8.2. Read this file instead of the
chat transcript. Every claim below was measured or verified in that session; the commands
that prove each one are given inline.

## 1. What shipped

`route` **0.8.2** — "size the scout dispatch to its 30-turn budget".

| Item | Value |
| ---- | ---- |
| Commit | `26f54a2` on `main` |
| Tag | `v0.8.2` (annotated) |
| Remote | Both are on GitHub. Confirm with `gh api repos/CTJ425/Model-Routing/commits/main` |
| Files changed | `route/agents/scout.md`, `route/skills/route/SKILL.md`, `README.md`, `route/.claude-plugin/plugin.json`, `docs/agent/PROGRESS.md`, `docs/agent/PROGRESS_ARCHIVE.md` |
| Gate 1 | `python3 -m pytest tests/ -q` — 177 passed, 0 failed, exit 0 |
| Gate 2 | `claude plugin validate ./route` — Validation passed, exit 0 |

The release adds prose only. It changes no hook decision and no schema key, which is why
the test count did not move.

**The problem it solves.** `maxTurns: 30` sat in scout's frontmatter and was documented
nowhere. `route.config.schema.json` has no such key, so no consumer could see the ceiling
or raise it. Nothing told the caller how to size a dispatch against the ceiling, and scout
itself had no instruction for what to do as the budget ran out — it stopped mid-trace and
returned nothing usable.

**What the release now says.**

- `route/skills/route/SKILL.md` Step 1 — the caller-side rule: one question per dispatch;
  split a multi-part trace into parallel scouts; pass line ranges when you already know
  them; resume a cut-off scout with `SendMessage` instead of re-dispatching cold.
- `route/agents/scout.md` — the agent-side rule: answer several questions in order and,
  when the budget looks tight, stop and report with a `NOT ANSWERED:` line.
- `README.md` Step 1 — states the ceiling so a reader sees it without opening frontmatter.

## 2. Open items in this repo

None of the three is started. None is urgent.

### A1 — GitHub Releases are four versions behind

`gh release list --repo CTJ425/Model-Routing` shows **v0.4.0** as Latest. Tags `v0.8.0`,
`v0.8.1` and `v0.8.2` exist on the remote but have no matching Release.

- **Impact: none functional.** A plugin install reads the marketplace git clone at `main`.
  It does not read Releases.
- **Source material for the bodies**: `docs/agent/PROGRESS.md` holds the 0.8.1 and 0.8.2
  entries; `docs/agent/PROGRESS_ARCHIVE.md` holds 0.8.0.
- **Ask the owner before creating them.** Creating a Release is outward-facing and the gap
  may be deliberate.

### A2 — `maxTurns` is still not settable per project

0.8.2 documented the ceiling. It did not expose it. This was deferred on purpose and is
recorded as **Accepted risk** in the 0.8.2 entry of `docs/agent/PROGRESS.md`.

- **Do not start this without evidence.** The agreed remedy is splitting the dispatch. Act
  only if splitting proves insufficient in real use.
- Files it would touch: `route/schema/route.config.schema.json`, `route/hooks/_config.py`,
  and the suite under `tests/`.

### A3 — Optional field report

The repo keeps `docs/field-reports/<date>-<project>-<topic>.md`. The 2026-08-27 session
produced the measurement in section 4 and it is not written up as a field report. The user
was offered one and did not ask for it. Treat it as optional.

### Note on tracking

`docs/agent/TASK.md` and `docs/agent/BUG_FIX.md` are both **empty**. The three items above
are not filed there. File them if you want the session brief to count them.

## 3. Open observation in the other repo (`stock-pnl-web`)

This one is technical and unresolved. It is recorded here because the session that found it
is the session that shipped 0.8.2. It is **not a bug report** — it needs a decision first.

**B1 — the second `bfi82u` probe window collects nothing.**

`sources/supabase/functions/stock-report/sourceProbePlan.ts` defines two daily windows for
`bfi82u`: 15:00–16:30 and 19:30–20:15. The code comment states the second window exists
because block trades and omnibus accounts revise the institutional figures late.

Six consecutive trading days (2026-08-19 to 2026-08-26) contradict that premise on both
DEV and PROD. The probe fingerprint is byte-identical across both windows every day. The
fingerprint was proved complete: recomputing `fingerprint(day.institutional)` from the
final stored `market/daily.json` reproduces the recorded probe fingerprint exactly on all
six days, so it covers net, buy and sell for all five institutional categories.

Therefore the three `bfi82u` probes at 19:30, 19:35 and 19:40 fetch the same data every
day and change nothing.

**What is NOT wrong, so do not re-investigate it:**

- The retire gate is correct. One landed hit plus two more ticks with an unchanged
  fingerprint, evaluated **per window** — `summariseLandedTicks()` filters ticks outside
  the active window, which is why the second window restarts the count at 1.
- `sync-market：updated` is truthful. The comparison is the `signature()` function in
  `index.ts`; it covers `tradeValueTwd`, `taiexOpen` and five institutional totals per day.
- `法人補 N 天` is truthful. `institutionalFilled` counts days **fetched**, not days
  changed. The evening branch forces the current day back into the backfill list.
- Because the fingerprint proves the institutional figures did not move, the field that
  flipped `signature()` at 19:30 is `tradeValueTwd` or `taiexOpen`. The upstream endpoint
  that supplies `tradeValueTwd` was measured lagging: at 14:20 Taipei it had not yet
  published the current day, while the open/high/low endpoint already had.

**The decision to take**: either the second window keeps a different target (the market
turnover endpoint, not `bfi82u`), or `bfi82u` drops out of that window. Confirm first by
capturing the turnover endpoint at about 15:10 and again at about 19:35 on one trading day
and diffing the current day's row.

## 4. The measurement behind 0.8.2

Quote this if you write the field report in A3.

| Dispatch | Questions asked | Target | Tool calls | Result |
| ---- | ---- | ---- | ---- | ---- |
| 1 | 2 | several files under `docs/` | 13 | completed |
| 2 | 2 | one 200-line module | 12 | completed |
| 3 | **4** | one file of **4,095 lines / 172 KB** | **36** | **cut off, nothing usable** |

**Cause.** `route:scout` has no Bash, so it cannot chain `grep -n X -A 20` in one shell
call. Every locate-then-read costs two turns. Four independent questions across a
4,000-line file exhaust 30 turns before the first answer is written. The caller then pays
for the reading twice, because it must do the trace itself.

**A detail the plugin cannot express.** A consuming project may define its own `scout` in
`.claude/agents/scout.md`. `stock-pnl-web` does, with the same haiku / low / 30 budget but
with `Bash` added. Dispatching the bare name `scout` selects the project copy; `route:scout`
selects the plugin copy. For shell-heavy tracing the project copy costs about half the
turns. The plugin cannot know this, so it is not documented in `SKILL.md`.

## 5. Items for the human, not for an agent

1. **Revoke the Supabase personal access token** that was pasted into the chat during this
   session, and issue a new one. Treat the old token as public. No agent can do this.
2. **Update the local plugin install.** This machine still runs 0.8.1. Run `/plugin` inside
   Claude Code. Do not hand-pull `~/.claude/plugins/marketplaces/route`; Claude Code manages
   that clone together with its version cache, and a manual pull desynchronises them.
