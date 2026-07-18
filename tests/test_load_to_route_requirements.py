import pandas as pd

import data_agent.agent.analysis_requirements as requirement_module
from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.route_capabilities import build_route_capabilities
from data_agent.agent.trust_contracts import (
    build_dataset_understanding_contract,
    build_route_proposals,
)


def test_real_route_proposal_preserves_requirements_in_runtime_capabilities():
    frame = pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=8),
        "revenue": [10, 12, 9, 14, 15, 16, 13, 18],
    })
    contract = build_dataset_understanding_contract(
        dataset="orders",
        df=frame,
        quality={"quality_score": 100, "block_issues": [], "warnings": []},
        interpretation_data={
            "grain": "daily_aggregate",
            "columns_classified": {
                "time_columns": ["date"],
                "key_metrics": [{"column": "revenue"}],
                "rate_metrics": [],
                "dimensions": [],
                "id_columns": [],
                "other_text": [],
            },
            "analysis_signals": {
                "has_time": True,
                "has_dimensions": False,
                "has_ids": False,
                "has_rates": False,
                "metric_count": 1,
            },
        },
        cleaning_log_ids=[],
        preview_digest_id="preview_orders",
        detail_path="",
    )
    routes = build_route_proposals(contract)
    trend = next(route for route in routes if route["direction"] == "trend")
    state = AnalysisSessionState(session_id="route-contract", data_state="data_loaded")
    state.set_active_dataset("orders", related_ref_id=contract["id"])
    state.dataset_contracts = [contract]
    state.route_proposals = [trend]

    runtime = build_route_capabilities(state)
    item = next(route for route in runtime["executable"] if route["direction"] == "trend")

    assert trend["evidence_requirements"] == [
        "time_scope",
        "sample_size",
        "trend_statistics",
        "limitations",
    ]
    assert "expected_evidence" not in trend
    assert item["evidence_requirements"] == trend["evidence_requirements"]


def test_route_proposals_project_requirements_from_the_canonical_owner(monkeypatch):
    monkeypatch.setitem(
        requirement_module._ROUTE_REQUIREMENT_INPUTS,
        "trend",
        ("time_scope", "limitations"),
    )
    contract = {
        "id": "duc_orders",
        "dataset": "orders",
        "field_roles": {},
        "supported_analyses": ["trend"],
    }

    route = build_route_proposals(contract)[0]

    assert route["evidence_requirements"] == ["time_scope", "limitations"]
