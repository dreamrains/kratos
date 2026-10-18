"""L1: 数据理解工具。"""

from __future__ import annotations

import json
import warnings as py_warnings
from typing import Optional

import numpy as np
import pandas as pd

from data_agent.session.workspace import workspace
from data_agent.tools._utils import get_df, persist_detail, validate_pandas_expr
from data_agent.tools.registry import ToolResult, registry
from data_agent.agent.publication.native import MINIMAL_PRODUCT_CONTRACTS


def _observed_date_scope(df: pd.DataFrame) -> dict:
    """Report typed date-column coverage, never an inferred data collection cutoff."""
    columns = {}
    for column in df.columns:
        values = df[column]
        if pd.api.types.is_datetime64_any_dtype(values) and values.notna().any():
            columns[str(column)] = {"min": str(values.min()), "max": str(values.max()),
                                    "non_null_rows": int(values.notna().sum()),
                                    "distinct_values": int(values.nunique())}
    return {"kind": "observed_date_columns", "columns": columns,
            "collection_cutoff": "unknown"} if columns else {}


@registry.register(
    name="describe_dataset",
    output_contract=MINIMAL_PRODUCT_CONTRACTS["describe_dataset"],
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
            number=lambda value: None if pd.isna(value) else value.item() if hasattr(value,"item") else value
            observed=df[col].dropna()
            total=(sum(int(value) for value in observed) if pd.api.types.is_integer_dtype(df[col]) else df[col].sum(min_count=1)) if len(observed) else None
            total=number(total)
            detail_info["stats"] = {
                "sum": total,
                "mean": number(desc["mean"]),
                "std": number(desc["std"]),
                "min": number(df[col].min()),
                "25%": number(desc["25%"]),
                "50%": number(desc["50%"]),
                "75%": number(desc["75%"]),
                "max": number(df[col].max()),
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
        "field_statistics": detail_fields,
        "observation_window": _observed_date_scope(df),
    }

    return json.dumps(summary, ensure_ascii=False, indent=2)


def _quality_result(df: pd.DataFrame, name: str) -> dict:
    """One diagnostic implementation for execution and source-owner verification."""
    rows = len(df)
    issues, diagnostics = [], []
    for position, column in enumerate(df.columns):
        values = df.iloc[:, position]
        missing = int(values.isna().sum())
        observed = values.dropna()
        unique = int(observed.nunique())
        constant = "unknown" if not len(observed) else "constant" if unique == 1 else "not_constant"
        if missing:
            issues.append({"type": "missing_values", "column": column, "count": missing,
                           "percentage": round(missing / rows * 100, 2)})
        if constant == "constant":
            issues.append({"type": "constant_column", "column": column, "unique_values": unique})
        numeric = pd.api.types.is_numeric_dtype(values) and not pd.api.types.is_bool_dtype(values)
        finite = observed[np.isfinite(observed)] if numeric else observed.iloc[:0]
        non_finite = len(observed) - len(finite) if numeric else 0
        if non_finite:
            issues.append({"type": "non_finite_values", "column": column, "count": non_finite,
                           "percentage": round(non_finite / rows * 100, 2)})
        iqr = {"status": "not_assessed", "method": "1.5*IQR", "quantile_interpolation": "linear",
               "effective_n": len(finite), "excluded_missing": missing, "excluded_non_finite": non_finite,
               "outlier_count": None, "bounds": None, "q1": None, "q3": None, "iqr": None,
               "reason": "非数值列，未作IQR异常判定" if not numeric else "无有限观测，未作异常判定"}
        if numeric and len(finite):
            if pd.api.types.is_complex_dtype(values):
                iqr["reason"] = "复数无有序实数范围，未作IQR异常判定"
            else:
                q1, q3 = (float(finite.quantile(q, interpolation="linear")) for q in (.25, .75))
                spread = q3 - q1
                lower, upper = q1 - 1.5 * spread, q3 + 1.5 * spread
                if not all(np.isfinite(v) for v in (q1, q3, spread, lower, upper)):
                    iqr["reason"] = "IQR范围无法有限表示，未作异常判定"
                else:
                    iqr.update(q1=q1, q3=q3, iqr=spread)
                    if spread == 0:
                        iqr["reason"] = "IQR为0，未作异常判定"
                    else:
                        count = int(((finite < lower) | (finite > upper)).sum())
                        bounds = {"lower": lower, "upper": upper}
                        iqr.update(status="computed", outlier_count=count, bounds=bounds, reason=None)
                        if count:
                            issues.append({"type": "outliers", "column": column, "count": count,
                                           "percentage": round(count / rows * 100, 2), "bounds": bounds})
        diagnostics.append({"column": column, "position": position + 1, "dtype": str(values.dtype),
            "source_rows": rows, "missing_count": missing, "non_missing_count": len(observed),
            "unique_values": unique, "constant_status": constant, "non_finite_count": non_finite, "iqr": iqr})
    duplicates = int(df.duplicated().sum())
    if duplicates:
        issues.append({"type": "duplicate_rows", "count": duplicates,
                       "percentage": round(duplicates / rows * 100, 2)})
    return {"dataset": name, "rows": rows, "observation_window": _observed_date_scope(df),
        "total_issues": len(issues), "issues": issues, "column_diagnostics": diagnostics,
        "observation": {"source_rows": rows, "source_columns": len(df.columns),
            "duplicate_rows_count": duplicates, "percentage_denominator": "source_rows",
            "iqr_scope": "每列有限观测；缺失与非有限值单独披露"},
        "limitations": ["这些基础诊断不表示数据已就绪；具体方法仍须核验其实际使用列及前提。",
            "1.5×IQR仅为诊断规则，不证明记录必然错误；IQR为0或无有限范围时未作异常判定。",
            "缺失和非有限值的业务含义未知；各问题可以重叠，问题总数是问题项数而非错误记录数。"]}


@registry.register(
    name="detect_data_quality",
    description="基础质量诊断：缺失、重复行、有观测的常量列、非有限数及有限观测的1.5×IQR。公开逐列有效/排除数和未舍入边界；无范围或IQR为0时不作异常判定。诊断不表示数据已就绪或记录必然错误。",
    output_contract=MINIMAL_PRODUCT_CONTRACTS["detect_data_quality"],
)
def detect_data_quality(name: str) -> str:
    df, err = get_df(name)
    if err:
        return json.dumps({"error": err}, ensure_ascii=False)
    return json.dumps(_quality_result(df, name), ensure_ascii=False, indent=2)


def _preview_result(df: pd.DataFrame, name: str, n: int = 10) -> dict:
    """Keep the source order and original preview serialization in one implementation."""
    if type(n) is not int or not 1 <= n <= 50:
        raise ValueError("预览行数 n 必须是 1—50 的整数。")
    preview = df.head(n)
    rows = preview.astype(object).where(pd.notna(preview), None).to_dict("records")
    rows = json.loads(json.dumps(rows, ensure_ascii=False, default=str))
    return {"dataset": name, "data": rows, "rows": len(rows), "columns": list(preview.columns),
        "shape": {"rows": len(df), "columns": len(df.columns)},
        "observation": {"requested_rows": n, "returned_rows": len(rows), "source_rows": len(df),
            "preview_limit": 50, "row_order": "current_dataset_order", "scope": "first_rows"}}


@registry.register(
    name="preview_data",
    description="按数据集当前顺序预览前 N 行，n 仅支持 1—50 的整数（默认10）。公开请求行数、实际返回行数和源表总行数；预览不表示全表交付或随机抽样。",
    schema_overrides={"n": {"minimum": 1, "maximum": 50}},
    output_contract=MINIMAL_PRODUCT_CONTRACTS["preview_data"],
)
def preview_data(name: str, n: int = 10) -> ToolResult | str:
    if type(n) is not int or not 1 <= n <= 50:
        return ToolResult(summary="预览行数 n 必须是 1—50 的整数。", data={"error": "unsupported_preview_rows"})
    df, err = get_df(name)
    if err:
        return ToolResult(summary=err, data={"error": err})
    result = _preview_result(df, name, n)
    return ToolResult(summary=f"前行预览：请求 {n} 行，实际返回 {result['rows']} 行，源表共 {len(df)} 行。仅当前顺序预览，不表示全表交付。\n" + df.head(n).to_string(), data=result)


@registry.register(
    name="derive_field",
    capability={"capability_id":"data.derive_field","category":"data_transform"},
    output_contract=MINIMAL_PRODUCT_CONTRACTS["derive_field"],
    description="从已有字段派生新列。expression 仅支持列引用、算术、比较、布尔运算，如 'revenue / users'；不支持函数调用、np.select/np.where 或 import。复杂条件请用受限 run_python 分析或已有 transform_data 操作。",
)
def derive_field(name: str, field_name: str, expression: str) -> str | ToolResult:
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
        target = f"{name}_{field_name}"
        summary = workspace.derive(name, target, new_df, expression)
        if summary.startswith("Error:"):
            return summary
        import ast
        program=ast.parse(expression,mode="eval").body
        algebra=dict(workspace.get_metadata(name,"_column_algebra") or {})
        algebra.pop(field_name,None)
        if any(isinstance(n,ast.Div) for n in ast.walk(program)):
            algebra[field_name]={"operator":"non_additive"}
            if isinstance(program,ast.BinOp) and isinstance(program.op,ast.Div) and isinstance(program.left,ast.Name) and isinstance(program.right,ast.Name) and program.left.id in df.columns and program.right.id in df.columns:
                algebra[field_name].update(numerator=program.left.id,denominator=program.right.id)
        workspace.set_metadata(target,"_column_algebra",algebra)
        return ToolResult(summary=summary, data={"dataset": target, "source_dataset": name,
            "operation": "derive_field", "field_name": field_name, "expression": expression,
            "rows": len(new_df), "source_rows": len(df),
            "preserved_columns": [str(c) for c in df.columns if c != field_name]})
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
    """Existing grain rules produce candidates, never method eligibility."""
    rows = len(df)
    def candidate(grain, basis):
        return {"grain":grain, "grain_hint":f"粒度启发候选：{grain}；依据：{basis}。尚未核验每行的业务分析单位；具体方法须另核其实际前提。",
                "grain_basis":{"status":"candidate_only","confidence":"low" if grain=="unknown" else "heuristic", "rule":basis}}
    if rows == 0:
        return candidate("unknown", "原表无记录")
    date_cols = [c for c in columns_info if c["likely_type"] == "date"]
    id_patterns = ["id", "uid", "user_id", "order_id", "device_id", "uuid", "openid"]
    for c in columns_info:
        if any(p in c["name"].lower().replace(" ", "") for p in id_patterns) and c["unique_values"] >= rows * 0.8:
            return candidate("individual", f"标识名称列 {c['name']} 的唯一值 {c['unique_values']}/{rows} 达到80%阈值；不保证实体唯一性")
    for dc in date_cols:
        col_name, nunique_dates = dc["name"], dc["unique_values"]
        if nunique_dates >= rows * 0.8:
            vals, _ = _date_observation(df[col_name])
            diffs = vals.dropna().sort_values().diff().dropna() if vals is not None else pd.Series(dtype="timedelta64[ns]")
            if len(diffs):
                median_diff = diffs.median()
                grain = "daily_aggregate" if median_diff.days <= 2 else "weekly_aggregate" if median_diff.days <= 8 else "monthly_aggregate" if median_diff.days <= 35 else "period_aggregate"
                return candidate(grain, f"时间候选列 {col_name} 唯一值 {nunique_dates}/{rows} 达到80%；已解析时间的中位间隔为 {median_diff}，沿用间隔天数阈值2/8/35；间隔不证明已汇总")
        elif 1 < nunique_dates < rows * 0.5:
            dims = [c for c in columns_info if c["likely_type"]=="category" and c["name"]!=col_name]
            expected = nunique_dates
            for c in dims: expected *= c["unique_values"]
            if dims and expected > 0 and 0.5 <= rows / expected <= 2:
                return candidate("multi_dimension_aggregate", f"时间 {col_name} × 维度 {[c['name'] for c in dims]} 的组合数 {expected}，行数 {rows}，比值 {rows/expected} 位于0.5—2；未核验组合唯一性")
    if _has_aggregate_keywords(columns_info):
        return candidate("aggregate", "至少两个列名匹配既有聚合关键词；列名不证明实际聚合")
    return candidate("unknown", "现有标识、时间间隔和聚合名称规则未得到候选")


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
    output_contract=MINIMAL_PRODUCT_CONTRACTS["quick_profile"],
    description=(
        "一次性获取结构、类型推断和列级基础诊断；空表明确无可分析记录，其他问题为诊断警告。具体方法前提由所选方法及实际使用列核验。"
        "使用场景：首次接触新数据集时快速了解数据特征。"
        "不适用场景：只需要某个特定信息（用 describe_dataset/detect_data_quality 更轻量）。"
        "参数说明：compact=True 返回精简版（适合 load_data 后自动调用）。"
        "替代分别调用 describe_dataset + detect_data_quality + assess_readiness。"
    ),
)
def quick_profile(name: str, compact: bool = False) -> str:
    df,err=get_df(name)
    if err:return err
    identity=workspace.get_data_identity(name)
    cached=workspace.get_metadata(name,"_profile_cache")
    if cached and workspace.get_metadata(name,"_profile_identity")==identity and not compact:return cached
    result=_quick_profile_result(df,name,compact)
    output=json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)
    if not compact:
        workspace.set_metadata(name,"_profile_cache",output)
        workspace.set_metadata(name,"_profile_identity",identity)
    return output


