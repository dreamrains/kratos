from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.route_capabilities import build_route_capabilities


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


def test_cleaning_confirmation_downgrades_executable_route():
    state = AnalysisSessionState(session_id="s1", data_state="data_loaded")
    state.active_scope["active_dataset"] = "orders"
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

    assert model["executable"][0]["category"] == "needs_confirmation"
    assert model["executable"][0]["risk_fields"] == ["order_date"]
    assert "Before running" in model["executable"][0]["prompt"]


def test_consulting_mode_hides_executable_routes_but_keeps_exploratory_context():
    state = AnalysisSessionState(session_id="s1")
    state.active_scope["active_mode"] = "consulting"
    state.last_recommended_paths = [
        {"id": "retention_lifecycle", "title": "Retention lifecycle", "data_requirements": ["user_id"]}
    ]

    model = build_route_capabilities(state)

    assert model["executable"] == []
    assert model["exploratory"][0]["category"] == "method_discussion"
