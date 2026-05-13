"""L1: 数据理解工具。"""

from __future__ import annotations

import json
from typing import Optional

import numpy as np
import pandas as pd

from data_agent.session.workspace import workspace
from data_agent.tools._utils import get_df, persist_detail, validate_pandas_expr
from data_agent.tools.registry import registry


@registry.register(
    name="describe_dataset",
    description="描述数据集的结构概览：字段名、类型、缺失率、基本统计。详细统计量自动持久化。",
)
def describe_dataset(name: str) -> str:
    df, err = get_df(name)
    if err:
        return err

    rows, cols = df.shape
    summary_fields = []
    detail_fields = []

    for col in df.columns:
        dtype = str(df[col].dtype)
        missing_count = int(df[col].isnull().sum())
        missing_pct = round(missing_count / rows * 100, 2) if rows > 0 else 0
        nunique = int(df[col].nunique())

        # 摘要：仅关键信息
        summary_fields.append({
            "name": col,
            "dtype": dtype,
            "missing_pct": missing_pct,
            "unique_values": nunique,
        })

        # 详情：完整统计量
        detail_info = {
            "name": col,
            "dtype": dtype,
            "missing_count": missing_count,
            "missing_pct": missing_pct,
            "unique_values": nunique,
        }

        if pd.api.types.is_datetime64_any_dtype(df[col]):
            col_min = df[col].min()
            col_max = df[col].max()
            detail_info["datetime_range"] = {
                "min": str(col_min) if pd.notna(col_min) else None,
                "max": str(col_max) if pd.notna(col_max) else None,
            }
            if pd.notna(col_min) and pd.notna(col_max):
                span = col_max - col_min
                detail_info["datetime_range"]["span_days"] = span.days
        elif pd.api.types.is_numeric_dtype(df[col]):
            desc = df[col].describe()
            detail_info["stats"] = {
                "mean": round(float(desc["mean"]), 4),
                "std": round(float(desc["std"]), 4),
                "min": _safe_val(desc["min"]),
                "25%": _safe_val(desc["25%"]),
                "50%": _safe_val(desc["50%"]),
                "75%": _safe_val(desc["75%"]),
                "max": _safe_val(desc["max"]),
            }
        else:
            top_vals = df[col].value_counts().head(5)
            detail_info["top_values"] = {str(k): int(v) for k, v in top_vals.items()}

        detail_fields.append(detail_info)

    # 精简摘要返回给 LLM
    summary = {
        "dataset": name,
        "shape": {"rows": rows, "columns": cols},
        "fields": summary_fields,
    }

    return json.dumps(summary, ensure_ascii=False, indent=2)


@registry.register(
    name="detect_data_quality",
    description="检测数据质量问题：缺失、异常值、重复行、常量列。",
)
def detect_data_quality(name: str) -> str:
    df, err = get_df(name)
    if err:
        return err

    rows = df.shape[0]
    issues = []

    # 缺失检测
    missing = df.isnull().sum()
    for col, count in missing.items():
        if count > 0:
            issues.append({
                "type": "missing_values",
                "column": col,
                "count": int(count),
                "percentage": round(count / rows * 100, 2),
            })

    # 常量列
    for col in df.columns:
        if df[col].nunique() <= 1:
            issues.append({
                "type": "constant_column",
                "column": col,
                "unique_values": int(df[col].nunique()),
            })

    # 重复行
    dup_count = int(df.duplicated().sum())
    if dup_count > 0:
        issues.append({
            "type": "duplicate_rows",
            "count": dup_count,
            "percentage": round(dup_count / rows * 100, 2),
        })

    # 数值列异常值（IQR方法）
    for col in df.select_dtypes(include=[np.number]).columns:
        q1 = df[col].quantile(0.25)
        q3 = df[col].quantile(0.75)
        iqr = q3 - q1
        if iqr > 0:
            lower = q1 - 1.5 * iqr
            upper = q3 + 1.5 * iqr
            outlier_count = int(((df[col] < lower) | (df[col] > upper)).sum())
            if outlier_count > 0:
                issues.append({
                    "type": "outliers",
                    "column": col,
                    "count": outlier_count,
                    "percentage": round(outlier_count / rows * 100, 2),
                    "bounds": {"lower": round(float(lower), 4), "upper": round(float(upper), 4)},
                })

    return json.dumps({
        "dataset": name,
        "total_issues": len(issues),
        "issues": issues,
    }, ensure_ascii=False, indent=2)


