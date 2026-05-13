"""数据加载后主动洞察扫描：生成业务级观察和建议关注点。"""

from __future__ import annotations

import json
from datetime import datetime

import numpy as np
import pandas as pd


def auto_insight_scan(df: pd.DataFrame, name: str) -> dict:
    """数据加载后自动洞察扫描。

    Returns:
        dict with keys: scan_mode, data_identity, field_semantics,
                        data_health, business_observations
    """
    rows = len(df)

    # 自适应采样
    if rows > 1_000_000:
        sample_df = df.sample(frac=0.01, random_state=42)
        scan_mode = "sampled_1pct"
    elif rows > 100_000:
        sample_df = df.sample(frac=0.1, random_state=42)
        scan_mode = "sampled_10pct"
    else:
        sample_df = df
        scan_mode = "full"

    return {
        "scan_mode": scan_mode,
        "data_identity": _identify_data(sample_df, name),
        "field_semantics": _classify_field_semantics(sample_df),
        "data_health": _assess_health(sample_df),
        "business_observations": _generate_observations(sample_df, scan_mode),
    }


def format_auto_insight(insight: dict) -> str:
    """将洞察结果格式化为 LLM 可读的文本。"""
    parts = []

    identity = insight.get("data_identity", {})
    health = insight.get("data_health", {})
    observations = insight.get("business_observations", [])

    # 数据身份行
    shape = identity.get("shape", "")
    parts.append(f"数据快速洞察 ({shape})")

    # 粒度（始终显示）
    grain_label = identity.get("grain_label", "")
    if grain_label:
        industry = identity.get("industry", "")
        if industry:
            parts.append(f"数据身份：{industry}行业，{grain_label}")
        else:
            parts.append(f"数据粒度：{grain_label}")
    if identity.get("time_range"):
        parts.append(f"时间范围：{identity['time_range']}")
    if identity.get("key_metrics"):
        parts.append(f"关键指标：{identity['key_metrics']}")
    if identity.get("dimensions"):
        parts.append(f"维度：{identity['dimensions']}")

    # 健康度
    health_items = health.get("items", [])
    if health_items:
        parts.append("数据健康：")
        for item in health_items:
            parts.append(f"  {item}")

    # 业务观察
    if observations:
        parts.append("值得关注：")
        for i, obs in enumerate(observations, 1):
            parts.append(f"  {i}. {obs}")

    return "\n".join(parts)


# ── 内部函数 ──────────────────────────────────────────────

def _identify_data(df: pd.DataFrame, name: str) -> dict:
    """数据身份识别：行业、粒度、时间范围、新鲜度。"""
    rows, cols = df.shape
    result = {"shape": f"{rows:,} 行 × {cols} 列"}

    # 复用 data_understand 的列分类
    try:
        from data_agent.tools.data_understand import (
            _classify_columns, _match_theme, _detect_grain, _detect_time_range,
        )

        classified = _classify_columns(df)
        theme, _ = _match_theme(classified)
        grain_map = {
            "individual": "个体明细",
            "daily_aggregate": "日级聚合",
            "weekly_aggregate": "周级聚合",
            "monthly_aggregate": "月级聚合",
            "multi_dimension_aggregate": "多维聚合",
            "aggregate": "聚合",
        }

        # 行业
        if theme != "unknown":
            result["industry"] = theme

        # 粒度
        columns_info = []
        for col in df.columns:
            nunique = int(df[col].nunique())
            missing_pct = round(df[col].isnull().sum() / max(len(df), 1) * 100, 2)
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                likely_type = "date"
            elif pd.api.types.is_numeric_dtype(df[col]):
                likely_type = "number"
            elif nunique / max(len(df), 1) < 0.05:
                likely_type = "category"
            else:
                likely_type = "text"
            columns_info.append({
                "name": col, "likely_type": likely_type,
                "missing_pct": missing_pct, "unique_values": nunique,
            })
        grain_info = _detect_grain(df, columns_info)
        result["grain_label"] = grain_map.get(grain_info["grain"], grain_info["grain"])

        # 时间范围
        time_range = _detect_time_range(df, classified.get("time_columns", []))
        if time_range:
            result["time_range"] = f"{time_range['min']} ~ {time_range['max']}（{time_range['span_days']}天）"

            # 数据新鲜度
            max_date_str = time_range["max"]
            try:
                max_date = pd.Timestamp(max_date_str)
                days_old = (pd.Timestamp.now() - max_date).days
                if days_old <= 1:
                    result["freshness"] = "实时"
                elif days_old <= 7:
                    result["freshness"] = f"最新数据 {days_old} 天前"
                elif days_old <= 30:
                    result["freshness"] = f"最新数据 {days_old} 天前"
                else:
                    result["freshness"] = f"数据已过期（最新 {days_old} 天前）"
            except Exception:
                pass

        # 关键指标和维度
        if classified.get("key_metrics"):
            result["key_metrics"] = ", ".join(m["column"] for m in classified["key_metrics"][:5])
        if classified.get("dimensions"):
            result["dimensions"] = ", ".join(d["column"] for d in classified["dimensions"][:5])

    except Exception:
        pass

    return result


