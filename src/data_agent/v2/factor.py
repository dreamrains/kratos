from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.stats.multitest import multipletests
from statsmodels.stats.outliers_influence import variance_inflation_factor

from data_agent.v2.models import ClaimClass


@dataclass(frozen=True, slots=True)
class FactorAnalysisSpec:
    target: str
    features: tuple[str, ...]
    analysis_unit: str
    time_field: str = ""
    alpha: float = 0.05

    def __post_init__(self) -> None:
        target = str(self.target or "").strip()
        unit = str(self.analysis_unit or "").strip()
        time_field = str(self.time_field or "").strip()
        features = tuple(
            str(item or "").strip() for item in self.features if str(item or "").strip()
        )
        if not target or not unit or not features:
            raise ValueError("target, features, and analysis_unit are required")
        if len(features) != len(set(features)):
            raise ValueError("features must be unique")
        if target in features or unit in features:
            raise ValueError("target and analysis_unit cannot also be features")
        if time_field and time_field in {target, unit, *features}:
            raise ValueError("time_field must have a distinct field identity")
        if not 0 < float(self.alpha) < 1:
            raise ValueError("alpha must be between 0 and 1")
        object.__setattr__(self, "target", target)
        object.__setattr__(self, "features", features)
        object.__setattr__(self, "analysis_unit", unit)
        object.__setattr__(self, "time_field", time_field)


@dataclass(frozen=True, slots=True)
class FactorEstimate:
    feature: str
    coefficient: float
    standard_error: float
    confidence_low: float
    confidence_high: float
    p_value: float
    p_adjusted: float
    vif: float
    reliable: bool


@dataclass(frozen=True, slots=True)
class FactorAnalysisResult:
    status: str
    reason_code: str
    target: str
    tested_features: tuple[str, ...]
    coefficients: tuple[FactorEstimate, ...] = ()
    reliable_factors: tuple[FactorEstimate, ...] = ()
    excluded_features: dict[str, str] = field(default_factory=dict)
    unstable_features: tuple[str, ...] = ()
    complete_case_rows: int = 0
    source_rows: int = 0
    effective_units: int = 0
    covariance_method: str = ""
    time_controlled: bool = False
    alpha: float = 0.05
    maximum_claim_class: ClaimClass = ClaimClass.INFERENTIAL
    limitations: tuple[str, ...] = ()


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    return pd.to_numeric(frame[column], errors="coerce").astype(float)


def _near_identity(target: pd.Series, candidate: pd.Series) -> bool:
    paired = pd.DataFrame({"target": target, "candidate": candidate}).replace(
        [np.inf, -np.inf], np.nan
    ).dropna()
    if len(paired) < 6:
        return False
    return bool(
        np.allclose(
            paired["target"].to_numpy(),
            paired["candidate"].to_numpy(),
            rtol=1e-8,
            atol=1e-10,
        )
    )


def _identity_exclusions(
    frame: pd.DataFrame,
    target: str,
    features: tuple[str, ...],
) -> dict[str, str]:
    target_values = _numeric(frame, target)
    numeric = {feature: _numeric(frame, feature) for feature in features}
    excluded: dict[str, str] = {}
    for feature, values in numeric.items():
        if _near_identity(target_values, values):
            excluded[feature] = "target_equivalent"

    remaining = [feature for feature in features if feature not in excluded]
    for left, right in itertools.combinations(remaining, 2):
        left_values = numeric[left]
        right_values = numeric[right]
        candidates = {
            "add": left_values + right_values,
            "multiply": left_values * right_values,
            "subtract": left_values - right_values,
            "reverse_subtract": right_values - left_values,
            "divide": left_values / right_values.replace(0, np.nan),
            "reverse_divide": right_values / left_values.replace(0, np.nan),
        }
        matched_operation = next(
            (
                operation
                for operation, candidate in candidates.items()
                if _near_identity(target_values, candidate)
            ),
            "",
        )
        if matched_operation:
            reason = f"mathematical_identity:{matched_operation}"
            excluded[left] = reason
            excluded[right] = reason
    return excluded


def _feature_vifs(design: pd.DataFrame, features: list[str]) -> dict[str, float]:
    if len(design.columns) == 1:
        return {features[0]: 1.0}
    matrix = sm.add_constant(design, has_constant="add").to_numpy(dtype=float)
    names = ["const", *design.columns]
    values: dict[str, float] = {}
    for feature in features:
        index = names.index(feature)
        with np.errstate(divide="ignore", invalid="ignore"):
            vif = float(variance_inflation_factor(matrix, index))
        values[feature] = vif if math.isfinite(vif) else float("inf")
    return values


