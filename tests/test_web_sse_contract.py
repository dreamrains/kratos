"""Collected Flask/SSE contracts for the Web chat endpoint.

These deterministic server tests verify the protocol projection only. They do
not replace the actual-browser observation required by release Gate E.
"""

from __future__ import annotations

import json
import threading

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


class UnsavableLoop(ScriptedLoop):
    def _auto_save(self):
        raise OSError("disk unavailable")


class ScriptedManager:
    def __init__(self, loop):
        self.loop = loop

    def get_or_create(self, **_kwargs):
        return self.loop

    def get(self, session_id):
        return self.loop if session_id == self.loop.session_id else None

    def remove(self, _session_id):
        return None


class CheckpointingBlockingLoop(ScriptedLoop):
    session_id = "sse_checkpoint"

    def __init__(self):
        super().__init__()
        self.release = threading.Event()
        self.checkpoints = 0

    def stream_turn(self, message):
        self.messages.append({"role": "user", "content": message})
        yield {
            "type": "analysis_progress",
            "code": "analysis_plan_ready",
            "label": "Analysis plan is ready",
            "status": "finished",
            "step_id": "step_profile",
        }
        assert self.release.wait(timeout=5), "test did not release the stream"
        self.messages.append({"role": "assistant", "content": "persisted answer"})
        yield {"type": "text_delta", "text": "persisted answer"}

    def _stream_checkpoint(self):
        from data_agent.session.history import checkpoint_session

        checkpoint_session(
            self.messages,
            self.session_id,
            start_index=0 if self.checkpoints == 0 else len(self.messages),
        )
        self.checkpoints += 1

    def _auto_save(self):
        from data_agent.session.history import save_session

        save_session(self.messages, self.session_id)
        self.saved += 1


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
        "turn_persisted",
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

    persisted = events[-2][1]
    assert persisted == {
        "session_id": session_id,
        "turn_id": turn_id,
        "status": "persisted",
    }
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
            "turn_persisted",
            {"session_id": "sse_contract", "turn_id": "t_123", "status": "persisted"},
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
        "turn_persisted",
        "turn_end",
    ]
    assert events[-3][1] == {"message": "scripted SSE failure"}
    assert events[-2][1]["status"] == "persisted"
    assert events[-1][1]["status"] == "error"
    assert queue._closed is True
    assert list(queue.iter()) == []
    assert loop.saved == 1


def test_turn_end_is_enqueued_only_after_final_session_save():
    from data_agent.web.blueprints.chat import _feed_events
    from data_agent.web.event_bus import EventQueue

    loop = ScriptedLoop()

    class ObservingQueue(EventQueue):
        saved_when_terminal_was_enqueued = None

        def put(self, event):
            if event.event == "turn_end":
                self.saved_when_terminal_was_enqueued = loop.saved
            super().put(event)

    queue = ObservingQueue()
    _feed_events(queue, loop, "t_saved_first", loop.stream_turn("finish"))

    assert queue.saved_when_terminal_was_enqueued == 1


def test_turn_persisted_is_observable_before_the_terminal_event():
    from data_agent.web.blueprints.chat import _feed_events
    from data_agent.web.event_bus import EventQueue

    loop = ScriptedLoop()
    queue = EventQueue()
    _feed_events(queue, loop, "t_persisted", loop.stream_turn("finish"))
    events = list(parse_sse_chunks(queue.iter()))

    assert [event for event, _data in events][-2:] == [
        "turn_persisted",
        "turn_end",
    ]
    assert events[-2][1] == {
        "session_id": loop.session_id,
        "turn_id": "t_persisted",
        "status": "persisted",
    }


def test_persistence_failure_is_terminal_and_does_not_claim_completion():
    from data_agent.web.blueprints.chat import _feed_events
    from data_agent.web.event_bus import EventQueue

    loop = UnsavableLoop()
    queue = EventQueue()
    _feed_events(queue, loop, "t_unsaved", loop.stream_turn("finish"))
    events = list(parse_sse_chunks(queue.iter()))

    assert [event for event, _data in events][-2:] == [
        "turn_persisted",
        "turn_end",
    ]
    assert events[-2][1]["status"] == "failed"
    assert events[-1][1]["status"] == "persistence_error"


def test_running_session_is_listed_and_reloadable_before_turn_end(app):
    loop = CheckpointingBlockingLoop()
    app.config["agent_manager"] = ScriptedManager(loop)
    stream_client = app.test_client()
    read_client = app.test_client()

    response = stream_client.post(
        "/api/chat",
        json={"message": "checkpoint me"},
        buffered=False,
    )
    event_iter = parse_sse_chunks(response.response)
    assert next(event_iter)[0] == "turn_start"
    assert next(event_iter)[0] == "analysis_progress"

    sessions = read_client.get("/api/sessions").get_json()
    assert [item["session_id"] for item in sessions] == [loop.session_id]
    running = read_client.get(f"/api/sessions/{loop.session_id}").get_json()
    assert running["messages"] == [
        {"role": "user", "content": "checkpoint me"},
    ]

    loop.release.set()
    remaining = list(event_iter)
    assert remaining[-1][0] == "turn_end"
    completed = read_client.get(f"/api/sessions/{loop.session_id}").get_json()
    assert completed["messages"][-1] == {
        "role": "assistant",
        "content": "persisted answer",
    }
