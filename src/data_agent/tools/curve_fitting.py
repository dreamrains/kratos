"""Deterministic descriptive curve fitting for existing analysis sessions."""

from __future__ import annotations

import json
import math
import re

import numpy as np
import pandas as pd

from data_agent.tools._utils import get_df
from data_agent.tools.method_contract import method_receipt
from data_agent.tools.registry import ToolResult, registry


_DAY = re.compile(r"(\d+)")


def _fit(x: np.ndarray, y: np.ndarray, family: str):
    if np.any(x <= 0) or (family != "logarithmic" and np.any(y <= 0)):
        return None
    design = np.log(x)
    if family == "power":
        slope, intercept = np.polyfit(design, np.log(y), 1)
        predicted = np.exp(intercept + slope * design)
        formula, params = "y = a*x^b", {"a": math.exp(intercept), "b": slope}
    elif family == "exponential":
        slope, intercept = np.polyfit(x, np.log(y), 1)
        predicted = np.exp(intercept + slope * x)
        formula, params = "y = a*exp(b*x)", {"a": math.exp(intercept), "b": slope}
    else:
        slope, intercept = np.polyfit(design, y, 1)
        predicted = intercept + slope * design
        formula, params = "y = a + b*ln(x)", {"a": intercept, "b": slope}
    residual = y - predicted
    sse = float(np.sum(residual**2))
    total = float(np.sum((y - y.mean()) ** 2))
    return {
        "family": family,
        "formula": formula,
        "parameters": {key: round(float(value), 8) for key, value in params.items()},
        "sse": round(sse, 10),
        "r_squared": round(1 - sse / total, 8) if total else 0.0,
        "mean_residual": round(float(residual.mean()), 10),
        "max_abs_residual": round(float(np.abs(residual).max()), 10),
        "predicted": [float(value) for value in predicted],
    }


@registry.register(
    name="curve_fitting",
    description="比较幂律、指数和对数曲线族；仅描述观测区间，不生成外推或因果结论。返回已计算的实际/拟合序列。绘图请把详情引用传给 create_chart.result_ref，避免重新计算或改变零值口径。",
    schema_overrides={
        "name": {"description": "数据集名称"},
        "series_columns": {"description": "宽表序列列，逗号分隔；列名中的数字作为 x"},
        "x_col": {"description": "长表 x 列（与 y_col 同时使用）"},
        "y_col": {"description": "长表 y 列（与 x_col 同时使用）"},
        "zero_values": {"description": "零值处理", "enum": ["exclude", "keep"]},
    },
)
def curve_fitting(name: str, series_columns: str = "", x_col: str = "", y_col: str = "", zero_values: str = "exclude") -> ToolResult:
    df, error = get_df(name)
    if error:
        return ToolResult(summary=error)
    if zero_values not in {"exclude", "keep"}:
        return ToolResult(summary="zero_values must be exclude or keep")
    if bool(series_columns) == bool(x_col or y_col):
        return ToolResult(summary="Specify series_columns, or both x_col and y_col")
    points: list[dict] = []
    if series_columns:
        columns = [item.strip() for item in series_columns.split(",") if item.strip()]
        missing = sorted(set(columns) - set(df.columns))
        if missing:
            return ToolResult(summary=f"列不存在: {missing}")
        for position, column in enumerate(columns, 1):
            values = pd.to_numeric(df[column], errors="coerce").dropna()
            excluded = int((values == 0).sum()) if zero_values == "exclude" else 0
            if zero_values == "exclude":
                values = values[values != 0]
            if values.empty:
                continue
            match = _DAY.search(column)
            points.append({"x": float(match.group(1)) if match else float(position), "y": float(values.mean()), "n_observed": int(len(values)), "n_excluded_zeros": excluded, "column": column})
        mode = "wide_series"
    else:
        if x_col not in df.columns or y_col not in df.columns:
            return ToolResult(summary=f"列不存在。可用: {list(df.columns)}")
        values = pd.DataFrame({"x": pd.to_numeric(df[x_col], errors="coerce"), "y": pd.to_numeric(df[y_col], errors="coerce")}).dropna().groupby("x", as_index=False).mean()
        points = [{"x": float(row.x), "y": float(row.y), "n_observed": 1, "n_excluded_zeros": 0} for row in values.itertuples(index=False)]
        mode = "long_columns"
    receipt = method_receipt(name, method="curve_family_comparison", status="limited", effective_n=len(points), parameters={"mode": mode, "zero_values": zero_values}, limitations=["拟合只描述当前观测范围，不支持外推或因果解释。", "零值处理是计算口径；排除零值不证明其为未观测。无法据此确定个体行为、优化ROI或选择偏差大小。"], claim_ceiling="descriptive")
    receipt["zero_value_semantics"] = "unknown"
    if len(points) < 5:
        receipt.update(reason_code="insufficient_points", points=points, fits=[])
        return ToolResult(summary="可用拟合点不足（至少需要 5 个不同 x）", data=receipt)
    x = np.asarray([point["x"] for point in points], dtype=float)
    y = np.asarray([point["y"] for point in points], dtype=float)
    fits, excluded = [], {}
    for family in ("power", "exponential", "logarithmic"):
        result = _fit(x, y, family)
        if result is None:
            excluded[family] = "requires x > 0 and, for power/exponential, y > 0"
        else:
            fits.append(result)
    fits.sort(key=lambda item: item["r_squared"], reverse=True)
    status = "supported" if fits and fits[0]["r_squared"] >= 0.5 else "limited"
    receipt.update(status=status, reason_code="curve_described" if status == "supported" else "no_family_describes_series", points=points, fits=fits, excluded_families=excluded, best_family=fits[0]["family"] if fits else "")
    receipt["chart_data"] = [
        {"x": point["x"], "actual": point["y"],
         **{fit["family"] + "_fit": fit["predicted"][i] for fit in fits}}
        for i, point in enumerate(points)
    ]
    receipt["chart_columns"] = {"x": "x", "actual": "actual", "fitted": receipt["best_family"] + "_fit"}
    summary = f"最佳描述曲线: {receipt['best_family'] or '无'}；有效点 {len(points)}。"
    return ToolResult(summary=summary, data=receipt)