@registry.register(
    name="preview_data",
    description="预览数据集的前 N 行。",
)
def preview_data(name: str, n: int = 10) -> str:
    df, err = get_df(name)
    if err:
        return err

    n = min(int(n), 50)
    preview = df.head(n)
    return preview.to_string()


@registry.register(
    name="derive_field",
    description="从已有字段派生新列。expression 为 pandas 表达式，如 'revenue / users'。",
)
def derive_field(name: str, field_name: str, expression: str) -> str:
    df, err = get_df(name)
    if err:
        return err

    err = validate_pandas_expr(expression)
    if err:
        return f"Error: 表达式不安全 — {err}"

    try:
        new_col = df.eval(expression)
        new_df = df.copy()
        new_df[field_name] = new_col
        return workspace.derive(name, f"{name}_{field_name}", new_df, expression)
    except Exception as e:
        return f"Error deriving field: {e}"


def _safe_val(val):
    try:
        if pd.isna(val):
            return None
        return round(float(val), 4)
    except (TypeError, ValueError):
        return str(val)


# ── 数据粒度检测 ────────────────────────────────────────

_AGG_KEYWORDS = {
    "count", "cnt", "sum", "total", "avg", "mean", "rate", "ratio",
    "arpu", "arppu", "ltv", "gmv", "dau", "mau", "wap", "retention",
    "付费率", "转化率", "留存率", "人均", "次均", "总数", "合计",
    "汇总", "占比", "转化", "占比",
}


def _detect_grain(df: pd.DataFrame, columns_info: list[dict]) -> dict:
    """推断数据粒度，返回 {grain, grain_hint}。

    grain 枚举：
      individual              — 每行代表一个实体（用户/订单/事件）
      daily_aggregate         — 每行代表一天的数据汇总
      monthly_aggregate       — 每行代表一月的数据汇总
      multi_dimension_aggregate — 多维度聚合（如每天×渠道）
      unknown                 — 无法判断
    """
    rows = len(df)
    if rows == 0:
        return {"grain": "unknown", "grain_hint": "数据为空"}

    # 收集列特征
    date_cols = [c for c in columns_info if c["likely_type"] == "date"]
    date_col_names = [c["name"] for c in date_cols]

    # 1. 检测唯一标识列 → individual
    id_patterns = ["id", "uid", "user_id", "order_id", "device_id", "uuid", "openid"]
    for c in columns_info:
        col_lower = c["name"].lower().replace(" ", "")
        if any(p in col_lower for p in id_patterns) and c["unique_values"] >= rows * 0.8:
            return {
                "grain": "individual",
                "grain_hint": (
                    f"每行代表一个独立实体（检测到标识列 '{c['name']}'，唯一值 {c['unique_values']}/{rows}）。"
                    "可做个体级分析（用户画像、分群等）。"
                ),
            }

    # 2. 基于时间列判断聚合粒度
    if date_cols:
        for dc in date_cols:
            col_name = dc["name"]
            nunique_dates = dc["unique_values"]

            # 日期 unique 数 ≈ 行数 → 每行对应一个时间段（纯时间聚合）
            if rows > 0 and nunique_dates >= rows * 0.8:
                # 判断是日聚合还是月聚合
                if pd.api.types.is_datetime64_any_dtype(df[col_name]):
                    date_vals = df[col_name].dropna()
                    if len(date_vals) >= 2:
                        sorted_vals = date_vals.sort_values()
                        diffs = sorted_vals.diff().dropna()
                        if len(diffs) > 0:
                            median_diff = diffs.median()
                            if median_diff.days <= 2:
                                grain = "daily_aggregate"
                                grain_label = "天"
                            elif median_diff.days <= 8:
                                grain = "weekly_aggregate"
                                grain_label = "周"
                            elif median_diff.days <= 35:
                                grain = "monthly_aggregate"
                                grain_label = "月"
                            else:
                                grain = "period_aggregate"
                                grain_label = f"{median_diff.days}天"

                            # 检查是否有聚合指标关键词增强判断
                            has_agg_cols = _has_aggregate_keywords(columns_info)
                            hint = (
                                f"每行代表一{grain_label}的汇总数据"
                                f"（时间列 '{col_name}'，共 {nunique_dates} 个时间点，{rows} 行）。"
                                "不含用户个体信息，不可做用户画像、用户分群等个体级分析。"
                                "可做趋势分析、指标对比、周期性检测等聚合级分析。"
                            )
                            if has_agg_cols:
                                hint += "（检测到聚合指标列，确认此为聚合数据）"
                            return {"grain": grain, "grain_hint": hint}

            # 日期 unique 数 << 行数 → 每个日期有多行（可能是多维聚合或事件明细）
            elif rows > 0 and nunique_dates < rows * 0.5 and nunique_dates > 1:
                # 检查是否有维度列（category 列，非日期非数值）
                dim_cols = [
                    c for c in columns_info
                    if c["likely_type"] == "category" and c["name"] != col_name
                ]
                if dim_cols:
                    # 通过"实际行数 vs 预期行数（日期数 × 维度值数）"区分聚合与明细
                    # 聚合：每个 (日期 × 维度) 组合仅一行，rows ≈ dates × dims
                    # 明细：每个组合有多行，rows >> dates × dims
                    expected_rows = nunique_dates
                    for dc in dim_cols:
                        expected_rows *= dc["unique_values"]
                    fill_ratio = rows / expected_rows if expected_rows > 0 else 0

                    if 0.5 <= fill_ratio <= 2.0:
                        return {
                            "grain": "multi_dimension_aggregate",
                            "grain_hint": (
                                f"数据为多维聚合（时间列 '{col_name}' × 维度列 {[d['name'] for d in dim_cols[:3]]}）。"
                                f"每个时间点有 {rows // nunique_dates} 行。"
                                "可做维度对比分析，但不可做个体级分析。"
                            ),
                        }

    # 3. 无时间列，但有聚合指标关键词
    if _has_aggregate_keywords(columns_info):
        return {
            "grain": "aggregate",
            "grain_hint": (
                "检测到聚合指标列（如 ARPU、付费率等），数据为汇总粒度。"
                "不可做个体级分析（用户画像、分群等）。"
            ),
        }

    return {
        "grain": "unknown",
        "grain_hint": "无法确定数据粒度。分析前请确认每行代表什么（用户/订单/日汇总等）。",
    }


