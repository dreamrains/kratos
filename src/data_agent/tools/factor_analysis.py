"""Original standardized OLS/HC3 association, with explicit data boundaries."""
from __future__ import annotations

import math
import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.api import OLS, add_constant
from statsmodels.stats.multitest import multipletests
from statsmodels.stats.outliers_influence import variance_inflation_factor
from data_agent.tools._utils import get_df
from data_agent.tools.method_contract import method_receipt
from data_agent.tools.registry import ToolResult


def _finite(value):
    return round(float(value), 8) if value is not None and math.isfinite(float(value)) else None


def _attribution_result(frame, arguments, identity):
    raw=arguments.get("features", "")
    features=[c.strip() for c in raw.split(",")] if raw else [c for c in frame.select_dtypes(include=[np.number]).columns if c!=arguments["target_col"]]
    return _factor_result(frame, arguments["name"], arguments["target_col"], features, arguments.get("unit_col", ""), arguments.get("time_col", ""), identity)


def _factor_result(frame, name, target, features, unit_col, time_col, identity):
    if not target or target not in frame.columns:
        raise ValueError("目标列不存在。")
    if any(not isinstance(c,str) or not c for c in features) or len(set(features))!=len(features):
        raise ValueError("特征列必须非空且不重复。")
    if target in features:
        raise ValueError("目标列不能作为自身特征。")
    missing=sorted(set(features+[c for c in [unit_col,time_col] if c])-set(frame.columns))
    if missing:raise ValueError(f"列不存在: {missing}")
    if frame.columns.duplicated().any():raise ValueError("数据列名重复，无法唯一绑定因素范围。")
    numeric={c:pd.to_numeric(frame[c],errors="coerce") for c in [target,*features]}
    y=numeric[target];excluded={};usable=[]
    for feature in features:
        value=numeric[feature]
        if value.nunique(dropna=True)<2:
            excluded[feature]="constant_or_non_numeric";continue
        # Preserve the existing exact ratio-identity exclusion.
        for other in features:
            if other==feature:continue
            other_value=numeric[other]
            valid=y.notna() & value.notna() & other_value.notna() & (other_value!=0)
            if valid.sum()>=3 and np.allclose(y[valid],value[valid]/other_value[valid],rtol=1e-7,atol=1e-9):
                excluded[feature]="mathematical_identity_with_target";break
        if feature not in excluded:usable.append(feature)
    working=pd.DataFrame({c:numeric[c] for c in [target,*usable]}).replace([np.inf,-np.inf],np.nan).dropna()
    mask=pd.DataFrame({c:numeric[c] for c in [target,*usable]}).replace([np.inf,-np.inf],np.nan).notna().all(axis=1)
    audits={}
    for c in [target,*features]:
        values=numeric[c];missing_raw=frame[c].isna()
        audits[c]={"missing_rows":int(missing_raw.sum()),"non_numeric_rows":int((~missing_raw & values.isna()).sum()),"nonfinite_rows":int((values.notna() & ~np.isfinite(values)).sum()),"used_for_filter":c==target or c in usable}
    for c in list(usable):
        if len(working) and working[c].nunique(dropna=True)<2:
            excluded[c]="constant_after_complete_case_filter";usable.remove(c)
    gaps=[]
    if len(frame)!=len(working):gaps.append(f"原范围排除 {len(frame)-len(working)} 条缺失、无法转为数值或非有限观测，仅 {len(working)} 条完整有限观测参与估计。")
    if excluded:gaps.append("特征未估计："+"、".join(c+"（"+reason+"）" for c,reason in excluded.items())+"。")
    limits=["结果仅为调整后的统计关联，不识别因果效应。","使用原按行标准化 OLS＋HC3、Holm 多重校正与 VIF；样本独立性仍未验证。","单位/时间列仅作范围说明，未按单位聚类、聚合或校正时间相关性。","缺失及数值转换失败的业务含义未知，不自动填补。"]
    unit_observation={"column":unit_col,"supplied":bool(unit_col)}
    time_observation={"column":time_col,"supplied":bool(time_col)}
    selected=frame.loc[mask]
    if unit_col:
        units=selected[unit_col];counts=units.dropna().value_counts()
        unit_observation.update(effective_rows=len(selected),missing_rows=int(units.isna().sum()),distinct_units=int(units.nunique(dropna=True)),repeated_units=int((counts>1).sum()),rows_in_repeated_units=int(counts[counts>1].sum()),used_for_grouping=False,used_as_feature=unit_col in usable)
    if time_col:
        raw=selected[time_col];parsed=pd.to_datetime(raw,errors="coerce");valid=parsed.dropna()
        time_observation.update(effective_rows=len(selected),missing_rows=int(raw.isna().sum()),invalid_rows=int((raw.notna() & parsed.isna()).sum()),valid_rows=len(valid),distinct_times=int(valid.nunique()),duplicate_rows=int(valid.duplicated().sum()),range=[valid.min().isoformat(),valid.max().isoformat()] if len(valid) else [None,None],used_for_correlation_correction=False,used_as_feature=time_col in usable)
    receipt=method_receipt(name,method="adjusted_factor_relationships",status="limited",effective_n=len(working),parameters={"target":target,"features":features,"analysis_unit":unit_col,"time_col":time_col},limitations=limits,claim_ceiling="associational",data_identity=identity)
    receipt.update(observation={"source_rows":len(frame),"effective_rows":len(working),"excluded_rows":len(frame)-len(working),"columns":audits},excluded_features=excluded,unstable_features=[],vif={},estimates=[],bivariate_associations=[],unit_observation=unit_observation,time_observation=time_observation,completion_gaps=gaps)
    def finish(reason):
        receipt["reason_code"]=reason
        receipt["top_drivers"]=receipt["estimates"] or receipt["bivariate_associations"]
        return receipt
    def unknown_estimates():
        return [{"feature":c,"coefficient":None,"confidence_interval_95":[None,None],"p_value":None,"p_value_holm":None,"vif":None,"reliable":None} for c in usable]
    if not usable or len(working)<len(usable)+5:
        gaps.append("完整有限观测或可识别特征不足，调整系数及推断未知。")
        receipt["estimates"]=unknown_estimates()
        return finish("insufficient_identifiable_data")
    if working[target].nunique()<2:
        gaps.append("目标为常数，标准化调整系数、区间、p 值及关联未知。")
        receipt["estimates"]=unknown_estimates()
        receipt["bivariate_associations"]=[{"feature":c,"pearson_r":None,"p_value":None,"n_pairs":len(working)} for c in usable]
        return finish("constant_target")
    design=working[usable].copy();design=(design-design.mean())/design.std(ddof=0)
    vifs={}
    for index,column in enumerate(usable):
        try:vifs[column]=float(variance_inflation_factor(add_constant(design).values,index+1))
        except (ValueError,np.linalg.LinAlgError,ZeroDivisionError):vifs[column]=float("nan")
    unstable=[c for c,v in vifs.items() if not np.isfinite(v) or v>=10];stable=[c for c in usable if c not in unstable]
    associations=[]
    for column in usable:
        coefficient,pvalue=stats.pearsonr(working[column],working[target])
        associations.append({"feature":column,"pearson_r":_finite(coefficient),"p_value":_finite(pvalue),"n_pairs":len(working)})
    receipt.update(unstable_features=unstable,vif={c:_finite(v) for c,v in vifs.items()})
    if unstable:gaps.append("VIF 过高或未知的特征不进入调整模型："+"、".join(unstable)+"。")
    if not stable:
        gaps.append("共线性使调整模型无法识别；仅保留未调整关联。")
        receipt["bivariate_associations"]=associations
        return finish("multicollinearity_prevents_attribution")
    try:
        x=add_constant(design[stable],has_constant="add")
        model=OLS((working[target]-working[target].mean())/working[target].std(ddof=0),x).fit(cov_type="HC3")
        raw=[float(model.pvalues[c]) for c in stable]
        adjusted=multipletests(raw,method="holm")[1] if all(np.isfinite(v) for v in raw) else [None]*len(raw)
        intervals=model.conf_int();estimates=[]
        for column,pvalue,corrected in zip(stable,raw,adjusted):
            low,high=intervals.loc[column];coef=model.params[column]
            known=all(v is not None and np.isfinite(v) for v in [coef,low,high,pvalue,corrected])
            estimates.append({"feature":column,"coefficient":_finite(coef),"confidence_interval_95":[_finite(low),_finite(high)],"p_value":_finite(pvalue),"p_value_holm":_finite(corrected),"vif":_finite(vifs[column]),"reliable":bool(corrected<.05 and (low>0 or high<0)) if known else None})
        if any(r["reliable"] is None for r in estimates):gaps.append("部分 HC3 推断无法计算，相关区间、p 值或可靠性为未知。")
    except (ValueError,np.linalg.LinAlgError,ZeroDivisionError):
        estimates=unknown_estimates();gaps.append("原 OLS＋HC3 无法完成计算；系数与推断未知，未更换算法。")
    reliable=[r for r in estimates if r["reliable"] is True]
    receipt.update(status="supported" if reliable else "limited",estimates=estimates,bivariate_associations=associations)
    return finish("adjusted_associations_found" if reliable else "no_adjusted_association")


def factor_relationships(name: str,target: str,features: list[str],unit_col: str="",time_col: str="") -> ToolResult:
    from data_agent.session.workspace import workspace
    frame,error=get_df(name)
    if error:return ToolResult(summary=error)
    try:data=_factor_result(frame,name,target,features,unit_col,time_col,workspace.get_data_identity(name))
    except (ValueError,TypeError) as exc:return ToolResult(summary=str(exc))
    return ToolResult(summary="已完成调整关联计算；"+data["reason_code"],data=data)
