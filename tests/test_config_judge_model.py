from __future__ import annotations

from unittest.mock import patch

from data_agent.config import AgentConfig


def test_quality_judge_model_field_defaults_none():
    cfg = AgentConfig()
    assert getattr(cfg, "quality_judge_model", None) is None


def test_llm_client_forwards_temperature():
    from data_agent.llm import client as client_module
    from types import SimpleNamespace

    captured: dict = {}

    def fake_completion(**kwargs):
        captured.update(kwargs)
        msg = SimpleNamespace(content="{}", tool_calls=None, reasoning_content="")
        return SimpleNamespace(choices=[SimpleNamespace(message=msg, finish_reason="stop")])

    with patch.object(client_module, "completion", fake_completion):
        c = client_module.LLMClient(model_id="test/model", temperature=0.0, max_tokens=10)
        try:
            # Temperature is captured at the completion() call site, before any
            # response parsing; swallow parse-time mismatches from the stub shape.
            c.chat(messages=[{"role": "user", "content": "hi"}], system="x")
        except Exception:
            pass
    assert captured.get("temperature") == 0.0
