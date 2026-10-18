"""L2: 探索性分析工具。"""

from __future__ import annotations

import json
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats as sp_stats

from data_agent.session.workspace import workspace
from data_agent.tools._utils import get_df, safe_jsonify, resolve_date_col, parse_period_range, inclusive_date_period_mask, analyze_period_structure, compare_period_structures
from data_agent.tools.registry import ToolResult
from data_agent.agent.publication.native import MINIMAL_PRODUCT_CONTRACTS
from data_agent.tools.registry import registry


@registry.register(
    name="analyze_time_series",
    output_contract=MINIMAL_PRODUCT_CONTRACTS["analyze_time_series"],
    description=(
        "原逐记录时间趋势、滑窗变化与自相关候选；不证明季节性或变点。"
        "使用场景：指标随时间变化的趋势方向、周期性检测、异常时间点定位。"
        "不适用场景：无时间列的数据、跨维度对比（用 compare_periods）。"
        "参数说明：date_col 和 value_col 可自动推断（留空即可），target_col 为 value_col 的别名。"
        "日期按原口径解析；显式错列、数值转换失败及两个目标别名冲突会拒绝。"
    ),
    recovery_hint=(
        "时间序列分析需要日期列和数值列。"
        "请用 describe_dataset 检查列类型：date_col 应为 datetime，value_col 应为数值。"
        "如数据点不足 3 个，使用 distribution_analysis 替代。"
    ),
    schema_overrides={
        "name": {"description": "数据集名称"},
        "date_col": {"description": "日期/时间列名，留空自动推断"},
        "value_col": {"description": "数值列名，留空自动推断"},
        "target_col": {"description": "目标列名（value_col 的别名）"},
    },
)
def analyze_time_series(name: str, date_col: str = "", value_col: str = "", target_col: str = "") -> str:
    df,err=get_df(name)
    if err:return err
    try:result=_time_series_result(df,{"name":name,"date_col":date_col,"value_col":value_col,"target_col":target_col})
    except (ValueError,TypeError,OverflowError) as exc:return "Error: "+str(exc)
    return json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)


