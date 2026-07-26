"""L3: 统计推断工具。"""

from __future__ import annotations

import json
import math
import warnings
from typing import Any, Literal

import numpy as np
import pandas as pd
from scipy import stats as sp_stats

from data_agent.session.workspace import workspace
from data_agent.tools._utils import get_df
from data_agent.tools.registry import registry


def _mean_difference_interval(
    left: np.ndarray,
    right: np.ndarray,
    *,
    equal_var: bool,
    level: float = 0.95,
) -> dict[str, float | str]:
    """Return a two-sided interval for right mean minus left mean."""

    n_left, n_right = len(left), len(right)
    var_left = float(np.var(left, ddof=1))
    var_right = float(np.var(right, ddof=1))
    difference = float(np.mean(right) - np.mean(left))
    if equal_var:
        degrees = n_left + n_right - 2
        pooled = ((n_left - 1) * var_left + (n_right - 1) * var_right) / degrees
        standard_error = float(np.sqrt(pooled * (1 / n_left + 1 / n_right)))
        interval_method = "student_mean_difference"
    else:
        left_term = var_left / n_left
        right_term = var_right / n_right
        standard_error = float(np.sqrt(left_term + right_term))
        denominator = (
            (left_term**2 / (n_left - 1))
            + (right_term**2 / (n_right - 1))
        )
        degrees = (
            (left_term + right_term) ** 2 / denominator
            if denominator > 0
            else n_left + n_right - 2
        )
        interval_method = "welch_mean_difference"
    critical = float(sp_stats.t.ppf((1 + level) / 2, degrees)) if standard_error > 0 else 0.0
    margin = critical * standard_error
    return {
        "level": level,
        "lower": round(difference - margin, 6),
        "upper": round(difference + margin, 6),
        "method": interval_method,
    }


def _rank_biserial_effect(left: np.ndarray, right: np.ndarray) -> float:
    """Return stochastic superiority of right over left on a [-1, 1] scale."""

    u_left = float(sp_stats.mannwhitneyu(left, right, alternative="two-sided").statistic)
    return float(1 - (2 * u_left / (len(left) * len(right))))


def _rank_biserial_interval(
    left: np.ndarray,
    right: np.ndarray,
    *,
    level: float = 0.95,
) -> dict[str, float | str]:
    """Return a deterministic percentile-bootstrap interval for rank-biserial correlation."""

    rng = np.random.default_rng(0)
    estimates = [
        _rank_biserial_effect(
            rng.choice(left, size=len(left), replace=True),
            rng.choice(right, size=len(right), replace=True),
        )
        for _ in range(600)
    ]
    alpha = (1 - level) / 2
    lower, upper = np.quantile(estimates, [alpha, 1 - alpha])
    point = _rank_biserial_effect(left, right)
    return {
        "level": level,
        "lower": round(float(min(lower, point)), 6),
        "upper": round(float(max(upper, point)), 6),
        "method": "bootstrap_rank_biserial_correlation",
    }


def _cramers_v(contingency: np.ndarray) -> float:
    statistic = float(sp_stats.chi2_contingency(contingency, correction=False)[0])
    total = float(contingency.sum())
    scale = min(contingency.shape[0] - 1, contingency.shape[1] - 1)
    return float(np.sqrt(statistic / (total * scale))) if total > 0 and scale > 0 else 0.0


def _cramers_v_interval(contingency: np.ndarray) -> dict[str, float | str]:
    """Return a deterministic parametric-bootstrap interval for Cramer's V."""

    total = int(contingency.sum())
    probabilities = contingency.reshape(-1).astype(float) / total
    rng = np.random.default_rng(0)
    estimates: list[float] = []
    for sampled in rng.multinomial(total, probabilities, size=400):
        table = sampled.reshape(contingency.shape)
        if bool((table.sum(axis=0) == 0).any()) or bool((table.sum(axis=1) == 0).any()):
            continue
        estimates.append(_cramers_v(table))
    if not estimates:
        point = _cramers_v(contingency)
        lower = upper = point
    else:
        lower, upper = np.quantile(estimates, [0.025, 0.975])
    return {
        "level": 0.95,
        "lower": round(float(lower), 6),
        "upper": round(float(upper), 6),
        "method": "parametric_bootstrap_cramers_v",
    }


def _comparison_missingness(df: pd.DataFrame, *columns: str) -> dict[str, dict[str, float | int]]:
    return {
        column: {
            "missing_count": int(df[column].isna().sum()),
            "missing_rate": float(df[column].isna().mean()) if len(df) else 0.0,
        }
        for column in columns
    }


