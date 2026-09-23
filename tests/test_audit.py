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

