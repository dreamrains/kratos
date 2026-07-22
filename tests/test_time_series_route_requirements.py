import json

import pandas as pd

from data_agent.agent.analysis_requirements import (
    compile_analysis_requirements,
    evaluate_requirement_satisfaction,
)
from data_agent.agent.analysis_entry import decide_analysis_entry
from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.intent import TurnIntent
from data_agent.agent.question_need_detector import detect_question_need
from data_agent.agent.trust_contracts import build_dataset_understanding_contract
from data_agent.agent.context import AgentContext, use_agent_context
from data_agent.session.workspace import Workspace
from data_agent.tools.analysis_flow import _calibrate_confidence


def _contract(dates):
    df = pd.DataFrame({"month": pd.to_datetime(dates), "revenue": range(len(dates))})
    return build_dataset_understanding_contract(
        "orders",
        df,
        {"quality_score": 100, "block_issues": [], "warnings": []},
        {
            "grain": "monthly_aggregate",
            "columns_classified": {
                "time_columns": ["month"],
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
                "metric_count": 1,
            },
        },
        [],
        "preview_orders",
    )


def _time_series_plan(**step_overrides):
    step = {
        "step_id": "step_trend",
        "goal": "analyze the time series",
        "node_type": "analysis",
        "required_capability": "analysis.time_series",
        "evidence_requirements": [],
    }
    step.update(step_overrides)
    return {
        "id": "plan_trend",
        "goal": "analyze revenue over time",
        "method_plan": [step],
    }


def _compile(plan, contract):
    return compile_analysis_requirements(
        plan=plan,
        route={"direction": "trend"},
        playbook=None,
        dataset_contracts=[contract],
        user_intent=plan["goal"],
    )


def test_eight_monthly_points_mark_annual_seasonality_not_estimable():
    contract = _contract(pd.date_range("2025-01-01", periods=8, freq="MS"))
    profile = contract["analysis_profiles"]["time_series"]

    assert profile["frequency"] == "monthly"
    assert profile["missing_interval_count"] == 0
    assert profile["seasonality"]["annual"] == {
        "period_observations": 12,
        "minimum_complete_cycles": 2,
        "complete_cycles": 0,
        "status": "not_estimable",
        "reason": "Annual seasonality requires at least 2 complete cycles (24 monthly observations).",
    }


def test_seasonality_claim_compiles_explicit_cycle_guard_from_dataset_profile():
    contract = _contract(pd.date_range("2025-01-01", periods=8, freq="MS"))
    requirements = _compile(
        _time_series_plan(claim_type="seasonality", seasonality_period="annual"),
        contract,
    )
    seasonality = next(item for item in requirements if item["name"] == "seasonality_estimability")

    assert seasonality["status"] == "pending"
    assert seasonality["unmet_action"] == "block_claim"
    assert seasonality["assessment_status"] == "not_estimable"
    assert seasonality["claim_guard"] == "block_claim"
    assert seasonality["parameters"] == {
        "seasonality_period": "annual",
        "frequency": "monthly",
        "period_observations": 12,
        "minimum_complete_cycles": 2,
        "complete_cycles": 0,
        "estimability": "not_estimable",
    }
    assert "24 monthly observations" in seasonality["reason"]


def test_marginal_seasonal_history_is_estimable_only_with_limits():
    contract = _contract(pd.date_range("2024-01-01", periods=24, freq="MS"))

    annual = contract["analysis_profiles"]["time_series"]["seasonality"]["annual"]

    assert annual["complete_cycles"] == 2
    assert annual["status"] == "estimable_with_limits"


def test_month_end_series_is_recognized_as_monthly():
    contract = _contract(pd.date_range("2024-01-31", periods=8, freq="ME"))

    assert contract["analysis_profiles"]["time_series"]["frequency"] == "monthly"


def test_same_day_of_month_series_is_recognized_as_monthly():
    dates = pd.date_range("2024-01-01", periods=8, freq="MS") + pd.Timedelta(days=14)
    contract = _contract(dates)

    assert contract["analysis_profiles"]["time_series"]["frequency"] == "monthly"


