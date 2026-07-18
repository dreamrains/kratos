import json
from unittest.mock import patch

import pandas as pd

from data_agent.agent.analysis_flow_controller import AnalysisFlowController
from data_agent.agent.analysis_state import AnalysisSessionState, STAGES
from data_agent.agent.intent import TurnIntent, plan_turn_intent
from data_agent.agent.method_playbooks import (
    PLAYBOOKS,
    apply_selection_to_state,
    choose_playbook,
    list_playbooks,
    select_playbooks,
)
from data_agent.session.task_manager import task_manager
from data_agent.tools.analysis_flow import record_analysis_spec
from data_agent.tools.registry import registry
from data_agent.agent.context import AgentContext, use_agent_context
from data_agent.session.workspace import Workspace


def _no_llm_playbook(*args, **kwargs):
    """Mock that simulates LLM unavailability for deterministic keyword-path testing."""
    return None


def _loaded_context(columns: str = "date, revenue, channel") -> str:
    return f"- main: 10 rows x 3 cols, columns: {columns}"


def test_method_playbooks_are_complete():
    expected = {
        "data_understanding",
        "metric_overview",
        "trend_period_comparison",
        "driver_decomposition",
        "funnel_conversion",
        "retention_lifecycle",
        "evaluation_causal",
        "forecast_decision_simulation",
        "product_feature_analysis",
        "effect_evaluation",
        "revenue_profitability",
        "user_behavior_analysis",
        "growth_opportunity",
    }
    assert {p.id for p in list_playbooks()} == expected

    for playbook in PLAYBOOKS.values():
        data = playbook.to_dict()
        for field in (
            "id",
            "name",
            "description",
            "question_types",
            "typical_user_goals",
            "applicability",
            "data_requirements",
            "method_plan_template",
            "confirmation_policy",
            "evidence_policy",
            "limitation_policy",
            "output_policy",
        ):
            assert data[field] not in ("", [], {})
        assert playbook.data_requirements["must_have_data"]
        assert playbook.data_requirements["minimum_viable_data"]
        assert playbook.method_plan_template
        assert playbook.evidence_policy["required_evidence"]
        for step in playbook.method_plan_template:
            assert step["required_capability"]

    for high_risk in ("evaluation_causal", "forecast_decision_simulation", "retention_lifecycle"):
        assert PLAYBOOKS[high_risk].confirmation_policy["requires_confirmation"] is True


@patch("data_agent.agent.llm_playbook.select_playbook_llm", _no_llm_playbook)
def test_method_confirmation_is_answerable_when_playbook_requires_confirmation():
    state = AnalysisSessionState(session_id="method_confirmation_contract", data_state="data_loaded")
    intent = TurnIntent(
        intent_type="directed_analysis",
        clarity="clear",
        data_state="data_loaded",
        analysis_stage="plan",
        recommended_action="run_analysis",
        execution_readiness="ready",
    )

    selection = choose_playbook("predict user churn next month", intent, has_data=True)
    apply_selection_to_state(state, selection)

    pending = [
        item for item in state.pending_confirmations
        if item.get("confirmation_type") == "method_confirmation"
    ]
    assert pending
    confirmation = pending[0]
    assert confirmation["status"] == "pending"
    assert confirmation["confirmation_type"] == "method_confirmation"
    assert confirmation["question"]
    assert confirmation["options"]
    assert confirmation["blocking_reason"]
    assert confirmation["state_updates"]
    assert confirmation["source"] == "method_playbook"


@patch("data_agent.agent.llm_playbook.select_playbook_llm", _no_llm_playbook)
def test_method_confirmation_uses_new_selection_plan_when_existing_state_has_stale_plan():
    state = AnalysisSessionState(session_id="method_stale_spec", data_state="data_loaded")
    state.set_analysis_plan({
        "id": "old_plan",
        "playbook_id": "driver_decomposition",
        "confirmation_policy": {
            "requires_confirmation": True,
            "confirmation_type": "method_confirmation",
            "blocking_reason": "old reason",
        },
    })
    intent = TurnIntent(
        intent_type="directed_analysis",
        clarity="clear",
        data_state="data_loaded",
        analysis_stage="plan",
        recommended_action="run_analysis",
        execution_readiness="ready",
    )
    selection = choose_playbook("forecast revenue and ROI", intent, has_data=True)
    assert selection.analysis_plan is not None
    selection.analysis_plan["id"] = "new_forecast_plan"

    apply_selection_to_state(state, selection)

    confirmation = next(
        item for item in state.pending_confirmations
        if item.get("related_plan_id") == selection.analysis_plan["id"]
    )
    updates = json.loads(confirmation["state_updates"])
    assert confirmation["related_plan_id"] == selection.analysis_plan["id"]
    assert state.analysis_plan["id"] == selection.analysis_plan["id"]
    assert state.analysis_plan["playbook_id"] == "forecast_decision_simulation"
    assert updates["method_confirmation"]["analysis_plan_id"] == selection.analysis_plan["id"]
    assert confirmation["blocking_reason"] != "old reason"