def _time_series_result(df,arguments):
    date_col=arguments.get("date_col","");value_col=arguments.get("value_col","");target_col=arguments.get("target_col","")
    if value_col and target_col and value_col!=target_col:raise ValueError("value_col 与 target_col 冲突；请选择唯一目标列。")
    if df.columns.duplicated().any():raise ValueError("列名重复，无法唯一绑定时间序列范围。")
    for c in [date_col,value_col,target_col]:
        if c and c not in df.columns:raise ValueError(f"列不存在: {c}")
    inferred={}
    if not date_col:
        dt_cols=[c for c in df.columns if pd.api.types.is_datetime64_any_dtype(df[c])]
        if dt_cols:date_col=dt_cols[0]
        else:
            for c in df.columns:
                if pd.api.types.is_object_dtype(df[c]) or pd.api.types.is_string_dtype(df[c]):
                    try:pd.to_datetime(df[c].dropna().head(20));date_col=c;break
                    except (ValueError,TypeError):continue
        if date_col:inferred["date_col"]=date_col
    col=target_col or value_col
    if not col:
        num_cols=df.select_dtypes(include=[np.number]).columns
        for c in num_cols:
            nunique=df[c].nunique()
            if nunique>2 and nunique>len(df)*.01:col=c;break
        if not col and len(num_cols):col=num_cols[0]
        if col:inferred["value_col"]=col
    if not date_col:raise ValueError("无法自动推断日期列，请指定 date_col。")
    if not col:raise ValueError("无法自动推断数值列，请指定 value_col。")
    if date_col==col:raise ValueError("日期与数值角色不能绑定同一列。")
    dates=pd.to_datetime(df[date_col],errors="coerce")
    try:converted=df[col].astype(float)
    except (ValueError,TypeError,OverflowError) as exc:raise ValueError("数值列存在无法按原 float 口径转换的值，未静默排除或换列。") from exc
    finite=np.isfinite(converted);mask=dates.notna() & converted.notna() & finite
    ts=pd.DataFrame({"date":dates[mask],"value":converted[mask]}).sort_values("date");values=ts["value"].to_numpy(dtype=float);n=len(values)
    deltas=ts["date"].diff().dropna()
    observation={"source_rows":len(df),"effective_rows":n,"excluded_rows":len(df)-n,"missing_date":int(df[date_col].isna().sum()),"invalid_date":int((df[date_col].notna() & dates.isna()).sum()),"missing_value":int(df[col].isna().sum()),"nonfinite_value":int((converted.notna() & ~finite).sum()),"duplicate_date_rows":int(ts["date"].duplicated().sum()),"unique_dates":int(ts["date"].nunique()),"equal_intervals":bool(deltas.nunique()==1) if len(deltas) else None}
    gaps=[f"原范围排除 {len(df)-n} 条缺失、坏日期或非有限值；仅 {n} 条有限有效记录已计算。"] if n<len(df) else []
    def finite_value(v,digits=4):return round(float(v),digits) if np.isfinite(v) else None
    result={"data_points":n,"date_range":{"start":safe_jsonify(ts['date'].iloc[0]) if n else None,"end":safe_jsonify(ts['date'].iloc[-1]) if n else None},"statistics":{"mean":finite_value(np.mean(values)) if n else None,"std":finite_value(np.std(values)) if n else None,"min":finite_value(np.min(values)) if n else None,"max":finite_value(np.max(values)) if n else None},"inferred_columns":inferred,"parameters":{"date_col":date_col,"value_col":col},"observation":observation,"status":"partial" if gaps else "supported","completion_gaps":gaps,"claim_ceiling":"descriptive","limitations":["斜率及自相关滞后以每条排序观测为单位，不是每个自然日；重复日期保留逐记录，未自动聚合。","原线性回归 p 值未校正时间相关；样本独立性未验证，不授予预测或因果验证。","原序列自相关阈值仅为启发候选，不证明季节性；未去趋势或另做季节检验。","滑窗均值差是描述性比较，阈值10%未经变点检验或多重校正；零前均值的百分比和阈值判定未知。","排除项的业务含义未知，不静默填补。"]}
    trend={"axis":"sorted_observation_index","direction":None,"slope":None,"r_squared":None,"p_value":None,"significant":None,"inference_limitation":"不足3条有效观测，原线性回归未计算。"}
    if n>=3:
        slope,intercept,r_value,p_value,std_err=sp_stats.linregress(np.arange(n),values)
        trend.update(direction="up" if slope>0 else "down" if slope<0 else "flat",slope=finite_value(slope),r_squared=finite_value(r_value**2),p_value=finite_value(p_value,6),significant=bool(p_value<.05) if np.isfinite(p_value) else None,inference_limitation="常数或退化观测的推断未知。" if not np.isfinite(p_value) else "")
    result["trend"]=trend
    comparisons=[];changes=[];window=max(3,n//5)
    if n>=10:
        for i in range(window,n-window):
            before=float(np.mean(values[i-window:i]));after=float(np.mean(values[i:i+window]));pct=(after-before)/abs(before)*100 if before!=0 else None
            exceeds=bool(abs(pct)>10) if pct is not None and np.isfinite(pct) else None
            row={"index":i,"date":safe_jsonify(ts["date"].iloc[i]),"window_size":window,"before_mean":before,"after_mean":after,"absolute_change":after-before,"change_pct":finite_value(pct,2) if pct is not None else None,"threshold_exceeded":exceeds,"direction":"increase" if after>before else "decrease" if after<before else "unchanged"}
            comparisons.append(row)
            if exceeds:changes.append(dict(row))
    changes.sort(key=lambda r:abs(r["change_pct"]),reverse=True)
    result.update(window_comparisons=comparisons,change_points=changes)
    acf=[]
    if n>=14:
        for lag in range(1,min(n//2,30)+1):
            a,b=values[:-lag],values[lag:]
            value=float(np.corrcoef(a,b)[0,1]) if len(a)>2 and np.std(a)>0 and np.std(b)>0 else float("nan")
            acf.append({"lag":lag,"autocorrelation":finite_value(value),"n_pairs":len(a)})
    valid=[row for row in acf if row["autocorrelation"] is not None]
    best=max(valid,key=lambda row:abs(row["autocorrelation"])) if valid else None
    result["autocorrelation"]=acf
    result["seasonality"]={"strongest_lag":best["lag"] if best else None,"lag_unit":"sorted_observations","autocorrelation":best["autocorrelation"] if best else None,"threshold_exceeded":bool(abs(best["autocorrelation"])>.5) if best else None,"seasonality_validated":False,"interpretation":"heuristic_autocorrelation_candidate"}
    result["suggested_next"]=["correlation_analysis 检查哪些指标与目标变量相关","distribution_analysis 检查目标变量分布特征"]
    return result


@registry.register(
    name="correlation_analysis",
    output_contract=MINIMAL_PRODUCT_CONTRACTS["correlation_analysis"],
    description=(
        "计算数值列之间的相关系数矩阵，识别高相关性变量对。"
        "使用场景：发现指标间的关联关系、筛选冗余特征、为归因分析提供线索。"
        "不适用场景：类别型变量（无法计算相关系数）、非线性关系（考虑用 distribution_analysis）。"
        "参数说明：columns 留空分析所有数值列，method 支持 pearson/spearman/kendall。"
        "常见错误：非数值列会被自动过滤，如遗漏请用 describe_dataset 检查类型。"
    ),
    schema_overrides={
        "name": {"description": "数据集名称"},
        "columns": {"description": "数值列，逗号分隔，为空则分析所有数值列"},
        "method": {"description": "相关系数方法", "enum": ["pearson", "spearman", "kendall"]},
    },
)
def correlation_analysis(name: str, columns: str = "", method: str = "pearson") -> str:
    df, err = get_df(name)
    if err:
        return err

    numeric_df = df.select_dtypes(include=[np.number])
    if columns:
        cols = list(dict.fromkeys(c.strip() for c in columns.split(",") if c.strip()))
        numeric_df = numeric_df[[c for c in cols if c in numeric_df.columns]]

    if numeric_df.empty:
        return "Error: 没有可分析的数值列"

    if method not in {"pearson", "spearman", "kendall"}:
        return json.dumps({"error": "method must be pearson, spearman or kendall", "error_type": "unsupported_correlation_method"}, ensure_ascii=False)
    # Pairwise finite observations retain each method's existing estimator.
    from data_agent.tools._utils import finite_pairwise_correlation
    numeric_df, corr, pairwise_counts = finite_pairwise_correlation(numeric_df, method)
    excluded_columns = list(dict.fromkeys(c for c in (cols if columns else df.columns) if c not in numeric_df.columns))

    # 完整矩阵（详情）
    full_matrix = {}
    cols_list = list(corr.columns)
    for c1 in cols_list:
        full_matrix[c1] = {}
        for c2 in cols_list:
            coefficient = float(corr.loc[c1, c2])
            defined = np.isfinite(coefficient) and pairwise_counts[c1][c2] >= 2
            if c1 == c2 and numeric_df[c1].nunique(dropna=True) < 2:
                defined = False  # Approved: undefined self-correlation remains unknown.
            full_matrix[c1][c2] = round(coefficient, 4) if defined else None

    # 高相关性列表（摘要）
    high_correlations = []
    for i, c1 in enumerate(cols_list):
        for j, c2 in enumerate(cols_list):
            if i < j:
                val = round(float(corr.loc[c1, c2]), 4)
                if abs(val) > 0.3:
                    high_correlations.append({
                        "var1": c1,
                        "var2": c2,
                        "correlation": val,
                        "strength": "strong" if abs(val) > 0.7 else "moderate" if abs(val) > 0.5 else "weak",
                    })

    result = {
        "method": method,
        "columns_analyzed": cols_list,
        "correlation_matrix": full_matrix,
        "pairwise_counts": pairwise_counts,
        "excluded_columns": excluded_columns,
        "high_correlations": high_correlations,
        "limitations": [
            "仅描述所选数值列的成对关联，不证明因果或已验证预测；系数无量纲。",
            "各对仅使用共同有限观测；常数列或不足观测的未定义系数为 null（未知），不是零相关。",
            "high_correlations 只列绝对值大于0.3的变量对；完整矩阵保留弱相关、零相关与未知系数。",
        ],
        "suggested_next": [
            "distribution_analysis 检查相关变量的分布特征",
            "regression_analysis 建立回归模型量化影响",
        ],
    }

    return json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2)


@registry.register(
    name="distribution_analysis",
    output_contract=MINIMAL_PRODUCT_CONTRACTS["distribution_analysis"],
    description="分析数值列的分布特征：偏度、峰度、正态性。完整分位数详情自动持久化。",
)
def distribution_analysis(name: str, columns: str = "") -> str:
    df, err = get_df(name)
    if err:return err
    try:selected=_distribution_columns(df,columns)
    except ValueError as exc:return json.dumps({"error":str(exc),"error_type":"invalid_parameter"},ensure_ascii=False)
    result={}
    def finite(value):return round(float(value),4) if np.isfinite(value) else None
    for col in selected:
        values,observation=_distribution_observations(df[col]);n=len(values)
        constant=bool(n and np.all(values==values[0]))
        with np.errstate(all="ignore"):
            mean=finite(np.mean(values)) if n else None
            std=finite(np.std(values,ddof=0)) if n else None
            skew=finite(sp_stats.skew(values)) if n>=2 and not constant else None
            kurt=finite(sp_stats.kurtosis(values)) if n>=2 and not constant else None
        reason="insufficient_sample" if n<3 else "sample_limit" if n>=5000 else "constant_sample" if constant else ""
        normality={"test":"shapiro","p_value":None,"reject_normality":None,"conclusion":"unknown","reason":reason}
        if not reason:
            _,p=sp_stats.shapiro(values)
            if np.isfinite(p):
                reject=bool(p<=.05)
                normality.update(p_value=float(p),reject_normality=reject,conclusion="rejected" if reject else "not_rejected")
            else:normality["reason"]="undefined_test"
        result[col]={"count":n,"mean":mean,"std":std,"skewness":skew,"kurtosis":kurt,
            "normality_test":normality,"observation":observation,"constant_sample":constant,
            "quantiles":_distribution_quantiles(values),"quantile_interpolation":"linear",
            "status":"partial" if observation["excluded_nonfinite"] else "complete",
            "limitations":["仅对有限观测计算；缺失的业务含义未知。","总体标准差 ddof=0；偏度/峰度沿原有偏置矩估计。",
                "Shapiro p>0.05仅表示未拒绝正态性，不能证明正态；退化、不足三条或达到5000条时推断未知。"]}
    result["_suggested_next"]=["correlation_analysis 检查变量间相关性","segmentation_analysis 基于分布特征进行分群"]
    return json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)


def _distribution_columns(frame,columns):
    numeric=list(frame.select_dtypes(include=[np.number]).columns)
    if columns:
        selected=[c.strip() for c in columns.split(",")]
        if any(not c for c in selected) or len(set(selected))!=len(selected):raise ValueError("分布列必须非空且不重复")
        invalid=[c for c in selected if c not in numeric]
        if invalid:raise ValueError(f"分布列不存在或不是数值列: {invalid}")
    else:selected=numeric
    if not selected:raise ValueError("没有可分析的数值列")
    return selected


def _distribution_quantiles(values):
    keys=("min","25%","50%","75%","max")
    if not len(values):return dict.fromkeys(keys)
    with np.errstate(all="ignore"):
        measured=pd.Series(values).quantile([0.,.25,.5,.75,1.],interpolation="linear")
    return {key:float(value) if np.isfinite(value) else None for key,value in zip(keys,measured)}


def _distribution_observations(series):
    observed=series.dropna().to_numpy()
    values=observed[np.isfinite(observed)]
    return values,{"source_rows":len(series),"missing_count":int(series.isna().sum()),
        "excluded_nonfinite":len(observed)-len(values),"count":len(values)}


@registry.register(
    name="segmentation_analysis",
    output_contract=MINIMAL_PRODUCT_CONTRACTS["segmentation_analysis"],
    description="基于特征进行用户/数据分群（KMeans聚类）。",
    schema_overrides={
        "name": {"description": "数据集名称"},
        "features": {"description": "分群特征列，逗号分隔"},
        "n_clusters": {"description": "聚类数量"},
    },
)
def segmentation_analysis(name: str, features: str, n_clusters: int = 3) -> str:
    df, err = get_df(name)
    if err:return err
    try:result=_segmentation_result(df,{"features":features,"n_clusters":n_clusters})
    except (ValueError,TypeError) as exc:return "Error: "+str(exc)
    return json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)


