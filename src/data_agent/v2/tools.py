from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from data_agent.v2.models import ClaimClass


@dataclass(frozen=True, slots=True)
class ResultContract:
    capability: str
    required_inputs: tuple[str, ...]
    result_fields: tuple[str, ...]
    maximum_claim_class: ClaimClass
    known_limitations: tuple[str, ...] = ()


DESCRIBE_NUMERIC_CONTRACT = ResultContract(
    capability="analysis.describe",
    required_inputs=("dataset_version_id", "metric"),
    result_fields=("count", "missing", "mean", "minimum", "maximum"),
    maximum_claim_class=ClaimClass.DESCRIPTIVE,
    known_limitations=("描述统计仅概括当前数据范围，不识别因果关系。",),
)

DESCRIBE_TREND_CONTRACT = ResultContract(
    capability="analysis.describe_trend",
    required_inputs=("dataset_version_id", "metric", "time_field"),
    result_fields=(
        "count",
        "missing",
        "start_time",
        "end_time",
        "start_value",
        "end_value",
        "absolute_change",
        "percent_change",
    ),
    maximum_claim_class=ClaimClass.DESCRIPTIVE,
    known_limitations=(
        "首尾变化仅描述当前观测区间，不代表长期趋势或因果效应。",
        "未进行季节性、结构突变或统计显著性检验。",
    ),
)


def describe_numeric(frame: pd.DataFrame, metric: str) -> dict[str, float | int | None]:
    if metric not in frame.columns:
        raise KeyError(f"unknown metric column: {metric}")
    values = pd.to_numeric(frame[metric], errors="coerce")
    valid = values.dropna()
    if valid.empty:
        return {
            "count": 0,
            "missing": int(values.isna().sum()),
            "mean": None,
            "minimum": None,
            "maximum": None,
        }
    return {
        "count": int(valid.size),
        "missing": int(values.isna().sum()),
        "mean": float(valid.mean()),
        "minimum": float(valid.min()),
        "maximum": float(valid.max()),
    }


def describe_trend(
    frame: pd.DataFrame,
    metric: str,
    time_field: str,
) -> dict[str, float | int | str | None]:
    if metric not in frame.columns or time_field not in frame.columns:
        raise KeyError("trend fields are not present in the dataset")
    values = pd.to_numeric(frame[metric], errors="coerce")
    times = pd.to_datetime(frame[time_field], errors="coerce", format="mixed")
    paired = pd.DataFrame({"time": times, "value": values}).dropna().sort_values("time")
    if len(paired) < 2 or paired["time"].nunique() < 2:
        raise ValueError("trend description requires at least two ordered observations")
    start = paired.iloc[0]
    end = paired.iloc[-1]
    start_value = float(start["value"])
    end_value = float(end["value"])
    absolute_change = end_value - start_value
    percent_change = (
        (absolute_change / abs(start_value)) * 100.0
        if start_value != 0
        else None
    )
    return {
        "count": int(len(paired)),
        "missing": int(len(frame) - len(paired)),
        "start_time": start["time"].date().isoformat(),
        "end_time": end["time"].date().isoformat(),
        "start_value": start_value,
        "end_value": end_value,
        "absolute_change": float(absolute_change),
        "percent_change": float(percent_change) if percent_change is not None else None,
    }
