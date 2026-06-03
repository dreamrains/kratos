import pandas as pd

from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.intent import TurnIntent
from data_agent.agent.intent_refinement import refine_intent_with_data
from data_agent.agent.trust_contracts import (
    build_cleaning_decision_log,
    build_dataset_understanding_contract,
    build_preview_digest,
    build_route_proposals,
)
from data_agent.agent.verification import verify_analysis_claims
from data_agent.utils.data_features import scan_data_quality


def test_trustworthy_workflow_mvp_chain():
    df = pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=10),
        "gmv": [100, 120, 110, 130, 140, 125, 135, 150, 155, 160],
        "channel": ["a", "b"] * 5,
    })
    state = AnalysisSessionState(session_id="s1")

    cleaning = build_cleaning_decision_log("main", [], [])
    preview = build_preview_digest("main", df)
    quality = scan_data_quality(df)
    interpretation = {
        "grain": "daily_aggregate",
        "columns_classified": {
            "time_columns": ["date"],
            "key_metrics": [{"column": "gmv"}],
            "rate_metrics": [],
            "dimensions": [{"column": "channel"}],
            "id_columns": [],
            "other_text": [],
        },
        "time_range": {
            "column": "date",
            "min": "2026-01-01",
            "max": "2026-01-10",
            "span_days": 9,
        },
        "analysis_signals": {
            "has_time": True,
            "has_dimensions": True,
            "has_ids": False,
            "has_rates": False,
            "metric_count": 1,
        },
    }
    contract = build_dataset_understanding_contract(
        dataset="main",
        df=df,
        quality=quality,
        interpretation_data=interpretation,
        cleaning_log_ids=[cleaning["id"]],
        preview_digest_id=preview["id"],
        detail_path="tool_outputs/load_main_detail.json",
    )
    routes = build_route_proposals(contract)

    state.add_cleaning_log_ref({"id": cleaning["id"], "dataset": "main"})
    state.add_preview_digest_ref({"id": preview["id"], "dataset": "main"})
    state.add_dataset_contract_ref({
        "id": contract["id"],
        "dataset": "main",
        "quality_status": contract["quality"]["status"],
        "supported_analyses": contract["supported_analyses"],
    })
    for route in routes:
        state.add_route_proposal_ref({
            "id": route["id"],
            "dataset": "main",
            "direction": route["direction"],
            "budget_level": route["budget_level"],
        })

    intent = TurnIntent(
        intent_type="intent_negotiation",
        clarity="vague",
        data_state="data_loaded",
        analysis_stage="discover",
        recommended_action="guide_analysis",
        execution_readiness="ready",
        reason="test",
        ambiguities=[],
    )
    refined = refine_intent_with_data("help me look at this data", intent, [contract], routes)

    report = verify_analysis_claims(
        claims=["GMV increased over the period"],
        evidence_records=[{
            "id": "ev1",
            "claim": "GMV increased over the period",
            "method": "compare_periods",
            "dataset": "main",
            "sample_size": "10",
            "time_scope": "2026-01-01 to 2026-01-10",
            "calculation_method": "period comparison",
            "method_detail": "manual comparison",
            "limitations": ["Small sample"],
            "confidence": "medium",
        }],
        route_proposals=routes,
        cleaning_logs=[cleaning],
    )
    state.add_verification_report_ref({
        "id": report["id"],
        "overall_status": report["overall_status"],
    })

    assert contract["supported_analyses"]
    assert routes
    assert refined.recommended_action == "guide_analysis"
    assert any(item.get("field") == "analysis_route" for item in refined.ambiguities)
    assert report["overall_status"] in {"pass", "pass_with_downgrades"}
    assert state.cleaning_logs
    assert state.preview_digests
    assert state.dataset_contracts
    assert state.route_proposals
    assert state.verification_reports
