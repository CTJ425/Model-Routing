"""Tests for routing_audit.py pricing: longest-prefix match and per-model cache reads."""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "route", "scripts"))

import routing_audit  # noqa: E402

ONE_M_READS = {"out": 0, "in": 0, "cache_read": 1_000_000, "cw5": 0, "cw1h": 0}


def test_opus_5_5_has_its_own_key_and_cache_rate():
    assert routing_audit.price_entry("claude-opus-5-5")[0] == "claude-opus-5-5"
    assert routing_audit.rate("claude-opus-5-5") == (4.0, 20.0)
    # 0.05x of $4, not the default 0.1x.
    assert abs(routing_audit.cost("claude-opus-5-5", ONE_M_READS)["cache_read"] - 0.20) < 1e-9


def test_opus_5_falls_back_to_the_family_key():
    assert routing_audit.price_entry("claude-opus-5")[0] == "claude-opus-"
    assert abs(routing_audit.cost("claude-opus-5", ONE_M_READS)["cache_read"] - 0.50) < 1e-9


def test_sonnet_5_is_priced_at_list():
    assert routing_audit.price_entry("claude-sonnet-5")[0] == "claude-sonnet-5"
    assert routing_audit.rate("claude-sonnet-5") == (2.0, 10.0)
    assert routing_audit.rate("claude-sonnet-4-6") == (3.0, 15.0)


# --- T2: task identity and resume count from an agent transcript ---

import json  # noqa: E402

HANDBACK = "<system-reminder>\nYour final report is delivered through SubagentHandback."
NUDGE = "[Your previous response had no visible output. Please continue and produce it.]"
ENFORCE = "[handback-send-enforce] Your report has not been delivered."


def _write(path, rows):
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return str(path)


def _user(content, **extra):
    return dict({"type": "user", "message": {"role": "user", "content": content}}, **extra)


def _tool_result():
    return _user([{"type": "tool_result", "tool_use_id": "t", "content": "ok"}])


def _assistant(model="claude-opus-5-5", out=10, cache_read=100):
    return {"type": "assistant", "message": {"model": model, "usage": {
        "output_tokens": out, "input_tokens": 1,
        "cache_read_input_tokens": cache_read, "cache_creation_input_tokens": 50}}}


def _resume(text="fix line 3"):
    return _user("The coordinator sent a message while you were working:\n" + text,
                 isMeta=True, origin={"kind": "coordinator"})


def test_task_from_brief_and_only_coordinator_messages_count_as_resumes(tmp_path):
    p = _write(tmp_path / "agent-a.jsonl", [
        _user("Task: T2 — task identity\nContract: ..."),
        _user(HANDBACK, isMeta=True),
        _assistant(), _tool_result(), _assistant(),
        _resume(),
        _user(ENFORCE, isMeta=True),
        _user(NUDGE, isMeta=True),
        _assistant(),
    ])
    assert routing_audit.task_identity(p) == ("T2", 1)


def test_task_id_is_the_first_token_of_a_block_list_brief(tmp_path):
    p = _write(tmp_path / "agent-b.jsonl", [
        _user([{"type": "text", "text": "Task: ?-fix-typo — one line\nFiles: x"}]),
        _assistant(),
    ])
    assert routing_audit.task_identity(p) == ("?-fix-typo", 0)


def test_task_id_stops_at_an_em_dash_without_spaces(tmp_path):
    p = _write(tmp_path / "agent-c.jsonl", [_user("Task: T4—every dispatch"), _assistant()])
    assert routing_audit.task_identity(p) == ("T4", 0)


def test_a_task_line_that_is_not_first_is_untagged(tmp_path):
    p = _write(tmp_path / "agent-d.jsonl", [
        _user("Spec: docs/x.md\nTask: T9"), _assistant(), _resume(), _resume(), _assistant(),
    ])
    assert routing_audit.task_identity(p) == ("(untagged)", 2)


# --- T3: cost grouped by task ---


def _stats_usd(path, model):
    return sum(routing_audit.cost(model, routing_audit.tally(path)[model]).values())


def _task_runs(tmp_path):
    b1 = _write(tmp_path / "agent-b1.jsonl", [
        _user("Task: T3a — first task"), _assistant(), _resume(), _assistant()])
    r1 = _write(tmp_path / "agent-r1.jsonl", [_user("Task: T3a — review"), _assistant()])
    b2 = _write(tmp_path / "agent-b2.jsonl", [
        _user("Task: T3b — second task"), _assistant(model="claude-sonnet-5")])
    s1 = _write(tmp_path / "agent-s1.jsonl", [
        _user("Question: where is X?"), _assistant(model="claude-haiku-4-5-20251001")])
    other = _write(tmp_path / "agent-o1.jsonl", [_user("Task: T3a — not a route role"),
                                                  _assistant()])
    return [("builder", b1), ("reviewer", r1), ("builder", b2), ("scout", s1),
            ("?", other), ("general-purpose", other)], b1, r1


