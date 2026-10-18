"""One original ordered-holdout forecast owner, shared with storage verification."""
from __future__ import annotations
import numpy as np
import pandas as pd
from data_agent.tools._utils import get_df
from data_agent.tools.method_contract import method_receipt
from data_agent.tools.registry import ToolResult


def _backtested_forecast_result(frame, name, target_col, date_col, periods, identity):
    if frame.columns.duplicated().any():raise ValueError("重名列不能确定预测输入。")
    if target_col not in frame.columns or date_col not in frame.columns:raise ValueError(f"列不存在。可用: {list(frame.columns)}")
    if date_col==target_col:raise ValueError("预测时间列与数值列必须不同。")
    dates=pd.to_datetime(frame[date_col],errors="coerce");values=pd.to_numeric(frame[target_col],errors="coerce")
    numeric=values.to_numpy(dtype=float,na_value=np.nan);finite=np.isfinite(numeric)
    valid=dates.notna() & values.notna() & finite
    data=pd.DataFrame({"date":dates[valid],"value":numeric[valid]}).sort_values("date")
    effective=len(data);group_counts=data.groupby("date").size()
    data=data.groupby("date",as_index=False)["value"].sum()
    if not np.isfinite(data["value"].to_numpy(dtype=float)).all():raise ValueError("同时间求和产生非有限值，未生成预测。")
    deltas=data["date"].diff().dropna();equal=bool(len(deltas) and deltas.nunique()==1)
    observation={"source_rows":len(frame),"effective_rows":effective,"excluded_rows":len(frame)-effective,
        "missing_date":int(frame[date_col].isna().sum()),"invalid_date":int((frame[date_col].notna() & dates.isna()).sum()),
        "missing_value":int(frame[target_col].isna().sum()),"non_numeric_value":int((frame[target_col].notna() & values.isna()).sum()),
        "nonfinite_value":int((values.notna() & ~finite).sum()),"time_points":len(data),
        "collapsed_duplicate_rows":effective-len(data),"duplicate_timestamp_groups":int((group_counts>1).sum()),
        "duplicate_aggregation":"sum","timestamp_aggregation":[{"date":date.isoformat(),"input_rows":int(count)} for date,count in group_counts.items()],
        "equal_intervals":equal if len(data)>=2 else None,"interval":str(deltas.iloc[0]) if equal else None}
    limits=["预测为短期统计外推，不构成保证或因果结论。","候选模型仅在当前时间范围内以有序留出误差比较，未来误差未经验证。",
        "区间为未校准的残差启发带：1.96乘留出残差样本标准差，不表示95%预测覆盖；未来不确定性未经验证。",
        "缺失、坏日期、非数值和非有限记录排除；重复时间的有限观测按原算法求和，不补值，不解释缺失的业务含义。"]
    gaps=[f"原范围{observation['source_rows']}条中排除{observation['excluded_rows']}条；仅有效范围已计算，原范围未完整覆盖。"] if observation["excluded_rows"] else []
    params={"date_col":date_col,"target_col":target_col,"periods":periods}
    date_range={"start":data.date.iloc[0].isoformat(),"end":data.date.iloc[-1].isoformat()} if len(data) else None
    interval={"method":"uncalibrated_residual_heuristic","multiplier":1.96,"residual_count":0,"residual_std":None,"coverage_probability":None,"future_uncertainty_validated":False}
    def receipt(method,status,reason="",extra_limits=()):
        r=method_receipt(name,method=method,status=status,effective_n=len(data),parameters=dict(params),limitations=limits+list(extra_limits),reason_code=reason,claim_ceiling="predictive" if status=="supported" else "descriptive",data_identity=identity)
        r.update(observation=observation,date_range=date_range,interval=interval,completion_gaps=list(gaps),backtest={})
        return r
    if len(data)<max(20,periods*3):return receipt("ordered_holdout_baselines","limited","insufficient_time_points",["有效时间点不足以同时完成留出回测和预测。"])
    if not equal:return receipt("ordered_holdout_baselines","limited","missing_time_intervals",["时间间隔不完整或不规则；系统不会静默补值。"])
    horizon=min(periods,max(3,len(data)//5));train,validation=data.iloc[:-horizon],data.iloc[-horizon:]
    naive=np.repeat(float(train.value.iloc[-1]),horizon)
    slope,intercept=np.polyfit(np.arange(len(train)),train.value.to_numpy(),1)
    trend=intercept+slope*np.arange(len(train),len(train)+horizon)
    actual=validation.value.to_numpy(dtype=float);candidates={"naive_last_value":naive,"linear_trend":trend}
    scores={key:float(np.mean(np.abs(actual-predicted))) for key,predicted in candidates.items()}
    if not all(np.isfinite(v) for v in scores.values()):raise ValueError("留出误差产生非有限值，未交付预测。")
    selected=min(scores,key=scores.get)
    scale=float(np.std(actual-candidates[selected],ddof=1)) if horizon>1 else None
    if scale is not None and not np.isfinite(scale):scale=None
    interval.update(residual_count=horizon,residual_std=scale)
    if scale is None:gaps.append("不足两条留出残差或样本标准差不可计算；点预测保留，残差启发带上下界未知。")
    full_values=data.value.to_numpy(dtype=float)
    if selected=="naive_last_value":predicted=np.repeat(float(full_values[-1]),periods)
    else:
        full_slope,full_intercept=np.polyfit(np.arange(len(full_values)),full_values,1)
        predicted=full_intercept+full_slope*np.arange(len(full_values),len(full_values)+periods)
    if not np.isfinite(predicted).all():raise ValueError("点预测产生非有限值，未交付预测。")
    future_dates=pd.date_range(data.date.iloc[-1]+deltas.iloc[0],periods=periods,freq=deltas.iloc[0])
    params.update(validation_points=horizon,backtest_scheme="ordered_holdout")
    r=receipt(selected,"supported")
    def bound(value):return round(float(value),8) if np.isfinite(value) else None
    r.update(backtest={"mae":round(scores[selected],8),"candidates_mae":{key:round(value,8) for key,value in scores.items()}},
        forecast=[{"date":date.isoformat(),"yhat":round(float(value),8),"yhat_lower":None if scale is None else bound(value-1.96*scale),"yhat_upper":None if scale is None else bound(value+1.96*scale)} for date,value in zip(future_dates,predicted)])
    if scale is not None and any(row[k] is None for row in r["forecast"] for k in ("yhat_lower","yhat_upper")):
        r["completion_gaps"].append("部分残差启发带边界不可计算，保留点预测和未知边界。")
    return r


def _forecast_result(frame, arguments, identity):
    from data_agent.tools.ml import _coerce_forecast_periods, _infer_forecast_date_col
    periods,error=_coerce_forecast_periods(arguments.get("periods",7))
    if error:raise ValueError(error)
    method=arguments.get("method","auto")
    if method not in {"auto","backtest"}:raise ValueError("method must be auto or backtest")
    date_col=arguments.get("date_col","") or _infer_forecast_date_col(frame)
    if not date_col:raise ValueError("date_col is required for a time-series forecast")
    r=_backtested_forecast_result(frame,arguments["name"],arguments["target_col"],date_col,periods,identity)
    r["parameters"]["requested_method"]=method
    r.update(periods=periods,date_col=date_col,fallback_used=False,diagnostics={"mae":r["backtest"].get("mae"),"backtest_scheme":r["parameters"].get("backtest_scheme")})
    return r


def backtested_forecast(name: str,target_col: str,date_col: str,periods: int)->ToolResult:
    frame,error=get_df(name)
    if error:return ToolResult(summary=error)
    from data_agent.session.workspace import workspace
    try:r=_backtested_forecast_result(frame,name,target_col,date_col,periods,workspace.get_data_identity(name))
    except (ValueError,TypeError,OverflowError) as exc:return ToolResult(summary=str(exc))
    return ToolResult(summary="已完成有序留出和点预测；残差启发带未经校准。" if r.get("forecast") else "预测前提不足，未生成预测。",data=r)