_DIAGNOSTIC_LIMITATIONS=["仅为当前数据列级基础诊断；缺失、重复、异常和原样本量阈值是诊断提示，不裁决整个分析是否可做。", "具体可行性由所选方法及实际使用列的真实前提决定；基础检查不授予统计、预测或因果验证。"]


def _column_diagnostics(frame):
    result={}
    for column in frame.columns:
        values=frame[column];numeric=pd.api.types.is_numeric_dtype(values)
        finite=np.isfinite(values.to_numpy(dtype=float,na_value=np.nan)) if numeric else None
        result[str(column)]={"source_rows":len(values),"observed_count":int(values.notna().sum()),"missing_count":int(values.isna().sum()),"unique_values":int(values.nunique()),"finite_count":int(finite.sum()) if numeric else None,"nonfinite_count":int((values.notna() & ~finite).sum()) if numeric else 0}
    return result


def _quick_profile_result(df,name,compact=False):
    rows, cols = df.shape
    diagnostics=_column_diagnostics(df)
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
        if diagnostics[str(col)]["nonfinite_count"]:
            warnings.append(f"列 {col!r} 含 {diagnostics[str(col)]['nonfinite_count']} 条非有限观测；具体方法须核对实际有效范围。")

        # 质量问题检测
        if missing_pct >= 50:
            quality_issues.append(f"列 '{col}' 缺失率 {missing_pct:.0f}%")
        elif missing_pct > 0:
            warnings.append(f"列 '{col}' 缺失率 {missing_pct:.1f}%")

        # 日期列检查：是否为字符串格式的日期
        if likely_type == "text" and not pd.api.types.is_datetime64_any_dtype(df[col]):
            sample = df[col].dropna().head(5)
            try:
                with py_warnings.catch_warnings():
                    py_warnings.simplefilter("ignore", UserWarning)
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
        if diagnostics[str(col)]["nonfinite_count"]:
            warnings.append(f"列 {col!r} 含非有限值，原IQR异常值检查未计算；不补零或自动清洗。")
            continue
        q1 = df[col].quantile(0.25)
        q3 = df[col].quantile(0.75)
        iqr = q3 - q1
        if iqr > 0:
            outlier_count += int(((df[col] < q1 - 1.5 * iqr) | (df[col] > q3 + 1.5 * iqr)).sum())
    if outlier_count > 0:
        warnings.append(f"检测到 {outlier_count} 个数值异常值")

    # 就绪度
    readiness = "ready"
    if rows==0:
        readiness="blocked"
        quality_issues.append("没有可分析记录；列级诊断不验证任何方法前提。")
    elif quality_issues or warnings:
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
                "missing": sum(row["missing_count"]>0 for row in diagnostics.values()),
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
                "missing": sum(row["missing_count"]>0 for row in diagnostics.values()),
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

    result.update(dataset=name,column_diagnostics=diagnostics,method_preconditions_verified=False,limitations=_DIAGNOSTIC_LIMITATIONS)
    return result


