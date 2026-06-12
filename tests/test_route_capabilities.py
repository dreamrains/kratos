from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.route_capabilities import build_route_capabilities
from data_agent.agent.trust_contracts import build_route_proposals


def test_builds_ready_executable_routes_for_active_dataset():
    state = AnalysisSessionState(session_id="s1", data_state="data_loaded")
    state.active_scope["active_dataset"] = "orders"
    state.active_scope["active_mode"] = "data_loaded"
    state.dataset_contracts = [
        {
            "dataset": "orders",
            "supported_analyses": ["cohort", "funnel"],
            "unsupported_analyses": [
                {"type": "user_level_retention", "reason": "missing event history"}
            ],
        },
        {"dataset": "old_sales", "supported_analyses": ["trend"]},
    ]
    state.route_proposals = [
        {
            "id": "route_cohort",
            "dataset": "orders",
            "direction": "cohort",
            "label": "Cohort",
            "reason": "user id and order date exist",
            "limitations": ["descriptive only"],
            "evidence_requirements": ["user_id", "order_date"],
        },
        {"id": "route_old", "dataset": "old_sales", "direction": "trend"},
    ]

    model = build_route_capabilities(state)

    assert model["active_dataset"] == "orders"
    assert [item["route"] for item in model["executable"]] == ["cohort"]
    assert model["executable"][0]["category"] == "ready"
    assert model["executable"][0]["auto_submit"] is False
    assert model["exploratory"] == [
        {
            "id": "explore_orders_user_level_retention",
            "dataset": "orders",
            "analysis": "user_level_retention",
            "label": "user_level_retention",
            "category": "needs_more_data",
            "reason": "missing event history",
            "data_requirements": [],
            "value_if_available": "",
            "prompt": (
                'I want to explore "user_level_retention". Please tell me what data is missing, '
                "why the current data cannot verify it, and what dataset would be needed."
            ),
        }
    ]


def test_executable_route_carries_data_supported_basis():
    state = AnalysisSessionState(session_id="support_guard", data_state="data_loaded")
    state.active_scope["active_dataset"] = "orders"
    state.active_scope["active_mode"] = "data_loaded"
    state.dataset_contracts = [{
        "dataset": "orders",
        "field_roles": {
            "date": ["order_date"],
            "metrics": ["revenue"],
            "dimensions": ["channel"],
            "ids": ["user_id"],
        },
        "supported_analyses": ["trend"],
    }]
    state.route_proposals = [{
        "id": "route_trend",
        "dataset": "orders",
        "direction": "trend",
        "label": "Revenue trend",
        "reason": "date and revenue fields exist",
        "evidence_requirements": ["order_date", "revenue"],
    }]

    model = build_route_capabilities(state)

    route = model["executable"][0]
    assert route["support_status"] == "supported"
    assert route["support_basis"] == "data_supported"
    assert route["support_reasons"] == ["date and revenue fields exist"]
    assert route["missing_requirements"] == []


def test_route_missing_required_fields_becomes_exploratory_not_executable():
    state = AnalysisSessionState(session_id="support_guard_missing", data_state="data_loaded")
    state.active_scope["active_dataset"] = "orders"
    state.active_scope["active_mode"] = "data_loaded"
    state.dataset_contracts = [{
        "dataset": "orders",
        "field_roles": {"date": ["order_date"], "metrics": ["revenue"]},
        "unsupported_analyses": [],
    }]
    state.route_proposals = [{
        "id": "route_retention",
        "dataset": "orders",
        "direction": "cohort",
        "label": "Retention",
        "reason": "retention may answer lifecycle questions",
        "evidence_requirements": ["user_id", "event_date"],
    }]

    model = build_route_capabilities(state)

    assert model["executable"] == []
    assert model["exploratory"][0]["category"] == "needs_more_data"
    assert model["exploratory"][0]["support_status"] == "needs_more_data"
    assert model["exploratory"][0]["missing_requirements"] == ["user_id", "event_date"]


def test_route_key_is_accepted_as_executable_direction():
    state = AnalysisSessionState(session_id="s1", data_state="data_loaded")
    state.active_scope["active_dataset"] = "orders"
    state.active_scope["active_mode"] = "data_loaded"
    state.route_proposals = [
        {"id": "route_trend", "dataset": "orders", "route": "trend", "label": "Trend"}
    ]

    model = build_route_capabilities(state)

    assert [item["direction"] for item in model["executable"]] == ["trend"]
    assert [item["route"] for item in model["executable"]] == ["trend"]


def test_route_key_uses_field_roles_for_cleaning_confirmation():
    state = AnalysisSessionState(session_id="s1", data_state="data_loaded")
    state.active_scope["active_dataset"] = "orders"
    state.active_scope["active_mode"] = "data_loaded"
    state.route_proposals = [
        {
            "id": "route_trend",
            "dataset": "orders",
            "route": "trend",
            "field_roles": {"date": ["order_date"]},
        }
    ]
    state.cleaning_logs = [
        {
            "dataset": "orders",
            "decisions": [
                {"column": "order_date", "decision_type": "needs_confirmation"}
            ],
        }
    ]

    model = build_route_capabilities(state)

    assert model["executable"] == []
    assert model["confirmation_gate"]["status"] == "needs_confirmation"
    assert model["confirmation_gate"]["confirmation_type"] == "data_quality_confirmation"
    assert model["confirmation_gate"]["risk_fields"] == ["order_date"]


