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


def test_loop_blocks_high_risk_tool_when_confirmation_pending(tmp_path, monkeypatch):
    monkeypatch.setattr(
        AnalysisFlowController,
        "prepare_turn",
        lambda self, state, intent, user_input, dataset_profile: None,
    )
    monkeypatch.setattr(
        "data_agent.agent.question_need_detector.detect_question_need",
        lambda user_input, intent, state: {"status": "no_question"},
    )
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


def test_structured_loop_auto_suspends_for_required_question(monkeypatch):
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

    class FailingClient:
        def chat(self, *args, **kwargs):
            raise AssertionError("LLM should not be called before required confirmation")

    workspace_obj = Workspace()
    ctx = AgentContext(session_id="auto_question_gate", workspace=workspace_obj)
    state = AnalysisSessionState(session_id="auto_question_gate", data_state="data_loaded")
    state.active_scope["active_dataset"] = "orders"
    state.active_scope["active_mode"] = "data_loaded"
    state.route_proposals = [
        {"id": "route_trend", "dataset": "orders", "direction": "trend", "label": "Trend"},
        {"id": "route_compare", "dataset": "orders", "direction": "period_compare", "label": "Compare"},
    ]
    ctx.analysis_state = state
    loop = AgentLoop(client=FailingClient(), session_id="auto_question_gate")
    loop.context = ctx

    with use_agent_context(ctx):
        result = loop.run_turn_structured("please analyze this dataset")

    from data_agent.agent.loop import SuspendedForConfirmation

    assert isinstance(result, SuspendedForConfirmation)
    assert result.confirmation_type == "route_selection"
    assert len(result.options) == 2
    assert result.confirmation_id == result.suspension_id
    assert state.pending_confirmations == []


def test_auto_suspend_for_required_question_uses_confirmation_runtime(tmp_path, monkeypatch):
    from data_agent.config import get_config
    from data_agent.agent.confirmation.models import ConfirmationStatus

    cfg = get_config()
    old_sessions = cfg.sessions_dir
    cfg.sessions_dir = tmp_path / "sessions"
    try:
        ctx = AgentContext(session_id="auto_runtime_gate", workspace=Workspace())
        state = AnalysisSessionState(session_id="auto_runtime_gate", data_state="data_loaded")
        ctx.analysis_state = state
        loop = AgentLoop(client=None, session_id="auto_runtime_gate")
        loop.context = ctx
        loop._turn_question_need = {
            "status": "hard_question",
            "question_type": "route_selection",
            "question": "Choose an analysis route.",
            "options": [
                {"label": "Trend", "value": "trend"},
                {"label": "Compare", "value": "period_compare"},
            ],
            "reason": "Different routes change the analysis output.",
            "state_updates": {"stage": "scope"},
        }

        result = loop._maybe_auto_suspend_for_required_question()

        assert result is not None
        assert result.confirmation_id == result.suspension_id
        assert result.version >= 2
        assert (
            cfg.sessions_resolved
            / "auto_runtime_gate"
            / "confirmations"
            / "events.jsonl"
        ).exists()
        assert list(cfg.sessions_resolved.glob("suspension_*.json")) == []
        record = loop._confirmation_runtime().get(
            "auto_runtime_gate",
            result.confirmation_id,
        )
        assert record.status == ConfirmationStatus.SUSPENDED
        assert record.source == "question_need_detector"
    finally:
        cfg.sessions_dir = old_sessions


def test_structured_loop_relationship_diagnostic_does_not_suspend(monkeypatch):
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

    class FinalClient:
        def chat(self, *args, **kwargs):
            return Response(text="analysis continued")

    ctx = AgentContext(session_id="auto_file_relationship_gate", workspace=Workspace())
    state = AnalysisSessionState(session_id="auto_file_relationship_gate", data_state="data_loaded")
    state.active_scope["active_dataset"] = "orders"
    state.active_scope["active_mode"] = "data_loaded"
    state.file_relationships = [{
        "relationship_id": "rel_orders_history",
        "file_ids": ["file_old", "file_new"],
        "status": "possibly_linked",
        "requires_confirmation": True,
        "confirmation_type": "file_relationship_confirmation",
    }]
    ctx.analysis_state = state
    loop = AgentLoop(client=FinalClient(), session_id="auto_file_relationship_gate")
    loop.context = ctx

    with use_agent_context(ctx):
        result = loop.run_turn_structured("analyze revenue trend")

    from data_agent.agent.loop import FinalResponse

    assert isinstance(result, FinalResponse)
    assert result.content == "analysis continued"
    assert state.pending_confirmations == []


