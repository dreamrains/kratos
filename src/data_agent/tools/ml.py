"""L4: 机器学习工具。"""

from __future__ import annotations

import json
from typing import Optional

import numpy as np
import pandas as pd

from data_agent.session.workspace import workspace
from data_agent.tools._utils import get_df
from data_agent.tools.registry import registry


# 存储trained models
_trained_models: dict = {}
# Ephemeral estimator objects remain process-local, but their provenance is
# explicit and checked before downstream explanations or simulations use them.
_trained_model_metadata: dict = {}


def _record_model(name: str, key: str, target_col: str, feature_cols: list[str], model, kind: str) -> None:
    _trained_models[key] = model
    _trained_model_metadata[key] = {
        "model_key": key,
        "kind": kind,
        "target_col": target_col,
        "feature_cols": list(feature_cols),
        "data_identity": workspace.get_data_identity(name),
    }


@registry.register(
    name="forecast",
    description="时间序列预测。支持 Prophet 和简单统计方法。返回诊断指标（MAPE、RMSE、季节性强度）。",
    schema_overrides={
        "name": {"description": "数据集名称"},
        "target_col": {"description": "预测目标列"},
        "date_col": {"description": "日期列名"},
        "periods": {"description": "预测期数"},
        "method": {"description": "预测方法", "enum": ["auto", "simple", "prophet"]},
    },
)
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


