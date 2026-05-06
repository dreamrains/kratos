"""L1: 数据理解工具。"""

from __future__ import annotations

import json
from typing import Optional

import numpy as np
import pandas as pd

from data_agent.session.workspace import workspace
from data_agent.tools._utils import get_df, persist_detail
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
