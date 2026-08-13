import numpy as np
import pandas as pd
import pytest

from data_agent.v2.forecasting import ForecastSpec, forecast_time_series
from data_agent.v2.time_series import TimeAggregation, TimeFrequency


def _spec(horizon: int = 7) -> ForecastSpec:
    return ForecastSpec(
        time_field="date",
        metric="sales",
        frequency=TimeFrequency.DAILY,
        aggregation=TimeAggregation.SUM,
        horizon=horizon,
    )


def test_trending_series_uses_ordered_backtest_and_publishes_intervals():
    dates = pd.date_range("2026-01-01", periods=70, freq="D")
    values = 100 + 2 * np.arange(70) + np.sin(np.arange(70))
    result = forecast_time_series(
        pd.DataFrame({"date": dates, "sales": values}), _spec()
    )

    assert result.status == "supported"
    assert result.selected_method == "drift"
    assert result.maximum_claim_class.value == "predictive"
    assert result.validation_points >= 7
    assert result.mase <= 1.25
    assert len(result.forecast_times) == 7
    assert len(result.forecast_values) == 7
    assert all(low <= point <= high for low, point, high in zip(
        result.interval_low, result.forecast_values, result.interval_high
    ))
    assert result.backtest_scheme == "expanding_window_one_step"


def test_weekly_seasonal_candidate_requires_two_complete_seasons():
    dates = pd.date_range("2024-01-01", periods=120, freq="W-MON")
    season = np.tile(np.arange(52, dtype=float), 3)[:120]
    frame = pd.DataFrame({"date": dates, "sales": 100 + season})

    result = forecast_time_series(
        frame,
        ForecastSpec(
            "date", "sales", TimeFrequency.WEEKLY, TimeAggregation.MEAN, 4
        ),
    )

    assert "seasonal_naive" in result.candidate_methods
    assert result.selected_method == "seasonal_naive"
    assert result.status == "supported"


def test_unpredictable_series_is_limited_by_backtest_quality():
    rng = np.random.default_rng(41)
    dates = pd.date_range("2026-01-01", periods=80, freq="D")
    values = rng.normal(0, 100, size=80)
    result = forecast_time_series(
        pd.DataFrame({"date": dates, "sales": values}), _spec()
    )

    assert result.status == "limited"
    assert result.reason_code == "backtest_quality_below_threshold"
    assert result.forecast_values == ()
    assert result.error_to_level_ratio > 1.0


def test_missing_period_is_limited_without_imputation():
    dates = pd.date_range("2026-01-01", periods=50, freq="D").delete(8)
    result = forecast_time_series(
        pd.DataFrame({"date": dates, "sales": np.arange(49)}), _spec()
    )

    assert result.status == "limited"
    assert result.reason_code == "missing_time_intervals"
    assert result.imputed_periods == 0
    assert result.forecast_values == ()


def test_ambiguous_date_is_delegated_to_semantic_confirmation():
    frame = pd.DataFrame(
        {"date": ["01/02/2026", "03/04/2026", "05/06/2026"], "sales": [1, 2, 3]}
    )
    result = forecast_time_series(frame, _spec(1))

    assert result.status == "limited"
    assert result.reason_code == "date_semantics_require_confirmation"


def test_horizon_cannot_exceed_quarter_of_observed_periods():
    dates = pd.date_range("2026-01-01", periods=40, freq="D")
    frame = pd.DataFrame({"date": dates, "sales": np.arange(40)})

    result = forecast_time_series(frame, _spec(11))

    assert result.status == "limited"
    assert result.reason_code == "forecast_horizon_too_long"


def test_forecast_spec_rejects_non_positive_or_excessive_horizon():
    with pytest.raises(ValueError, match="horizon"):
        _spec(0)
    with pytest.raises(ValueError, match="horizon"):
        _spec(31)
