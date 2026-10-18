"""数据类型智能推断与清洗。"""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Optional

import numpy as np
import pandas as pd

from data_agent.session.workspace import workspace
from data_agent.tools.registry import registry
from data_agent.agent.publication.native import MINIMAL_PRODUCT_CONTRACTS
from data_agent.utils.column_semantics import is_identifier_name, is_monetary_name


# ── 识别模式 ──────────────────────────────────────────────

_PERCENT_RE = re.compile(r'^[(-+]?\s*\d+\.?\d*\s*%\s*\)?:?$')
_DATE_FORMATS = [
    "%Y-%m-%d", "%Y/%m/%d", "%Y年%m月%d日",
    "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S",
    "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M",
    "%Y%m%d", "%m/%d/%Y", "%d/%m/%Y",
    "%m-%d-%Y", "%d-%m-%Y",
    "%Y.%m.%d", "%Y.%m.%d %H:%M",
]
_BOOL_MAP = {
    "true": True, "false": False,
    "yes": True, "no": False,
    "是": True, "否": False,
    "y": True, "n": False,
    "1": True, "0": False,
}
_INT_SUFFIXES = ("人", "个", "次", "天", "元", "万", "件", "台", "笔", "条")


def _sample_values(series: pd.Series, n: int = 20) -> list:
    """取非空样本值。"""
    vals = series.dropna().unique()
    if len(vals) <= n:
        return list(vals)
    rng = np.random.default_rng(42)
    indices = rng.choice(len(vals), size=n, replace=False)
    return [vals[i] for i in indices]


def _try_parse_dates(values: list) -> Optional[str]:
    """尝试将值列表解析为日期，返回匹配的格式字符串，否则 None。"""
    for fmt in _DATE_FORMATS:
        ok = 0
        for v in values:
            s = str(v).strip()
            if not s:
                continue
            try:
                pd.to_datetime(s, format=fmt)
                ok += 1
            except (ValueError, TypeError):
                break
        if ok == len(values) and ok > 0:
            return fmt
    return None


def _is_percentage(values: list) -> bool:
    """判断值列表是否全为百分比字符串。"""
    if not values:
        return False
    return all(_PERCENT_RE.match(str(v)) for v in values)


def _parse_percent(s: str) -> float:
    """'12.5%' -> 0.125"""
    return float(re.sub(r'[%\s()　]', '', s)) / 100


def _is_integer_like(values: list) -> bool:
    """判断数值列是否实际为整数（如 20250101 形式的日期、ID 等）。"""
    if not values:
        return False
    return all(isinstance(v, (int, np.integer)) or (isinstance(v, float) and np.isfinite(v) and v == int(v)) for v in values)


def _looks_like_date_int(values: list) -> bool:
    """检测 20250101 这种整数值是否是日期。"""
    if not values:
        return False
    for v in values:
        s = str(int(v))
        if len(s) != 8:
            return False
        try:
            date(int(s[:4]), int(s[4:6]), int(s[6:8]))
        except ValueError:
            return False
    return True


def _is_bool_like(values: list) -> bool:
    if not values:
        return False
    return all(str(v).strip().lower() in _BOOL_MAP for v in values)


def _has_numeric_suffix(values: list) -> bool:
    """检测 '123元' '1.5万' 这类带单位后缀的数值。"""
    if not values:
        return False
    count = sum(1 for v in values if any(str(v).strip().endswith(s) for s in _INT_SUFFIXES))
    return count / len(values) >= 0.8


def _parse_number_with_suffix(s: str) -> Optional[float]:
    """解析带中文单位的数值，如 '1.5万' -> 15000。"""
    s = str(s).strip()
    if s.endswith("万"):
        try:
            return float(s[:-1]) * 10000
        except ValueError:
            return None
    if s.endswith("亿"):
        try:
            return float(s[:-1]) * 100000000
        except ValueError:
            return None
    for suf in _INT_SUFFIXES:
        if s.endswith(suf):
            try:
                return float(s[:-len(suf)])
            except ValueError:
                return None
    return None


# ── 主推断逻辑 ────────────────────────────────────────────

