from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats

from data_agent.v2.models import ClaimClass
from data_agent.v2.transformation import (
    DateTransformDisposition,
    apply_date_option,
    inspect_date_conversion,
)


class TimeFrequency(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class TimeAggregation(StrEnum):
    SUM = "sum"
    MEAN = "mean"


@dataclass(frozen=True, slots=True)
class TimeSeriesSpec:
    time_field: str
    metric: str
    frequency: TimeFrequency
    aggregation: TimeAggregation
    alpha: float = 0.05

    def __post_init__(self) -> None:
        time_field = str(self.time_field or "").strip()
        metric = str(self.metric or "").strip()
        if not time_field or not metric or time_field == metric:
            raise ValueError("distinct time_field and metric are required")
        object.__setattr__(self, "time_field", time_field)
        object.__setattr__(self, "metric", metric)
        object.__setattr__(self, "frequency", TimeFrequency(self.frequency))
        object.__setattr__(self, "aggregation", TimeAggregation(self.aggregation))
        if not 0 < float(self.alpha) < 1:
            raise ValueError("alpha must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class TimeSeriesResult:
    status: str
    reason_code: str
    time_field: str
    metric: str
    frequency: TimeFrequency
    aggregation: TimeAggregation
    series_times: tuple[str, ...] = ()
    series_values: tuple[float, ...] = ()
    fitted_values: tuple[float, ...] = ()
    trend_per_period: float | None = None
    standard_error: float | None = None
    confidence_low: float | None = None
    confidence_high: float | None = None
    p_value: float | None = None
    kendall_tau: float | None = None
    kendall_p_value: float | None = None
    lag1_autocorrelation: float | None = None
    covariance_method: str = ""
    hac_max_lag: int = 0
    seasonality_control: str = "none"
    source_rows: int = 0
    valid_rows: int = 0
    observed_periods: int = 0
    missing_periods: int = 0
    imputed_periods: int = 0
    start_time: str = ""
    end_time: str = ""
    alpha: float = 0.05
    maximum_claim_class: ClaimClass = ClaimClass.INFERENTIAL
    limitations: tuple[str, ...] = field(default_factory=tuple)


def _periodize(values: pd.Series, frequency: TimeFrequency) -> pd.Series:
    if frequency is TimeFrequency.DAILY:
        return values.dt.floor("D")
    if frequency is TimeFrequency.WEEKLY:
        return values.dt.to_period("W-SUN").dt.start_time
    return values.dt.to_period("M").dt.start_time


def _expected_index(start: pd.Timestamp, end: pd.Timestamp, frequency: TimeFrequency):
    alias = {
        TimeFrequency.DAILY: "D",
        TimeFrequency.WEEKLY: "W-MON",
        TimeFrequency.MONTHLY: "MS",
    }[frequency]
    return pd.date_range(start, end, freq=alias)


def _base(
    frame: pd.DataFrame,
    spec: TimeSeriesSpec,
    *,
    status: str,
    reason_code: str,
    times: tuple[str, ...] = (),
    values: tuple[float, ...] = (),
    valid_rows: int = 0,
    missing_periods: int = 0,
) -> TimeSeriesResult:
    return TimeSeriesResult(
        status=status,
        reason_code=reason_code,
        time_field=spec.time_field,
        metric=spec.metric,
        frequency=spec.frequency,
        aggregation=spec.aggregation,
        series_times=times,
        series_values=values,
        source_rows=len(frame),
        valid_rows=valid_rows,
        observed_periods=len(values),
        missing_periods=missing_periods,
        imputed_periods=0,
        start_time=times[0] if times else "",
        end_time=times[-1] if times else "",
        alpha=spec.alpha,
        maximum_claim_class=ClaimClass.ASSOCIATIONAL,
        limitations=(
            "当前时间结构不足以支持可靠趋势推断，系统没有补零或插值。",
            "历史时间变化不等于预测，也不识别因果效应。",
        ),
    )


def analyze_time_series(frame: pd.DataFrame, spec: TimeSeriesSpec) -> TimeSeriesResult:
    missing = sorted({spec.time_field, spec.metric} - set(frame.columns))
    if missing:
        raise KeyError(f"time-series fields not found: {missing}")
    if pd.api.types.is_datetime64_any_dtype(frame[spec.time_field]):
        parsed_time = pd.to_datetime(frame[spec.time_field], errors="coerce")
    else:
        date_plan = inspect_date_conversion(frame, spec.time_field)
        if date_plan.disposition is DateTransformDisposition.NEEDS_INPUT:
            return _base(
                frame,
                spec,
                status="limited",
                reason_code="date_semantics_require_confirmation",
            )
        if date_plan.disposition is DateTransformDisposition.UNAVAILABLE:
            return _base(
                frame,
                spec,
                status="limited",
                reason_code="time_field_not_losslessly_parseable",
            )
        converted = apply_date_option(frame, spec.time_field, date_plan.options[0])
        parsed_time = converted[spec.time_field]
    numeric = pd.to_numeric(frame[spec.metric], errors="coerce")
    working = pd.DataFrame({"time": parsed_time, "value": numeric}).replace(
        [np.inf, -np.inf], np.nan
    ).dropna()
    valid_rows = len(working)
    if valid_rows == 0:
        return _base(
            frame, spec, status="limited", reason_code="no_valid_time_metric_rows"
        )
    working["period"] = _periodize(working["time"], spec.frequency)
    grouped = working.groupby("period", sort=True)["value"]
    series = grouped.sum() if spec.aggregation is TimeAggregation.SUM else grouped.mean()
    times = tuple(pd.Timestamp(item).isoformat() for item in series.index)
    values = tuple(float(item) for item in series.to_numpy(dtype=float))
    expected = _expected_index(series.index.min(), series.index.max(), spec.frequency)
    missing_periods = int(len(expected.difference(series.index)))
    if missing_periods:
        return _base(
            frame,
            spec,
            status="limited",
            reason_code="missing_time_intervals",
            times=times,
            values=values,
            valid_rows=valid_rows,
            missing_periods=missing_periods,
        )
    if len(series) < 6:
        return _base(
            frame,
            spec,
            status="limited",
            reason_code="insufficient_trend_degrees_of_freedom",
            times=times,
            values=values,
            valid_rows=valid_rows,
        )
    if float(series.std(ddof=0)) == 0:
        return _base(
            frame,
            spec,
            status="limited",
            reason_code="constant_time_series",
            times=times,
            values=values,
            valid_rows=valid_rows,
        )
    trend = np.arange(len(series), dtype=float)
    design = pd.DataFrame({"trend": trend}, index=series.index)
    seasonality = "none"
    if spec.frequency is TimeFrequency.DAILY and len(series) >= 28:
        dummies = pd.get_dummies(series.index.dayofweek, prefix="weekday", drop_first=True, dtype=float)
        dummies.index = series.index
        design = pd.concat([design, dummies], axis=1)
        seasonality = "weekday"
    elif spec.frequency is TimeFrequency.MONTHLY and len(series) >= 24:
        dummies = pd.get_dummies(series.index.month, prefix="month", drop_first=True, dtype=float)
        dummies.index = series.index
        design = pd.concat([design, dummies], axis=1)
        seasonality = "month"
    residual_df = len(series) - len(design.columns) - 1
    if residual_df < 4:
        return _base(
            frame,
            spec,
            status="limited",
            reason_code="insufficient_trend_degrees_of_freedom",
            times=times,
            values=values,
            valid_rows=valid_rows,
        )
    x = sm.add_constant(design, has_constant="add")
    hac_lag = max(1, min(len(series) // 4, int(math.floor(4 * (len(series) / 100) ** (2 / 9)))))
    model = sm.OLS(series.to_numpy(dtype=float), x).fit(
        cov_type="HAC", cov_kwds={"maxlags": hac_lag, "use_correction": True}, use_t=True
    )
    coefficient = float(model.params["trend"])
    interval = model.conf_int(alpha=spec.alpha).loc["trend"]
    low, high = float(interval.iloc[0]), float(interval.iloc[1])
    p_value = float(model.pvalues["trend"])
    kendall = stats.kendalltau(trend, series.to_numpy(dtype=float))
    lag1 = float(series.autocorr(lag=1)) if len(series) > 2 else None
    supported = p_value < spec.alpha and (low > 0 or high < 0)
    limitations = [
        "线性趋势只描述当前历史范围，不是未来预测。",
        "时间先后与趋势不识别因果效应。",
        "HAC 推断仍依赖聚合口径、频率和模型形式适合当前序列。",
    ]
    if seasonality == "none":
        limitations.append("当前规格未加入季节哑变量，未建模季节结构可能影响趋势解释。")
    return TimeSeriesResult(
        status="supported" if supported else "null_result",
        reason_code="reliable_linear_trend" if supported else "no_reliable_linear_trend",
        time_field=spec.time_field,
        metric=spec.metric,
        frequency=spec.frequency,
        aggregation=spec.aggregation,
        series_times=times,
        series_values=values,
        fitted_values=tuple(float(item) for item in model.fittedvalues),
        trend_per_period=coefficient,
        standard_error=float(model.bse["trend"]),
        confidence_low=low,
        confidence_high=high,
        p_value=p_value,
        kendall_tau=float(kendall.statistic),
        kendall_p_value=float(kendall.pvalue),
        lag1_autocorrelation=lag1,
        covariance_method="HAC",
        hac_max_lag=hac_lag,
        seasonality_control=seasonality,
        source_rows=len(frame),
        valid_rows=valid_rows,
        observed_periods=len(series),
        missing_periods=0,
        imputed_periods=0,
        start_time=times[0],
        end_time=times[-1],
        alpha=spec.alpha,
        maximum_claim_class=ClaimClass.INFERENTIAL,
        limitations=tuple(limitations),
    )
