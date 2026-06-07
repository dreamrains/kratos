from data_agent.agent.analysis_entry import decide_analysis_entry
from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.intent import TurnIntent


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
    state = AnalysisSessionState(session_id="entry_tests", data_state="data_loaded")
    state.dataset_contracts = [{
        "id": "duc_sales",
        "dataset": "sales",
        "quality": {"status": "ready", "score": 96},
        "field_roles": {
            "date": ["date"],
            "metrics": ["revenue", "orders"],
            "dimensions": ["channel"],
            "ids": ["user_id"],
        },
        "supported_analyses": ["trend", "period_compare", "dimension_decomposition"],
        "unsupported_analyses": [],
    }]
    state.route_proposals = [
        {
            "id": "route_trend",
            "dataset": "sales",
            "direction": "trend",
            "limitations": ["Descriptive trend only"],
            "evidence_requirements": ["date", "metric"],
        },
        {
            "id": "route_compare",
            "dataset": "sales",
            "direction": "period_compare",
            "limitations": ["Requires comparable periods"],
            "evidence_requirements": ["date", "metric", "period coverage"],
        },
    ]
    return state


def test_supported_trend_request_returns_direct_analysis():
    decision = decide_analysis_entry("show revenue trend", _intent(), _state())

    assert decision["decision"] == "direct_analysis"
    assert decision["dataset"] == "sales"
    assert decision["route"] == "trend"
    assert decision["reason"] == "The request matches a supported data route."
    assert decision["confidence"] == "medium"
    assert decision["required_user_action"] == ""
    assert decision["limitations"] == ["Descriptive trend only"]
    assert decision["evidence_requirements"] == ["date", "metric"]


def test_vague_request_with_multiple_routes_returns_clarify_intent():
    vague = _intent(
        "intent_negotiation",
        clarity="vague",
        analysis_stage="discover",
        recommended_action="guide_analysis",
    )

    decision = decide_analysis_entry("help me analyze this data", vague, _state())

    assert decision["decision"] == "clarify_intent"
    assert decision["reason"] == "Multiple data-supported analysis routes are available."
    assert decision["route"] == ""
    assert decision["required_user_action"] == "choose_analysis_route"
    assert decision["route_options"] == [
        {"direction": "trend", "label": "trend", "dataset": "sales"},
        {"direction": "period_compare", "label": "period_compare", "dataset": "sales"},
    ]


def test_unsupported_retention_request_returns_request_data():
    state = _state()
    state.dataset_contracts[0]["unsupported_analyses"] = [
        {"type": "user_level_retention", "reason": "aggregate grain and missing user id"}
    ]

    decision = decide_analysis_entry("analyze cohort retention", _intent(), state)

    assert decision["decision"] == "request_data"
    assert decision["reason"] == "The loaded data cannot support user-level retention analysis."
    assert decision["route"] == ""
    assert decision["required_user_action"] == "provide_user_level_retention_data"
    assert decision["limitations"] == ["aggregate grain and missing user id"]


def test_cleaning_confirmation_on_required_field_returns_clarify_intent():
    state = _state()
    state.cleaning_logs = [{
        "dataset": "sales",
        "decisions": [{
            "column": "date",
            "decision_type": "needs_confirmation",
            "impact": "Date parsing changed the original column type",
        }],
    }]

    decision = decide_analysis_entry("show revenue trend", _intent(), state)

    assert decision["decision"] == "clarify_intent"
    assert decision["reason"] == "A required field has a cleaning decision that needs confirmation."
    assert decision["required_user_action"] == "confirm_cleaning_decision"
    assert decision["risk_fields"] == ["date"]


def test_blocked_quality_returns_blocked():
    state = _state()
    state.dataset_contracts[0]["quality"] = {
        "status": "blocked",
        "block_issues": ["date column has no usable values"],
    }

    decision = decide_analysis_entry("show revenue trend", _intent(), state)

    assert decision["decision"] == "blocked"
    assert decision["reason"] == "Data quality blocks formal analysis."
    assert decision["required_user_action"] == "resolve_data_quality"
    assert decision["limitations"] == ["date column has no usable values"]