def _segmentation_result(frame,arguments):
    """One owner for original standardized KMeans and its actual observation scope."""
    from sklearn.cluster import KMeans
    from sklearn.preprocessing import StandardScaler
    features=[c.strip() for c in arguments["features"].split(",")]
    if not features or any(not c for c in features) or len(set(features))!=len(features):
        raise ValueError("分群特征必须非空且不重复。")
    invalid=[c for c in features if c not in frame.columns or not pd.api.types.is_numeric_dtype(frame[c])]
    if invalid:raise ValueError("分群特征不存在或不是数值列: "+str(invalid))
    if any(not np.isfinite(frame[c].dropna().to_numpy()).all() for c in features):
        raise ValueError("分群特征存在非有限值；不静默排除或填补。")
    requested=arguments.get("n_clusters",3)
    if type(requested) is not int or requested<1:raise ValueError("n_clusters 必须为正整数。")
    data=frame[features].dropna()
    observation={"source_rows":len(frame),"effective_rows":len(data),"excluded_rows":len(frame)-len(data),
        "missing_by_feature":{c:int(frame[c].isna().sum()) for c in features}}
    if len(data)<requested:raise ValueError(f"有效数据 ({len(data)}) 少于聚类数 ({requested})")
    scaled=StandardScaler().fit_transform(data)
    labels=KMeans(n_clusters=requested,random_state=42,n_init=10).fit_predict(scaled)
    clusters=[]
    def finite(value):return round(float(value),4) if np.isfinite(value) else None
    for label in sorted(set(labels)):
        cluster=data[labels==label]
        profile={c:{"mean":finite(cluster[c].mean()),"std":finite(cluster[c].std(ddof=1)) if len(cluster)>1 else None} for c in features}
        clusters.append({"cluster_id":int(label),"size":len(cluster),"percentage":round(len(cluster)/len(data)*100,2),"profile":profile})
    actual=len(clusters);gaps=[]
    if observation["excluded_rows"]:gaps.append(f"原范围有{observation['excluded_rows']}条记录因特征缺失被排除；仅{len(data)}条完整特征记录已聚类。")
    if actual!=requested:gaps.append(f"请求{requested}簇，实际仅{actual}个非空簇；不能制造额外客群差异。")
    if any(v is None for c in clusters for p in c["profile"].values() for v in p.values()):gaps.append("单记录簇的样本标准差或退化描述量未知，可计算均值与人数保留。")
    return {"requested_n_clusters":requested,"n_clusters":actual,"total_samples":len(data),"clusters":clusters,
        "observation":observation,"analysis_unit":"input_record",
        "parameters":{"features":features,"n_clusters":requested,"scaler":"StandardScaler","algorithm":"KMeans","random_state":42,"n_init":10},
        "status":"partial" if gaps else "complete","completion_gaps":gaps,
        "limitations":[f"请求{requested}簇，实际{actual}个非空簇；簇编号只是当前模型标签，不代表业务等级。",
            "按输入记录聚类，不证明记录等于独立用户；不证明因果、稳定客群差异或预测有效。",
            "仅使用所选特征均非缺失的记录；按列缺失数可能重叠，联合排除只计一次；缺失业务含义未知。",
            "StandardScaler标准化后沿原KMeans(random_state=42,n_init=10)；profile按原尺度计算均值和ddof=1样本标准差，单记录标准差未知。"]}


@registry.register(
    name="cohort_analysis",
    output_contract=MINIMAL_PRODUCT_CONTRACTS["cohort_analysis"],
    description=(
        "进行留存分析。user_col 必须是唯一用户ID列（如 user_id），"
        "time_col 是事件时间列，event_col 是可选的事件类型列。"
        "按首次观测月份分 cohort 计算用户留存率；未到达月份返回 null，末月不完整须披露。注意：不适合用非唯一ID列（如渠道名、地区）作为 user_col。"
    ),
)
def cohort_analysis(name: str, user_col: str, time_col: str, event_col: str = "") -> str:
    df, err = get_df(name)
    if err:
        return err

    try:result=_cohort_result(df,{"user_col":user_col,"time_col":time_col,"event_col":event_col})
    except (ValueError,TypeError) as exc:return "Error: "+str(exc)
    return json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)


def _cohort_result(frame,arguments):
    """Sole monthly distinct-user method and storage-owned receipt verification."""
    args={"user_col":arguments["user_col"],"time_col":arguments["time_col"],"event_col":arguments.get("event_col","")}
    required=[args["user_col"],args["time_col"]]+([args["event_col"]] if args["event_col"] else [])
    missing=[c for c in required if c not in frame.columns]
    if missing:raise ValueError("列不存在："+", ".join(missing))
    user=frame[args["user_col"]];raw_time=frame[args["time_col"]]
    parsed=pd.to_datetime(raw_time,errors="coerce")
    valid=user.notna() & parsed.notna()
    observation={"source_rows":len(frame),"effective_rows":int(valid.sum()),"excluded_rows":int((~valid).sum()),
        "missing_user_rows":int(user.isna().sum()),"missing_time_rows":int(raw_time.isna().sum()),
        "invalid_time_rows":int((raw_time.notna() & parsed.isna()).sum())}
    if not valid.any():
        return {"error":"没有可用用户与事件时间","observation":observation,"status":"not_computed"}
    # Internal role names avoid collisions with user-supplied columns.
    data=pd.DataFrame({"user":user[valid],"time":parsed[valid]})
    data["period"]=data["time"].dt.to_period("M")
    data["cohort"]=data.groupby("user")["period"].transform("min")
    data["age"]=(data["period"]-data["cohort"]).apply(lambda x:x.n)
    counts=data.groupby(["cohort","age"])["user"].nunique()
    observed_end=data["time"].max();final_period=observed_end.to_period("M")
    cohorts=sorted(data["cohort"].unique());axis=list(range((final_period-cohorts[0]).n+1))
    rows=[]
    for cohort in cohorts:
        size=int(counts.loc[(cohort,0)]);retention={};user_counts={}
        for age in axis:
            key="month_"+str(age)
            count=None if cohort+age>final_period else int(counts.get((cohort,age),0))
            user_counts[key]=count;retention[key]=round(count/size*100,2) if count is not None else None
        rows.append({"cohort":str(cohort),"size":size,"retention":retention,"user_counts":user_counts})
    return {"cohorts":rows,"age_axis":axis,"analysis_unit":"distinct_user",
        "cohort_definition":"first_observed_event_month","parameters":args,"observation":observation,
        "observation_window":[str(data["time"].min().date()),str(observed_end.date())],
        "right_censoring":True,"final_month_incomplete":bool(observed_end.normalize()<final_period.end_time.normalize()),
        "status":"partial" if observation["excluded_rows"] else "complete",
        "limitations":["首次观测事件不等于真实首次或首次购卡；user_col的业务用户身份仍由所选口径决定。",
            "已到达且无事件的月份为0；未到达月份为未知（null），不能解释为零留存。",
            "末月可能不完整；按实际最后观测日披露，不证明数据完整性或因果关系。",
            "retention为百分比，size/user_counts为逐月去重用户数；event_col仅声明事件列，不筛选事件值。",
            "排除原因可能重叠，excluded_rows为联合排除记录数；缺失的业务含义未知。"]}


def _recommend_statistical_test(n_a: int, n_b: int, metric_cols: list, result: dict) -> dict | None:
    """Recommend a statistical test based on the comparison context."""
    if n_a < 2 or n_b < 2 or not metric_cols:
        return None
    has_diff = False
    metrics = result.get("metrics", {})
    for col_data in (metrics.values() if metrics else []):
        pct = col_data.get("change_pct")
        if pct is not None and abs(pct) > 1:
            has_diff = True
            break
    if not has_diff:
        comparisons = result.get("comparisons", [])
        for comp in comparisons:
            for k, v in comp.items():
                if isinstance(v, dict) and v.get("change_pct") is not None and abs(v["change_pct"]) > 1:
                    has_diff = True
                    break
            if has_diff:
                break
    if not has_diff:
        return None
    return {
        "recommended_tool": "ab_test",
        "reason": f"两组样本量分别为 {n_a} 和 {n_b}，指标变化已观察到；是否适用 ab_test 仍需核对单位与独立性，当前未验证统计显著性",
        "suggested_args": {
            "name": "<数据集名>",
            "group_col": "<分组列（需包含两组标识）>",
            "metric_col": metric_cols[0],
            "method": "auto",
        },
    }


