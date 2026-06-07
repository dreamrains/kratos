from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.trust_view import build_trust_view


def test_none_state_returns_empty_view_for_requested_session():
    assert build_trust_view(None, session_id="missing") == {
        "status": "empty",
        "session_id": "missing",
        "updated_at": "",
        "datasets": [],
        "routes": [],
        "risks": [],
        "verification": None,
    }


def test_dataset_summaries_combine_contracts_and_preview_digests():
    state = AnalysisSessionState(session_id="s1", updated_at="2026-06-07 10:00:00")
    state.dataset_contracts = [
        {
            "dataset": "sales",
            "row_count": 120,
            "column_count": 3,
            "quality": {
                "status": "warning",
                "score": 0.82,
            },
            "field_roles": {
                "date": ["date"],
                "metrics": ["revenue", "orders", "margin", "discount"],
                "rate_metrics": ["conversion"],
                "dimensions": ["region", "channel"],
                "ids": ["order_id"],
            },
            "supported_analyses": ["trend", "segment"],
        }
    ]
    state.preview_digests = [
        {
            "dataset": "sales",
            "notable_patterns": ["3 null regions", "date is daily"],
            "risks": ["10 rows sampled", "extra note"],
        }
    ]

    view = build_trust_view(state)

    assert view["status"] == "ready"
    assert view["datasets"] == [
        {
            "dataset": "sales",
            "rows": 120,
            "columns": 3,
            "quality_status": "warning",
            "quality_score": 0.82,
            "key_fields": ["date", "revenue", "orders", "margin", "discount", "conversion"],
            "supported_analyses": ["trend", "segment"],
            "preview_notes": ["3 null regions", "date is daily", "10 rows sampled"],
        }
    ]


def test_route_cards_are_limited_skip_malformed_and_include_editable_prompt():
    state = AnalysisSessionState(session_id="s1", data_state="data_loaded")
    state.route_proposals = [
        {"direction": "trend", "label": "Trend", "reason": "Time column exists", "budget_level": "low"},
        {"label": "Missing direction"},
        "not a dict",
        {"direction": "segment", "label": "Segment", "limitations": ["few dimensions"]},
        {"direction": "compare", "label": "Compare"},
        {"direction": "forecast", "label": "Forecast"},
        {"direction": "extra", "label": "Extra"},
    ]

    routes = build_trust_view(state)["routes"]

    assert len(routes) == 4
    assert [route["direction"] for route in routes] == ["trend", "segment", "compare", "forecast"]
    assert routes[0]["prompt"].startswith("Please analyze the current dataset")
    assert "trend" in routes[0]["prompt"]
    assert routes[0]["auto_submit"] is False


def test_risk_items_include_quality_unsupported_and_cleaning_decisions():
    state = AnalysisSessionState(session_id="s1")
    state.dataset_contracts = [
        {
            "dataset": "sales",
            "quality": {
                "block_issues": [
                    {"field": "revenue", "message": "Revenue has negative values"},
                    "Dataset has duplicate rows",
                ],
                "warnings": [
                    {"field": "region", "message": "Region has missing values"},
                ],
            },
            "unsupported_analyses": [
                {"analysis": "causal", "reason": "No treatment assignment"},
                "forecasting",
            ],
        }
    ]
    state.cleaning_logs = [
        {
            "dataset": "sales",
            "decisions": [
                {
                    "field": "date",
                    "decision_type": "needs_confirmation",
                    "message": "Confirm date parsing",
                },
                {
                    "field": "cost",
                    "decision_type": "blocked",
                    "reason": "Cannot infer currency",
                },
                {"decision_type": "auto_cleaned", "message": "not a risk"},
            ],
        },
    ]

    risks = build_trust_view(state)["risks"]

    assert risks == [
        {
            "severity": "blocked",
            "source": "data_quality",
            "dataset": "sales",
            "field": "revenue",
            "message": "Revenue has negative values",
        },
        {
            "severity": "blocked",
            "source": "data_quality",
            "dataset": "sales",
            "field": "",
            "message": "Dataset has duplicate rows",
        },
        {
            "severity": "warning",
            "source": "data_quality",
            "dataset": "sales",
            "field": "region",
            "message": "Region has missing values",
        },
        {
            "severity": "warning",
            "source": "unsupported_analysis",
            "dataset": "sales",
            "field": "causal",
            "message": "No treatment assignment",
        },
        {
            "severity": "warning",
            "source": "unsupported_analysis",
            "dataset": "sales",
            "field": "",
            "message": "forecasting",
        },
        {
            "severity": "warning",
            "source": "cleaning",
            "dataset": "sales",
            "field": "date",
            "message": "Confirm date parsing",
        },
        {
            "severity": "blocked",
            "source": "cleaning",
            "dataset": "sales",
            "field": "cost",
            "message": "Cannot infer currency",
        },
    ]


def test_latest_verification_report_becomes_summary_and_counts_claim_checks():
    state = AnalysisSessionState(session_id="s1")
    state.verification_reports = [
        {"id": "old", "overall_status": "failed", "claim_count": 99},
        {
            "id": "latest",
            "overall_status": "pass_with_downgrades",
            "failed_count": 1,
            "downgraded_count": 2,
            "evidence_signature": "abc123",
            "created_at": "2026-06-07 11:00:00",
            "claim_checks": [{"claim": "a"}, {"claim": "b"}, "bad"],
        },
    ]

    assert build_trust_view(state)["verification"] == {
        "id": "latest",
        "status": "pass_with_downgrades",
        "claim_count": 2,
        "failed_count": 1,
        "downgraded_count": 2,
        "evidence_signature": "abc123",
        "created_at": "2026-06-07 11:00:00",
    }


def test_malformed_refs_are_ignored_and_loaded_state_is_ready():
    state = AnalysisSessionState(session_id="s1", data_state="data_loaded", updated_at="now")
    state.dataset_contracts = {"dataset": "bad"}
    state.preview_digests = "bad"
    state.route_proposals = [{"label": "bad"}]
    state.cleaning_logs = "bad"
    state.verification_reports = {"id": "bad"}

    view = build_trust_view(state)

    assert view == {
        "status": "ready",
        "session_id": "s1",
        "updated_at": "now",
        "datasets": [],
        "routes": [],
        "risks": [],
        "verification": None,
    }


def test_state_with_trust_content_is_ready_even_before_data_loaded():
    state = AnalysisSessionState(session_id="s1", data_state="unknown")
    state.dataset_contracts = [{"dataset": "sales"}]

    assert build_trust_view(state)["status"] == "ready"
