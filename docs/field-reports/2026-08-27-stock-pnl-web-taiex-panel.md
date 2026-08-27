# Field report — 2026-08-26/27, stock-pnl-web, TAIEX intraday panel (0.9.19 → 0.9.20)

- **Recorded**: 2026-08-27 09:30 CST
- **Host project**: `/root/dev/stock-pnl-web` (public repo, `main` deploys GitHub Pages)
- **Session shape**: one verification sweep, then two Lane 2 features shipped end to end.
  Dispatches: `scout` ×2 (one resumed), `builder` ×2, `reviewer` ×2, `scribe` ×5.
- **Outcome**: both features shipped, deployed to DEV and PROD, merged to `main`. One builder
  stalled for 84 minutes and was killed; the main session finished its work directly.
- **Why this report exists**: the 2026-08-24 report named two stalls as 74% of the waiting
  time. This session produced a third, and this time the hooks were measured rather than
  suspected — so the usual suspect can be ruled out with numbers.

Ordered by how much each one costs autonomy.

---

## 1. A builder stalled for 84 minutes, and the hooks were not the cause

**Severity: high. This is the third stall in four sessions.**

The builder was resumed via `SendMessage` with two small, fully specified fixes: move three
formatter helpers into an existing module, and restore a date string on one sub-line. It had
already completed a much larger first pass (43 tool uses) successfully.

It then wrote nothing for 84 minutes.

| Signal | Value |
| --- | --- |
| Last file write by the builder | 17:56:41 |
| Time when the main session checked | 19:20:44 |
| Fix 1 applied (`utils/formatters.ts` touched) | no — file still dated 2026-08-20 |
| Fix 2 applied (date restored) | no — sub-line still read `最近交易日` |
| Import cycle removed | no — `from './TwMarketSection'` still present |

**Diagnosis method worth keeping.** The stall was detected from file `mtime` and three
`grep`s, not by reading the agent's transcript. The transcript is the expensive way to ask
"is it progressing", and the cheap way answered it completely. A stalled agent and a working
one are distinguishable from outside.

### The hooks did not do it

The obvious hypothesis was hook overhead or a hook silently blocking the builder. Both were
tested directly by feeding synthetic payloads to `routing_guard.py`:

| Role | Operation | Decision |
| --- | --- | --- |
| `route:builder` | `Edit sources/src/utils/formatters.ts` | silent pass (rc=0, no output) |
| `route:builder` | `Edit .../Macro/TwIndexToday.tsx` | silent pass |
| `route:builder` | `Bash npm test` | silent pass |
| `route:builder` | `Bash npx vitest run …` | silent pass |
| `route:builder` | `Read` a 29 KB file | silent pass |

Latency, 20 runs each: **46 ms** per `PreToolUse` guard call, **41 ms** per `PostToolUse`
observe call. Across the builder's ~43 tool uses that is roughly **4 seconds** total — three
orders of magnitude short of the 84 minutes.

The host project's own `PostToolUse` hook on `Edit|Write` (`code-review-graph update`, 30 s
timeout) never runs at all: it is guarded by `command -v code-review-graph`, and the binary is
not installed.

**So the cause remains unknown.** What this rules out is worth writing down anyway, because
"the hooks are slowing the subagents down" is the intuition that gets reached for first, and
in this session it was wrong by a factor of about 1,200.

### What the main session did instead

Killed the builder with `TaskStop` and applied both fixes itself. They were four edits. The
lesson is not "do it yourself" — it is that a resumed builder given work far below the size
that justified a dispatch is a bad trade even when it succeeds, and a catastrophic one when
it stalls. The break-even in the `route` skill is measured in *replaced main-session turns*;
two small edits do not clear it.

---

## 2. The installed plugin is behind this repo, so the newest reviewer instructions were not in force

**Severity: medium. Silent, and it degrades exactly the check that catches the worst defects.**

```
diff ~/.claude/plugins/marketplaces/route/route/agents/reviewer.md \
     /root/dev/Model-Routing/route/agents/reviewer.md
→ the installed copy is missing the whole "## The standing checks" section (27 lines)
```

That section is commit `20a48bb`, *feat(reviewer): standing checks that do not depend on the
spec*. Both `reviewer` dispatches this session ran without it.

The irony is sharp: **standing check #1 is the `[object Object]` defect** — an error value
stringified from a plain object — and this very host project shipped that exact bug as
BUG-036 a day earlier. The rule was written from that incident, landed in the repo, and then
did not reach the agent that was supposed to apply it.

