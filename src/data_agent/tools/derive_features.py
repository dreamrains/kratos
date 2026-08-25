"""特征派生工具：从原始数据自动派生新分析特征。"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from data_agent.session.workspace import workspace
from data_agent.tools.registry import registry


@registry.register(
    name="derive_features",
    description=(
        "从原始数据自动派生新特征。feature_type 可选: "
        "time_features（从日期列提取年/月/日/周几/季度/是否周末），"
        "lag_features（滞后特征，params: lag_periods 如 1,7,30），"
        "rolling_features（滚动统计，params: window 如 7, agg 如 mean/std/min/max），"
        "ratio_features（比率特征，params: numerator, denominator），"
        "bin_features（分箱，params: bins 如 5 或 [0,10,20,100], labels），"
        "onehot_encoding（独热编码，params: drop_first=true/false）。"
        "columns 指定目标列（逗号分隔）。save_as 指定保存为新数据集名称。"
    ),
    schema_overrides={
        "name": {"description": "数据集名称"},
        "feature_type": {"description": "特征类型", "enum": ["time_features", "lag_features", "rolling_features", "ratio_features", "bin_features", "onehot_encoding"]},
        "columns": {"description": "目标列，逗号分隔"},
        "params": {"description": "特征参数，JSON 格式"},
        "save_as": {"description": "保存为新数据集名称"},
    },
)
def derive_features(
    name: str,
    feature_type: str,
    columns: str = "",
    params: str = "",
    save_as: str = "",
) -> str:
    df = workspace.get(name)
    if df is None:
        available = list(workspace.list_datasets().keys())
        return json.dumps({"error": f"数据集 '{name}' 不存在。可用: {available}"}, ensure_ascii=False)

    df = df.copy()

    try:
        p = json.loads(params) if params else {}
    except json.JSONDecodeError:
        return json.dumps({"error": "params 必须是有效的 JSON"}, ensure_ascii=False)

    target_cols = [c.strip() for c in columns.split(",") if c.strip()] if columns else list(df.columns)
    new_cols = []

    try:
        if feature_type == "time_features":
            for col in target_cols:
                if col not in df.columns:
                    continue
                if not pd.api.types.is_datetime64_any_dtype(df[col]):
                    try:
                        df[col] = pd.to_datetime(df[col])
                    except Exception:
                        continue
                df[f"{col}_year"] = df[col].dt.year
                df[f"{col}_month"] = df[col].dt.month
                df[f"{col}_day"] = df[col].dt.day
                df[f"{col}_dayofweek"] = df[col].dt.dayofweek
                df[f"{col}_quarter"] = df[col].dt.quarter
                df[f"{col}_is_weekend"] = df[col].dt.dayofweek.isin([5, 6]).astype(int)
                new_cols.extend([f"{col}_year", f"{col}_month", f"{col}_day",
                                 f"{col}_dayofweek", f"{col}_quarter", f"{col}_is_weekend"])

        elif feature_type == "lag_features":
            lag_periods = p.get("lag_periods", "1")
            if isinstance(lag_periods, str):
                lag_periods = [int(x.strip()) for x in lag_periods.split(",")]
            for col in target_cols:
                if col not in df.columns or not pd.api.types.is_numeric_dtype(df[col]):
                    continue
                for lag in lag_periods:
                    lag_col = f"{col}_lag{lag}"
                    df[lag_col] = df[col].shift(lag)
                    new_cols.append(lag_col)

        elif feature_type == "rolling_features":
            window = int(p.get("window", 7))
            agg = p.get("agg", "mean")
            for col in target_cols:
                if col not in df.columns or not pd.api.types.is_numeric_dtype(df[col]):
                    continue
                roll_col = f"{col}_rolling{window}_{agg}"
                roller = df[col].rolling(window=window, min_periods=1)
                if agg == "mean":
                    df[roll_col] = roller.mean()
                elif agg == "std":
                    df[roll_col] = roller.std()
                elif agg == "min":
                    df[roll_col] = roller.min()
                elif agg == "max":
                    df[roll_col] = roller.max()
                new_cols.append(roll_col)

        elif feature_type == "ratio_features":
            numerator = p.get("numerator", "")
            denominator = p.get("denominator", "")
            if not numerator or not denominator:
                return json.dumps({"error": "ratio_features 需要 numerator 和 denominator"}, ensure_ascii=False)
            ratio_col = f"{numerator}_div_{denominator}"
            df[ratio_col] = df[numerator] / df[denominator].replace(0, np.nan)
            new_cols.append(ratio_col)

        elif feature_type == "bin_features":
            bins = p.get("bins", "5")
            if isinstance(bins, str):
                try:
                    bins = int(bins)
                except ValueError:
                    bins = [float(x.strip()) for x in bins.split(",")]
            for col in target_cols:
                if col not in df.columns or not pd.api.types.is_numeric_dtype(df[col]):
                    continue
                bin_col = f"{col}_binned"
                df[bin_col] = pd.cut(df[col], bins=bins)
                new_cols.append(bin_col)

        elif feature_type == "onehot_encoding":
            drop_first = p.get("drop_first", "true").lower() == "true"
            for col in target_cols:
                if col not in df.columns:
                    continue
                dummies = pd.get_dummies(df[col], prefix=col, drop_first=drop_first)
                df = pd.concat([df, dummies], axis=1)
                new_cols.extend(list(dummies.columns))

        else:
            return json.dumps({"error": f"不支持的 feature_type: {feature_type}"}, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"error": f"特征派生失败: {e}"}, ensure_ascii=False)

    target_name = save_as or workspace.next_analysis_name(name, "features")
    derive_result = workspace.derive(
        name,
        target_name,
        df,
        expression=f"feature_type={feature_type}; columns={columns or 'all'}",
    )
    if derive_result.startswith("Error:"):
        return json.dumps({"error": derive_result}, ensure_ascii=False)

    return json.dumps({
        "dataset": target_name,
        "source_dataset": name,
        "feature_type": feature_type,
        "new_columns": new_cols,
        "total_columns": len(df.columns),
        "rows": len(df),
    }, ensure_ascii=False, indent=2)