@registry.register(
    name="compare_periods",
    output_contract=MINIMAL_PRODUCT_CONTRACTS["compare_periods"],
    description=(
        "比较两个时间段的真实有限数值合计、差值和变化率；公开每期/组有效与排除范围，无有效观测为未知，文本/错列/重复选择拒绝。"
        "使用场景：环比/同比分析、活动前后效果对比、不同时期业务表现对比。"
        "不适用场景：无时间列的数据、单时间点快照。"
        "参数说明：period 格式为 'YYYY-MM-DD~YYYY-MM-DD' 或快捷词（last_month/this_month/last_week/this_week）。"
        "常见错误：日期格式不匹配、时间段内无数据（先用 preview_data 确认时间范围）。"
    ),
    recovery_hint=(
        "时段对比失败。常见原因："
        "1) 日期格式不正确（需要 YYYY-MM-DD 格式或快捷词）"
        "2) 指定时间段内无数据（用 preview_data 检查时间范围）"
        "3) date_col 不是日期类型（用 describe_dataset 检查）"
    ),
    schema_overrides={
        "name": {"description": "数据集名称"},
        "date_col": {"description": "日期列名"},
        "metrics": {"description": "要比较的指标列，逗号分隔，为空则比较所有数值列"},
        "period_a": {"description": "时间段 A（基准期），格式: 'YYYY-MM-DD~YYYY-MM-DD' 或 'last_month'/'this_month'"},
        "period_b": {"description": "时间段 B（对比期），格式同上"},
        "dimensions": {"description": "可选维度列，逗号分隔，按维度分组对比"},
        "metric_formulas": {"type":"object","description":"非可加指标须明确窗口聚合公式，例如 {cost_per_order:{operator:ratio_of_sums,numerator:campaign_cost,denominator:orders}}；不累计逐行比率。", "maxProperties":32,"additionalProperties":{"type":"object","required":["operator","numerator","denominator"],"properties":{"operator":{"type":"string","enum":["ratio_of_sums"]},"numerator":{"type":"string"},"denominator":{"type":"string"}}}},
    },
)
def compare_periods(name: str,date_col: str="",metrics: str="",period_a: str="",period_b: str="",dimensions: str="",metric_formulas: dict | None=None)->str:
    frame,error=get_df(name)
    if error:return error
    args={"name":name,"date_col":date_col,"metrics":metrics,"period_a":period_a,"period_b":period_b,"dimensions":dimensions,"metric_formulas":metric_formulas}
    try:result=_period_comparison_result(frame,args,workspace.get_metadata(name,"_column_algebra"))
    except (ValueError,TypeError,OverflowError) as exc:return "Error: "+str(exc)
    return json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)


