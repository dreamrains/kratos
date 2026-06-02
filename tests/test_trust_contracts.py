import json

import pandas as pd

from data_agent.agent.trust_contracts import (
    build_cleaning_decision_log,
    build_dataset_understanding_contract,
    build_preview_digest,
    build_route_proposals,
)


def test_build_cleaning_decision_log_classifies_decision_levels():
    applied = [
        {"column": "date", "from": "object", "to": "datetime64[ns]", "action": "datetime", "reason": "date"},
        {"column": "amount", "from": "object", "to": "float64", "action": "numeric", "reason": "numeric"},
    ]
    needs_confirm = [
        {
            "column": "channel_code",
            "current_dtype": "int64",
            "suggested_type": "category_maybe",
            "reason": "low cardinality",
        },
        {"column": "raw_payload", "current_dtype": "object", "reason": "unparseable nested records", "blocked": True},
    ]

    log = build_cleaning_decision_log("main", applied, needs_confirm)

    assert log["dataset"] == "main"
    assert log["summary"]["safe_auto"] == 1
    assert log["summary"]["notify_auto"] == 1
    assert log["summary"]["needs_confirmation"] == 1
    assert log["summary"]["blocked"] == 1
    assert log["decisions"][0]["impact"] == "Enables time-aware analysis"
    json.dumps(log)


def test_build_preview_digest_limits_examples_and_records_risks():
    df = pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=8),
        "channel": ["a", "b"] * 4,
        "gmv": [1, 2, None, 4, 5, 6, 7, 8],
    })

    digest = build_preview_digest("main", df, max_rows=3)

    assert digest["dataset"] == "main"
    assert digest["sample_rows_count"] == 3
    assert len(digest["sample_rows"]) == 3
    assert "date" in digest["column_examples"]
    assert any("missing" in risk.lower() for risk in digest["risks"])
    json.dumps(digest)


def test_build_dataset_understanding_contract_maps_supported_and_unsupported_analyses():
    df = pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=20),
        "gmv": range(20),
        "channel": ["a", "b"] * 10,
    })
    quality = {
        "quality_score": 95,
        "block_issues": [],
        "warnings": [],
        "columns": {
            "date": {"type": "date", "missing_rate": 0},
            "gmv": {"type": "numeric", "missing_rate": 0},
            "channel": {"type": "categorical", "missing_rate": 0},
        },
    }
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
        "time_range": {"column": "date", "min": "2026-01-01", "max": "2026-01-20", "span_days": 19},
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
        cleaning_log_ids=["clean_main_001"],
        preview_digest_id="preview_main_001",
        detail_path="tool_outputs/load_main_detail.json",
    )

    assert contract["field_roles"]["date"] == ["date"]
    assert contract["field_roles"]["metrics"] == ["gmv"]
    assert contract["field_roles"]["dimensions"] == ["channel"]
    assert "trend" in contract["supported_analyses"]
    assert "period_compare" in contract["supported_analyses"]
    assert "dimension_decomposition" in contract["supported_analyses"]
    assert any(item["type"] == "user_level_retention" for item in contract["unsupported_analyses"])
    json.dumps(contract)


def test_build_route_proposals_adds_expected_evidence():
    contract = {
        "id": "duc_main_001",
        "dataset": "main",
        "field_roles": {
            "date": ["date"],
            "metrics": ["gmv"],
            "rate_metrics": [],
            "dimensions": ["channel"],
            "ids": [],
            "text": [],
            "unknown": [],
        },
        "supported_analyses": ["trend", "period_compare", "dimension_decomposition"],
        "quality": {"status": "ready"},
    }

    proposals = build_route_proposals(contract)

    assert {proposal["direction"] for proposal in proposals} >= {
        "trend",
        "period_compare",
        "dimension_decomposition",
    }
    first = proposals[0]
    assert first["dataset_contract_id"] == "duc_main_001"
    assert "record_evidence_record" in first["tool_chain"]
    assert "limitations" in first["expected_evidence"]
    assert first["budget_level"] in {"light", "standard", "deep"}
    json.dumps(proposals)
