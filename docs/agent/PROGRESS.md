# Progress

Newest entry at the top, immediately after this header block. Older entries roll into
`PROGRESS_ARCHIVE.md`, prepended so newest-first order holds there too.

---

## 📅 Log: 2026-09-22 18:51:06 CST (0.9.4 — a role turned off hands its writes to the main session)

- **Changed**: route/hooks/routing_guard.py, route/hooks/routing_observe.py,
  route/skills/route/SKILL.md, route/schema/route.config.schema.json,
  route/commands/config.md, README.md, tests/test_guard.py, tests/test_observe.py,
  docs/CHANGELOG.md; new spec docs/agent/specs/route-role-off-main-writes.md
- **Why**: a check of "builder off, the main session writes the code" found the guard
  still asked on every main-session production-code write, through `Write`/`Edit` and
  Bash, and named `builder` as the cheaper path, which the guard denies. Reproduced
  against the real hook scripts on a temp project. `roles.scribe.enabled=false` had the
  same defect for tracking records. Fixed by user decision.
- **What changed**: a main-session write whose owning role is off passes with no ask,
  under every `guard.mainSeverity` (`deny` included: with the role off, nobody else can
  write it). Bash skips such a target and keeps scanning, so a later target whose role
  is on still asks. The session brief's guard line drops the absorbed edit class.
  SKILL.md Steps 0/3/4/5/6, the schema, `/route:config` and the README say the same;
  Step 4 has the main session produce builder's report lines for reviewer.
- **Not changed**: the ask text, subagent write rules, the record timestamp check, and
  the review nudge (it still fires only when a `builder` dispatch returns).
- **Review**: Lane 2, reviewer PASS with no findings.
- **Housekeeping**: `roll_records.py --keep 2` moved the 2026-09-17 10:12:22 entry into
  `PROGRESS_ARCHIVE.md`.
- **Tests**: 295 passed, 0 failed (was 278). Against the previous code 12 of the 17 new
  cases fail (8 guard, 4 observe); the other 5 pin behaviour it already had.

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
