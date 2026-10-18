"""Deterministic descriptive curve fitting for existing analysis sessions."""

from __future__ import annotations

import json
import math
import re

import numpy as np
import pandas as pd

from data_agent.agent.publication.native import MINIMAL_PRODUCT_CONTRACTS
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
        "residuals": [float(value) for value in residual],
    }


def _aggregate_point(df, raw_values, x, *, zero_values, weight_col, mature_through_col, compare_weights=False):
    values = pd.to_numeric(raw_values, errors="coerce")
    mature = pd.Series(True, index=df.index)
    if mature_through_col:
        through = pd.to_numeric(df[mature_through_col], errors="coerce")
        if not (through.notna() & np.isfinite(through) & (through >= 0)).all():
            raise ValueError("最大已观测日龄列含未知、非有限或负值，无法核定成熟范围")
        mature = through >= x
    valid = np.isfinite(values).fillna(False)
    excluded_zeros = int((mature & valid & (values == 0)).sum()) if zero_values == "exclude" else 0
    selected = mature & valid
    if zero_values == "exclude":
        selected &= values != 0
    observed = values[selected]
    if observed.empty:
        return None
    weight_sum = None
    if weight_col:
        weights = pd.to_numeric(df.loc[selected, weight_col], errors="coerce")
        if not (weights.notna() & np.isfinite(weights) & (weights > 0)).all():
            raise ValueError("有效观测的人数权重含未知、非有限或非正值，无法计算人数加权均值")
        weight_sum = float(weights.sum())
        if not math.isfinite(weight_sum):
            raise ValueError("有效观测的人数权重合计非有限，无法计算人数加权均值")
        y = float(np.sum(observed * (weights / weight_sum)))
    else:
        y = float(observed.mean())
    point = {"x": float(x), "y": y, "n_observed": int(selected.sum()),
            "n_excluded_zeros": excluded_zeros, "n_excluded_immature": int((~mature).sum()),
            "n_excluded_invalid": int((mature & ~valid).sum()), "weight_sum": weight_sum}
    if compare_weights:
        point["ordinary_mean"] = float(observed.mean())
    return point


def _curve_points(df, *, series_columns="", x_col="", y_col="", zero_values="exclude", weight_col="", mature_through_col="", compare_weights=False):
    points: list[dict] = []
    if series_columns:
        columns = [item.strip() for item in series_columns.split(",") if item.strip()]
        missing = sorted(set(columns) - set(df.columns))
        if missing:
            raise ValueError(f"列不存在: {missing}")
        for position, column in enumerate(columns, 1):
            match = _DAY.search(column)
            x = float(match.group(1)) if match else float(position)
            point = _aggregate_point(df, df[column], x, zero_values=zero_values,
                                     weight_col=weight_col, mature_through_col=mature_through_col, compare_weights=compare_weights)
            if point is not None:
                points.append(dict(point, column=column))
        mode = "wide_series"
    else:
        if x_col not in df.columns or y_col not in df.columns:
            raise ValueError(f"列不存在。可用: {list(df.columns)}")
        x_values = pd.to_numeric(df[x_col], errors="coerce")
        for x, group in df.loc[np.isfinite(x_values)].groupby(x_values):
            point = _aggregate_point(group, group[y_col], float(x), zero_values=zero_values,
                                     weight_col=weight_col, mature_through_col=mature_through_col, compare_weights=compare_weights)
            if point is not None:
                points.append(point)
        mode = "long_columns"
    return points, mode


def _weight_sensitivity(points):
    rows = [{"x": p["x"], "ordinary_mean": p["ordinary_mean"], "weighted_mean": p["y"],
             "absolute_difference": abs(p["ordinary_mean"]-p["y"]),
             "n_observed": p["n_observed"], "weight_sum": p["weight_sum"]} for p in points]
    maximum = max((p["absolute_difference"] for p in rows), default=None)
    return {"points": rows, "max_absolute_difference": maximum,
            "max_difference_x": [p["x"] for p in rows if p["absolute_difference"] == maximum],
            "comparison": "ordinary_vs_population_weighted_same_observations"}


