import json

import numpy as np
import pandas as pd

from data_agent.agent.trust_contracts import (
    build_cleaning_decision_log,
    build_dataset_understanding_contract,
    build_preview_digest,
    build_route_proposals,
    route_evidence_requirements,
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


def test_build_route_proposals_adds_evidence_requirements():
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
    assert "limitations" in first["evidence_requirements"]
    assert "expected_evidence" not in first
    assert first["budget_level"] in {"light", "standard", "deep"}
    json.dumps(proposals)


def test_route_evidence_requirements_reads_legacy_expected_evidence():
    legacy_route = {"expected_evidence": [" sample_size ", "limitations"]}

    assert route_evidence_requirements(legacy_route) == ["sample_size", "limitations"]


def test_builders_accept_pandas_and_numpy_containers_as_json_safe_values():
    df = pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=3),
        "gmv": np.array([10, 20, 30]),
    })
    cleaning = build_cleaning_decision_log(
        "main",
        [],
        [{
            "column": "gmv",
            "current_dtype": np.dtype("int64"),
            "suggested_type": "ambiguous_numeric",
            "reason": "manual sample review",
            "sample": pd.Series(np.array([10, 20, 30]), index=pd.Index(["a", "b", "c"])),
        }],
    )
    quality = {
        "quality_score": np.float64(91.5),
        "block_issues": [],
        "warnings": [{"columns": pd.Index(["gmv", "date"]), "codes": np.array(["missing", "skew"])}],
    }
    interpretation = {
        "grain": "daily_aggregate",
        "columns_classified": {
            "time_columns": pd.Index(["date"]),
            "key_metrics": [{"column": "gmv"}],
            "rate_metrics": [],
            "dimensions": [],
            "id_columns": [],
            "other_text": [],
        },
        "time_range": {"column": "date", "observed_days": np.array([1, 2, 3]), "tags": {"daily", "complete"}},
        "analysis_signals": {"has_time": True, "has_dimensions": False, "has_ids": False, "metric_count": 1},
    }

    contract = build_dataset_understanding_contract(
        "main",
        df,
        quality,
        interpretation,
        [cleaning["id"]],
        "preview_main_001",
    )

    json.dumps(cleaning)
    json.dumps(contract)
    assert cleaning["decisions"][0]["sample"] == [10, 20, 30]
    assert contract["quality"]["warnings"][0]["columns"] == ["gmv", "date"]


def test_set_order_does_not_change_stable_contract_id():
    df = pd.DataFrame({"date": pd.date_range("2026-01-01", periods=2), "gmv": [10, 20]})
    base_interpretation = {
        "grain": "daily_aggregate",
        "columns_classified": {
            "time_columns": ["date"],
            "key_metrics": [{"column": "gmv"}],
            "rate_metrics": [],
            "dimensions": [],
            "id_columns": [],
            "other_text": [],
        },
        "analysis_signals": {"has_time": True, "has_dimensions": False, "has_ids": False, "metric_count": 1},
    }
    first = build_dataset_understanding_contract(
        "main",
        df,
        {"quality_score": 90, "warnings": [{"codes": {"b", "a", "c"}}], "block_issues": []},
        {**base_interpretation, "time_range": {"tags": {"complete", "daily"}}},
        [],
        "preview_main_001",
    )
    second = build_dataset_understanding_contract(
        "main",
        df,
        {"quality_score": 90, "warnings": [{"codes": {"c", "b", "a"}}], "block_issues": []},
        {**base_interpretation, "time_range": {"tags": {"daily", "complete"}}},
        [],
        "preview_main_001",
    )

    assert first["id"] == second["id"]


def test_user_level_retention_unsupported_reason_distinguishes_id_and_grain_causes():
    aggregate_contract = {
        "grain": "daily_aggregate",
        "columns_classified": {
            "time_columns": ["date"],
            "key_metrics": [{"column": "gmv"}],
            "rate_metrics": [],
            "dimensions": [],
            "id_columns": [{"column": "user_id"}],
            "other_text": [],
        },
        "analysis_signals": {"has_time": True, "has_ids": True, "metric_count": 1},
    }
    no_id_contract = {
        **aggregate_contract,
        "grain": "event_level",
        "columns_classified": {**aggregate_contract["columns_classified"], "id_columns": []},
        "analysis_signals": {"has_time": True, "has_ids": False, "metric_count": 1},
    }
    df = pd.DataFrame({"date": pd.date_range("2026-01-01", periods=2), "gmv": [10, 20], "user_id": [1, 2]})

    aggregate = build_dataset_understanding_contract("main", df, {}, aggregate_contract, [], "preview")
    no_id = build_dataset_understanding_contract("main", df, {}, no_id_contract, [], "preview")

    aggregate_reason = next(item["reason"] for item in aggregate["unsupported_analyses"] if item["type"] == "user_level_retention")
    no_id_reason = next(item["reason"] for item in no_id["unsupported_analyses"] if item["type"] == "user_level_retention")
    assert "aggregate grain" in aggregate_reason
    assert "missing user or entity id" in no_id_reason