def _period_comparison_result(frame,arguments,algebra=None):
    name=arguments["name"];date_col=arguments.get("date_col","");metrics=arguments.get("metrics","");period_a=arguments.get("period_a","");period_b=arguments.get("period_b","");dimensions=arguments.get("dimensions","");metric_formulas=arguments.get("metric_formulas")
    if frame.columns.duplicated().any():raise ValueError("重名列不能确定比较输入。")
    if date_col and date_col not in frame.columns:raise ValueError("显式日期列不存在，不自动换列。")
    date_col,error=resolve_date_col(frame,date_col)
    if error:raise ValueError(error)
    parsed=pd.to_datetime(frame[date_col],errors="coerce");df=frame.copy();df[date_col]=parsed;df=df.dropna(subset=[date_col])
    if df.empty:raise ValueError("没有有效日期记录，未计算时段比较。")
    ref_date=df[date_col].max().normalize()
    if not period_a or not period_b:
        raise ValueError("请指定 period_a 和 period_b 参数")

    pa = parse_period_range(period_a, ref_date)
    pb = parse_period_range(period_b, ref_date)
    if not pa or not pb:
        raise ValueError("无法解析时间段。格式: YYYY-MM-DD~YYYY-MM-DD 或快捷词")

    mask_a = inclusive_date_period_mask(df[date_col], pa[0], pa[1])
    mask_b = inclusive_date_period_mask(df[date_col], pb[0], pb[1])
    df_a = df[mask_a]
    df_b = df[mask_b]

    if df_a.empty or df_b.empty:
        return {"error": "某个时间段内没有数据", "period_a_rows": len(df_a), "period_b_rows": len(df_b)}

    # 时段结构分析
    struct_a = analyze_period_structure(pa[0], pa[1])
    struct_b = analyze_period_structure(pb[0], pb[1])
    comparability = compare_period_structures(struct_a, struct_b)
    combined_dates = pd.date_range(pa[0].normalize(), pa[1].normalize(), freq="D").union(
        pd.date_range(pb[0].normalize(), pb[1].normalize(), freq="D")
    )

    # 指标列
    if metrics:
        metric_cols = [c.strip() for c in metrics.split(",")]
        if any(not c for c in metric_cols) or len(set(metric_cols))!=len(metric_cols):raise ValueError("显式指标不可重复或为空。")
    else:
        metric_cols = list(df.select_dtypes(include=[np.number]).columns)
    formulas={} if metric_formulas is None else metric_formulas
    if not isinstance(formulas,dict) or len(formulas)>32:
        return {"error":"指标公式必须为最多32项的结构化对象","error_type":"invalid_metric_formula"}
    for metric, formula in formulas.items():
        if (not isinstance(metric,str) or not metric or len(metric)>128 or not isinstance(formula,dict)
                or set(formula)!={"operator","numerator","denominator"} or formula["operator"]!="ratio_of_sums"
                or any(not isinstance(formula[k],str) or formula[k] not in df.columns or not pd.api.types.is_numeric_dtype(df[formula[k]]) for k in ("numerator","denominator"))):
            return {"error":"指标公式必须引用真实数值分子/分母列","error_type":"invalid_metric_formula"}
    if any(c not in df.columns and c not in formulas for c in metric_cols):raise ValueError("显式指标列不存在。")
    if any(c not in formulas and not pd.api.types.is_numeric_dtype(df[c]) for c in metric_cols):raise ValueError("显式指标须为数值列；不会拼接文本或静默转换。")
    if not metric_cols:
        raise ValueError("没有可比较的数值列")
    algebra=algebra or {}
    unresolved=[c for c in metric_cols if c in algebra and algebra[c].get("operator")=="non_additive" and c not in formulas]
    if unresolved:
        return {"error":"逐行比率不能默认累加；请明确窗口聚合公式。","error_type":"non_additive_metric_requires_formula","metrics":unresolved}

    dim_cols = [c.strip() for c in dimensions.split(",")] if dimensions else []
    if any(not c or c not in df.columns for c in dim_cols) or len(set(dim_cols))!=len(dim_cols):raise ValueError("显式维度列不存在、重复或为空。")

    def _daily_avg_fields(va: float, vb: float):
        """计算日均值相关字段。"""
        days_a = struct_a["day_count"]
        days_b = struct_b["day_count"]
        da = va / days_a if va is not None and days_a > 0 else None
        db = vb / days_b if vb is not None and days_b > 0 else None
        d_diff = db - da if da is not None and db is not None else None
        d_pct = (d_diff / abs(da) * 100) if d_diff is not None and da and da != 0 else None
        return {
            "daily_avg_a": round(da, 4) if da is not None else None,
            "daily_avg_b": round(db, 4) if db is not None else None,
            "daily_avg_diff": round(d_diff, 4) if d_diff is not None else None,
            "daily_avg_change_pct": round(d_pct, 2) if d_pct is not None else None,
        }

    def _column_scope(frame,column):
        values=frame[column].to_numpy(dtype=float,na_value=np.nan);finite=np.isfinite(values)
        audit={"source_rows":len(frame),"effective_rows":int(finite.sum()),"excluded_rows":int((~finite).sum()),"missing_value":int(frame[column].isna().sum()),"nonfinite_value":int((frame[column].notna() & ~finite).sum())}
        return values[finite],audit

    def _measurement(frame,column):
        formula=formulas.get(column);gaps=[]
        if formula is None:
            values,audit=_column_scope(frame,column)
            value=float(np.sum(values)) if len(values) else None
            if value is not None and not np.isfinite(value):value=None;gaps.append("有限观测合计超出可计算范围，合计未知。")
            if audit["excluded_rows"]:gaps.append(f"{column}的{audit['source_rows']}条中排除{audit['excluded_rows']}条缺失/非有限，仅{audit['effective_rows']}条有限值参与求和，原范围未完整覆盖。")
            if not len(values):gaps.append("没有有效有限观测，合计未知；不补零。")
            return value,None,audit,gaps
        operands={};audits={}
        for key in ("numerator","denominator"):
            values,audit=_column_scope(frame,formula[key]);audits[key]=audit
            # Preserve the original strict ratio contract: any missing operand
            # makes its whole period sum unknown, never silently changes scope.
            value=float(np.sum(values)) if len(values) and not audit["excluded_rows"] else None
            operands[key]=value if value is not None and np.isfinite(value) else None
        valid=np.isfinite(frame[formula["numerator"]].to_numpy(dtype=float,na_value=np.nan)) & np.isfinite(frame[formula["denominator"]].to_numpy(dtype=float,na_value=np.nan))
        audit={"source_rows":len(frame),"effective_rows":int(valid.sum()),"excluded_rows":int((~valid).sum()),"operands":audits,"policy":"strict_complete_operand_sums"}
        if operands["numerator"] is None or operands["denominator"] in (None,0):
            gaps.append("窗口比率的分母为零或原列合计缺失；原严格操作数要求未满足，比率未知。")
            return None,operands,audit,gaps
        value=operands["numerator"]/operands["denominator"]
        if not np.isfinite(value):value=None;gaps.append("窗口比率超出可计算范围，未知。")
        return value,operands,audit,gaps

    def _comparison(frame_a,frame_b,column,keys):
        va,operands_a,audit_a,gaps_a=_measurement(frame_a,column);vb,operands_b,audit_b,gaps_b=_measurement(frame_b,column)
        aggregation={"operator":"sum"}
        if column in formulas:aggregation={**formulas[column],"operand_sums":{keys[0]:operands_a,keys[1]:operands_b}}
        diff=vb-va if va is not None and vb is not None else None
        if diff is not None and not np.isfinite(diff):diff=None;gaps_a.append("差值超出可计算范围，未知。")
        pct=diff/abs(va)*100 if diff is not None and va!=0 else None
        if pct is not None and not np.isfinite(pct):pct=None
        gaps=list(dict.fromkeys(gaps_a+gaps_b));unknown=va is None or vb is None or diff is None
        row={"aggregation":aggregation,"exact_aggregates":dict(zip(keys,(va,vb,diff))),
            **{k:round(v,4) if v is not None else None for k,v in zip(keys,(va,vb,diff))},"change_pct":round(pct,2) if pct is not None else None,
            "observation":{keys[0]:audit_a,keys[1]:audit_b},"period_gaps":{keys[0]:gaps_a,keys[1]:gaps_b},"completion_gaps":gaps,
            "percentage_limitation":"前期为零或期值/百分比不可计算；相对变化未知。" if pct is None else ""}
        if unknown:row.update(status="evidence_insufficient",reason="分母为零或原列合计缺失" if column in formulas else "无有效观测或算术不可计算，期值/差值未知。")
        if column not in formulas:row.update(_daily_avg_fields(va,vb))
        return row

    result = {
        "period_a": {
            "label": period_a,
            "range": [str(pa[0].date()), str(pa[1].date())],
            "rows": len(df_a),
            "day_count": struct_a["day_count"],
            "weekday_count": struct_a["weekday_count"],
            "weekend_count": struct_a["weekend_count"],
            **({"dates": struct_a["dates"]} if "dates" in struct_a else {}),
        },
        "period_b": {
            "label": period_b,
            "range": [str(pb[0].date()), str(pb[1].date())],
            "rows": len(df_b),
            "day_count": struct_b["day_count"],
            "weekday_count": struct_b["weekday_count"],
            "weekend_count": struct_b["weekend_count"],
            **({"dates": struct_b["dates"]} if "dates" in struct_b else {}),
        },
        "combined": {
            "row_count": int((mask_a | mask_b).sum()),
            "day_count": int(len(combined_dates)),
        },
        "comparability": comparability,
    }

    if dim_cols:
        result["dimensions"] = dim_cols
        result["comparisons"] = []
        # Both periods own groups, including newly appearing and disappearing ones.
        keys = pd.concat([df_a[dim_cols], df_b[dim_cols]]).drop_duplicates()
        for _, values in keys.iterrows():
            mask_a_group = pd.Series(True, index=df_a.index)
            mask_b_group = pd.Series(True, index=df_b.index)
            for dim in dim_cols:
                value=values[dim]
                mask_a_group &= df_a[dim].isna() if pd.isna(value) else df_a[dim].eq(value)
                mask_b_group &= df_b[dim].isna() if pd.isna(value) else df_b[dim].eq(value)
            grp_a,grp_b=df_a[mask_a_group],df_b[mask_b_group]
            key=tuple(str(values[dim]) for dim in dim_cols)
            row = {"dimension": " / ".join(key),"dimension_values":{dim:safe_jsonify(values[dim]) for dim in dim_cols}}
            for col in metric_cols:
                row[col]=_comparison(grp_a,grp_b,col,("a","b","diff"))
            result["comparisons"].append(row)
    else:
        result["metrics"] = {}
        for col in metric_cols:
            result["metrics"][col]=_comparison(df_a,df_b,col,("period_a","period_b","diff"))

    # Statistical test recommendation
    rec = _recommend_statistical_test(len(df_a), len(df_b), metric_cols, result)
    if rec:
        result["statistical_test_recommendation"] = rec

    result["observation"]={"source_rows":len(frame),"valid_date_rows":len(df),"date_excluded_rows":len(frame)-len(df),"missing_date":int(frame[date_col].isna().sum()),"invalid_date":int((frame[date_col].notna() & parsed.isna()).sum()),"outside_windows_rows":int((~(mask_a | mask_b)).sum()),"period_a_rows":len(df_a),"period_b_rows":len(df_b)}
    result["parameters"]={"date_col":date_col,"metrics":metric_cols,"dimensions":dim_cols,"period_a":period_a,"period_b":period_b,"metric_formulas":formulas}
    result["completion_gaps"]=[f"原范围{len(frame)}条中{len(frame)-len(df)}条缺失/坏日期无法归入时段，原范围未完整覆盖。"] if len(frame)!=len(df) else []
    result["limitations"]=["原可加数值合计；日均为窗口合计除以含首尾日历日数，未做观测缺日填补。","窗口比率保留严格原操作数合计要求；不把缺失/非有限当零，不推断其业务含义。","比较为描述性算术；统计检验建议不代表已检验，不授予因果或预测验证。"]
    result["status"]="partial" if result["completion_gaps"] or any(item["completion_gaps"] or item["percentage_limitation"] for item in (result.get("metrics",{}).values() if not dim_cols else [row[c] for row in result["comparisons"] for c in metric_cols])) else "complete"
    return result


@registry.register(
    name="top_n",
    output_contract=MINIMAL_PRODUCT_CONTRACTS["top_n"],
    description=(
        "获取按指定列排序的 Top N 记录。"
        "使用场景：查找销量最高/最低的产品、贡献最大的客户、表现最好/最差的维度值。"
        "不适用场景：需要全量排序（数据量太大时考虑先 group_aggregate 再 top_n）。"
        "参数说明：sort_by 留空自动选第一个数值列，ascending=False 为降序（默认）。"
        "常见错误：sort_by 列不存在或非数值列。"
    ),
    schema_overrides={
        "name": {"description": "数据集名称"},
        "sort_by": {"description": "排序依据的列名"},
        "n": {"description": "返回记录数"},
        "ascending": {"description": "是否升序（False=从大到小）"},
        "columns": {"description": "返回的列，逗号分隔，为空则返回所有列"},
        "save_as": {"description": "可选：将选出的 Top N 保存为新的派生分析数据集，用于后续图表或导出"},
    },
)
def top_n(
    name: str,
    sort_by: str = "",
    n: int = 10,
    ascending: bool = False,
    columns: str = "",
    save_as: str = "",
) -> str:
    df, err = get_df(name)
    if err:
        return err

    try:top,result=_top_n_selection(df,{"sort_by":sort_by,"n":n,"ascending":ascending,"columns":columns})
    except (ValueError,TypeError) as exc:return "Error: "+str(exc)
    if save_as:
        derive_result=workspace.derive(name,save_as,top,
            expression=f"top_n(sort_by={result['sort_by']}; n={n}; ascending={ascending})")
        if derive_result.startswith("Error:"):return json.dumps({"error":derive_result},ensure_ascii=False)
        result.update(dataset=save_as,source_dataset=name)
    return json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False,default=str)


