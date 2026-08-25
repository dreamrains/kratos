"""L2: 探索性分析工具。"""

from __future__ import annotations

import json
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats as sp_stats

from data_agent.session.workspace import workspace
from data_agent.tools._utils import get_df, safe_jsonify, resolve_date_col, parse_period_range, analyze_period_structure, compare_period_structures
from data_agent.tools.registry import ToolResult
from data_agent.tools.registry import registry


@registry.register(
    name="analyze_time_series",
    description=(
        "分析时间序列趋势、季节性和突变点。"
        "使用场景：指标随时间变化的趋势方向、周期性检测、异常时间点定位。"
        "不适用场景：无时间列的数据、跨维度对比（用 compare_periods）。"
        "参数说明：date_col 和 value_col 可自动推断（留空即可），target_col 为 value_col 的别名。"
        "常见错误：日期列未转换为 datetime 类型（先用 apply_type_conversion 转换）。"
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
    schema_overrides={
        "name": {"description": "数据集名称"},
        "features": {"description": "分群特征列，逗号分隔"},
        "n_clusters": {"description": "聚类数量"},
    },
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


@registry.register(
    name="compare_periods",
    description=(
        "比较两个时间段的数据差异，自动计算各指标的变化量和变化率。"
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
    },
)
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
        "reason": f"两组样本量分别为 {n_a} 和 {n_b}，均值差异存在，建议用 ab_test 验证统计显著性",
        "suggested_args": {
            "name": "<数据集名>",
            "group_col": "<分组列（需包含两组标识）>",
            "metric_col": metric_cols[0],
            "method": "auto",
        },
    }


def compare_periods(
    name: str,
    date_col: str = "",
    metrics: str = "",
    period_a: str = "",
    period_b: str = "",
    dimensions: str = "",
) -> str:
    df, err = get_df(name)
    if err:
        return err

    date_col, dc_err = resolve_date_col(df, date_col)
    if dc_err:
        return f"Error: {dc_err}"

    if date_col not in df.columns:
        return f"Error: 列 '{date_col}' 不存在。可用: {list(df.columns)}"

    df = df.copy()
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.dropna(subset=[date_col])

    ref_date = df[date_col].max().normalize()

    if not period_a or not period_b:
        return "Error: 请指定 period_a 和 period_b 参数"

    pa = parse_period_range(period_a, ref_date)
    pb = parse_period_range(period_b, ref_date)
    if not pa or not pb:
        return "Error: 无法解析时间段。格式: 'YYYY-MM-DD~YYYY-MM-DD' 或 'last_month'/'this_month'"

    mask_a = (df[date_col] >= pa[0]) & (df[date_col] <= pa[1])
    mask_b = (df[date_col] >= pb[0]) & (df[date_col] <= pb[1])
    df_a = df[mask_a]
    df_b = df[mask_b]

    if df_a.empty or df_b.empty:
        return json.dumps({"error": "某个时间段内没有数据", "period_a_rows": len(df_a), "period_b_rows": len(df_b)}, ensure_ascii=False)

    # 时段结构分析
    struct_a = analyze_period_structure(pa[0], pa[1])
    struct_b = analyze_period_structure(pb[0], pb[1])
    comparability = compare_period_structures(struct_a, struct_b)

    # 指标列
    if metrics:
        metric_cols = [c.strip() for c in metrics.split(",")]
    else:
        metric_cols = list(df.select_dtypes(include=[np.number]).columns)
    metric_cols = [c for c in metric_cols if c in df.columns]
    if not metric_cols:
        return "Error: 没有可比较的数值列"

    dim_cols = [c.strip() for c in dimensions.split(",") if c.strip()] if dimensions else []

    def _daily_avg_fields(va: float, vb: float):
        """计算日均值相关字段。"""
        days_a = struct_a["day_count"]
        days_b = struct_b["day_count"]
        da = va / days_a if days_a > 0 else None
        db = vb / days_b if days_b > 0 else None
        d_diff = db - da if da is not None and db is not None else None
        d_pct = (d_diff / abs(da) * 100) if d_diff is not None and da and da != 0 else None
        return {
            "daily_avg_a": round(da, 4) if da is not None else None,
            "daily_avg_b": round(db, 4) if db is not None else None,
            "daily_avg_diff": round(d_diff, 4) if d_diff is not None else None,
            "daily_avg_change_pct": round(d_pct, 2) if d_pct is not None else None,
        }

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
        "comparability": comparability,
    }

    if dim_cols:
        result["dimensions"] = dim_cols
        result["comparisons"] = []
        for _, grp_a in df_a.groupby(dim_cols):
            key = tuple(str(grp_a[dim].iloc[0]) for dim in dim_cols)
            match_mask = pd.Series(True, index=df_b.index)
            for dim, val in zip(dim_cols, key):
                match_mask &= df_b[dim].astype(str) == val
            grp_b = df_b[match_mask]
            row = {"dimension": " / ".join(key)}
            for col in metric_cols:
                va = grp_a[col].sum() if len(grp_a) > 0 else 0
                vb = grp_b[col].sum() if len(grp_b) > 0 else 0
                diff = float(vb) - float(va)
                pct = (diff / abs(float(va)) * 100) if float(va) != 0 else None
                row[col] = {
                    "a": round(float(va), 4),
                    "b": round(float(vb), 4),
                    "diff": round(diff, 4),
                    "change_pct": round(pct, 2) if pct is not None else None,
                    **_daily_avg_fields(float(va), float(vb)),
                }
            result["comparisons"].append(row)
    else:
        result["metrics"] = {}
        for col in metric_cols:
            va = float(df_a[col].sum())
            vb = float(df_b[col].sum())
            diff = vb - va
            pct = (diff / abs(va) * 100) if va != 0 else None
            result["metrics"][col] = {
                "period_a": round(va, 4),
                "period_b": round(vb, 4),
                "diff": round(diff, 4),
                "change_pct": round(pct, 2) if pct is not None else None,
                **_daily_avg_fields(va, vb),
            }

    # Statistical test recommendation
    rec = _recommend_statistical_test(len(df_a), len(df_b), metric_cols, result)
    if rec:
        result["statistical_test_recommendation"] = rec

    return json.dumps(result, ensure_ascii=False, indent=2)