@registry.register(
    name="ab_test",
    description=(
        "进行 A/B 测试统计检验。比较两组之间的指标差异。"
        "auto 模式自动判断正态性并选择检验方法，附加 Levene 方差齐性检验。"
    ),
    schema_overrides={
        "name": {"description": "数据集名称"},
        "group_col": {"description": "分组列名（二值列，区分实验组和对照组）"},
        "metric_col": {"description": "指标列名"},
        "method": {"description": "检验方法", "enum": ["auto", "ttest", "mannwhitneyu", "chi2"]},
    },
)
def ab_test(name: str, group_col: str, metric_col: str, method: str = "auto") -> str:
    df, err = get_df(name)
    if err:
        return err

    if group_col not in df.columns or metric_col not in df.columns:
        return f"Error: 列不存在。可用列: {list(df.columns)}"

    groups = df[group_col].dropna().unique()
    if len(groups) < 2:
        return f"Error: 分组列只有 {len(groups)} 个唯一值，至少需要 2 个"
    if len(groups) > 2:
        return f"Error: A/B 比较要求恰好 2 个分组，当前有 {len(groups)} 个"

    g1_name, g2_name = str(groups[0]), str(groups[1])

    # chi2 直接使用列联表，不需要 float 转换
    if method == "chi2":
        contingency = pd.crosstab(df[group_col], df[metric_col])
        if contingency.size < 4:
            return "Error: chi2 检验需要每组至少 2 个类别"
        stat, p_value, dof, expected = sp_stats.chi2_contingency(contingency)
        counts = {
            str(group): int(contingency.loc[group].sum())
            for group in groups
        }
        effect = _cramers_v(contingency.to_numpy())
        minimum_expected = float(np.min(expected))
        result = {
            "group_col": group_col,
            "metric_col": metric_col,
            "groups": {g1_name: {"n": int(contingency.loc[groups[0]].sum())},
                       g2_name: {"n": int(contingency.loc[groups[1]].sum())}},
            "method": "chi2",
            "effective_sample_size": {
                "total": int(contingency.to_numpy().sum()),
                "groups": counts,
            },
            "denominator": counts,
            "missingness": _comparison_missingness(df, group_col, metric_col),
            "estimand": {
                "metric": metric_col,
                "aggregation": "categorical_association",
                "contrast": "two_group_distribution_difference",
            },
            "effect_estimate": {
                "value": round(effect, 6),
                "metric": "cramers_v",
            },
            "confidence_interval": _cramers_v_interval(contingency.to_numpy()),
            "test": {
                "statistic": round(float(stat), 4),
                "p_value": round(float(p_value), 6),
                "dof": int(dof),
                "significant": bool(p_value < 0.05),
            },
            "assumptions": [
                {
                    "name": "independent_observations",
                    "status": "assumed",
                    "reason": "Independence and sampling-unit validity must be confirmed from the study design.",
                },
                {
                    "name": "method_appropriate_for_design",
                    "status": "passed",
                    "reason": "The chi-square calculation matches the declared independent two-group categorical design.",
                },
                {
                    "name": "expected_cell_counts",
                    "status": "passed" if minimum_expected >= 5 else "failed",
                    "reason": f"Minimum expected cell count is {minimum_expected:.4f}.",
                },
            ],
            "sample_adequacy": {
                "status": "adequate_with_limits" if minimum_expected >= 5 else "inadequate",
                "design": "independent_groups_categorical",
                "reason": (
                    "Expected cell counts support the chi-square approximation, but independence "
                    "and population representativeness remain design assumptions."
                    if minimum_expected >= 5
                    else "At least one expected cell count is below 5; the chi-square approximation is unreliable."
                ),
            },
        }
        return json.dumps(result, ensure_ascii=False, indent=2)

    try:
        g1 = df[df[group_col] == groups[0]][metric_col].dropna().values.astype(float)
        g2 = df[df[group_col] == groups[1]][metric_col].dropna().values.astype(float)
    except (ValueError, TypeError) as e:
        return json.dumps({
            "error": f"指标列 '{metric_col}' 包含非数值数据，无法进行统计检验",
            "error_type": "non_numeric_metric",
            "detail": str(e),
        }, ensure_ascii=False)

    if len(g1) < 2 or len(g2) < 2:
        return "Error: 每组至少需要 2 个有效数据点"

    # Levene 方差齐性检验
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        levene_stat, levene_p = sp_stats.levene(g1, g2)
    levene_estimable = bool(np.isfinite(levene_stat) and np.isfinite(levene_p))
    equal_var = bool(levene_estimable and levene_p > 0.05)

    # 自动选择检验方法
    if method == "auto":
        # 正态性检验 (Shapiro-Wilk, n < 5000)
        g1_normal = True
        g2_normal = True
        if np.ptp(g1) == 0:
            g1_normal = False
        elif len(g1) < 5000:
            _, p1 = sp_stats.shapiro(g1[:5000] if len(g1) > 5000 else g1)
            g1_normal = p1 > 0.05
        if np.ptp(g2) == 0:
            g2_normal = False
        elif len(g2) < 5000:
            _, p2 = sp_stats.shapiro(g2[:5000] if len(g2) > 5000 else g2)
            g2_normal = p2 > 0.05

        if g1_normal and g2_normal:
            method = "ttest"
        else:
            method = "mannwhitneyu"

    result = {
        "group_col": group_col,
        "metric_col": metric_col,
        "groups": {
            g1_name: {"n": len(g1), "mean": round(float(np.mean(g1)), 4), "std": round(float(np.std(g1)), 4)},
            g2_name: {"n": len(g2), "mean": round(float(np.mean(g2)), 4), "std": round(float(np.std(g2)), 4)},
        },
        "method": method,
        "effective_sample_size": {
            "total": len(g1) + len(g2),
            "groups": {g1_name: len(g1), g2_name: len(g2)},
        },
        "denominator": {g1_name: len(g1), g2_name: len(g2)},
        "missingness": _comparison_missingness(df, group_col, metric_col),
        "sample_adequacy": {
            "status": "adequate_with_limits",
            "design": "independent_groups",
            "reason": (
                f"The test is computable with group sizes {len(g1)} and {len(g2)}, but independence, "
                "sampling-unit validity, and population representativeness require design evidence."
            ),
        },
    }

    diff = float(np.mean(g2) - np.mean(g1))
    result["difference"] = {
        "absolute": round(diff, 4),
        "relative_pct": round(diff / abs(np.mean(g1)) * 100, 2) if np.mean(g1) != 0 else None,
        "cohens_d": round(diff / np.sqrt((np.std(g1, ddof=1)**2 + np.std(g2, ddof=1)**2) / 2), 4)
                     if (np.std(g1) + np.std(g2)) > 0 else None,
    }
    if method == "mannwhitneyu":
        rank_effect = _rank_biserial_effect(g1, g2)
        result["estimand"] = {
            "metric": metric_col,
            "aggregation": "pairwise_probability",
            "contrast": "group_2_stochastic_superiority_minus_reverse",
        }
        result["effect_estimate"] = {
            "value": round(rank_effect, 8),
            "metric": "rank_biserial_correlation",
        }
        result["confidence_interval"] = _rank_biserial_interval(g1, g2)
    else:
        result["estimand"] = {
            "metric": metric_col,
            "aggregation": "mean",
            "contrast": "group_2_minus_group_1",
        }
        result["effect_estimate"] = {
            "value": round(diff, 8),
            "metric": "mean_difference",
        }
        result["confidence_interval"] = _mean_difference_interval(
            g1,
            g2,
            equal_var=equal_var,
        )
    result["assumptions"] = [
        {
            "name": "independent_observations",
            "status": "assumed",
            "reason": "Independence and sampling-unit validity must be confirmed from the study design.",
        },
        {
            "name": "method_appropriate_for_design",
            "status": "passed",
            "reason": (
                "The calculation matches the declared independent two-group design; "
                "study-level independence remains a disclosed assumption."
            ),
        },
    ]
    if method == "ttest":
        result["assumptions"].append({
            "name": "variance_handling",
            "status": "passed" if levene_estimable else "disclosed",
            "reason": (
                "Student variance pooling is used after the Levene check."
                if equal_var
                else (
                    "Welch variance handling is used because equal variance was not supported."
                    if levene_estimable
                    else "Levene's test was not estimable; Welch variance handling is used without pooling."
                )
            ),
        })
    else:
        result["assumptions"].append({
            "name": "interpretation_scope",
            "status": "disclosed",
            "reason": (
                "The Mann-Whitney test, rank-biserial effect, and bootstrap interval assess "
                "stochastic ordering rather than a difference in group means."
            ),
        })

    # 方差齐性检验
    if levene_estimable:
        result["levene_test"] = {
            "statistic": round(float(levene_stat), 4),
            "p_value": round(float(levene_p), 6),
            "equal_variance": equal_var,
        }
    else:
        result["levene_test"] = {
            "status": "not_estimable",
            "reason": "Levene's variance test is undefined for the observed within-group deviations.",
        }

    if method == "ttest":
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            stat, p_value = sp_stats.ttest_ind(g1, g2, equal_var=equal_var)
        if np.isfinite(stat) and np.isfinite(p_value):
            result["test"] = {
                "statistic": round(float(stat), 4),
                "p_value": round(float(p_value), 6),
                "significant": bool(p_value < 0.05),
            }
        else:
            reason = "Both groups have zero within-group variance; a t-test is undefined."
            result["test"] = {"status": "not_estimable", "reason": reason}
            result["sample_adequacy"] = {
                "status": "not_estimable",
                "design": "independent_groups",
                "reason": reason,
            }
            method_check = next(
                item for item in result["assumptions"]
                if item["name"] == "method_appropriate_for_design"
            )
            method_check.update({"status": "failed", "reason": reason})
    elif method == "mannwhitneyu":
        stat, p_value = sp_stats.mannwhitneyu(g1, g2, alternative="two-sided")
        result["test"] = {
            "statistic": round(float(stat), 4),
            "p_value": round(float(p_value), 6),
            "significant": bool(p_value < 0.05),
        }
    return json.dumps(result, ensure_ascii=False, indent=2)


