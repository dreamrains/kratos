from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.intent import TurnIntent
from data_agent.agent.question_need_detector import detect_question_need
import pytest


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


def test_pending_file_relationship_requires_hard_question():
    state = _state()
    state.file_relationships = [{
        "relationship_id": "rel_orders_history",
        "status": "possibly_linked",
        "requires_confirmation": True,
        "confirmation_type": "join_logic_confirmation",
        "new_files": ["orders_latest.csv"],
        "existing_files": ["orders_history.csv"],
        "uncertainties": ["Shared IDs exist but business theme evidence is unclear."],
    }]

    gate = detect_question_need("analyze revenue trend", _intent(), state)

    assert gate["status"] == "hard_question"
    assert gate["question_type"] == "join_logic_confirmation"
    assert gate["reason"] == "Shared IDs exist but business theme evidence is unclear."
    assert gate["state_updates"] == {
        "stage": "scope",
        "file_relationship_confirmation": {"relationship_id": "rel_orders_history"},
    }
    assert [option["value"] for option in gate["options"]] == [
        "include_in_active_bundle",
        "separate_bundle",
        "latest_only",
    ]


def test_file_exclusion_confirmation_uses_include_or_exclude_options():
    state = _state()
    state.file_relationships = [{
        "relationship_id": "rel_independent",
        "status": "independent",
        "requires_confirmation": True,
        "confirmation_type": "file_exclusion_confirmation",
        "uncertainties": ["User may know an external relationship not visible in the file profiles."],
    }]

    gate = detect_question_need("analyze the data", _intent(), state)

    assert gate["status"] == "hard_question"
    assert gate["question_type"] == "file_exclusion_confirmation"
    assert [option["value"] for option in gate["options"]] == [
        "include_in_active_bundle",
        "exclude_from_active_bundle",
    ]


def test_latest_only_request_skips_file_relationship_confirmation():
    state = _state()
    state.file_relationships = [{
        "relationship_id": "rel_latest_only",
        "status": "possibly_linked",
        "requires_confirmation": True,
        "confirmation_type": "file_relationship_confirmation",
        "uncertainties": ["Shared IDs exist but business theme evidence is unclear."],
    }]

    gate = detect_question_need("only analyze latest file revenue trend", _intent(), state)

    assert gate["status"] == "clear"


@pytest.mark.parametrize("user_input", [
    "exclude historical files",
    "ignore history",
    "no history",
])
def test_explicit_history_exclusion_skips_file_relationship_confirmation(user_input):
    state = _state()
    state.file_relationships = [{
        "relationship_id": "rel_exclude_history",
        "status": "possibly_linked",
        "requires_confirmation": True,
        "confirmation_type": "file_relationship_confirmation",
        "uncertainties": ["Shared IDs exist but business theme evidence is unclear."],
    }]

    gate = detect_question_need(user_input, _intent(), state)

    assert gate["status"] == "clear"


def test_latest_with_historical_comparison_still_requires_relationship_confirmation():
    state = _state()
    state.file_relationships = [{
        "relationship_id": "rel_latest_compare_history",
        "status": "possibly_linked",
        "requires_confirmation": True,
        "confirmation_type": "file_relationship_confirmation",
        "uncertainties": ["Shared IDs exist but business theme evidence is unclear."],
    }]

    gate = detect_question_need(
        "only analyze the latest file and compare it with historical orders",
        _intent(),
        state,
    )

    assert gate["status"] == "hard_question"
    assert gate["question_type"] == "file_relationship_confirmation"


def test_consulting_intent_does_not_block_on_pending_file_relationship():
    state = _state()
    state.file_relationships = [{
        "relationship_id": "rel_consulting",
        "status": "possibly_linked",
        "requires_confirmation": True,
        "confirmation_type": "file_relationship_confirmation",
        "uncertainties": ["Shared IDs exist but business theme evidence is unclear."],
    }]

    gate = detect_question_need(
        "what is a good way to compare these files?",
        _intent("analysis_consultation", recommended_action="answer_directly"),
        state,
    )

    assert gate["status"] == "clear"
