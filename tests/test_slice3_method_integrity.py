"""Slice 3 deterministic method contracts and real-data oracle tests."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from data_agent.session.workspace import workspace
from data_agent.tools.curve_fitting import curve_fitting
from data_agent.tools.factor_analysis import factor_relationships
from data_agent.tools.ml import forecast
from data_agent.tools.registry import registry
import data_agent.tools.simulation  # register existing advanced capability
import data_agent.tools.statistics  # register existing advanced capability


def _load(name: str, frame: pd.DataFrame) -> None:
    workspace.remove(name)
    workspace.add(name, frame)


def test_d09_curve_oracle_is_source_bound_and_discloses_truncation():
    frame = pd.read_excel(Path("reference/test_doc") / "游戏B留存.xlsx")
    _load("slice3_d09", frame)
    columns = ",".join(column for column in frame.columns if column.endswith("天后"))
    result = curve_fitting("slice3_d09", series_columns=columns)
    assert result.data["method_contract"] == "analysis_method_result.v1"
    assert result.data["data_identity"]["fingerprint"].startswith("sha256:")
    assert result.data["best_family"] == "power"
    assert result.data["fits"][0]["parameters"]["a"] == pytest_approx(0.1880, 0.002)
    assert result.data["fits"][0]["parameters"]["b"] == pytest_approx(-0.7167, 0.003)
    assert result.data["fits"][0]["r_squared"] == pytest_approx(0.9824, 0.002)
    assert result.data["points"][-1]["n_excluded_zeros"] == 6


def pytest_approx(value: float, tolerance: float):
    # Avoid a module-level pytest dependency in direct tool smoke runners.
    class Approx:
        def __eq__(self, actual):
            return abs(actual - value) <= tolerance
    return Approx()


def test_curve_fitting_is_limited_for_too_few_points():
    _load("curve_short", pd.DataFrame({"1天后": [0.2], "2天后": [0.1], "3天后": [0.05]}))
    result = curve_fitting("curve_short", series_columns="1天后,2天后,3天后")
    assert result.data["status"] == "limited"
    assert result.data["reason_code"] == "insufficient_points"


def test_forecast_uses_ordered_holdout_and_rejects_missing_intervals():
    dates = pd.date_range("2026-01-01", periods=30, freq="D")
    _load("forecast_ok", pd.DataFrame({"date": dates, "sales": 100 + np.arange(30)}))
    result = json.loads(forecast("forecast_ok", "sales", "date", 5))
    assert result["parameters"]["backtest_scheme"] == "ordered_holdout"
    assert len(result["forecast"]) == 5
    assert all(item["yhat_lower"] <= item["yhat"] <= item["yhat_upper"] for item in result["forecast"])
    _load("forecast_gap", pd.DataFrame({"date": dates.delete(5), "sales": np.arange(29)}))
    gap = json.loads(forecast("forecast_gap", "sales", "date", 5))
    assert gap["reason_code"] == "missing_time_intervals"
    assert "forecast" not in gap


def test_factor_identity_and_collinearity_degrade_without_claim():
    x = np.arange(1, 33, dtype=float)
    _load("factor_collinear", pd.DataFrame({"target": x + np.sin(x), "x1": x, "x2": x * 2}))
    result = factor_relationships("factor_collinear", "target", ["x1", "x2"])
    assert result.data["status"] == "limited"
    assert result.data["reason_code"] == "multicollinearity_prevents_attribution"
    assert result.data["claim_ceiling"] == "associational"


def test_advanced_tools_remain_registered_and_curve_is_provider_neutral_reachable():
    for name in ("forecast", "classification", "regression_analysis", "attribution_analysis", "shap_analysis", "what_if_simulation", "curve_fitting"):
        assert registry.get(name) is not None
