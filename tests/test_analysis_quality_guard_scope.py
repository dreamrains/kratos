from __future__ import annotations

from types import SimpleNamespace

from data_agent.agent.loop import AgentLoop


def _loop_with(tools_used, intent_type="directed_analysis", readiness="ready"):
    loop = AgentLoop(client=None, session_id="quality_guard_scope")
    loop._last_turn_intent = SimpleNamespace(intent_type=intent_type, execution_readiness=readiness)
    loop._turn_tools_used = list(tools_used)
    return loop


def test_guard_triggers_when_only_profiling_and_browsing_tools_were_used():
    # Observed in the authorized R07 journey pilot: the model used list_files,
    # which fell outside the profiling whitelist, so a profile-only final
    # answer slipped past the guard. Any tool use without a substantive
    # analysis tool must still trigger the guard.
    loop = _loop_with(["load_data", "list_files", "describe_dataset"])
    assert loop._should_continue_for_analysis_quality("比较前 15 天与后 15 天收入", "只有数据概况的回答") is True


def test_guard_stays_silent_when_a_substantive_tool_ran():
    loop = _loop_with(["load_data", "compare_periods"])
    assert loop._should_continue_for_analysis_quality("比较收入", "answer") is False


def test_guard_stays_silent_without_any_tool_use():
    loop = _loop_with([])
    assert loop._should_continue_for_analysis_quality("比较收入", "answer") is False


def test_guard_stays_silent_for_non_analysis_intents():
    loop = _loop_with(["load_data"], intent_type="casual_chat")
    assert loop._should_continue_for_analysis_quality("聊聊", "answer") is False


def test_guard_fires_once_per_turn_only():
    loop = _loop_with(["load_data"])
    assert loop._should_continue_for_analysis_quality("比较收入", "answer") is True
    loop._inject_analysis_quality_guard()
    assert loop._should_continue_for_analysis_quality("比较收入", "answer") is False


def _wrap_up_count(loop):
    return sum(
        1
        for message in loop.messages
        if message.get("role") == "system" and "<analysis_wrap_up_guard>" in str(message.get("content") or "")
    )


def _finalization_count(loop):
    return sum(
        1
        for message in loop.messages
        if message.get("role") == "system" and "<analysis_finalization_mode>" in str(message.get("content") or "")
    )


def test_wrap_up_nudge_injects_once_after_the_threshold_round(monkeypatch):
    from data_agent.config import get_config

    monkeypatch.setattr(get_config(), "wrap_up_round", 2)
    loop = AgentLoop(client=None, session_id="wrap_up_nudge_unit")
    loop._reset_turn_tracking()
    loop._maybe_inject_wrap_up(round_num=1)
    assert _wrap_up_count(loop) == 0
    loop._maybe_inject_wrap_up(round_num=2)
    assert _wrap_up_count(loop) == 1
    loop._maybe_inject_wrap_up(round_num=3)
    assert _wrap_up_count(loop) == 1  # once per turn
    assert loop._turn_finalization_mode is False


def test_round_count_keeps_tools_available_even_after_one_success(monkeypatch):
    from data_agent.config import get_config
    from data_agent.llm.client import Response, StreamComplete

    monkeypatch.setattr(get_config(), "wrap_up_round", 2)
    loop = AgentLoop(client=None, session_id="wrap_up_finalization")
    loop._reset_turn_tracking()
    loop._turn_tools_used = ["load_data", "curve_fitting"]
    loop._turn_successful_substantive_tools = {"curve_fitting"}
    loop._maybe_inject_wrap_up(round_num=2)

    assert loop._turn_finalization_mode is False
    assert _finalization_count(loop) == 0
    assert loop._tools_for_current_round() is not None

    class CaptureClient:
        def __init__(self):
            self.tools_seen = []

        def stream_chat_structured(self, **kwargs):
            self.tools_seen.append(kwargs["tools"])
            yield StreamComplete(response=Response(text="基于已有证据收尾"))

    client = CaptureClient()
    loop.client = client
    list(loop._stream_llm_round(3))
    assert client.tools_seen[0] is not None


def test_failed_substantive_tool_does_not_unlock_finalization(monkeypatch):
    from data_agent.config import get_config

    monkeypatch.setattr(get_config(), "wrap_up_round", 1)
    loop = AgentLoop(client=None, session_id="wrap_up_failed_analysis")
    loop._reset_turn_tracking()
    loop._record_turn_tool_result("curve_fitting", '{"error":"insufficient data"}')
    loop._maybe_inject_wrap_up(round_num=1)

    assert loop._turn_finalization_mode is False
    assert _wrap_up_count(loop) == 1


