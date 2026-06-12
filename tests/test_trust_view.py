from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.trust_view import build_trust_view


def _clear_confirmation_gate():
    return {
        "status": "clear",
        "confirmation_type": "",
        "question": "",
        "blocking_reason": "",
        "risk_fields": [],
        "affected_routes": [],
        "blocked_surfaces": [],
    }


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
        "active_scope": {
            "active_dataset": "",
            "active_route": "",
            "active_goal": "",
            "active_mode": "consulting",
        },
        "scope_counts": {
            "datasets": 0,
            "routes": 0,
            "risks": 0,
            "hypothesis_sets": 0,
            "artifacts": 0,
        },
        "recommendations": {
            "active_dataset": "",
            "active_route": "",
            "active_mode": "consulting",
            "executable": [],
            "exploratory": [],
            "counts": {"executable": 0, "exploratory": 0},
            "confirmation_gate": _clear_confirmation_gate(),
        },
        "active_bundle": None,
        "file_relationships": [],
        "history": {"datasets": [], "routes": [], "risks": [], "hypotheses": []},
    }


def test_trust_view_exposes_active_bundle_and_recent_relationships_without_mutating_state():
    state = AnalysisSessionState(session_id="bundle_session", data_state="data_loaded")
    state.data_pool = [
        {
            "file_id": "file_orders_old",
            "filename": "orders_old.csv",
            "dataset": "orders_old",
            "row_count": 120,
            "column_count": 6,
            "columns": ["a", "b", "c", "d", "e", "f", "large_column_list_should_not_leak"],
            "status": "available",
        },
        {
            "file_id": "file_orders_new",
            "filename": "orders_new.csv",
            "dataset": "orders_new",
            "rows": 98,
            "columns": ["order_id", "revenue"],
            "status": "available",
        },
        {
            "file_id": "file_region",
            "filename": "region.csv",
            "dataset": "regions",
            "row_count": 12,
            "column_count": 3,
            "status": "excluded",
        },
        {
            "file_id": "file_hidden_1",
            "filename": "hidden1.csv",
            "dataset": "hidden1",
            "row_count": 1,
            "column_count": 1,
        },
        {
            "file_id": "file_hidden_2",
            "filename": "hidden2.csv",
            "dataset": "hidden2",
            "row_count": 1,
            "column_count": 1,
        },
        {
            "file_id": "file_hidden_3",
            "filename": "hidden3.csv",
            "dataset": "hidden3",
            "row_count": 1,
            "column_count": 1,
        },
    ]
    state.dataset_bundles = [
        {
            "bundle_id": "bundle_orders",
            "label": "Orders scope",
            "file_ids": [
                "file_orders_old",
                "file_orders_new",
                "file_region",
                "file_hidden_1",
                "file_hidden_2",
                "file_hidden_3",
            ],
            "dataset_names": ["orders_old", "orders_new", "regions"],
            "relationship_status": "confirmed",
            "relationship_mode": "include_in_active_bundle",
        }
    ]
    state.active_bundle_id = "bundle_orders"
    state.file_relationships = [
        {
            "relationship_id": "rel_old",
            "file_ids": ["old"],
            "status": "linked",
            "evidence": ["older evidence"],
        },
        {
            "relationship_id": "rel_pending",
            "status": "possibly_linked",
            "requires_confirmation": True,
            "relationship_mode": "include_in_active_bundle",
            "confirmation_type": "scope_confirmation",
            "file_ids": ["file_orders_old", "file_orders_new", "file_region", "file_hidden_1"],
            "evidence": ["same order_id", "overlapping dates", "third evidence should not leak"],
            "uncertainties": ["different row counts", "missing region keys", "third uncertainty should not leak"],
        },
    ]
    before = state.to_dict()

    view = build_trust_view(state)

    assert state.to_dict() == before
    assert view["active_bundle"] == {
        "bundle_id": "bundle_orders",
        "label": "Orders scope",
        "file_count": 6,
        "dataset_names": ["orders_old", "orders_new", "regions"],
        "relationship_status": "confirmed",
        "relationship_mode": "include_in_active_bundle",
        "files": [
            {
                "file_id": "file_orders_old",
                "filename": "orders_old.csv",
                "dataset": "orders_old",
                "rows": 120,
                "columns": 6,
                "status": "available",
            },
            {
                "file_id": "file_orders_new",
                "filename": "orders_new.csv",
                "dataset": "orders_new",
                "rows": 98,
                "columns": 2,
                "status": "available",
            },
            {
                "file_id": "file_region",
                "filename": "region.csv",
                "dataset": "regions",
                "rows": 12,
                "columns": 3,
                "status": "excluded",
            },
            {
                "file_id": "file_hidden_1",
                "filename": "hidden1.csv",
                "dataset": "hidden1",
                "rows": 1,
                "columns": 1,
                "status": "",
            },
            {
                "file_id": "file_hidden_2",
                "filename": "hidden2.csv",
                "dataset": "hidden2",
                "rows": 1,
                "columns": 1,
                "status": "",
            },
        ],
        "remaining_file_count": 1,
    }
    assert view["file_relationships"] == [
        {
            "relationship_id": "rel_pending",
            "status": "possibly_linked",
            "requires_confirmation": True,
            "relationship_mode": "include_in_active_bundle",
            "confirmation_type": "scope_confirmation",
            "file_count": 4,
            "file_ids": ["file_orders_old", "file_orders_new", "file_region"],
            "evidence": ["same order_id", "overlapping dates"],
            "uncertainties": ["different row counts", "missing region keys"],
        },
        {
            "relationship_id": "rel_old",
            "status": "linked",
            "requires_confirmation": False,
            "relationship_mode": "",
            "confirmation_type": "",
            "file_count": 1,
            "file_ids": ["old"],
            "evidence": ["older evidence"],
            "uncertainties": [],
        },
    ]


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
    state.active_scope["active_dataset"] = "game_b_retention"
    state.active_scope["active_mode"] = "data_loaded"
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
    state.active_scope["active_mode"] = "data_loaded"
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
    state.active_scope["active_mode"] = "data_loaded"
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
    state.active_scope["active_dataset"] = "sales"
    state.active_scope["active_mode"] = "data_loaded"
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