@registry.register(
    name="causal_analysis",
    description=(
        "因果分析：DID（双重差分）。"
        "参数顺序：name → treatment_col（处理组标识列，0=控制组/1=处理组）→ "
        "outcome_col（结果变量列）→ target_col（outcome_col 的别名）→ "
        "time_col（期次列，0=预处理/1=处理后）→ method。"
        "示例：causal_analysis(name='数据集', treatment_col='group', outcome_col='revenue', time_col='period')"
    ),
    schema_overrides={
        "name": {"description": "数据集名称"},
        "treatment_col": {"description": "处理组标识列（0=控制组/1=处理组）"},
        "outcome_col": {"description": "结果变量列"},
        "time_col": {"description": "期次列（0=预处理/1=处理后）"},
        "method": {"description": "分析方法", "enum": ["did"]},
    },
)
def causal_analysis(name: str, treatment_col: str, outcome_col: str = "", target_col: str = "", time_col: str = "", method: str = "did") -> str:
    # 兼容 outcome_col 和 target_col 两种命名
    outcome = target_col or outcome_col
    if not outcome:
        return "Error: 请指定 outcome_col 或 target_col 参数"

    df, err = get_df(name)
    if err:
        return err

    if method == "did":
        if not time_col:
            return "Error: DID 方法需要 time_col（时间/期次列）"
        required = [treatment_col, outcome, time_col]
        missing = [c for c in required if c not in df.columns]
        if missing:
            return f"Error: 列不存在: {missing}"

        df = df.dropna(subset=required).copy()
        df[treatment_col] = df[treatment_col].astype(int)
        df[time_col] = df[time_col].astype(int)

        # 四组均值和标准差
        groups = {}
        for t in [0, 1]:
            for period in [0, 1]:
                mask = (df[treatment_col] == t) & (df[time_col] == period)
                vals = df.loc[mask, outcome].dropna().values.astype(float)
                groups[(t, period)] = {
                    "mean": float(np.mean(vals)) if len(vals) > 0 else 0,
                    "std": float(np.std(vals, ddof=1)) if len(vals) > 1 else 0,
                    "n": len(vals),
                }

        # DID = (T1_post - T1_pre) - (T0_post - T0_pre)
        treat_diff = groups[(1, 1)]["mean"] - groups[(1, 0)]["mean"]
        control_diff = groups[(0, 1)]["mean"] - groups[(0, 0)]["mean"]
        did_effect = treat_diff - control_diff

        # 标准误（合并方差公式）
        def _se(g):
            return g["std"] / np.sqrt(g["n"]) if g["n"] > 0 else 0

        se_did = np.sqrt(
            _se(groups[(1, 1)])**2 + _se(groups[(1, 0)])**2 +
            _se(groups[(0, 1)])**2 + _se(groups[(0, 0)])**2
        )

        # 置信区间和 t 检验
        z_95 = 1.96
        ci_lower = did_effect - z_95 * se_did
        ci_upper = did_effect + z_95 * se_did
        t_stat = did_effect / se_did if se_did > 0 else 0

        total_n = sum(g["n"] for g in groups.values())
        p_value = 2 * (1 - sp_stats.norm.cdf(abs(t_stat)))

        result = {
            "method": "DID",
            "treatment_col": treatment_col,
            "outcome_col": outcome,
            "group_means": {
                f"treatment={t}_period={p}": round(groups[(t, p)]["mean"], 4)
                for (t, p) in groups
            },
            "treatment_diff": round(float(treat_diff), 4),
            "control_diff": round(float(control_diff), 4),
            "did_effect": round(float(did_effect), 4),
            "standard_error": round(float(se_did), 4),
            "ci_95": [round(float(ci_lower), 4), round(float(ci_upper), 4)],
            "t_statistic": round(float(t_stat), 4),
            "p_value": round(float(p_value), 6),
            "significant_at_005": bool(p_value < 0.05),
            "total_observations": total_n,
        }

        # 预处理期趋势对比
        treat_pre_mean = groups[(1, 0)]["mean"]
        control_pre_mean = groups[(0, 0)]["mean"]
        if control_pre_mean != 0:
            trend_diff_pct = abs(treat_pre_mean - control_pre_mean) / abs(control_pre_mean) * 100
            if trend_diff_pct > 20:
                result["warning"] = (
                    f"预处理期趋势差异较大（{trend_diff_pct:.1f}%），"
                    f"DID 平行趋势假设可能不成立，结果需谨慎解读"
                )

        return json.dumps(result, ensure_ascii=False, indent=2)

    return f"Error: 不支持的方法 '{method}'。可用: did"