def _has_aggregate_keywords(columns_info: list[dict]) -> bool:
    """检查列名中是否包含聚合指标关键词。"""
    count = 0
    for c in columns_info:
        col_lower = c["name"].lower()
        for kw in _AGG_KEYWORDS:
            if kw in col_lower:
                count += 1
                break
    # 至少2个列匹配才认为是聚合数据（避免误判）
    return count >= 2


@registry.register(
    name="quick_profile",
    description=(
        "一次性获取数据全貌：结构、类型推断、质量评估、就绪度。"
        "使用场景：首次接触新数据集时快速了解数据特征。"
        "不适用场景：只需要某个特定信息（用 describe_dataset/detect_data_quality 更轻量）。"
        "参数说明：compact=True 返回精简版（适合 load_data 后自动调用）。"
        "替代分别调用 describe_dataset + detect_data_quality + assess_readiness。"
    ),
)
def quick_profile(name: str, compact: bool = False) -> str:
    from data_agent.session.workspace import workspace

    # Check cache: if profile was already computed for this dataset and data hasn't changed
    cached = workspace.get_metadata(name, "_profile_cache")
    cached_shape = workspace.get_metadata(name, "_profile_shape")
    df, err = get_df(name)
    if err:
        return err

    current_shape = f"{df.shape[0]}x{df.shape[1]}"
    if cached and cached_shape == current_shape and not compact:
        return cached

    rows, cols = df.shape
    columns_info = []
    quality_issues = []
    warnings = []
    suggested_next = []

    for col in df.columns:
        dtype = str(df[col].dtype)
        missing_pct = round(df[col].isnull().sum() / rows * 100, 2) if rows > 0 else 0
        nunique = int(df[col].nunique())

        # 类型推断
        likely_type = "unknown"
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            likely_type = "date"
        elif pd.api.types.is_numeric_dtype(df[col]):
            likely_type = "number"
        elif nunique / rows < 0.05 if rows > 0 else False:
            likely_type = "category"
        else:
            likely_type = "text"

        col_info = {
            "name": col,
            "dtype": dtype,
            "likely_type": likely_type,
            "missing_pct": missing_pct,
            "unique_values": nunique,
        }
        columns_info.append(col_info)

        # 质量问题检测
        if missing_pct >= 50:
            quality_issues.append(f"列 '{col}' 缺失率 {missing_pct:.0f}%")
        elif missing_pct > 0:
            warnings.append(f"列 '{col}' 缺失率 {missing_pct:.1f}%")

        # 日期列检查：是否为字符串格式的日期
        if likely_type == "text" and not pd.api.types.is_datetime64_any_dtype(df[col]):
            sample = df[col].dropna().head(5)
            try:
                pd.to_datetime(sample)
                warnings.append(f"列 '{col}' 可能是日期列（当前 dtype={dtype}），建议转换")
                suggested_next.append("apply_type_conversion 转换日期列")
            except (ValueError, TypeError):
                pass

        # 百分比字符串检查
        if likely_type == "text":
            sample_str = str(df[col].dropna().iloc[0]) if not df[col].dropna().empty else ""
            if "%" in sample_str:
                warnings.append(f"列 '{col}' 是百分号字符串，建议转换")
                suggested_next.append("apply_type_conversion 转换百分比列")

    # 重复行
    dup_count = int(df.duplicated().sum())
    if dup_count > 0:
        quality_issues.append(f"{dup_count} 行重复数据")

    # 异常值计数
    outlier_count = 0
    for col in df.select_dtypes(include=[np.number]).columns:
        q1 = df[col].quantile(0.25)
        q3 = df[col].quantile(0.75)
        iqr = q3 - q1
        if iqr > 0:
            outlier_count += int(((df[col] < q1 - 1.5 * iqr) | (df[col] > q3 + 1.5 * iqr)).sum())
    if outlier_count > 0:
        warnings.append(f"检测到 {outlier_count} 个数值异常值")

    # 就绪度
    readiness = "ready"
    if quality_issues:
        readiness = "blocked"
    elif warnings:
        readiness = "ready_with_warnings"

    # 时间列检测 → 建议 resample
    date_cols = [c["name"] for c in columns_info if c["likely_type"] == "date"]
    if date_cols:
        suggested_next.append(f"transform_data(resample) 时间重采样（时间列: {', '.join(date_cols[:3])}）")

    # 粒度检测
    grain_info = _detect_grain(df, columns_info)

    # 紧凑模式：缩减列信息，仅保留有问题的列的详情
    if compact:
        compact_columns = []
        for c in columns_info:
            if c["missing_pct"] > 0 or c["likely_type"] in ("text", "unknown"):
                # 有问题或特殊类型的列保留完整信息
                compact_columns.append({
                    "name": c["name"],
                    "type": c["likely_type"],
                    "missing%": c["missing_pct"],
                })
            else:
                # 正常列只保留名字和类型
                compact_columns.append(f"{c['name']}({c['likely_type']})")

        # 数值列统计摘要（紧凑格式）
        numeric_cols = [c for c in columns_info if c["likely_type"] == "number"]
        category_cols = [c for c in columns_info if c["likely_type"] == "category"]
        date_cols_names = [c["name"] for c in columns_info if c["likely_type"] == "date"]

        result = {
            "shape": [rows, cols],
            "columns": compact_columns,
            "summary": {
                "numeric": len(numeric_cols),
                "category": len(category_cols),
                "date": date_cols_names or None,
            },
            "quality": {
                "missing": len([q for q in quality_issues if "缺失" in q]),
                "outliers": outlier_count,
                "duplicates": dup_count,
            },
            "grain": grain_info["grain"],
            "grain_hint": grain_info["grain_hint"],
            "readiness": readiness,
            "warnings": quality_issues + warnings,
            "suggested_next": suggested_next[:5],
        }
        # 移除 None 值以节省 token
        result["summary"] = {k: v for k, v in result["summary"].items() if v is not None}
    else:
        # 非 compact 模式：追加 interpret_dataset 的推荐分析路径
        suggested_analyses = []
        try:
            classified = _classify_columns(df)
            suggested_analyses = _build_suggested_analyses(classified, grain_info)
        except Exception:
            pass

        result = {
            "shape": [rows, cols],
            "columns": columns_info,
            "quality": {
                "missing": len([q for q in quality_issues if "缺失" in q]),
                "outliers": outlier_count,
                "duplicates": dup_count,
            },
            "grain": grain_info["grain"],
            "grain_hint": grain_info["grain_hint"],
            "readiness": readiness,
            "warnings": quality_issues + warnings,
            "suggested_next": suggested_next[:5],
            "suggested_analyses": suggested_analyses[:5],
        }

    output = json.dumps(result, ensure_ascii=False, indent=2)

    # Cache the result for future calls (full mode only, not compact)
    if not compact:
        from data_agent.session.workspace import workspace
        workspace.set_metadata(name, "_profile_cache", output)
        workspace.set_metadata(name, "_profile_shape", f"{rows}x{cols}")

    return output