@registry.register(
    name="curve_fitting",
    description="比较幂律、指数和对数曲线族；默认仅描述观测区间。显式 scenario_points 可计算未验证参数情景，不授予预测或因果结论。返回已计算的实际/拟合序列。绘图请把详情引用传给 create_chart.result_ref，避免重新计算或改变零值口径。",
    output_contract=MINIMAL_PRODUCT_CONTRACTS["curve_fitting"],
    schema_overrides={
        "name": {"description": "数据集名称"},
        "series_columns": {"description": "宽表序列列，逗号分隔；列名中的数字作为 x"},
        "x_col": {"description": "长表 x 列（与 y_col 同时使用）"},
        "y_col": {"description": "长表 y 列（与 x_col 同时使用）"},
        "zero_values": {"description": "先按记录处理零值，再聚合；零值业务含义仍未知", "enum": ["exclude", "keep"]},
        "value_scale": {"enum":["unknown","fraction","percentage_points"],"description":"同一正式计划的声明呈现口径；原值及源单位证据不改，不代表原表单位已验证。"},
        "compare_weights": {"type":"boolean","description":"显式比较同一成熟/零值筛选后的普通与人数加权均值、逐点绝对差和最大差；需要weight_col，不重复拟合。"},
        "weight_col": {"description": "显式 cohort 人数列；仅对成熟且按零值口径保留的有效观测加权。省略使用普通均值，不推断人数。"},
        "mature_through_col": {"description": "显式每条 cohort 最大已观测日龄列；仅纳入 x 不大于该值的记录。省略不推断成熟度，零值业务含义仍未知。"},
        "scenario_points": {"type":"array","items":{"type":"number","exclusiveMinimum":0},"maxItems":16,"uniqueItems":True,"description":"明确请求的未验证参数情景 x 点；省略不计算。不代表未来真实值，不升级为已验证预测。"},
    },
)
def curve_fitting(name: str, series_columns: str = "", x_col: str = "", y_col: str = "", zero_values: str = "exclude", scenario_points: list[float] | None = None, weight_col: str = "", mature_through_col: str = "", value_scale: str = "unknown", compare_weights: bool = False) -> ToolResult:
    df, error = get_df(name)
    if error:
        return ToolResult(summary=error)
    if zero_values not in {"exclude", "keep"}:
        return ToolResult(summary="zero_values must be exclude or keep")
    if bool(series_columns) == bool(x_col or y_col):
        return ToolResult(summary="Specify series_columns, or both x_col and y_col")
    if scenario_points is not None and (not isinstance(scenario_points,list) or len(scenario_points)>16 or any(type(v) not in {int,float} or not math.isfinite(v) or v<=0 for v in scenario_points) or len(set(scenario_points))!=len(scenario_points)):
        return ToolResult(summary="scenario_points must contain at most 16 unique finite positive x values")
    if value_scale not in ("unknown", "fraction", "percentage_points"):
        return ToolResult(summary="value_scale must be unknown, fraction or percentage_points")
    if type(compare_weights) is not bool or (compare_weights and not weight_col):
        return ToolResult(summary="compare_weights须为布尔值；显式比较需要人数权重列")
    for column in (weight_col, mature_through_col):
        if not isinstance(column, str):
            return ToolResult(summary="人数权重列与最大已观测日龄列必须为列名字符串，无法核定所指定列")
        if column and column not in df.columns:
            return ToolResult(summary=f"列不存在: {column}")
    try:
        points, mode = _curve_points(df, series_columns=series_columns, x_col=x_col, y_col=y_col,
                                    zero_values=zero_values, weight_col=weight_col,
                                    mature_through_col=mature_through_col, compare_weights=compare_weights)
    except ValueError as exc:
        return ToolResult(summary=str(exc))
    parameters = {"mode": mode, "zero_values": zero_values}
    if weight_col:
        parameters["weight_col"] = weight_col
    if mature_through_col:
        parameters["mature_through_col"] = mature_through_col
    if value_scale != "unknown":
        parameters["value_scale"] = value_scale
    if compare_weights:
        parameters["compare_weights"] = True
    receipt = method_receipt(name, method="curve_family_comparison", status="limited", effective_n=len(points), parameters=parameters, limitations=["拟合只描述当前观测范围，不支持外推或因果解释。", "零值处理是计算口径；排除零值不证明其为未观测。无法据此确定个体行为、优化ROI或选择偏差大小。"], claim_ceiling="descriptive")
    receipt["zero_value_semantics"] = "unknown"
    if compare_weights:
        receipt["sensitivity"] = _weight_sensitivity(points)
    if points:
        receipt["observed_x_range"] = [min(p["x"] for p in points), max(p["x"] for p in points)]
        receipt["limitations"].append(f"实际观测 x 范围：{receipt['observed_x_range'][0]:g} 至 {receipt['observed_x_range'][1]:g}；拟合参数和误差仅针对这些已纳入点。")
    receipt["limitations"].append("聚合口径：" + ("按显式人数列加权。" if weight_col else "普通均值；未提供人数权重，不能解释为总体人数加权留存。"))
    receipt["limitations"].append("成熟范围：" + ("按显式最大已观测日龄逐点筛选。" if mature_through_col else "未提供最大已观测日龄列，成熟度未知；不从零值推断未到期。"))
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
    if scenario_points:
        scenarios=[]
        for point in scenario_points:
            for fit in fits:
                a,b=(fit["parameters"][key] for key in ("a","b"))
                row={"x":point,"family":fit["family"],"parameters":fit["parameters"],
                     "r_squared":fit["r_squared"],"observed_x_range":[float(x.min()),float(x.max())],
                     "validation":"none","status":"unvalidated"}
                try:
                    value=a*math.exp(b*point) if fit["family"]=="exponential" else a*point**b if fit["family"]=="power" else a+b*math.log(point)
                    if not math.isfinite(value): raise ValueError("nonfinite scenario")
                    row["value"]=value
                except (ValueError,OverflowError):
                    row.update(value=None,status="unavailable",reason="原参数在所请求点无法产生有限值")
                scenarios.append(row)
        receipt["scenarios"]=scenarios
        receipt["limitations"].append("未验证参数情景只比较原拟合公式在指定 x 的数值；未来真实值未知，没有留出、回测或外部验证，不裁剪负值，不证明预测可用。")
    receipt["chart_data"] = [
        {"x": point["x"], "actual": point["y"],
         **{fit["family"] + "_fit": fit["predicted"][i] for fit in fits}}
        for i, point in enumerate(points)
    ]
    receipt["chart_columns"] = {"x": "x", "actual": "actual", "fitted": receipt["best_family"] + "_fit"}
    summary = f"最佳描述曲线: {receipt['best_family'] or '无'}；有效点 {len(points)}。"
    return ToolResult(summary=summary, data=receipt)