def test_structured_loop_promotes_actionable_pending_when_detector_is_clear(monkeypatch):
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
    monkeypatch.setattr(
        "data_agent.agent.question_need_detector.detect_question_need",
        lambda user_input, intent, state: {"status": "clear"},
    )

    class FailingClient:
        def chat(self, *args, **kwargs):
            raise AssertionError("LLM should not be called before required confirmation")

    ctx = AgentContext(session_id="preexisting_method_gate", workspace=Workspace())
    state = AnalysisSessionState(session_id="preexisting_method_gate", data_state="data_loaded")
    state.pending_confirmations = [{
        "id": "existing_method_confirmation",
        "status": "pending",
        "question": "Confirm the existing method?",
        "options": [{"label": "Confirm", "value": "confirm_method"}],
        "confirmation_type": "method_confirmation",
        "blocking_reason": "Method choice changes the analysis",
        "state_updates": json.dumps({"stage": "plan"}),
    }]
    ctx.analysis_state = state
    loop = AgentLoop(client=FailingClient(), session_id="preexisting_method_gate")
    loop.context = ctx

    with use_agent_context(ctx):
        result = loop.run_turn_structured("analyze revenue trend")

    from data_agent.agent.loop import SuspendedForConfirmation

    assert isinstance(result, SuspendedForConfirmation)
    assert result.question == "Confirm the existing method?"
    assert result.options == [{"label": "Confirm", "value": "confirm_method", "description": ""}]
    assert result.confirmation_type == "method_confirmation"
    assert result.blocking_reason == "Method choice changes the analysis"
    assert json.loads(result.state_updates)["stage"] == "plan"
    assert "suspension_id" not in state.pending_confirmations[0]
    assert len(state.pending_confirmations) == 1


def test_auto_suspend_does_not_duplicate_pending_confirmation_with_suspension_id():
    ctx = AgentContext(session_id="existing_suspension_gate", workspace=Workspace())
    state = AnalysisSessionState(session_id="existing_suspension_gate", data_state="data_loaded")
    state.pending_confirmations = [
        {
            "id": "existing_confirmation",
            "status": "pending",
            "suspension_id": "susp_existing",
            "question": "Already suspended?",
            "options": [{"label": "Yes", "value": "yes"}],
            "state_updates": json.dumps({"stage": "scope"}),
        },
        {
            "id": "second_confirmation",
            "status": "pending",
            "suspension_id": "susp_second",
            "question": "Also suspended?",
            "options": [{"label": "Yes", "value": "yes"}],
            "state_updates": json.dumps({"stage": "plan"}),
        },
    ]
    ctx.analysis_state = state
    loop = AgentLoop(client=None, session_id="existing_suspension_gate")
    loop.context = ctx
    loop._turn_question_need = {
        "status": "hard_question",
        "question_type": "scope_confirmation",
        "question": "Regenerated question",
        "options": [{"label": "Continue", "value": "continue"}],
        "reason": "Regenerated reason",
        "state_updates": {"stage": "scope"},
    }

    assert loop._maybe_auto_suspend_for_required_question() is None
    assert len(state.pending_confirmations) == 2
    assert [item["suspension_id"] for item in state.pending_confirmations] == [
        "susp_existing",
        "susp_second",
    ]


def test_auto_suspend_selects_new_unsuspended_confirmation_after_suspended_pending():
    ctx = AgentContext(session_id="new_confirmation_after_suspension", workspace=Workspace())
    state = AnalysisSessionState(session_id="new_confirmation_after_suspension", data_state="data_loaded")
    state.pending_confirmations = [
        {
            "id": "old_confirmation",
            "status": "pending",
            "suspension_id": "susp_old",
            "question": "Old question?",
            "options": [{"label": "Old", "value": "old"}],
            "state_updates": json.dumps({"stage": "scope"}),
        },
        {
            "id": "new_confirmation",
            "status": "pending",
            "question": "New question?",
            "options": [{"label": "New", "value": "new"}],
            "state_updates": json.dumps({"stage": "plan"}),
        },
    ]
    ctx.analysis_state = state
    loop = AgentLoop(client=None, session_id="new_confirmation_after_suspension")
    loop.context = ctx
    loop._turn_existing_pending_ids = {"old_confirmation"}
    loop._turn_question_need = {
        "status": "hard_question",
        "question_type": "scope_confirmation",
        "question": "Detector question?",
        "options": [{"label": "Continue", "value": "continue"}],
        "reason": "Detector reason",
        "state_updates": {"stage": "scope"},
    }

    result = loop._maybe_auto_suspend_for_required_question()

    assert result is not None
    assert result.question == "New question?"
    assert state.pending_confirmations[0]["suspension_id"] == "susp_old"
    assert "suspension_id" not in state.pending_confirmations[1]
    assert result.confirmation_id == result.suspension_id
    assert len(state.pending_confirmations) == 2


