from pathlib import Path

import data_agent.config as config_module
import data_agent.agent.intent as intent_module
from data_agent.agent.loop import AgentLoop
from data_agent.agent.prompts import build_system_prompt
from data_agent.config import AgentConfig
from data_agent.tools import knowledge_tools


def test_tools_create_search_memory_and_prompt_context(tmp_path: Path, monkeypatch):
    cfg = AgentConfig(WORKSPACE_DIR=tmp_path / "workspace", SESSIONS_DIR=tmp_path / "sessions")
    monkeypatch.setattr(config_module, "_config", cfg)
    knowledge_tools.reset_knowledge_services_for_tests()

    created = knowledge_tools.create_knowledge_item(
        title="GMV definition",
        domain="ecommerce",
        content="GMV excludes canceled orders.",
        summary="GMV rule",
        tags=["metric"],
    )
    assert created["title"] == "GMV definition"

    results = knowledge_tools.search_knowledge("canceled", domain="ecommerce")
    assert results[0]["id"] == created["id"]

    memory = knowledge_tools.create_memory_candidate(
        text="Use net revenue for ecommerce revenue analysis.",
        summary="Net revenue preference.",
        memory_type="domain_fact",
        confidence=0.7,
        domain="ecommerce",
    )
    knowledge_tools.confirm_memory(memory["id"])

    prompt = knowledge_tools.retrieve_knowledge_context("net revenue", domain="ecommerce")
    assert "<memory_hints" in prompt


class _FakeIntent:
    intent_type = "directed_analysis"

    def to_dict(self):
        return {"intent_type": self.intent_type, "ambiguities": []}


def test_prompt_wraps_dynamic_context_without_project_knowledge_label(monkeypatch):
    monkeypatch.setattr(intent_module, "plan_turn_intent", lambda *_args, **_kwargs: _FakeIntent())

    prompt = build_system_prompt(
        tool_list="search_knowledge",
        domain_knowledge="<retrieved_knowledge>GMV rule</retrieved_knowledge>",
        user_input="分析 GMV",
    )

    assert "<retrieved_context>" in prompt
    assert "<project_knowledge>" not in prompt


def test_agent_loop_uses_recent_user_message_for_retrieval_query():
    loop = AgentLoop(client=object(), session_id="s1", project_name="demo")
    loop.messages = [
        {"role": "user", "content": "旧问题"},
        {"role": "assistant", "content": "回答"},
        {"role": "user", "content": "请按 GMV 分析成交表现"},
    ]

    assert loop._build_retrieval_query(loop.messages) == "请按 GMV 分析成交表现"
