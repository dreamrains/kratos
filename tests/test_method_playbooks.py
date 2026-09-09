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


def test_injected_playbook_client_is_called_once_before_deterministic_fallback():
    class _InvalidJsonClient:
        def __init__(self):
            self.calls = 0

        def chat(self, messages, tools=None, system=None):
            self.calls += 1
            return type("Response", (), {"text": "not-json"})()

    client = _InvalidJsonClient()
    intent = TurnIntent(
        intent_type="directed_analysis",
        clarity="clear",
        data_state="data_loaded",
        analysis_stage="execute",
        recommended_action="run_analysis",
        execution_readiness="ready",
    )

    selection = select_playbooks(
        "inspect this unusual business dataset",
        intent,
        dataset_profile=_loaded_context(),
        llm_client=client,
    )

    assert client.calls == 1
    assert selection.primary_playbook_id == "data_understanding"


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
def test_p08_method_selection_no_longer_creates_confirmation():
    """P08-01 契约更新：原断言方法模板会创建可回答的 method pending；
    新原则下方法运行不需要通用审批——选择只写 spec/路径/数据要求，
    模板风险说明降为审计元数据（template_risk_note）。"""
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

    assert not [
        item for item in state.pending_confirmations
        if item.get("confirmation_type") == "method_confirmation"
    ]
    assert selection.requires_confirmation is False
    assert selection.template_risk_note  # 审计提示保留，不再是签发权
    assert state.analysis_spec is not None
    assert state.last_recommended_paths


@patch("data_agent.agent.llm_playbook.select_playbook_llm", _no_llm_playbook)
def test_method_confirmation_uses_new_selection_spec_when_existing_state_has_stale_spec():
    state = AnalysisSessionState(session_id="method_stale_spec", data_state="data_loaded")
    state.set_analysis_spec({
        "id": "old_spec",
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
    assert selection.analysis_spec is not None
    selection.analysis_spec["id"] = "new_forecast_spec"

    apply_selection_to_state(state, selection)

    # P08-01：spec 替换语义保留；不再产生方法确认
    assert state.analysis_spec["id"] == selection.analysis_spec["id"]
    assert state.analysis_spec["playbook_id"] == "forecast_decision_simulation"
    assert not [
        item for item in state.pending_confirmations
        if item.get("related_spec_id") == selection.analysis_spec["id"]
    ]


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
        # P08-01：新选择不再创建确认；这里手工注入旧形状的 pending，
        # 验证历史会话在恢复/应答时的解析安全性不回退。
        confirmation = state.add_confirmation({
            "id": f"method_forecast_{state.analysis_spec['id']}",
            "confirmation_type": "method_confirmation",
            "related_spec_id": state.analysis_spec["id"],
            "source": "method_playbook",
            "state_updates": json.dumps(
                {
                    "stage": "plan",
                    "method_confirmation": {
                        "playbook_id": "forecast_decision_simulation",
                        "analysis_spec_id": state.analysis_spec["id"],
                        "allowed_actions": ["confirm_method", "clarify_method_scope"],
                    },
                },
                ensure_ascii=False,
            ),
        })
        updates = json.loads(confirmation["state_updates"])

        assert updates["stage"] in STAGES
        assert updates["method_confirmation"]["analysis_spec_id"] == state.analysis_spec["id"]

        result = state.resolve_confirmation(confirmation["id"], answer)

        assert result is not None
        assert result["status"] == "resolved"
        assert state.stage in STAGES
        assert state.active_scope["active_mode"] in {"consulting", "data_loaded", "analysis", "artifact_review"}


@patch("data_agent.agent.llm_playbook.select_playbook_llm", _no_llm_playbook)
def test_p08_forecast_capability_not_blocked_by_method_state():
    """P08-01/Q07 契约更新：原断言 forecast 能力在方法确认前被封锁；
    新原则下能力名称不是确认理由——方法状态（无论已选/待澄清）不封锁；
    只有 affected_operations 覆盖该能力的语义确认才封锁。"""
    intent = TurnIntent(
        intent_type="directed_analysis",
        clarity="clear",
        data_state="data_loaded",
        analysis_stage="plan",
        recommended_action="run_analysis",
        execution_readiness="ready",
    )
    controller = AnalysisFlowController("method_scope_resolution")

    state = AnalysisSessionState(session_id="method_scope_clarify", data_state="data_loaded")
    selection = choose_playbook("forecast next month revenue and estimate ROI", intent, has_data=True)
    apply_selection_to_state(state, selection)

    assert controller.is_capability_blocked_by_confirmation(state, "analysis.forecast") is False

    # 语义确认明确覆盖该能力时仍封锁（保留真正的语义依赖门）
    state.add_confirmation({
        "id": "window_semantic_gate",
        "confirmation_type": "time_window",
        "status": "pending",
        "question": "请确认预测的时间窗口",
        "options": [],
        "state_updates": "{}",
        "affected_operations": ["analysis.forecast"],
    })
    assert controller.is_capability_blocked_by_confirmation(state, "analysis.forecast") is True
    assert controller.is_capability_blocked_by_confirmation(state, "analysis.causal") is False


@patch("data_agent.agent.llm_playbook.select_playbook_llm", _no_llm_playbook)
def test_changed_high_risk_request_replaces_spec_and_requires_new_confirmation():
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
    assert first.analysis_spec is not None
    assert first.analysis_spec["id"]
    apply_selection_to_state(state, first)
    first_spec_id = state.analysis_spec["id"]

    second = choose_playbook("forecast cost and ROI next quarter", intent, has_data=True)
    duplicate_second = choose_playbook("forecast cost and ROI next quarter", intent, has_data=True)
    assert second.analysis_spec is not None
    assert duplicate_second.analysis_spec is not None
    assert second.primary_playbook_id == first.primary_playbook_id
    assert second.analysis_spec["id"] != first_spec_id
    assert duplicate_second.analysis_spec["id"] == second.analysis_spec["id"]

    apply_selection_to_state(state, second)
    apply_selection_to_state(state, duplicate_second)

    second_spec_id = second.analysis_spec["id"]
    assert state.analysis_spec["id"] == second_spec_id
    assert state.analysis_spec["goal"] == "forecast cost and ROI next quarter"
    assert state.goal == "forecast cost and ROI next quarter"
    # P08-01：更换请求替换 spec，但不再要求新的方法确认
    assert not [
        item for item in state.pending_confirmations
        if item.get("related_spec_id") == second_spec_id and item.get("status") == "pending"
    ]


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


@patch("data_agent.agent.llm_playbook.select_playbook_llm", _no_llm_playbook)
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
def test_controller_keeps_generated_legacy_spec_display_only(tmp_path):
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

        assert state.analysis_spec is not None
        assert state.analysis_spec.get("contract_version") is None
        assert state.analysis_spec.get("workflow_id") is None
        assert first_tasks == []
        assert second_tasks == []
    finally:
        task_manager._dir = old_task_dir
        task_manager._next_id_val = old_next_id


@patch("data_agent.agent.llm_playbook.select_playbook_llm", _no_llm_playbook)
def test_playbook_legacy_analysis_spec_is_display_only(tmp_path):
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
            result = json.loads(record_analysis_spec(json.dumps(selection.analysis_spec)))

        assert result["workflow"] == {
            "created": 0,
            "task_ids": [],
            "display_only": True,
            "reason": "legacy_analysis_spec_display_only",
        }
        assert task_manager.list_for_scope(session_id="playbook_tasks") == []
    finally:
        task_manager._dir = old_task_dir
        task_manager._next_id_val = old_next_id