@registry.register(
    name="shap_analysis",
    description="使用 SHAP 值分析已训练模型的特征重要性。需要先通过 regression_analysis 或 classification 训练模型。",
    requires=["regression_analysis", "classification"],
    schema_overrides={
        "name": {"description": "数据集名称"},
        "target_col": {"description": "目标变量列"},
    },
)
def shap_analysis(name: str, target_col: str) -> str:
    from data_agent.tools.ml import _trained_models

    # 查找已训练的模型
    for suffix in ("_reg_", "_cls_"):
        model_key = f"{name}{suffix}{target_col}"
        if model_key in _trained_models:
            model = _trained_models[model_key]
            break
    else:
        return json.dumps({
            "error": f"未找到目标 '{target_col}' 的已训练模型。请先调用 regression_analysis 或 classification 训练模型。",
        }, ensure_ascii=False)

    df, err = get_df(name)
    if err:
        return err

    feature_cols = [c for c in df.select_dtypes(include=[np.number]).columns if c != target_col]
    if not feature_cols:
        return json.dumps({"error": "没有可用的数值特征列"}, ensure_ascii=False)

    data = df[feature_cols].dropna()

    try:
        import shap
        explainer = shap.TreeExplainer(model)
        shap_values = explainer.shap_values(data[feature_cols])

        # 分类任务可能是多类别
        if isinstance(shap_values, list):
            shap_values = shap_values[0]

        mean_abs_shap = np.abs(shap_values).mean(axis=0)

        features_shap = sorted(
            zip(feature_cols, mean_abs_shap),
            key=lambda x: -x[1],
        )

        result = {
            "model_type": type(model).__name__,
            "target": target_col,
            "n_features": len(feature_cols),
            "shap_importance": [
                {"feature": f, "mean_abs_shap": round(float(v), 6)}
                for f, v in features_shap
            ],
        }
        return json.dumps(result, ensure_ascii=False, indent=2)

    except ImportError:
        return json.dumps({"error": "SHAP 未安装。运行: pip install shap"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"SHAP 分析失败: {e}"}, ensure_ascii=False)


