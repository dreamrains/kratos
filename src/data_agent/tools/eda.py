"""L2: 探索性分析工具。"""

from __future__ import annotations

import json
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats as sp_stats

from data_agent.session.workspace import workspace
from data_agent.tools._utils import get_df, safe_jsonify
from data_agent.tools.registry import registry


@registry.register(
    name="analyze_time_series",
    description="分析时间序列趋势、季节性和突变点。date_col 和 value_col 可自动推断（留空即可）。",
)
def analyze_time_series(name: str, date_col: str = "", value_col: str = "", target_col: str = "") -> str:
    df, err = get_df(name)
    if err:
        return err

    # 自动推断日期列
    inferred = {}
    if not date_col:
        # 优先选择 datetime64 列
        dt_cols = [c for c in df.columns if pd.api.types.is_datetime64_any_dtype(df[c])]
        if dt_cols:
            date_col = dt_cols[0]
        else:
            # 尝试可转换为日期的列
            for c in df.columns:
                if df[c].dtype == object:
                    try:
                        pd.to_datetime(df[c].dropna().head(20))
                        date_col = c
                        break
                    except (ValueError, TypeError):
                        continue
        if date_col:
            inferred["date_col"] = date_col

    # 自动推断数值列
    col = target_col or value_col
    if not col:
        # 选择第一个 int64/float64 列（排除 ID 类低 nunique 列）
        num_cols = df.select_dtypes(include=[np.number]).columns
        for c in num_cols:
            nunique = df[c].nunique()
            if nunique > 2 and nunique > len(df) * 0.01:
                col = c
                break
        if not col and len(num_cols) > 0:
            col = num_cols[0]
        if col:
            inferred["value_col"] = col

    if not date_col:
        return "Error: 无法自动推断日期列，请手动指定 date_col 参数"
    if not col:
        return "Error: 无法自动推断数值列，请手动指定 value_col 参数"

    if date_col not in df.columns or col not in df.columns:
        return f"Error: 列不存在。可用列: {list(df.columns)}"

    ts = df[[date_col, col]].dropna().copy()
    ts[date_col] = pd.to_datetime(ts[date_col], errors="coerce")
    ts = ts.dropna().sort_values(date_col)

    if ts.empty:
        return "Error: 有效数据为空"

    values = ts[col].values.astype(float)

    result = {
        "data_points": len(values),
        "date_range": {
            "start": safe_jsonify(ts[date_col].iloc[0]),
            "end": safe_jsonify(ts[date_col].iloc[-1]),
        },
        "statistics": {
            "mean": round(float(np.mean(values)), 4),
            "std": round(float(np.std(values)), 4),
            "min": round(float(np.min(values)), 4),
            "max": round(float(np.max(values)), 4),
        },
    }

    if inferred:
        result["inferred_columns"] = inferred

    # 趋势检测（线性回归）
    if len(values) >= 3:
        x = np.arange(len(values))
        slope, intercept, r_value, p_value, std_err = sp_stats.linregress(x, values)
        result["trend"] = {
            "direction": "up" if slope > 0 else "down" if slope < 0 else "flat",
            "slope": round(float(slope), 4),
            "r_squared": round(float(r_value**2), 4),
            "p_value": round(float(p_value), 6),
            "significant": bool(p_value < 0.05),
        }

    # 突变点检测（简单方法：滑动窗口均值差异）
    if len(values) >= 10:
        window = max(3, len(values) // 5)
        changes = []
        for i in range(window, len(values) - window):
            before = np.mean(values[max(0, i - window):i])
            after = np.mean(values[i:i + window])
            change_pct = (after - before) / abs(before) * 100 if before != 0 else 0
            if abs(change_pct) > 10:
                changes.append({
                    "index": int(i),
                    "date": safe_jsonify(ts[date_col].iloc[i]),
                    "change_pct": round(float(change_pct), 2),
                    "direction": "increase" if change_pct > 0 else "decrease",
                })
        if changes:
            changes.sort(key=lambda x: abs(x["change_pct"]), reverse=True)
            result["change_points"] = changes[:5]

    # 季节性检测（自相关）
    if len(values) >= 14:
        acf_values = []
        max_lag = min(len(values) // 2, 30)
        for lag in range(1, max_lag + 1):
            if len(values) > lag:
                r = np.corrcoef(values[:-lag], values[lag:])[0, 1]
                acf_values.append({"lag": lag, "autocorrelation": round(float(r), 4)})
        if acf_values:
            best = max(acf_values, key=lambda x: abs(x["autocorrelation"]))
            result["seasonality"] = {
                "strongest_period": best["lag"],
                "autocorrelation": best["autocorrelation"],
                "likely_seasonal": bool(abs(best["autocorrelation"]) > 0.5),
            }

    # 添加 suggested_next
    result["suggested_next"] = [
        "correlation_analysis 检查哪些指标与目标变量相关",
        "distribution_analysis 检查目标变量分布特征",
    ]

    return json.dumps(result, ensure_ascii=False, indent=2)


@registry.register(
    name="correlation_analysis",
    description="计算数值列之间的相关系数矩阵。返回高相关性列表，完整矩阵自动持久化。",
)
def correlation_analysis(name: str, columns: str = "", method: str = "pearson") -> str:
    df, err = get_df(name)
    if err:
        return err

    numeric_df = df.select_dtypes(include=[np.number])
    if columns:
        cols = [c.strip() for c in columns.split(",")]
        numeric_df = numeric_df[[c for c in cols if c in numeric_df.columns]]

    if numeric_df.empty:
        return "Error: 没有可分析的数值列"

    method = method if method in ("pearson", "spearman", "kendall") else "pearson"
    corr = numeric_df.corr(method=method)

    # 完整矩阵（详情）
    full_matrix = {}
    cols_list = list(corr.columns)
    for c1 in cols_list:
        full_matrix[c1] = {}
        for c2 in cols_list:
            full_matrix[c1][c2] = round(float(corr.loc[c1, c2]), 4)

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
        "high_correlations": high_correlations,
        "suggested_next": [
            "distribution_analysis 检查相关变量的分布特征",
            "regression_analysis 建立回归模型量化影响",
        ],
    }

    return json.dumps(result, ensure_ascii=False, indent=2)


@registry.register(
    name="distribution_analysis",
    description="分析数值列的分布特征：偏度、峰度、正态性。完整分位数详情自动持久化。",
)
def distribution_analysis(name: str, columns: str = "") -> str:
    df, err = get_df(name)
    if err:
        return err

    numeric_df = df.select_dtypes(include=[np.number])
    if columns:
        cols = [c.strip() for c in columns.split(",")]
        numeric_df = numeric_df[[c for c in cols if c in numeric_df.columns]]

    if numeric_df.empty:
        return "Error: 没有可分析的数值列"

    result = {}
    for col in numeric_df.columns:
        values = numeric_df[col].dropna().values
        if len(values) < 2:
            continue

        skewness = round(float(sp_stats.skew(values)), 4)
        kurtosis = round(float(sp_stats.kurtosis(values)), 4)

        # 正态性检验 (Shapiro-Wilk, n < 5000)
        normality = None
        if len(values) < 5000:
            stat_sw, p_sw = sp_stats.shapiro(values)
            normality = {
                "test": "shapiro",
                "p_value": round(float(p_sw), 6),
                "is_normal": bool(p_sw > 0.05),
            }

        col_result = {
            "count": int(len(values)),
            "mean": round(float(np.mean(values)), 4),
            "std": round(float(np.std(values)), 4),
            "skewness": skewness,
            "kurtosis": kurtosis,
        }
        if normality:
            col_result["normality_test"] = normality

        result[col] = col_result

    result["_suggested_next"] = [
        "correlation_analysis 检查变量间相关性",
        "segmentation_analysis 基于分布特征进行分群",
    ]

    return json.dumps(result, ensure_ascii=False, indent=2)


@registry.register(
    name="segmentation_analysis",
    description="基于特征进行用户/数据分群（KMeans聚类）。",
)
def segmentation_analysis(name: str, features: str, n_clusters: int = 3) -> str:
    df, err = get_df(name)
    if err:
        return err

    from sklearn.cluster import KMeans
    from sklearn.preprocessing import StandardScaler

    feature_cols = [c.strip() for c in features.split(",")]
    missing = [c for c in feature_cols if c not in df.columns]
    if missing:
        return f"Error: 列不存在: {missing}. 可用: {list(df.columns)}"

    data = df[feature_cols].dropna()
    if len(data) < n_clusters:
        return f"Error: 有效数据 ({len(data)}) 少于聚类数 ({n_clusters})"

    scaler = StandardScaler()
    scaled = scaler.fit_transform(data)

    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    labels = kmeans.fit_predict(scaled)

    result = {
        "n_clusters": n_clusters,
        "total_samples": len(data),
        "clusters": [],
    }

    for i in range(n_clusters):
        mask = labels == i
        cluster_data = data[mask]
        profile = {}
        for col in feature_cols:
            profile[col] = {
                "mean": round(float(cluster_data[col].mean()), 4),
                "std": round(float(cluster_data[col].std()), 4),
            }
        result["clusters"].append({
            "cluster_id": i,
            "size": int(mask.sum()),
            "percentage": round(float(mask.sum() / len(data) * 100), 2),
            "profile": profile,
        })

    return json.dumps(result, ensure_ascii=False, indent=2)


@registry.register(
    name="cohort_analysis",
    description=(
        "进行留存分析。user_col 必须是唯一用户ID列（如 user_id），"
        "time_col 是事件时间列，event_col 是可选的事件类型列。"
        "按月计算用户留存率。注意：不适合用非唯一ID列（如渠道名、地区）作为 user_col。"
    ),
)
def cohort_analysis(name: str, user_col: str, time_col: str, event_col: str = "") -> str:
    df, err = get_df(name)
    if err:
        return err

    required = [user_col, time_col]
    missing = [c for c in required if c not in df.columns]
    if missing:
        return f"Error: 列不存在: {missing}. 可用: {list(df.columns)}"

    df = df[required + ([event_col] if event_col and event_col in df.columns else [])].copy()
    df[time_col] = pd.to_datetime(df[time_col], errors="coerce")
    df = df.dropna(subset=[user_col, time_col])

    # 每个用户的首次时间作为 cohort
    df["period"] = df[time_col].dt.to_period("M")
    first_period = df.groupby(user_col)["period"].min().rename("cohort")

    df = df.join(first_period, on=user_col)
    df["cohort_age"] = (df["period"] - df["cohort"]).apply(lambda x: x.n)

    # 留存矩阵
    cohort_counts = df.groupby(["cohort", "cohort_age"])[user_col].nunique().reset_index()
    cohort_counts.columns = ["cohort", "cohort_age", "users"]

    cohort_pivot = cohort_counts.pivot(index="cohort", columns="cohort_age", values="users").fillna(0)

    # 计算留存率
    cohort_sizes = cohort_pivot.iloc[:, 0]
    retention = cohort_pivot.divide(cohort_sizes, axis=0) * 100

    result = {
        "cohorts": [],
    }
    for cohort in retention.index:
        row = {
            "cohort": str(cohort),
            "size": int(cohort_sizes[cohort]),
            "retention": {},
        }
        for age in retention.columns:
            val = retention.loc[cohort, age]
            if not pd.isna(val):
                row["retention"][f"month_{age}"] = round(float(val), 2)
        result["cohorts"].append(row)

    return json.dumps(result, ensure_ascii=False, indent=2)