def test_auto_suspend_falls_back_to_unsuspended_preexisting_confirmation():
    ctx = AgentContext(session_id="preexisting_unsuspended_gate", workspace=Workspace())
    state = AnalysisSessionState(session_id="preexisting_unsuspended_gate", data_state="data_loaded")
    state.pending_confirmations = [{
        "id": "preexisting_confirmation",
        "status": "pending",
        "question": "Resume this question?",
        "options": [{"label": "Resume", "value": "resume"}],
        "state_updates": json.dumps({"stage": "plan"}),
    }]
    ctx.analysis_state = state
    loop = AgentLoop(client=None, session_id="preexisting_unsuspended_gate")
    loop.context = ctx
    loop._turn_existing_pending_ids = {"preexisting_confirmation"}
    loop._turn_question_need = {
        "status": "hard_question",
        "question_type": "scope_confirmation",
        "question": "Detector question?",
        "options": [{"label": "Continue", "value": "continue"}],
        "reason": "Detector reason",
        "state_updates": {"stage": "scope"},
    }

    result = loop._maybe_auto_suspend_for_required_question()

    assert result is not None
    assert result.question == "Resume this question?"
    assert "suspension_id" not in state.pending_confirmations[0]
    assert result.confirmation_id == result.suspension_id


def test_structured_loop_ignores_untyped_obsolete_pending_when_detector_is_clear(monkeypatch):
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
    monkeypatch.setattr(
        "data_agent.agent.question_need_detector.detect_question_need",
        lambda user_input, intent, state: {"status": "clear"},
    )

    class FinalClient:
        def chat(self, *args, **kwargs):
            return Response(text="analysis continued")

    def prepare_turn_with_rich_confirmation(self, state, intent, user_input, dataset_profile):
        state.add_confirmation({
            "id": "rich_pending",
            "action": "resolve_file_relationship",
            "question": "confirm relationship",
            "options": [{"label": "Together", "value": "include_in_active_bundle"}],
            "state_updates": json.dumps({
                "stage": "plan",
                "file_relationship_confirmation": {"relationship_id": "rel_custom"},
                "analysis_spec": {"goal": "preserve me"},
            }),
        })

    monkeypatch.setattr(AnalysisFlowController, "prepare_turn", prepare_turn_with_rich_confirmation)

    ctx = AgentContext(session_id="preserve_pending_updates", workspace=Workspace())
    state = AnalysisSessionState(session_id="preserve_pending_updates", data_state="data_loaded")
    state.file_relationships = [{
        "relationship_id": "rel_detector",
        "file_ids": ["file_old", "file_new"],
        "status": "possibly_linked",
        "requires_confirmation": True,
        "confirmation_type": "file_relationship_confirmation",
    }]
    ctx.analysis_state = state
    loop = AgentLoop(client=FinalClient(), session_id="preserve_pending_updates")
    loop.context = ctx

    with use_agent_context(ctx):
        result = loop.run_turn_structured("analyze revenue trend")

    from data_agent.agent.loop import FinalResponse

    assert isinstance(result, FinalResponse)
    assert result.content == "analysis continued"
    saved_updates = json.loads(state.pending_confirmations[0]["state_updates"])
    assert saved_updates == {
        "stage": "plan",
        "file_relationship_confirmation": {"relationship_id": "rel_custom"},
        "analysis_spec": {"goal": "preserve me"},
    }
    assert "suspension_id" not in state.pending_confirmations[0]


