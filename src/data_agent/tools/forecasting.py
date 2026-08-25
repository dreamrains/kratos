"""Backtested baseline forecasting used by the existing ``forecast`` tool."""

from __future__ import annotations

import numpy as np
import pandas as pd

from data_agent.tools._utils import get_df
from data_agent.tools.method_contract import method_receipt
from data_agent.tools.registry import ToolResult


def backtested_forecast(name: str, target_col: str, date_col: str, periods: int) -> ToolResult:
    frame, error = get_df(name)
    if error:
        return ToolResult(summary=error)
    if target_col not in frame.columns or date_col not in frame.columns:
        return ToolResult(summary=f"列不存在。可用: {list(frame.columns)}")
    dates = pd.to_datetime(frame[date_col], errors="coerce")
    values = pd.to_numeric(frame[target_col], errors="coerce")
    data = pd.DataFrame({"date": dates, "value": values}).dropna().sort_values("date")
    if data["date"].duplicated().any():
        data = data.groupby("date", as_index=False)["value"].sum()
    if len(data) < max(20, periods * 3):
        receipt = method_receipt(name, method="expanding_window_naive_baseline", status="limited", effective_n=len(data), parameters={"date_col": date_col, "target_col": target_col, "periods": periods}, limitations=["有效时间点不足以同时完成留出回测和预测。"], reason_code="insufficient_time_points")
        return ToolResult(summary="有效时间点不足，未生成预测", data=receipt)
    deltas = data["date"].diff().dropna()
    if deltas.empty or deltas.nunique() != 1:
        receipt = method_receipt(name, method="expanding_window_naive_baseline", status="limited", effective_n=len(data), parameters={"date_col": date_col, "target_col": target_col, "periods": periods}, limitations=["时间间隔不完整或不规则；系统不会静默补值。"], reason_code="missing_time_intervals")
        return ToolResult(summary="时间间隔不完整，未生成预测", data=receipt)
    horizon = min(periods, max(3, len(data) // 5))
    train, validation = data.iloc[:-horizon], data.iloc[-horizon:]
    # Candidate 1: last observation; candidate 2: linear trend.  Both are
    # evaluated only on data unavailable to their fit.
    naive = np.repeat(float(train["value"].iloc[-1]), horizon)
    slope, intercept = np.polyfit(np.arange(len(train)), train["value"].to_numpy(), 1)
    trend = intercept + slope * np.arange(len(train), len(train) + horizon)
    actual = validation["value"].to_numpy(dtype=float)
    candidates = {"naive_last_value": naive, "linear_trend": trend}
    scores = {key: float(np.mean(np.abs(actual - predicted))) for key, predicted in candidates.items()}
    selected = min(scores, key=scores.get)
    residual_scale = float(np.std(actual - candidates[selected], ddof=1)) if horizon > 1 else 0.0
    if not np.isfinite(residual_scale):
        residual_scale = 0.0
    full_values = data["value"].to_numpy(dtype=float)
    if selected == "naive_last_value":
        predicted = np.repeat(float(full_values[-1]), periods)
    else:
        full_slope, full_intercept = np.polyfit(np.arange(len(full_values)), full_values, 1)
        predicted = full_intercept + full_slope * np.arange(len(full_values), len(full_values) + periods)
    future_dates = pd.date_range(data["date"].iloc[-1] + deltas.iloc[0], periods=periods, freq=deltas.iloc[0])
    receipt = method_receipt(name, method=selected, status="supported", effective_n=len(data), parameters={"date_col": date_col, "target_col": target_col, "periods": periods, "validation_points": horizon, "backtest_scheme": "ordered_holdout"}, limitations=["预测为短期统计外推，不构成保证或因果结论。", "候选模型仅在当前时间范围内以留出误差比较。"], claim_ceiling="predictive")
    receipt.update(backtest={"mae": round(scores[selected], 8), "candidates_mae": {key: round(value, 8) for key, value in scores.items()}}, forecast=[{"date": str(date.date()), "yhat": round(float(value), 8), "yhat_lower": round(float(value - 1.96 * residual_scale), 8), "yhat_upper": round(float(value + 1.96 * residual_scale), 8)} for date, value in zip(future_dates, predicted)])
    return ToolResult(summary=f"已用 {selected} 完成 {horizon} 点留出回测，并生成 {periods} 期预测。", data=receipt)