@registry.register(
    name="assess_readiness",
    output_contract=MINIMAL_PRODUCT_CONTRACTS["assess_readiness"],
    description=(
        "报告时间粒度、样本量提示、逐列缺失与非有限值、常量列及数据时效性等基础诊断。"
        "空表明确无可分析记录；其他问题只作诊断警告，不裁决整个分析可行性，也不验证具体方法前提。"
    ),
)
def assess_readiness(name: str, intent: str = "") -> str:
    df,err=get_df(name)
    if err:return err
    return json.dumps(_readiness_result(df,name,intent),ensure_ascii=False,indent=2,allow_nan=False)


def _readiness_result(df,name,intent=""):
    from datetime import datetime
    rows, cols = df.shape
    findings = []
    diagnostics=_column_diagnostics(df)
    if rows==0:findings.append({"severity":"block","check":"empty_data","message":"没有可分析记录。"})
    for column,diagnostic in diagnostics.items():
        if diagnostic["nonfinite_count"]:findings.append({"severity":"warning","check":"nonfinite","column":column,"message":f"列 {column!r} 含 {diagnostic['nonfinite_count']} 条非有限观测；具体方法须核对实际有效范围。"})

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
                "message": f"当前{rows}行数据，{intent}建模建议≥{min_rows}行，仅为原经验提示，不是样本充分性或置信度检验",
            })

    # 3. Key column missing rate
    for col in df.columns:
        missing_pct = df[col].isnull().sum() / rows * 100 if rows > 0 else 0
        if missing_pct >= 50:
            findings.append({
                "severity": "warning",
                "check": "missing_data",
                "column":str(col),
                "message": f"列 '{col}' 缺失率 {missing_pct:.0f}%，影响取决于具体方法及实际使用列",
            })
        elif missing_pct > 30:
            findings.append({
                "severity": "warning",
                "check": "missing_data",
                "column":str(col),
                "message": f"列 '{col}' 缺失率 {missing_pct:.0f}%，部分分析可能受影响",
            })

    # 4. Constant / near-constant columns
    for col in df.columns:
        if df[col].nunique() <= 1:
            findings.append({
                "severity": "info",
                "check": "constant_column",
                "message": f"列 '{col}' 有 {df[col].nunique()} 个非缺失唯一值；影响由所选方法判断",
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

    recommendations = []
    if has_block:
        recommendations.append("没有可分析记录；请提供所需数据后再检查具体方法前提。")
    if has_warning:
        recommendations.append("分析结论需要显式说明数据质量警告和可能影响。")
    if any(f["check"] == "time_granularity" for f in findings):
        recommendations.append("时间序列或前后对比前，先确认时间粒度和缺失时间段。")
    if any(f["check"] == "sample_size" for f in findings):
        recommendations.append("原经验样本量建议不能替代具体方法实际要求，不据此判定统计置信度。")
    if not recommendations:
        recommendations.append("未发现现有基础检查中的问题；具体方法前提仍未评估。")

    # Build summary
    icon_map = {"block": "BLOCK", "warning": "WARN", "info": "INFO"}
    summary_lines = [f"Data Readiness: {overall} ({rows} rows x {cols} cols)"]
    for f in findings:
        summary_lines.append(f"  [{icon_map.get(f['severity'], '?')}] {f['message']}")
    if not findings:
        summary_lines.append("  [OK] 未发现现有基础检查问题；方法前提未评估")

    return {
        "dataset": name,
        "summary": "\n".join(summary_lines),
        "overall": overall,
        "findings": findings,
        "recommendations": recommendations,
        "rows": rows,
        "cols": cols,
        "column_diagnostics":diagnostics,"method_preconditions_verified":False,"limitations":_DIAGNOSTIC_LIMITATIONS,
    }


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
    from data_agent.utils.column_semantics import is_identifier_name, is_monetary_name
    rows = len(df)
    id_cols = []
    time_cols = []
    dim_cols = []
    key_metrics = []
    rate_metrics = []
    other_numeric = []
    other_text = []

    for col in df.columns:
        nunique = df[col].nunique()
        missing_pct = df[col].isnull().sum() / rows * 100 if rows > 0 else 0
        col_lower = col.lower().replace(" ", "").replace("_", "")

        # ID 列
        if is_identifier_name(col):
            id_cols.append({"column": col, "unique_count": nunique})
            continue

        # 时间列
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            time_cols.append(col)
            continue
        if pd.api.types.is_object_dtype(df[col]) or pd.api.types.is_string_dtype(df[col]):
            _, audit = _date_observation(df[col])
            if audit["time_candidate"]:
                time_cols.append(col)
                continue

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
            if nunique > 2 or is_monetary_name(col):
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
        "key_metrics": key_metrics,
        "rate_metrics": rate_metrics,
        "other_numeric": other_numeric,
        "other_text": other_text,
    }


def _date_observation(series: pd.Series):
    """Parse an observation view; retain the original column and parser rules."""
    native = pd.api.types.is_datetime64_any_dtype(series)
    inspected = native or pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series)
    sample = series.dropna().head(20)
    parsed = None
    sample_valid = None
    if inspected:
        with py_warnings.catch_warnings():
            py_warnings.simplefilter("ignore", UserWarning)
            parsed = series if native else pd.to_datetime(series, errors="coerce")
            sample_parsed = sample if native else pd.to_datetime(sample, errors="coerce")
        sample_valid = int(sample_parsed.notna().sum())
    valid = int(parsed.notna().sum()) if parsed is not None else None
    missing = int(series.isna().sum())
    return parsed, {"original_dtype":str(series.dtype), "source_rows":len(series), "missing_count":missing,
                    "inspected":inspected, "parseable_count":valid,
                    "parse_failed_count":len(series)-missing-valid if valid is not None else None,
                    "sample_size":len(sample) if inspected else 0, "sample_parseable_count":sample_valid,
                    "sample_rule":"前20条非缺失；可解析率至少80%；原生日期直接识别",
                    "confidence":"heuristic", "time_candidate":native or bool(inspected and len(sample) and sample_valid/len(sample)>=0.8)}


