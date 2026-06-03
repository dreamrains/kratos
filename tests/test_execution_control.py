import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from data_agent.agent.analysis_flow_controller import AnalysisFlowController
from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.context import AgentContext, use_agent_context
from data_agent.agent.execution_control import (
    BudgetExceeded,
    ToolExecutionBudget,
    TurnExecutionState,
)
from data_agent.agent.intent import TurnIntent, plan_turn_intent
from data_agent.llm.client import Response, ToolCall
from data_agent.agent.loop import AgentLoop
from data_agent.session.task_manager import task_manager
from data_agent.session.workspace import Workspace


def _loaded_context() -> str:
    return "- main: 20 rows x 4 cols, columns: date, revenue, cost, user_id"


def test_budget_soft_and_hard_thresholds():
    state = TurnExecutionState(ToolExecutionBudget(profile="interactive", max_tool_calls=6, max_fallback_calls=2))

    state.record_tool_call("list_data", {})
    state.record_tool_call("describe_dataset", {})
    # run_python counts toward tool_calls and sets pending_fallback_resolution
    state.record_tool_call("run_python", {})
    # record_evidence_record is meta, does NOT count toward tool_calls, but resolves fallback
    state.record_tool_call("record_evidence_record", {})

    assert state.tool_calls == 3  # list_data + describe_dataset + run_python
    assert state.pending_fallback_resolution is False

    state.record_tool_call("create_chart", {})
    state.record_tool_call("preview_data", {})
    # tool_calls = 5, ceil(6*0.75) = 5 → should_converge
    assert state.should_converge is True
    assert state.should_restrict_exploration is False

    state.record_tool_call("analyze_time_series", {})
    assert state.should_restrict_exploration is True  # 6 >= ceil(6*0.85) = 6

    try:
        state.ensure_can_call("list_data", {})
    except BudgetExceeded as exc:
        assert "tool call budget" in str(exc).lower()
    else:
        raise AssertionError("expected hard budget to stop further tool calls")


def test_chart_calls_are_not_limited_by_chart_count():
    state = TurnExecutionState(ToolExecutionBudget(profile="analysis", max_tool_calls=20, max_fallback_calls=2))

    for idx in range(8):
        args = {"chart_type": "bar", "data": "pay", "x_col": "month", "y_col": f"metric_{idx}"}
        state.ensure_can_call("create_chart", args)
        state.record_tool_call("create_chart", args)
        state.record_tool_success()

    assert state.chart_calls == 8
    assert state.should_restrict_exploration is False


def test_duplicate_chart_call_is_treated_as_low_value_exploration():
    state = TurnExecutionState(ToolExecutionBudget(profile="analysis", max_tool_calls=20))
    args = {"chart_type": "bar", "data": "pay", "x_col": "month", "y_col": "revenue"}

    state.ensure_can_call("create_chart", args)
    state.record_tool_call("create_chart", args)
    state.record_tool_success()

    try:
        state.ensure_can_call("create_chart", args)
    except BudgetExceeded as exc:
        assert "duplicate" in str(exc).lower() or "low-value" in str(exc).lower()
    else:
        raise AssertionError("expected duplicate chart to be blocked")


def test_elapsed_time_budget_blocks_more_tools():
    state = TurnExecutionState(ToolExecutionBudget(profile="analysis", max_elapsed_seconds=1))
    state.started_at -= 2

    try:
        state.ensure_can_call("list_data", {})
    except BudgetExceeded as exc:
        assert "time budget" in str(exc).lower()
    else:
        raise AssertionError("expected elapsed time budget to block tool calls")


def test_large_tool_output_is_persisted_before_llm_context(tmp_path, monkeypatch):
    from data_agent.agent.compact import persist_large_output
    from data_agent.config import get_config

    monkeypatch.setattr(get_config(), "sessions_dir", tmp_path / "sessions")
    output = persist_large_output("large_output", "tc_big", "x" * 20000)

    assert "<persisted-output>" in output
    assert len(output) < 3000
    assert (tmp_path / "sessions" / "large_output" / "tool_outputs" / "tc_big.txt").exists()