def _base_result(
    *,
    spec: FactorAnalysisSpec,
    frame: pd.DataFrame,
    status: str,
    reason_code: str,
    excluded: dict[str, str],
    complete_rows: int,
    effective_units: int,
    limitations: tuple[str, ...],
    maximum_claim_class: ClaimClass = ClaimClass.INFERENTIAL,
) -> FactorAnalysisResult:
    return FactorAnalysisResult(
        status=status,
        reason_code=reason_code,
        target=spec.target,
        tested_features=tuple(feature for feature in spec.features if feature not in excluded),
        excluded_features=dict(excluded),
        complete_case_rows=complete_rows,
        source_rows=len(frame),
        effective_units=effective_units,
        covariance_method="",
        time_controlled=bool(spec.time_field),
        alpha=spec.alpha,
        maximum_claim_class=maximum_claim_class,
        limitations=limitations,
    )


def analyze_factor_relationships(
    frame: pd.DataFrame,
    spec: FactorAnalysisSpec,
) -> FactorAnalysisResult:
    required = {spec.target, spec.analysis_unit, *spec.features}
    if spec.time_field:
        required.add(spec.time_field)
    missing = sorted(required - set(frame.columns))
    if missing:
        raise KeyError(f"factor analysis fields not found: {missing}")

    limitations = (
        "结果描述当前数据和模型中的调整后统计关联，不识别因果效应。",
        "系数依赖已提供因素、函数形式、缺失值处理和观测范围。",
    )
    excluded = _identity_exclusions(frame, spec.target, spec.features)
    candidate_features: list[str] = []
    for feature in spec.features:
        if feature in excluded:
            continue
        values = _numeric(frame, feature)
        if values.notna().sum() < 2:
            excluded[feature] = "insufficient_numeric_values"
        elif values.nunique(dropna=True) < 2:
            excluded[feature] = "constant_feature"
        else:
            candidate_features.append(feature)

    unit_values = frame[spec.analysis_unit].astype("string")
    effective_units = int(unit_values.nunique(dropna=True))
    repeated_units = bool(unit_values.dropna().duplicated().any())
    if repeated_units and not spec.time_field:
        return _base_result(
            spec=spec,
            frame=frame,
            status="limited",
            reason_code="repeated_units_require_time_field",
            excluded=excluded,
            complete_rows=0,
            effective_units=effective_units,
            limitations=limitations
            + ("分析单位存在重复观测，但没有时间字段，无法可靠处理观测相关性。",),
            maximum_claim_class=ClaimClass.ASSOCIATIONAL,
        )

    working = pd.DataFrame(
        {
            spec.target: _numeric(frame, spec.target),
            spec.analysis_unit: unit_values,
            **{feature: _numeric(frame, feature) for feature in candidate_features},
        }
    )
    if spec.time_field:
        parsed_time = pd.to_datetime(frame[spec.time_field], errors="coerce", format="mixed")
        working[spec.time_field] = parsed_time
    working = working.replace([np.inf, -np.inf], np.nan).dropna()
    complete_rows = len(working)
    effective_units = int(working[spec.analysis_unit].nunique(dropna=True))

    if not candidate_features or complete_rows == 0:
        return _base_result(
            spec=spec,
            frame=frame,
            status="null_result",
            reason_code="no_eligible_features",
            excluded=excluded,
            complete_rows=complete_rows,
            effective_units=effective_units,
            limitations=limitations,
        )
    if working[spec.target].nunique(dropna=True) < 2:
        return _base_result(
            spec=spec,
            frame=frame,
            status="null_result",
            reason_code="target_has_no_variation",
            excluded=excluded,
            complete_rows=complete_rows,
            effective_units=effective_units,
            limitations=limitations,
        )

    design = working[candidate_features].copy()
    design = (design - design.mean()) / design.std(ddof=0)
    time_controlled = False
    if spec.time_field:
        time_ns = working[spec.time_field].astype("int64").astype(float)
        time_std = float(time_ns.std(ddof=0))
        if time_std > 0:
            design["__time_trend__"] = (time_ns - float(time_ns.mean())) / time_std
            time_controlled = True

    vifs = _feature_vifs(design, candidate_features)
    unstable_features = tuple(
        feature for feature in candidate_features if vifs.get(feature, float("inf")) >= 10
    )
    stable_features = [feature for feature in candidate_features if feature not in unstable_features]
    if not stable_features:
        return FactorAnalysisResult(
            status="limited",
            reason_code="multicollinearity_prevents_attribution",
            target=spec.target,
            tested_features=tuple(candidate_features),
            excluded_features=excluded,
            unstable_features=unstable_features,
            complete_case_rows=complete_rows,
            source_rows=len(frame),
            effective_units=effective_units,
            time_controlled=time_controlled,
            alpha=spec.alpha,
            maximum_claim_class=ClaimClass.ASSOCIATIONAL,
            limitations=limitations + ("候选因素高度共线，无法稳定区分各因素关系。",),
        )

    model_columns = list(stable_features)
    if time_controlled:
        model_columns.append("__time_trend__")
    residual_degrees = complete_rows - len(model_columns) - 1
    if residual_degrees < max(3, len(stable_features)):
        return FactorAnalysisResult(
            status="limited",
            reason_code="insufficient_model_degrees_of_freedom",
            target=spec.target,
            tested_features=tuple(candidate_features),
            excluded_features=excluded,
            unstable_features=unstable_features,
            complete_case_rows=complete_rows,
            source_rows=len(frame),
            effective_units=effective_units,
            time_controlled=time_controlled,
            alpha=spec.alpha,
            maximum_claim_class=ClaimClass.ASSOCIATIONAL,
            limitations=limitations + ("当前完整案例不足以支持该模型复杂度的稳定不确定性估计。",),
        )
    cluster_degrees = effective_units - 1
    if repeated_units and cluster_degrees < max(3, len(model_columns)):
        return FactorAnalysisResult(
            status="limited",
            reason_code="insufficient_cluster_degrees_of_freedom",
            target=spec.target,
            tested_features=tuple(candidate_features),
            excluded_features=excluded,
            unstable_features=unstable_features,
            complete_case_rows=complete_rows,
            source_rows=len(frame),
            effective_units=effective_units,
            time_controlled=time_controlled,
            alpha=spec.alpha,
            maximum_claim_class=ClaimClass.ASSOCIATIONAL,
            limitations=limitations + ("独立分析单位不足以支持聚类稳健推断。",),
        )

    y = working[spec.target]
    y = (y - y.mean()) / y.std(ddof=0)
    x = sm.add_constant(design[model_columns], has_constant="add")
    base_model = sm.OLS(y, x)
    if repeated_units:
        model = base_model.fit(
            cov_type="cluster",
            cov_kwds={"groups": working[spec.analysis_unit].astype(str), "use_correction": True},
            use_t=True,
        )
        covariance_method = "cluster"
    else:
        model = base_model.fit(cov_type="HC3", use_t=True)
        covariance_method = "HC3"

    raw_p_values = np.array([float(model.pvalues[feature]) for feature in stable_features])
    adjusted = multipletests(raw_p_values, alpha=spec.alpha, method="holm")[1]
    intervals = model.conf_int(alpha=spec.alpha)
    coefficients: list[FactorEstimate] = []
    for index, feature in enumerate(stable_features):
        low = float(intervals.loc[feature, 0])
        high = float(intervals.loc[feature, 1])
        p_adjusted = float(adjusted[index])
        reliable = p_adjusted < spec.alpha and (low > 0 or high < 0)
        coefficients.append(
            FactorEstimate(
                feature=feature,
                coefficient=float(model.params[feature]),
                standard_error=float(model.bse[feature]),
                confidence_low=low,
                confidence_high=high,
                p_value=float(raw_p_values[index]),
                p_adjusted=p_adjusted,
                vif=float(vifs[feature]),
                reliable=reliable,
            )
        )
    reliable_factors = tuple(
        sorted(
            (item for item in coefficients if item.reliable),
            key=lambda item: abs(item.coefficient),
            reverse=True,
        )
    )
    return FactorAnalysisResult(
        status="supported" if reliable_factors else "null_result",
        reason_code=("adjusted_associations_found" if reliable_factors else "no_adjusted_association"),
        target=spec.target,
        tested_features=tuple(candidate_features),
        coefficients=tuple(coefficients),
        reliable_factors=reliable_factors,
        excluded_features=excluded,
        unstable_features=unstable_features,
        complete_case_rows=complete_rows,
        source_rows=len(frame),
        effective_units=effective_units,
        covariance_method=covariance_method,
        time_controlled=time_controlled,
        alpha=spec.alpha,
        maximum_claim_class=ClaimClass.INFERENTIAL,
        limitations=limitations
        + (("模型同时控制线性时间趋势。",) if time_controlled else ())
        + (("标准误按分析单位聚类。",) if repeated_units else ()),
    )
