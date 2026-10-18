"""L4: 机器学习工具。"""

from __future__ import annotations

import json
import hashlib
from typing import Optional

import numpy as np
import pandas as pd

from data_agent.session.workspace import workspace
from data_agent.tools._utils import get_df
from data_agent.tools.registry import registry
from data_agent.agent.publication.native import MINIMAL_PRODUCT_CONTRACTS
from data_agent.agent.publication.deliveries import CV_FOLDS_SCHEMA


# 存储trained models
_trained_models: dict = {}
# Ephemeral estimator objects remain process-local, but their provenance is
# explicit and checked before downstream explanations or simulations use them.
_trained_model_metadata: dict = {}


def _model_key(name: str, kind: str, target_col: str) -> str:
    from data_agent.agent.context import get_current_context
    context=get_current_context()
    scope=[getattr(context,"session_id",None),getattr(context,"project_name",None)]
    owner=hashlib.sha256(json.dumps(scope,ensure_ascii=False).encode("utf-8")).hexdigest()[:24]
    return f"{owner}:{name}_{'cls' if kind=='classification' else 'reg'}_{target_col}"


def _record_model(name: str, key: str, target_col: str, feature_cols: list[str], model, kind: str, label_mapping=None) -> None:
    _trained_models[key] = model
    _trained_model_metadata[key] = {
        "model_key": key,
        "kind": kind,
        "target_col": target_col,
        "feature_cols": list(feature_cols),
        "data_identity": workspace.get_data_identity(name),
        "label_mapping": list(label_mapping or []),
    }


def _supervised_data(name,target_col,features,method,allowed,cv_folds):
    """One input contract shared by the existing supervised producers."""
    def error(code,message):return None,None,json.dumps({"error":message,"error_type":code},ensure_ascii=False)
    if method not in allowed:return error("unsupported_model_method","不支持的显式模型方法；不会改跑auto。")
    if type(cv_folds) is not int or cv_folds<0 or cv_folds==1:return error("invalid_cv_folds","cv_folds必须为0或至少2的整数。")
    df,err=get_df(name)
    if err:return error("missing_dataset",err)
    if target_col not in df.columns:return error("missing_target",f"目标列 '{target_col}' 不存在")
    columns=list(dict.fromkeys(c.strip() for c in features.split(",") if c.strip())) if features else [c for c in df.select_dtypes(include=[np.number]).columns if c!=target_col]
    if not columns or any(c not in df.columns for c in columns):return error("invalid_features","特征列为空或不存在。")
    if target_col in columns:return error("target_leakage","目标列不能同时作为训练特征。")
    if df.columns.duplicated().any():return error("ambiguous_columns","重名列不能确定模型输入。")
    data=df[columns+[target_col]].dropna().copy()
    if len(data)<20:return error("insufficient_observations",f"Error: 有效数据({len(data)})太少，至少需要20条。")
    for column in columns:
        data[column]=pd.to_numeric(data[column],errors="coerce")
        if not np.isfinite(data[column].to_numpy(dtype=float)).all():return error("invalid_feature_values",f"特征{column}包含非数值或非有限值。")
    if cv_folds>len(data):return error("invalid_cv_folds","交叉验证折数不能超过有效记录数。")
    return data,columns,None


def _model_validation(source_rows,effective_rows):
    return {"scheme":"random_holdout","random_state":42,"test_fraction":.2,"stratified":False,"split_unit":"row", "time_aware":False,
            "source_rows":source_rows,"effective_rows":effective_rows,"excluded_missing_rows":source_rows-effective_rows}


def _forecast_error(message: str, error_type: str = "tool_error", field: str = "") -> str:
    return json.dumps({"error": message, "error_type": error_type, "field": field}, ensure_ascii=False)


def _coerce_forecast_periods(periods) -> tuple[int | None, str]:
    try:
        value = int(periods)
    except (TypeError, ValueError):
        return None, "periods must be an integer"
    if value <= 0:
        return None, "periods must be greater than 0"
    if value > 365:
        return None, "periods must be <= 365"
    return value, ""


def _infer_forecast_date_col(df: pd.DataFrame) -> str:
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            return str(col)
    for col in df.columns:
        col_name = str(col).lower()
        if any(token in col_name for token in ("date", "time", "日期", "时间")):
            parsed = pd.to_datetime(df[col], errors="coerce")
            if parsed.notna().sum() >= max(3, int(len(df) * 0.5)):
                return str(col)
    return ""




