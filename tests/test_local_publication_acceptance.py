import traceback

import pytest

from data_agent.llm.client import StreamComplete
from scripts.acceptance.local_publication_synthesis_web import (
    _LocalPublicationClient,
    _LocalPublicationManager,
    _forbid_default_provider_calls,
)


def _stream_response(client, tools):
    events = list(client.stream_chat_structured(messages=[], tools=tools, system="main"))
    return next(event.response for event in events if isinstance(event, StreamComplete))


def test_auxiliary_calls_do_not_consume_the_deterministic_main_journey():
    client = _LocalPublicationClient()
    offered_tools = [{"type": "function", "function": {"name": "placeholder"}}]

    auxiliary = client.chat(messages=[{"role": "user", "content": "classify"}], system="json")
    first = _stream_response(client, offered_tools)
    client.chat(messages=[{"role": "user", "content": "extract requirements"}], system="json")
    second = _stream_response(client, offered_tools)
    third = _stream_response(client, offered_tools)
    final = _stream_response(client, offered_tools)

    assert auxiliary.text == ""
    assert [call.name for call in first.tool_calls] == ["load_data"]
    assert [call.name for call in second.tool_calls] == ["compare_periods"]
    assert [call.name for call in third.tool_calls] == ["record_evidence_record"]
    assert final.text
    assert client.main_rounds_served == 4
    assert client.allow_stream_sync_fallback is False


def test_local_web_manager_routes_auxiliary_hooks_to_the_same_zero_provider_client(monkeypatch):
    captured = {}

    def fake_agent_loop(*, client, auxiliary_llm_client, session_id):
        captured.update({
            "client": client,
            "auxiliary_llm_client": auxiliary_llm_client,
            "session_id": session_id,
        })
        return object()

    monkeypatch.setattr("data_agent.agent.loop.AgentLoop", fake_agent_loop)
    monkeypatch.setattr("data_agent.agent.loop.set_interaction_mode", lambda _mode: None)

    manager = _LocalPublicationManager()
    manager.get_or_create("isolated_local_web")

    assert captured["client"] is captured["auxiliary_llm_client"]
    assert isinstance(captured["client"], _LocalPublicationClient)
    assert captured["client"].provider_calls == 0
    assert captured["session_id"] == "isolated_local_web"


def test_local_web_acceptance_fails_fast_on_any_default_provider_call(monkeypatch):
    from data_agent.llm.client import LLMClient

    monkeypatch.setattr(LLMClient, "chat", LLMClient.chat)
    monkeypatch.setattr(LLMClient, "stream_chat_structured", LLMClient.stream_chat_structured)
    monkeypatch.setattr(traceback, "print_stack", lambda **_kwargs: None)
    _forbid_default_provider_calls()

    client = LLMClient()
    with pytest.raises(RuntimeError, match="forbids default Provider"):
        client.chat([])