def _classify_field_semantics(df: pd.DataFrame) -> dict:
    """字段语义分类：ID / 时间 / 维度 / 指标 / 标签。

    Delegates to data_understand._classify_columns for consistent classification
    across the system, then converts to the simplified {key: [names]} format.
    """
    from data_agent.tools.data_understand import _classify_columns

    classified = _classify_columns(df)

    # Extract simple column name lists from the detailed classification
    id_cols = [c["column"] for c in classified["id_columns"]]
    time_cols = classified["time_columns"]
    dim_cols = [c["column"] for c in classified["dimensions"]]
    metric_cols = [c["column"] for c in classified["key_metrics"]]
    rate_cols = [c["column"] for c in classified["rate_metrics"]]
    other = classified.get("other_numeric", []) + classified.get("other_text", [])

    return {
        "id": id_cols,
        "time": time_cols,
        "dimension": dim_cols,
        "metric": metric_cols + rate_cols,
        "other": other,
    }


def _assess_health(df: pd.DataFrame) -> dict:
    """数据健康度评估。"""
    rows = len(df)
    items = []

    # 关键列缺失率
    for col in df.columns:
        missing_pct = df[col].isnull().sum() / max(rows, 1) * 100
        if missing_pct >= 50:
            items.append(f"[BLOCK] 列 '{col}' 缺失 {missing_pct:.0f}%，该列数据不可用")
        elif missing_pct >= 20:
            items.append(f"[WARN] 列 '{col}' 缺失 {missing_pct:.1f}%，部分分析受限")
        elif missing_pct > 0:
            items.append(f"[INFO] 列 '{col}' 缺失 {missing_pct:.1f}%")

    # 数据量级评估
    if rows < 30:
        items.append("[WARN] 数据不足 30 行，统计结果置信度低")
    elif rows < 100:
        items.append("[INFO] 数据量较少，复杂分析（预测、建模）可能不可靠")

    # 常量列
    for col in df.columns:
        if df[col].nunique() <= 1:
            items.append(f"[INFO] 列 '{col}' 为常量列，无分析价值")

    # 重复率
    dup_pct = df.duplicated().sum() / max(rows, 1) * 100
    if dup_pct > 10:
        items.append(f"[WARN] 重复行占比 {dup_pct:.1f}%，可能影响统计准确性")

    # 数值异常值
    outlier_info = []
    for col in df.select_dtypes(include=[np.number]).columns:
        q1 = df[col].quantile(0.25)
        q3 = df[col].quantile(0.75)
        iqr = q3 - q1
        if iqr > 0:
            lower = q1 - 1.5 * iqr
            upper = q3 + 1.5 * iqr
            outlier_count = int(((df[col] < lower) | (df[col] > upper)).sum())
            if outlier_count > 0:
                outlier_pct = outlier_count / max(rows, 1) * 100
                if outlier_pct > 5:
                    outlier_info.append(f"'{col}' ({outlier_pct:.1f}%)")
    if outlier_info:
        items.append(f"[INFO] 异常值较多: {', '.join(outlier_info[:3])}")

    # 只保留最有价值的健康信息（最多 6 条）
    # 优先级: BLOCK > WARN > INFO
    def _priority(item: str) -> int:
        if "[BLOCK]" in item:
            return 0
        if "[WARN]" in item:
            return 1
        return 2

    items.sort(key=_priority)
    # 至少保留所有 BLOCK 和 WARN
    critical = [i for i in items if "[BLOCK]" in i or "[WARN]" in i]
    info_items = [i for i in items if "[INFO]" in i]
    kept = critical + info_items[:max(6 - len(critical), 0)]

    return {"items": kept, "score": _compute_health_score(df, rows)}


