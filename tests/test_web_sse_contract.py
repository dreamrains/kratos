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
    types = [event for event, _data in events]

    assert response.status_code == 200
    assert response.mimetype == "text/event-stream"
    assert response.headers["X-Accel-Buffering"] == "no"
    assert types == [
        "turn_start",
        "analysis_progress",
        "text_delta",
        "text_delta",
        "turn_end",
    ]
    assert events[1][1] == {
        "code": "analysis_plan_ready",
        "label": "Analysis plan is ready",
        "status": "finished",
        "step_id": "step_profile",
        "phase": "",
    }
    assert "finding" not in events[1][1]
    assert events[-1][1]["status"] == "completed"

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
