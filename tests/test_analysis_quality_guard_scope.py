from __future__ import annotations

from types import SimpleNamespace

from data_agent.agent.loop import AgentLoop


def _loop_with(tools_used, intent_type="directed_analysis", readiness="ready"):
    loop = AgentLoop(client=None, session_id="quality_guard_scope")
    loop._last_turn_intent = SimpleNamespace(intent_type=intent_type, execution_readiness=readiness)
    loop._turn_tools_used = list(tools_used)
    return loop


def _current_hypothesis_audit(loop, *, hypothesis_id="set_plan_1_h1", delta=10):
    loop.context.analysis_state.analysis_plan = {"id": "plan_1"}
    loop.context.analysis_state.hypothesis_sets = [{
        "id": "set_plan_1", "plan_id": "plan_1", "dataset": "sales",
        "hypotheses": [{
            "id": "set_plan_1_h1", "claim": "销售额发生变化",
            "claim_type": "descriptive", "verification_level": "verifiable",
            "decision_rule": {"metrics": ["amount"], "predicate": "changed"},
        }],
    }]
    loop.context.analysis_state.evidence_records = [{
        "id": "ev_1", "plan_id": "plan_1", "dataset": "sales",
        "measurements": [{"metric": "amount", "delta": delta}],
        "competing_hypotheses": [{
            "hypothesis_id": hypothesis_id, "relation": "supports",
            "metric": "amount", "observed": "increased",
        }],
    }]


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


def test_explicit_hypothesis_task_requires_plan_set_and_structured_relations():
    loop = _loop_with(["compare_periods", "record_evidence_record"])
    loop.context.analysis_state.analysis_plan = None
    loop.context.analysis_state.hypothesis_sets = [{"id": "hypotheses_sales_trend"}]
    loop.context.analysis_state.evidence_records = [{"id": "ev_1"}]

    assert loop._should_continue_for_analysis_quality(
        "请提出并检验至少两种竞争性假设", "prose only",
    ) is True
    loop._inject_analysis_quality_guard()

    guard = loop.messages[-1]["content"]
    assert "<competing_hypothesis_quality_guard>" in guard
    assert "record_analysis_plan" in guard
    assert "structured hypothesis relations" in guard


def test_explicit_hypothesis_task_structural_gate_accepts_complete_audit_presence():
    loop = _loop_with(["record_analysis_plan", "record_evidence_record"])
    _current_hypothesis_audit(loop)

    assert loop._should_continue_for_analysis_quality(
        "请提出并检验至少两种竞争性假设", "structured answer",
    ) is False


def test_r4_relation_alias_does_not_close_current_hypothesis_audit():
    loop = _loop_with(["record_analysis_plan", "record_evidence_record"])
    _current_hypothesis_audit(loop, hypothesis_id="h_trend")

    gaps = loop._competing_hypothesis_quality_gaps("请提出并检验至少两种竞争性假设")
    assert any("host-validated hypothesis relation" in gap for gap in gaps), gaps
    loop._turn_analysis_quality_gaps = gaps
    loop._inject_analysis_quality_guard()
    guard = loop.messages[-1]["content"]
    assert "id=set_plan_1_h1" in guard
    assert "id=h_trend" not in guard


def test_hypothesis_brief_excludes_prior_plan_ids():
    loop = _loop_with(["record_analysis_plan", "record_evidence_record"])
    _current_hypothesis_audit(loop)
    loop.context.analysis_state.hypothesis_sets.insert(0, {
        "id": "set_old", "plan_id": "old_plan", "dataset": "sales",
        "hypotheses": [{"id": "old_h1", "claim": "旧版本解释", "status": "supported"}],
    })

    brief = loop._current_plan_hypothesis_brief()
    assert "id=set_plan_1_h1" in brief
    assert "old_h1" not in brief


def test_guard_round_prompt_replaces_preplan_hypothesis_ids(monkeypatch):
    loop = _loop_with(["record_analysis_plan", "record_evidence_record"])
    _current_hypothesis_audit(loop, hypothesis_id="h_trend")
    loop._turn_synthesis_policy_instruction = (
        "keep the analysis policy\n<competing_hypotheses>\nid=old_h1\n</competing_hypotheses>"
    )
    loop._turn_final_guard_injected = True
    loop._turn_analysis_quality_gaps = ["no current-plan host-validated hypothesis relation exists"]
    monkeypatch.setattr(loop, "_build_system_prompt", lambda: "base prompt")
    monkeypatch.setattr(loop, "_execution_prompt_hint", lambda: "")

    prompt = loop._get_system_prompt()
    assert "keep the analysis policy" in prompt
    assert "id=set_plan_1_h1" in prompt
    assert "id=old_h1" not in prompt


