# Changelog

All notable changes to the `route` plugin. This file is the source of truth from 0.9.1
onward; releases 0.9.0 and earlier live in the git tags and their GitHub Releases, and
the fuller narrative for every version is in `docs/agent/PROGRESS.md` and its archive.

## [0.10.0] - 2026-09-01

### Added

- `architect` — a fifth route role on the `opus` tier (overridable via
  `models.architect`). It owns Lane 2 spec authoring plus the failing tests, root-cause
  analysis, review adjudication, and a `consult` mode: dispatched before any spec
  exists, it writes a `<task>-design.md` design note under `paths.specs` — options, a
  recommendation, open questions — that a human reads directly and answers through the
  caller with `SendMessage`, and only when the design is settled does it produce the spec.
- Guard scope for `architect`: `spec` and `test` paths only, through `Write`/`Edit` and
  Bash alike. Production code, records, and config are denied — the mirror of the rule
  the guard already applies to `builder`.
- `roles.architect.enabled` switch, `models.architect` tier (default `opus`), a five-tier
  `/route:doctor` report, and a SessionStart roster entry.
- Step 5 escalation path: dispatch `architect` to rule on a reviewer `FAIL` the Boss
  cannot adjudicate. SKILL.md tells a Boss that is not on the expensive tier to set
  `review.policy=always`.

### Why

The loop assumed the main session runs on the expensive model. Under an `opusplan`
session (Opus in plan mode, Sonnet after) or a session started on a mid tier, lane
classification, spec authoring, the seven risk triggers, and adjudication all ran at the
builder's tier, with no model above the builder anywhere in the execution loop.

### Unchanged

`scout` / `builder` / `reviewer` / `scribe` guard behaviour, the main-session rules, and
the config deep-merge — every `architect` rule is gated on the role name.

### Deferred

The `pricing.json` Sonnet 5 rate, a `/route:doctor` check on the session model, this
repo's own `review.policy`, and a `builder` effort raise.

### Tests

231 passed, 0 failed (was 212). Review: `route:reviewer` PASS, no findings.

## [0.9.1] - 2026-09-01

### Changed

- `scribe` no longer composes prose a human will read; the caller supplies the finished
  text and scribe places it. Step 6 adds a two-file cap per dispatch.
- Step 4 tells the caller to paste builder's `VERIFY`/`TESTS`/`LINT` lines into the
  reviewer dispatch; `reviewer` has no Bash and now says what to do when a brief tells it
  to run commands anyway.
- Step 2 gains four pre-dispatch checks on the builder's contract: watch the verify
  command fail, type-check the Lane 2 failing test against the proposed signature,
  validate any classification rule against real data with the counts recorded, and state
  the negative case.
- Step 5 adds the one place worth spending context on: where a wrong answer is silent —
  money arithmetic, authorization, migrations, retries — the main session reads the diff
  itself.

### Tests

212 passed.