@registry.register(
    name="assess_readiness",
    description=(
        "评估数据是否已就绪可进行分析。检查项：时间粒度一致性、样本量充足性、"
        "关键列缺失率、常量列、多表关系、数据时效性。"
        "首次加载新数据集时应在 DAG 第一阶段调用。"
    ),
)
def assess_readiness(name: str, intent: str = "") -> str:
    """评估数据就绪度，返回结构化报告。"""
    df, err = get_df(name)
    if err:
        return err

    from datetime import datetime
    rows, cols = df.shape
    findings = []

    # 1. Time granularity consistency
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            sorted_vals = df[col].dropna().sort_values()
            if len(sorted_vals) >= 3:
                diffs = sorted_vals.diff().dropna()
                if len(diffs) > 0:
                    median_diff = diffs.median()
                    safe_denom = max(median_diff, pd.Timedelta(seconds=1))
                    non_uniform = diffs[abs((diffs - median_diff) / safe_denom) > 0.5]
                    if len(non_uniform) > len(diffs) * 0.1:
                        findings.append({
                            "severity": "warning",
                            "check": "time_granularity",
                            "message": f"时间列 '{col}' 间隔不一致：约{len(non_uniform)}/{len(diffs)}个间隔偏离中位数超过50%",
                        })

    # 2. Sample size sufficiency (intent-specific)
    ml_intents = {"forecast", "classification"}
    if intent in ml_intents:
        min_rows = 200 if intent == "classification" else 100
        if rows < min_rows:
            findings.append({
                "severity": "warning",
                "check": "sample_size",
                "message": f"当前{rows}行数据，{intent}建模建议≥{min_rows}行，结果置信度可能较低",
            })

    # 3. Key column missing rate
    for col in df.columns:
        missing_pct = df[col].isnull().sum() / rows * 100 if rows > 0 else 0
        if missing_pct >= 50:
            findings.append({
                "severity": "block",
                "check": "missing_data",
                "message": f"列 '{col}' 缺失率 {missing_pct:.0f}%，分析结果不可靠",
            })
        elif missing_pct > 30:
            findings.append({
                "severity": "warning",
                "check": "missing_data",
                "message": f"列 '{col}' 缺失率 {missing_pct:.0f}%，部分分析可能受影响",
            })

    # 4. Constant / near-constant columns
    for col in df.columns:
        if df[col].nunique() <= 1:
            findings.append({
                "severity": "info",
                "check": "constant_column",
                "message": f"列 '{col}' 仅含单一值或方差≈0，无法用于维度拆解",
            })

    # 5. Data freshness
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            max_date = df[col].max()
            if pd.notna(max_date):
                try:
                    days_old = (datetime.now() - max_date.to_pydatetime()).days
                    if days_old > 7:
                        findings.append({
                            "severity": "info",
                            "check": "data_freshness",
                            "message": f"数据最新日期 {str(max_date)[:10]}，距今{days_old}天",
                        })
                except (TypeError, ValueError):
                    pass

    # Compute overall readiness
    has_block = any(f["severity"] == "block" for f in findings)
    has_warning = any(f["severity"] == "warning" for f in findings)
    if has_block:
        overall = "blocked"
    elif has_warning:
        overall = "ready_with_warnings"
    else:
        overall = "ready"

    # Build summary
    icon_map = {"block": "BLOCK", "warning": "WARN", "info": "INFO"}
    summary_lines = [f"Data Readiness: {overall} ({rows} rows x {cols} cols)"]
    for f in findings:
        summary_lines.append(f"  [{icon_map.get(f['severity'], '?')}] {f['message']}")
    if not findings:
        summary_lines.append("  [OK] 所有检查通过，数据已就绪")

    return json.dumps({
        "summary": "\n".join(summary_lines),
        "overall": overall,
        "findings": findings,
        "rows": rows,
        "cols": cols,
    }, ensure_ascii=False, indent=2)