def test_structured_loop_converts_playbook_pending_confirmation_to_suspension(monkeypatch):
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
    monkeypatch.setattr("data_agent.agent.llm_playbook.select_playbook_llm", lambda **kwargs: None)

    class FailingClient:
        def chat(self, *args, **kwargs):
            raise AssertionError("LLM should not be called before required confirmation")

    ctx = AgentContext(session_id="playbook_pending_gate", workspace=Workspace())
    state = AnalysisSessionState(session_id="playbook_pending_gate", data_state="data_loaded")
    state.active_scope["active_dataset"] = "main"
    state.active_scope["active_mode"] = "data_loaded"
    ctx.analysis_state = state
    loop = AgentLoop(client=FailingClient(), session_id="playbook_pending_gate")
    loop.context = ctx

    with use_agent_context(ctx):
        result = loop.run_turn_structured("forecast revenue and ROI next month")

    from data_agent.agent.loop import SuspendedForConfirmation

    assert isinstance(result, SuspendedForConfirmation)
    assert result.confirmation_type == "method_confirmation"
    pending = [item for item in state.pending_confirmations if item.get("status") == "pending"]
    assert len(pending) == 1
    assert "suspension_id" not in pending[0]
    assert result.confirmation_id == result.suspension_id


def test_stream_loop_auto_suspends_for_required_question(monkeypatch):
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

    class FailingClient:
        def chat(self, *args, **kwargs):
            raise AssertionError("LLM should not be called before required confirmation")

    ctx = AgentContext(session_id="auto_question_gate_stream", workspace=Workspace())
    state = AnalysisSessionState(session_id="auto_question_gate_stream", data_state="data_loaded")
    state.active_scope["active_dataset"] = "orders"
    state.active_scope["active_mode"] = "data_loaded"
    state.route_proposals = [
        {"id": "route_trend", "dataset": "orders", "direction": "trend", "label": "Trend"},
        {"id": "route_compare", "dataset": "orders", "direction": "period_compare", "label": "Compare"},
    ]
    ctx.analysis_state = state
    loop = AgentLoop(client=FailingClient(), session_id="auto_question_gate_stream")
    loop.context = ctx

    events = list(loop.stream_turn("please analyze this dataset"))

    assert events[0]["type"] == "suspended"
    assert events[0]["confirmation_type"] == "route_selection"
    assert len(events[0]["options"]) == 2


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

    assert result.startswith("final answer\n\n---\n\n### 已验证计算结果")
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


def test_synthesis_policy_injection_creates_verification_report_first(monkeypatch):
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
    workspace_obj = Workspace()
    ctx = AgentContext(session_id="loop_verify_before_synthesis", workspace=workspace_obj)
    state = AnalysisSessionState(session_id="loop_verify_before_synthesis")
    state.evidence_records = [{
        "id": "ev_1",
        "claim": "Retention follows a power-law curve",
        "result_summary": "R(t)=0.1917*t^(-0.7335), R2=0.9743",
        "confidence": "high",
        "dataset": "retention",
        "sample_size": 1200,
        "time_scope": "2026-01-01 to 2026-05-31",
        "calculation_method": "retention curve fit",
        "method_detail": "fit log retention against log elapsed time",
        "limitations": "Aggregated data only",
        "method": "log-linear least squares",
    }]
    ctx.analysis_state = state
    ctx.user_quality_requirements = ""
    loop = AgentLoop(client=object(), session_id="loop_verify_before_synthesis")
    loop.context = ctx
    loop._last_turn_intent = intent
    loop._reset_turn_tracking()

    with use_agent_context(ctx):
        loop._maybe_inject_synthesis_policy("summarize the retention formula")

    assert state.verification_reports
    assert state.verification_reports[-1]["overall_status"] == "pass"
    assert loop._turn_verification_injected is True
    assert loop._turn_synthesis_policy_injected is True
    assert "<synthesis_policy" in loop._turn_synthesis_policy_instruction