def _compute_health_score(df: pd.DataFrame, rows: int) -> int:
    """计算健康度分数 0-100。"""
    score = 100

    # 缺失惩罚
    for col in df.columns:
        missing_pct = df[col].isnull().sum() / max(rows, 1)
        if missing_pct >= 0.5:
            score -= 15
        elif missing_pct >= 0.2:
            score -= 5
        elif missing_pct > 0:
            score -= 1

    # 重复惩罚
    dup_pct = df.duplicated().sum() / max(rows, 1)
    if dup_pct > 0.1:
        score -= 10
    elif dup_pct > 0.05:
        score -= 5

    # 数据量不足惩罚
    if rows < 30:
        score -= 20
    elif rows < 100:
        score -= 5

    return max(score, 0)


def _generate_observations(df: pd.DataFrame, scan_mode: str) -> list[str]:
    """生成业务级观察。最多 3 条，每条格式：观察 + 数据支撑。"""
    observations: list[str] = []
    rows = len(df)

    # 需要足够的数据点才有观察价值
    if rows < 5:
        return observations

    numeric_cols = list(df.select_dtypes(include=[np.number]).columns)
    date_cols = [c for c in df.columns if pd.api.types.is_datetime64_any_dtype(df[c])]

    # 观察1：时间趋势（需要时间列 + 数值列）
    if date_cols and numeric_cols and len(df) >= 10:
        obs = _observe_time_trend(df, date_cols[0], numeric_cols[:3])
        if obs:
            observations.append(obs)

    # 观察2：维度贡献度（需要 category 列 + 数值列）
    if numeric_cols:
        cat_cols = _find_dimension_cols(df)
        if cat_cols:
            obs = _observe_dimension_contribution(df, cat_cols[0], numeric_cols[0])
            if obs:
                observations.append(obs)

    # 观察3：分布特征 / 指标间相关性
    if len(numeric_cols) >= 2 and len(observations) < 3:
        obs = _observe_correlation(df, numeric_cols[:5])
        if obs:
            observations.append(obs)
    elif len(numeric_cols) >= 1 and len(observations) < 3:
        obs = _observe_distribution(df, numeric_cols[0])
        if obs:
            observations.append(obs)

    return observations[:3]


def _find_dimension_cols(df: pd.DataFrame) -> list[str]:
    """找到适合做维度拆解的列。"""
    rows = len(df)
    result = []
    for col in df.columns:
        if pd.api.types.is_numeric_dtype(df[col]):
            continue
        nunique = df[col].nunique()
        if 2 <= nunique <= min(rows * 0.3, 50):
            result.append(col)
    return result