def infer_column_type(series: pd.Series) -> dict:
    """
    推断列的最佳类型。返回:
      { "column": str, "current_dtype": str, "suggested_type": str,
        "sample": list, "confidence": str, "reason": str }
    """
    col_name = series.name
    current = str(series.dtype)
    sample = [str(v) for v in _sample_values(series)[:8]]
    result = {
        "column": col_name,
        "current_dtype": current,
        "sample": sample,
        "suggested_type": "keep",
        "confidence": "high",
        "reason": "",
    }

    # 已经是 datetime
    if pd.api.types.is_datetime64_any_dtype(series):
        result["suggested_type"] = "datetime"
        result["reason"] = "已经是 datetime 类型"
        return result

    values = _sample_values(series, n=20)
    if not values:
        result["reason"] = "全为空值"
        return result

    if is_identifier_name(col_name):
        result["reason"] = "标识字段保留原值；重复标识不等于数值指标，是否唯一须另行审计"
        return result

    # 1) 字符串 / object 列
    if pd.api.types.is_string_dtype(series) or pd.api.types.is_object_dtype(series):
        # 百分比
        if _is_percentage(values):
            result["suggested_type"] = "percentage_to_float"
            result["reason"] = "检测到百分比格式（如 '12.5%'），建议转为小数 0.125"
            result["confidence"] = "high"
            return result

        # 带单位后缀的数值
        if _has_numeric_suffix(values):
            result["suggested_type"] = "numeric_with_suffix"
            result["reason"] = f"检测到带单位的数值（如 {sample[:3]}），建议提取数值部分"
            result["confidence"] = "medium"
            return result

        # 布尔
        if _is_bool_like(values):
            result["suggested_type"] = "bool"
            result["reason"] = "检测到布尔值（是/否、yes/no、true/false）"
            result["confidence"] = "high"
            return result

        # 日期
        fmt = _try_parse_dates(values)
        if fmt:
            result["suggested_type"] = "datetime"
            result["reason"] = f"检测到日期格式（示例格式: {fmt}）"
            result["confidence"] = "high"
            return result

        # 尝试转数值
        num_ok = 0
        for v in values:
            try:
                float(str(v).replace(",", "").replace("，", ""))
                num_ok += 1
            except (ValueError, TypeError):
                pass
        if num_ok == len(values) and num_ok > 0:
            result["suggested_type"] = "numeric"
            result["reason"] = "字符串形式的数值，建议转为数值类型"
            result["confidence"] = "high"
            return result

        result["reason"] = "文本类型，无需转换"
        return result

    # 2) 数值列：检测是否实际为日期或类别
    if pd.api.types.is_numeric_dtype(series):
        nunique = series.nunique()
        if is_monetary_name(col_name):
            result["reason"] = "金额字段保留数值类型；取值少不代表类别编码，币种与单位仍须核对"
            return result
        # 整数且看起来像日期（20250101）
        if _is_integer_like(values) and _looks_like_date_int(values):
            result["suggested_type"] = "date_int_to_datetime"
            result["reason"] = "检测到 8 位整数形式的日期（如 20250101），建议转为 datetime"
            result["confidence"] = "medium"
            return result

        # 低基数整数可能是类别（如 0/1 编码）
        if nunique <= 10 and _is_integer_like(values):
            result["suggested_type"] = "category_maybe"
            result["reason"] = f"低基数整数列（{nunique} 个唯一值），可能为类别编码，请确认"
            result["confidence"] = "low"
            return result

        result["reason"] = "数值类型，无需转换"
        return result

    result["reason"] = "无需转换"
    return result


# ── 执行转换 ──────────────────────────────────────────────

def apply_conversion(series: pd.Series, suggested_type: str) -> pd.Series:
    """根据推断的类型执行转换。"""
    if suggested_type == "percentage_to_float":
        return series.apply(lambda x: _parse_percent(str(x)) if pd.notna(x) else x)

    if suggested_type == "numeric_with_suffix":
        def _conv(v):
            if pd.isna(v):
                return v
            r = _parse_number_with_suffix(str(v))
            return r if r is not None else v
        return series.apply(_conv)

    if suggested_type == "datetime":
        return pd.to_datetime(series, errors="coerce")

    if suggested_type == "date_int_to_datetime":
        return pd.to_datetime(series.astype(str), format="%Y%m%d", errors="coerce")

    if suggested_type == "numeric":
        return pd.to_numeric(series.astype(str).str.replace(",", "").str.replace("，", ""), errors="coerce")

    if suggested_type == "bool":
        return series.apply(lambda x: _BOOL_MAP.get(str(x).strip().lower(), x) if pd.notna(x) else x)

    if suggested_type == "category":
        return series.astype("category")

    return series


# ── 自动清洗 ──────────────────────────────────────────────