# ── 业务语义理解 ──────────────────────────────────────────

# 率类指标关键词
_RATE_KEYWORDS = (
    "率", "rate", "ratio", "pct", "percent", "占比", "转化", "留存", "付费率",
    "完成率", "成功率", "点击率", "渗透率", "覆盖率",
)

# 行业主题模板
_THEME_PATTERNS: dict[str, list[str]] = {
    "游戏": ["arpu", "arppu", "dau", "mau", "ltv", "留存", "付费", "游戏", "渠道", "充值", "wa", "wap"],
    "电商": ["gmv", "客单价", "复购", "uv", "pv", "转化率", "订单", "商品", "购物车", "退货"],
    "广告营销": ["ctr", "cvr", "cpm", "cpc", "cpa", "曝光", "点击", "投放", "roi", "roas", "素材"],
    "金融": ["余额", "贷款", "利率", "逾期", "坏账", "资产", "负债", "净值", "收益", "波动率"],
    "内容/社交": ["点赞", "评论", "分享", "收藏", "关注", "粉丝", "帖子", "播放", "互动"],
}

# 分析路径策略矩阵
_ANALYSIS_STRATEGY: list[dict] = [
    {
        "conditions": {"has_time": True, "has_dimensions": True},
        "analyses": [
            {"direction": "趋势分析", "tools": ["analyze_time_series"], "priority": 1},
            {"direction": "维度对比", "tools": ["compare_periods", "ab_test"], "priority": 2},
            {"direction": "变动归因", "tools": ["contribute_decomposition"], "priority": 3},
        ],
    },
    {
        "conditions": {"has_time": True, "has_dimensions": False},
        "analyses": [
            {"direction": "趋势分析", "tools": ["analyze_time_series"], "priority": 1},
            {"direction": "异常检测", "tools": ["distribution_analysis"], "priority": 2},
            {"direction": "趋势预测", "tools": ["forecast"], "priority": 3},
        ],
    },
    {
        "conditions": {"has_time": False, "has_dimensions": True},
        "analyses": [
            {"direction": "分组对比", "tools": ["ab_test", "transform_data(group_aggregate)"], "priority": 1},
            {"direction": "相关性分析", "tools": ["correlation_analysis"], "priority": 2},
        ],
    },
    {
        "conditions": {"has_time": False, "has_dimensions": False},
        "analyses": [
            {"direction": "分布分析", "tools": ["distribution_analysis"], "priority": 1},
            {"direction": "异常检测", "tools": ["detect_data_quality"], "priority": 2},
            {"direction": "相关性分析", "tools": ["correlation_analysis"], "priority": 3},
        ],
    },
]


