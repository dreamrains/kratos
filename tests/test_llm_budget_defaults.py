from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from data_agent.config import AgentConfig
from data_agent.llm import client as client_module


def _capture_completion(captured):
    def fake_completion(**kwargs):
        captured.update(kwargs)
        msg = SimpleNamespace(content="ok", tool_calls=None, reasoning_content="")
        return SimpleNamespace(choices=[SimpleNamespace(message=msg, finish_reason="stop")])

    return fake_completion


def test_max_tokens_defaults_to_none_and_the_request_omits_it(monkeypatch):
    monkeypatch.delenv("MAX_TOKENS", raising=False)
    cfg = AgentConfig(_env_file=None)
    assert cfg.max_tokens is None

    captured: dict = {}
    with patch.object(client_module, "completion", _capture_completion(captured)):
        with patch.object(client_module, "get_config", lambda: cfg):
            client = client_module.LLMClient(model_id="test/model")
            client.chat(messages=[{"role": "user", "content": "hi"}])
    assert client.max_tokens is None
    assert "max_tokens" not in captured


def test_explicit_max_tokens_still_overrides_and_is_sent(monkeypatch):
    cfg = AgentConfig(_env_file=None)
    captured: dict = {}
    with patch.object(client_module, "completion", _capture_completion(captured)):
        with patch.object(client_module, "get_config", lambda: cfg):
            client = client_module.LLMClient(model_id="test/model", max_tokens=2000)
            client.chat(messages=[{"role": "user", "content": "hi"}])
    assert client.max_tokens == 2000
    assert captured["max_tokens"] == 2000


def test_configured_max_tokens_env_override_is_sent(monkeypatch):
    monkeypatch.setenv("MAX_TOKENS", "6000")
    cfg = AgentConfig(_env_file=None)
    captured: dict = {}
    with patch.object(client_module, "completion", _capture_completion(captured)):
        with patch.object(client_module, "get_config", lambda: cfg):
            client_module.LLMClient(model_id="test/model").chat(messages=[{"role": "user", "content": "hi"}])
    assert captured["max_tokens"] == 6000


@pytest.mark.parametrize("bad", [50, 200000])
def test_explicit_max_tokens_out_of_range_is_rejected(monkeypatch, bad):
    monkeypatch.setenv("MAX_TOKENS", str(bad))
    with pytest.raises(Exception):
        AgentConfig(_env_file=None)
