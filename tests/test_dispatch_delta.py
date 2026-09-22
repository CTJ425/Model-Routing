"""Tests for dispatch_delta.py — what one dispatch puts into main's context.

Each test writes a main transcript plus one subagent transcript in the on-disk layout the
script reads (`<session>/subagents/agent-*.meta.json` beside `agent-*.jsonl`), then checks
the per-dispatch record `collect()` builds from them.
"""
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "route", "scripts"))

import dispatch_delta  # noqa: E402

CPT = dispatch_delta.CHARS_PER_TOKEN


def assistant(block, cache_read=0):
    return {"type": "assistant",
            "message": {"role": "assistant", "model": "claude-opus-5",
                        "usage": {"cache_read_input_tokens": cache_read},
                        "content": [block]}}


def tool_result(tool_use_id, content, tool_use_result=None):
    row = {"type": "user",
           "message": {"role": "user", "content": [
               {"type": "tool_result", "tool_use_id": tool_use_id, "content": content}]}}
    if tool_use_result is not None:
        row["toolUseResult"] = tool_use_result
    return row


def write_jsonl(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def delivery(origin, text):
    """A row Claude Code adds to main after a background launch, such as a hand-back."""
    return {"type": "user", "origin": origin, "message": {"role": "user", "content": text}}


def session(tmp_path, launch_result, launch_meta, sub_rows, late_rows=()):
    """-> the single record collect() builds for one route:scout dispatch."""
    main = tmp_path / "s1.jsonl"
    write_jsonl(str(main), [
        assistant({"type": "tool_use", "id": "tu1", "name": "Agent",
                   "input": {"subagent_type": "route:scout", "prompt": "p" * 400}},
                  cache_read=1000),
        tool_result("tu1", launch_result, launch_meta),
        assistant({"type": "text", "text": "ok"}, cache_read=1300),
        *late_rows,
    ])
    sub = tmp_path / "s1" / "subagents" / "agent-a1"
    write_jsonl(str(sub) + ".jsonl", sub_rows)
    with open(str(sub) + ".meta.json", "w", encoding="utf-8") as fh:
        json.dump({"toolUseId": "tu1", "agentType": "scout"}, fh)
    (rec,) = dispatch_delta.collect(str(main))
    return rec


def reading_then(*final_blocks):
    """A subagent that reads 4000 chars, then ends with `final_blocks`."""
    rows = [assistant({"type": "tool_use", "id": "r1", "name": "Read", "input": {}}),
            tool_result("r1", "y" * 4000)]
    return rows + [assistant(b) for b in final_blocks]


def test_foreground_report_is_the_tool_result(tmp_path):
    rec = session(tmp_path, "F" * 600, {"status": "completed"},
                  reading_then({"type": "text", "text": "F" * 600}))
    assert rec["report"] == 600 / CPT
    assert rec["benefit"] == 4000 / CPT
    assert rec["measured"] == 300


def test_background_launch_counts_the_report_not_the_launch_notice(tmp_path):
    """Since Claude Code 2.1.198 a dispatch returns its launch; the report comes later."""
    rec = session(tmp_path, "Async agent launched successfully.",
                  {"status": "async_launched", "agentId": "a1"},
                  reading_then({"type": "text", "text": "Found "},
                               {"type": "text", "text": "R" * 794}))
    assert rec["report"] == 800 / CPT
    assert rec["cost"] == (400 + 800) / CPT
    assert rec["measured"] is None, "the launch turn grows context by the prompt alone"


def test_handback_message_is_the_report(tmp_path):
    """Auto mode (2.1.271+) delivers the report as SubagentHandback's message."""
    rec = session(tmp_path, "Report delivered via hand-back.", {"status": "completed"},
                  reading_then(
                      {"type": "tool_use", "id": "h1", "name": "SubagentHandback",
                       "input": {"message": "M" * 1200}},
                  ) + [tool_result("h1", "ok"),
                       assistant({"type": "text", "text": "done"})])
    assert rec["report"] == 1200 / CPT


def test_background_report_counts_every_row_it_puts_into_main(tmp_path):
    """Main keeps the launch notice, the framed hand-back (2.1.277+) and the
    task-notification. Rows for another agent or another dispatch are not this cost."""
    notice = "<task-notification>\n<tool-use-id>tu1</tool-use-id>\n" + "N" * 800
    rec = session(tmp_path, "L" * 1000, {"status": "async_launched", "agentId": "a1"},
                  reading_then({"type": "tool_use", "id": "h1", "name": "SubagentHandback",
                                "input": {"message": "M" * 300}}),
                  late_rows=[
                      delivery({"kind": "peer", "from": "a1", "handback": True}, "P" * 1500),
                      delivery({"kind": "task-notification"}, notice),
                      delivery({"kind": "peer", "from": "a9", "handback": True}, "X" * 5000),
                      delivery({"kind": "task-notification"},
                               "<task-notification>\n<tool-use-id>tu9</tool-use-id>\n"
                               + "X" * 5000),
                  ])
    assert rec["report"] == (1000 + 1500 + len(notice)) / CPT
    assert rec["cost"] == (400 + 1000 + 1500 + len(notice)) / CPT


def test_text_before_the_last_tool_call_is_not_the_report(tmp_path):
    rec = session(tmp_path, "launched", {"status": "async_launched"},
                  [assistant({"type": "text", "text": "N" * 5000})]
                  + reading_then({"type": "text", "text": "R" * 100}))
    assert rec["report"] == 100 / CPT