@registry.register(
    name="top_n",
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

    if not sort_by:
        num_cols = list(df.select_dtypes(include=[np.number]).columns)
        if not num_cols:
            return "Error: 没有可排序的数值列，请指定 sort_by 参数"
        sort_by = num_cols[0]

    if sort_by not in df.columns:
        return f"Error: 列 '{sort_by}' 不存在。可用: {list(df.columns)}"

    sorted_df = df.sort_values(by=sort_by, ascending=ascending)

    if columns:
        col_list = [c.strip() for c in columns.split(",")]
        col_list = [c for c in col_list if c in sorted_df.columns]
        if col_list:
            sorted_df = sorted_df[col_list]

    top = sorted_df.head(n)

    result = {
        "sort_by": sort_by,
        "ascending": ascending,
        "n": len(top),
        "records": json.loads(top.to_json(orient="records", date_format="iso", force_ascii=False)),
    }
    if save_as:
        derive_result = workspace.derive(
            name,
            save_as,
            top,
            expression=f"top_n(sort_by={sort_by}; n={n}; ascending={ascending})",
        )
        if derive_result.startswith("Error:"):
            return json.dumps({"error": derive_result}, ensure_ascii=False)
        result["dataset"] = save_as
        result["source_dataset"] = name

    return json.dumps(result, ensure_ascii=False, indent=2)


@registry.register(
    name="contribute_decomposition",
    description=(
        "贡献度分解：将指标的总变化拆解为各维度的贡献比例。"
        "适用于环比/同比变动的归因分析（回答'为什么X变了'）。"
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

    if metric not in df.columns:
        return f"Error: 列 '{metric}' 不存在。可用: {list(df.columns)}"
    if dimension not in df.columns:
        return f"Error: 列 '{dimension}' 不存在。可用: {list(df.columns)}"

    date_col, dc_err = resolve_date_col(df, date_col)
    if dc_err:
        return f"Error: {dc_err}"

    df = df.copy()
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.dropna(subset=[date_col, metric, dimension])

    ref_date = df[date_col].max().normalize()
    pa = parse_period_range(period_a, ref_date)
    pb = parse_period_range(period_b, ref_date)
    if not pa or not pb:
        return "Error: 无法解析时间段。格式: 'YYYY-MM-DD~YYYY-MM-DD' 或 'last_month'/'this_month'"

    mask_a = (df[date_col] >= pa[0]) & (df[date_col] <= pa[1])
    mask_b = (df[date_col] >= pb[0]) & (df[date_col] <= pb[1])
    df_a = df[mask_a]
    df_b = df[mask_b]

    if df_a.empty or df_b.empty:
        return json.dumps({"error": "某个时间段内没有数据"}, ensure_ascii=False)

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
            mean_a_v = float(grp_a[metric].mean()) if len(grp_a) > 0 else 0
            mean_b_v = float(grp_b[metric].mean()) if len(grp_b) > 0 else 0
            weight_a = len(grp_a) / n_a if n_a > 0 else 0
            weight_b = len(grp_b) / n_b if n_b > 0 else 0

            # 加权分解
            weight_effect = (weight_b - weight_a) * (mean_a_v - total_a)
            level_effect = weight_b * (mean_b_v - mean_a_v)
            contrib = weight_effect + level_effect

            pct = (contrib / abs(total_change) * 100) if total_change != 0 else None
            decomposition.append({
                "value": str(v),
                "period_a_mean": round(mean_a_v, 4),
                "period_b_mean": round(mean_b_v, 4),
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
            "label": period_a,
            "range": [str(pa[0].date()), str(pa[1].date())],
            "value": round(total_a, 4),
            "day_count": struct_a["day_count"],
            "weekday_count": struct_a["weekday_count"],
            "weekend_count": struct_a["weekend_count"],
        },
        "period_b": {
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


@registry.register(
    name="funnel_analysis",
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

    # Auto-detect mode
    if mode == "auto":
        if user_col and event_col and steps:
            mode = "steps"
        elif step_col and count_col:
            mode = "aggregate"
        elif rate_cols:
            mode = "rates"
        else:
            # 尝试基于数据结构推断
            cols_lower = {c.lower(): c for c in df.columns}
            if any(k in cols_lower for k in ["user_id", "uid", "openid"]) and any(
                k in cols_lower for k in ["event", "action", "event_type"]
            ):
                mode = "steps"
            elif any(k in cols_lower for k in ["step", "stage", "阶段", "步骤"]):
                mode = "aggregate"
            else:
                # 检查是否有多个率列
                rate_cols_found = [
                    c for c in df.columns
                    if any(kw in c.lower() for kw in ("率", "rate", "ratio", "pct"))
                    and pd.api.types.is_numeric_dtype(df[c])
                ]
                if len(rate_cols_found) >= 2:
                    rate_cols = ",".join(rate_cols_found)
                    mode = "rates"
                else:
                    return "Error: 无法自动检测漏斗模式。请指定 mode 和相应参数。"

    if mode == "steps":
        return _funnel_steps(df, name, user_col, event_col, time_col, steps, dimension, window_hours)
    elif mode == "aggregate":
        return _funnel_aggregate(df, name, step_col, count_col, steps, dimension)
    elif mode == "rates":
        return _funnel_rates(df, name, rate_cols, dimension)
    else:
        return f"Error: 不支持的模式 '{mode}'。可用: auto, steps, aggregate, rates"


def _funnel_steps(
    df: pd.DataFrame, name: str, user_col: str, event_col: str,
    time_col: str, steps: str, dimension: str, window_hours: int,
) -> str:
    """场景A：事件明细数据的漏斗分析。"""
    step_list = [s.strip() for s in steps.split(",") if s.strip()]
    if len(step_list) < 2:
        return "Error: steps 至少需要 2 个步骤"

    for col in [user_col, event_col]:
        if col not in df.columns:
            return f"Error: 列 '{col}' 不存在。可用: {list(df.columns)}"

    if time_col and time_col not in df.columns:
        return f"Error: 时间列 '{time_col}' 不存在"

    # 检查所有步骤是否在数据中存在
    existing_events = set(df[event_col].dropna().unique())
    missing_steps = [s for s in step_list if s not in existing_events]
    if missing_steps:
        return f"Error: 步骤 {missing_steps} 在 '{event_col}' 列中不存在。可用事件: {list(existing_events)[:20]}"

    dim_values = [None]
    if dimension:
        if dimension not in df.columns:
            return f"Error: 维度列 '{dimension}' 不存在"
        dim_values = list(df[dimension].dropna().unique())

    overall_steps_data = {s: set() for s in step_list}
    dim_funnels = {}

    for dv in dim_values:
        sub_df = df if dv is None else df[df[dimension] == dv]
        step_counts = {s: 0 for s in step_list}

        for uid, user_events in sub_df.groupby(user_col):
            user_step_times = {}
            for i, step in enumerate(step_list):
                mask = user_events[event_col] == step
                step_events = user_events[mask]
                if step_events.empty:
                    break

                if time_col and time_col in step_events.columns:
                    first_time = pd.to_datetime(step_events[time_col]).min()
                    if i > 0 and step_list[i - 1] in user_step_times:
                        if first_time < user_step_times[step_list[i - 1]]:
                            break
                        if window_hours > 0:
                            elapsed = (first_time - user_step_times[step_list[i - 1]]).total_seconds() / 3600
                            if elapsed > window_hours:
                                break
                    user_step_times[step] = first_time
                else:
                    user_step_times[step] = True

                step_counts[step] += 1
                if dv is None:
                    overall_steps_data[step].add(uid)

        funnel_steps_list = []
        for i, step in enumerate(step_list):
            count = step_counts[step]
            entry = {"step": step, "count": count}
            if i > 0:
                prev_count = step_counts[step_list[i - 1]]
                entry["step_conversion"] = round(count / prev_count, 4) if prev_count > 0 else 0
            funnel_steps_list.append(entry)

        overall_conv = round(step_counts[step_list[-1]] / step_counts[step_list[0]], 4) if step_counts[step_list[0]] > 0 else 0

        if dv is not None:
            dim_funnels[str(dv)] = {
                "overall_conversion": overall_conv,
                "steps": funnel_steps_list,
            }
        else:
            dim_funnels["all"] = {
                "overall_conversion": overall_conv,
                "steps": funnel_steps_list,
            }

    # 构建总漏斗（无维度时）
    final_steps = dim_funnels.get("all", {}).get("steps", [])
    if not final_steps and dim_funnels:
        final_steps = list(dim_funnels.values())[0]["steps"]

    # 找最大流失点
    biggest_drop = None
    for i in range(1, len(final_steps)):
        if final_steps[i].get("step_conversion") is not None:
            drop_rate = 1 - final_steps[i]["step_conversion"]
            if biggest_drop is None or drop_rate > biggest_drop["drop_rate"]:
                biggest_drop = {
                    "from": final_steps[i - 1]["step"],
                    "to": final_steps[i]["step"],
                    "drop_rate": round(drop_rate, 4),
                }

    data = {
        "mode": "steps",
        "steps": final_steps,
        "overall_conversion": final_steps[-1]["count"] / final_steps[0]["count"] if final_steps and final_steps[0]["count"] > 0 else 0,
        "biggest_drop": biggest_drop,
        "dimension_funnels": dim_funnels if dimension else None,
    }

    summary_lines = [f"漏斗分析（事件明细）: {' → '.join(step_list)}"]
    for s in final_steps:
        conv = f" (转化: {s['step_conversion']:.1%})" if "step_conversion" in s else ""
        summary_lines.append(f"  {s['step']}: {s['count']}{conv}")
    if biggest_drop:
        summary_lines.append(f"最大流失: {biggest_drop['from']} → {biggest_drop['to']} (流失率 {biggest_drop['drop_rate']:.1%})")

    return ToolResult(
        summary="\n".join(summary_lines),
        data=data,
        suggested_next="contribute_decomposition 分析各维度转化差异",
    )


def _funnel_aggregate(
    df: pd.DataFrame, name: str, step_col: str, count_col: str,
    steps: str, dimension: str,
) -> str:
    """场景B：预聚合步骤数据的漏斗分析。"""
    if step_col not in df.columns or count_col not in df.columns:
        return f"Error: 列不存在。可用: {list(df.columns)}"

    step_order = [s.strip() for s in steps.split(",") if s.strip()] if steps else None

    dim_values = [None]
    if dimension:
        if dimension not in df.columns:
            return f"Error: 维度列 '{dimension}' 不存在"
        dim_values = list(df[dimension].dropna().unique())

    dim_funnels = {}

    for dv in dim_values:
        sub_df = df if dv is None else df[df[dimension] == dv]

        if step_order:
            ordered_steps = step_order
        else:
            ordered_steps = list(sub_df.sort_values(count_col, ascending=False)[step_col].values)

        funnel_steps_list = []
        prev_count = None
        for i, step_name in enumerate(ordered_steps):
            row = sub_df[sub_df[step_col] == step_name]
            count = int(row[count_col].sum()) if not row.empty else 0
            entry = {"step": str(step_name), "count": count}
            if i > 0 and prev_count and prev_count > 0:
                entry["step_conversion"] = round(count / prev_count, 4)
            funnel_steps_list.append(entry)
            prev_count = count

        overall_conv = round(funnel_steps_list[-1]["count"] / funnel_steps_list[0]["count"], 4) if funnel_steps_list and funnel_steps_list[0]["count"] > 0 else 0
        dim_funnels[str(dv) if dv is not None else "all"] = {
            "overall_conversion": overall_conv,
            "steps": funnel_steps_list,
        }

    final_steps = dim_funnels.get("all", {}).get("steps", [])
    if not final_steps and dim_funnels:
        final_steps = list(dim_funnels.values())[0]["steps"]

    biggest_drop = None
    for i in range(1, len(final_steps)):
        if final_steps[i].get("step_conversion") is not None:
            drop_rate = 1 - final_steps[i]["step_conversion"]
            if biggest_drop is None or drop_rate > biggest_drop["drop_rate"]:
                biggest_drop = {
                    "from": final_steps[i - 1]["step"],
                    "to": final_steps[i]["step"],
                    "drop_rate": round(drop_rate, 4),
                }

    data = {
        "mode": "aggregate",
        "steps": final_steps,
        "overall_conversion": final_steps[-1]["count"] / final_steps[0]["count"] if final_steps and final_steps[0]["count"] > 0 else 0,
        "biggest_drop": biggest_drop,
        "dimension_funnels": dim_funnels if dimension else None,
    }

    summary_lines = [f"漏斗分析（预聚合数据）:"]
    for s in final_steps:
        conv = f" (转化: {s['step_conversion']:.1%})" if "step_conversion" in s else ""
        summary_lines.append(f"  {s['step']}: {s['count']}{conv}")
    if biggest_drop:
        summary_lines.append(f"最大流失: {biggest_drop['from']} → {biggest_drop['to']} (流失率 {biggest_drop['drop_rate']:.1%})")

    return ToolResult(
        summary="\n".join(summary_lines),
        data=data,
        suggested_next="create_chart(funnel) 可视化漏斗",
    )


def _funnel_rates(
    df: pd.DataFrame, name: str, rate_cols: str, dimension: str,
) -> str:
    """场景C：宽表多列率数据的漏斗分析。"""
    cols = [c.strip() for c in rate_cols.split(",") if c.strip()]
    missing = [c for c in cols if c not in df.columns]
    if missing:
        return f"Error: 列不存在: {missing}。可用: {list(df.columns)}"

    for c in cols:
        if not pd.api.types.is_numeric_dtype(df[c]):
            return f"Error: 列 '{c}' 不是数值类型"

    dim_values = [None]
    if dimension:
        if dimension not in df.columns:
            return f"Error: 维度列 '{dimension}' 不存在"
        dim_values = list(df[dimension].dropna().unique())

    dim_funnels = {}

    for dv in dim_values:
        sub_df = df if dv is None else df[df[dimension] == dv]

        # 使用均值作为代表性转化率
        cumulative_rates = []
        for c in cols:
            rate_val = float(sub_df[c].mean())
            cumulative_rates.append(min(rate_val, 1.0))  # cap at 100%

        funnel_steps_list = []
        for i, (col, cum_rate) in enumerate(zip(cols, cumulative_rates)):
            entry = {"step": col, "cumulative_rate": round(cum_rate, 4)}
            if i == 0:
                entry["count"] = 10000  # 假设基准量
            else:
                entry["count"] = int(round(cum_rate * 10000))

            if i > 0 and cumulative_rates[i - 1] > 0:
                step_conv = cum_rate / cumulative_rates[i - 1]
                entry["step_conversion"] = round(step_conv, 4)
            elif i == 0:
                entry["step_conversion"] = 1.0

            funnel_steps_list.append(entry)

        overall_conv = round(cumulative_rates[-1], 4) if cumulative_rates else 0
        dim_funnels[str(dv) if dv is not None else "all"] = {
            "overall_conversion": overall_conv,
            "steps": funnel_steps_list,
        }

    final_steps = dim_funnels.get("all", {}).get("steps", [])
    if not final_steps and dim_funnels:
        final_steps = list(dim_funnels.values())[0]["steps"]

    biggest_drop = None
    for i in range(1, len(final_steps)):
        if final_steps[i].get("step_conversion") is not None:
            drop_rate = 1 - final_steps[i]["step_conversion"]
            if biggest_drop is None or drop_rate > biggest_drop["drop_rate"]:
                biggest_drop = {
                    "from": final_steps[i - 1]["step"],
                    "to": final_steps[i]["step"],
                    "drop_rate": round(drop_rate, 4),
                }

    data = {
        "mode": "rates",
        "steps": final_steps,
        "overall_conversion": final_steps[-1]["cumulative_rate"] if final_steps else 0,
        "biggest_drop": biggest_drop,
        "dimension_funnels": dim_funnels if dimension else None,
        "note": "rate_cols 为累积转化率，step_conversion 为步骤间转化率",
    }

    summary_lines = [f"漏斗分析（率列模式）:"]
    for s in final_steps:
        conv = f" (步骤转化: {s['step_conversion']:.1%})" if "step_conversion" in s and s["step_conversion"] < 1 else ""
        cum = f" 累积: {s['cumulative_rate']:.1%}" if "cumulative_rate" in s else ""
        summary_lines.append(f"  {s['step']}: {cum}{conv}")
    if biggest_drop:
        summary_lines.append(f"最大流失: {biggest_drop['from']} → {biggest_drop['to']} (流失率 {biggest_drop['drop_rate']:.1%})")

    return ToolResult(
        summary="\n".join(summary_lines),
        data=data,
        suggested_next="ab_test 检验维度间转化率差异显著性",
    )