@registry.register(
    name="forecast",
    output_contract=MINIMAL_PRODUCT_CONTRACTS["forecast"],
    description="时间序列预测：auto/backtest原末值/线性候选经有序留出选择，返回完整时间戳、有限筛样/重复时间求和范围与未校准残差启发带；不表示95%预测覆盖。",
    schema_overrides={
        "name": {"description": "数据集名称"},
        "target_col": {"description": "预测目标列"},
        "date_col": {"description": "日期列；为空时自动推断"},
        "periods": {"description": "短期预测期数"},
        "method": {"description": "仅支持 backtest/auto；不再将样本内拟合报告为验证", "enum": ["auto", "backtest"]},
    },
)
def forecast(name: str, target_col: str, date_col: str = "", periods: int = 7, method: str = "auto"):
    """Existing public forecast entry with Slice 3 backtesting semantics."""
    periods_value, error = _coerce_forecast_periods(periods)
    if error:
        return _forecast_error(error, "invalid_parameter", "periods")
    if method not in {"auto", "backtest"}:
        return _forecast_error("method must be auto or backtest", "invalid_parameter", "method")
    df, lookup_error = get_df(name)
    if lookup_error:
        return lookup_error
    if not date_col:
        date_col = _infer_forecast_date_col(df)
    if not date_col:
        return _forecast_error("date_col is required for a time-series forecast", "missing_date_column", "date_col")
    from data_agent.tools.forecasting import _forecast_result
    try:payload=_forecast_result(df,{"name":name,"target_col":target_col,"date_col":date_col,"periods":periods_value,"method":method},workspace.get_data_identity(name))
    except (ValueError,TypeError,OverflowError) as exc:return _forecast_error(str(exc),"forecast_failed")
    return json.dumps(payload,ensure_ascii=False,allow_nan=False)