def _classify_columns(df: pd.DataFrame) -> dict:
    """将 DataFrame 的列分类为 id/time/dimension/metric 等角色。"""
    rows = len(df)
    id_cols = []
    time_cols = []
    dim_cols = []
    key_metrics = []
    rate_metrics = []
    other_numeric = []
    other_text = []

    id_patterns = ["id", "uid", "user_id", "order_id", "device_id", "uuid", "openid"]

    for col in df.columns:
        nunique = df[col].nunique()
        missing_pct = df[col].isnull().sum() / rows * 100 if rows > 0 else 0
        col_lower = col.lower().replace(" ", "").replace("_", "")

        # ID 列
        if any(p in col_lower for p in id_patterns) and nunique >= rows * 0.8:
            id_cols.append({"column": col, "unique_count": nunique})
            continue

        # 时间列
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            time_cols.append(col)
            continue
        if df[col].dtype == object:
            try:
                pd.to_datetime(df[col].dropna().head(20))
                time_cols.append(col)
                continue
            except (ValueError, TypeError):
                pass

        # 率类指标
        col_orig_lower = col.lower()
        if any(kw in col_orig_lower for kw in _RATE_KEYWORDS):
            if pd.api.types.is_numeric_dtype(df[col]):
                rate_metrics.append({"column": col, "is_rate": True, "unique_count": nunique})
                continue

        # 类别维度
        if not pd.api.types.is_numeric_dtype(df[col]) and nunique < max(rows * 0.05, 2) and nunique >= 2:
            dim_cols.append({"column": col, "unique_count": nunique})
            continue

        # 数值列
        if pd.api.types.is_numeric_dtype(df[col]):
            if nunique > 2:
                key_metrics.append({"column": col, "is_rate": False, "unique_count": nunique})
            else:
                other_numeric.append(col)
            continue

        other_text.append(col)

    # 按 variance rank 排序 key_metrics
    if key_metrics:
        metric_variances = []
        for m in key_metrics:
            vals = df[m["column"]].dropna()
            var = float(vals.var()) if len(vals) > 1 else 0
            metric_variances.append((m, var))
        metric_variances.sort(key=lambda x: -x[1])
        key_metrics = [
            {**m, "variance_rank": i + 1}
            for i, (m, _) in enumerate(metric_variances)
        ]

    return {
        "id_columns": id_cols,
        "time_columns": time_cols,
        "dimensions": dim_cols,
        "key_metrics": key_metrics[:8],
        "rate_metrics": rate_metrics,
        "other_numeric": other_numeric,
        "other_text": other_text,
    }