def test_irregular_or_gapped_time_marks_window_comparability_unmet():
    dates = pd.to_datetime([
        "2026-01-01",
        "2026-01-02",
        "2026-01-04",
        "2026-01-05",
        "2026-01-09",
    ])
    contract = _contract(dates)
    requirements = _compile(
        _time_series_plan(required_capability="analysis.period_compare"),
        contract,
    )
    by_name = {item["name"]: item for item in requirements}

    assert contract["analysis_profiles"]["time_series"]["frequency"] == "irregular"
    assert contract["analysis_profiles"]["time_series"]["missing_interval_count"] > 0
    assert by_name["window_comparability"]["status"] == "pending"
    assert by_name["window_comparability"]["unmet_action"] == "block_claim"
    assert by_name["window_comparability"]["assessment_status"] == "requires_adjustment"
    assert by_name["window_comparability"]["claim_guard"] == "ordinary_window_assumptions_unsupported"
    assert "irregular" in by_name["window_comparability"]["reason"].lower()


def test_step_selected_time_column_uses_its_own_profile():
    regular = pd.date_range("2026-01-01", periods=5, freq="D")
    irregular = pd.to_datetime([
        "2026-01-01", "2026-01-02", "2026-01-05", "2026-01-09", "2026-01-10",
    ])
    frame = pd.DataFrame({
        "created_at": regular,
        "event_at": irregular,
        "revenue": range(5),
    })
    contract = build_dataset_understanding_contract(
        "orders",
        frame,
        {"quality_score": 100, "block_issues": [], "warnings": []},
        {
            "grain": "daily_aggregate",
            "columns_classified": {
                "time_columns": ["created_at", "event_at"],
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
                "metric_count": 1,
            },
        },
        [],
        "preview_orders",
    )
    requirements = _compile(
        _time_series_plan(date_column="event_at"),
        contract,
    )
    window = next(item for item in requirements if item["name"] == "window_comparability")

    assert contract["analysis_profiles"]["time_series"]["frequency"] == "daily"
    assert contract["analysis_profiles"]["time_series_by_column"]["event_at"]["frequency"] == "irregular"
    assert window["assessment_status"] == "requires_adjustment"


def test_time_series_compiles_frequency_gaps_comparability_and_dependence_requirements():
    requirements = _compile(
        _time_series_plan(),
        _contract(pd.date_range("2024-01-01", periods=30, freq="MS")),
    )
    names = {item["name"] for item in requirements}

    assert {
        "time_frequency",
        "missing_intervals",
        "window_comparability",
        "autocorrelation_awareness",
        "effective_sample_size",
        "missingness",
        "calculation_method",
        "assumptions",
    } <= names


def test_inferential_time_series_requires_interval_and_serial_design_adequacy():
    requirements = _compile(
        _time_series_plan(claim_type="inferential"),
        _contract(pd.date_range("2024-01-01", periods=30, freq="D")),
    )
    by_name = {item["name"]: item for item in requirements}

    assert by_name["confidence_interval"]["trigger"] == "inferential time-series claim"
    assert by_name["sample_adequacy"]["parameters"] == {
        "sampling_structure": "serially_dependent_time_series",
    }
    warnings = _calibrate_confidence({
        "confidence": "high",
        "claim_type": "inferential",
        "method": "analysis.time_series",
        "sample_size": 30,
        "limitations": ["serial dependence requires a robust method"],
    })
    assert any("样本充分性" in item for item in warnings)
    assert any("置信区间" in item for item in warnings)


def test_daily_series_gets_explicit_monthly_cycle_requirement():
    contract = _contract(pd.date_range("2025-01-01", periods=60, freq="D"))
    requirements = _compile(
        _time_series_plan(claim_type="seasonality", seasonality_period="monthly"),
        contract,
    )
    seasonality = next(item for item in requirements if item["name"] == "seasonality_estimability")

    assert seasonality["assessment_status"] == "estimable_with_limits"
    assert seasonality["parameters"] == {
        "seasonality_period": "monthly",
        "frequency": "daily",
        "period_observations": 30,
        "minimum_complete_cycles": 2,
        "complete_cycles": 2,
        "estimability": "estimable_with_limits",
    }