@registry.register(
    name="classification",
    output_contract=MINIMAL_PRODUCT_CONTRACTS["classification"],
    description="分类模型训练和评估。支持 cv_folds 交叉验证。",
    schema_overrides={
        "name": {"description": "数据集名称"},
        "target_col": {"description": "目标分类列"},
        "features": {"description": "特征列，逗号分隔，为空则自动选择数值列"},
        "method": {"description": "分类方法", "enum": ["auto", "logistic", "rf"]},
        "cv_folds": dict(CV_FOLDS_SCHEMA,description="交叉验证折数，0表示不交叉验证，启用时至少2折"),
    },
)
def classification(name: str, target_col: str, features: str = "", method: str = "auto", cv_folds: int = 0) -> str:
    from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import train_test_split, cross_val_score
    from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, precision_recall_fscore_support, confusion_matrix
    from sklearn.preprocessing import LabelEncoder
    data,feature_cols,err=_supervised_data(name,target_col,features,method,{"auto","logistic","rf"},cv_folds)
    if err:return err
    try:
        encoder=LabelEncoder();y=encoder.fit_transform(data[target_col].to_numpy())
        labels=[v.item() if isinstance(v,np.generic) else v for v in encoder.classes_]
        json.dumps(labels,allow_nan=False)
    except (TypeError,ValueError) as exc:
        return json.dumps({"error":f"分类标签类型不一致或不支持: {exc}","error_type":"invalid_class_labels"},ensure_ascii=False)
    n_classes=len(labels)
    if n_classes<2:return json.dumps({"error":"目标变量只有1个类别","error_type":"insufficient_classes"},ensure_ascii=False)
    if cv_folds and min(np.bincount(y))<cv_folds:return json.dumps({"error":"每类有效观测不足以支持指定分层CV折数","error_type":"invalid_cv_folds"},ensure_ascii=False)
    X=data[feature_cols].to_numpy(dtype=float)
    X_train,X_test,y_train,y_test=train_test_split(X,y,test_size=.2,random_state=42)
    constructors={"auto":lambda:GradientBoostingClassifier(n_estimators=100,random_state=42),"logistic":lambda:LogisticRegression(max_iter=1000,random_state=42),"rf":lambda:RandomForestClassifier(n_estimators=100,random_state=42)}
    model=constructors[method]()
    try:
        model.fit(X_train,y_train);y_pred=model.predict(X_test)
        scores=cross_val_score(model,X,y,cv=cv_folds,scoring="accuracy",error_score="raise") if cv_folds else None
    except ValueError as exc:return json.dumps({"error":f"分类训练或验证前提不足: {exc}","error_type":"model_validation_failed"},ensure_ascii=False)
    if scores is not None and not np.isfinite(scores).all():return json.dumps({"error":"交叉验证结果非有限","error_type":"nonfinite_validation"},ensure_ascii=False)
    all_labels=np.arange(n_classes)
    precision,recall,f1,support=precision_recall_fscore_support(y_test,y_pred,labels=all_labels,zero_division=0)
    class_metrics=[{"encoded":i,"label":label,"precision":round(float(precision[i]),4),"recall":round(float(recall[i]),4),"f1":round(float(f1[i]),4),"support":int(support[i])} for i,label in enumerate(labels)]
    importances={};coefficient_classes=[]
    if hasattr(model,"feature_importances_"):
        importances={f:round(float(v),4) for f,v in sorted(zip(feature_cols,model.feature_importances_),key=lambda pair:-pair[1])}
        importance_semantics="impurity_based_model_importance"
    else:
        coefficients=model.coef_;mapped=[labels[1]] if n_classes==2 else labels
        coefficient_classes=[{"label":label,"coefficients":{f:float(v) for f,v in zip(feature_cols,row)}} for label,row in zip(mapped,coefficients)]
        importances={f:round(float(v),4) for f,v in sorted(zip(feature_cols,coefficients[0]),key=lambda pair:-abs(pair[1]))}
        importance_semantics="signed_coefficients_for_class_"+str(mapped[0])
    result={"method_contract":"analysis_method_result.v1","status":"supported","claim_ceiling":"predictive_holdout_only",
            "data_identity":workspace.get_data_identity(name),"target_col":target_col,"feature_cols":feature_cols,"requested_method":method,"method":type(model).__name__,
            "n_classes":n_classes,"label_mapping":[{"encoded":i,"label":label} for i,label in enumerate(labels)],"positive_class":labels[1] if n_classes==2 else None,
            "class_metrics":class_metrics,"confusion_matrix":confusion_matrix(y_test,y_pred,labels=all_labels).tolist(),"coefficients_by_class":coefficient_classes,
            "train_size":len(X_train),"test_size":len(X_test),"validation":_model_validation(len(workspace.get(name)),len(data)),
            "evaluation":{"y_true":y_test.tolist(),"y_pred":y_pred.tolist()},"metrics":{"accuracy":round(float(accuracy_score(y_test,y_pred)),4),"f1_macro":round(float(np.mean(f1)),4),"precision_macro":round(float(np.mean(precision)),4),"recall_macro":round(float(np.mean(recall)),4)},
            "feature_importance":importances,"feature_importance_semantics":importance_semantics,
            "limitations":["当前随机按行留出评估；未按时间或业务单位分组，不证明未来、总体或因果效果。","原标签统一编码；二分类默认正类为排序后末类，仅统计约定，不代表业务好坏。","特征重要性解释该模型；类别系数按公开类别分别保留，不以首类代替其他类别。"]}
    if n_classes==2:
        result["metrics"].update(f1=round(float(f1[1]),4),precision=round(float(precision[1]),4),recall=round(float(recall[1]),4))
    if cv_folds:result["cv"]={"folds":cv_folds,"mean":round(float(scores.mean()),4),"std":round(float(scores.std()),4),"scores":scores.tolist(),"scheme":"stratified_kfold_without_shuffle","scoring":"accuracy"}
    _record_model(name,_model_key(name,"classification",target_col),target_col,feature_cols,model,"classification",result["label_mapping"])
    return json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)