def test_cleaning_confirmation_downgrades_executable_route():
    state = AnalysisSessionState(session_id="s1", data_state="data_loaded")
    state.active_scope["active_dataset"] = "orders"
    state.active_scope["active_mode"] = ""
    state.dataset_contracts = [{"dataset": "orders", "supported_analyses": ["cohort"]}]
    state.route_proposals = [
        {
            "id": "route_cohort",
            "dataset": "orders",
            "direction": "cohort",
            "label": "Cohort",
            "evidence_requirements": ["order_date"],
        }
    ]
    state.cleaning_logs = [
        {
            "dataset": "orders",
            "decisions": [
                {
                    "column": "order_date",
                    "decision_type": "needs_confirmation",
                    "impact": "date parsing changed values",
                }
            ],
        }
    ]

    model = build_route_capabilities(state)

    assert model["executable"] == []
    assert model["confirmation_gate"]["status"] == "needs_confirmation"
    assert model["confirmation_gate"]["affected_routes"] == ["cohort"]
    assert "order_date" in model["confirmation_gate"]["question"]


def test_consulting_mode_hides_executable_routes_but_keeps_exploratory_context():
    state = AnalysisSessionState(session_id="s1")
    state.active_scope["active_mode"] = "consulting"
    state.last_recommended_paths = [
        {"id": "retention_lifecycle", "title": "Retention lifecycle", "data_requirements": ["user_id"]}
    ]

    model = build_route_capabilities(state)

    assert model["executable"] == []
    assert model["exploratory"][0]["category"] == "method_discussion"


def test_explicit_consulting_mode_wins_even_with_loaded_active_dataset():
    state = AnalysisSessionState(session_id="s1", data_state="data_loaded")
    state.active_scope["active_dataset"] = "orders"
    state.active_scope["active_mode"] = "consulting"
    state.route_proposals = [
        {"id": "route_cohort", "dataset": "orders", "direction": "cohort", "label": "Cohort"}
    ]
    state.last_recommended_paths = [
        {"id": "retention_lifecycle", "title": "Retention lifecycle", "data_requirements": ["user_id"]}
    ]

    model = build_route_capabilities(state)

    assert model["active_mode"] == "consulting"
    assert model["executable"] == []
    assert model["exploratory"][0]["category"] == "method_discussion"


def test_generated_trend_route_field_roles_trigger_cleaning_confirmation():
    state = AnalysisSessionState(session_id="s1", data_state="data_loaded")
    state.active_scope["active_dataset"] = "orders"
    state.active_scope["active_mode"] = "data_loaded"
    state.route_proposals = build_route_proposals({
        "id": "duc_orders_001",
        "dataset": "orders",
        "field_roles": {
            "date": ["date"],
            "metrics": ["gmv"],
            "rate_metrics": [],
            "dimensions": ["channel"],
            "ids": [],
        },
        "supported_analyses": ["trend"],
    })
    state.cleaning_logs = [
        {
            "dataset": "orders",
            "decisions": [
                {"column": "date", "decision_type": "needs_confirmation"}
            ],
        }
    ]

    model = build_route_capabilities(state)

    assert model["executable"] == []
    assert model["confirmation_gate"]["status"] == "needs_confirmation"
    assert model["confirmation_gate"]["affected_routes"] == ["trend"]
    assert model["confirmation_gate"]["risk_fields"] == ["date"]


def test_pending_confirmation_hides_current_recommendations_without_exposing_candidates():
    state = AnalysisSessionState(session_id="s1", data_state="data_loaded")
    state.active_scope["active_dataset"] = "orders"
    state.active_scope["active_mode"] = "data_loaded"
    state.route_proposals = [
        {"id": "route_trend", "dataset": "orders", "direction": "trend"},
        {"id": "route_compare", "dataset": "orders", "direction": "period_compare"},
    ]
    state.pending_confirmations = [
        {
            "id": "method_gate",
            "status": "pending",
            "confirmation_type": "route_selection",
            "question": "请先确认分析目标",
            "blocking_reason": "目标会影响推荐方向",
        }
    ]

    model = build_route_capabilities(state)

    assert model["executable"] == []
    assert model["counts"]["executable"] == 0
    assert model["confirmation_gate"] == {
        "status": "needs_confirmation",
        "confirmation_type": "route_selection",
        "question": "请先确认分析目标",
        "blocking_reason": "目标会影响推荐方向",
        "risk_fields": [],
        "affected_routes": [],
        "blocked_surfaces": ["direct_recommendation", "analysis_execution", "report_generation"],
    }


def test_limit_zero_returns_no_capability_items():
    state = AnalysisSessionState(session_id="s1", data_state="data_loaded")
    state.active_scope["active_dataset"] = "orders"
    state.active_scope["active_mode"] = "data_loaded"
    state.dataset_contracts = [
        {
            "dataset": "orders",
            "unsupported_analyses": [{"type": "user_level_retention"}],
        }
    ]
    state.route_proposals = [
        {"id": "route_cohort", "dataset": "orders", "direction": "cohort"}
    ]

    model = build_route_capabilities(state, limit=0)

    assert model["executable"] == []
    assert model["exploratory"] == []
    assert model["counts"] == {"executable": 0, "exploratory": 0}
