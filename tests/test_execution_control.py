import json

from data_agent.agent.analysis_flow_controller import AnalysisFlowController
from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.context import AgentContext, use_agent_context
from data_agent.agent.execution_control import (
    BudgetExceeded,
    ToolExecutionBudget,
    TurnExecutionState,
)
from data_agent.agent.intent import plan_turn_intent
from data_agent.llm.client import Response, ToolCall
from data_agent.agent.loop import AgentLoop
from data_agent.session.task_manager import task_manager
from data_agent.session.workspace import Workspace


def _loaded_context() -> str:
    return "- main: 20 rows x 4 cols, columns: date, revenue, cost, user_id"


def test_budget_soft_and_hard_thresholds():
    state = TurnExecutionState(ToolExecutionBudget(profile="interactive", max_tool_calls=5, max_chart_calls=2, max_fallback_calls=2))

    state.record_tool_call("list_data", {})
    state.record_tool_call("describe_dataset", {})
    state.record_tool_call("run_python", {})

    assert state.should_converge is True
    assert state.should_restrict_exploration is False

    state.record_tool_call("create_chart", {})
    state.record_tool_call("preview_data", {})
    assert state.should_restrict_exploration is True

    state.record_tool_call("describe_dataset", {})
    try:
        state.ensure_can_call("list_data", {})
    except BudgetExceeded as exc:
        assert "tool call budget" in str(exc).lower()
    else:
        raise AssertionError("expected hard budget to stop further tool calls")


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
        intent.intent_type = "direct_analysis"
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
