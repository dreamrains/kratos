"""The Web acceptance entry point must not create unbounded auxiliary calls."""

from types import SimpleNamespace

from data_agent.config import get_config
from data_agent.llm import client as llm
from data_agent.web.agent_manager import AgentManager


def _response(text="", reason="length"):
    return SimpleNamespace(
        choices=[SimpleNamespace(
            message=SimpleNamespace(content=text, tool_calls=None), finish_reason=reason,
        )],
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=300),
    )


def test_main_client_does_not_silently_upgrade_output_limit(monkeypatch):
    calls = []
    responses = iter([_response(), _response(), _response("done", "stop")])
    monkeypatch.setattr(llm, "completion", lambda **kw: calls.append(kw) or next(responses))

    result = llm.LLMClient(max_tokens=8000).chat([])

    assert result.text == "" and result.finish_reason == "length"
    assert [call["max_tokens"] for call in calls] == [8000]


def test_web_manager_injects_auxiliary_for_each_new_or_reconstructed_loop(tmp_path, monkeypatch):
    cfg = get_config()
    monkeypatch.setattr(cfg, "workspace_dir", tmp_path / "workspace")
    monkeypatch.setattr(cfg, "sessions_dir", tmp_path / "sessions")
    clients = []

    def factory():
        client = object()
        clients.append(client)
        return client

    manager = AgentManager(auxiliary_client_factory=factory)
    first = manager.get_or_create("first")
    second = manager.get_or_create("second")
    assert manager.get_or_create("first") is first
    manager.remove("first")
    restored = manager.get_or_create("first")

    assert len(clients) == 3
    assert [loop.auxiliary_llm_client for loop in (first, second, restored)] == clients
    assert AgentManager().get_or_create("normal").auxiliary_llm_client.max_tokens == 300
