from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy import stats

from data_agent.v2.models import ClaimClass


@dataclass(frozen=True, slots=True)
class GroupComparisonSpec:
    metric: str
    group: str
    analysis_unit: str
    alpha: float = 0.05

    def __post_init__(self) -> None:
        metric = str(self.metric or "").strip()
        group = str(self.group or "").strip()
        unit = str(self.analysis_unit or "").strip()
        if not metric or not group or not unit:
            raise ValueError("metric, group, and analysis_unit are required")
        if len({metric, group, unit}) != 3:
            raise ValueError("metric, group, and analysis_unit must be distinct")
        if not 0 < float(self.alpha) < 1:
            raise ValueError("alpha must be between 0 and 1")
        object.__setattr__(self, "metric", metric)
        object.__setattr__(self, "group", group)
        object.__setattr__(self, "analysis_unit", unit)


@dataclass(frozen=True, slots=True)
class GroupSummary:
    group_value: str
    sample_size: int
    mean: float
    median: float
    standard_deviation: float


@dataclass(frozen=True, slots=True)
class GroupComparisonResult:
    status: str
    reason_code: str
    metric: str
    group_field: str
    group_order: tuple[str, ...] = ()
    groups: tuple[GroupSummary, ...] = ()
    difference: float | None = None
    standard_error: float | None = None
    confidence_low: float | None = None
    confidence_high: float | None = None
    p_value: float | None = None
    welch_degrees_of_freedom: float | None = None
    hedges_g: float | None = None
    mann_whitney_p_value: float | None = None
    source_rows: int = 0
    complete_case_rows: int = 0
    dropped_rows: int = 0
    effective_units: int = 0
    alpha: float = 0.05
    maximum_claim_class: ClaimClass = ClaimClass.INFERENTIAL
    limitations: tuple[str, ...] = field(default_factory=tuple)


def _limited(
    frame: pd.DataFrame,
    spec: GroupComparisonSpec,
    *,
    reason_code: str,
    complete_rows: int,
    effective_units: int,
    groups: tuple[GroupSummary, ...] = (),
) -> GroupComparisonResult:
    return GroupComparisonResult(
        status="limited",
        reason_code=reason_code,
        metric=spec.metric,
        group_field=spec.group,
        group_order=tuple(item.group_value for item in groups),
        groups=groups,
        source_rows=len(frame),
        complete_case_rows=complete_rows,
        dropped_rows=len(frame) - complete_rows,
        effective_units=effective_units,
        alpha=spec.alpha,
        maximum_claim_class=ClaimClass.ASSOCIATIONAL,
        limitations=(
            "当前数据条件不足以支持可靠的双组均值推断。",
            "分组差异不识别组别对指标的因果效应。",
        ),
    )


def analyze_group_comparison(
    frame: pd.DataFrame,
    spec: GroupComparisonSpec,
) -> GroupComparisonResult:
    missing = sorted({spec.metric, spec.group, spec.analysis_unit} - set(frame.columns))
    if missing:
        raise KeyError(f"group comparison fields not found: {missing}")
    working = pd.DataFrame(
        {
            spec.metric: pd.to_numeric(frame[spec.metric], errors="coerce"),
            spec.group: frame[spec.group].astype("string"),
            spec.analysis_unit: frame[spec.analysis_unit].astype("string"),
        }
    ).replace([np.inf, -np.inf], np.nan).dropna()
    complete_rows = len(working)
    effective_units = int(working[spec.analysis_unit].nunique(dropna=True))
    if working[spec.analysis_unit].duplicated().any():
        return _limited(
            frame,
            spec,
            reason_code="repeated_analysis_units",
            complete_rows=complete_rows,
            effective_units=effective_units,
        )
    group_values = tuple(sorted(str(item) for item in working[spec.group].unique()))
    if len(group_values) != 2:
        return _limited(
            frame,
            spec,
            reason_code="requires_exactly_two_groups",
            complete_rows=complete_rows,
            effective_units=effective_units,
        )
    samples = [
        working.loc[working[spec.group].astype(str) == group_value, spec.metric].to_numpy(
            dtype=float
        )
        for group_value in group_values
    ]
    summaries = tuple(
        GroupSummary(
            group_value=group_value,
            sample_size=len(values),
            mean=float(np.mean(values)) if len(values) else float("nan"),
            median=float(np.median(values)) if len(values) else float("nan"),
            standard_deviation=float(np.std(values, ddof=1)) if len(values) > 1 else float("nan"),
        )
        for group_value, values in zip(group_values, samples, strict=True)
    )
    if any(len(values) < 2 for values in samples):
        return _limited(
            frame,
            spec,
            reason_code="insufficient_group_degrees_of_freedom",
            complete_rows=complete_rows,
            effective_units=effective_units,
            groups=summaries,
        )
    first, second = samples
    variance_first = float(np.var(first, ddof=1))
    variance_second = float(np.var(second, ddof=1))
    if variance_first == 0 and variance_second == 0:
        return _limited(
            frame,
            spec,
            reason_code="zero_within_group_variance",
            complete_rows=complete_rows,
            effective_units=effective_units,
            groups=summaries,
        )
    difference = float(np.mean(second) - np.mean(first))
    first_term = variance_first / len(first)
    second_term = variance_second / len(second)
    standard_error = math.sqrt(first_term + second_term)
    denominator = (first_term**2 / (len(first) - 1)) + (
        second_term**2 / (len(second) - 1)
    )
    degrees = (first_term + second_term) ** 2 / denominator
    critical = float(stats.t.ppf(1 - spec.alpha / 2, degrees))
    low = difference - critical * standard_error
    high = difference + critical * standard_error
    t_value = difference / standard_error
    p_value = float(2 * stats.t.sf(abs(t_value), degrees))
    pooled_df = len(first) + len(second) - 2
    pooled_sd = math.sqrt(
        ((len(first) - 1) * variance_first + (len(second) - 1) * variance_second)
        / pooled_df
    )
    correction = 1 - (3 / (4 * pooled_df - 1)) if pooled_df > 1 else 1.0
    hedges_g = (difference / pooled_sd) * correction if pooled_sd else float("nan")
    mann_whitney = stats.mannwhitneyu(first, second, alternative="two-sided", method="auto")
    supported = p_value < spec.alpha and (low > 0 or high < 0)
    return GroupComparisonResult(
        status="supported" if supported else "null_result",
        reason_code=(
            "reliable_mean_difference" if supported else "no_reliable_mean_difference"
        ),
        metric=spec.metric,
        group_field=spec.group,
        group_order=group_values,
        groups=summaries,
        difference=difference,
        standard_error=standard_error,
        confidence_low=float(low),
        confidence_high=float(high),
        p_value=p_value,
        welch_degrees_of_freedom=float(degrees),
        hedges_g=float(hedges_g),
        mann_whitney_p_value=float(mann_whitney.pvalue),
        source_rows=len(frame),
        complete_case_rows=complete_rows,
        dropped_rows=len(frame) - complete_rows,
        effective_units=effective_units,
        alpha=spec.alpha,
        maximum_claim_class=ClaimClass.INFERENTIAL,
        limitations=(
            "Welch 推断依赖独立观测与样本对目标总体具有可解释代表性。",
            "观察性组间差异不识别组别对指标的因果效应。",
        ),
    )