@patch("data_agent.agent.llm_playbook.select_playbook_llm", _no_llm_playbook)
def test_method_confirmation_state_updates_are_safe_for_resolution_options():
    intent = TurnIntent(
        intent_type="directed_analysis",
        clarity="clear",
        data_state="data_loaded",
        analysis_stage="plan",
        recommended_action="run_analysis",
        execution_readiness="ready",
    )

    for answer in ("confirm_method", "clarify_method_scope"):
        state = AnalysisSessionState(session_id=f"method_resolution_{answer}", data_state="data_loaded")
        selection = choose_playbook("forecast next month revenue and estimate ROI", intent, has_data=True)
        apply_selection_to_state(state, selection)
        confirmation = next(
            item for item in state.pending_confirmations
            if item.get("related_plan_id") == state.analysis_plan["id"]
        )
        updates = json.loads(confirmation["state_updates"])

        assert updates["stage"] in STAGES
        assert updates["method_confirmation"] == {
            "playbook_id": "forecast_decision_simulation",
            "analysis_plan_id": state.analysis_plan["id"],
            "allowed_actions": ["confirm_method", "clarify_method_scope"],
        }

        result = state.resolve_confirmation(confirmation["id"], answer)

        assert result is not None
        assert result["status"] == "resolved"
        assert state.stage in STAGES
        assert state.active_scope["active_mode"] in {"consulting", "data_loaded", "analysis", "artifact_review"}


@patch("data_agent.agent.llm_playbook.select_playbook_llm", _no_llm_playbook)
def test_method_scope_clarification_keeps_forecast_blocked_until_method_is_confirmed():
    intent = TurnIntent(
        intent_type="directed_analysis",
        clarity="clear",
        data_state="data_loaded",
        analysis_stage="plan",
        recommended_action="run_analysis",
        execution_readiness="ready",
    )
    controller = AnalysisFlowController("method_scope_resolution")

    clarify_state = AnalysisSessionState(session_id="method_scope_clarify", data_state="data_loaded")
    selection = choose_playbook("forecast next month revenue and estimate ROI", intent, has_data=True)
    apply_selection_to_state(clarify_state, selection)
    confirmation = next(item for item in clarify_state.pending_confirmations if item["status"] == "pending")

    clarify_state.resolve_confirmation(confirmation["id"], "clarify_method_scope")

    assert clarify_state.stage == "scope"
    assert controller.is_capability_blocked_by_confirmation(clarify_state, "analysis.forecast") is True
    clarification = next(item for item in clarify_state.pending_confirmations if item["status"] == "pending")
    assert clarification["confirmation_type"] == "method_scope_clarification"
    assert clarification["related_plan_id"] == clarify_state.analysis_plan["id"]
    assert clarification["options"]

    clarify_state.resolve_confirmation(clarification["id"], "confirm_method")

    assert controller.is_capability_blocked_by_confirmation(clarify_state, "analysis.forecast") is False
    assert not any(item["status"] == "pending" for item in clarify_state.pending_confirmations)

    confirm_state = AnalysisSessionState(session_id="method_scope_confirm", data_state="data_loaded")
    apply_selection_to_state(confirm_state, selection)
    confirmation = next(item for item in confirm_state.pending_confirmations if item["status"] == "pending")

    confirm_state.resolve_confirmation(confirmation["id"], "confirm_method")

    assert confirm_state.analysis_plan["method_confirmation"]["status"] == "approved"
    assert controller.is_capability_blocked_by_confirmation(confirm_state, "analysis.forecast") is False


@patch("data_agent.agent.llm_playbook.select_playbook_llm", _no_llm_playbook)
def test_changed_high_risk_request_replaces_plan_and_requires_new_confirmation():
    state = AnalysisSessionState(session_id="method_changed_request", data_state="data_loaded")
    intent = TurnIntent(
        intent_type="directed_analysis",
        clarity="clear",
        data_state="data_loaded",
        analysis_stage="plan",
        recommended_action="run_analysis",
        execution_readiness="ready",
    )

    first = choose_playbook("forecast revenue and ROI next month", intent, has_data=True)
    assert first.analysis_plan is not None
    assert first.analysis_plan["id"]
    apply_selection_to_state(state, first)
    first_plan_id = state.analysis_plan["id"]
    first_confirmation = next(
        item for item in state.pending_confirmations
        if item.get("related_plan_id") == first_plan_id
    )
    state.resolve_confirmation(first_confirmation["id"], "confirm_method")

    second = choose_playbook("forecast cost and ROI next quarter", intent, has_data=True)
    duplicate_second = choose_playbook("forecast cost and ROI next quarter", intent, has_data=True)
    assert second.analysis_plan is not None
    assert duplicate_second.analysis_plan is not None
    assert second.primary_playbook_id == first.primary_playbook_id
    assert second.analysis_plan["id"] != first_plan_id
    assert duplicate_second.analysis_plan["id"] == second.analysis_plan["id"]

    apply_selection_to_state(state, second)
    apply_selection_to_state(state, duplicate_second)

    second_plan_id = second.analysis_plan["id"]
    second_confirmations = [
        item for item in state.pending_confirmations
        if item.get("related_plan_id") == second_plan_id and item.get("status") == "pending"
    ]
    assert state.analysis_plan["id"] == second_plan_id
    assert state.analysis_plan["goal"] == "forecast cost and ROI next quarter"
    assert state.goal == "forecast cost and ROI next quarter"
    assert len(second_confirmations) == 1
    assert second_confirmations[0]["id"] != first_confirmation["id"]