# 高置信度：自动执行无需确认
_AUTO_CONVERT_TYPES = {"datetime", "percentage_to_float", "date_int_to_datetime", "bool"}

# 中置信度：自动执行但需告知用户
_NOTIFY_CONVERT_TYPES = {"numeric_with_suffix", "numeric"}


def _conversion_audit(source: pd.Series, converted: pd.Series, *, target_type="", error="") -> dict:
    """Count actual compatible outputs; retained bad text is not a conversion."""
    from numbers import Number
    from datetime import datetime
    non_null=source.notna();source_non_null=int(non_null.sum())
    valid=converted.notna()
    if target_type=="bool":
        valid=converted.map(lambda v:isinstance(v,(bool,np.bool_))).astype(bool)
    elif target_type in {"numeric","percentage_to_float","numeric_with_suffix"}:
        valid=converted.map(lambda v:isinstance(v,Number) and not isinstance(v,(bool,np.bool_)) and pd.notna(v)).astype(bool)
    elif target_type in {"datetime","date_int_to_datetime"}:
        valid=converted.map(lambda v:pd.notna(v) and isinstance(v,(datetime,np.datetime64))).astype(bool)
    elif target_type=="category" and not isinstance(converted.dtype,pd.CategoricalDtype):
        valid=valid & False
    converted_values=0 if error else int(valid.loc[non_null].sum())
    failures=source_non_null-converted_values
    result={"source_non_null":source_non_null,"converted_values":converted_values,
        "conversion_failures":failures,"conversion_failure_rate":round(failures/source_non_null,6) if source_non_null else 0.0}
    if target_type:
        result.update(column=source.name,to=target_type,from_dtype=str(source.dtype),new_dtype=str(converted.dtype),
            original_missing=int(source.isna().sum()),remaining_missing=int(converted.isna().sum()),
            new_missing=int(converted.loc[non_null].isna().sum()),
            reason=error or ("部分非缺失值未转换为所选目标；保留该策略原有坏值处理方式" if failures else ""))
    return result


def auto_clean(df: pd.DataFrame) -> tuple[pd.DataFrame, list[dict], list[dict]]:
    """自动推断并转换数据类型。

    Returns:
        (df, applied, needs_confirm)
        - df: 清洗后的 DataFrame
        - applied: 已自动转换的列列表
        - needs_confirm: 需要用户确认的列列表
    """
    df = df.copy()
    applied = []
    needs_confirm = []

    for col in df.columns:
        info = infer_column_type(df[col])
        st = info["suggested_type"]

        if st == "keep":
            continue

        if st in _AUTO_CONVERT_TYPES and info["confidence"] == "high":
            try:
                before = str(df[col].dtype)
                df[col] = apply_conversion(df[col], st)
                after = str(df[col].dtype)
                applied.append({
                    "column": col,
                    "from": before,
                    "to": after,
                    "action": st,
                    "reason": info["reason"],
                })
            except Exception as e:
                applied.append({"column": col, "action": st, "error": str(e)})

        elif st in _NOTIFY_CONVERT_TYPES:
            try:
                before = str(df[col].dtype)
                source_values = df[col].copy()
                df[col] = apply_conversion(df[col], st)
                after = str(df[col].dtype)
                entry = {
                    "column": col,
                    "from": before,
                    "to": after,
                    "action": st,
                    "reason": info["reason"],
                }
                if st == "numeric":
                    entry.update(_conversion_audit(source_values, df[col]))
                applied.append(entry)
            except Exception as e:
                applied.append({"column": col, "action": st, "error": str(e)})

        elif info["confidence"] == "low" or st == "category_maybe":
            needs_confirm.append({
                "column": col,
                "current_dtype": info["current_dtype"],
                "suggested_type": st,
                "reason": info["reason"],
                "sample": info["sample"],
            })

    # Post-pass: coerce remaining object columns to numeric where possible
    df, numeric_conversions = _try_coerce_object_to_numeric(df)
    applied.extend(numeric_conversions)

    return df, applied, needs_confirm


