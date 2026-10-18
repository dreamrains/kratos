"""L2.5: 情景模拟与假设分析工具。"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from data_agent.session.workspace import workspace
from data_agent.tools.registry import ToolResult, registry


@registry.register(
    name="what_if_simulation",
    output_contract={"version":"native_business_product.v1","adapter":"data_agent.agent.publication.native.resolve_native_claims","kinds":["scenario"]},
    description=(
        "情景模拟与影响分析。支持三种模式：\n"
        "- sensitivity（Level 1 参数敏感性）：指定 dimension + metric + change_pct，"
        "计算对总量的正向影响。支持 target_value 反向推算。\n"
        "- predict（Level 2 模型预测）：基于回归模型预测特征变化后的结果。"
        "需先训练当前数据版本的回归模型。\n"
        "- optimize（约束分配候选）：指定 target_metric 和 goal_pct，"
        "按现有份额分配与逐次剪裁构造候选，复核全部上下界与目标；不证明最优或不可行。\n"
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
    """Multiplicative arithmetic scenarios; no inferred allocation at zero base."""
    def error(reason):return json.dumps({"error":reason},ensure_ascii=False,allow_nan=False)
    if metric not in df.columns or dimension not in df.columns:return error("需要存在的 metric 和 dimension 列")
    if df.empty or not pd.api.types.is_numeric_dtype(df[metric]) or pd.api.types.is_bool_dtype(df[metric]) or df[metric].isna().any() or df[dimension].isna().any() or not np.isfinite(df[metric].to_numpy(dtype=float)).all():
        return error("指标必须全部为有限数值，维度不能缺失；不静默删除记录")
    grouped=df[metric].astype(float).groupby(df[dimension],observed=True,sort=False).sum()
    keys=[str(v) for v in grouped.index]
    if len(set(keys))!=len(keys):return error("维度字符串身份存在歧义")
    basis={str(k):float(v) for k,v in grouped.items()}
    baseline=sum(basis.values())
    if not np.isfinite(baseline) or not all(np.isfinite(v) for v in basis.values()):return error("聚合总量溢出")
    limits=["仅乘法/等比例算术情景；不识别干预因果收益，不授予预测验证。", "零或负值的业务含义未由算术确认；分组不自动解释为可执行业务分配。"]
    parameters={"simulation_dimension":dimension}
    if target_value:
        if dim_value:return error("反向等比例推算不支持单维度选择；请明确全体分组目标")
        try:target=float(target_value)
        except (TypeError,ValueError):return error("target_value 必须是有限数字")
        if not np.isfinite(target):return error("target_value 必须是有限数字")
        gap=target-baseline
        if not np.isfinite(gap):return error("目标缺口溢出")
        unknown=baseline==0 and gap!=0
        rows=[]
        for key,value in basis.items():
            required=None if unknown else (gap*value/baseline if baseline!=0 else 0.0)
            if required is not None and not np.isfinite(required):return error("反推分组变化溢出")
            rows.append({"dimension_value":key,"current":value,"required_change":required,
                         "required_pct":required/value*100 if required is not None and value!=0 else None})
        pct=gap/baseline*100 if baseline!=0 else None
        parameters.update(simulation_mode="sensitivity_reverse",simulation_target=target)
        data={"mode":"sensitivity_reverse","metric":metric,"dimension":dimension,"baseline_total":baseline,
              "target":target,"gap":gap,"required_total_pct":pct,"breakdown":rows,
              "status":"limited" if unknown else "arithmetic_complete"}
        if unknown:limits.append("总量为零且目标非零，既有等比例方法不能确定各组所需变化；保留未知，不新增分配方法。")
        summary=f"反向算术情景：{metric} 从 {baseline} 到目标 {target}；缺口 {gap}。"+("比例和分组所需变化未知。" if unknown else "已保留全部分组等比例变化。")
    else:
        if type(change_pct) not in (int,float) or not np.isfinite(change_pct) or change_pct==0:return error("change_pct 必须是非零有限数值")
        if dim_value and dim_value not in basis:return error("dim_value 没有唯一实际维度匹配")
        rows=[]
        for key,value in basis.items():
            projected=value*(1+change_pct/100) if not dim_value or key==dim_value else value
            if not np.isfinite(projected):return error("情景分组总量溢出")
            rows.append({"dimension_value":key,"baseline":value,"projected":projected,"change":projected-value})
        projected=sum(r["projected"] for r in rows);impact=projected-baseline
        if not np.isfinite(projected) or not np.isfinite(impact):return error("情景总量溢出")
        impact_pct=impact/baseline*100 if baseline!=0 else None
        parameters.update(simulation_mode="sensitivity",simulation_change_pct=change_pct)
        if dim_value:parameters["simulation_dimension_value"]=dim_value
        data={"mode":"sensitivity","metric":metric,"dimension":dimension,"scenario":f"{dim_value or '全部'} {metric} {change_pct:+g}%",
              "baseline":{"total":baseline},"projected":{"total":projected},"impact":{"absolute":impact,"relative_pct":impact_pct},
              "elasticity":impact_pct/change_pct if impact_pct is not None else None,"breakdown":rows,"status":"arithmetic_complete"}
        limits.append("elasticity只表示本次人为比例改动下的算术比值，不是估计的经济弹性或因果参数。")
        summary=f"正向算术情景：{metric} 从 {baseline} 到 {projected}；已保留全部 {len(rows)} 组。"
    data.update(basis_by_dimension=basis,scenario_parameters=parameters,claim_ceiling="arithmetic_scenario",limitations=limits)
    # Reject finite input combinations whose derived percentages overflow.
    try:json.dumps(data,allow_nan=False)
    except ValueError:return error("情景算术结果溢出")
    return ToolResult(summary=summary,data=data)


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

    if not isinstance(changes,dict) or not changes or any(type(v) not in (int,float) or not np.isfinite(v) for v in changes.values()):
        return "Error: feature_changes 必须为非空对象，值为有限数值百分比，不接受布尔值"

    # 查找已训练的模型
    from data_agent.tools.ml import _trained_models, _trained_model_metadata, _model_key

    model_key = _model_key(name, "regression", target_col)
    model = None
    if model_key in _trained_models:
        model = _trained_models[model_key]
        metadata = _trained_model_metadata.get(model_key, {})
        if metadata.get("data_identity") != workspace.get_data_identity(name):
            return "Error: 已训练模型与当前数据版本不一致；请先重新训练"
        reused = True
    else:
        return "Error: predict 模式需要当前数据版本的已训练回归模型；不会静默自动训练。"

    # 获取特征列
    feature_cols = list(metadata.get("feature_cols") or [])
    if not feature_cols or any(column not in df.columns for column in feature_cols):
        return "Error: 已训练模型的原特征列缺失"

    # 验证特征
    invalid_features = [f for f in changes.keys() if f not in feature_cols]
    if invalid_features:
        return f"Error: 特征 {invalid_features} 不在模型中。可用: {feature_cols}"

    # 基线预测
    data = df[feature_cols + [target_col]].dropna()
    if data.empty or not np.isfinite(data.to_numpy(dtype=float)).all():
        return "Error: 模型情景没有完整有限观测"
    X_base = data[feature_cols].values
    y_base_pred = model.predict(X_base)
    baseline = float(np.mean(y_base_pred))

    # 应用变化
    X_new = data[feature_cols].copy()
    for feat, pct in changes.items():
        if feat in X_new.columns:
            X_new[feat] = X_new[feat] * (1 + pct / 100)

    if not np.isfinite(X_new.to_numpy(dtype=float)).all():return "Error: 特征改动溢出"
    y_new_pred = model.predict(X_new.values)
    if not np.isfinite(y_base_pred).all() or not np.isfinite(y_new_pred).all():return "Error: 模型情景产生非有限预测"
    projected = float(np.mean(y_new_pred))
    impact = projected - baseline
    if not all(np.isfinite(v) for v in (baseline,projected,impact)):return "Error: 模型情景均值或变化溢出"
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
        "model_identity": {key: metadata.get(key) for key in ("model_key","kind","target_col","feature_cols","data_identity")},
        "claim_ceiling": "model_scenario",
        "limitations": ["当前模型的特征改动情景，不识别干预因果收益；预测变化未获外部或未来验证。"],
        "feature_changes": changes,
        "effective_rows":len(data),
        "source_rows":len(df),
        "excluded_missing_rows":len(df)-len(data),
        "scenario_predictions":{"baseline":[float(v) for v in y_base_pred],"projected":[float(v) for v in y_new_pred]},
        "baseline": round(baseline, 4),
        "projected": round(projected, 4),
        "impact": {"absolute": round(impact, 4), "relative_pct": impact_pct},
        "feature_importance": importance,
    }

    changes_desc = ", ".join(f"{k} {v:+.0f}%" for k, v in changes.items())
    summary_lines = [
        f"模型预测: {target_col} 在 {changes_desc} 下",
        f"基线: {baseline:.4f} → 预测: {projected:.4f} ({impact:+.4f}, {impact_pct:+.2f}%)" if impact_pct is not None else f"基线: {baseline:.4f} → 预测: {projected:.4f}",
        f"模型: {type(model).__name__} (复用当前模型)",
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
    """Construct and verify the existing allocation heuristic, without a solver."""
    def error(reason):
        return json.dumps({"error":reason},ensure_ascii=False,allow_nan=False)
    if target_metric not in df.columns or dimension not in df.columns:
        return error("需要指定存在的 target_metric 与 dimension")
    if type(goal_pct) not in (int,float) or not np.isfinite(goal_pct) or goal_pct==0:
        return error("goal_pct 必须是非零有限数值")
    if not pd.api.types.is_numeric_dtype(df[target_metric]) or df[target_metric].isna().any() or not np.isfinite(df[target_metric].to_numpy(dtype=float)).all() or df[dimension].isna().any():
        return error("指标必须全部为有限数值，维度不能缺失；不静默删除记录")
    grouped=df.groupby(dimension,observed=True)[target_metric].sum().sort_values(ascending=False)
    if grouped.empty or any(not np.isfinite(v) or v<=0 for v in grouped):
        return error("约束分配仅支持每个分组基数为有限正数")
    dim_values=list(grouped.index)
    names=[str(d) for d in dim_values]
    if len(set(names))!=len(names):return error("维度字符串身份冲突")
    try:
        constraint_map=json.loads(constraints) if isinstance(constraints,str) and constraints else constraints or {}
    except (ValueError,TypeError):return error("constraints 必须是 JSON 对象")
    if not isinstance(constraint_map,dict) or set(constraint_map)-set(names):
        return error("constraints 必须仅引用实际维度的 JSON 对象")
    bounds={}
    for dv in dim_values:
        c=constraint_map.get(str(dv),{})
        if not isinstance(c,dict) or set(c)-{"min","max"}:return error("约束仅支持 min/max")
        lower,upper=c.get("min",-100),c.get("max",100)
        if any(type(v) not in (int,float) or not np.isfinite(v) for v in (lower,upper)) or lower>upper:
            return error("每维 min/max 必须有限且 min<=max")
        bounds[dv]=(lower,upper)
    baseline=float(grouped.sum());target=baseline*(1+goal_pct/100);gap=target-baseline
    if not np.isfinite(baseline) or not np.isfinite(target) or not np.isfinite(gap):return error("总量或目标溢出")
    allocations={dv:gap*float(v)/baseline for dv,v in grouped.items()}
    # Preserve the existing one-pass share/clipping procedure. Its result is
    # only a candidate: later redistribution can invalidate an earlier bound.
    for dv in dim_values:
        lower,upper=bounds[dv];current=float(grouped[dv]);alloc=allocations[dv]
        clipped_pct=max(lower,min(upper,alloc/current*100))
        clipped=current*clipped_pct/100;overflow=alloc-clipped
        allocations[dv]=clipped
        if abs(overflow)>0.001:
            eligible=[d for d in dim_values if str(d) not in constraint_map or
                (clipped_pct>0 and allocations[d]/float(grouped[d])*100<bounds[d][1]) or
                (clipped_pct<0 and allocations[d]/float(grouped[d])*100>bounds[d][0])]
            if eligible:
                for d in eligible:allocations[d]+=overflow/len(eligible)
    projected=baseline+sum(allocations.values())
    valid_bounds=all(np.isfinite(allocations[d]) and bounds[d][0]-1e-9<=allocations[d]/float(grouped[d])*100<=bounds[d][1]+1e-9 for d in dim_values)
    target_met=bool(np.isfinite(projected) and np.isclose(projected,target,rtol=1e-10,atol=1e-8))
    verified=bool(valid_bounds and target_met)
    breakdown=[]
    if verified:
        breakdown=[{"dimension_value":str(d),"current":float(grouped[d]),"required_change":allocations[d],
            "required_pct":allocations[d]/float(grouped[d])*100,"min_pct":bounds[d][0],"max_pct":bounds[d][1],
            "constrained":str(d) in constraint_map} for d in dim_values]
    data={"mode":"optimize","method":"share_allocation_sequential_clipping","status":"candidate_verified" if verified else "candidate_not_found",
        "metric":target_metric,"dimension":dimension,"baseline":baseline,"target":target,"goal_pct":goal_pct,"gap":gap,
        "projected":projected if verified else None,"actual_pct":(projected-baseline)/baseline*100 if verified else None,
        "basis_by_dimension":{str(d):float(grouped[d]) for d in dim_values},"constraints":constraint_map,"default_bounds":{"min":-100,"max":100},
        "verification":{"all_bounds_satisfied":valid_bounds,"target_satisfied":target_met},"breakdown":breakdown,
        "limitations":["仅按份额分配与逐次剪裁构造并复核候选，不证明最优、最小变化或数学不可行。","算术情景不识别真实业务干预的因果收益。"]}
    return ToolResult(summary=("约束分配候选已核验" if verified else "当前份额/剪裁方法未找到同时满足全部边界与目标的候选，未交付分配方案。"),data=data)