def test_monthly_seasonality_requirement_rejects_annual_evidence():
    requirement = next(
        item
        for item in _compile(
            _time_series_plan(claim_type="seasonality", seasonality_period="monthly"),
            _contract(pd.date_range("2025-01-01", periods=60, freq="D")),
        )
        if item["name"] == "seasonality_estimability"
    )
    annual_evidence = [{
        "id": "annual_assessment",
        "requirement_ids": [requirement["id"]],
        "seasonality_estimability": {
            "period": "annual",
            "status": "not_estimable",
            "period_observations": 365,
            "minimum_complete_cycles": 2,
            "complete_cycles": 0,
            "reason": "Only 60 daily observations are available.",
        },
    }]

    evaluated = evaluate_requirement_satisfaction([requirement], annual_evidence)

    assert evaluated[0]["status"] == "unmet"


def test_computable_time_series_evidence_does_not_trigger_user_question():
    state = AnalysisSessionState(session_id="time_series_question", data_state="data_loaded")
    state.active_scope.update({"active_dataset": "orders", "active_mode": "data_loaded"})
    state.dataset_contracts = [_contract(pd.date_range("2026-01-01", periods=8, freq="MS"))]
    state.route_proposals = [{
        "id": "route_trend",
        "dataset": "orders",
        "direction": "trend",
        "field_roles": {"date": ["month"], "metrics": ["revenue"], "dimensions": []},
        "evidence_requirements": [
            "time_frequency",
            "missing_intervals",
            "window_comparability",
            "autocorrelation_awareness",
            "seasonality_estimability",
        ],
    }]
    intent = TurnIntent(
        intent_type="directed_analysis",
        clarity="clear",
        data_state="data_loaded",
        analysis_stage="execute",
        recommended_action="run_analysis",
        execution_readiness="ready",
        reason="test",
        ambiguities=[],
    )

    gate = detect_question_need("show revenue trend by month", intent, state)
    decision = decide_analysis_entry("show revenue trend by month", intent, state)

    assert gate["status"] == "clear"
    assert decision["decision"] == "direct_analysis"
    assert decision["analysis_evidence_to_compute"] == [
        "time_frequency",
        "missing_intervals",
        "window_comparability",
        "autocorrelation_awareness",
        "seasonality_estimability",
    ]


def test_time_series_tool_emits_server_checkable_assurance_fields(tmp_path):
    from data_agent.agent.evidence_contracts import persist_computation_output
    from data_agent.tools.eda import analyze_time_series
    from data_agent.tools.registry import registry

    frame = pd.DataFrame({
        "month": pd.date_range("2025-01-01", periods=8, freq="MS"),
        "revenue": [10, 11, 12, 13, 15, 14, 16, 17],
    })
    context = AgentContext(session_id="time_series_tool", workspace=Workspace())
    with use_agent_context(context):
        context.workspace.add("orders", frame)
        result = json.loads(
            analyze_time_series("orders", date_col="month", value_col="revenue")
        )

    assert result["time_frequency"] == "monthly"
    assert result["missing_intervals"]["count"] == 0
    assert result["effective_sample_size"]["observed_total"] == 8
    assert 0 < result["effective_sample_size"]["total"] <= 8
    assert result["effective_sample_size"]["design"] == "time_series"
    assert result["window_comparability"]["status"] == "comparable"
    assert result["seasonality_estimability"]["status"] == "not_estimable"
    assert result["seasonality_estimability"]["minimum_complete_cycles"] == 2
    assert result["seasonality_estimability"]["period"] == "annual"
    assert "seasonality" not in result
    assert result["trend"]["inference_status"] == "not_assessed"
    assert "p_value" not in result["trend"]
    assert "significant" not in result["trend"]

    capability = registry.capability_for("analyze_time_series")
    assert {
        "time_frequency",
        "missing_intervals",
        "window_comparability",
        "autocorrelation_awareness",
        "effective_sample_size",
        "missingness",
        "seasonality_estimability",
        "assumptions",
    } <= set(capability["evidence_fields"])
    ref = persist_computation_output(
        sessions_root=tmp_path,
        session_id="time_series_tool",
        turn_id="turn_1",
        plan_id="plan_time",
        step_id="step_time",
        tool_call_id="call_time",
        tool_name="analyze_time_series",
        arguments={"name": "orders"},
        output={"data": result},
        dataset_versions=["dataset_orders"],
        success=True,
        capability_id=capability["capability_id"],
        evidence_fields=capability["evidence_fields"],
    )
    assert {
        "time_frequency",
        "missing_intervals",
        "window_comparability",
        "autocorrelation_awareness",
        "effective_sample_size",
        "missingness",
        "seasonality_estimability",
        "assumptions",
    } <= set(ref["structured_checked_fields"])


