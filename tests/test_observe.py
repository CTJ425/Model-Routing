"""Tests for routing_observe.py — the brief, the counters, and the review nudge."""
import json

from conftest import BASE_CONFIG, write_config
from helpers import run_observe


def context(result):
    if not result:
        return None
    return result.get("hookSpecificOutput", {}).get("additionalContext")


def brief(project):
    return context(run_observe(
        {"hook_event_name": "SessionStart", "session_id": "t1"}, project))


# --- SessionStart brief ---

def test_brief_omits_the_open_line_when_no_records_exist(project):
    (project / "docs" / "agent" / "TASK.md").unlink()
    text = brief(project)
    assert "?" not in text
    assert "Open now" not in text


def test_brief_does_not_turn_one_unreadable_record_into_zero(project):
    (project / "docs" / "agent" / "TASK.md").unlink()
    (project / "docs" / "agent" / "BUG_FIX.md").write_text("### Bug 1\n")
    text = brief(project)
    assert "1 open bug(s)" in text
    assert "task(s)" not in text


def test_brief_counts_only_unfinished_tasks(project):
    (project / "docs" / "agent" / "TASK.md").write_text(
        "### Task 1\n- **Status**: ✅ DONE\n\n"
        "### Task 2\n- **Status**: 🔄 IN PROGRESS\n\n"
        "### Task 3\n- **Status**: 🔁 Recurring\n")
    assert "**Open now:** 2 task(s)" in brief(project)


def test_brief_drops_bookkeeping_language_when_disabled(project):
    cfg = json.loads(json.dumps(BASE_CONFIG))
    cfg["bookkeeping"] = {"enabled": False}
    write_config(project, cfg)
    text = brief(project)
    assert "scribe" not in text
    assert "Open now" not in text
    assert "tracking record" not in text


def test_brief_reports_the_configured_read_threshold(project):
    cfg = json.loads(json.dumps(BASE_CONFIG))
    cfg["guard"] = {"readKB": 64}
    write_config(project, cfg)
    assert "over 64KB" in brief(project)


def test_brief_omits_scout_from_roster_when_disabled(project):
    cfg = json.loads(json.dumps(BASE_CONFIG))
    cfg["scout"] = {"enabled": False}
    write_config(project, cfg)
    assert "scout` reads and compresses" not in brief(project)


def test_brief_includes_scout_in_roster_by_default(project):
    assert "`scout` reads and compresses" in brief(project)


# --- discovery counter ---

def discovery(project, session="t1"):
    return context(run_observe(
        {"hook_event_name": "PostToolUse", "tool_name": "Read",
         "agent_type": "", "session_id": session}, project))


def test_discovery_nudge_fires_at_the_threshold(project):
    for _ in range(11):
        assert discovery(project) is None
    assert "12 discovery calls" in discovery(project)


def test_subagent_discovery_is_not_counted(project):
    for _ in range(20):
        assert context(run_observe(
            {"hook_event_name": "PostToolUse", "tool_name": "Read",
             "agent_type": "route:scout", "session_id": "t2"}, project)) is None


def test_session_end_clears_the_counter(project):
    for _ in range(11):
        discovery(project)
    run_observe({"hook_event_name": "SessionEnd", "session_id": "t1"}, project)
    assert not list((project / ".claude" / "routing" / "state").iterdir())
    assert discovery(project) is None  # count restarted from one


def test_discovery_nudge_suppressed_when_scout_disabled(project):
    cfg = json.loads(json.dumps(BASE_CONFIG))
    cfg["scout"] = {"enabled": False}
    write_config(project, cfg)
    for _ in range(12):
        assert discovery(project) is None


def test_discovery_nudge_fires_when_scout_enabled_explicitly(project):
    cfg = json.loads(json.dumps(BASE_CONFIG))
    cfg["scout"] = {"enabled": True}
    write_config(project, cfg)
    for _ in range(11):
        assert discovery(project) is None
    assert "12 discovery calls" in discovery(project)


# --- review nudge ---

def dispatch_return(project, subagent_type, agent_type="", tool_result=None):
    payload = {
        "hook_event_name": "PostToolUse", "tool_name": "Agent",
        "agent_type": agent_type, "session_id": "t1",
        "tool_input": {"subagent_type": subagent_type},
    }
    if tool_result is not None:
        payload["tool_result"] = tool_result
    return context(run_observe(payload, project))


def test_builder_return_nudges_about_review(project):
    assert "Step 4 review policy" in dispatch_return(project, "route:builder")