def _detect_time_range(df: pd.DataFrame, time_cols: list[str]) -> dict | None:
    """检测时间列的数据范围。要求 time_cols 中的列已经是 datetime 类型。"""
    if not time_cols:
        return None
    col = time_cols[0]
    vals = df[col].dropna()
    if len(vals) == 0:
        return None
    mn, mx = vals.min(), vals.max()
    span = (mx - mn).days if hasattr(mx - mn, "days") else 0
    return {
        "column": col,
        "min": str(mn)[:10],
        "max": str(mx)[:10],
        "span_days": span,
    }


def _match_theme(columns_classified: dict) -> tuple[str, str]:
    """基于列名关键词匹配行业主题。返回 (theme, confidence)。"""
    all_cols_lower = set()
    for m in columns_classified.get("key_metrics", []):
        all_cols_lower.add(m["column"].lower())
    for m in columns_classified.get("rate_metrics", []):
        all_cols_lower.add(m["column"].lower())
    for d in columns_classified.get("dimensions", []):
        all_cols_lower.add(d["column"].lower())

    best_theme = "unknown"
    best_score = 0
    for theme, keywords in _THEME_PATTERNS.items():
        score = sum(1 for kw in keywords if any(kw in c for c in all_cols_lower))
        if score > best_score:
            best_score = score
            best_theme = theme

    confidence = "high" if best_score >= 3 else "medium" if best_score >= 2 else "low"
    return best_theme, confidence


def _build_suggested_analyses(
    columns_classified: dict,
    grain_info: dict,
) -> list[dict]:
    """根据数据特征构建推荐分析路径。"""
    has_time = bool(columns_classified.get("time_columns"))
    has_dims = bool(columns_classified.get("dimensions"))
    has_ids = bool(columns_classified.get("id_columns"))
    has_rates = bool(columns_classified.get("rate_metrics"))

    # 匹配策略矩阵
    matched = []
    for strategy in _ANALYSIS_STRATEGY:
        cond = strategy["conditions"]
        if cond.get("has_time") == has_time and cond.get("has_dimensions") == has_dims:
            matched = strategy["analyses"]
            break

    # 追加基于特殊特征的推荐
    extras = []
    if has_ids:
        extras.append({"direction": "漏斗/留存分析", "tools": ["funnel_analysis", "cohort_analysis"], "priority": 4})
    if has_rates:
        extras.append({"direction": "率指标变动追踪", "tools": ["compare_periods", "contribute_decomposition"], "priority": 4})

    # 率类指标追加提示
    result = list(matched)
    for e in extras:
        if not any(a["direction"] == e["direction"] for a in result):
            result.append(e)

    # 排序并添加 reason
    result.sort(key=lambda x: x["priority"])
    for r in result:
        r.setdefault("reason", "")

    # 为每个推荐生成 reason
    reasons = {
        "趋势分析": "检测指标的时间走向和周期性",
        "维度对比": "比较不同分组间的差异",
        "变动归因": "拆解指标变化的驱动因素",
        "异常检测": "识别偏离正常范围的数据点",
        "趋势预测": "基于历史数据预测未来趋势",
        "分组对比": "比较不同群体间的关键差异",
        "相关性分析": "发现指标间的关联关系",
        "分布分析": "了解数据的分布特征和集中趋势",
        "漏斗/留存分析": "追踪用户转化路径或留存情况",
        "率指标变动追踪": "率类指标的小幅变动也值得关注",
    }
    for r in result:
        r["reason"] = reasons.get(r["direction"], "")

    return result[:6]


