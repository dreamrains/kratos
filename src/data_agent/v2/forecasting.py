from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from data_agent.v2.models import ClaimClass
from data_agent.v2.time_series import (
    TimeAggregation,
    TimeFrequency,
    prepare_regular_series,
)


@dataclass(frozen=True, slots=True)
class ForecastSpec:
    time_field: str
    metric: str
    frequency: TimeFrequency
    aggregation: TimeAggregation
    horizon: int
    alpha: float = 0.05

    def __post_init__(self) -> None:
        time_field = str(self.time_field or "").strip()
        metric = str(self.metric or "").strip()
        if not time_field or not metric or time_field == metric:
            raise ValueError("distinct time_field and metric are required")
        try:
            horizon = int(self.horizon)
        except (TypeError, ValueError) as exc:
            raise ValueError("horizon must be an integer") from exc
        if horizon <= 0 or horizon > 30:
            raise ValueError("horizon must be between 1 and 30")
        if not 0 < float(self.alpha) < 1:
            raise ValueError("alpha must be between 0 and 1")
        object.__setattr__(self, "time_field", time_field)
        object.__setattr__(self, "metric", metric)
        object.__setattr__(self, "frequency", TimeFrequency(self.frequency))
        object.__setattr__(self, "aggregation", TimeAggregation(self.aggregation))
        object.__setattr__(self, "horizon", horizon)


@dataclass(frozen=True, slots=True)
class ForecastResult:
    status: str
    reason_code: str
    time_field: str
    metric: str
    frequency: TimeFrequency
    aggregation: TimeAggregation
    horizon: int
    historical_times: tuple[str, ...] = ()
    historical_values: tuple[float, ...] = ()
    forecast_times: tuple[str, ...] = ()
    forecast_values: tuple[float, ...] = ()
    interval_low: tuple[float, ...] = ()
    interval_high: tuple[float, ...] = ()
    selected_method: str = ""
    candidate_methods: tuple[str, ...] = ()
    candidate_metrics: dict[str, dict[str, float]] = field(default_factory=dict)
    validation_points: int = 0
    mae: float | None = None
    rmse: float | None = None
    mase: float | None = None
    skill_vs_naive: float | None = None
    error_to_level_ratio: float | None = None
    backtest_scheme: str = ""
    interval_method: str = ""
    source_rows: int = 0
    valid_rows: int = 0
    observed_periods: int = 0
    missing_periods: int = 0
    imputed_periods: int = 0
    maximum_claim_class: ClaimClass = ClaimClass.PREDICTIVE
    limitations: tuple[str, ...] = field(default_factory=tuple)


def _season_length(frequency: TimeFrequency) -> int:
    return {
        TimeFrequency.DAILY: 7,
        TimeFrequency.WEEKLY: 52,
        TimeFrequency.MONTHLY: 12,
    }[frequency]


def _method_forecast(
    history: np.ndarray,
    method: str,
    horizon: int,
    season_length: int,
) -> np.ndarray:
    if method == "naive_last":
        return np.repeat(history[-1], horizon).astype(float)
    if method == "drift":
        slope = (history[-1] - history[0]) / max(1, len(history) - 1)
        return history[-1] + slope * np.arange(1, horizon + 1, dtype=float)
    if method == "seasonal_naive":
        if len(history) < season_length:
            raise ValueError("seasonal history is unavailable")
        season = history[-season_length:]
        return np.asarray(
            [season[(step - 1) % season_length] for step in range(1, horizon + 1)],
            dtype=float,
        )
    raise ValueError(f"unsupported forecast method: {method}")


def _limited(
    frame: pd.DataFrame,
    spec: ForecastSpec,
    *,
    reason_code: str,
    series: pd.Series | None = None,
    valid_rows: int = 0,
    missing_periods: int = 0,
    selected_method: str = "",
    candidate_methods: tuple[str, ...] = (),
    candidate_metrics: dict[str, dict[str, float]] | None = None,
    validation_points: int = 0,
    mae: float | None = None,
    rmse: float | None = None,
    mase: float | None = None,
    skill_vs_naive: float | None = None,
    error_to_level_ratio: float | None = None,
) -> ForecastResult:
    regular = series if series is not None else pd.Series(dtype=float)
    return ForecastResult(
        status="limited",
        reason_code=reason_code,
        time_field=spec.time_field,
        metric=spec.metric,
        frequency=spec.frequency,
        aggregation=spec.aggregation,
        horizon=spec.horizon,
        historical_times=tuple(pd.Timestamp(item).isoformat() for item in regular.index),
        historical_values=tuple(float(item) for item in regular.to_numpy(dtype=float)),
        selected_method=selected_method,
        candidate_methods=candidate_methods,
        candidate_metrics=candidate_metrics or {},
        validation_points=validation_points,
        mae=mae,
        rmse=rmse,
        mase=mase,
        skill_vs_naive=skill_vs_naive,
        error_to_level_ratio=error_to_level_ratio,
        backtest_scheme="expanding_window_one_step" if validation_points else "",
        source_rows=len(frame),
        valid_rows=valid_rows,
        observed_periods=len(regular),
        missing_periods=missing_periods,
        imputed_periods=0,
        maximum_claim_class=ClaimClass.ASSOCIATIONAL,
        limitations=(
            "当前数据或时间外回测不足以支持可用的未来预测。",
            "系统没有补零、插值或随机打乱时间顺序。",
        ),
    )