def _top_n_selection(frame,arguments):
    """Sole owner of the existing record sort/head and lossless finite values."""
    import math
    from datetime import date,datetime
    n=arguments.get("n",10);ascending=arguments.get("ascending",False)
    if type(n) is not int or n<=0:raise ValueError("n 必须是正整数。")
    if type(ascending) is not bool:raise ValueError("ascending 必须是布尔值。")
    sort_by=arguments.get("sort_by","")
    if not sort_by:
        numeric=list(frame.select_dtypes(include=[np.number]).columns)
        if not numeric:raise ValueError("没有可排序的数值列，请指定 sort_by 参数。")
        sort_by=numeric[0]
    if sort_by not in frame.columns:raise ValueError(f"排序列 {sort_by!r} 不存在。")
    columns=arguments.get("columns","")
    selected=[c.strip() for c in columns.split(",")] if columns else list(frame.columns)
    if not selected or any(not c or c not in frame.columns for c in selected) or len(set(selected))!=len(selected):
        raise ValueError("返回列必须存在且不能重复或为空。")
    top=frame.sort_values(by=sort_by,ascending=ascending)[selected].head(n)
    def cell(value):
        if value is None or value is pd.NA or value is pd.NaT:return None
        if isinstance(value,(float,np.floating)) and not math.isfinite(value):return None
        if isinstance(value,(datetime,date)):return value.isoformat()
        if isinstance(value,np.generic):return value.item()
        return value
    records=[{k:cell(v) for k,v in row.items()} for row in top.to_dict("records")]
    result={"sort_by":sort_by,"ascending":ascending,"n":len(top),"records":records,
        "parameters":{"sort_by":sort_by,"ascending":ascending,"n":n,"columns":selected},
        "observation":{"source_rows":len(frame),"returned_rows":len(top)},
        "limitations":["按输入记录排序并截取前 n 条；不等于分组贡献或独立用户排行。",
            "沿用原 sort_values 的并列次序和缺失置后规则；缺失与非有限单元格沿原 JSON 口径显示未知，不解释其业务含义。",
            "有限数值使用原值序列化，不预先舍入；当前排行不证明因果、未来表现或总体代表性。"]}
    return top,result


@registry.register(
    name="contribute_decomposition",
    output_contract=MINIMAL_PRODUCT_CONTRACTS["contribute_decomposition"],
    description=(
        "贡献度分解：将指标的总变化拆解为各维度的贡献比例。"
        "适用于环比/同比变动的描述性算术拆解，不识别因果驱动。"
        "metric 为目标指标列，dimension 为拆解维度列。"
        "period_a/period_b 格式同 compare_periods（'YYYY-MM-DD~YYYY-MM-DD' 或快捷词）。"
        "agg_func: sum 时使用绝对值加法分解，mean 时使用加权分解（适用于均值指标如ARPU）。"
    ),
    schema_overrides={
        "name": {"description": "数据集名称"},
        "metric": {"description": "目标指标列"},
        "dimension": {"description": "拆解维度列"},
        "date_col": {"description": "日期列名"},
        "period_a": {"description": "基准期，格式: 'YYYY-MM-DD~YYYY-MM-DD' 或 'last_month'/'this_month'"},
        "period_b": {"description": "对比期，格式同上"},
        "agg_func": {"description": "聚合方式", "enum": ["sum", "mean"]},
    },
)
def contribute_decomposition(
    name: str,
    metric: str,
    dimension: str,
    date_col: str = "",
    period_a: str = "",
    period_b: str = "",
    agg_func: str = "sum",
) -> str:
    df, err = get_df(name)
    if err:
        return err

    try:data=_contribution_result(df,{"metric":metric,"dimension":dimension,"date_col":date_col,"period_a":period_a,"period_b":period_b,"agg_func":agg_func})
    except (ValueError,TypeError) as exc:return "Error: "+str(exc)
    decomposition=data["decomposition"];total_change=data["total_change"];total_pct=data["total_change_pct"]
    top_neg=data["top_negative"];top_pos=data["top_positive"];comparability=data["comparability"]
    # CLI summary
    summary_lines = [
        f"指标 '{metric}' {period_a}→{period_b} 变化: {total_change:+.4f} ({total_pct:+.2f}%)" if total_pct is not None else f"指标 '{metric}' 变化: {total_change:+.4f}",
        f"按 '{dimension}' 拆解:",
    ]
    for d in decomposition[:5]:
        pct_str = f" ({d['contribution_pct']:+.1f}%)" if d["contribution_pct"] is not None else ""
        summary_lines.append(f"  {d['value']}: {d['contribution']:+.4f}{pct_str}")
    if top_neg:
        summary_lines.append(f"主要下降因素: {', '.join(top_neg)}")
    if top_pos:
        summary_lines.append(f"主要增长因素: {', '.join(top_pos)}")

    # 可比性警告
    if comparability["warnings"]:
        summary_lines.append("⚠ 可比性提示:")
        for w in comparability["warnings"]:
            summary_lines.append(f"  - {w}")

    return ToolResult(
        summary="\n".join(summary_lines),
        data=data,
        suggested_next="compare_periods 查看更多指标的变化",
    )