def test_finalization_discards_unexecuted_tool_markup_then_allows_one_direct_answer(monkeypatch):
    from data_agent.llm.client import Response

    loop = AgentLoop(client=None, session_id="wrap_up_tool_markup_recovery")
    original_reset = loop._reset_turn_tracking

    def reset_with_finalization():
        original_reset()
        loop._turn_finalization_mode = True

    loop._reset_turn_tracking = reset_with_finalization
    loop._prepare_analysis_turn = lambda _user_input: None
    loop._ensure_mcp_initialized = lambda: None
    loop._should_continue_for_analysis_quality = lambda *_args: False
    loop._verify_before_publication = lambda *_args: None
    loop._maybe_archive = lambda *_args: None
    loop._auto_save = lambda: None
    calls = []

    def scripted_round(round_num):
        calls.append(round_num)
        if round_num == 1:
            text = '<｜｜DSML｜｜tool_calls><｜｜DSML｜｜invoke name="run_python">'
        else:
            text = "基于已验证结果的直接结论：1818。"
        yield {"type": "text_delta", "text": text, "turn_id": None}
        yield {"type": "_response", "response": Response(text=text), "streamed_text": text}

    loop._stream_llm_round = scripted_round
    events = list(loop.stream_turn("分析数据"))
    published = "".join(str(event.get("text") or "") for event in events if event.get("type") == "text_delta")

    assert calls == [1, 2]
    assert "1818" in published
    assert "DSML" not in published
    assert _finalization_count(loop) == 0
    assert any("<analysis_finalization_recovery>" in str(message.get("content") or "") for message in loop.messages)
    assert not [event for event in events if event.get("type") == "error"]


def test_finalization_tool_markup_recovery_is_bounded():
    loop = AgentLoop(client=None, session_id="wrap_up_tool_markup_bound")
    loop._reset_turn_tracking()

    assert loop._contains_unexecuted_tool_markup('<｜｜DSML｜｜tool_calls>') is True
    assert loop._contains_unexecuted_tool_markup('"tool_calls": []') is True
    assert loop._contains_unexecuted_tool_markup("直接给出结论") is False
    assert loop._recover_finalization_tool_markup() is True
    assert loop._recover_finalization_tool_markup() is False


def test_wrap_up_nudge_can_be_disabled(monkeypatch):
    from data_agent.config import get_config

    monkeypatch.setattr(get_config(), "wrap_up_round", None)
    loop = AgentLoop(client=None, session_id="wrap_up_nudge_disabled")
    loop._reset_turn_tracking()
    for round_num in range(1, 12):
        loop._maybe_inject_wrap_up(round_num=round_num)
    assert _wrap_up_count(loop) == 0


def test_wrap_up_nudge_resets_between_turns(monkeypatch):
    from data_agent.config import get_config

    monkeypatch.setattr(get_config(), "wrap_up_round", 1)
    loop = AgentLoop(client=None, session_id="wrap_up_nudge_reset")
    loop._reset_turn_tracking()
    loop._maybe_inject_wrap_up(round_num=1)
    assert _wrap_up_count(loop) == 1
    loop._reset_turn_tracking()
    loop._maybe_inject_wrap_up(round_num=1)
    assert _wrap_up_count(loop) == 2


def test_streaming_turn_wraps_up_long_tool_loops(monkeypatch):
    from data_agent.config import get_config
    from data_agent.llm.client import Response, ToolCall

    monkeypatch.setattr(get_config(), "wrap_up_round", 2)
    loop = AgentLoop(client=None, session_id="wrap_up_integration")

    def scripted_round(round_num):
        if round_num >= 3:
            seen = any(
                "<analysis_wrap_up_guard>" in str(message.get("content") or "")
                for message in loop.messages
            )
            text = f"wrap-up visible before round 3: {seen}"
            # The loop publishes final answers through delta events.
            yield {"type": "text_delta", "text": text, "turn_id": None}
            yield {
                "type": "_response",
                "response": Response(text=text),
                "streamed_text": text,
            }
            return
        yield {
            "type": "_response",
            "response": Response(
                tool_calls=[ToolCall(id=f"c{round_num}", name="list_data", arguments={})],
                finish_reason="tool_calls",
            ),
            "streamed_text": "",
        }

    loop._stream_llm_round = scripted_round
    events = list(loop.stream_turn("分析数据"))
    streamed = "".join(str(event.get("text") or "") for event in events if event.get("type") == "text_delta")
    assert "wrap-up visible before round 3: True" in streamed
    assert not [event for event in events if event.get("type") == "error"]