def forecast_time_series(frame: pd.DataFrame, spec: ForecastSpec) -> ForecastResult:
    prepared = prepare_regular_series(
        frame,
        time_field=spec.time_field,
        metric=spec.metric,
        frequency=spec.frequency,
        aggregation=spec.aggregation,
    )
    if prepared.status == "limited":
        return _limited(
            frame,
            spec,
            reason_code=prepared.reason_code,
            series=prepared.series,
            valid_rows=prepared.valid_rows,
            missing_periods=prepared.missing_periods,
        )
    series = prepared.series
    values = series.to_numpy(dtype=float)
    observed = len(values)
    if spec.horizon > observed // 4:
        return _limited(
            frame,
            spec,
            reason_code="forecast_horizon_too_long",
            series=series,
            valid_rows=prepared.valid_rows,
        )
    validation_points = max(6, spec.horizon, int(math.ceil(observed * 0.2)))
    if observed - validation_points < 8:
        return _limited(
            frame,
            spec,
            reason_code="insufficient_forecast_history",
            series=series,
            valid_rows=prepared.valid_rows,
        )
    season_length = _season_length(spec.frequency)
    methods = ["naive_last", "drift"]
    if observed >= 2 * season_length + 6:
        methods.append("seasonal_naive")
    start = observed - validation_points
    errors: dict[str, list[float]] = {method: [] for method in methods}
    signed_errors: dict[str, list[float]] = {method: [] for method in methods}
    for index in range(start, observed):
        history = values[:index]
        actual = float(values[index])
        for method in methods:
            prediction = float(_method_forecast(history, method, 1, season_length)[0])
            signed_errors[method].append(actual - prediction)
            errors[method].append(abs(actual - prediction))
    metrics: dict[str, dict[str, float]] = {}
    for method in methods:
        signed = np.asarray(signed_errors[method], dtype=float)
        absolute = np.asarray(errors[method], dtype=float)
        metrics[method] = {
            "mae": float(np.mean(absolute)),
            "rmse": float(np.sqrt(np.mean(np.square(signed)))),
        }
    selected = min(methods, key=lambda item: (metrics[item]["mae"], item))
    selected_mae = metrics[selected]["mae"]
    selected_rmse = metrics[selected]["rmse"]
    naive_mae = metrics["naive_last"]["mae"]
    training = values[:start]
    seasonal_scale = (
        np.abs(training[season_length:] - training[:-season_length])
        if len(training) > season_length
        else np.asarray([], dtype=float)
    )
    lag1_scale = np.abs(np.diff(training))
    scale_values = seasonal_scale[seasonal_scale > 0]
    if not len(scale_values):
        scale_values = lag1_scale[lag1_scale > 0]
    scale = float(np.mean(scale_values)) if len(scale_values) else 0.0
    mase = selected_mae / scale if scale > 0 else 0.0 if selected_mae == 0 else math.inf
    skill = 1 - selected_mae / naive_mae if naive_mae > 0 else 0.0
    typical_level = float(np.median(np.abs(values[start:])))
    error_to_level = selected_mae / typical_level if typical_level > 0 else math.inf
    for method in methods:
        metrics[method]["validation_points"] = float(validation_points)
    if not np.isfinite(mase) or mase > 1.25 or error_to_level > 1.0:
        return _limited(
            frame,
            spec,
            reason_code="backtest_quality_below_threshold",
            series=series,
            valid_rows=prepared.valid_rows,
            selected_method=selected,
            candidate_methods=tuple(methods),
            candidate_metrics=metrics,
            validation_points=validation_points,
            mae=selected_mae,
            rmse=selected_rmse,
            mase=float(mase),
            skill_vs_naive=float(skill),
            error_to_level_ratio=float(error_to_level),
        )
    forecast_values = _method_forecast(values, selected, spec.horizon, season_length)
    absolute_errors = np.asarray(errors[selected], dtype=float)
    quantile_level = min(1.0, math.ceil((len(absolute_errors) + 1) * (1 - spec.alpha)) / len(absolute_errors))
    one_step_radius = float(np.quantile(absolute_errors, quantile_level, method="higher"))
    radii = one_step_radius * np.sqrt(np.arange(1, spec.horizon + 1, dtype=float))
    alias = {
        TimeFrequency.DAILY: "D",
        TimeFrequency.WEEKLY: "W-MON",
        TimeFrequency.MONTHLY: "MS",
    }[spec.frequency]
    future_times = pd.date_range(series.index[-1], periods=spec.horizon + 1, freq=alias)[1:]
    return ForecastResult(
        status="supported",
        reason_code="backtested_baseline_forecast",
        time_field=spec.time_field,
        metric=spec.metric,
        frequency=spec.frequency,
        aggregation=spec.aggregation,
        horizon=spec.horizon,
        historical_times=tuple(pd.Timestamp(item).isoformat() for item in series.index),
        historical_values=tuple(float(item) for item in values),
        forecast_times=tuple(pd.Timestamp(item).isoformat() for item in future_times),
        forecast_values=tuple(float(item) for item in forecast_values),
        interval_low=tuple(float(item) for item in forecast_values - radii),
        interval_high=tuple(float(item) for item in forecast_values + radii),
        selected_method=selected,
        candidate_methods=tuple(methods),
        candidate_metrics=metrics,
        validation_points=validation_points,
        mae=selected_mae,
        rmse=selected_rmse,
        mase=float(mase),
        skill_vs_naive=float(skill),
        error_to_level_ratio=float(error_to_level),
        backtest_scheme="expanding_window_one_step",
        interval_method="empirical_backtest_absolute_error_sqrt_h",
        source_rows=len(frame),
        valid_rows=prepared.valid_rows,
        observed_periods=observed,
        missing_periods=0,
        imputed_periods=0,
        maximum_claim_class=ClaimClass.PREDICTIVE,
        limitations=(
            "预测区间来自有限的滚动时间外误差，并按预测步长扩张，不保证未来必然覆盖。",
            "预测是历史延续条件下的可解释基线，不代表结构变化、外部冲击或干预效果。",
            "新增真实数据后应重新回测并更新预测。",
        ),
    )