def _observe_time_trend(df: pd.DataFrame, date_col: str, value_cols: list[str]) -> str | None:
    """观察时间趋势方向。"""
    try:
        ts = df[[date_col] + value_cols].dropna().sort_values(date_col)
        if len(ts) < 10:
            return None

        col = value_cols[0]
        vals = ts[col].values.astype(float)

        # 简单分段对比：前 30% vs 后 30%
        n = len(vals)
        head_end = max(int(n * 0.3), 3)
        tail_start = max(int(n * 0.7), n - 3)
        head_mean = float(np.mean(vals[:head_end]))
        tail_mean = float(np.mean(vals[tail_start:]))

        if head_mean == 0:
            return None

        change_pct = (tail_mean - head_mean) / abs(head_mean) * 100
        direction = "上升" if change_pct > 0 else "下降"

        if abs(change_pct) < 5:
            return None

        col_label = col

        # 检查最近趋势（最后 20% vs 总体尾部）
        recent_start = max(int(n * 0.8), n - 5)
        recent_mean = float(np.mean(vals[recent_start:]))
        recent_change = (recent_mean - tail_mean) / abs(tail_mean) * 100 if tail_mean != 0 else 0

        obs = f"{col_label} 整体呈{direction}趋势（{change_pct:+.1f}%）"
        if abs(recent_change) > 5:
            recent_dir = "下滑" if recent_change < 0 else "回升"
            obs += f"，但最近出现{recent_dir}（{recent_change:+.1f}%）"
        obs += "，建议关注趋势持续性"

        return obs
    except Exception:
        return None


def _observe_dimension_contribution(df: pd.DataFrame, dim_col: str, metric_col: str) -> str | None:
    """观察维度贡献度。"""
    try:
        grouped = df.groupby(dim_col)[metric_col].sum()
        total = grouped.sum()
        if total == 0:
            return None

        top = grouped.nlargest(1)
        if len(top) == 0:
            return None

        top_name = str(top.index[0])
        top_pct = float(top.iloc[0]) / abs(total) * 100

        if top_pct < 40:
            return None

        nunique = df[dim_col].nunique()
        obs = f"{dim_col}='{top_name}' 贡献了 {top_pct:.0f}% 的 {metric_col}"
        if nunique <= 5:
            obs += f"（共 {nunique} 个维度值）"
        obs += "，集中度较高，建议关注依赖风险"

        return obs
    except Exception:
        return None


def _observe_correlation(df: pd.DataFrame, cols: list[str]) -> str | None:
    """观察指标间相关性。"""
    try:
        if len(cols) < 2:
            return None

        data = df[cols].dropna()
        if len(data) < 10:
            return None

        # 找最强相关对
        best_pair = None
        best_corr = 0
        for i in range(len(cols)):
            for j in range(i + 1, len(cols)):
                r = data[cols[i]].corr(data[cols[j]])
                if pd.notna(r) and abs(r) > abs(best_corr):
                    best_corr = r
                    best_pair = (cols[i], cols[j])

        if best_pair is None or abs(best_corr) < 0.6:
            return None

        strength = "高度" if abs(best_corr) > 0.8 else "较强"
        direction = "正" if best_corr > 0 else "负"
        obs = f"{best_pair[0]} 与 {best_pair[1]} 存在{strength}{direction}相关（r={best_corr:.2f}）"

        if best_corr > 0.8:
            obs += "，可能存在冗余指标或共同驱动因素"

        return obs
    except Exception:
        return None


def _observe_distribution(df: pd.DataFrame, col: str) -> str | None:
    """观察分布特征。"""
    try:
        vals = df[col].dropna().values.astype(float)
        if len(vals) < 10:
            return None

        mean = float(np.mean(vals))
        std = float(np.std(vals))
        if std == 0 or mean == 0:
            return None

        cv = std / abs(mean)  # 变异系数

        from scipy import stats as sp_stats
        skewness = float(sp_stats.skew(vals))

        if abs(skewness) > 1.5:
            direction = "右偏（集中在低值区）" if skewness > 0 else "左偏（集中在高值区）"
            return f"{col} 分布{direction}，偏度={skewness:.2f}，均值可能被极端值拉偏，建议使用中位数"

        if cv > 1.0:
            return f"{col} 离散度较高（变异系数={cv:.2f}），数据波动大，建议分段分析"

        return None
    except Exception:
        return None