def test_trust_view_exposes_active_scope_counts_and_recommendations():
    state = AnalysisSessionState(session_id="s1", data_state="data_loaded")
    state.active_scope["active_dataset"] = "orders"
    state.active_scope["active_mode"] = "data_loaded"
    state.dataset_contracts = [
        {"dataset": "old_sales", "row_count": 10, "supported_analyses": ["trend"]},
        {
            "dataset": "orders",
            "row_count": 20,
            "supported_analyses": ["cohort"],
            "unsupported_analyses": [{"type": "user_level_retention", "reason": "missing events"}],
        },
    ]
    state.route_proposals = [
        {"id": "old", "dataset": "old_sales", "direction": "trend"},
        {"id": "new", "dataset": "orders", "direction": "cohort", "label": "Cohort"},
    ]

    view = build_trust_view(state)

    assert view["active_scope"]["active_dataset"] == "orders"
    assert view["scope_counts"]["datasets"] == 2
    assert view["scope_counts"]["routes"] == 2
    assert [dataset["dataset"] for dataset in view["datasets"]] == ["orders"]
    assert [route["direction"] for route in view["routes"]] == ["cohort"]
    assert [route["route"] for route in view["recommendations"]["executable"]] == ["cohort"]
    assert view["recommendations"]["exploratory"][0]["analysis"] == "user_level_retention"


def test_trust_view_consulting_mode_hides_current_routes_but_keeps_history():
    state = AnalysisSessionState(session_id="s1")
    state.active_scope["active_mode"] = "consulting"
    state.route_proposals = [{"id": "route_old", "dataset": "sales", "direction": "trend"}]
    state.last_recommended_paths = [{"id": "metric_overview", "title": "Metric overview"}]

    view = build_trust_view(state)

    assert view["active_scope"]["active_mode"] == "consulting"
    assert view["routes"] == []
    assert view["history"]["routes"][0]["direction"] == "trend"
    assert view["recommendations"]["exploratory"][0]["category"] == "method_discussion"


def test_chat_three_panel_two_pattern_is_classified_not_conflicting():
    state = AnalysisSessionState(session_id="s1", data_state="data_loaded")
    state.active_scope["active_dataset"] = "card_orders"
    state.active_scope["active_mode"] = "data_loaded"
    state.dataset_contracts = [
        {
            "dataset": "card_orders",
            "supported_analyses": ["cohort", "funnel"],
            "unsupported_analyses": [
                {"type": "user_level_retention", "reason": "缺少用户级事件历史"}
            ],
        }
    ]
    state.route_proposals = [
        {"id": "route_cohort", "dataset": "card_orders", "direction": "cohort"},
        {"id": "route_funnel", "dataset": "card_orders", "direction": "funnel"},
    ]

    view = build_trust_view(state)

    assert len(view["recommendations"]["executable"]) == 2
    assert len(view["routes"]) == 2
    assert view["recommendations"]["exploratory"][0]["analysis"] == "user_level_retention"
    assert view["recommendations"]["exploratory"][0]["category"] == "needs_more_data"


def test_trust_view_hides_current_routes_when_confirmation_is_pending():
    state = AnalysisSessionState(session_id="s1", data_state="data_loaded")
    state.active_scope["active_dataset"] = "orders"
    state.active_scope["active_mode"] = "data_loaded"
    state.route_proposals = [
        {"id": "route_trend", "dataset": "orders", "direction": "trend"},
        {"id": "route_compare", "dataset": "orders", "direction": "period_compare"},
    ]
    state.pending_confirmations = [
        {
            "id": "scope_gate",
            "status": "pending",
            "confirmation_type": "scope_confirmation",
            "question": "请先确认你更关注趋势还是对比？",
        }
    ]

    view = build_trust_view(state)

    assert view["routes"] == []
    assert view["recommendations"]["executable"] == []
    assert view["recommendations"]["confirmation_gate"]["status"] == "needs_confirmation"
    assert len(view["history"]["routes"]) == 2