def test_time_series_tool_emits_the_requested_monthly_estimability():
    from data_agent.tools.eda import analyze_time_series

    frame = pd.DataFrame({
        "date": pd.date_range("2025-01-01", periods=60, freq="D"),
        "revenue": range(60),
    })
    context = AgentContext(session_id="monthly_seasonality", workspace=Workspace())
    with use_agent_context(context):
        context.workspace.add("orders", frame)
        result = json.loads(analyze_time_series(
            "orders",
            date_col="date",
            value_col="revenue",
            seasonality_period="monthly",
        ))

    assert result["seasonality_estimability"] == {
        "period": "monthly",
        "period_observations": 30,
        "minimum_complete_cycles": 2,
        "complete_cycles": 2,
        "status": "estimable_with_limits",
        "reason": (
            "Only 2 complete monthly cycles are available; "
            "seasonality estimates require explicit uncertainty and limitations."
        ),
    }


def test_constant_time_series_emits_finite_flat_trend():
    from data_agent.tools.eda import analyze_time_series

    frame = pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=10, freq="D"),
        "revenue": [7.0] * 10,
    })
    context = AgentContext(session_id="constant_series", workspace=Workspace())
    with use_agent_context(context):
        context.workspace.add("orders", frame)
        raw = analyze_time_series("orders", date_col="date", value_col="revenue")
        result = json.loads(raw, parse_constant=lambda value: (_ for _ in ()).throw(
            AssertionError(f"non-standard JSON constant: {value}")
        ))

    assert result["trend"] == {
        "direction": "flat",
        "slope": 0.0,
        "r_squared": 0.0,
        "method": "descriptive_ordinary_least_squares",
        "inference_status": "not_assessed",
    }


def test_unparseable_dates_are_counted_as_missing_time_evidence():
    from data_agent.tools.eda import analyze_time_series

    frame = pd.DataFrame({
        "date": ["2026-01-01", "bad-date", "2026-01-03"],
        "revenue": [10.0, 20.0, 30.0],
    })
    context = AgentContext(session_id="invalid_date", workspace=Workspace())
    with use_agent_context(context):
        context.workspace.add("orders", frame)
        result = json.loads(analyze_time_series(
            "orders",
            date_col="date",
            value_col="revenue",
        ))

    assert result["data_points"] == 2
    assert result["missingness"]["date"] == {
        "missing_count": 1,
        "missing_rate": 1 / 3,
    }


def test_duplicate_timestamps_require_an_explicit_time_point_estimand():
    from data_agent.tools.eda import analyze_time_series

    frame = pd.DataFrame({
        "date": list(pd.date_range("2026-01-01", periods=4, freq="D")) * 2,
        "revenue": [1, 2, 3, 4, 10, 20, 30, 40],
    })
    context = AgentContext(session_id="duplicate_time", workspace=Workspace())
    with use_agent_context(context):
        context.workspace.add("transactions", frame)
        blocked = json.loads(analyze_time_series(
            "transactions",
            date_col="date",
            value_col="revenue",
        ))
        aggregated = json.loads(analyze_time_series(
            "transactions",
            date_col="date",
            value_col="revenue",
            agg_func="sum",
        ))

    assert blocked["error_type"] == "estimand_definition_required"
    assert aggregated["data_points"] == 4
    assert aggregated["estimand"]["aggregation"] == "sum"
    assert aggregated["effective_sample_size"]["unique_time_points"] == 4