def test_run_python_success_requires_resolution_before_more_exploration():
    state = TurnExecutionState(ToolExecutionBudget(profile="analysis", max_tool_calls=20))

    state.ensure_can_call("run_python", {"purpose": "unsupported custom check", "code": "1 + 1"})
    state.record_tool_call("run_python", {"purpose": "unsupported custom check", "code": "1 + 1"})
    state.record_tool_success()

    try:
        state.ensure_can_call("preview_data", {"name": "main"})
    except BudgetExceeded as exc:
        assert "fallback python result" in str(exc).lower()
    else:
        raise AssertionError("expected fallback result to require evidence or limitation resolution")

    state.ensure_can_call("record_evidence_record", {"record_json": "{}"})


def test_repeated_tool_error_is_blocked_after_two_failures():
    state = TurnExecutionState(ToolExecutionBudget())
    args = {"name": "main", "target_col": "missing"}

    state.record_tool_error("forecast", args, '{"error":"column missing"}')
    state.record_tool_error("forecast", args, '{"error":"column missing"}')

    try:
        state.ensure_can_call("forecast", args)
    except BudgetExceeded as exc:
        assert "repeated tool error" in str(exc).lower()
    else:
        raise AssertionError("expected repeated forecast error to be blocked")


def test_high_risk_gate_blocks_causal_and_creates_confirmation_task(tmp_path):
    old_task_dir = task_manager._dir
    old_next_id = task_manager._next_id_val
    task_manager._dir = tmp_path / "tasks"
    task_manager._next_id_val = 0
    try:
        state = AnalysisSessionState(session_id="gate_savings", project_name=None)
        intent = plan_turn_intent("evaluate whether the savings card is worth long-term operation", _loaded_context())
        intent.intent_type = "directed_analysis"
        intent.data_state = "data_loaded"

        controller = AnalysisFlowController("gate_savings")
        controller.prepare_turn(state, intent, user_input="evaluate whether the savings card is worth long-term operation", dataset_profile=_loaded_context())

        assert controller.is_capability_blocked_by_confirmation(state, "analysis.causal") is True
        assert controller.is_capability_blocked_by_confirmation(state, "data.profile") is False

        tasks = task_manager.list_for_scope(session_id="gate_savings")
        assert any(t.get("node_type") == "confirmation" for t in tasks)
        assert any(t.get("confirmation_policy", {}).get("requires_confirmation") for t in tasks)
    finally:
        task_manager._dir = old_task_dir
        task_manager._next_id_val = old_next_id


def test_confirmation_gate_ignores_tools_without_capability_metadata():
    state = AnalysisSessionState(session_id="gate_unknown_tool")
    state.analysis_spec = {
        "confirmation_policy": {"requires_confirmation": True},
        "method_plan": [{"required_capability": "analysis.causal", "node_type": "analysis"}],
    }
    state.pending_confirmations = [{"id": "method_gate", "status": "pending"}]

    controller = AnalysisFlowController("gate_unknown_tool")

    assert controller.is_tool_blocked_by_confirmation(state, "list_files") is False


class _OneToolClient:
    def __init__(self, tool_name: str, args: dict):
        self._calls = [
            Response(tool_calls=[ToolCall("tc1", tool_name, args)]),
            Response(text="done"),
        ]

    def chat(self, messages, tools=None, system=None):
        if not self._calls:
            return Response(text="done")
        return self._calls.pop(0)


class _EvidenceThenFinalClient:
    def __init__(self):
        evidence = {
            "claim": "retention follows a power-law decay curve",
            "dataset": "main",
            "method": "log-linear retention formula fit",
            "tool_calls": ["run_python"],
            "result_summary": "R(t)=0.1917*t^(-0.7335) describes the observed retention curve.",
            "limitations": ["aggregate retention data only"],
            "confidence": "high",
        }
        self.system_prompts = []
        self._calls = [
            Response(tool_calls=[ToolCall("tc1", "record_evidence_record", {"record_json": json.dumps(evidence)})]),
            Response(text="final answer"),
        ]

    def chat(self, messages, tools=None, system=None):
        self.system_prompts.append(system or "")
        if not self._calls:
            return Response(text="final answer")
        return self._calls.pop(0)