@registry.register(
    name="interpret_dataset",
    description=(
        "推断数据集的业务语义：列角色分类、分析信号检测、推荐分析路径。"
        "输出结构化数据供分析引擎使用，不含 LLM 推断（由 prompt 层完成）。"
    ),
)
def interpret_dataset(name: str) -> str:
    from data_agent.tools.registry import ToolResult, ArtifactRef

    df, err = get_df(name)
    if err:
        return err

    rows, cols = df.shape

    # 0. 确保字符串日期列被转为 datetime（与 load_data 中 auto_clean 行为一致）
    for col in df.columns:
        if df[col].dtype == object and col not in (df.select_dtypes(include=[np.number]).columns):
            sample = df[col].dropna().head(20)
            if len(sample) > 0:
                try:
                    pd.to_datetime(sample)
                    df = df.copy()
                    df[col] = pd.to_datetime(df[col], errors="coerce")
                except (ValueError, TypeError):
                    pass

    # 1. 列分类
    classified = _classify_columns(df)

    # 2. 时间范围
    time_range = _detect_time_range(df, classified["time_columns"])

    # 3. 粒度检测（复用已有逻辑）
    columns_info = []
    for col in df.columns:
        dtype = str(df[col].dtype)
        missing_pct = round(df[col].isnull().sum() / rows * 100, 2) if rows > 0 else 0
        nunique = int(df[col].nunique())
        likely_type = "unknown"
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            likely_type = "date"
        elif pd.api.types.is_numeric_dtype(df[col]):
            likely_type = "number"
        elif nunique / rows < 0.05 if rows > 0 else False:
            likely_type = "category"
        else:
            likely_type = "text"
        columns_info.append({
            "name": col, "dtype": dtype, "likely_type": likely_type,
            "missing_pct": missing_pct, "unique_values": nunique,
        })
    grain_info = _detect_grain(df, columns_info)

    # 4. 分析信号
    signals = {
        "has_time": bool(classified["time_columns"]),
        "has_dimensions": len(classified["dimensions"]) > 0,
        "has_rates": len(classified["rate_metrics"]) > 0,
        "has_ids": len(classified["id_columns"]) > 0,
        "metric_count": len(classified["key_metrics"]) + len(classified["rate_metrics"]),
        "dimension_count": len(classified["dimensions"]),
    }

    # 5. 推荐分析路径
    suggested = _build_suggested_analyses(classified, grain_info)

    # 6. 主题匹配
    theme, theme_confidence = _match_theme(classified)

    # 7. 多数据集关联分析推荐 (using shared detection function)
    cross_dataset_hints = []
    try:
        existing = {k: v for k, v in workspace.list_datasets().items() if k != name}
        if existing:
            from data_agent.utils.data_features import detect_cross_dataset_relationships
            other_dfs = {}
            for other_name in existing:
                other_df = workspace.get(other_name)
                if other_df is not None:
                    other_dfs[other_name] = other_df
            if other_dfs:
                relationships = detect_cross_dataset_relationships({name: df, **other_dfs})
                for rel in relationships[:5]:
                    if rel["left"] == name:
                        other_name = rel["right"]
                    else:
                        other_name = rel["left"]
                    cross_dataset_hints.append({
                        "other_dataset": other_name,
                        "shared_columns": [rel["column"]],
                        "rows_other": len(other_dfs.get(other_name, [])),
                        "overlap_pct": rel["overlap_pct"],
                    })
    except Exception:
        pass

    if cross_dataset_hints:
        for hint in cross_dataset_hints:
            suggested.append({
                "direction": f"关联分析: {name} × {hint['other_dataset']}",
                "tools": ["transform_data(merge)", "correlation_analysis", "compare_periods"],
                "priority": max(s["priority"] for s in suggested) + 1 if suggested else 4,
                "reason": f"共享列 {hint['shared_columns'][:3]}，可通过 merge 合并后做跨数据集分析",
            })

    # 构建结果
    data = {
        "theme": theme,
        "theme_confidence": theme_confidence,
        "grain": grain_info["grain"],
        "grain_hint": grain_info["grain_hint"],
        "columns_classified": classified,
        "data_shape": {"rows": rows, "columns": cols},
        "time_range": time_range,
        "analysis_signals": signals,
        "suggested_analyses": suggested,
    }
    if cross_dataset_hints:
        data["cross_dataset_hints"] = cross_dataset_hints

    # CLI summary
    summary_parts = [f"数据集 '{name}' ({rows}×{cols})"]
    if theme != "unknown":
        summary_parts.append(f"行业主题: {theme} (置信度: {theme_confidence})")
    summary_parts.append(f"粒度: {grain_info['grain']}")
    if classified["key_metrics"]:
        metric_names = [m["column"] for m in classified["key_metrics"][:5]]
        summary_parts.append(f"关键指标: {', '.join(metric_names)}")
    if classified["dimensions"]:
        dim_names = [d["column"] for d in classified["dimensions"][:5]]
        summary_parts.append(f"维度: {', '.join(dim_names)}")
    if time_range:
        summary_parts.append(f"时间范围: {time_range['min']} ~ {time_range['max']} ({time_range['span_days']}天)")
    if suggested:
        summary_parts.append("推荐分析:")
        for s in suggested[:4]:
            summary_parts.append(f"  {s['priority']}. {s['direction']} — {s['reason']}")

    summary = "\n".join(summary_parts)

    return ToolResult(
        summary=summary,
        data=data,
        suggested_next=suggested[0]["tools"][0] if suggested else None,
    )