Nothing in the session surfaces this drift. The plugin loads, the reviewer answers, and the
answer is simply thinner than the repo believes it should be. **A version marker the guard
could compare, or a `SessionStart` line reporting the installed plugin's commit, would make
this visible without anyone having to run a `diff`.**

---

## 3. `ask` from a hook overrides auto mode — by design, and worth documenting

The caller asked why a session in `permissions.defaultMode: "auto"` still prompts. Measured:

| Role | Operation | Decision |
| --- | --- | --- |
| `main` | `Read docs/agent/TASK_ARCHIVE.md` (200 KB) | **ask** |
| `main` | `Agent{subagent_type: "general-purpose"}` | **ask** |
| `main` | `Read` a 29 KB file | silent pass |

A `PreToolUse` hook's `permissionDecision` is evaluated after the permission system and wins.
Auto mode governs what the *permission system* would prompt for; it cannot suppress a hook
that explicitly asks. That is the correct precedence — otherwise enabling auto mode would
quietly disable every project policy — but it reads as a bug from the caller's seat, because
the prompt looks identical to a permission prompt.

Both asks earned their keep in this session: they pushed a 200 KB archive read onto `scout`
and blocked an `Explore`/`general-purpose` dispatch that would have inherited the main
session's model. **Suggestion: word the ask so it is obviously the routing guard speaking and
not the permission system** — the reason string already starts with `[routing/main]`, so the
information is there; it is the framing around it that misleads.

Escape hatches, already documented in the guard: `ROUTING_MAIN=off`, `ROUTING_GUARD=off`.

---

## 4. Hook inventory: 15 commands, 12 of them from plugins

The caller's impression that subagents carry "a lot of hooks" is accurate, and almost none of
it is theirs:

| Source | Commands |
| --- | ---: |
| `route` plugin | 8 |
| `agy` plugin | 4 |
| project `.claude/settings.json` | 2 |
| user `~/.claude/settings.json` | 1 |

`route` covers `PreToolUse` on `Write\|Edit\|NotebookEdit\|Agent\|Task` and on `Bash`,
`PostToolUse` on `Read\|Grep\|Glob` and on `Agent\|Task`, plus `SessionStart`,
`SubagentStart`, `SubagentStop` and `SessionEnd`. Every subagent tool call therefore crosses
a hook. At 41–46 ms that is the right price for what the guard buys, and this report exists
partly so the next person does not re-litigate it from suspicion.

---

## 5. A test can force a wrong implementation, and still be green

Not a routing defect — a spec-authoring one, and the loop is where it showed up.

The main session wrote this assertion:

```js
expect(screen.getByText(/2026-08-25/)).toBeTruthy()
expect(screen.getByText(/2026-08-26/)).toBeTruthy()
```

`IntradayChart` renders the session date in its own badge, so `2026-08-26` matched twice and
`getByText` threw. The builder made it pass **by deleting the date from the panel** — the one
row whose entire purpose was to say which day its numbers described. It reported the change
honestly as a deviation, and every gate was green.

The fix was to scope the queries with `within(band)` and add a test that forbids the
degenerate wording. Step 5 of the loop says a second FAIL usually means the spec is wrong; this
case shows the same thing can happen **on a PASS** — the implementation bent to the test, the
test was satisfied, and the product got worse. A builder that reports a deviation is doing its
job; the deviation report is the signal, not the test result.

---

## 6. `autoMode.environment` described a different project

`~/.claude/settings.json` → `autoMode.environment` named `/root/dev/vuln-beacon` as the
trusted repo and stated *"no remote configured, so treat it as local-only / not yet
published"*. The session was running in `/root/dev/stock-pnl-web`, which is **public on
GitHub and publishes to Pages on every `main` push**.

Auto mode was therefore reasoning about publication risk from the wrong repo's profile. Every
secret sweep and every "this repo is public" judgement in the session came from the host
project's `CLAUDE.md`, not from that profile.

Fixed by rewriting the entries to describe each repo separately rather than swapping one
project's name for another's — the field is global, so naming a single repo is wrong for
whichever project is not open at the time.

---

## Summary of suggested changes to `route`

1. Make the installed plugin's version visible at `SessionStart`, so drift from this repo
   cannot stay silent (item 2). Highest value of the five — it silently weakened review.
2. Frame the guard's `ask` so it is legible as a routing decision rather than a permission
   prompt (item 3).
3. Say in the skill that a resumed builder handed sub-dispatch-sized work should be taken back
   by the main session instead (item 1).
4. Add to the reviewer's brief: when a builder reports a deviation, judge the *test* as well
   as the code (item 5).
5. Nothing to change for hook cost — measured, and it is fine (item 4).
