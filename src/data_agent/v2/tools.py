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
