"""P08-04: assistant tool_calls / tool results stay paired everywhere.

M04 repro shape: v1 analysis with tools → same-name dataset reloaded as v2 →
next request must not produce an orphan tool message for the Provider. Unit
coverage: validation catches orphans, provider copy drops them without
touching history, and the suspension serializer preserves pairing fields.
"""

from data_agent.agent.compact import (
    drop_orphan_tool_messages,
    validate_tool_message_sequence,
)


def _assistant_with_calls(*call_ids):
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {"id": call_id, "type": "function",
             "function": {"name": "list_data", "arguments": "{}"}}
            for call_id in call_ids
        ],
    }


def _tool_result(call_id, content="ok"):
    return {"role": "tool", "tool_call_id": call_id, "content": content}


def test_valid_sequence_passes():
    messages = [
        {"role": "user", "content": "分析"},
        _assistant_with_calls("a", "b"),
        _tool_result("a"),
        _tool_result("b"),
        {"role": "assistant", "content": "结论"},
    ]
    assert validate_tool_message_sequence(messages) == []


def test_orphan_tool_result_is_a_violation():
    messages = [
        {"role": "user", "content": "分析"},
        _tool_result("ghost"),
    ]
    violations = validate_tool_message_sequence(messages)
    assert any("ghost" in violation and "orphan" in violation for violation in violations)


def test_missing_tool_result_is_a_violation():
    messages = [
        _assistant_with_calls("a", "b"),
        _tool_result("a"),
    ]
    violations = validate_tool_message_sequence(messages)
    assert any("b" in violation and "no tool result" in violation for violation in violations)


def test_tool_message_without_id_is_a_violation():
    messages = [{"role": "tool", "content": "ok"}]
    assert any("without tool_call_id" in violation for violation in validate_tool_message_sequence(messages))


def test_provider_copy_drops_orphans_but_keeps_history_intact():
    history = [
        {"role": "user", "content": "v1 分析"},
        _assistant_with_calls("a", "b"),
        _tool_result("a"),
        _tool_result("b"),
        {"role": "assistant", "content": "v1 结论"},
        # 模拟版本重载/恢复后产生的孤立工具消息
        _tool_result("orphan_1"),
        {"role": "user", "content": "v2 竞争性假设"},
    ]

    provider_copy, dropped = drop_orphan_tool_messages(history)

    assert dropped == ["orphan_1"]
    assert len(provider_copy) == len(history) - 1
    assert any(m.get("tool_call_id") == "orphan_1" for m in history)  # 原始历史不删
    assert validate_tool_message_sequence(provider_copy) == []


def test_m04_version_reload_turn_recovers_instead_of_provider_400():
    """端到端：恢复含孤立 tool 消息的会话，下一轮不得把非法序列发给 Provider。"""
    from types import SimpleNamespace

    from data_agent.agent.loop import AgentLoop

    delivered = []

    class RecordingClient:
        def chat(self, messages, tools=None, system=None):
            delivered.append(messages)
            from data_agent.llm.client import Response

            return Response(text="v2 竞争性假设已处理。")

    loop = AgentLoop(client=RecordingClient(), session_id="p08_m04_protocol")
    loop._reset_turn_tracking()
    # 构造 v1 工具轮完成后的历史 + 版本重载后的孤立工具消息
    loop.messages = [
        {"role": "user", "content": "v1 分析"},
        _assistant_with_calls("v1_a"),
        _tool_result("v1_a"),
        {"role": "assistant", "content": "v1 结论"},
        _tool_result("orphan_after_reload"),
        {"role": "user", "content": "请提出并检验至少两种竞争性假设"},
    ]
    loop._prepare_analysis_turn = lambda _user_input: None
    loop._maybe_auto_suspend_for_required_question = lambda: None
    loop._maybe_archive = lambda *_args: None
    loop._auto_save = lambda: None

    result = loop.run_turn("请提出并检验至少两种竞争性假设")

    assert delivered, "本轮应完成一次合法 Provider 投递"
    for messages in delivered:
        assert validate_tool_message_sequence(messages) == [], "投递序列必须成对完整"
        assert not any(m.get("tool_call_id") == "orphan_after_reload" for m in messages)
    # 原始会话历史仍保留该消息（审计不删）
    assert any(m.get("tool_call_id") == "orphan_after_reload" for m in loop.messages)
    assert "v2 竞争性假设" in result or result


def test_serializer_preserves_pairing_fields():
    from data_agent.agent.loop import AgentLoop

    loop = AgentLoop(client=None, session_id="p08_serializer")
    loop.messages = [
        {"role": "user", "content": "分析"},
        _assistant_with_calls("a"),
        _tool_result("a", "result body"),
    ]

    serialized = loop._serialize_messages()

    assert serialized[1].get("tool_calls")
    assert serialized[1]["tool_calls"][0]["id"] == "a"
    assert serialized[1]["tool_calls"][0]["function"]["name"] == "list_data"
    assert serialized[2].get("tool_call_id") == "a"
    assert validate_tool_message_sequence(serialized) == []