def test_plan_recorded_after_guard_refreshes_existing_hypothesis_producer(monkeypatch):
    from data_agent.agent import trust_workflow_runtime

    loop = _loop_with(["record_analysis_plan"])
    loop._turn_synthesis_policy_injected = True
    loop._turn_final_guard_injected = True
    loop._turn_analysis_quality_gaps = ["no current-plan host-validated hypothesis relation exists"]
    calls = []
    monkeypatch.setattr(
        trust_workflow_runtime, "maybe_create_hypothesis_set",
        lambda user_input, intent, state: calls.append((user_input, intent, state)),
    )

    loop._maybe_inject_synthesis_policy("请提出并检验至少两种竞争性假设")
    assert len(calls) == 1
    assert calls[0][2] is loop.context.analysis_state


def test_relation_shape_with_conflicting_measurement_does_not_close_audit():
    loop = _loop_with(["record_analysis_plan", "record_evidence_record"])
    _current_hypothesis_audit(loop, delta=0)

    gaps = loop._competing_hypothesis_quality_gaps("请提出并检验至少两种竞争性假设")
    assert any("host-validated hypothesis relation" in gap for gap in gaps), gaps


def test_executable_hypothesis_plan_task_ledger_no_longer_blocks_publication(tmp_path, monkeypatch):
    """Contract change (2026-09-21 goal realignment).

    The R20 contract required all projected tasks completed before
    publication; both R21 M04 runs died on that ("analysis_audit_incomplete")
    while carrying honest structured artifacts.  The task ledger is now host
    bookkeeping: unfinished tasks stop blocking the turn and the host closes
    them with an explicit reason at successful publication
    (close_open_tasks_for_publication).  What still blocks is the absence of
    the plan / hypothesis set / structured relations themselves.
    """
    from data_agent.session.task_manager import task_manager

    monkeypatch.setattr(task_manager, "_dir", tmp_path / "tasks")
    monkeypatch.setattr(task_manager, "_next_id_val", 0)
    loop = _loop_with(["record_analysis_plan", "record_evidence_record"])
    analysis_plan_id = "analysis_plan_1"
    workflow = task_manager.create_plan(session_id=loop.session_id, goal="Compare hypotheses")
    task_manager.create(
        "Test H1",
        session_id=loop.session_id,
        plan_id=workflow["id"],
        analysis_plan_id=analysis_plan_id,
        step_id="step_h1",
    )
    loop.context.analysis_state.analysis_plan = {
        "id": "plan_1",
        "method_plan": [{"step_id": "step_h1"}],
    }
    _current_hypothesis_audit(loop)

    # Unfinished projected task: no longer a publication gap.
    gaps = loop._competing_hypothesis_quality_gaps("请提出并检验至少两种竞争性假设")
    assert gaps == [], gaps

    # Missing structured relations still block.
    loop.context.analysis_state.evidence_records = []
    gaps = loop._competing_hypothesis_quality_gaps("请提出并检验至少两种竞争性假设")
    assert any("structured hypothesis relations" in gap for gap in gaps), gaps


def test_explicit_hypothesis_task_rechecks_gaps_after_guard():
    loop = _loop_with(["record_analysis_plan", "record_evidence_record"])
    loop.context.analysis_state.analysis_plan = None
    loop.context.analysis_state.hypothesis_sets = []
    loop.context.analysis_state.evidence_records = []
    loop._turn_analysis_quality_gaps = ["initial gap"]
    loop._inject_analysis_quality_guard()

    assert loop._should_continue_for_analysis_quality(
        "请提出并检验至少两种竞争性假设", "still prose only",
    ) is False
    assert "analysis_audit_incomplete" in loop._analysis_quality_failure_after_guard()
    assert sum(
        "<competing_hypothesis_quality_guard>" in str(message.get("content") or "")
        for message in loop.messages
    ) == 1


def test_complete_repair_clears_post_guard_failure():
    loop = _loop_with(["record_analysis_plan", "record_evidence_record"])
    loop._turn_analysis_quality_gaps = ["initial gap"]
    loop._inject_analysis_quality_guard()
    _current_hypothesis_audit(loop)

    assert loop._should_continue_for_analysis_quality(
        "请提出并检验至少两种竞争性假设", "structured answer",
    ) is False
    assert loop._analysis_quality_failure_after_guard() is None
    assert sum(
        "<competing_hypothesis_quality_guard>" in str(message.get("content") or "")
        for message in loop.messages
    ) == 1


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
