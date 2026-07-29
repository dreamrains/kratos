"""Collected Flask/SSE contracts for the Web chat endpoint.

These deterministic server tests verify the protocol projection only. They do
not replace the actual-browser observation required by release Gate E.
"""

from __future__ import annotations

import json

import pytest


class ScriptedLoop:
    session_id = "sse_contract"

    def __init__(self):
        self.messages = []
        self.saved = 0

    def stream_turn(self, message):
        self.messages.append({"role": "user", "content": message})
        yield {
            "type": "analysis_progress",
            "code": "analysis_plan_ready",
            "label": "Analysis plan is ready",
            "status": "finished",
            "step_id": "step_profile",
            "finding": "must not cross the boundary",
        }
        yield {"type": "text_delta", "text": "first segment"}
        yield {"type": "text_delta", "text": "second segment"}
        self.messages.append({"role": "assistant", "content": "first segmentsecond segment"})

    def _auto_save(self):
        self.saved += 1


class FailingLoop(ScriptedLoop):
    def stream_turn(self, message):
        self.messages.append({"role": "user", "content": message})
        yield {
            "type": "analysis_progress",
            "code": "analysis_plan_ready",
            "label": "Analysis plan is ready",
            "status": "finished",
            "step_id": "step_profile",
        }
        raise RuntimeError("scripted SSE failure")


class ScriptedManager:
    def __init__(self, loop):
        self.loop = loop

    def get_or_create(self, **_kwargs):
        return self.loop

    def get(self, session_id):
        return self.loop if session_id == self.loop.session_id else None

    def remove(self, _session_id):
        return None


def parse_sse_chunks(chunks):
    """Incrementally decode an SSE chunk iterator into event/data pairs."""
    pending = ""
    for chunk in chunks:
        if isinstance(chunk, bytes):
            chunk = chunk.decode("utf-8")
        pending += chunk
        while "\n\n" in pending:
            frame, pending = pending.split("\n\n", 1)
            event = None
            data = None
            for line in frame.splitlines():
                if line.startswith("event: "):
                    event = line.removeprefix("event: ")
                elif line.startswith("data: "):
                    data = json.loads(line.removeprefix("data: "))
            assert event is not None and data is not None, frame
            yield event, data
    assert not pending, f"incomplete SSE frame: {pending!r}"


def assert_success_stream_contract(events):
    """Assert the non-negotiable success-wire payload and identity contract."""
    types = [event for event, _data in events]
    assert types == [
        "turn_start",
        "analysis_progress",
        "text_delta",
        "text_delta",
        "turn_end",
    ]

    start = events[0][1]
    session_id = start["session_id"]
    turn_id = start["turn_id"]
    assert isinstance(session_id, str) and session_id
    assert isinstance(turn_id, str) and turn_id

    deltas = [events[2][1], events[3][1]]
    assert [delta["text"] for delta in deltas] == ["first segment", "second segment"]
    assert all(delta["turn_id"] == turn_id for delta in deltas)

    terminal = events[-1][1]
    assert terminal["status"] == "completed"
    assert terminal["session_id"] == session_id
    assert terminal["turn_id"] == turn_id


def test_success_stream_contract_rejects_blank_text_or_mismatched_terminal_identity():
    events = [
        ("turn_start", {"session_id": "sse_contract", "turn_id": "t_123"}),
        ("analysis_progress", {}),
        (
            "text_delta",
            {"text": "first segment", "session_id": "sse_contract", "turn_id": "t_123"},
        ),
        (
            "text_delta",
            {"text": "second segment", "session_id": "sse_contract", "turn_id": "t_123"},
        ),
        (
            "turn_end",
            {"session_id": "sse_contract", "turn_id": "t_123", "status": "completed"},
        ),
    ]
    assert_success_stream_contract(events)

    blank_delta = [*events]
    blank_delta[2] = ("text_delta", {**blank_delta[2][1], "text": ""})
    with pytest.raises(AssertionError):
        assert_success_stream_contract(blank_delta)

    wrong_nonblank_delta = [*events]
    wrong_nonblank_delta[3] = (
        "text_delta",
        {**wrong_nonblank_delta[3][1], "text": "wrong second segment"},
    )
    with pytest.raises(AssertionError):
        assert_success_stream_contract(wrong_nonblank_delta)

    mismatched_turn_end = [*events]
    mismatched_turn_end[-1] = (
        "turn_end",
        {**mismatched_turn_end[-1][1], "turn_id": "t_other"},
    )
    with pytest.raises(AssertionError):
        assert_success_stream_contract(mismatched_turn_end)


@pytest.fixture
def app(monkeypatch, tmp_path):
    import data_agent.config
    from data_agent.config import AgentConfig
    from data_agent.web.app import create_app

    monkeypatch.setattr(
        data_agent.config,
        "_config",
        AgentConfig(
            WORKSPACE_DIR=tmp_path / "workspace",
            SESSIONS_DIR=tmp_path / "sessions",
            _env_file=None,
        ),
    )
    application = create_app()
    loop = ScriptedLoop()
    application.config["agent_manager"] = ScriptedManager(loop)
    application.testing = True
    return application


def test_real_chat_route_streams_progress_before_text_and_turn_end(app):
    response = app.test_client().post(
        "/api/chat",
        json={"message": "analyze this data"},
        buffered=False,
    )
    events = list(parse_sse_chunks(response.response))
    assert response.status_code == 200
    assert response.mimetype == "text/event-stream"
    assert response.headers["X-Accel-Buffering"] == "no"
    assert_success_stream_contract(events)
    assert events[1][1] == {
        "code": "analysis_plan_ready",
        "label": "Analysis plan is ready",
        "status": "finished",
        "step_id": "step_profile",
        "phase": "",
    }
    assert "finding" not in events[1][1]

    loop = app.config["agent_manager"].loop
    assert loop.messages == [
        {"role": "user", "content": "analyze this data"},
        {"role": "assistant", "content": "first segmentsecond segment"},
    ]
    assert loop.saved == 1


def test_feed_events_serializes_generator_error_then_closes_and_autosaves():
    from data_agent.web.blueprints.chat import _feed_events, _sse_response
    from data_agent.web.event_bus import EventQueue

    loop = FailingLoop()
    queue = EventQueue()
    _feed_events(queue, loop, "t_failure", loop.stream_turn("fail safely"))

    response = _sse_response(queue)
    events = list(parse_sse_chunks(response.response))
    assert [event for event, _data in events] == [
        "analysis_progress",
        "error",
        "turn_end",
    ]
    assert events[-2][1] == {"message": "scripted SSE failure"}
    assert events[-1][1]["status"] == "error"
    assert queue._closed is True
    assert list(queue.iter()) == []
    assert loop.saved == 1
