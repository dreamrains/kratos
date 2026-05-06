"""L2.5: 情景模拟与假设分析工具。"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from data_agent.session.workspace import workspace
from data_agent.tools.registry import ToolResult, registry


@registry.register(
    name="what_if_simulation",
    description=(
        "情景模拟与影响分析。支持三种模式：\n"
        "- sensitivity（Level 1 参数敏感性）：指定 dimension + metric + change_pct，"
        "计算对总量的正向影响。支持 target_value 反向推算。\n"
        "- predict（Level 2 模型预测）：基于回归模型预测特征变化后的结果。"
        "需先训练回归模型或自动训练。\n"
        "- optimize（Level 3 目标规划）：指定 target_metric 和 goal_pct，"
        "反推各维度所需最小变化量，支持约束条件。\n"
    ),
    schema_overrides={
        "name": {"description": "数据集名称"},
        "mode": {"description": "模拟模式", "enum": ["sensitivity", "predict", "optimize"]},
        "metric": {"description": "目标指标列（sensitivity/optimize）"},
        "dimension": {"description": "拆解维度列（sensitivity/optimize）"},
        "change_pct": {"description": "变化百分比，如 10 表示 +10%（sensitivity）"},
        "target_value": {"description": "目标值（sensitivity 反向推算时使用）"},
        "dim_value": {"description": "指定维度值（sensitivity，为空则对所有维度值应用）"},
        "target_col": {"description": "回归目标列（predict）"},
        "feature_changes": {"description": "特征变化 JSON，如 {\"col1\": 10, \"col2\": -5}（predict）"},
        "target_metric": {"description": "目标指标列（optimize）"},
        "goal_pct": {"description": "目标变化百分比，如 10 表示增长10%（optimize）"},
        "constraints": {"description": "约束条件 JSON，如 {\"渠道A\": {\"min\": -5, \"max\": 20}}（optimize）"},
    },
)
def what_if_simulation(
    name: str,
    mode: str = "sensitivity",
    # Level 1
    metric: str = "",
    dimension: str = "",
    change_pct: float = 0.0,
    target_value: str = "",
    dim_value: str = "",
    # Level 2
    target_col: str = "",
    feature_changes: str = "",
    # Level 3
    target_metric: str = "",
    goal_pct: float = 0.0,
    constraints: str = "",
) -> str:
    df = workspace.get(name)
    if df is None:
        available = list(workspace.list_datasets().keys())
        return json.dumps({"error": f"数据集 '{name}' 不存在。可用: {available}"}, ensure_ascii=False)

    if mode == "sensitivity":
        return _sensitivity(df, name, metric, dimension, change_pct, target_value, dim_value)
    elif mode == "predict":
        return _predict(df, name, target_col, feature_changes)
    elif mode == "optimize":
        return _optimize(df, name, target_metric or metric, dimension, goal_pct, constraints)
    else:
        return f"Error: 不支持的模式 '{mode}'。可用: sensitivity, predict, optimize"


def _sensitivity(
    df: pd.DataFrame, name: str, metric: str, dimension: str,
    change_pct: float, target_value: str, dim_value: str,
) -> str:
    """Level 1: 参数敏感性分析。"""
    if metric not in df.columns:
        return f"Error: 列 '{metric}' 不存在。可用: {list(df.columns)}"
    if not dimension or dimension not in df.columns:
        return f"Error: 需要指定 dimension 参数且列存在。可用: {list(df.columns)}"

    # 计算基线
    baseline_total = float(df[metric].sum())
    baseline_by_dim = df.groupby(dimension)[metric].sum().to_dict()

    # 反向推算模式
    if target_value:
        try:
            target = float(target_value)
        except ValueError:
            return f"Error: target_value 必须为数字，收到 '{target_value}'"

        gap = target - baseline_total
        required_pct = round(gap / baseline_total * 100, 2) if baseline_total != 0 else None

        # 按当前份额等比分配
        breakdown = []
        for dv, val in baseline_by_dim.items():
            share = val / baseline_total if baseline_total != 0 else 0
            required_change = gap * share
            dim_pct = round(required_change / val * 100, 2) if val != 0 else None
            breakdown.append({
                "dimension_value": str(dv),
                "current": round(float(val), 4),
                "required_change": round(float(required_change), 4),
                "required_pct": dim_pct,
            })
        breakdown.sort(key=lambda x: -abs(x.get("required_pct") or 0))

        data = {
            "mode": "sensitivity_reverse",
            "metric": metric,
            "baseline_total": round(baseline_total, 4),
            "target": target,
            "gap": round(gap, 4),
            "required_total_pct": required_pct,
            "breakdown": breakdown,
        }

        summary_lines = [
            f"目标反推: {metric} 从 {baseline_total:.2f} → {target:.2f}",
            f"需要变化: {gap:+.2f} ({required_pct:+.2f}%)" if required_pct is not None else f"需要变化: {gap:+.2f}",
            "各维度所需变化:",
        ]
        for b in breakdown[:5]:
            pct_str = f" ({b['required_pct']:+.1f}%)" if b["required_pct"] is not None else ""
            summary_lines.append(f"  {b['dimension_value']}: {b['required_change']:+.2f}{pct_str}")

        return ToolResult(summary="\n".join(summary_lines), data=data)

    # 正向模拟模式
    if change_pct == 0:
        return "Error: 请指定 change_pct 或 target_value"

    perturbed = df.copy()
    if dim_value:
        mask = perturbed[dimension] == dim_value
        perturbed.loc[mask, metric] = perturbed.loc[mask, metric] * (1 + change_pct / 100)
    else:
        # 对所有维度值应用
        perturbed[metric] = perturbed[metric] * (1 + change_pct / 100)

    projected_total = float(perturbed[metric].sum())
    impact = projected_total - baseline_total
    impact_pct = round(impact / baseline_total * 100, 2) if baseline_total != 0 else None

    # 弹性系数
    elasticity = round(impact_pct / change_pct, 4) if change_pct != 0 and impact_pct is not None else None

    projected_by_dim = perturbed.groupby(dimension)[metric].sum().to_dict()
    breakdown = []
    for dv in sorted(set(baseline_by_dim.keys()) | set(projected_by_dim.keys())):
        b = float(baseline_by_dim.get(dv, 0))
        p = float(projected_by_dim.get(dv, 0))
        breakdown.append({
            "dimension_value": str(dv),
            "baseline": round(b, 4),
            "projected": round(p, 4),
            "change": round(p - b, 4),
        })

    data = {
        "mode": "sensitivity",
        "metric": metric,
        "scenario": f"{dim_value or '全部'} {metric} {change_pct:+.0f}%",
        "baseline": {"total": round(baseline_total, 4)},
        "projected": {"total": round(projected_total, 4)},
        "impact": {"absolute": round(impact, 4), "relative_pct": impact_pct},
        "elasticity": elasticity,
        "breakdown": breakdown[:10],
    }

    dim_label = f"'{dim_value}'" if dim_value else "所有"
    summary_lines = [
        f"情景模拟: {dim_label} {metric} {change_pct:+.0f}%",
        f"总量: {baseline_total:.2f} → {projected_total:.2f} ({impact:+.2f}, {impact_pct:+.2f}%)" if impact_pct is not None else f"总量: {baseline_total:.2f} → {projected_total:.2f}",
    ]
    if elasticity:
        summary_lines.append(f"弹性系数: {elasticity:.2f} (全局变化 {change_pct:.0f}% → 总量变化 {impact_pct:.2f}%)")

    return ToolResult(
        summary="\n".join(summary_lines),
        data=data,
        suggested_next="compare_periods 验证历史实际变化",
    )


def _predict(
    df: pd.DataFrame, name: str, target_col: str, feature_changes: str,
) -> str:
    """Level 2: 基于回归模型的预测模拟。"""
    if not target_col:
        return "Error: predict 模式需要 target_col 参数"
    if not feature_changes:
        return "Error: predict 模式需要 feature_changes 参数（JSON 格式）"

    try:
        changes = json.loads(feature_changes) if isinstance(feature_changes, str) else feature_changes
    except json.JSONDecodeError:
        return "Error: feature_changes 必须是有效的 JSON，如 {\"col1\": 10, \"col2\": -5}"

    # 查找已训练的模型
    from data_agent.tools.ml import _trained_models

    model_key = f"{name}_reg_{target_col}"
    model = None
    if model_key in _trained_models:
        model = _trained_models[model_key]
        reused = True
    else:
        # 自动训练
        from sklearn.ensemble import GradientBoostingRegressor

        feature_cols = [c for c in df.select_dtypes(include=[np.number]).columns if c != target_col]
        if not feature_cols:
            return "Error: 没有可用的数值特征列"

        data = df[feature_cols + [target_col]].dropna()
        if len(data) < 20:
            return f"Error: 有效数据 ({len(data)}) 太少，至少需要 20 条"

        model = GradientBoostingRegressor(n_estimators=100, random_state=42)
        model.fit(data[feature_cols].values, data[target_col].values.astype(float))
        _trained_models[model_key] = model
        reused = False

    # 获取特征列
    feature_cols = list(model.feature_names_in_) if hasattr(model, "feature_names_in_") else [
        c for c in df.select_dtypes(include=[np.number]).columns if c != target_col
    ]

    # 验证特征
    invalid_features = [f for f in changes.keys() if f not in feature_cols]
    if invalid_features:
        return f"Error: 特征 {invalid_features} 不在模型中。可用: {feature_cols}"

    # 基线预测
    data = df[feature_cols + [target_col]].dropna()
    X_base = data[feature_cols].values
    y_base_pred = model.predict(X_base)
    baseline = float(np.mean(y_base_pred))

    # 应用变化
    X_new = data[feature_cols].copy()
    for feat, pct in changes.items():
        if feat in X_new.columns:
            X_new[feat] = X_new[feat] * (1 + pct / 100)

    y_new_pred = model.predict(X_new.values)
    projected = float(np.mean(y_new_pred))
    impact = projected - baseline
    impact_pct = round(impact / abs(baseline) * 100, 2) if baseline != 0 else None

    # 特征重要性（如果有）
    importance = {}
    if hasattr(model, "feature_importances_"):
        for fname, imp in sorted(zip(feature_cols, model.feature_importances_), key=lambda x: -x[1]):
            importance[fname] = round(float(imp), 4)

    data_result = {
        "mode": "predict",
        "target_col": target_col,
        "model_type": type(model).__name__,
        "model_reused": reused,
        "feature_changes": changes,
        "baseline": round(baseline, 4),
        "projected": round(projected, 4),
        "impact": {"absolute": round(impact, 4), "relative_pct": impact_pct},
        "feature_importance": importance,
    }

    changes_desc = ", ".join(f"{k} {v:+.0f}%" for k, v in changes.items())
    summary_lines = [
        f"模型预测: {target_col} 在 {changes_desc} 下",
        f"基线: {baseline:.4f} → 预测: {projected:.4f} ({impact:+.4f}, {impact_pct:+.2f}%)" if impact_pct is not None else f"基线: {baseline:.4f} → 预测: {projected:.4f}",
        f"模型: {type(model).__name__} ({'复用已有' if reused else '自动训练'})",
    ]

    return ToolResult(
        summary="\n".join(summary_lines),
        data=data_result,
        suggested_next="regression_analysis 查看模型详情",
    )


def _optimize(
    df: pd.DataFrame, name: str, target_metric: str, dimension: str,
    goal_pct: float, constraints: str,
) -> str:
    """Level 3: 目标规划——反推各维度所需最小变化量。"""
    if not target_metric or target_metric not in df.columns:
        return f"Error: 需要指定有效的 target_metric。可用: {list(df.columns)}"

    if not dimension or dimension not in df.columns:
        return f"Error: 需要指定 dimension 参数。可用: {list(df.columns)}"

    if goal_pct == 0:
        return "Error: goal_pct 不能为 0"

    # 解析约束
    constraint_map = {}
    if constraints:
        try:
            constraint_map = json.loads(constraints) if isinstance(constraints, str) else constraints
        except json.JSONDecodeError:
            return "Error: constraints 必须是有效的 JSON"

    baseline_total = float(df[target_metric].sum())
    target_total = baseline_total * (1 + goal_pct / 100)
    gap = target_total - baseline_total

    # 按维度拆解基线
    baseline_by_dim = df.groupby(dimension)[target_metric].sum().sort_values(ascending=False)
    dim_values = list(baseline_by_dim.index)

    # 使用最小二乘求解：各维度等贡献分配 + 约束剪裁
    result_breakdown = []
    remaining_gap = gap

    # 按份额加权分配
    total_baseline = sum(baseline_by_dim.values)
    allocations = {}
    for dv, val in baseline_by_dim.items():
        share = val / total_baseline if total_baseline != 0 else 0
        allocations[dv] = gap * share

    # 应用约束
    for dv in dim_values:
        c = constraint_map.get(str(dv), {})
        min_pct = c.get("min", -100)
        max_pct = c.get("max", 100)

        current_val = float(baseline_by_dim[dv])
        alloc = allocations[dv]
        alloc_pct = alloc / current_val * 100 if current_val != 0 else 0

        # 剪裁到约束范围
        clipped_pct = max(min_pct, min(max_pct, alloc_pct))
        clipped_alloc = current_val * clipped_pct / 100

        overflow = alloc - clipped_alloc
        allocations[dv] = clipped_alloc

        # 将溢出重新分配给未约束满的维度
        if abs(overflow) > 0.001:
            unconstrained = [
                d for d in dim_values
                if str(d) not in constraint_map or
                (clipped_pct > 0 and allocations[d] / float(baseline_by_dim[d]) * 100 < constraint_map.get(str(d), {}).get("max", 100)) or
                (clipped_pct < 0 and allocations[d] / float(baseline_by_dim[d]) * 100 > constraint_map.get(str(d), {}).get("min", -100))
            ]
            if unconstrained:
                per_dim = overflow / len(unconstrained)
                for d in unconstrained:
                    allocations[d] += per_dim

    # 构建结果
    projected_total = baseline_total + sum(allocations.values())
    actual_pct = round((projected_total - baseline_total) / baseline_total * 100, 2) if baseline_total != 0 else 0

    for dv in dim_values:
        current_val = float(baseline_by_dim[dv])
        alloc = allocations[dv]
        pct = round(alloc / current_val * 100, 2) if current_val != 0 else 0
        c = constraint_map.get(str(dv), {})
        result_breakdown.append({
            "dimension_value": str(dv),
            "current": round(current_val, 4),
            "required_change": round(alloc, 4),
            "required_pct": pct,
            "constrained": str(dv) in constraint_map,
        })

    result_breakdown.sort(key=lambda x: -abs(x.get("required_pct") or 0))

    data = {
        "mode": "optimize",
        "metric": target_metric,
        "dimension": dimension,
        "baseline": round(baseline_total, 4),
        "target": round(target_total, 4),
        "goal_pct": goal_pct,
        "actual_pct": actual_pct,
        "gap": round(gap, 4),
        "feasible": abs(actual_pct - goal_pct) < 1,
        "breakdown": result_breakdown,
    }

    feasible_note = "" if data["feasible"] else f" (约束限制，实际可达 {actual_pct:.1f}%)"
    summary_lines = [
        f"目标规划: {target_metric} {'增长' if goal_pct > 0 else '降低'} {abs(goal_pct):.1f}%{feasible_note}",
        f"基线: {baseline_total:.2f} → 目标: {target_total:.2f}",
        "各维度所需变化:",
    ]
    for b in result_breakdown[:7]:
        constrained_tag = " [约束]" if b["constrained"] else ""
        summary_lines.append(
            f"  {b['dimension_value']}: {b['required_pct']:+.1f}% "
            f"({b['current']:.2f} → {b['current'] + b['required_change']:.2f}){constrained_tag}"
        )

    return ToolResult(
        summary="\n".join(summary_lines),
        data=data,
        suggested_next="what_if_simulation(sensitivity) 验证单维度变化影响",
    )