@registry.register(
    name="regression_analysis",
    output_contract=MINIMAL_PRODUCT_CONTRACTS["regression_analysis"],
    description="回归分析。linear实际为ElasticNet，rf为随机森林，auto/gbrt为梯度提升。保留随机按行留出和可选CV，公开实际算法与验证限制。",
    schema_overrides={
        "name": {"description": "数据集名称"},
        "target_col": {"description": "目标回归列"},
        "features": {"description": "特征列，逗号分隔，为空则自动选择数值列"},
        "method": {"description": "回归方法", "enum": ["auto", "linear", "rf", "gbrt"]},
        "cv_folds": dict(CV_FOLDS_SCHEMA,description="交叉验证折数，0表示不交叉验证，启用时至少2折"),
    },
)
def regression_analysis(name: str, target_col: str, features: str = "", method: str = "auto", cv_folds: int = 0) -> str:
    from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
    from sklearn.linear_model import ElasticNet
    from sklearn.model_selection import train_test_split, cross_val_score
    from sklearn.metrics import mean_absolute_error,mean_squared_error,r2_score
    data,feature_cols,err=_supervised_data(name,target_col,features,method,{"auto","linear","rf","gbrt"},cv_folds)
    if err:return err
    y=pd.to_numeric(data[target_col],errors="coerce").to_numpy(dtype=float)
    if not np.isfinite(y).all():return json.dumps({"error":"目标列包含非数值或非有限值","error_type":"invalid_target_values"},ensure_ascii=False)
    if cv_folds and len(data)//cv_folds<2:return json.dumps({"error":"R2交叉验证每折至少需要两条验证观测","error_type":"invalid_cv_folds"},ensure_ascii=False)
    X=data[feature_cols].to_numpy(dtype=float)
    X_train,X_test,y_train,y_test=train_test_split(X,y,test_size=.2,random_state=42)
    constructors={"auto":lambda:GradientBoostingRegressor(n_estimators=100,random_state=42),"gbrt":lambda:GradientBoostingRegressor(n_estimators=100,random_state=42),"linear":lambda:ElasticNet(random_state=42),"rf":lambda:RandomForestRegressor(n_estimators=100,random_state=42)}
    model=constructors[method]()
    try:
        model.fit(X_train,y_train);y_pred=model.predict(X_test)
        scores=cross_val_score(model,X,y,cv=cv_folds,scoring="r2",error_score="raise") if cv_folds else None
    except ValueError as exc:return json.dumps({"error":f"回归训练或验证前提不足: {exc}","error_type":"model_validation_failed"},ensure_ascii=False)
    if not np.isfinite(y_pred).all() or scores is not None and not np.isfinite(scores).all():return json.dumps({"error":"模型预测或验证结果非有限","error_type":"nonfinite_validation"},ensure_ascii=False)
    coefficients=getattr(model,"coef_",None);weights=model.feature_importances_ if hasattr(model,"feature_importances_") else coefficients
    importance={f:round(float(v),4) for f,v in sorted(zip(feature_cols,weights),key=lambda pair:-abs(pair[1]))}
    result={"method_contract":"analysis_method_result.v1","status":"supported","claim_ceiling":"predictive_holdout_only",
            "data_identity":workspace.get_data_identity(name),"requested_method":method,"method":type(model).__name__,"target_col":target_col,"feature_cols":feature_cols,
            "train_size":len(X_train),"test_size":len(X_test),"validation":_model_validation(len(workspace.get(name)),len(data)),"evaluation":{"y_true":y_test.tolist(),"y_pred":y_pred.tolist()},
            "metrics":{"r2":round(float(r2_score(y_test,y_pred)),4),"rmse":round(float(np.sqrt(mean_squared_error(y_test,y_pred))),4),"mae":round(float(mean_absolute_error(y_test,y_pred)),4)},
            "feature_importance":importance,"feature_importance_semantics":"signed_elastic_net_coefficients" if method=="linear" else "impurity_based_model_importance",
            "limitations":["当前随机按行留出评估；未按时间或业务单位分组，不证明未来、总体或因果效果。","linear参数实际使用ElasticNet；不代表未惩罚普通最小二乘。","模型特征重要性或系数只描述当前拟合，不识别因果驱动。"]}
    if coefficients is not None:result["coefficients"]={f:float(v) for f,v in zip(feature_cols,coefficients)}
    if cv_folds:result["cv"]={"folds":cv_folds,"mean":round(float(scores.mean()),4),"std":round(float(scores.std()),4),"scores":scores.tolist(),"scheme":"kfold_without_shuffle","scoring":"r2"}
    _record_model(name,_model_key(name,"regression",target_col),target_col,feature_cols,model,"regression")
    return json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)


@registry.register(
    name="attribution_analysis",
    description="因素分析：原标准化 OLS＋HC3、Holm 与 VIF 的调整关联；不识别因果驱动。",
    output_contract=MINIMAL_PRODUCT_CONTRACTS["attribution_analysis"],
    schema_overrides={
        "name": {"description": "数据集名称"},
        "target_col": {"description": "目标变量列；不得同时作为特征"},
        "unit_col": {"description": "可选单位列，仅披露观测范围；不据此聚合或聚类校正"},
        "time_col": {"description": "可选时间列，仅披露观测范围；不据此校正时间相关性"},
        "features": {"description": "特征列，逗号分隔，为空则自动选择数值列"},
    },
)
def attribution_analysis(name: str, target_col: str, features: str = "", unit_col: str = "", time_col: str = "") -> str:
    df, err = get_df(name)
    if err:
        return err

    from data_agent.tools.factor_analysis import _attribution_result
    from data_agent.session.workspace import workspace
    try:
        payload=_attribution_result(df,{"name":name,"target_col":target_col,"features":features,"unit_col":unit_col,"time_col":time_col},workspace.get_data_identity(name))
    except (ValueError,TypeError) as exc:
        return json.dumps({"error":str(exc)},ensure_ascii=False)
    return json.dumps(payload,ensure_ascii=False,allow_nan=False)
