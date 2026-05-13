import json

import pandas as pd

from data_agent.agent.analysis_flow_controller import AnalysisFlowController
from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.intent import plan_turn_intent
from data_agent.agent.method_playbooks import PLAYBOOKS, list_playbooks, select_playbooks
from data_agent.session.task_manager import task_manager
from data_agent.tools.analysis_flow import record_analysis_spec
from data_agent.tools.registry import registry
from data_agent.agent.context import AgentContext, use_agent_context
from data_agent.session.workspace import Workspace


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


def test_selector_maps_common_questions_to_playbooks():
    cases = [
        ("review dataset structure and suggest useful analysis paths", "intent_negotiation", "data_understanding"),
        ("why did revenue decline", "directed_analysis", "driver_decomposition"),
        ("analyze where the conversion funnel loses the most users", "directed_analysis", "funnel_conversion"),
        ("will users keep purchasing after the first order", "directed_analysis", "retention_lifecycle"),
        ("forecast next month revenue and estimate ROI", "directed_analysis", "forecast_decision_simulation"),
        ("evaluate whether the savings card is worth long-term operation; include retention and cost", "directed_analysis", "evaluation_causal"),
    ]

    for user_input, expected_intent, expected_playbook in cases:
        intent = plan_turn_intent(user_input, _loaded_context())
        if expected_intent == "directed_analysis":
            intent.intent_type = "directed_analysis"
            intent.data_state = "data_loaded"
        selection = select_playbooks(user_input, intent, AnalysisSessionState(session_id="s"), _loaded_context())
        assert selection.primary_playbook_id == expected_playbook
        assert selection.recommended_paths
        if expected_intent == "directed_analysis":
            assert selection.analysis_spec is not None
            capabilities = {
                step["required_capability"]
                for step in selection.analysis_spec["method_plan"]
                if step.get("required_capability")
            }
            assert capabilities


def test_business_playbook_analysis_spec_contains_visualization_strategy_and_stats():
    ctx = _loaded_context("user_id, revenue, pay_time, feature_type, period")
    intent = plan_turn_intent("分析功能效果和收益", ctx)
    selection = select_playbooks("分析功能效果和收益", intent, AnalysisSessionState(session_id="business_spec"), ctx)

    spec = selection.analysis_spec

    assert spec is not None
    assert "visualization_strategy" in spec
    assert "required_charts" not in spec
    assert "statistical_requirements" in spec
    assert "effect_size" in spec["statistical_requirements"]
    assert any(item.get("chart_name") == "before_after_comparison" for item in spec["visualization_strategy"])


def test_selector_handles_no_data_business_question_as_requirement():
    user_input = "I want to evaluate whether a savings card is worth long term operation. What data do I need?"
    intent = plan_turn_intent(user_input, "")
    selection = select_playbooks(user_input, intent, AnalysisSessionState(session_id="s"), "")

    assert selection.primary_playbook_id == "evaluation_causal"
    assert "retention_lifecycle" in selection.supporting_playbook_ids
    assert selection.analysis_spec is None
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

    assert state.analysis_spec is not None
    assert state.analysis_spec["playbook_id"] == "driver_decomposition"
    assert state.last_recommended_paths
    capabilities = {
        step["required_capability"]
        for step in state.analysis_spec["method_plan"]
        if step.get("required_capability")
    }
    assert "analysis.dimension_decomposition" in capabilities
    assert "eda" in registry._get_active_groups()


def test_english_business_requests_are_direct_analysis():
    context = _loaded_context("date, revenue, cost, user_id, funnel_step")
    cases = [
        ("Analyze the rewarded video funnel from request to completed watch", "funnel_conversion"),
        ("Forecast next month revenue and ROI trend", "forecast_decision_simulation"),
        ("Evaluate whether the savings card is worth long-term operation and discuss retention", "evaluation_causal"),
    ]

    for text, expected_playbook in cases:
        intent = plan_turn_intent(text, context)
        assert intent.intent_type == "directed_analysis"
        selection = select_playbooks(text, intent, AnalysisSessionState(session_id="english_direct"), context)
        assert selection.primary_playbook_id == expected_playbook


def test_controller_creates_workflow_tasks_for_direct_analysis(tmp_path):
    old_task_dir = task_manager._dir
    old_next_id = task_manager._next_id_val
    task_manager._dir = tmp_path / "tasks"
    task_manager._next_id_val = 0
    try:
        state = AnalysisSessionState(session_id="controller_workflow", project_name=None)
        intent = plan_turn_intent("why did revenue decline", _loaded_context())
        intent.intent_type = "direct_analysis"
        intent.data_state = "data_loaded"

        controller = AnalysisFlowController("controller_workflow")
        controller.prepare_turn(state, intent, user_input="why did revenue decline", dataset_profile=_loaded_context())
        first_tasks = task_manager.list_for_scope(session_id="controller_workflow")
        controller.prepare_turn(state, intent, user_input="why did revenue decline", dataset_profile=_loaded_context())
        second_tasks = task_manager.list_for_scope(session_id="controller_workflow")

        assert state.analysis_spec is not None
        assert state.analysis_spec.get("workflow_id")
        assert len(first_tasks) == len(state.analysis_spec["method_plan"])
        assert len(second_tasks) == len(first_tasks)
        assert {t.get("analysis_spec_id") for t in first_tasks} == {state.analysis_spec["id"]}
        assert "analysis.dimension_decomposition" in {t.get("required_capability") for t in first_tasks}
    finally:
        task_manager._dir = old_task_dir
        task_manager._next_id_val = old_next_id


def test_playbook_analysis_spec_creates_workflow_tasks_with_capability(tmp_path):
    old_task_dir = task_manager._dir
    old_next_id = task_manager._next_id_val
    task_manager._dir = tmp_path / "tasks"
    task_manager._next_id_val = 0
    ctx = AgentContext(session_id="playbook_tasks", workspace=Workspace())
    try:
        user_input = "forecast next month revenue and estimate ROI"
        intent = plan_turn_intent(user_input, _loaded_context("month, revenue, cost"))
        intent.intent_type = "direct_analysis"
        intent.data_state = "data_loaded"
        selection = select_playbooks(user_input, intent, AnalysisSessionState(session_id="playbook_tasks"), _loaded_context("month, revenue, cost"))

        with use_agent_context(ctx):
            result = json.loads(record_analysis_spec(json.dumps(selection.analysis_spec)))

        assert result["workflow"]["created"] >= 2
        tasks = task_manager.list_for_scope(session_id="playbook_tasks")
        capabilities = {t.get("required_capability") for t in tasks}
        assert "analysis.forecast" in capabilities
        assert "fallback.python" in capabilities
        assert any(t.get("confirmation_policy", {}).get("requires_confirmation") for t in tasks)
    finally:
        task_manager._dir = old_task_dir
        task_manager._next_id_val = old_next_id