@patch("data_agent.agent.llm_playbook.select_playbook_llm", _no_llm_playbook)
def test_selector_maps_common_questions_to_playbooks():
    cases = [
        ("review dataset structure and suggest useful analysis paths", "intent_negotiation", "data_understanding"),
        ("why did revenue decline", "directed_analysis", "driver_decomposition"),
        ("analyze where the conversion funnel loses the most users", "directed_analysis", "funnel_conversion"),
        ("will users keep purchasing after the first order", "directed_analysis", "retention_lifecycle"),
        ("forecast next month revenue and estimate ROI", "directed_analysis", "forecast_decision_simulation"),
        ("evaluate whether the savings card is worth long-term operation; include retention and cost", "directed_analysis", {"evaluation_causal", "retention_lifecycle"}),
    ]

    for user_input, expected_intent, expected_playbook in cases:
        intent = plan_turn_intent(user_input, _loaded_context())
        if expected_intent == "directed_analysis":
            intent.intent_type = "directed_analysis"
            intent.data_state = "data_loaded"
        selection = select_playbooks(user_input, intent, AnalysisSessionState(session_id="s"), _loaded_context())
        if isinstance(expected_playbook, set):
            assert selection.primary_playbook_id in expected_playbook, f"Expected one of {expected_playbook}, got {selection.primary_playbook_id}"
        else:
            assert selection.primary_playbook_id == expected_playbook
        assert selection.recommended_paths
        if expected_intent == "directed_analysis":
            assert selection.analysis_plan is not None
            assert selection.analysis_plan["contract_version"] == "analysis_plan.v1"
            assert "analysis_spec" not in selection.to_dict()
            capabilities = {
                step["required_capability"]
                for step in selection.analysis_plan["method_plan"]
                if step.get("required_capability")
            }
            assert capabilities


@patch("data_agent.agent.llm_playbook.select_playbook_llm", _no_llm_playbook)
def test_business_playbook_analysis_plan_contains_visualization_strategy_and_stats():
    ctx = _loaded_context("user_id, revenue, pay_time, feature_type, period")
    intent = plan_turn_intent("分析功能效果和收益", ctx)
    selection = select_playbooks("分析功能效果和收益", intent, AnalysisSessionState(session_id="business_spec"), ctx)

    plan = selection.analysis_plan

    assert plan is not None
    assert "visualization_strategy" in plan
    assert "required_charts" not in plan
    assert "statistical_requirements" in plan
    assert "effect_size" in plan["statistical_requirements"]
    compiled_names = {
        requirement["name"]
        for group in plan["analysis_requirements"].values()
        for requirement in group
    }
    assert set(plan["statistical_requirements"]) <= compiled_names
    assert any(item.get("chart_name") == "before_after_comparison" for item in plan["visualization_strategy"])


def test_playbook_requirement_strings_remain_compiler_inputs():
    playbook = PLAYBOOKS["effect_evaluation"]

    assert playbook.output_policy["statistical_requirements"] == [
        "sample_size",
        "effect_size",
        "significance",
        "confidence_interval",
    ]
    assert playbook.method_plan_template[1]["evidence_requirements"] == [
        "effect_size",
        "significance",
        "sample_size",
    ]


@patch("data_agent.agent.llm_playbook.select_playbook_llm", _no_llm_playbook)
def test_selector_handles_no_data_business_question_as_requirement():
    user_input = "I want to evaluate whether a savings card is worth long term operation. What data do I need?"
    intent = plan_turn_intent(user_input, "")
    selection = select_playbooks(user_input, intent, AnalysisSessionState(session_id="s"), "")

    assert selection.primary_playbook_id == "evaluation_causal"
    assert "retention_lifecycle" in selection.supporting_playbook_ids
    assert selection.analysis_plan is None
    assert selection.data_requirement is not None
    text = json.dumps(selection.data_requirement).lower()
    for term in ("treatment", "outcome", "control", "cost"):
        assert term in text