def test_builder_async_launch_says_dispatched_not_returned(project):
    text = dispatch_return(project, "route:builder",
                           tool_result="Async agent launched successfully. Task id: task-1")
    assert "just returned" not in text
    assert "dispatched" in text
    assert "completion notification" in text
    assert "dispatch `route:reviewer` now" not in text


def test_reviewer_return_is_silent(project):
    assert dispatch_return(project, "route:reviewer") is None


def test_nudge_respects_review_policy_never(project):
    cfg = json.loads(json.dumps(BASE_CONFIG))
    cfg["review"] = {"policy": "never"}
    write_config(project, cfg)
    assert dispatch_return(project, "route:builder") is None


def test_nudge_can_be_switched_off(project):
    cfg = json.loads(json.dumps(BASE_CONFIG))
    cfg["review"] = {"policy": "risk", "nudge": False}
    write_config(project, cfg)
    assert dispatch_return(project, "route:builder") is None


def test_nudge_uses_configured_review_triggers(project):
    cfg = json.loads(json.dumps(BASE_CONFIG))
    cfg["review"] = {"policy": "risk", "triggers": ["boundary"]}
    write_config(project, cfg)
    text = dispatch_return(project, "route:builder")
    assert "a boundary another system depends on" in text
    assert "persisted state" not in text


def test_always_policy_is_explicit_in_the_nudge(project):
    cfg = json.loads(json.dumps(BASE_CONFIG))
    cfg["review"] = {"policy": "always"}
    write_config(project, cfg)
    assert "every builder round" in dispatch_return(project, "route:builder")


def test_empty_risk_triggers_are_explicitly_reported(project):
    cfg = json.loads(json.dumps(BASE_CONFIG))
    cfg["review"] = {"policy": "risk", "triggers": []}
    write_config(project, cfg)
    assert "no automatic risk triggers" in dispatch_return(project, "route:builder")


def test_nudge_does_not_fire_inside_a_subagent(project):
    assert dispatch_return(project, "route:builder", agent_type="route:builder") is None


# --- dispatch log ---

def test_subagent_events_are_logged_with_transcript_paths(project):
    run_observe({"hook_event_name": "SubagentStop", "session_id": "t1",
                 "agent_type": "route:builder", "agent_id": "a1",
                 "effort": "low",
                 "transcript_path": "/tmp/main.jsonl",
                 "agent_transcript_path": "/tmp/agent-a1.jsonl"}, project)
    rows = [json.loads(line) for line in
            (project / ".claude" / "routing" / "dispatch.jsonl").read_text().splitlines()]
    assert rows[0]["agent_transcript_path"] == "/tmp/agent-a1.jsonl"
    assert rows[0]["transcript_path"] == "/tmp/main.jsonl"
    assert rows[0]["effort"] == "low"


# --- dispatch.jsonl rotation must never destroy a larger archive ---

def test_rotation_never_replaces_a_larger_archive_with_a_smaller_file(project):
    """Two processes can both observe an over-threshold file. The second one sees a live
    file that the first already rotated and truncated; rotating again would overwrite a
    full archive with a few bytes. Size is the ordering that makes that impossible."""
    d = project / ".claude" / "routing"
    d.mkdir(parents=True, exist_ok=True)
    archive = d / "dispatch.jsonl.1"
    archive.write_text("x" * 5000)
    (d / "dispatch.jsonl").write_text("y" * 200)
    run_observe({"hook_event_name": "SubagentStop", "session_id": "t1",
                 "agent_type": "route:builder", "agent_id": "a1"},
                project, env_extra={"ROUTING_DISPATCH_MAX_BYTES": "100"})
    assert archive.read_text() == "x" * 5000, "the larger archive was clobbered"


def test_rotation_still_happens_when_the_live_file_is_the_bigger_one(project):
    d = project / ".claude" / "routing"
    d.mkdir(parents=True, exist_ok=True)
    (d / "dispatch.jsonl.1").write_text("x" * 10)
    (d / "dispatch.jsonl").write_text("y" * 5000)
    run_observe({"hook_event_name": "SubagentStop", "session_id": "t1",
                 "agent_type": "route:builder", "agent_id": "a1"},
                project, env_extra={"ROUTING_DISPATCH_MAX_BYTES": "100"})
    assert (d / "dispatch.jsonl.1").read_text() == "y" * 5000
    assert "route:builder" in (d / "dispatch.jsonl").read_text()
