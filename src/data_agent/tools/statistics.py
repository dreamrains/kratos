"""L3: 统计推断工具。"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
from scipy import stats as sp_stats

from data_agent.session.workspace import workspace
from data_agent.tools._utils import get_df
from data_agent.tools.registry import registry
from data_agent.agent.publication.native import MINIMAL_PRODUCT_CONTRACTS


@registry.register(
    name="ab_test",
    output_contract=MINIMAL_PRODUCT_CONTRACTS["ab_test"],
    description=(
        "进行 A/B 测试统计检验。比较两组之间的指标差异。"
        "auto 模式自动判断正态性并选择检验方法，附加 Levene 方差齐性检验。"
        "单位存在时先按 unit_aggregation 聚合；跨两组时固定配对设计，仅auto/ttest支持已有配对t与Wilcoxon附加结果。显式独立秩检验或chi2不会被替换。仅接受恰好两组，推断不足保留未知。"
    ),
    schema_overrides={
        "name": {"description": "数据集名称"},
        "group_col": {"description": "分组列名（二值列，区分实验组和对照组）"},
        "metric_col": {"description": "指标列名"},
        "unit_col": {"description": "分析单位列；为空时自动尝试 user_id。单位跨两组时按单位聚合后配对比较"},
        "unit_aggregation": {"description": "同一单位同组多行的聚合方式", "enum": ["sum", "mean"]},
        "method": {"description": "检验方法", "enum": ["auto", "ttest", "mannwhitneyu", "chi2"]},
    },
)
def ab_test(
    name: str,
    group_col: str,
    metric_col: str,
    method: str = "auto",
    unit_col: str = "",
    unit_aggregation: str = "sum",
) -> str:
    df, err = get_df(name)
    if err:
        return err
    def reject(code,message):
        return json.dumps({"error":message,"error_type":code},ensure_ascii=False)
    if method not in {"auto","ttest","mannwhitneyu","chi2"}:
        return reject("unsupported_ab_method","不支持的A/B方法；不会自动更换显式方法。")
    if group_col not in df.columns or metric_col not in df.columns:
        return reject("missing_ab_column",f"列不存在。可用列: {list(df.columns)}")
    if unit_aggregation not in {"sum","mean"}:
        return reject("invalid_unit_aggregation","unit_aggregation must be sum or mean")
    groups=df[group_col].dropna().unique().tolist()
    if len(groups)!=2 or len({str(v) for v in groups})!=2:
        return reject("invalid_ab_groups",f"A/B检验需要恰好2个可区分组，当前为{len(groups)}组。")
    unit=unit_col or ("user_id" if "user_id" in df.columns else "")
    if unit and unit not in df.columns:
        return reject("missing_analysis_unit",f"分析单位列 '{unit}' 不存在")
    working=pd.DataFrame({"group":df[group_col],"metric":df[metric_col]})
    if unit:working["unit"]=df[unit]
    working=working.dropna()
    if method!="chi2":
        numeric=pd.to_numeric(working["metric"],errors="coerce")
        if not np.isfinite(numeric.to_numpy(dtype=float)).all():
            return reject("non_numeric_metric",f"指标列 '{metric_col}' 包含非数值或非有限数据，无法进行统计检验")
        working["metric"]=numeric
    if unit:
        memberships=working.groupby("unit",sort=False)["group"].nunique()
        paired=bool((memberships>1).any())
        if paired and method in {"mannwhitneyu","chi2"}:
            return reject("incompatible_paired_method","当前单位跨组；显式方法要求独立组，不能改成配对t或按独立行计算。")
        if method=="chi2" and not pd.api.types.is_numeric_dtype(working["metric"]):
            if working.duplicated(["unit","group"]).any():
                return reject("unsupported_categorical_unit_aggregation","分类指标同单位多行不支持sum/mean聚合。")
            samples=working.groupby(["unit","group"],sort=False)["metric"].first().unstack()
        else:
            samples=working.groupby(["unit","group"],sort=False)["metric"].agg(unit_aggregation).unstack()
        if paired:
            groups=sorted(groups,key=lambda value:str(value))
            complete=samples.reindex(columns=groups).dropna()
            arrays=[complete[g].to_numpy(dtype=float) for g in groups]
            excluded=int(len(samples)-len(complete))
        else:
            arrays=[samples[g].dropna().to_numpy() if g in samples else np.array([]) for g in groups]
            excluded=0
    else:
        paired=False;excluded=0
        arrays=[working.loc[working["group"]==g,"metric"].to_numpy() for g in groups]
    limits=["分组或前后比较不识别因果效应；随机分配及独立性未经验证。",
            f"差值按第二组减第一组报告；组序为{[str(g) for g in groups]}。"]
    if unit:limits.append(f"分析单位为{unit}，同单位同组按{unit_aggregation}聚合；配对只使用完整单位。")
    result={"group_col":group_col,"metric_col":metric_col,"requested_method":method,
            "method":"paired_ttest" if paired else method,"design":"paired" if paired else "independent",
            "analysis_unit":unit or "row","unit_aggregation":unit_aggregation if unit else None,
            "source_rows":int(len(df)),"complete_case_rows":int(len(working)),
            "assumptions":{"random_assignment":"unverified","independence":"unverified"},"limitations":limits,
            "status":"supported","reason_code":None}
    if method=="chi2":
        rows=[{"group":str(g),"metric":str(v)} for g,values in zip(groups,arrays) for v in values]
        table=pd.crosstab(pd.Series([r["group"] for r in rows]),pd.Series([r["metric"] for r in rows]))
        if table.shape[0]!=2 or table.shape[1]<2:
            return reject("insufficient_contingency","chi2检验需要两个非空组和至少两个类别。")
        stat,p_value,dof,expected=sp_stats.chi2_contingency(table)
        result.update(groups={str(g):{"n":int(len(a))} for g,a in zip(groups,arrays)},
                      contingency_table={str(g):{str(c):int(table.loc[str(g),c]) for c in table.columns} for g in groups},
                      expected_counts={str(g):{str(c):float(expected[table.index.get_loc(str(g)),i]) for i,c in enumerate(table.columns)} for g in groups},
                      method="chi2",test={"statistic":round(float(stat),4),"p_value":round(float(p_value),6),"dof":int(dof),"significant":bool(p_value<.05),"correction":"Yates" if dof==1 else "none"})
        limits.append("卡方使用独立单位列联表；小期望频数可能不满足渐近近似，未改用其他检验。")
        return json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)
    a,b=[np.asarray(v,dtype=float) for v in arrays]
    if not all(np.isfinite(v).all() for v in (a,b)):
        return reject("nonfinite_unit_aggregate","单位聚合溢出或产生非有限值。")
    if not paired and min(len(a),len(b))<2:
        return reject("insufficient_group_observations","Error: 每组至少需要2个有效分析单位。")
    means=[float(np.mean(v)) if len(v) else None for v in (a,b)]
    variances=[float(np.var(v,ddof=1)) if len(v)>=2 else None for v in (a,b)]
    result["exact_statistics"]={str(g):{"n":int(len(v)),"mean":m,"sample_variance":var} for g,v,m,var in zip(groups,(a,b),means,variances)}
    result["groups"]={str(g):{"n":int(len(v)),"mean":round(m,4) if m is not None else None,
                        "std":round(float(np.std(v,ddof=1 if paired else 0)),4) if len(v)>(1 if paired else 0) else None} for g,v,m in zip(groups,(a,b),means)}
    diff=means[1]-means[0] if None not in means else None
    result["difference"]={"absolute":round(diff,4) if diff is not None else None,
                          "relative_pct":round(diff/abs(means[0])*100,2) if diff is not None and means[0] else None}
    result["test"]={"statistic":None,"p_value":None,"significant":None,"difference_direction":"second_minus_first"}
    if paired:
        n=len(a);result.update(paired_sample_size=n,excluded_unpaired_units=excluded,selection_reason="同一分析单位跨组，保留配对设计。")
        differences=b-a;sd=float(np.std(differences,ddof=1)) if n>=2 else None
        result["difference"].update(cohens_dz=round(diff/sd,4) if sd else None,confidence_interval_95=None)
        result["paired_difference_statistics"]={"mean":diff,"sample_variance":sd*sd if sd is not None else None,"n":n}
        result["wilcoxon_signed_rank"]={"p_value":None,"alternative":"two-sided","zero_method":"wilcox","method":"auto"}
        if n>=2 and not np.all(differences==0):
            result["wilcoxon_signed_rank"]["p_value"]=round(float(sp_stats.wilcoxon(a,b).pvalue),6)
        if n<2 or not sd:
            result.update(status="limited",reason_code="insufficient_pairs" if n<2 else "degenerate_t_variance")
            limits.append("完整配对不足两对或差值方差退化；配对t的区间、p值及显著性未知，不退回独立行检验。")
        else:
            stat,p_value=sp_stats.ttest_rel(b,a);se=sd/np.sqrt(n);critical=float(sp_stats.t.ppf(.975,n-1))
            result["difference"]["confidence_interval_95"]=[round(diff-critical*se,4),round(diff+critical*se,4)]
            result["test"].update(statistic=round(float(stat),4),p_value=round(float(p_value),6),significant=bool(p_value<.05),degrees_of_freedom=n-1)
    else:
        pooled=sum(variances)/2 if None not in variances else None
        result["difference"]["cohens_d"]=round(diff/np.sqrt(pooled),4) if pooled and diff is not None else None
        equal_var=False
        levene_result={"statistic":None,"p_value":None,"equal_variance":None}
        if min(len(a),len(b))>=2 and pooled:
            levene=sp_stats.levene(a,b);lp=float(levene.pvalue);ls=float(levene.statistic)
            equal_var=bool(lp>.05) if np.isfinite(lp) else False
            levene_result={"statistic":round(ls,4) if np.isfinite(ls) else None,"p_value":round(lp,6) if np.isfinite(lp) else None,"equal_variance":equal_var}
        result["levene_test"]=levene_result
        normality={}
        for g,v in zip(groups,(a,b)):
            eligible=3<=len(v)<5000 and np.ptp(v)>0
            p=float(sp_stats.shapiro(v).pvalue) if eligible else None
            normality[str(g)]={"n":int(len(v)),"p_value":p,"status":"tested" if eligible else "unassessed"}
        result["normality"]=normality
        if method=="auto":
            method="ttest" if all(v["p_value"] is not None and v["p_value"]>.05 for v in normality.values()) else "mannwhitneyu"
            result["method"]=method
            result["selection_reason"]="两组Shapiro检查均通过，选择t检验。" if method=="ttest" else "正态性不足以核验或检查未通过，选择已有双侧秩检验。"
        else:result["selection_reason"]="使用显式方法；不把正态性或独立性当作已证明。"
        if min(len(a),len(b))<2:
            result.update(status="limited",reason_code="insufficient_group_observations")
        elif method=="ttest" and not pooled:
            result.update(status="limited",reason_code="degenerate_t_variance")
        else:
            if method=="ttest":
                stat,p_value=sp_stats.ttest_ind(b,a,equal_var=equal_var)
                result["test"]["variance_model"]="pooled" if equal_var else "welch"
            else:
                stat,p_value=sp_stats.mannwhitneyu(a,b,alternative="two-sided")
                result["test"]["statistic_reference"]="first_group_U"
            result["test"].update(statistic=round(float(stat),4),p_value=round(float(p_value),6),significant=bool(p_value<.05))
        if result["status"]=="limited":limits.append("组样本不足或t方差退化；保留可计算均值和差值，推断未知。")
    return json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)


@registry.register(
    name="causal_analysis",
    output_contract=MINIMAL_PRODUCT_CONTRACTS["causal_analysis"],
    description=(
        "因果分析：DID（双重差分）；当前采用四格独立组均值与正态近似，平行趋势未验证。缺格不计算效应，任一格不足两条仅交付点估计。"
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
    def error(reason):
        return json.dumps({"error": reason, "error_type": "invalid_did_input"}, ensure_ascii=False)
    if outcome_col and target_col and outcome_col != target_col:
        return error("outcome_col 与 target_col 指向不同指标。")
    outcome = target_col or outcome_col
    if not outcome or not time_col or method != "did":
        return error("DID 需要 outcome_col/target_col、time_col 且 method=did。")
    df, err = get_df(name)
    if err: return err
    required = list(dict.fromkeys([treatment_col, outcome, time_col]))
    missing = [c for c in required if c not in df.columns]
    if missing: return error(f"列不存在: {missing}")
    working = df[required].dropna().copy()
    for column in required:
        working[column] = pd.to_numeric(working[column], errors="coerce")
        if not np.isfinite(working[column]).all():
            return error(f"列 {column} 包含非数值或非有限观测。")
    if any(not set(working[column]).issubset({0, 1}) for column in (treatment_col, time_col)):
        return error("treatment_col 与 time_col 必须使用 0/1，不能截断或忽略其他组/期。")
    means, variances, counts = {}, {}, {}
    for treatment in (0, 1):
        for period in (0, 1):
            key = f"treatment={treatment}_period={period}"
            values = working.loc[(working[treatment_col] == treatment) & (working[time_col] == period), outcome].to_numpy(dtype=float)
            counts[key] = len(values)
            means[key] = float(values.mean()) if len(values) else None
            variances[key] = float(values.var(ddof=1)) if len(values) >= 2 else None
    result = {
        "method": "DID", "treatment_col": treatment_col, "outcome_col": outcome, "time_col": time_col,
        "group_means": {key: round(value, 4) if value is not None else None for key, value in means.items()},
        "exact_cell_means": means, "cell_counts": counts, "cell_variances": variances,
        "source_rows": len(df), "excluded_missing_rows": len(df)-len(working), "total_observations": len(working),
        "assumptions": {"parallel_trends": "unverified", "independent_groups": "unverified"},
        "test_distribution": "normal_approximation",
        "limitations": [
            "DID 差中差点估计的因果解读依赖平行趋势等尚未验证的假设，计算完成不证明因果。",
            "区间及p值采用四格独立组方差和正态近似，未校正重复个体、聚类或序列相关。",
            "仅有0/1两期，不能验证平行趋势；基线水平差异不等于趋势差异。",
        ],
        "status": "limited", "did_effect": None, "standard_error": None, "ci_95": None,
        "t_statistic": None, "p_value": None, "significant_at_005": None,
    }
    if any(n == 0 for n in counts.values()):
        result.update(reason_code="missing_did_cell", inference_limitation="缺少处理组×期次单元，DID点估计、区间及p值未知；不以零填补。")
    else:
        control_diff = means["treatment=0_period=1"] - means["treatment=0_period=0"]
        treat_diff = means["treatment=1_period=1"] - means["treatment=1_period=0"]
        effect = treat_diff - control_diff
        result.update(treatment_diff=round(treat_diff, 4), control_diff=round(control_diff, 4), did_effect=round(effect, 4))
        if any(value is None for value in variances.values()):
            result.update(reason_code="insufficient_did_cell_variance", inference_limitation="任一单元不足两条观测，无法估计所需样本方差；仅交付点估计，区间及p值未知。")
        else:
            se = float(np.sqrt(sum(variances[key] / counts[key] for key in counts)))
            result["standard_error"] = round(se, 4)
            if se == 0:
                result.update(reason_code="degenerate_did_variance", inference_limitation="四格样本方差退化为零，无法进行有限标准误下的正态近似检验；区间及p值未知。")
            else:
                z = effect / se
                p_value = float(2 * sp_stats.norm.sf(abs(z)))
                result.update(status="supported", reason_code="did_calculated", ci_95=[round(effect-1.96*se, 4), round(effect+1.96*se, 4)],
                    t_statistic=round(z, 4), p_value=round(p_value, 6), significant_at_005=bool(p_value < .05))
    if result.get("inference_limitation"): result["limitations"].append(result["inference_limitation"])
    return json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2)


@registry.register(
    name="shap_analysis",
    output_contract=MINIMAL_PRODUCT_CONTRACTS["shap_analysis"],
    description="使用 SHAP 值分析已训练模型的特征重要性。需要先通过 regression_analysis 或 classification 训练模型。",
    # The implementation checks the exact current trained model; either family suffices.
    schema_overrides={
        "name": {"description": "数据集名称"},
        "target_col": {"description": "目标变量列"},
        "model_kind": {"description": "auto仅匹配本会话当前数据版的唯一模型；有两种时需显式选择", "enum": ["auto", "regression", "classification"]},
    },
)
def shap_analysis(name: str, target_col: str, model_kind: str = "auto") -> str:
    from data_agent.tools.ml import _trained_models,_trained_model_metadata,_model_key
    if model_kind not in {"auto","regression","classification"}:
        return json.dumps({"error":"不支持的model_kind","error_type":"invalid_model_kind"},ensure_ascii=False)
    current=[];stale=False
    for kind in (("regression","classification") if model_kind=="auto" else (model_kind,)):
        model_key=_model_key(name,kind,target_col)
        if model_key in _trained_models:
            metadata=_trained_model_metadata.get(model_key,{})
            if metadata.get("data_identity")!=workspace.get_data_identity(name):
                stale=True;continue
            current.append((kind,model_key,_trained_models[model_key],metadata))
    if len(current)>1:return json.dumps({"error":"当前目标同时存在回归和分类模型；请显式选择model_kind。","error_type":"ambiguous_current_model"},ensure_ascii=False)
    if not current:return json.dumps({"error":f"当前会话和数据版未找到目标'{target_col}'的已训练模型。请先训练。","error_type":"stale_model_data_identity" if stale else "missing_current_model"},ensure_ascii=False)
    kind,model_key,model,metadata=current[0]
    df,err=get_df(name)
    if err:return err
    feature_cols=list(metadata.get("feature_cols",[]))
    if not feature_cols or any(c not in df.columns for c in feature_cols):return json.dumps({"error":"模型原特征缺失","error_type":"model_feature_mismatch"},ensure_ascii=False)
    data=df[feature_cols].dropna()
    if data.empty:return json.dumps({"error":"没有可解释的完整特征观测","error_type":"insufficient_explanation_rows"},ensure_ascii=False)
    try:
        import shap
        values=shap.TreeExplainer(model).shap_values(data[feature_cols])
        values=np.stack(values,axis=-1) if isinstance(values,list) else np.asarray(values)
        if not np.isfinite(values).all():raise ValueError("SHAP返回非有限值")
        if values.shape[:2]!=(len(data),len(feature_cols)):raise ValueError("SHAP样本/特征轴与原模型不一致")
        def rows(weights):return [{"feature":feature,"mean_abs_shap":round(float(weight),6)} for feature,weight in sorted(zip(feature_cols,weights),key=lambda pair:-pair[1])]
        per_class=[];missing_classes=[];status="supported";reason=None
        mapping=metadata.get("label_mapping",[])
        if kind=="classification":
            if values.ndim==3 and values.shape[2]==len(mapping):
                per_class=[{"label":entry["label"],"importance":rows(np.abs(values[:,:,i]).mean(axis=0))} for i,entry in enumerate(mapping)]
                overall=np.abs(values).mean(axis=(0,2));aggregation="equal_weight_mean_across_classes"
            elif values.ndim==2 and len(mapping)==2:
                # Some binary tree estimators explain one margin only. Preserve
                # that actual output; never invent the other class by negation.
                per_class=[{"label":mapping[1]["label"],"importance":rows(np.abs(values).mean(axis=0))}]
                missing_classes=[mapping[0]["label"]];overall=None;aggregation="single_model_output"
                status="limited";reason="unexplained_class_output"
            else:raise ValueError("SHAP类别轴与原标签映射不一致")
        else:
            if values.ndim!=2:raise ValueError("单目标回归SHAP形状不匹配")
            overall=np.abs(values).mean(axis=0);aggregation="mean_abs_across_observations"
        result={"method_contract":"analysis_method_result.v1","status":status,"reason_code":reason,
                "data_identity":metadata["data_identity"],"model_identity":{k:metadata.get(k) for k in ("model_key","kind","target_col","feature_cols","label_mapping")},
                "claim_ceiling":"associational","limitations":["SHAP解释当前模型预测，不识别因果效应。","按实际返回的类别轴保留逐类绝对均值；完整分类总体重要性采用各类等权平均。"],
                "model_type":type(model).__name__,"target":target_col,"n_features":len(feature_cols),"n_observations":len(data),"aggregation":aggregation,
                "shap_importance":rows(overall) if overall is not None else None,"per_class_importance":per_class,"unexplained_classes":missing_classes}
        if missing_classes:result["limitations"].append("模型仅返回一个分类输出；其他类别未解释，完整各类平均重要性未知，不由首类冒充。")
        return json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)
    except ImportError:return json.dumps({"error":"SHAP未安装","error_type":"missing_shap_dependency"},ensure_ascii=False)
    except Exception as exc:return json.dumps({"error":f"TreeExplainer解释失败: {exc}","error_type":"unsupported_or_invalid_shap_output"},ensure_ascii=False)