def test_controller_writes_playbook_selection_to_state_and_activates_capability():
    state = AnalysisSessionState(session_id="controller_playbook", project_name=None)
    intent = plan_turn_intent("why did revenue decline", _loaded_context())
    intent.intent_type = "directed_analysis"
    intent.data_state = "data_loaded"

    controller = AnalysisFlowController("controller_playbook")
    controller.prepare_turn(state, intent, user_input="why did revenue decline", dataset_profile=_loaded_context())
    controller.activate_tool_groups(registry, intent, state, "why did revenue decline")

    assert state.analysis_plan is not None
    assert state.analysis_plan["playbook_id"] == "driver_decomposition"
    assert state.last_recommended_paths
    capabilities = {
        step["required_capability"]
        for step in state.analysis_plan["method_plan"]
        if step.get("required_capability")
    }
    assert "analysis.dimension_decomposition" in capabilities
    assert "eda" in registry._get_active_groups()


@patch("data_agent.agent.llm_playbook.select_playbook_llm", _no_llm_playbook)
def test_english_business_requests_are_direct_analysis():
    context = _loaded_context("date, revenue, cost, user_id, funnel_step")
    cases = [
        ("Analyze the rewarded video funnel from request to completed watch", "funnel_conversion"),
        ("Forecast next month revenue and ROI trend", "forecast_decision_simulation"),
        ("Evaluate whether the savings card is worth long-term operation and discuss retention", {"evaluation_causal", "retention_lifecycle"}),
    ]

    for text, expected_playbook in cases:
        intent = plan_turn_intent(text, context)
        assert intent.intent_type == "directed_analysis"
        selection = select_playbooks(text, intent, AnalysisSessionState(session_id="english_direct"), context)
        if isinstance(expected_playbook, set):
            assert selection.primary_playbook_id in expected_playbook, f"Expected one of {expected_playbook}, got {selection.primary_playbook_id}"
        else:
            assert selection.primary_playbook_id == expected_playbook


@patch("data_agent.agent.llm_playbook.select_playbook_llm", _no_llm_playbook)
def test_controller_keeps_generated_playbook_plan_display_only(tmp_path):
    old_task_dir = task_manager._dir
    old_next_id = task_manager._next_id_val
    task_manager._dir = tmp_path / "tasks"
    task_manager._next_id_val = 0
    try:
        state = AnalysisSessionState(session_id="controller_workflow", project_name=None)
        intent = plan_turn_intent("why did revenue decline", _loaded_context())
        intent.intent_type = "directed_analysis"
        intent.data_state = "data_loaded"

        controller = AnalysisFlowController("controller_workflow")
        controller.prepare_turn(state, intent, user_input="why did revenue decline", dataset_profile=_loaded_context())
        first_tasks = task_manager.list_for_scope(session_id="controller_workflow")
        controller.prepare_turn(state, intent, user_input="why did revenue decline", dataset_profile=_loaded_context())
        second_tasks = task_manager.list_for_scope(session_id="controller_workflow")

        assert state.analysis_plan is not None
        assert state.analysis_plan["contract_version"] == "analysis_plan.v1"
        assert state.analysis_plan["review_status"] == "display_only"
        assert state.analysis_plan.get("workflow_id") is None
        assert first_tasks == []
        assert second_tasks == []
    finally:
        task_manager._dir = old_task_dir
        task_manager._next_id_val = old_next_id


@patch("data_agent.agent.llm_playbook.select_playbook_llm", _no_llm_playbook)
def test_deprecated_analysis_spec_adapter_keeps_playbook_plan_display_only(tmp_path):
    old_task_dir = task_manager._dir
    old_next_id = task_manager._next_id_val
    task_manager._dir = tmp_path / "tasks"
    task_manager._next_id_val = 0
    ctx = AgentContext(session_id="playbook_tasks", workspace=Workspace())
    try:
        user_input = "forecast next month revenue and estimate ROI"
        intent = plan_turn_intent(user_input, _loaded_context("month, revenue, cost"))
        intent.intent_type = "directed_analysis"
        intent.data_state = "data_loaded"
        selection = select_playbooks(user_input, intent, AnalysisSessionState(session_id="playbook_tasks"), _loaded_context("month, revenue, cost"))

        with use_agent_context(ctx):
            result = json.loads(record_analysis_spec(json.dumps(selection.analysis_plan)))

        assert result["workflow"] == {
            "created": 0,
            "task_ids": [],
            "display_only": True,
            "reason": "deprecated_analysis_spec_adapter_display_only",
        }
        assert task_manager.list_for_scope(session_id="playbook_tasks") == []
    finally:
        task_manager._dir = old_task_dir
        task_manager._next_id_val = old_next_id