def _contribution_result(df,arguments):
    """Sole owner of original sum/mean decomposition and observed scope."""
    metric=arguments["metric"];dimension=arguments["dimension"];date_col=arguments.get("date_col","")
    period_a=arguments.get("period_a","");period_b=arguments.get("period_b","");agg_func=arguments.get("agg_func","sum")
    if agg_func not in {"sum","mean"}:raise ValueError("agg_func 只支持 sum/mean。")
    if metric not in df.columns:
        raise ValueError(f"指标列 {metric!r} 不存在。")
    if dimension not in df.columns:
        raise ValueError(f"维度列 {dimension!r} 不存在。")

    if date_col and date_col not in df.columns:raise ValueError(f"日期列 {date_col!r} 不存在。")
    date_col, dc_err = resolve_date_col(df, date_col)
    if dc_err:
        raise ValueError(dc_err)

    from numbers import Number
    if not pd.api.types.is_numeric_dtype(df[metric]) and not all(isinstance(v,Number) for v in df[metric].dropna()):raise ValueError("指标须为数值观测。")
    if np.isinf(df[metric].dropna().to_numpy(dtype=float)).any():raise ValueError("非有限指标不能计算贡献分解。")
    source_rows=len(df);raw_time=df[date_col];parsed=pd.to_datetime(raw_time,errors="coerce")
    observation={"source_rows":source_rows,"missing_time":int(raw_time.isna().sum()),
        "invalid_time":int((raw_time.notna() & parsed.isna()).sum()),"missing_metric":int(df[metric].isna().sum()),"missing_dimension":int(df[dimension].isna().sum())}
    df=df.copy();df[date_col]=parsed;df=df.dropna(subset=[date_col,metric,dimension])
    observation.update(effective_rows=len(df),excluded_rows=source_rows-len(df))
    if df.empty:raise ValueError("没有有效日期、指标和维度的记录。")

    ref_date = df[date_col].max().normalize()
    pa = parse_period_range(period_a, ref_date)
    pb = parse_period_range(period_b, ref_date)
    if not pa or not pb:
        raise ValueError("无法解析时间段。格式 YYYY-MM-DD~YYYY-MM-DD 或 last_month/this_month。")

    mask_a = inclusive_date_period_mask(df[date_col], pa[0], pa[1])
    mask_b = inclusive_date_period_mask(df[date_col], pb[0], pb[1])
    observation.update(outside_period_rows=int((~(mask_a|mask_b)).sum()),overlap_rows=int((mask_a&mask_b).sum()))
    df_a = df[mask_a]
    df_b = df[mask_b]

    if df_a.empty or df_b.empty:
        raise ValueError("某个时间段内没有有效数据。")

    # 时段结构分析
    struct_a = analyze_period_structure(pa[0], pa[1])
    struct_b = analyze_period_structure(pb[0], pb[1])
    comparability = compare_period_structures(struct_a, struct_b)

    # 获取所有维度值（取两个时期的并集）
    all_dim_values = sorted(set(df_a[dimension].unique()) | set(df_b[dimension].unique()))

    if agg_func == "sum":
        # 绝对值加法分解: total_change = sum(contribution[v])
        total_a = float(df_a[metric].sum())
        total_b = float(df_b[metric].sum())
        total_change = total_b - total_a

        decomposition = []
        for v in all_dim_values:
            va = float(df_a.loc[df_a[dimension] == v, metric].sum())
            vb = float(df_b.loc[df_b[dimension] == v, metric].sum())
            contrib = vb - va
            pct = (contrib / abs(total_change) * 100) if total_change != 0 else None
            decomposition.append({
                "value": str(v),
                "count_a":int((df_a[dimension]==v).sum()),"count_b":int((df_b[dimension]==v).sum()),
                "period_a": round(va, 4),
                "period_b": round(vb, 4),
                "contribution": round(contrib, 4),
                "contribution_pct": round(pct, 2) if pct is not None else None,
                "direction": "positive" if contrib > 0 else "negative" if contrib < 0 else "neutral",
            })
    else:
        # mean 加权分解: total_change ≈ sum(weight_change + level_change)
        total_a = float(df_a[metric].mean())
        total_b = float(df_b[metric].mean())
        total_change = total_b - total_a
        n_a, n_b = len(df_a), len(df_b)

        decomposition = []
        for v in all_dim_values:
            grp_a = df_a[df_a[dimension] == v]
            grp_b = df_b[df_b[dimension] == v]
            mean_a_v = float(grp_a[metric].mean()) if len(grp_a) > 0 else None
            mean_b_v = float(grp_b[metric].mean()) if len(grp_b) > 0 else None
            weight_a = len(grp_a) / n_a if n_a > 0 else 0
            weight_b = len(grp_b) / n_b if n_b > 0 else 0

            # 加权分解
            # Algebraically identical combined contribution; absent means are never operands.
            observed_a=weight_a*(mean_a_v-total_a) if len(grp_a) else 0.
            observed_b=weight_b*(mean_b_v-total_a) if len(grp_b) else 0.
            contrib=observed_b-observed_a

            pct = (contrib / abs(total_change) * 100) if total_change != 0 else None
            decomposition.append({
                "value": str(v),
                "count_a":len(grp_a),"count_b":len(grp_b),
                "period_a_mean": round(mean_a_v, 4) if mean_a_v is not None else None,
                "period_b_mean": round(mean_b_v, 4) if mean_b_v is not None else None,
                "weight_a": round(weight_a, 4),
                "weight_b": round(weight_b, 4),
                "contribution": round(contrib, 4),
                "contribution_pct": round(pct, 2) if pct is not None else None,
                "direction": "positive" if contrib > 0 else "negative" if contrib < 0 else "neutral",
            })

    # 排序：按绝对贡献度降序
    decomposition.sort(key=lambda x: -abs(x["contribution"]))

    total_pct = round(total_change / abs(total_a) * 100, 2) if total_a != 0 else None

    top_neg = [d["value"] for d in decomposition if d["direction"] == "negative"][:3]
    top_pos = [d["value"] for d in decomposition if d["direction"] == "positive"][:3]

    data = {
        "metric": metric,
        "dimension": dimension,
        "agg_func": agg_func,
        "period_a": {
            "rows":len(df_a),
            "label": period_a,
            "range": [str(pa[0].date()), str(pa[1].date())],
            "value": round(total_a, 4),
            "day_count": struct_a["day_count"],
            "weekday_count": struct_a["weekday_count"],
            "weekend_count": struct_a["weekend_count"],
        },
        "period_b": {
            "rows":len(df_b),
            "label": period_b,
            "range": [str(pb[0].date()), str(pb[1].date())],
            "value": round(total_b, 4),
            "day_count": struct_b["day_count"],
            "weekday_count": struct_b["weekday_count"],
            "weekend_count": struct_b["weekend_count"],
        },
        "comparability": comparability,
        "total_change": round(total_change, 4),
        "total_change_pct": total_pct,
        "decomposition": decomposition,
        "top_negative": top_neg,
        "top_positive": top_pos,
    }

    # 时长不等时增加日均值归一化
    if comparability["daily_avg_recommended"] and agg_func == "sum":
        days_a = struct_a["day_count"]
        days_b = struct_b["day_count"]
        daily_a = total_a / days_a if days_a > 0 else 0
        daily_b = total_b / days_b if days_b > 0 else 0
        daily_change = daily_b - daily_a
        daily_pct = round(daily_change / abs(daily_a) * 100, 2) if daily_a != 0 else None
        data["daily_normalized"] = {
            "daily_avg_a": round(daily_a, 4),
            "daily_avg_b": round(daily_b, 4),
            "daily_change": round(daily_change, 4),
            "daily_change_pct": daily_pct,
            "note": "Daily averages account for different period lengths",
        }

    data.update(observation=observation,parameters={"metric":metric,"dimension":dimension,"date_col":date_col,"period_a":period_a,"period_b":period_b,"agg_func":agg_func},
        percentage_denominators={"contribution_pct":"abs(total_change)","total_change_pct":"abs(period_a.value)"},
        limitations=["仅对当前有效记录做描述性算术分解，不识别因果归因或验证业务驱动。",
            "mean采用前期总体均值中心化的合并加权贡献；缺席组条数/权重为0、均值未知，只使用已观测加权项。sum为分组观测总和之差。",
            "贡献百分比=贡献/abs(总变化)；总体变化百分比=变化/abs(前期值)，零分母未知；下降时贡献百分比可合计为-100%。",
            "缺失/无效时间、指标或维度按联合行数排除，逐项计数可重叠；不解释其业务含义。两期重叠保留原窗口成员关系。",
            "日均归一化仅按窗口日数计算，不证明两期可比或时间/个体独立。"],completion_gaps=[])
    if observation["excluded_rows"]:data["completion_gaps"].append(f"原范围有 {observation['excluded_rows']} 条缺失或无效记录被排除；仅有效范围已计算。")
    if total_change==0:data["completion_gaps"].append("总变化为0，贡献百分比未知；绝对贡献仍保留。")
    data["status"]="partial" if data["completion_gaps"] else "complete"
    json.dumps(data,allow_nan=False,default=str)
    return data


@registry.register(
    name="funnel_analysis",
    output_contract=MINIMAL_PRODUCT_CONTRACTS["funnel_analysis"],
    description=(
        "漏斗转化分析。支持三种数据格式：\n"
        "- steps 模式（场景A）：事件明细数据，指定 user_col/event_col，"
        "  steps 为有序事件列表（逗号分隔），自动统计每步用户数和转化率。\n"
        "- aggregate 模式（场景B）：预聚合的步骤数据，指定 step_col/count_col，"
        "  steps 为步骤名称列表（逗号分隔，按顺序）。\n"
        "- rates 模式（场景C）：宽表多列率数据，指定 rate_cols（逗号分隔），"
        "  每列代表一个累积转化率（相对于第一步），自动推算步骤间转化率。\n"
        "mode 为 auto 时自动检测数据格式。dimension 参数可选，按维度分组生成子漏斗。"
    ),
    schema_overrides={
        "name": {"description": "数据集名称"},
        "mode": {"description": "分析模式", "enum": ["auto", "steps", "aggregate", "rates"]},
        "user_col": {"description": "用户ID列（steps 模式）"},
        "event_col": {"description": "事件类型列（steps 模式）"},
        "time_col": {"description": "事件时间列（steps 模式，可选）"},
        "steps": {"description": "步骤名称列表（逗号分隔）"},
        "step_col": {"description": "步骤名称列（aggregate 模式）"},
        "count_col": {"description": "计数值列（aggregate 模式）"},
        "rate_cols": {"description": "累积转化率列名（逗号分隔，rates 模式）"},
        "dimension": {"description": "维度列名（可选，按维度分组）"},
        "window_hours": {"description": "步骤间最大时间窗口（小时，0=不限制，steps 模式）"},
    },
)
def funnel_analysis(
    name: str,
    mode: str = "auto",
    user_col: str = "",
    event_col: str = "",
    time_col: str = "",
    steps: str = "",
    step_col: str = "",
    count_col: str = "",
    rate_cols: str = "",
    dimension: str = "",
    window_hours: int = 0,
) -> str:
    df, err = get_df(name)
    if err:
        return err

    arguments=dict(mode=mode,user_col=user_col,event_col=event_col,time_col=time_col,steps=steps,
        step_col=step_col,count_col=count_col,rate_cols=rate_cols,dimension=dimension,window_hours=window_hours)
    try:data=_funnel_result(df,arguments)
    except (ValueError,TypeError,OverflowError) as exc:return "Error: "+str(exc)
    lines=["漏斗分析（"+data["mode"]+"）"]
    for row in data["steps"]:
        value=row.get("cumulative_rate") if data["mode"]=="rates" else row["count"]
        lines.append(row["step"]+": "+("未知" if value is None else str(value)))
    lines.extend(data["limitations"])
    return ToolResult(summary="\n".join(lines),data=data,
        suggested_next="create_chart(funnel) 可视化已交付的漏斗步骤")