def _legacy_forecast(name: str, target_col: str, date_col: str = "", periods: int = 7, method: str = "auto") -> str:
    periods_value, periods_error = _coerce_forecast_periods(periods)
    if periods_error:
        return _forecast_error(periods_error, "invalid_parameter", "periods")
    periods = periods_value
    df, err = get_df(name)
    if err:
        return err

    if target_col not in df.columns:
        return _forecast_error(f"Column '{target_col}' not found. Available columns: {list(df.columns)}", "missing_column", "target_col")

    if not date_col:
        date_col = _infer_forecast_date_col(df)

    if target_col not in df.columns:
        return f"Error: 列 '{target_col}' 不存在。可用: {list(df.columns)}"

    if date_col and date_col in df.columns:
        ts = df[[date_col, target_col]].dropna().copy()
        ts[date_col] = pd.to_datetime(ts[date_col], errors="coerce")
        ts = ts.dropna().sort_values(date_col)
    else:
        ts = df[[target_col]].dropna().copy()

    values = ts[target_col].values.astype(float)
    if len(values) < 10:
        return _forecast_error(f"Too few data points ({len(values)}); at least 10 are required.", "insufficient_data", "name")
    if len(values) < 10:
        return f"Error: 数据点太少 ({len(values)})，至少需要 10 个"

    if method == "auto":
        method = "simple" if len(values) < 30 else "prophet"

    # 计算季节性强度（自相关）
    seasonality_strength = 0.0
    if len(values) >= 14:
        max_lag = min(len(values) // 2, 30)
        acf_vals = []
        for lag in range(1, max_lag + 1):
            if len(values) > lag:
                r = np.corrcoef(values[:-lag], values[lag:])[0, 1]
                acf_vals.append(r)
        if acf_vals:
            seasonality_strength = round(float(max(abs(v) for v in acf_vals)), 4)

    if method == "simple":
        # 简单方法：移动平均 + 趋势外推
        window = min(7, len(values) // 3)
        ma = np.convolve(values, np.ones(window) / window, mode="valid")
        trend_slope = np.polyfit(np.arange(len(ma)), ma, 1)[0]
        last_ma = ma[-1]
        forecast_vals = [last_ma + trend_slope * (i + 1) for i in range(periods)]

        # 计算历史拟合 MAPE 和 RMSE
        fitted = np.convolve(values, np.ones(window) / window, mode="valid")
        actual = values[window - 1:]
        min_len = min(len(fitted), len(actual))
        fitted = fitted[:min_len]
        actual = actual[:min_len]
        nonzero_mask = actual != 0
        mape = round(float(np.mean(np.abs((actual[nonzero_mask] - fitted[nonzero_mask]) / actual[nonzero_mask])) * 100), 2) if nonzero_mask.any() else None
        rmse = round(float(np.sqrt(np.mean((actual - fitted) ** 2))), 4)

        result = {
            "method": "moving_average_trend",
            "periods": periods,
            "date_col": date_col,
            "fallback_used": False,
            "window": window,
            "trend_slope": round(float(trend_slope), 4),
            "last_observed": round(float(values[-1]), 4),
            "forecast": [round(float(v), 4) for v in forecast_vals],
            "diagnostics": {
                "mape": mape,
                "rmse": rmse,
                "seasonality_strength": seasonality_strength,
            },
            "note": "简单趋势外推，适用于短期预测",
        }
        return json.dumps(result, ensure_ascii=False, indent=2)

    if method == "prophet":
        try:
            from prophet import Prophet

            if date_col and date_col in ts.columns:
                prophet_df = pd.DataFrame({
                    "ds": ts[date_col],
                    "y": values,
                })
            else:
                dates = pd.date_range(start="2020-01-01", periods=len(values), freq="D")
                prophet_df = pd.DataFrame({"ds": dates, "y": values})

            model = Prophet(yearly_seasonality=True, weekly_seasonality=True, daily_seasonality=False)
            model.fit(prophet_df)

            future = model.make_future_dataframe(periods=periods)
            forecast_df = model.predict(future)

            # 计算历史拟合 MAPE 和 RMSE
            historical = forecast_df.iloc[:-periods]
            hist_actual = values
            hist_min = min(len(historical["yhat"].values), len(hist_actual))
            yhat_hist = historical["yhat"].values[:hist_min]
            y_actual = hist_actual[:hist_min]
            nonzero_mask = y_actual != 0
            mape = round(float(np.mean(np.abs((y_actual[nonzero_mask] - yhat_hist[nonzero_mask]) / y_actual[nonzero_mask])) * 100), 2) if nonzero_mask.any() else None
            rmse = round(float(np.sqrt(np.mean((y_actual - yhat_hist) ** 2))), 4)

            fc = forecast_df.tail(periods)
            result = {
                "method": "prophet",
                "forecast": [],
                "components": {
                    "trend": round(float(fc["trend"].iloc[-1]), 4),
                },
                "diagnostics": {
                    "mape": mape,
                    "rmse": rmse,
                    "seasonality_strength": seasonality_strength,
                },
            }
            for _, row in fc.iterrows():
                result["forecast"].append({
                    "date": str(row["ds"].date()),
                    "yhat": round(float(row["yhat"]), 4),
                    "yhat_lower": round(float(row["yhat_lower"]), 4),
                    "yhat_upper": round(float(row["yhat_upper"]), 4),
                })
            return json.dumps(result, ensure_ascii=False, indent=2)

        except ImportError:
            from data_agent.utils.logging import get_logger
            get_logger("tools").warning("Prophet not available, falling back to simple forecast")
            raw = _legacy_forecast(name, target_col, date_col, periods, "simple")
            try:
                result = json.loads(raw)
                result["fallback_used"] = True
                result["fallback_reason"] = "prophet_not_available"
                return json.dumps(result, ensure_ascii=False, indent=2)
            except json.JSONDecodeError:
                return raw
        except (AttributeError, Exception) as e:
            from data_agent.utils.logging import get_logger
            get_logger("tools").warning(f"Prophet failed: {e}, falling back to simple forecast")
            raw = _legacy_forecast(name, target_col, date_col, periods, "simple")
            try:
                result = json.loads(raw)
                result["fallback_used"] = True
                result["fallback_reason"] = f"prophet_failed: {e}"
                return json.dumps(result, ensure_ascii=False, indent=2)
            except json.JSONDecodeError:
                return raw

    return f"Error: 不支持的方法 '{method}'。可用: auto, simple, prophet"


@registry.register(
    name="forecast",
    description="时间序列预测：候选基线经有序留出回测选择，返回区间、窗口和限制。",
    schema_overrides={
        "name": {"description": "数据集名称"},
        "target_col": {"description": "预测目标列"},
        "date_col": {"description": "日期列；为空时自动推断"},
        "periods": {"description": "短期预测期数"},
        "method": {"description": "仅支持 backtest/auto；不再将样本内拟合报告为验证"},
    },
)
def forecast(name: str, target_col: str, date_col: str = "", periods: int = 7, method: str = "auto"):
    """Existing public forecast entry with Slice 3 backtesting semantics."""
    periods_value, error = _coerce_forecast_periods(periods)
    if error:
        return _forecast_error(error, "invalid_parameter", "periods")
    if method not in {"auto", "backtest", "simple", "prophet"}:
        return _forecast_error("method must be auto or backtest", "invalid_parameter", "method")
    df, lookup_error = get_df(name)
    if lookup_error:
        return lookup_error
    if not date_col:
        date_col = _infer_forecast_date_col(df)
    if not date_col:
        return _forecast_error("date_col is required for a time-series forecast", "missing_date_column", "date_col")
    from data_agent.tools.forecasting import backtested_forecast
    result = backtested_forecast(name, target_col, date_col, periods_value)
    if result.data is None:
        return json.dumps({"error": result.summary, "error_type": "forecast_failed"}, ensure_ascii=False)
    payload = dict(result.data)
    payload["periods"] = periods_value
    payload["date_col"] = date_col
    payload["fallback_used"] = False
    payload["diagnostics"] = {
        "mae": payload.get("backtest", {}).get("mae"),
        "backtest_scheme": payload.get("parameters", {}).get("backtest_scheme"),
    }
    return json.dumps(payload, ensure_ascii=False, default=str)


@registry.register(
    name="classification",
    description="分类模型训练和评估。支持 cv_folds 交叉验证。",
    schema_overrides={
        "name": {"description": "数据集名称"},
        "target_col": {"description": "目标分类列"},
        "features": {"description": "特征列，逗号分隔，为空则自动选择数值列"},
        "method": {"description": "分类方法", "enum": ["auto", "logistic", "rf"]},
        "cv_folds": {"description": "交叉验证折数，0表示不交叉验证"},
    },
)
def classification(name: str, target_col: str, features: str = "", method: str = "auto", cv_folds: int = 0) -> str:
    from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import train_test_split, cross_val_score
    from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score
    from sklearn.preprocessing import LabelEncoder

    df, err = get_df(name)
    if err:
        return err

    if target_col not in df.columns:
        return f"Error: 目标列 '{target_col}' 不存在。可用: {list(df.columns)}"

    if features:
        feature_cols = [c.strip() for c in features.split(",")]
    else:
        feature_cols = [c for c in df.select_dtypes(include=[np.number]).columns if c != target_col]

    if not feature_cols:
        return "Error: 没有可用的特征列"

    data = df[feature_cols + [target_col]].dropna()
    if len(data) < 20:
        return f"Error: 有效数据 ({len(data)}) 太少，至少需要 20 条"

    X = data[feature_cols].values
    y = data[target_col].values

    # 标签编码（如果是字符串）
    le = None
    if y.dtype == object:
        le = LabelEncoder()
        y = le.fit_transform(y)

    n_classes = len(np.unique(y))
    if n_classes < 2:
        return "Error: 目标变量只有 1 个类别"

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    if method == "auto":
        model = GradientBoostingClassifier(n_estimators=100, random_state=42)
    elif method == "logistic":
        model = LogisticRegression(max_iter=1000, random_state=42)
    elif method == "rf":
        model = RandomForestClassifier(n_estimators=100, random_state=42)
    else:
        model = GradientBoostingClassifier(n_estimators=100, random_state=42)

    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)

    # 特征重要性
    importances = {}
    if hasattr(model, "feature_importances_"):
        for fname, imp in sorted(zip(feature_cols, model.feature_importances_), key=lambda x: -x[1]):
            importances[fname] = round(float(imp), 4)
    elif hasattr(model, "coef_"):
        coefs = model.coef_[0] if model.coef_.ndim > 1 else model.coef_
        for fname, coef in sorted(zip(feature_cols, coefs), key=lambda x: abs(x[1]), reverse=True):
            importances[fname] = round(float(coef), 4)

    result = {
        "method": type(model).__name__,
        "n_classes": int(n_classes),
        "train_size": len(X_train),
        "test_size": len(X_test),
        "metrics": {
            "accuracy": round(float(accuracy_score(y_test, y_pred)), 4),
        },
        "feature_importance": importances,
    }

    if n_classes == 2:
        result["metrics"]["f1"] = round(float(f1_score(y_test, y_pred, average="binary")), 4)
        result["metrics"]["precision"] = round(float(precision_score(y_test, y_pred, average="binary")), 4)
        result["metrics"]["recall"] = round(float(recall_score(y_test, y_pred, average="binary")), 4)
    else:
        result["metrics"]["f1_macro"] = round(float(f1_score(y_test, y_pred, average="macro")), 4)

    # 交叉验证
    if cv_folds >= 2:
        cv_scores = cross_val_score(model, X, y, cv=cv_folds, scoring="accuracy")
        result["cv"] = {
            "folds": cv_folds,
            "mean": round(float(cv_scores.mean()), 4),
            "std": round(float(cv_scores.std()), 4),
        }

    # 保存模型
    model_key = f"{name}_cls_{target_col}"
    _record_model(name, model_key, target_col, feature_cols, model, "classification")

    return json.dumps(result, ensure_ascii=False, indent=2)


@registry.register(
    name="regression_analysis",
    description="回归分析。支持线性回归、弹性网络、梯度提升。支持 cv_folds 交叉验证。",
    schema_overrides={
        "name": {"description": "数据集名称"},
        "target_col": {"description": "目标回归列"},
        "features": {"description": "特征列，逗号分隔，为空则自动选择数值列"},
        "method": {"description": "回归方法", "enum": ["auto", "linear", "rf", "gbrt"]},
        "cv_folds": {"description": "交叉验证折数，0表示不交叉验证"},
    },
)
def regression_analysis(name: str, target_col: str, features: str = "", method: str = "auto", cv_folds: int = 0) -> str:
    from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
    from sklearn.linear_model import ElasticNet
    from sklearn.model_selection import train_test_split, cross_val_score
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

    df, err = get_df(name)
    if err:
        return err

    if target_col not in df.columns:
        return f"Error: 目标列 '{target_col}' 不存在。可用: {list(df.columns)}"

    if features:
        feature_cols = [c.strip() for c in features.split(",")]
    else:
        feature_cols = [c for c in df.select_dtypes(include=[np.number]).columns if c != target_col]

    if not feature_cols:
        return "Error: 没有可用的特征列"

    data = df[feature_cols + [target_col]].dropna()
    if len(data) < 20:
        return f"Error: 有效数据 ({len(data)}) 太少，至少需要 20 条"

    X = data[feature_cols].values
    y = data[target_col].values.astype(float)

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    if method == "auto" or method == "gbrt":
        model = GradientBoostingRegressor(n_estimators=100, random_state=42)
    elif method == "linear":
        model = ElasticNet(random_state=42)
    elif method == "rf":
        model = RandomForestRegressor(n_estimators=100, random_state=42)
    else:
        model = GradientBoostingRegressor(n_estimators=100, random_state=42)

    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)

    importances = {}
    if hasattr(model, "feature_importances_"):
        for fname, imp in sorted(zip(feature_cols, model.feature_importances_), key=lambda x: -x[1]):
            importances[fname] = round(float(imp), 4)
    elif hasattr(model, "coef_"):
        for fname, coef in sorted(zip(feature_cols, model.coef_), key=lambda x: abs(x[1]), reverse=True):
            importances[fname] = round(float(coef), 4)

    result = {
        "method": type(model).__name__,
        "train_size": len(X_train),
        "test_size": len(X_test),
        "metrics": {
            "r2": round(float(r2_score(y_test, y_pred)), 4),
            "rmse": round(float(np.sqrt(mean_squared_error(y_test, y_pred))), 4),
            "mae": round(float(mean_absolute_error(y_test, y_pred)), 4),
        },
        "feature_importance": importances,
    }

    # 交叉验证
    if cv_folds >= 2:
        cv_scores = cross_val_score(model, X, y, cv=cv_folds, scoring="r2")
        result["cv"] = {
            "folds": cv_folds,
            "mean": round(float(cv_scores.mean()), 4),
            "std": round(float(cv_scores.std()), 4),
        }

    model_key = f"{name}_reg_{target_col}"
    _record_model(name, model_key, target_col, feature_cols, model, "regression")

    return json.dumps(result, ensure_ascii=False, indent=2)