_FACTOR_CATEGORICAL_CARDINALITY_CEILING = 12
_FACTOR_MAXIMUM_HAC_LAGS = 4


def _hac_maxlags(n: int) -> int:
    """Documented HAC lag rule for the factor relationship tool.

    We use ``min(4, floor(n / 100))`` with a minimum of one lag whenever the
    sample is large enough to support HAC at all. The 4-lag ceiling keeps the
    bandwidth tractable for the daily/weekly panels this tool is typically
    applied to; users with stronger serial dependence should disclose it as a
    limitation rather than silently widen the kernel.
    """

    if n < 30:
        return 1
    return max(1, min(_FACTOR_MAXIMUM_HAC_LAGS, n // 100))


def _safe_float(value: Any, ndigits: int = 6) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):
        return None
    return round(f, ndigits)


def _encode_factor_design_matrix(
    df: pd.DataFrame,
    target_col: str,
    feature_names: list[str],
) -> tuple[pd.DataFrame, dict[str, Any], list[str], list[str]]:
    """One-hot encode low-cardinality categoricals and collect numeric features.

    Returns the design DataFrame (without the target), an encoding map
    describing how each categorical was expanded, the list of dropped feature
    names (and why), and the list of final design columns.
    """

    design_columns: list[pd.Series] = []
    encoding_map: dict[str, Any] = {}
    excluded: list[str] = []

    for feature in feature_names:
        if feature not in df.columns:
            excluded.append(feature)
            continue
        col = df[feature]
        if pd.api.types.is_numeric_dtype(col):
            design_columns.append(col.astype(float))
            continue
        # Categorical (object/category/etc.) — only one-hot encode when the
        # cardinality is small enough to keep the design identifiable.
        distinct = col.dropna().astype(str).unique()
        if len(distinct) < 2:
            excluded.append(feature)
            continue
        if len(distinct) > _FACTOR_CATEGORICAL_CARDINALITY_CEILING:
            excluded.append(feature)
            continue
        dummies = pd.get_dummies(col.astype(str), prefix=feature, drop_first=True)
        for dcol in dummies.columns:
            design_columns.append(dummies.astype(float))
        encoding_map[feature] = {
            "levels": list(distinct),
            "encoding": "one_hot_drop_first",
            "design_columns": list(dummies.columns),
            "reference_level": sorted(set(distinct) - {str(c).split("_", 1)[-1] for c in dummies.columns}),
        }

    if not design_columns:
        return pd.DataFrame(), encoding_map, excluded, []

    design = pd.concat(design_columns, axis=1)
    return design, encoding_map, excluded, list(design.columns)


def _fit_factor_relationship(
    *,
    name: str,
    target_col: str,
    features: str,
    time_col: str,
    alpha: float,
    correction: str,
) -> dict[str, Any]:
    df, err = get_df(name)
    if err:
        return {"error": err}

    if target_col not in df.columns:
        return {
            "error": f"目标列 '{target_col}' 不存在",
            "available_columns": list(df.columns),
        }
    if not pd.api.types.is_numeric_dtype(df[target_col]):
        return {
            "error": (
                f"目标列 '{target_col}' 必须是数值类型才能拟合 OLS；"
                "对分类目标请使用分类建模工具。"
            )
        }

    requested_features = [c.strip() for c in (features or "").split(",") if c.strip()]
    if not requested_features:
        numeric_features = [
            c for c in df.select_dtypes(include=[np.number]).columns
            if c != target_col
        ]
        requested_features = numeric_features
    if not requested_features:
        return {"error": "没有可用的特征列；请显式传入 features 或加载包含数值列的数据集。"}

    required_columns = [target_col] + [c for c in requested_features if c in df.columns]
    if time_col and time_col in df.columns:
        required_columns.append(time_col)
    df_required = df[required_columns].dropna()
    effective_sample_size = int(len(df_required))

    design, encoding_map, excluded, design_columns = _encode_factor_design_matrix(
        df_required, target_col, requested_features
    )
    if design.empty or len(design_columns) == 0:
        return {
            "error": "设计矩阵为空：所有特征均被排除（类型不匹配或低基数类别不足）。",
            "effective_sample_size": effective_sample_size,
            "excluded_features": excluded,
        }

    design = design.loc[df_required.index]
    y = df_required[target_col].astype(float).loc[df_required.index]

    if effective_sample_size < (len(design_columns) + 2):
        return {
            "allowed_claim_class": "inferential_associations",
            "effective_sample_size": effective_sample_size,
            "excluded_features": excluded,
            "limitations": [
                "有效样本量不足以稳定估计所请求的特征空间。",
                "请减少特征数量、合并类别或补充样本后再尝试。",
            ],
            "diagnostics": {"status": "insufficient_sample_for_design"},
        }

    import statsmodels.api as sm
    from statsmodels.stats.outliers_influence import variance_inflation_factor
    from statsmodels.stats.multitest import multipletests

    X = sm.add_constant(design.astype(float), has_constant="add")

    use_hac = bool(time_col) and time_col in df_required.columns
    if use_hac:
        maxlags = _hac_maxlags(effective_sample_size)
        model = sm.OLS(y, X, hasconst=True)
        try:
            fit = model.fit(cov_type="HAC", cov_kwds={"maxlags": maxlags})
            covariance_label = f"HAC(maxlags={maxlags})"
            covariance_method = "HAC"
        except Exception as exc:
            return {
                "error": f"HAC 协方差估计失败：{exc}",
                "allowed_claim_class": "inferential_associations",
            }
    else:
        model = sm.OLS(y, X, hasconst=True)
        try:
            fit = model.fit(cov_type="HC3")
            covariance_label = "HC3 robust"
            covariance_method = "HC3"
        except Exception as exc:
            return {
                "error": f"HC3 协方差估计失败：{exc}",
                "allowed_claim_class": "inferential_associations",
            }

    # Confidence intervals (robust).
    ci_df = fit.conf_int(alpha=alpha)
    raw_p_values = fit.pvalues
    coefficients: list[dict[str, Any]] = []
    coefficient_names = list(fit.params.index)

    # Multiplicity correction on FEATURE coefficient p-values only.
    # The intercept ("const") is a nuisance location parameter, not an
    # effect being tested for significance, so it MUST be excluded from
    # the correction input: including it would inflate the size of the
    # correction family and overstate the significance of the feature
    # coefficients. The intercept's adjusted_p_value is reported as None.
    correction_method = "none" if correction == "none" else correction
    coefficient_p = raw_p_values.astype(float)
    is_intercept_mask = np.array(
        [coef_name == "const" for coef_name in coefficient_names], dtype=bool
    )
    feature_p_values = coefficient_p.values[~is_intercept_mask]
    if correction == "none":
        feature_adjusted = feature_p_values
    else:
        try:
            _, feature_adjusted, _, _ = multipletests(
                feature_p_values, method=correction
            )
        except Exception:
            correction_method = "none (fallback)"
            feature_adjusted = feature_p_values

    # Realign the corrected feature p-values to the original coefficient
    # order; the intercept keeps adjusted_p_value=None because it was not
    # part of the correction family.
    feature_adjusted_iter = iter(feature_adjusted)
    for index, coef_name in enumerate(coefficient_names):
        estimate = _safe_float(fit.params.iloc[index])
        std_err = _safe_float(fit.bse.iloc[index])
        raw_p = _safe_float(coefficient_p.iloc[index])
        is_intercept = bool(is_intercept_mask[index])
        adj_p = None if is_intercept else _safe_float(next(feature_adjusted_iter))
        ci_lower = _safe_float(ci_df.iloc[index, 0])
        ci_upper = _safe_float(ci_df.iloc[index, 1])
        coefficients.append({
            "term": str(coef_name),
            "estimate": estimate,
            "std_error": std_err,
            "confidence_interval": {"level": 1 - alpha, "lower": ci_lower, "upper": ci_upper},
            "p_value": None if is_intercept else raw_p,
            "adjusted_p_value": adj_p,
            "is_intercept": is_intercept,
        })

    # Collinearity diagnostics — VIF is undefined when the design has only one
    # predictor (besides the constant). Report an exact failure instead of a
    # NaN silent-pass.
    feature_only = design.copy()
    collinearity: dict[str, Any]
    if feature_only.shape[1] < 2:
        collinearity = {
            "status": "not_estimable",
            "reason": "VIF requires at least two predictors; with a single predictor the design is exactly identified.",
        }
    else:
        vif_values = []
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                for column_index, column_name in enumerate(feature_only.columns):
                    vif_value = variance_inflation_factor(feature_only.values, column_index)
                    vif_values.append({
                        "term": str(column_name),
                        "variance_inflation_factor": _safe_float(vif_value),
                    })
            collinearity = {
                "status": "assessed",
                "method": "variance_inflation_factor",
                "terms": vif_values,
                "high_vif_terms": [
                    item["term"] for item in vif_values
                    if item["variance_inflation_factor"] is not None
                    and item["variance_inflation_factor"] >= 10
                ],
            }
        except Exception as exc:
            collinearity = {
                "status": "exact_failure",
                "reason": (
                    "VIF computation failed because the design matrix is "
                    f"singular: {exc}"
                ),
            }

    # Residual / time-dependence diagnostics.
    residuals = fit.resid
    time_dependence: dict[str, Any]
    if use_hac:
        try:
            # Durbin-Watson is a quick residual autocorrelation summary;
            # reported alongside the HAC covariance so users see WHY HAC
            # was chosen, not just that it was.
            dw = float(sm.stats.stattools.durbin_watson(residuals))
            time_dependence = {
                "ordered_time_column": time_col,
                "durbin_watson": round(dw, 6),
                "hac_maxlags": maxlags,
                "rule": "min(4, floor(n/100)) with a minimum of 1 lag",
                "covariance": covariance_label,
                "status": "assessed",
                "reason": (
                    "HAC standard errors are used because an ordered time "
                    "column was supplied; residual autocorrelation is "
                    "summarized by Durbin-Watson."
                ),
            }
        except Exception as exc:
            time_dependence = {
                "ordered_time_column": time_col,
                "status": "not_estimable",
                "reason": f"Durbin-Watson diagnostic failed: {exc}",
                "covariance": covariance_label,
            }
    else:
        time_dependence = {
            "ordered_time_column": None,
            "status": "not_applicable",
            "reason": (
                "No ordered time column supplied. HC3 robust covariance is "
                "used; serial dependence is not assessed. Supply time_col "
                "to enable HAC and residual autocorrelation diagnostics."
            ),
            "covariance": covariance_label,
        }

    limitations = [
        "OLS 系数描述的是在控制其他变量的条件下的关联强度，不能直接解释为因果效应。",
        f"协方差方法：{covariance_label}。",
        f"多重比较校正：{correction_method}。",
        "若残差存在未建模的非线性或交互项，系数解释需要额外假设。",
    ]
    if use_hac:
        limitations.append(
            f"HAC 带宽使用 {maxlags} 阶（规则：min(4, floor(n/100))）。"
            "强自相关场景请考虑更专门的时序模型。"
        )
    if excluded:
        limitations.append(
            f"被排除的特征：{excluded}（类型不匹配或类别基数过高）。"
        )

    r_squared = _safe_float(fit.rsquared)
    adj_r_squared = _safe_float(fit.rsquared_adj)
    f_p_value = _safe_float(fit.f_pvalue)

    assumptions_block = [
        {
            "name": "linearity",
            "status": "assumed",
            "reason": "OLS estimates a linear conditional mean; non-linearity should be checked separately.",
        },
        {
            "name": "method_appropriate_for_design",
            "status": "passed",
            "reason": (
                "HC3/HAC robust covariance was selected based on the "
                f"{'ordered time column' if use_hac else 'cross-sectional design'}"
                "."
            ),
        },
    ]

    return {
        "method": "OLS with robust covariance",
        "covariance": covariance_label,
        "covariance_method": covariance_method,
        "target_col": target_col,
        "features_requested": requested_features,
        "features_included": [c for c in requested_features if c not in excluded],
        "design_columns": design_columns,
        "encoding_map": encoding_map,
        "excluded_features": excluded,
        "effective_sample_size": effective_sample_size,
        "coefficients": coefficients,
        "r_squared": r_squared,
        "adjusted_r_squared": adj_r_squared,
        "f_p_value": f_p_value,
        "collinearity": collinearity,
        "time_dependence": time_dependence,
        "correction_method": correction_method,
        "alpha": float(alpha),
        "assumptions": assumptions_block,
        "limitations": limitations,
        "allowed_claim_class": "inferential_associations",
    }


@registry.register(
    name="factor_relationship_analysis",
    description=(
        "拟合多变量 OLS 模型识别与目标值存在显著关联的因素，"
        "默认使用 HC3 稳健协方差；传入有序时间列时切换到 HAC。"
        "提供系数估计、稳健标准误、置信区间、原始与多重校正后的 p 值、"
        "VIF 共线性诊断、残差/时间依赖诊断，以及明确的 claim class。"
        "适用场景：哪些因素显著影响目标值、相关因素的相对强度。"
        "不适用场景：因果效应（请使用 causal_analysis）、纯预测排序（请使用 regression_analysis）。"
    ),
    schema_overrides={
        "name": {"description": "数据集名称"},
        "target_col": {"description": "目标数值列"},
        "features": {"description": "候选特征列，逗号分隔；留空则使用所有数值列"},
        "time_col": {"description": "可选：有序时间列，传入后使用 HAC 协方差"},
        "alpha": {"description": "置信区间与显著性水平，默认 0.05"},
        "correction": {
            "description": "p 值多重比较校正方法",
            "enum": ["fdr_bh", "holm", "none"],
        },
    },
)
def factor_relationship_analysis(
    name: str,
    target_col: str,
    features: str = "",
    time_col: str = "",
    alpha: float = 0.05,
    correction: Literal["fdr_bh", "holm", "none"] = "fdr_bh",
) -> str:
    return json.dumps(
        _fit_factor_relationship(
            name=name,
            target_col=target_col,
            features=features,
            time_col=time_col,
            alpha=alpha,
            correction=correction,
        ),
        ensure_ascii=False,
        indent=2,
    )