def test_trust_view_history_routes_and_counts_are_not_display_limited():
    state = AnalysisSessionState(session_id="s1", data_state="data_loaded")
    state.active_scope["active_mode"] = "data_loaded"
    state.route_proposals = [
        {"id": f"route_{index}", "dataset": "sales", "direction": f"route_{index}"}
        for index in range(6)
    ]

    view = build_trust_view(state)

    assert view["scope_counts"]["routes"] == 6
    assert [route["direction"] for route in view["history"]["routes"]] == [
        "route_0",
        "route_1",
        "route_2",
        "route_3",
        "route_4",
        "route_5",
    ]
    assert len(view["routes"]) == 4


def test_trust_view_filters_hypotheses_by_active_route_when_set():
    state = AnalysisSessionState(session_id="s1", data_state="data_loaded")
    state.active_scope["active_dataset"] = "sales"
    state.active_scope["active_route"] = "trend"
    state.active_scope["active_mode"] = "analysis"
    state.hypothesis_sets = [
        {
            "id": "match",
            "dataset": "sales",
            "route": "trend",
            "hypotheses": [{"claim": "matching route", "status": "supported"}],
        },
        {
            "id": "other-route",
            "dataset": "sales",
            "route": "funnel",
            "hypotheses": [{"claim": "wrong route", "status": "supported"}],
        },
        {
            "id": "blank-route",
            "dataset": "sales",
            "hypotheses": [{"claim": "blank route", "status": "supported"}],
        },
    ]

    view = build_trust_view(state)

    assert [item["id"] for item in view["hypotheses"]] == ["match"]


def test_trust_view_filters_hypotheses_before_current_display_limit():
    state = AnalysisSessionState(session_id="s1", data_state="data_loaded")
    state.active_scope["active_dataset"] = "active"
    state.active_scope["active_route"] = "trend"
    state.active_scope["active_mode"] = "analysis"
    state.hypothesis_sets = [
        {
            "id": f"old_{index}",
            "dataset": "old",
            "route": "trend",
            "hypotheses": [{"claim": f"old {index}", "status": "supported"}],
        }
        for index in range(4)
    ] + [
        {
            "id": "active_match",
            "dataset": "active",
            "route": "trend",
            "hypotheses": [{"claim": "active match", "status": "supported"}],
        }
    ]

    view = build_trust_view(state)

    assert view["scope_counts"]["hypothesis_sets"] == 5
    assert [item["id"] for item in view["hypotheses"]] == ["active_match"]
    assert [item["id"] for item in view["history"]["hypotheses"]] == [
        "old_0",
        "old_1",
        "old_2",
        "old_3",
        "active_match",
    ]


def test_trust_view_limits_current_hypotheses_after_active_filtering():
    state = AnalysisSessionState(session_id="s1", data_state="data_loaded")
    state.active_scope["active_dataset"] = "sales"
    state.active_scope["active_route"] = "trend"
    state.active_scope["active_mode"] = "analysis"
    state.hypothesis_sets = [
        {
            "id": f"active_{index}",
            "dataset": "sales",
            "route": "trend",
            "hypotheses": [{"claim": f"active {index}", "status": "supported"}],
        }
        for index in range(5)
    ]

    view = build_trust_view(state)

    assert [item["id"] for item in view["hypotheses"]] == [
        "active_0",
        "active_1",
        "active_2",
    ]
    assert view["scope_counts"]["hypothesis_sets"] == 5
    assert len(view["history"]["hypotheses"]) == 5


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
        "active_scope": {
            "active_dataset": "",
            "active_route": "",
            "active_goal": "",
            "active_mode": "consulting",
        },
        "scope_counts": {
            "datasets": 0,
            "routes": 0,
            "risks": 0,
            "hypothesis_sets": 0,
            "artifacts": 0,
        },
        "recommendations": {
            "active_dataset": "",
            "active_route": "",
            "active_mode": "consulting",
            "executable": [],
            "exploratory": [],
            "counts": {"executable": 0, "exploratory": 0},
            "confirmation_gate": _clear_confirmation_gate(),
        },
        "active_bundle": None,
        "file_relationships": [],
        "history": {"datasets": [], "routes": [], "risks": [], "hypotheses": []},
    }


def test_state_with_trust_content_is_ready_even_before_data_loaded():
    state = AnalysisSessionState(session_id="s1", data_state="unknown")
    state.dataset_contracts = [{"dataset": "sales"}]

    assert build_trust_view(state)["status"] == "ready"