def _funnel_result(df,arguments):
    """Sole funnel computation, also used for storage-owned receipt verification."""
    args={"mode":"auto","user_col":"","event_col":"","time_col":"","steps":"","step_col":"",
          "count_col":"","rate_cols":"","dimension":"","window_hours":0}
    args.update({k:v for k,v in arguments.items() if k in args})
    mode=args["mode"]
    if mode=="auto":
        if args["user_col"] and args["event_col"] and args["steps"]:mode="steps"
        elif args["step_col"] and args["count_col"]:mode="aggregate"
        elif args["rate_cols"]:mode="rates"
        else:
            lower={str(c).lower():c for c in df.columns}
            if any(k in lower for k in ["user_id","uid","openid"]) and any(k in lower for k in ["event","action","event_type"]):mode="steps"
            elif any(k in lower for k in ["step","stage","阶段","步骤"]):mode="aggregate"
            else:
                found=[c for c in df.columns if any(k in str(c).lower() for k in ["率","rate","ratio","pct"]) and pd.api.types.is_numeric_dtype(df[c])]
                if len(found)<2:raise ValueError("无法自动检测漏斗模式。请指定 mode 和相应参数。")
                mode="rates";args["rate_cols"]=",".join(found)
    if mode not in {"steps","aggregate","rates"}:raise ValueError("不支持的漏斗模式："+str(mode))
    args["mode"]=mode
    def column(c):
        if c not in df.columns:raise ValueError("列不存在："+str(c))
    dimension=args["dimension"]
    if dimension:column(dimension)
    step_list=[s.strip() for s in args["steps"].split(",") if s.strip()]
    if len(step_list)!=len(set(step_list)):raise ValueError("步骤名称不能重复。")
    temporal=mode=="steps" and bool(args["time_col"])
    order="explicit"
    limitations=[]
    if mode=="steps":
        column(args["user_col"]);column(args["event_col"])
        if len(step_list)<2:raise ValueError("steps 至少需要 2 个步骤")
        if args["time_col"]:column(args["time_col"])
        if type(args["window_hours"]) is not int or args["window_hours"]<0:raise ValueError("window_hours 必须是非负整数小时。")
        if args["window_hours"] and not temporal:raise ValueError("时间窗口需要 time_col，不能从集合包含推断间隔。")
        existing=set(df[args["event_col"]].dropna())
        if any(s not in existing for s in step_list):raise ValueError("请求的事件步骤不存在。")
        limitations.append("逐用户最早有效顺序路径；时间窗口限制相邻已选步骤。" if temporal else "未提供时间列；仅验证逐用户步骤集合包含，未验证时间顺序。")
        if df[args["user_col"]].isna().any():limitations.append("用户身份缺失记录不计入用户集合；业务含义未知。")
        make=lambda frame:_funnel_steps_rows(frame,args,step_list)
        unit="distinct_users"
    elif mode=="aggregate":
        column(args["step_col"]);column(args["count_col"])
        values=df[args["count_col"]].dropna()
        if not pd.api.types.is_numeric_dtype(df[args["count_col"]]) or any(not np.isfinite(v) or v<0 or v!=int(v) for v in values):raise ValueError("计数必须是有限非负整数，不能截断或补零。")
        actual=list(df[args["step_col"]].dropna().unique())
        if len({str(v) for v in actual})!=len(actual):raise ValueError("步骤字符串身份有歧义。")
        if not step_list:
            totals=_funnel_aggregate_counts(df,args)
            step_list=sorted(totals,key=lambda s:-(totals[s] if totals[s] is not None else -1))
            order="inferred_from_aggregate_counts"
            limitations.append("步骤顺序由完整范围聚合计数降序推断，不证明真实路径顺序。")
        limitations.append("预聚合计数按同一步骤求和；不证明人数去重或时间顺序。缺失步骤与缺失计数保持未知。")
        def make(frame):
            totals=_funnel_aggregate_counts(frame,args)
            return [{"step":s,"count":totals.get(s)} for s in step_list]
        unit="reported_counts"
    else:
        cols=[c.strip() for c in args["rate_cols"].split(",") if c.strip()]
        if not cols or len(cols)!=len(set(cols)):raise ValueError("rate_cols 需要不重复的率列。")
        for c in cols:
            column(c)
            if not pd.api.types.is_numeric_dtype(df[c]):raise ValueError("率列必须是数值列："+c)
            if any(not np.isfinite(v) or not 0<=v<=1 for v in df[c].dropna()):raise ValueError("累积率必须是有限的0—1比例。")
        for row in df[cols].itertuples(index=False,name=None):
            observed=[v for v in row if not pd.isna(v)]
            if any(b>a for a,b in zip(observed,observed[1:])):raise ValueError("后一步累积率不能高于前一步。")
        limitations.append("逐列对有效记录等权求均值；步骤比值为累积率列均值之比；人数未知，不代表真实用户转化或加权总体。")
        limitations.append("普通缺失逐列披露有效数；各列有效范围可能不同，不推断缺失的业务含义。")
        make=lambda frame:[{"step":c,"count":None,"cumulative_rate":round(float(frame[c].mean()),4) if frame[c].notna().any() else None,
            "effective_n":int(frame[c].notna().sum()),"missing_count":int(frame[c].isna().sum()),"source_rows":len(frame)} for c in cols]
        unit="equal_weight_column_means"
    def finish(frame):
        rows=make(frame)
        key="cumulative_rate" if mode=="rates" else "count"
        values=[float(frame[c].mean()) if frame[c].notna().any() else None for c in cols] if mode=="rates" else [row[key] for row in rows]
        for i,row in enumerate(rows):
            if i:row["step_conversion"]=_funnel_ratio(values[i],values[i-1])
        overall=_funnel_ratio(values[-1],values[0]) if values else None
        drops=[{"from":a["step"],"to":b["step"],"drop_rate":round(1-b["step_conversion"],4)} for a,b in zip(rows,rows[1:]) if b.get("step_conversion") is not None]
        return {"steps":rows,"overall_conversion":overall,"biggest_drop":max(drops,key=lambda x:x["drop_rate"]) if drops else None}
    data=finish(df);groups=None
    if dimension:
        groups={}
        for value,frame in df.groupby(dimension,dropna=False,sort=False,observed=True):
            label="(缺失)" if pd.isna(value) else str(value)
            if label in groups:raise ValueError("维度字符串身份有歧义。")
            groups[label]=finish(frame)
    data.update(mode=mode,parameters=args,dimension_funnels=groups,analysis_unit=unit,
        temporal_order_verified=temporal,step_order=order,limitations=limitations)
    unknown=any(row.get("cumulative_rate" if mode=="rates" else "count") is None or (i>0 and row.get("step_conversion") is None) for part in [data]+list((groups or {}).values()) for i,row in enumerate(part["steps"]))
    data["status"]="partial" if unknown or data["overall_conversion"] is None or (mode=="steps" and df[args["user_col"]].isna().any()) else "complete"
    return data


def _funnel_ratio(numerator,denominator):
    return round(numerator/denominator,4) if numerator is not None and denominator is not None and denominator>0 else None


def _funnel_aggregate_counts(frame,args):
    result={}
    for value,rows in frame.groupby(args["step_col"],sort=False,observed=True):
        counts=rows[args["count_col"]]
        result[str(value)]=sum(int(v) for v in counts) if counts.notna().all() else None
    return result


def _funnel_steps_rows(frame,args,steps):
    counts=[0]*len(steps)
    for _,events in frame.groupby(args["user_col"],sort=False,observed=True):
        previous=None
        for i,step in enumerate(steps):
            selected=events[events[args["event_col"]]==step]
            if selected.empty:break
            if args["time_col"]:
                times=pd.to_datetime(selected[args["time_col"]],format="mixed")
                if times.isna().any():raise ValueError("请求步骤存在缺失时间，无法核验时间顺序。")
                if previous is not None:times=times[times>=previous]
                chosen=times.min()
                if pd.isna(chosen):break
                if previous is not None and args["window_hours"] and (chosen-previous).total_seconds()>args["window_hours"]*3600:break
                previous=chosen
            counts[i]+=1
    return [{"step":step,"count":count} for step,count in zip(steps,counts)]
