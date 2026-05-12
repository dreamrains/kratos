"""L3: 统计推断工具。"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
from scipy import stats as sp_stats

from data_agent.session.workspace import workspace
from data_agent.tools._utils import get_df
from data_agent.tools.registry import registry


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

    g1_name, g2_name = str(groups[0]), str(groups[1])

    # chi2 直接使用列联表，不需要 float 转换
    if method == "chi2":
        contingency = pd.crosstab(df[group_col], df[metric_col])
        if contingency.size < 4:
            return "Error: chi2 检验需要每组至少 2 个类别"
        stat, p_value, dof, expected = sp_stats.chi2_contingency(contingency)
        result = {
            "group_col": group_col,
            "metric_col": metric_col,
            "groups": {g1_name: {"n": int(contingency.loc[groups[0]].sum())},
                       g2_name: {"n": int(contingency.loc[groups[1]].sum())}},
            "method": "chi2",
            "test": {
                "statistic": round(float(stat), 4),
                "p_value": round(float(p_value), 6),
                "dof": int(dof),
                "significant": bool(p_value < 0.05),
            },
        }
        return json.dumps(result, ensure_ascii=False, indent=2)

    g1 = df[df[group_col] == groups[0]][metric_col].dropna().values.astype(float)
    g2 = df[df[group_col] == groups[1]][metric_col].dropna().values.astype(float)

    if len(g1) < 2 or len(g2) < 2:
        return "Error: 每组至少需要 2 个有效数据点"

    # Levene 方差齐性检验
    levene_stat, levene_p = sp_stats.levene(g1, g2)
    equal_var = bool(levene_p > 0.05)

    # 自动选择检验方法
    if method == "auto":
        # 正态性检验 (Shapiro-Wilk, n < 5000)
        g1_normal = True
        g2_normal = True
        if len(g1) < 5000:
            _, p1 = sp_stats.shapiro(g1[:5000] if len(g1) > 5000 else g1)
            g1_normal = p1 > 0.05
        if len(g2) < 5000:
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
    }

    diff = float(np.mean(g2) - np.mean(g1))
    result["difference"] = {
        "absolute": round(diff, 4),
        "relative_pct": round(diff / abs(np.mean(g1)) * 100, 2) if np.mean(g1) != 0 else None,
        "cohens_d": round(diff / np.sqrt((np.std(g1, ddof=1)**2 + np.std(g2, ddof=1)**2) / 2), 4)
                     if (np.std(g1) + np.std(g2)) > 0 else None,
    }

    # 方差齐性检验
    result["levene_test"] = {
        "statistic": round(float(levene_stat), 4),
        "p_value": round(float(levene_p), 6),
        "equal_variance": equal_var,
    }

    if method == "ttest":
        stat, p_value = sp_stats.ttest_ind(g1, g2, equal_var=equal_var)
        result["test"] = {
            "statistic": round(float(stat), 4),
            "p_value": round(float(p_value), 6),
            "significant": bool(p_value < 0.05),
        }
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
