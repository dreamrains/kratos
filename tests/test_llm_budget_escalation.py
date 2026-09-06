from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from data_agent.llm import client as client_module
from data_agent.llm.client import LLMClient, Response
from data_agent.llm.request_policy import RequestPolicy


def _litellm_response(text: str, finish: str, completion_tokens: int | None = None):
    message = SimpleNamespace(content=text, tool_calls=None, reasoning_content="think" * 400)
    usage = SimpleNamespace(completion_tokens=completion_tokens) if completion_tokens is not None else None
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message, finish_reason=finish)],
        usage=usage,
    )


def _client(max_tokens=None):
    return LLMClient(model_id="test/model", max_tokens=max_tokens, temperature=0.0,
                     request_policy=RequestPolicy(max_attempts=3, output_token_limits=(8000, 32000)))


def test_chat_escalates_budget_when_reasoning_exhausts_the_output():
    calls: list = []

    def scripted(**kwargs):
        calls.append(kwargs.get("max_tokens"))
        if len(calls) == 1:
            return _litellm_response("", "length", completion_tokens=1981)
        return _litellm_response("final answer", "stop", completion_tokens=50)

    with patch.object(client_module, "completion", scripted):
        response = _client(max_tokens=2000).chat([{"role": "user", "content": "q"}])
    assert response.text == "final answer"
    assert response.finish_reason == "stop"
    # Explicit-budget ladder: one deterministic ×4 rung above the frozen value.
    assert calls == [2000, 8000]


def test_chat_escalation_is_bounded_and_returns_the_last_truncated_response():
    calls: list = []

    def always_truncated(**kwargs):
        calls.append(kwargs.get("max_tokens"))
        return _litellm_response("", "length", completion_tokens=8000)

    with patch.object(client_module, "completion", always_truncated):
        response = _client(max_tokens=2000).chat([{"role": "user", "content": "q"}])
    assert len(calls) == 3  # one original attempt plus at most two escalations
    assert calls == [2000, 8000, 32000]
    assert response.finish_reason == "length"
    assert response.text == ""


def test_chat_does_not_touch_a_complete_response():
    calls: list = []

    def fine(**kwargs):
        calls.append(kwargs.get("max_tokens"))
        return _litellm_response("answer", "stop", completion_tokens=20)

    with patch.object(client_module, "completion", fine):
        response = _client(max_tokens=2000).chat([{"role": "user", "content": "q"}])
    assert calls == [2000]
    assert response.text == "answer"


def test_chat_returns_partial_text_truncation_without_escalation():
    calls: list = []

    def partial(**kwargs):
        calls.append(kwargs.get("max_tokens"))
        return _litellm_response("partial answer", "length", completion_tokens=2000)

    with patch.object(client_module, "completion", partial):
        response = _client(max_tokens=2000).chat([{"role": "user", "content": "q"}])
    assert calls == [2000]
    assert response.text == "partial answer"
    assert response.finish_reason == "length"


def test_explicit_policy_supplies_the_rung_when_budget_is_omitted(monkeypatch):
    monkeypatch.delenv("MAX_TOKENS", raising=False)
    from data_agent.config import AgentConfig

    cfg = AgentConfig(_env_file=None)
    calls: list = []

    def scripted(**kwargs):
        calls.append(kwargs.get("max_tokens"))
        if len(calls) == 1:
            return _litellm_response("", "length", completion_tokens=4000)
        return _litellm_response("ok", "stop", completion_tokens=10)

    with patch.object(client_module, "completion", scripted):
        with patch.object(client_module, "get_config", lambda: cfg):
            response = client_module.LLMClient(model_id="test/model", request_policy=RequestPolicy(max_attempts=2, output_token_limits=(16000,))).chat([{"role": "user", "content": "q"}])
    assert calls == [None, 16000]
    assert response.text == "ok"


def _stream_chunks(text: str, finish: str, completion_tokens: int | None = None):
    def fake_completion(**kwargs):
        def generator():
            if not text:
                yield SimpleNamespace(choices=[SimpleNamespace(
                    delta=SimpleNamespace(content=None, tool_calls=None, reasoning_content="reasoning"),
                    finish_reason=None,
                )])
            else:
                yield SimpleNamespace(choices=[SimpleNamespace(
                    delta=SimpleNamespace(content=text, tool_calls=None, reasoning_content=None),
                    finish_reason=None,
                )])
            yield SimpleNamespace(choices=[SimpleNamespace(
                delta=SimpleNamespace(content=None, tool_calls=None, reasoning_content=None),
                finish_reason=finish,
            )])

        return generator()

    return fake_completion


def test_stream_propagates_the_real_finish_reason():
    with patch.object(client_module, "completion", _stream_chunks("answer", "length")):
        events = list(_client(max_tokens=2000).stream_chat_structured([{"role": "user", "content": "q"}]))
    complete = events[-1]
    assert complete.response.text == "answer"
    assert complete.response.finish_reason == "length"


def test_stream_restarts_only_with_an_explicit_output_policy():
    calls: list = []

    def scripted(**kwargs):
        calls.append(kwargs.get("max_tokens"))
        if len(calls) == 1:
            return _stream_chunks("", "length")(**kwargs)
        return _stream_chunks("recovered answer", "stop")(**kwargs)

    with patch.object(client_module, "completion", scripted):
        events = list(_client(max_tokens=2000).stream_chat_structured([{"role": "user", "content": "q"}]))
    text_events = [event for event in events if event.__class__.__name__ == "StreamTextDelta"]
    complete = events[-1]
    assert [event.text for event in text_events] == ["recovered answer"]
    assert complete.response.finish_reason == "stop"
    assert calls == [2000, 8000]


def test_stream_does_not_restart_after_partial_text_was_published():
    calls: list = []

    def partial(**kwargs):
        calls.append(kwargs.get("max_tokens"))
        return _stream_chunks("partial text", "length")(**kwargs)

    with patch.object(client_module, "completion", partial):
        events = list(_client(max_tokens=2000).stream_chat_structured([{"role": "user", "content": "q"}]))
    complete = events[-1]
    assert complete.response.text == "partial text"
    assert complete.response.finish_reason == "length"
    assert len(calls) == 1


def test_streaming_turn_reports_budget_truncation_explicitly(tmp_path, monkeypatch):
    from data_agent.agent.loop import AgentLoop
    from data_agent.llm.client import Response

    loop = AgentLoop(client=None, session_id="budget_truncation_guard")

    def truncated_round(_round_num):
        yield {
            "type": "_response",
            "response": Response(text="", finish_reason="length", reasoning_content="r" * 100),
            "streamed_text": "",
        }

    loop._stream_llm_round = truncated_round
    events = list(loop.stream_turn("分析订单与付费关系"))
    errors = [event for event in events if event.get("type") == "error"]
    assert len(errors) == 1
    assert "输出预算" in errors[0]["message"]
    assert "MAX_TOKENS" in errors[0]["message"]
