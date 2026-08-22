"""Deterministic curve fitting over log-linearized model families.

Descriptive only: fits describe the observed range and never extrapolate
or support causal claims. Three families are compared on the original
scale (power / exponential / logarithmic) via least squares on the
log-transformed linear form.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from data_agent.v2.models import ClaimClass


_FAMILIES = ("power", "exponential", "logarithmic")
_MIN_POINTS = 5
_DAY_PATTERN = re.compile(r"(\d+)")


@dataclass(frozen=True, slots=True)
class CurveFitSpec:
    y_column: str = ""
    x_column: str = ""
    series_columns: tuple[str, ...] = ()
    zero_values: str = "exclude"

    def __post_init__(self) -> None:
        y = str(self.y_column or "").strip()
        x = str(self.x_column or "").strip()
        series = tuple(
            str(item or "").strip() for item in self.series_columns if str(item or "").strip()
        )
        if not series and not (y and x):
            raise ValueError("either series_columns or both x_column and y_column are required")
        if y and series:
            raise ValueError("series_columns and x/y columns are mutually exclusive")
        if str(self.zero_values) not in {"exclude", "keep"}:
            raise ValueError("zero_values must be 'exclude' or 'keep'")
        if len(series) != len(set(series)):
            raise ValueError("series_columns must be unique")
        object.__setattr__(self, "y_column", y)
        object.__setattr__(self, "x_column", x)
        object.__setattr__(self, "series_columns", series)
        object.__setattr__(self, "zero_values", str(self.zero_values))


@dataclass(frozen=True, slots=True)
class CurveFitPoint:
    x: float
    y: float
    n_observed: int
    n_excluded_zeros: int


@dataclass(frozen=True, slots=True)
class CurveFit:
    family: str
    formula: str
    params: dict[str, float]
    r_squared: float
    sse: float
    n_points: int
    mean_residual: float
    max_abs_residual: float


@dataclass(frozen=True, slots=True)
class CurveFitResult:
    status: str
    reason_code: str
    metric: str
    mode: str
    x_label: str
    points: tuple[CurveFitPoint, ...] = ()
    fits: tuple[CurveFit, ...] = ()
    best_family: str = ""
    excluded_families: dict[str, str] = field(default_factory=dict)
    limitations: tuple[str, ...] = ()
    maximum_claim_class: ClaimClass = ClaimClass.DESCRIPTIVE


def _series_x(column: str, index: int) -> tuple[float, str]:
    match = _DAY_PATTERN.search(column)
    if match:
        return float(match.group(1)), f"列名序数（来自 {column}）"
    return float(index), f"列序位置（{index}，列名无数值）"


def _log_linear_fit(
    x: np.ndarray,
    y: np.ndarray,
    *,
    transform_x: str,
    require_positive_y: bool,
) -> tuple[dict[str, float], np.ndarray] | None:
    if require_positive_y and np.any(y <= 0):
        return None
    if np.any(x <= 0):
        return None
    if transform_x == "log":
        design = np.log(x)
    elif transform_x == "identity":
        design = x
    else:
        raise ValueError(f"unknown x transform: {transform_x}")
    if require_positive_y:
        slope, intercept = np.polyfit(design, np.log(y), 1)
        predicted = np.exp(intercept + slope * design)
        return {"slope": float(slope), "intercept": float(intercept)}, predicted
    slope, intercept = np.polyfit(design, y, 1)
    predicted = intercept + slope * design
    return {"slope": float(slope), "intercept": float(intercept)}, predicted


def _fit_families(x: np.ndarray, y: np.ndarray) -> tuple[tuple[CurveFit, ...], dict[str, str]]:
    fits: list[CurveFit] = []
    excluded: dict[str, str] = {}
    candidates = {
        "power": (
            _log_linear_fit(x, y, transform_x="log", require_positive_y=True),
            "y = a·x^b",
        ),
        "exponential": (
            _log_linear_fit(x, y, transform_x="identity", require_positive_y=True),
            "y = a·e^(b·x)",
        ),
        "logarithmic": (
            _log_linear_fit(x, y, transform_x="log", require_positive_y=False),
            "y = a + b·ln(x)",
        ),
    }
    ss_total = float(((y - y.mean()) ** 2).sum())
    for family, (fitted, formula) in candidates.items():
        if fitted is None:
            excluded[family] = "数据不满足该模型族的取值约束（需要 x>0 / y>0）"
            continue
        params, predicted = fitted
        residuals = y - predicted
        sse = float((residuals**2).sum())
        r_squared = 1 - sse / ss_total if ss_total > 0 else 0.0
        if family == "power":
            display = {"a": math.exp(params["intercept"]), "b": params["slope"]}
        elif family == "exponential":
            display = {"a": math.exp(params["intercept"]), "b": params["slope"]}
        else:
            display = {"a": params["intercept"], "b": params["slope"]}
        fits.append(
            CurveFit(
                family=family,
                formula=formula,
                params=display,
                r_squared=float(r_squared),
                sse=sse,
                n_points=int(len(x)),
                mean_residual=float(residuals.mean()),
                max_abs_residual=float(np.abs(residuals).max()),
            )
        )
    fits.sort(key=lambda item: -item.r_squared)
    return tuple(fits), excluded


def analyze_curve_fit(
    frame: pd.DataFrame,
    spec: CurveFitSpec,
) -> CurveFitResult:
    if spec.series_columns:
        missing = sorted(set(spec.series_columns) - set(frame.columns))
        if missing:
            raise KeyError(f"series columns not found: {missing}")
        points: list[CurveFitPoint] = []
        x_mode_labels: list[str] = []
        for index, column in enumerate(spec.series_columns):
            values = pd.to_numeric(frame[column], errors="coerce").dropna()
            excluded_zeros = 0
            if spec.zero_values == "exclude":
                excluded_zeros = int((values == 0).sum())
                values = values[values != 0]
            if values.empty:
                continue
            x_value, label = _series_x(column, index + 1)
            points.append(
                CurveFitPoint(
                    x=x_value,
                    y=float(values.mean()),
                    n_observed=int(len(values)),
                    n_excluded_zeros=excluded_zeros,
                )
            )
            x_mode_labels.append(label)
        mode = "wide_series"
        metric = f"各列均值（{len(spec.series_columns)} 列序列）"
        x_label = x_mode_labels[0] if x_mode_labels else "列序位置"
        zero_disclosure = (
            "宽表序列模式下零值按截断缺失排除（各点排除数见结构化结果）；可用 zero_values=keep 保留。"
            if spec.zero_values == "exclude" and any(p.n_excluded_zeros for p in points)
            else ""
        )
    else:
        missing = sorted({spec.x_column, spec.y_column} - set(frame.columns))
        if missing:
            raise KeyError(f"curve fitting fields not found: {missing}")
        working = pd.DataFrame(
            {
                "x": pd.to_numeric(frame[spec.x_column], errors="coerce"),
                "y": pd.to_numeric(frame[spec.y_column], errors="coerce"),
            }
        ).dropna()
        grouped = working.groupby("x", as_index=False)["y"].mean()
        points = [
            CurveFitPoint(x=float(row.x), y=float(row.y), n_observed=1, n_excluded_zeros=0)
            for row in grouped.itertuples(index=False)
        ]
        mode = "long_columns"
        metric = f"column:{spec.y_column}"
        x_label = f"column:{spec.x_column}"
        zero_disclosure = ""

    limitations = (
        "拟合仅描述当前观测范围，不支持外推；参数为描述性估计，不构成因果或预测断言。",
        "模型族为固定三种（幂律/指数/对数），R² 在原始尺度上比较。",
    )
    if zero_disclosure:
        limitations += (zero_disclosure,)

    if len(points) < _MIN_POINTS:
        return CurveFitResult(
            status="limited",
            reason_code="insufficient_points",
            metric=metric,
            mode=mode,
            x_label=x_label,
            points=tuple(points),
            limitations=limitations + (f"可用拟合点不足（≥{_MIN_POINTS} 个不同 x 才能比较模型族）。",),
        )

    x = np.array([point.x for point in points], dtype=float)
    y = np.array([point.y for point in points], dtype=float)
    fits, excluded = _fit_families(x, y)
    if not fits:
        return CurveFitResult(
            status="limited",
            reason_code="no_applicable_family",
            metric=metric,
            mode=mode,
            x_label=x_label,
            points=tuple(points),
            excluded_families=excluded,
            limitations=limitations + ("三种模型族的取值约束均不满足。",),
        )
    return CurveFitResult(
        status="supported" if fits[0].r_squared >= 0.5 else "null_result",
        reason_code=(
            "curve_described" if fits[0].r_squared >= 0.5 else "no_family_describes_the_series"
        ),
        metric=metric,
        mode=mode,
        x_label=x_label,
        points=tuple(points),
        fits=fits,
        best_family=fits[0].family,
        excluded_families=excluded,
        limitations=limitations,
    )