def _detect_time_range(df: pd.DataFrame, time_cols: list[str]) -> dict | None:
    """First time candidate's parseable range, including its actual exclusions."""
    if not time_cols: return None
    col = time_cols[0]
    parsed, audit = _date_observation(df[col])
    if parsed is None or not parsed.notna().any(): return None
    vals = parsed.dropna(); mn, mx = vals.min(), vals.max()
    return {"column":col, "min":mn.isoformat(), "max":mx.isoformat(), "span_days":(mx-mn).days,
            "parseable_count":audit["parseable_count"], "missing_count":audit["missing_count"],
            "parse_failed_count":audit["parse_failed_count"], "range_complete":audit["parse_failed_count"]==0,
            "range_basis":"仅可解析观测；普通缺失已披露；坏日期使原时间范围不完整"}


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
    result = [dict(item) for item in matched]
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
        r["status"] = "candidate_only"
        r["prerequisites"] = "仅根据候选列角色推荐方向；须另核所选方法、分析单位及实际使用列的前提"

    return result


def _interpret_result(df: pd.DataFrame, name: str, other_dfs: dict) -> dict:
    """Single owner for heuristic interpretation and its source observations."""
    other_dfs = dict(sorted(other_dfs.items()))
    rows, cols = df.shape

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
        if col in classified["time_columns"]:
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

    # All frames are supplied by the scoped tool or the verified host binding.
    cross_dataset_hints = []
    if other_dfs:
        from data_agent.utils.data_features import detect_cross_dataset_relationships
        relationships = detect_cross_dataset_relationships({name:df, **other_dfs})
        for rel in relationships:
            if name not in (rel["left"],rel["right"]): continue
            peer = rel["right"] if rel["left"]==name else rel["left"]
            cross_dataset_hints.append({"other_dataset":peer,"shared_columns":[rel["column"]],
                                        "rows_other":len(other_dfs[peer]),"overlap_pct":rel["overlap_pct"]})

    if cross_dataset_hints:
        for hint in cross_dataset_hints:
            suggested.append({
                "direction": f"关联分析: {name} × {hint['other_dataset']}",
                "tools": ["transform_data(merge)", "correlation_analysis", "compare_periods"],
                "priority": max(s["priority"] for s in suggested) + 1 if suggested else 4,
                "status":"candidate_only", "prerequisites":"先核分析单位、键基数、覆盖与时间范围",
                "reason": f"共享列 {hint['shared_columns'][:3]} 仅为候选线索；先审计分析单位、键基数、覆盖与时间范围，不能据此批准原始 merge。",
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
    data["cross_dataset_hints"] = cross_dataset_hints
    data["dataset"] = name
    data["dataset_reads"] = [name, *other_dfs]
    data["heuristic_status"] = "candidate_only"
    data["grain_basis"] = grain_info["grain_basis"]
    data["date_observation"] = {}
    data["column_role_basis"] = {}
    for col in df:
        _, audit = _date_observation(df[col])
        audit["time_candidate"] = col in classified["time_columns"]
        data["date_observation"][col] = audit
        roles = [role for role, entries in classified.items() if any((e.get("column") if isinstance(e,dict) else e)==col for e in entries)]
        data["column_role_basis"][col] = {"status":"candidate_only","confidence":"heuristic","roles":roles,
            "original_dtype":str(df[col].dtype),"unique_count":int(df[col].nunique()),"source_rows":rows,
            "rule":"依次按标识名称、原生日期或前20条80%可解析、数值率关键词、低基数非数值、数值基数/金额名称规则；关键指标沿原样本方差排序"}
    theme_cols = [m["column"] for role in ("key_metrics","rate_metrics","dimensions") for m in classified[role]]
    matches = {key:[kw for kw in keywords if any(kw in col.lower() for col in theme_cols)] for key,keywords in _THEME_PATTERNS.items()}
    data["theme_basis"] = {"candidate":theme,"status":"candidate_only","confidence":theme_confidence,
        "keyword_matches":matches,"confidence_rule":"匹配关键词数至少3为high、至少2为medium，否则low；置信标签未经业务验证"}
    data["limitations"] = ["列角色、行业主题、粒度和推荐路径均为启发候选，不能据此允许或禁止某类分析；具体方法与分析单位须核验真实前提。",
        "日期识别沿用前20条非缺失与80%可解析率；解释不转换原列，时间范围仅含可解析值；坏日期使范围不完整。",
        "跨表共享列与重合率只作线索，不证明关联键、可合并性、来源独立性或因果关系；overlap_pct沿用0—1比例：非缺失去重值交集数除以两侧较小集合大小，原检测器保留4位小数。"]
    return data




@registry.register(
    name="interpret_dataset",
    output_contract=MINIMAL_PRODUCT_CONTRACTS["interpret_dataset"],
    description="解释列角色、行业主题、粒度及跨表线索的启发候选，公开规则依据和日期解析范围；具体方法可行性另核真实前提，不改变原列。",
)
def interpret_dataset(name: str) -> str:
    from data_agent.tools.registry import ToolResult
    from data_agent.agent.execution_scope import current_context_execution_scope, ensure_dataset_allowed_in_current_context
    guard = ensure_dataset_allowed_in_current_context(name)
    if not guard.allowed:
        return json.dumps({"error":guard.message,"error_type":guard.error_type},ensure_ascii=False)
    df, err = get_df(name)
    if err: return ToolResult(summary=err,data={"error":err})
    scope = current_context_execution_scope()
    names = scope.allowed_datasets if scope.active else workspace.list_datasets()
    other_dfs = {}
    fingerprint = workspace.get_data_identity(name).get("source_fingerprint")
    for other_name in names:
        if other_name==name: continue
        if fingerprint and workspace.get_data_identity(other_name).get("source_fingerprint")==fingerprint: continue
        other = workspace.get(other_name)
        if other is not None: other_dfs[other_name]=other
    data = _interpret_result(df,name,other_dfs)
    summary = f"数据集 '{name}' ({len(df)}×{len(df.columns)})；主题候选：{data['theme']}；{data['grain_hint']}"
    return ToolResult(summary=summary,data=data,suggested_next=data["suggested_analyses"][0]["tools"][0] if data["suggested_analyses"] else None)