@registry.register(
    name="attribution_analysis",
    description="归因分析：识别目标变量的关键驱动因素，基于特征重要性和相关性。",
    schema_overrides={
        "name": {"description": "数据集名称"},
        "target_col": {"description": "目标变量列"},
        "features": {"description": "特征列，逗号分隔，为空则自动选择数值列"},
    },
)
def attribution_analysis(name: str, target_col: str, features: str = "", unit_col: str = "", time_col: str = "") -> str:
    df, err = get_df(name)
    if err:
        return err

    from data_agent.tools.factor_analysis import factor_relationships
    selected_features = [c.strip() for c in features.split(",") if c.strip()] if features else [c for c in df.select_dtypes(include=[np.number]).columns if c != target_col]
    result = factor_relationships(name, target_col, selected_features, unit_col, time_col)
    if result.data is None:
        return json.dumps({"error": result.summary}, ensure_ascii=False)
    payload = dict(result.data)
    payload["top_drivers"] = payload.get("estimates") or payload.get("bivariate_associations") or []
    return json.dumps(payload, ensure_ascii=False, default=str)

    if target_col not in df.columns:
        return f"Error: 目标列 '{target_col}' 不存在。可用: {list(df.columns)}"

    if features:
        feature_cols = [c.strip() for c in features.split(",")]
    else:
        feature_cols = [c for c in df.select_dtypes(include=[np.number]).columns if c != target_col]

    if not feature_cols:
        return "Error: 没有可用的特征列"

    data = df[feature_cols + [target_col]].dropna()
    X = data[feature_cols].values
    y = data[target_col].values.astype(float)

    # 相关性归因
    correlations = {}
    for col in feature_cols:
        r = np.corrcoef(data[col].values, y)[0, 1]
        correlations[col] = round(float(r), 4)

    # 优先复用已训练的模型
    model_key = f"{name}_reg_{target_col}"
    if model_key in _trained_models and hasattr(_trained_models[model_key], "feature_importances_"):
        model = _trained_models[model_key]
        reused = True
    else:
        from sklearn.ensemble import GradientBoostingRegressor
        model = GradientBoostingRegressor(n_estimators=100, random_state=42)
        model.fit(X, y)
        reused = False

    model_importance = {}
    for fname, imp in sorted(zip(feature_cols, model.feature_importances_), key=lambda x: -x[1]):
        model_importance[fname] = round(float(imp), 4)

    # 综合评分
    drivers = []
    for col in feature_cols:
        corr_score = abs(correlations.get(col, 0))
        imp_score = model_importance.get(col, 0)
        combined = round(corr_score * 0.3 + imp_score * 0.7, 4)
        drivers.append({
            "feature": col,
            "correlation": correlations.get(col, 0),
            "model_importance": model_importance.get(col, 0),
            "combined_score": combined,
        })

    drivers.sort(key=lambda x: x["combined_score"], reverse=True)

    result = {
        "target": target_col,
        "top_drivers": drivers[:10],
        "method": "correlation + GradientBoosting importance",
        "model_reused": reused,
    }

    return json.dumps(result, ensure_ascii=False, indent=2)