def test_by_task_groups_runs_and_counts_the_resume_on_the_right_task(tmp_path):
    runs, b1, r1 = _task_runs(tmp_path)
    t = routing_audit.by_task(runs)
    assert set(t) == {"T3a", "T3b", "(untagged)"}
    a = t["T3a"]
    assert (a["builder_dispatches"], a["builder_resumes"], a["reviewer_dispatches"]) == (1, 1, 1)
    assert (a["turns"], a["out"], a["cache_read"]) == (3, 30, 300)
    assert a["models"] == ["claude-opus-5-5"]
    b = t["T3b"]
    assert (b["builder_dispatches"], b["builder_resumes"], b["reviewer_dispatches"]) == (1, 0, 0)
    assert b["models"] == ["claude-sonnet-5"]
    assert t["(untagged)"]["turns"] == 1


def test_by_task_splits_cost_by_role_and_drops_non_route_roles(tmp_path):
    runs, b1, r1 = _task_runs(tmp_path)
    a = routing_audit.by_task(runs)["T3a"]
    assert set(a["usd_by_role"]) == {"builder", "reviewer"}
    assert abs(a["usd_by_role"]["builder"] - _stats_usd(b1, "claude-opus-5-5")) < 1e-12
    assert abs(a["usd_by_role"]["reviewer"] - _stats_usd(r1, "claude-opus-5-5")) < 1e-12
    assert abs(a["usd"] - sum(a["usd_by_role"].values())) < 1e-12


def test_report_by_task_prints_each_task_once(tmp_path, capsys):
    session = _write(tmp_path / "sess.jsonl", [_assistant(out=500)])
    sub = tmp_path / "sess" / "subagents"
    sub.mkdir(parents=True)
    for name, role, rows in (
            ("agent-x1", "route:builder", [_user("Task: T3a — x"), _assistant(), _resume(),
                                           _assistant()]),
            ("agent-x2", "route:reviewer", [_user("Task: T3a — x"), _assistant()])):
        _write(sub / (name + ".jsonl"), rows)
        (sub / (name + ".meta.json")).write_text(json.dumps({"agentType": role}))
    assert routing_audit.report([session], by_task=True) == 0
    out = capsys.readouterr().out
    assert "--- cost by task" in out
    rows = [ln.split() for ln in out.splitlines() if ln.split()[:1] == ["T3a"]]
    assert len(rows) == 1


def test_brief_text_blocks_are_joined_as_separate_lines(tmp_path):
    p = _write(tmp_path / "agent-e.jsonl", [
        _user([{"type": "text", "text": "Task: T2"}, {"type": "text", "text": "Contract: x"}]),
        _assistant(),
    ])
    assert routing_audit.task_identity(p) == ("T2", 0)


# --- one API message written as several transcript rows counts once ---


def _split(mid, blocks):
    rows = []
    for _ in range(blocks):
        r = _assistant()
        r["message"]["id"] = mid
        r["message"]["content"] = [{"type": "text", "text": "x"}]
        rows.append(r)
    return rows


def test_tally_counts_a_message_split_across_rows_once(tmp_path):
    p = _write(tmp_path / "s.jsonl", _split("m1", 3) + [_tool_result()] + _split("m2", 2))
    s = routing_audit.tally(p)["claude-opus-5-5"]
    assert (s["turns"], s["out"], s["cache_read"], s["cw5"]) == (2, 20, 200, 100)


def test_tally_rows_without_a_message_id_each_count(tmp_path):
    p = _write(tmp_path / "s.jsonl", [_assistant(), _assistant()])
    assert routing_audit.tally(p)["claude-opus-5-5"]["turns"] == 2


def test_tally_takes_the_last_row_of_a_streamed_message(tmp_path):
    rows = _split("m1", 3)
    for r, out in zip(rows, (5, 5, 40)):
        r["message"]["usage"]["output_tokens"] = out
    p = _write(tmp_path / "s.jsonl", rows)
    s = routing_audit.tally(p)["claude-opus-5-5"]
    assert (s["turns"], s["out"]) == (1, 40)
