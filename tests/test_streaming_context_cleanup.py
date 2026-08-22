from __future__ import annotations

import pytest

from data_agent.agent.context import AgentContext, get_current_context, use_agent_context
from data_agent.agent.loop import AgentLoop, SuspendedForConfirmation
from data_agent.llm.client import Response
from data_agent.session.workspace import Workspace


def _configure_single_round_stream(monkeypatch, loop: AgentLoop, *, raises: bool) -> None:
    monkeypatch.setattr(loop, "_prepare_analysis_turn", lambda _user_input: None)
    monkeypatch.setattr(loop, "_maybe_auto_suspend_for_required_question", lambda: None)
    monkeypatch.setattr(loop, "_ensure_mcp_initialized", lambda: None)
    monkeypatch.setattr(loop, "_is_analysis_quality_guard_candidate", lambda: False)
    monkeypatch.setattr(loop, "_runtime_confirmation_checkpoint", lambda: None)
    monkeypatch.setattr(loop, "_maybe_archive", lambda _user_input, _final_text: None)
    monkeypatch.setattr(loop, "_auto_save", lambda: None)

    def stream_round(_round_num):
        yield {"type": "text_delta", "text": "chunk"}
        if raises:
            raise RuntimeError("stream exploded")
        yield {
            "type": "_response",
            "response": Response(text="chunk"),
            "streamed_text": "chunk",
        }

    monkeypatch.setattr(loop, "_stream_llm_round", stream_round)


def _configure_resume(monkeypatch, loop: AgentLoop) -> None:
    suspension = SuspendedForConfirmation(
        suspension_id="confirmation-1",
        confirmation_id="confirmation-1",
        question="Continue?",
        options=[],
        context="",
        snapshot={},
    )
    monkeypatch.setattr(loop, "_load_confirmation_for_resume", lambda _suspension_id: suspension)
    monkeypatch.setattr(loop, "_resolve_runtime_confirmation", lambda susp, *_args, **_kwargs: susp)
    monkeypatch.setattr(loop, "_build_resume_user_input", lambda _susp, response: response)


@pytest.mark.parametrize("method", ["stream_turn", "resume_turn_streaming"])
@pytest.mark.parametrize("termination", ["exhaustion", "close", "exception"])
@pytest.mark.parametrize("outer_context", [False, True], ids=["no-current", "restore-outer"])
def test_streaming_context_is_bound_only_while_generator_runs(
    monkeypatch,
    method,
    termination,
    outer_context,
):
    loop = AgentLoop(client=object(), session_id=f"stream-{method}-{termination}")
    _configure_single_round_stream(monkeypatch, loop, raises=termination == "exception")
    if method == "resume_turn_streaming":
        _configure_resume(monkeypatch, loop)
    outer = AgentContext(session_id="outer", workspace=Workspace()) if outer_context else None

    def exercise():
        assert get_current_context() is outer
        if method == "stream_turn":
            events = loop.stream_turn("hello")
        else:
            events = loop.resume_turn_streaming("confirmation-1", "yes")

        assert get_current_context() is outer
        first = next(events)
        assert first == {"type": "text_delta", "text": "chunk"}
        assert get_current_context() is loop.context

        if termination == "close":
            events.close()
        elif termination == "exception":
            with pytest.raises(RuntimeError, match="stream exploded"):
                next(events)
        else:
            assert list(events) == []

        assert get_current_context() is outer

    if outer is None:
        exercise()
    else:
        with use_agent_context(outer):
            exercise()

    assert get_current_context() is None