def test_synthesis_policy_injection_creates_hypothesis_set_before_policy(tmp_path):
    from data_agent.config import get_config

    cfg = get_config()
    old_sessions = cfg.sessions_dir
    cfg.sessions_dir = tmp_path / "sessions"
    try:
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
        workspace_obj = Workspace()
        ctx = AgentContext(session_id="loop_hyp_before_synthesis", workspace=workspace_obj)
        state = AnalysisSessionState(session_id="loop_hyp_before_synthesis")
        state.dataset_contracts = [{
            "dataset": "sales",
            "quality": {"status": "ready"},
            "field_roles": {"date": ["date"], "metrics": ["revenue"]},
        }]
        state.route_proposals = [{
            "id": "route_trend",
            "dataset": "sales",
            "direction": "trend",
            "evidence_requirements": ["date", "metric"],
        }]
        state.evidence_records = [{
            "id": "ev_1",
            "claim": "Revenue changed across the selected period",
            "result_summary": "Revenue moved from 100 to 120.",
            "confidence": "high",
            "dataset": "sales",
            "sample_size": 20,
            "time_scope": "2026-01-01 to 2026-01-20",
            "calculation_method": "trend comparison",
            "method_detail": "compare daily revenue values",
            "limitations": "Descriptive trend only",
            "method": "descriptive",
        }]
        ctx.analysis_state = state
        ctx.user_quality_requirements = ""
        loop = AgentLoop(client=object(), session_id="loop_hyp_before_synthesis")
        loop.context = ctx
        loop._last_turn_intent = intent
        loop._reset_turn_tracking()

        with use_agent_context(ctx):
            loop._maybe_inject_synthesis_policy("show revenue trend")

        assert state.hypothesis_sets
        assert state.hypothesis_sets[-1]["dataset"] == "sales"
        assert state.hypothesis_sets[-1]["route"] == "trend"
        assert loop._turn_synthesis_policy_injected is True
    finally:
        cfg.sessions_dir = old_sessions


def test_synthesis_policy_injection_marks_failed_verification_attempt(monkeypatch):
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
    workspace_obj = Workspace()
    ctx = AgentContext(session_id="loop_verify_exception_policy", workspace=workspace_obj)
    state = AnalysisSessionState(session_id="loop_verify_exception_policy")
    state.evidence_records = [{
        "id": "ev_1",
        "claim": "Retention follows a power-law curve",
        "result_summary": "R(t)=0.1917*t^(-0.7335), R2=0.9743",
        "confidence": "high",
    }]
    ctx.analysis_state = state
    ctx.user_quality_requirements = ""
    loop = AgentLoop(client=object(), session_id="loop_verify_exception_policy")
    loop.context = ctx
    loop._last_turn_intent = intent
    loop._reset_turn_tracking()

    from data_agent.agent import trust_workflow_runtime as runtime

    def raise_verification_error(*_args, **_kwargs):
        raise RuntimeError("verification unavailable")

    monkeypatch.setattr(runtime, "maybe_verify_turn_claims", raise_verification_error)

    with use_agent_context(ctx):
        loop._maybe_inject_synthesis_policy("summarize retention")

    assert loop._turn_verification_injected is True
    assert loop._turn_synthesis_policy_injected is True
    assert "<synthesis_policy" in loop._turn_synthesis_policy_instruction


def test_synthesis_policy_instruction_reflects_failed_runtime_verification(monkeypatch):
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
    workspace_obj = Workspace()
    ctx = AgentContext(session_id="loop_failed_verification_policy", workspace=workspace_obj)
    state = AnalysisSessionState(session_id="loop_failed_verification_policy")
    state.evidence_records = [{
        "id": "ev_1",
        "claim": "Retention rose 500%",
        "result_summary": "Retention fell from 30% to 20%",
        "confidence": "high",
    }]
    from data_agent.agent import trust_workflow_runtime as runtime

    def fake_verify_analysis_claims(**_kwargs):
        return {
            "id": "failed_report",
            "claim_checks": [{
                "claim_id": "claim_1",
                "claim": "Retention rose 500%",
                "evidence_id": None,
                "status": "failed",
                "strength": "unsupported",
                "issues": ["No evidence record supports this claim"],
            }],
            "route_proposal_ids": [],
            "overall_status": "fail",
        }

    monkeypatch.setattr(runtime, "verify_analysis_claims", fake_verify_analysis_claims)
    ctx.analysis_state = state
    ctx.user_quality_requirements = ""
    loop = AgentLoop(client=object(), session_id="loop_failed_verification_policy")
    loop.context = ctx
    loop._last_turn_intent = intent
    loop._reset_turn_tracking()

    with use_agent_context(ctx):
        loop._maybe_inject_synthesis_policy("summarize retention")

    assert state.verification_reports[-1]["overall_status"] == "fail"
    assert "verification status is fail" in loop._turn_synthesis_policy_instruction.lower()
    assert "decision_recommendation" in loop._turn_synthesis_policy_instruction
    assert "suppressed" in loop._turn_synthesis_policy_instruction.lower()
