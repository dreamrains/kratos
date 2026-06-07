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
        "hypotheses": [],
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


def test_thin_artifact_refs_are_hydrated_for_inspector_details(tmp_path):
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(
        """
{
  "dataset": "game_b_retention",
  "row_count": 62,
  "column_count": 13,
  "quality": {"status": "ready", "score": 100},
  "field_roles": {
    "date": ["date"],
    "metrics": ["daily_active", "day_1_retention"],
    "dimensions": [],
    "ids": []
  },
  "supported_analyses": ["trend", "period_compare"],
  "unsupported_analyses": [
    {"type": "user_level_retention", "reason": "aggregate grain and missing user IDs"}
  ]
}
""",
        encoding="utf-8",
    )
    preview_path = tmp_path / "preview.json"
    preview_path.write_text(
        """
{
  "dataset": "game_b_retention",
  "notable_patterns": ["date is daily", "retention columns detected"]
}
""",
        encoding="utf-8",
    )
    route_path = tmp_path / "route.json"
    route_path.write_text(
        """
{
  "id": "route_trend",
  "dataset": "game_b_retention",
  "direction": "trend",
  "budget_level": "low",
  "limitations": ["Descriptive trend only unless supported by experimental evidence"]
}
""",
        encoding="utf-8",
    )
    cleaning_path = tmp_path / "cleaning.json"
    cleaning_path.write_text(
        """
{
  "dataset": "game_b_retention",
  "decisions": [
    {
      "column": "date",
      "decision_type": "needs_confirmation",
      "impact": "Date parsing changed the original column type"
    }
  ]
}
""",
        encoding="utf-8",
    )
    state = AnalysisSessionState(session_id="s1", data_state="data_loaded")
    state.dataset_contracts = [
        {
            "dataset": "game_b_retention",
            "artifact_path": str(contract_path),
            "quality_status": "ready",
            "supported_analyses": ["trend", "period_compare"],
        }
    ]
    state.preview_digests = [{"dataset": "game_b_retention", "artifact_path": str(preview_path)}]
    state.route_proposals = [
        {"id": "route_trend", "dataset": "game_b_retention", "artifact_path": str(route_path)}
    ]
    state.cleaning_logs = [{"dataset": "game_b_retention", "artifact_path": str(cleaning_path)}]

    view = build_trust_view(state)

    assert view["datasets"] == [
        {
            "dataset": "game_b_retention",
            "rows": 62,
            "columns": 13,
            "quality_status": "ready",
            "quality_score": 100,
            "key_fields": ["date", "daily_active", "day_1_retention"],
            "supported_analyses": ["trend", "period_compare"],
            "preview_notes": ["date is daily", "retention columns detected"],
        }
    ]
    assert view["routes"][0]["limitations"] == [
        "Descriptive trend only unless supported by experimental evidence"
    ]
    assert {
        "severity": "warning",
        "source": "unsupported_analysis",
        "dataset": "game_b_retention",
        "field": "user_level_retention",
        "message": "aggregate grain and missing user IDs",
    } in view["risks"]
    assert {
        "severity": "warning",
        "source": "cleaning",
        "dataset": "game_b_retention",
        "field": "date",
        "message": "Date parsing changed the original column type",
    } in view["risks"]


def test_route_cards_are_limited_skip_malformed_and_include_editable_prompt():
    state = AnalysisSessionState(session_id="s1", data_state="data_loaded")
    state.route_proposals = [
        {
            "id": "route-trend",
            "dataset": "sales",
            "direction": "trend",
            "label": "Trend",
            "reason": "Time column exists",
            "budget_level": "low",
        },
        {"label": "Missing direction"},
        "not a dict",
        {"dataset": "orders", "direction": "segment", "label": "Segment", "limitations": ["few dimensions"]},
        {"direction": "compare", "label": "Compare"},
        {"direction": "forecast", "label": "Forecast"},
        {"direction": "extra", "label": "Extra"},
    ]

    routes = build_trust_view(state)["routes"]

    assert len(routes) == 4
    assert [route["direction"] for route in routes] == ["trend", "segment", "compare", "forecast"]
    assert [route["id"] for route in routes] == ["route-trend", "route_2", "route_3", "route_4"]
    assert [route["dataset"] for route in routes] == ["sales", "orders", "", ""]
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
                    {"columns": ["revenue", "cost"], "codes": ["missing_values"]},
                ],
            },
            "unsupported_analyses": [
                {"type": "user_level_retention", "reason": "missing user id"},
                "forecasting",
            ],
        }
    ]
    state.cleaning_logs = [
        {
            "dataset": "orders",
            "decisions": [
                {
                    "column": "revenue",
                    "decision_type": "needs_confirmation",
                    "impact": "May change aggregate values",
                },
                {
                    "column": "date",
                    "decision_type": "blocked",
                    "impact": "Blocks dependent analysis",
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
            "source": "data_quality",
            "dataset": "sales",
            "field": "revenue, cost",
            "message": "missing_values",
        },
        {
            "severity": "warning",
            "source": "unsupported_analysis",
            "dataset": "sales",
            "field": "user_level_retention",
            "message": "missing user id",
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
            "dataset": "orders",
            "field": "revenue",
            "message": "May change aggregate values",
        },
        {
            "severity": "blocked",
            "source": "cleaning",
            "dataset": "orders",
            "field": "date",
            "message": "Blocks dependent analysis",
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


def test_trust_view_includes_compact_hypothesis_summary(tmp_path):
    hypothesis_path = tmp_path / "hypotheses.json"
    hypothesis_path.write_text(
        """
{
  "id": "hyps_sales_trend",
  "dataset": "sales",
  "route": "trend",
  "status_summary": {"supported": 1, "inconclusive": 1},
  "hypotheses": [
    {"id": "h1", "claim": "Revenue changed because orders changed.", "status": "supported"},
    {"id": "h2", "claim": "Revenue changed because channel mix changed.", "status": "inconclusive"},
    {"id": "h3", "claim": "Revenue movement is random fluctuation.", "status": "inconclusive"}
  ]
}
""",
        encoding="utf-8",
    )
    state = AnalysisSessionState(session_id="s1", data_state="data_loaded")
    state.hypothesis_sets = [
        {
            "id": "hyps_sales_trend",
            "dataset": "sales",
            "route": "trend",
            "count": 3,
            "artifact_path": str(hypothesis_path),
        }
    ]

    view = build_trust_view(state)

    assert view["hypotheses"] == [
        {
            "id": "hyps_sales_trend",
            "dataset": "sales",
            "route": "trend",
            "count": 3,
            "status_summary": {"supported": 1, "inconclusive": 1},
            "top_claims": [
                {"claim": "Revenue changed because orders changed.", "status": "supported"},
                {
                    "claim": "Revenue changed because channel mix changed.",
                    "status": "inconclusive",
                },
            ],
        }
    ]


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
        "hypotheses": [],
    }


def test_state_with_trust_content_is_ready_even_before_data_loaded():
    state = AnalysisSessionState(session_id="s1", data_state="unknown")
    state.dataset_contracts = [{"dataset": "sales"}]

    assert build_trust_view(state)["status"] == "ready"
