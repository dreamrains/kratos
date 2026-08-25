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