def test_loop_blocks_high_risk_tool_when_confirmation_pending(tmp_path):
    old_task_dir = task_manager._dir
    old_next_id = task_manager._next_id_val
    task_manager._dir = tmp_path / "tasks"
    task_manager._next_id_val = 0
    workspace_obj = Workspace()
    ctx = AgentContext(session_id="loop_gate", workspace=workspace_obj)
    state = AnalysisSessionState(session_id="loop_gate")
    state.analysis_spec = {
        "id": "spec_gate",
        "confirmation_policy": {"requires_confirmation": True, "confirmation_type": "method_confirmation"},
        "method_plan": [{"required_capability": "analysis.causal", "node_type": "analysis"}],
    }
    state.pending_confirmations = [{"id": "method_gate", "status": "pending", "confirmation_type": "method_confirmation"}]
    ctx.analysis_state = state
    loop = AgentLoop(client=_OneToolClient("causal_analysis", {"name": "main", "target_col": "revenue"}), session_id="loop_gate")
    loop.context = ctx

    try:
        with use_agent_context(ctx):
            result = loop.run_turn("run causal analysis")
        assert "confirmation" in result.lower() or "确认" in result
        tool_messages = [m for m in loop.messages if m.get("role") == "tool"]
        assert any("confirmation_required" in m.get("content", "") for m in tool_messages)
        assert not any("effect estimate" in m.get("content", "").lower() for m in tool_messages)
    finally:
        task_manager._dir = old_task_dir
        task_manager._next_id_val = old_next_id


def test_loop_injects_synthesis_policy_before_final_answer(monkeypatch):
    intent = TurnIntent(
        intent_type="directed_analysis",
        clarity="clear",
        data_state="data_loaded",
        analysis_stage="execute",
        recommended_action="run_analysis",
        execution_readiness="ready",
        reason="test",
        ambiguities=[],
    )
    monkeypatch.setattr("data_agent.agent.intent.plan_turn_intent", lambda user_input, session_context: intent)
    monkeypatch.setattr(AnalysisFlowController, "prepare_turn", lambda self, state, intent, user_input, dataset_profile: None)

    workspace_obj = Workspace()
    ctx = AgentContext(session_id="loop_synthesis_policy", workspace=workspace_obj)
    state = AnalysisSessionState(session_id="loop_synthesis_policy")
    state.analysis_spec = {
        "playbook_id": "retention_lifecycle",
        "question_type": "diagnostic",
        "confirmation_policy": {"requires_confirmation": False},
        "limitations": ["aggregate retention data"],
    }
    ctx.analysis_state = state
    client = _EvidenceThenFinalClient()
    loop = AgentLoop(client=client, session_id="loop_synthesis_policy")
    loop.context = ctx

    with use_agent_context(ctx):
        result = loop.run_turn("analyze retention formula")

    assert result == "final answer"
    assert any("<synthesis_policy" in prompt for prompt in client.system_prompts[1:])

    final_prompt = client.system_prompts[-1]
    assert ("answer_mode=\"analytical\"" in final_prompt) or ("answer_mode: analytical" in final_prompt)
    assert ("insight_depth=\"light\"" in final_prompt) or ("insight_depth: light" in final_prompt)
    assert ("business_translation=\"cautious\"" in final_prompt) or ("business_translation: cautious" in final_prompt)


def test_prepare_analysis_turn_stores_refined_intent_from_route_proposals(monkeypatch):
    intent = TurnIntent(
        intent_type="intent_negotiation",
        clarity="vague",
        data_state="data_loaded",
        analysis_stage="discover",
        recommended_action="guide_analysis",
        execution_readiness="ready",
        reason="test",
        ambiguities=[],
    )
    monkeypatch.setattr("data_agent.agent.intent.plan_turn_intent", lambda user_input, session_context: intent)
    monkeypatch.setattr(AnalysisFlowController, "prepare_turn", lambda self, state, intent, user_input, dataset_profile: None)
    monkeypatch.setattr(AnalysisFlowController, "activate_tool_groups", lambda self, registry, intent, state, user_input: [])

    workspace_obj = Workspace()
    ctx = AgentContext(session_id="loop_refined_intent", workspace=workspace_obj)
    state = AnalysisSessionState(session_id="loop_refined_intent")
    state.route_proposals = [{"id": "route_trend", "label": "Revenue trend", "direction": "trend"}]
    ctx.analysis_state = state
    loop = AgentLoop(client=object(), session_id="loop_refined_intent")
    loop.context = ctx

    with use_agent_context(ctx):
        loop._prepare_analysis_turn("help me explore this dataset")

    assert loop.context.turn_intent.ambiguities[-1]["field"] == "analysis_route"
    assert loop._last_turn_intent.ambiguities[-1]["routes"] == [
        {"label": "Revenue trend", "direction": "trend"},
    ]
