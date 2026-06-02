from data_agent.agent.intent import TurnIntent
from data_agent.agent.intent_refinement import refine_intent_with_data


def _intent(intent_type="directed_analysis", **overrides):
    values = {
        "intent_type": intent_type,
        "clarity": "clear",
        "data_state": "data_loaded",
        "analysis_stage": "execute",
        "recommended_action": "run_analysis",
        "execution_readiness": "ready",
        "reason": "initial",
        "ambiguities": [{"kind": "existing", "detail": "kept"}],
    }
    values.update(overrides)
    return TurnIntent(**values)


def test_blocked_quality_contract_requests_clarification_for_directed_analysis_without_mutating_original():
    original = _intent()
    contracts = [{
        "id": "duc_main_blocked",
        "dataset": "main",
        "quality": {
            "status": "blocked",
            "block_issues": ["date column cannot be parsed"],
        },
    }]

    refined = refine_intent_with_data("analyze revenue trend", original, contracts, [])

    assert refined is not original
    assert refined.clarity == "clarification_needed"
    assert refined.analysis_stage == "scope"
    assert refined.recommended_action == "ask_question"
    assert refined.execution_readiness == "insufficient_data"
    assert refined.ambiguities[-1]["kind"] == "data_quality"
    assert refined.ambiguities[-1]["contracts"] == ["duc_main_blocked"]
    assert original.clarity == "clear"
    assert original.ambiguities == [{"kind": "existing", "detail": "kept"}]


def test_blocked_quality_contract_requests_clarification_for_comprehensive_report():
    original = _intent("comprehensive_report", analysis_stage="report", recommended_action="generate_report")
    contracts = [{"id": "duc_orders", "dataset": "orders", "quality": {"status": "blocked"}}]

    refined = refine_intent_with_data("make a full report", original, contracts, [])

    assert refined.clarity == "clarification_needed"
    assert refined.analysis_stage == "scope"
    assert refined.recommended_action == "ask_question"
    assert refined.execution_readiness == "insufficient_data"
    assert refined.ambiguities[-1]["kind"] == "data_quality"


def test_retention_request_with_unsupported_user_level_retention_requests_data():
    original = _intent()
    contracts = [{
        "id": "duc_main",
        "dataset": "main",
        "unsupported_analyses": [
            {"type": "user_level_retention", "reason": "Data is missing user or entity id columns"},
        ],
    }]

    refined = refine_intent_with_data("请分析用户留存和 cohort", original, contracts, [])

    assert refined.clarity == "clarification_needed"
    assert refined.analysis_stage == "scope"
    assert refined.recommended_action == "request_data"
    assert refined.execution_readiness == "insufficient_data"
    assert refined.ambiguities[-1]["kind"] == "unsupported_analysis"
    assert refined.ambiguities[-1]["analysis_type"] == "user_level_retention"
    assert refined.ambiguities[-1]["contracts"] == ["duc_main"]


def test_intent_negotiation_with_routes_keeps_guidance_and_adds_top_three_routes():
    original = _intent(
        "intent_negotiation",
        clarity="clear",
        analysis_stage="discover",
        recommended_action="guide_analysis",
    )
    routes = [
        {"label": "Revenue trend", "direction": "trend"},
        {"label": "Period comparison", "direction": "period_compare"},
        {"direction": "dimension_decomposition"},
        {"label": "Correlation", "direction": "correlation"},
    ]

    refined = refine_intent_with_data("帮我看看这份数据", original, [], routes)

    assert refined.intent_type == "intent_negotiation"
    assert refined.recommended_action == "guide_analysis"
    assert refined.clarity == original.clarity
    route_ambiguity = refined.ambiguities[-1]
    assert route_ambiguity["kind"] == "analysis_route"
    assert route_ambiguity["routes"] == [
        {"label": "Revenue trend", "direction": "trend"},
        {"label": "Period comparison", "direction": "period_compare"},
        {"label": "dimension_decomposition", "direction": "dimension_decomposition"},
    ]


def test_other_intents_return_same_intent_instance():
    original = _intent("knowledge_qa", data_state="unknown", analysis_stage="follow_up", recommended_action="answer_directly")

    refined = refine_intent_with_data("what is retention", original, [], [{"direction": "trend"}])

    assert refined is original
