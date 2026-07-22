"""L3: 统计推断工具。"""

from __future__ import annotations

import json
import warnings

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
