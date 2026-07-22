import pandas as pd

from data_agent.agent.analysis_requirements import compile_analysis_requirements
from data_agent.agent.trust_contracts import build_dataset_understanding_contract


def _contract(df, *, date_columns=(), metric_columns=(), dimensions=(), grain="row_level"):
    return build_dataset_understanding_contract(
        "scenario",
        df,
        {"quality_score": 100, "block_issues": [], "warnings": []},
        {
            "grain": grain,
            "columns_classified": {
                "time_columns": list(date_columns),
                "key_metrics": [{"column": name} for name in metric_columns],
                "rate_metrics": [],
                "dimensions": [{"column": name} for name in dimensions],
                "id_columns": [],
                "other_text": [],
            },
            "analysis_signals": {
                "has_time": bool(date_columns),
                "has_dimensions": bool(dimensions),
                "has_ids": False,
                "metric_count": len(metric_columns),
            },
        },
        [],
        "preview_scenario",
    )


def test_many_rows_do_not_erase_imbalanced_segment_sample_structure():
    frame = pd.DataFrame({
        "segment": ["large"] * 10_000 + ["small_a"] * 4 + ["small_b"] * 2,
        "conversion": [0] * 10_006,
    })

    profile = _contract(
        frame,
        metric_columns=("conversion",),
        dimensions=("segment",),
    )["analysis_profiles"]["comparison"]

    assert profile["row_count"] == 10_006
    assert profile["group_sizes"]["segment"] == {
        "group_count": 3,
        "minimum": 2,
        "maximum": 10_000,
        "median": 4.0,
    }


def test_gapped_monthly_business_series_cannot_silently_support_annual_seasonality():
    dates = pd.date_range("2024-01-01", periods=28, freq="MS").delete([3, 8, 17])
    contract = _contract(
        pd.DataFrame({"month": dates, "revenue": range(len(dates))}),
        date_columns=("month",),
        metric_columns=("revenue",),
        grain="monthly_aggregate",
    )
    plan = {
        "id": "seasonality_scenario",
        "goal": "assess annual seasonality",
        "method_plan": [{
            "step_id": "step_seasonality",
            "goal": "assess annual seasonality",
            "required_capability": "analysis.time_series",
            "claim_type": "seasonality",
            "seasonality_period": "annual",
            "evidence_requirements": [],
        }],
    }

    requirements = compile_analysis_requirements(
        plan=plan,
        route={"direction": "trend"},
        playbook=None,
        dataset_contracts=[contract],
        user_intent=plan["goal"],
    )
    by_name = {item["name"]: item for item in requirements}

    assert contract["analysis_profiles"]["time_series"]["missing_interval_count"] == 3
    assert by_name["seasonality_estimability"]["status"] == "pending"
    assert by_name["seasonality_estimability"]["assessment_status"] == "not_estimable"
    assert by_name["seasonality_estimability"]["unmet_action"] == "block_claim"
