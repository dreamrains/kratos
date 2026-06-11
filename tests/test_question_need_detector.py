from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.intent import TurnIntent
from data_agent.agent.question_need_detector import detect_question_need


def _intent(intent_type="directed_analysis", **overrides):
    values = {
        "intent_type": intent_type,
        "clarity": "clear",
        "data_state": "data_loaded",
        "analysis_stage": "execute",
        "recommended_action": "run_analysis",
        "execution_readiness": "ready",
        "reason": "test",
        "ambiguities": [],
    }
    values.update(overrides)
    return TurnIntent(**values)


def _state():
    state = AnalysisSessionState(session_id="question_need", data_state="data_loaded")
    state.active_scope["active_dataset"] = "orders"
    state.active_scope["active_mode"] = "data_loaded"
    state.dataset_contracts = [{
        "dataset": "orders",
        "quality": {"status": "ready"},
        "field_roles": {
            "date": ["order_date"],
            "metrics": ["revenue", "orders"],
            "rate_metrics": ["conversion_rate"],
            "dimensions": ["channel"],
        },
    }]
    state.route_proposals = [
        {
            "id": "route_trend",
            "dataset": "orders",
            "direction": "trend",
            "label": "Revenue trend",
            "evidence_requirements": ["order_date", "revenue"],
        },
        {
            "id": "route_compare",
            "dataset": "orders",
            "direction": "period_compare",
            "label": "Period comparison",
            "evidence_requirements": ["order_date", "revenue", "period coverage"],
        },
    ]
    return state


def test_vague_goal_with_multiple_routes_requires_route_question():
    gate = detect_question_need(
        "please analyze this dataset",
        _intent("intent_negotiation", clarity="vague", analysis_stage="discover", recommended_action="guide_analysis"),
        _state(),
    )

    assert gate["status"] == "hard_question"
    assert gate["question_type"] == "route_selection"
    assert gate["blocking_surfaces"] == ["direct_recommendation", "analysis_execution", "report_generation"]
    assert [option["value"] for option in gate["options"]] == ["trend", "period_compare"]


def test_metric_ambiguity_requires_metric_scope_question():
    state = _state()

    gate = detect_question_need("analyze performance trend", _intent(), state)

    assert gate["status"] == "hard_question"
    assert gate["question_type"] == "metric_scope"
    assert [option["value"] for option in gate["options"]] == ["revenue", "orders", "conversion_rate"]


def test_period_comparison_requires_time_window_question_when_missing_window():
    state = _state()

    gate = detect_question_need("compare revenue", _intent(), state)

    assert gate["status"] == "hard_question"
    assert gate["question_type"] == "time_window"
    assert "period" in gate["reason"].lower()


def test_high_risk_predictive_analysis_requires_method_confirmation():
    gate = detect_question_need("predict next month revenue", _intent(), _state())

    assert gate["status"] == "hard_question"
    assert gate["question_type"] == "method_confirmation"
    assert gate["blocking_surfaces"] == ["analysis_execution", "report_generation"]


def test_consulting_and_knowledge_questions_do_not_block():
    state = _state()

    gate = detect_question_need("what is cohort analysis", _intent("knowledge_qa", recommended_action="answer_directly"), state)

    assert gate["status"] == "clear"
    assert gate["blocking_surfaces"] == []


def test_clear_metric_and_route_do_not_ask_unnecessarily():
    gate = detect_question_need("show revenue trend by date", _intent(), _state())

    assert gate["status"] == "clear"
    assert gate["question_type"] == ""


def test_cleaning_risk_on_required_field_requires_data_quality_question():
    state = _state()
    state.cleaning_logs = [{
        "dataset": "orders",
        "decisions": [
            {"column": "order_date", "decision_type": "needs_confirmation"},
        ],
    }]

    gate = detect_question_need("show revenue trend", _intent(), state)

    assert gate["status"] == "hard_question"
    assert gate["question_type"] == "data_quality_confirmation"
    assert gate["risk_fields"] == ["order_date"]