def _try_coerce_object_to_numeric(df: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """Post-pass: attempt pd.to_numeric on remaining object columns.

    Catches columns that infer_column_type missed due to mixed types,
    sparse nulls, or edge-case formatting. Only applies conversion when
    >90% of non-null values convert successfully.
    """
    df = df.copy()
    conversions = []

    for col in df.columns:
        if df[col].dtype != object:
            continue

        non_null = df[col].dropna()
        if len(non_null) == 0:
            continue

        converted = pd.to_numeric(non_null, errors="coerce")
        success_count = converted.notna().sum()
        total_count = len(non_null)

        if total_count > 0 and success_count / total_count >= 0.9:
            df[col] = pd.to_numeric(df[col], errors="coerce")
            conversions.append({
                "column": col,
                "from": "object",
                "to": str(df[col].dtype),
                "action": "object_to_numeric",
                "reason": f"object 列含数值数据 ({success_count}/{total_count} 成功转换)",
                "source_non_null": int(total_count),
                "converted_values": int(success_count),
                "conversion_failures": int(total_count - success_count),
                "conversion_failure_rate": round(float((total_count - success_count) / total_count), 6),
            })

    return df, conversions


# ── 工具接口 ──────────────────────────────────────────────

def _type_suggestions_result(df: pd.DataFrame, name: str) -> dict:
    """One rule owner for type advice and storage-owned receipt verification."""
    suggestions = []
    for col in df.columns:
        info = infer_column_type(df[col])
        if info["suggested_type"] != "keep":
            suggestions.append(info)
    return {
        "dataset": name,
        "columns_analyzed": len(df.columns),
        "suggestions": suggestions,
        "observation": {
            "source_rows": len(df),
            "columns_analyzed": len(df.columns),
            "max_unique_values_per_column": 20,
            "max_displayed_values_per_column": 8,
            "sampling": "每列非缺失唯一值不超过20个时全部使用，否则以固定随机种子42抽取20个；展示其中前8个。",
        },
        "limitations": [
            "类型建议来自列名、原dtype、唯一值数及既有样本规则，置信度是规则标签；不表示全列转换已通过验收或业务语义已确认。",
            "仅给出建议，不修改数据；低基数整数仅可能是类别编码，需确认。空建议集合只表示当前规则没有提出转换。",
        ],
    }


@registry.register(
    name="suggest_column_types",
    output_contract=MINIMAL_PRODUCT_CONTRACTS["suggest_column_types"],
    description="分析各列并给出类型转换建议及样本范围；每列最多20个非缺失唯一值，置信度为规则标签，不代表全列转换已验收。不修改数据。在 load_data 之后调用。",
)
def suggest_column_types(name: str) -> str:
    df = workspace.get(name)
    if df is None:
        available = list(workspace.list_datasets().keys())
        return json.dumps({"error": f"数据集 '{name}' 不存在。可用: {available}"}, ensure_ascii=False)

    return json.dumps(_type_suggestions_result(df, name), ensure_ascii=False, indent=2)


@registry.register(
    name="apply_type_conversion",
    capability={"capability_id":"data.apply_type_conversion","category":"data_transform"},
    output_contract={"version":"native_operation_effect.v1","adapter":"data_agent.agent.publication.native.resolve_operation_effect","kinds":["operation"]},
    description="对指定列执行类型转换。column 为列名，target_type 为: datetime/numeric/percentage_to_float/bool/category/date_int_to_datetime/numeric_with_suffix。也可以传 auto=true 自动应用所有建议转换。",
    schema_overrides={
        "name": {"description": "数据集名称"},
        "column": {"description": "目标列名"},
        "target_type": {"description": "目标类型", "enum": ["", "datetime", "numeric", "percentage_to_float", "bool", "category", "date_int_to_datetime", "numeric_with_suffix"]},
        "auto": {"description": "是否自动应用所有建议转换"},
    },
)
def apply_type_conversion(
    name: str,
    column: str = "",
    target_type: str = "",
    auto: bool = False,
) -> str:
    df = workspace.get(name)
    if df is None:
        return json.dumps({"error": f"数据集 '{name}' 不存在"}, ensure_ascii=False)

    df = df.copy()

    if auto:
        applied=[];audits=[];skipped=[]
        for col in df.columns:
            info=infer_column_type(df[col]);st=info["suggested_type"]
            if st=="keep" or info["confidence"]=="low" or st=="category_maybe":
                skipped.append({"column":col,"suggested_type":st,"reason":info["reason"]})
                continue
            original=df[col].copy();error=""
            try:
                df[col]=apply_conversion(original,st)
                applied.append({"column":col,"converted_to":st})
            except Exception as exc:
                error=str(exc);applied.append({"column":col,"error":error})
            audits.append(_conversion_audit(original,df[col],target_type=st,error=error))
        expression="automatic safe type conversions"
    else:
        if not column or not target_type:
            return json.dumps({"error":"手动模式需指定 column 和 target_type"},ensure_ascii=False)
        if column not in df.columns:
            return json.dumps({"error":f"列 '{column}' 不存在。可用: {list(df.columns)}"},ensure_ascii=False)
        if target_type not in {"datetime","numeric","percentage_to_float","bool","category","date_int_to_datetime","numeric_with_suffix"}:
            return json.dumps({"error":"未知目标类型"},ensure_ascii=False)
        original=df[column].copy()
        try:df[column]=apply_conversion(original,target_type)
        except Exception as exc:return json.dumps({"error":f"转换失败: {exc}"},ensure_ascii=False)
        audits=[_conversion_audit(original,df[column],target_type=target_type)]
        expression=f"{column}: {target_type}"
    target_name=workspace.next_analysis_name(name,"type_clean")
    derive_result=workspace.derive(name,target_name,df,expression=expression)
    if derive_result.startswith("Error:"):return json.dumps({"error":derive_result},ensure_ascii=False)
    result={"dataset":target_name,"source_dataset":name,"conversion_audit":audits,
        "status":"partial" if any(r["conversion_failures"] or r["reason"] for r in audits) else "complete"}
    if auto:result.update(auto_applied=applied,skipped=skipped)
    else:result["converted"]={"column":column,"to":target_type,"new_dtype":str(df[column].dtype)}
    return json.dumps(result,ensure_ascii=False,indent=2)


# ── 显式数据清洗 ────────────────────────────────────────

_FILL_STRATEGIES = {
    "drop": "删除含缺失值的行",
    "fill_mean": "均值填充",
    "fill_median": "中位数填充",
    "fill_mode": "众数填充",
    "fill_constant": "固定值填充（需通过 fill_value 参数指定）",
}

_OUTLIER_STRATEGIES = {
    "mark": "标记异常值但不处理",
    "cap": "截断到 IQR 边界",
    "drop": "删除含异常值的行",
}


@registry.register(
    name="clean_data",
    capability={"capability_id":"data.clean_data","category":"data_transform"},
    output_contract={"version":"native_operation_effect.v1","adapter":"data_agent.agent.publication.native.resolve_operation_effect","kinds":["operation"]},
    description=(
        "对数据集执行显式清洗：缺失值处理、去重、异常值处理。"
        "missing_strategy: keep（保留缺失值）/ drop（删除行）/ fill_mean / fill_median / fill_mode / fill_constant。"
        "outlier_strategy: mark（标记不处理）/ cap（截断到IQR边界）/ drop（删除行）。"
        "deduplicate 仅在用户明确选择时去除完全重复行。所有结果都会创建新的派生分析数据集，不会修改来源数据。"
    ),
    schema_overrides={
        "name": {"description": "数据集名称"},
        "missing_strategy": {"description": "缺失值处理策略", "enum": ["keep", "drop", "fill_mean", "fill_median", "fill_mode", "fill_constant"]},
        "outlier_strategy": {"description": "异常值处理策略", "enum": ["mark", "cap", "drop"]},
        "deduplicate": {"description": "是否去除完全重复行；仅在业务语义确认后使用"},
        "columns": {"description": "目标列，逗号分隔，为空则处理所有列"},
        "fill_value": {"description": "fill_constant 策略的填充值"},
    },
)
def clean_data(
    name: str,
    missing_strategy: str = "keep",
    outlier_strategy: str = "mark",
    deduplicate: bool = False,
    columns: str = "",
    fill_value: str = "",
) -> str:
    df = workspace.get(name)
    if df is None:
        available = list(workspace.list_datasets().keys())
        return json.dumps({"error": f"数据集 '{name}' 不存在。可用: {available}"}, ensure_ascii=False)

    df = df.copy()
    report = {"dataset": name, "original_rows": len(df), "actions": []}

    # 确定目标列
    target_cols = [c.strip() for c in columns.split(",") if c.strip()] if columns else list(df.columns)

    if missing_strategy not in {"keep", *_FILL_STRATEGIES} or outlier_strategy not in _OUTLIER_STRATEGIES:
        return json.dumps({"error": "未知清洗策略"}, ensure_ascii=False)
    if len(target_cols) != len(set(target_cols)) or any(c not in df.columns for c in target_cols):
        return json.dumps({"error": "目标列不存在或重复"}, ensure_ascii=False)

    # 1. 去重是业务语义选择：没有稳定订单/事件主键时，完全重复行也可能是有效观测。
    if deduplicate:
        before_dedup = len(df)
        df = df.drop_duplicates()
        removed_dedup = before_dedup - len(df)
        report["actions"].append({
            "action": "deduplicate",
            "removed": removed_dedup,
        })

    # Count actual changes at the imputation stage; row deletion is not filling.
    missing_before = df[target_cols].isna().sum().to_dict()
    handling = {"strategy": missing_strategy, "columns": []}
    if missing_strategy == "drop":
        before = len(df)
        df = df.dropna(subset=target_cols)
        report["actions"].append({"action": "missing_drop", "removed_rows": before-len(df)})
    for col in target_cols:
        count = int(missing_before[col]); reason = ""
        if count and missing_strategy.startswith("fill_"):
            value = None
            try:
                if missing_strategy in {"fill_mean", "fill_median"}:
                    if not pd.api.types.is_numeric_dtype(df[col]) or pd.api.types.is_bool_dtype(df[col]):
                        reason = "非数值列，所选均值/中位数策略不适用"
                    else:
                        value = df[col].mean() if missing_strategy == "fill_mean" else df[col].median()
                        if pd.isna(value) or not np.isfinite(value):
                            reason = "没有可用的有限数值，无法求填充值"
                elif missing_strategy == "fill_mode":
                    modes = df[col].mode()
                    if modes.empty: reason = "没有非缺失观测，众数未知"
                    else: value = modes.iloc[0]
                elif fill_value:
                    try: value = float(fill_value) if df[col].dtype in ("float64", "int64") else fill_value
                    except ValueError: value = fill_value
                else:
                    reason = "未指定固定填充值"
                if not reason:
                    df[col] = df[col].fillna(value)
            except (TypeError, ValueError, OverflowError) as exc:
                reason = "所选填充值无法应用于原列类型："+str(exc)
        after = int(df[col].isna().sum())
        filled = count-after if missing_strategy.startswith("fill_") else 0
        if count and missing_strategy == "keep": reason = "按明确选择保留缺失"
        handling["columns"].append({"column": col, "missing_before": count,
            "filled": filled, "missing_after_strategy": after, "reason": reason})
    handling["filled"] = sum(r["filled"] for r in handling["columns"])
    handling["rows_after_strategy"] = len(df)
    if missing_strategy != "drop":
        report["actions"].append({"action": "missing_"+missing_strategy, "filled": handling["filled"]})

    # 3. 异常值处理（仅数值列）
    outlier_report = []
    numeric_cols = [c for c in target_cols if c in df.columns and pd.api.types.is_numeric_dtype(df[c])]

    for col in numeric_cols:
        q1 = df[col].quantile(0.25)
        q3 = df[col].quantile(0.75)
        iqr = q3 - q1
        if iqr == 0:
            continue
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr
        outlier_mask = (df[col] < lower) | (df[col] > upper)
        outlier_count = int(outlier_mask.sum())

        if outlier_count > 0:
            if outlier_strategy == "cap":
                df[col] = df[col].clip(lower=lower, upper=upper)
                outlier_report.append({"column": col, "capped": outlier_count, "range": [float(lower), float(upper)]})
            elif outlier_strategy == "drop":
                before = len(df)
                df = df[~outlier_mask]
                outlier_report.append({"column": col, "removed": before - len(df)})
            elif outlier_strategy == "mark":
                outlier_report.append({"column": col, "marked": outlier_count, "range": [float(lower), float(upper)]})

    if outlier_report:
        report["actions"].append({"action": f"outlier_{outlier_strategy}", "details": outlier_report})

    for row in handling["columns"]:
        row["missing_after"] = int(df[row["column"]].isna().sum())
    handling["remaining"] = sum(r["missing_after"] for r in handling["columns"])
    report["missing_handling"] = handling
    report["status"] = "partial" if missing_strategy != "keep" and handling["remaining"] else "complete"
    report["final_rows"] = len(df)
    report["rows_removed"] = report["original_rows"] - len(df)

    target_name = workspace.next_analysis_name(name, "cleaned")
    derive_result = workspace.derive(
        name,
        target_name,
        df,
        expression=(
            f"missing={missing_strategy}; deduplicate={deduplicate}; "
            f"outlier={outlier_strategy}; columns={columns or 'all'}"
        ),
    )
    if derive_result.startswith("Error:"):
        return json.dumps({"error": derive_result}, ensure_ascii=False)
    report["dataset"] = target_name
    report["source_dataset"] = name
    return json.dumps(report, ensure_ascii=False, indent=2)
