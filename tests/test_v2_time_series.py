import numpy as np
import pandas as pd

from data_agent.v2.time_series import (
    TimeAggregation,
    TimeFrequency,
    TimeSeriesSpec,
    analyze_time_series,
)


def test_daily_trend_uses_hac_and_controls_weekday_seasonality():
    dates = pd.date_range("2026-01-01", periods=70, freq="D")
    index = np.arange(len(dates), dtype=float)
    frame = pd.DataFrame(
        {
            "date": dates.strftime("%Y-%m-%d"),
            "sales": 100 + 1.5 * index + 8 * np.sin(2 * np.pi * index / 7),
        }
    )

    result = analyze_time_series(
        frame,
        TimeSeriesSpec("date", "sales", TimeFrequency.DAILY, TimeAggregation.SUM),
    )

    assert result.status == "supported"
    assert result.trend_per_period > 1.4
    assert result.confidence_low > 0
    assert result.p_value < 0.001
    assert result.covariance_method == "HAC"
    assert result.seasonality_control == "weekday"
    assert result.hac_max_lag >= 1
    assert result.observed_periods == 70
    assert result.missing_periods == 0


def test_weekday_seasonality_without_trend_is_null_not_stable_claim():
    dates = pd.date_range("2026-01-01", periods=70, freq="D")
    index = np.arange(len(dates), dtype=float)
    frame = pd.DataFrame(
        {
            "date": dates,
            "sales": 100 + 8 * np.sin(2 * np.pi * index / 7),
        }
    )

    result = analyze_time_series(
        frame,
        TimeSeriesSpec("date", "sales", TimeFrequency.DAILY, TimeAggregation.MEAN),
    )

    assert result.status == "null_result"
    assert result.reason_code == "no_reliable_linear_trend"
    assert result.confidence_low <= 0 <= result.confidence_high


def test_missing_regular_interval_is_limited_without_imputation():
    dates = pd.date_range("2026-01-01", periods=20, freq="D").delete(7)
    frame = pd.DataFrame({"date": dates, "sales": np.arange(len(dates))})

    result = analyze_time_series(
        frame,
        TimeSeriesSpec("date", "sales", TimeFrequency.DAILY, TimeAggregation.SUM),
    )

    assert result.status == "limited"
    assert result.reason_code == "missing_time_intervals"
    assert result.missing_periods == 1
    assert result.imputed_periods == 0


def test_ambiguous_date_semantics_are_delegated_to_slice3():
    frame = pd.DataFrame(
        {"date": ["01/02/2026", "03/04/2026", "05/06/2026"], "sales": [1, 2, 3]}
    )

    result = analyze_time_series(
        frame,
        TimeSeriesSpec("date", "sales", TimeFrequency.MONTHLY, TimeAggregation.SUM),
    )

    assert result.status == "limited"
    assert result.reason_code == "date_semantics_require_confirmation"


def test_explicit_sum_and_mean_aggregation_produce_different_series():
    frame = pd.DataFrame(
        {
            "date": ["2026-01-01", "2026-01-01", "2026-01-02", "2026-01-02"],
            "sales": [10, 20, 30, 50],
        }
    )

    summed = analyze_time_series(
        frame,
        TimeSeriesSpec("date", "sales", TimeFrequency.DAILY, TimeAggregation.SUM),
    )
    averaged = analyze_time_series(
        frame,
        TimeSeriesSpec("date", "sales", TimeFrequency.DAILY, TimeAggregation.MEAN),
    )

    assert summed.series_values == (30.0, 80.0)
    assert averaged.series_values == (15.0, 40.0)
    assert summed.aggregation is TimeAggregation.SUM
    assert averaged.aggregation is TimeAggregation.MEAN


def test_small_weekly_series_is_judged_by_model_df_not_n30():
    dates = pd.date_range("2026-01-05", periods=10, freq="W-MON")
    frame = pd.DataFrame({"date": dates, "sales": 10 + 2 * np.arange(10)})

    result = analyze_time_series(
        frame,
        TimeSeriesSpec("date", "sales", TimeFrequency.WEEKLY, TimeAggregation.SUM),
    )

    assert result.reason_code != "fixed_small_sample_rule"
    assert result.status in {"supported", "null_result"}


def test_subweekly_rows_with_partial_boundary_weeks_fail_closed():
    dates = pd.date_range("2026-01-01", "2026-02-11", freq="D")
    frame = pd.DataFrame({"date": dates, "sales": 100 + np.arange(len(dates))})

    result = analyze_time_series(
        frame,
        TimeSeriesSpec("date", "sales", TimeFrequency.WEEKLY, TimeAggregation.SUM),
    )

    assert result.status == "limited"
    assert result.reason_code == "incomplete_boundary_periods"
    assert result.incomplete_boundary_periods == 2
    assert result.start_time.startswith("2026-01-01")
    assert result.end_time.startswith("2026-02-11")
    assert result.trend_per_period is None


def test_subweekly_rows_covering_complete_weeks_remain_eligible():
    dates = pd.date_range("2026-01-05", periods=70, freq="D")
    frame = pd.DataFrame({"date": dates, "sales": 100 + np.arange(len(dates))})

    result = analyze_time_series(
        frame,
        TimeSeriesSpec("date", "sales", TimeFrequency.WEEKLY, TimeAggregation.SUM),
    )

    assert result.status in {"supported", "null_result"}
    assert result.incomplete_boundary_periods == 0
    assert result.start_time.startswith("2026-01-05")
    assert result.end_time.startswith("2026-03-15")


def test_submonthly_rows_with_partial_boundary_months_fail_closed():
    dates = pd.date_range("2026-01-15", "2026-06-20", freq="D")
    frame = pd.DataFrame({"date": dates, "sales": 100 + np.arange(len(dates))})

    result = analyze_time_series(
        frame,
        TimeSeriesSpec("date", "sales", TimeFrequency.MONTHLY, TimeAggregation.MEAN),
    )

    assert result.status == "limited"
    assert result.reason_code == "incomplete_boundary_periods"
    assert result.incomplete_boundary_periods == 2


def test_monthly_two_year_series_controls_month_seasonality():
    dates = pd.date_range("2024-01-01", periods=30, freq="MS")
    index = np.arange(30, dtype=float)
    seasonal = np.tile(np.arange(12, dtype=float), 3)[:30]
    frame = pd.DataFrame({"date": dates, "sales": 50 + index + seasonal})

    result = analyze_time_series(
        frame,
        TimeSeriesSpec("date", "sales", TimeFrequency.MONTHLY, TimeAggregation.SUM),
    )

    assert result.seasonality_control == "month"
    assert result.observed_periods == 30
