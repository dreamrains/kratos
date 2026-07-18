"""数据类型智能推断与清洗。"""

from __future__ import annotations

import json
import re
from numbers import Number
from typing import Any, Optional

import numpy as np
import pandas as pd

from data_agent.session.workspace import workspace
from data_agent.tools.registry import registry


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
_SCALED_NUMERIC_SUFFIXES = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}


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
    return all(isinstance(v, (int, np.integer)) or (isinstance(v, float) and v == int(v)) for v in values)


def _looks_like_date_int(values: list) -> bool:
    """检测 20250101 这种整数值是否是日期。"""
    if not values:
        return False
    for v in values:
        s = str(int(v))
        if len(s) != 8:
            return False
        try:
            int(s[:4]), int(s[4:6]), int(s[6:8])
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
    count = sum(_parse_number_with_suffix(str(value)) is not None for value in values)
    return count / len(values) >= 0.8


def _parse_number_with_suffix(s: str) -> Optional[float]:
    """解析带中文单位的数值，如 '1.5万' -> 15000。"""
    s = str(s).strip()
    scaled_suffix = s[-1:].lower()
    if scaled_suffix in _SCALED_NUMERIC_SUFFIXES:
        try:
            return float(s[:-1]) * _SCALED_NUMERIC_SUFFIXES[scaled_suffix]
        except ValueError:
            return None
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


def prepare_analysis_copy(
    frame: pd.DataFrame,
    *,
    logical_name: str,
    raw_dataset_id: str,
    source_fingerprint: str,
) -> tuple[pd.DataFrame, dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    """Prepare a non-mutating analysis copy and describe every proposed change."""
    from data_agent.agent.data_lineage import TransformationRecord

    prepared = frame.copy(deep=True)
    applied: list[dict[str, Any]] = []
    proposals: list[dict[str, Any]] = []

    for column in prepared.columns:
        info = infer_column_type(prepared[column])
        suggested = info["suggested_type"]
        if suggested == "keep":
            continue
        if suggested in _AUTO_CONVERT_TYPES and info["confidence"] == "high":
            candidate = apply_conversion(prepared[column].copy(), suggested)
            new_nulls = int(candidate.isna().sum() - prepared[column].isna().sum())
            if new_nulls <= 0:
                prepared[column] = candidate
                applied.append({
                    "column": column,
                    "action": suggested,
                    "reason": info["reason"],
                    "decision_policy": "auto_safe",
                })
                continue
        proposals.append({
            "column": column,
            "suggested_type": suggested,
            "reason": info["reason"],
            "decision_policy": "confirmation_required",
        })

    record = TransformationRecord(
        parent_dataset_id=raw_dataset_id,
        raw_dataset_id=raw_dataset_id,
        source_fingerprint=source_fingerprint,
        logical_name=logical_name,
        operations=tuple(applied),
        affected_columns=tuple(item["column"] for item in applied),
        information_loss=False,
        decision_policy="auto_safe" if applied else "none",
    ).to_dict()
    return prepared, record, applied, proposals


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
            })

    return df, conversions


def _require_workspace_mapping(value: Any, operation: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RuntimeError(f"Workspace {operation} failed: {value}")
    return value


def _coerce_bool_flag(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _ensure_versioned_dataset(
    name: str,
    frame: pd.DataFrame,
) -> tuple[dict[str, Any], pd.DataFrame]:
    """Return the active version, initializing a legacy dataset when needed."""
    active_info = workspace.get_active_version_info(name)
    if active_info is not None:
        version = workspace.get_dataset_version(active_info["dataset_id"])
        return active_info, (version if version is not None else frame).copy(deep=True)

    from data_agent.agent.data_lineage import frame_fingerprint

    source_fingerprint = frame_fingerprint(frame)
    raw_info = _require_workspace_mapping(
        workspace.register_raw_snapshot(name, frame, source_fingerprint),
        "raw registration",
    )
    prepared, preparation_record, _, _ = prepare_analysis_copy(
        frame,
        logical_name=name,
        raw_dataset_id=raw_info["dataset_id"],
        source_fingerprint=source_fingerprint,
    )
    active_info = _require_workspace_mapping(
        workspace.promote_analysis_copy(
            name,
            prepared,
            raw_info["dataset_id"],
            preparation_record,
        ),
        "analysis-copy promotion",
    )
    return active_info, prepared.copy(deep=True)


def _make_transformation_record(
    *,
    active_info: dict[str, Any],
    logical_name: str,
    operations: list[dict[str, Any]],
    affected_columns: list[str],
    affected_row_count: int,
    before_after_metrics: dict[str, Any],
    information_loss: bool,
    decision_policy: str,
    confirmation_status: str,
) -> dict[str, Any]:
    from data_agent.agent.data_lineage import TransformationRecord

    return TransformationRecord(
        parent_dataset_id=active_info["dataset_id"],
        raw_dataset_id=active_info["raw_dataset_id"],
        source_fingerprint=active_info.get("source_fingerprint", ""),
        logical_name=logical_name,
        operations=tuple(operations),
        affected_columns=tuple(dict.fromkeys(affected_columns)),
        affected_row_count=int(affected_row_count),
        before_after_metrics=before_after_metrics,
        information_loss=information_loss,
        decision_policy=decision_policy,
        confirmation_status=confirmation_status,
    ).to_dict()


def _promote_candidate(
    name: str,
    candidate: pd.DataFrame,
    active_info: dict[str, Any],
    record: dict[str, Any],
) -> dict[str, Any]:
    return _require_workspace_mapping(
        workspace.promote_analysis_copy(
            name,
            candidate,
            active_info["raw_dataset_id"],
            record,
        ),
        "analysis-copy promotion",
    )


def _proposal_sessions_root():
    from data_agent.config import get_config

    return get_config().sessions_resolved


def _data_clean_session_id(value: str = "") -> str:
    if str(value or "").strip():
        return str(value).strip()
    from data_agent.tools.visualization import current_session_id

    return current_session_id() or "local"


def _proposal_ref(proposal: dict[str, Any], *, session_id: str) -> dict[str, Any]:
    """Persist a complete proposal while returning only its bounded identity."""
    from data_agent.tools._utils import persist_detail

    path = persist_detail(session_id, proposal["proposal_id"], proposal)
    return {
        "proposal_id": proposal["proposal_id"],
        "artifact_path": str(path),
        "data_version": (
            f"dataset:{proposal['dataset_version_id']}:{proposal['source_fingerprint']}"
        ),
        "spec_version": f"transformation:{proposal['transformation_fingerprint']}",
        "candidate_fingerprint": proposal["candidate_fingerprint"],
    }


def _request_transformation_confirmation(
    proposal: dict[str, Any],
    *,
    session_id: str,
    turn_id: str,
) -> tuple[dict[str, Any], str]:
    from data_agent.agent.confirmation.runtime import (
        build_action_registry,
        build_dataset_transformation_candidate,
    )
    from data_agent.agent.confirmation.service import ConfirmationService

    ref = _proposal_ref(proposal, session_id=session_id)
    candidate = build_dataset_transformation_candidate(
        session_id=session_id,
        turn_id=turn_id,
        proposal_ref=ref,
    )
    service = ConfirmationService(_proposal_sessions_root(), action_registry=build_action_registry())
    result = service.request(candidate)
    record = result.record or service.get(session_id, result.reused_confirmation_id or candidate.confirmation_id)
    checkpoint = service.checkpoint(session_id)
    if checkpoint is not None and checkpoint.confirmation_id == record.confirmation_id:
        record = checkpoint
    return ref, record.confirmation_id


def _material_proposal(
    *,
    name: str,
    active_info: dict[str, Any],
    operation: str,
    parameters: dict[str, Any],
    before: pd.DataFrame,
    candidate: pd.DataFrame,
    affected_columns: list[str],
    affected_row_count: int,
    information_loss: bool,
) -> dict[str, Any]:
    from data_agent.agent.data_lineage import build_transformation_proposal
    from data_agent.agent.data_lineage import frame_fingerprint

    return build_transformation_proposal(
        logical_dataset=name,
        active_dataset=active_info,
        operation=operation,
        parameters=parameters,
        candidate_fingerprint=frame_fingerprint(candidate),
        impact={
            "row_count_before": len(before),
            "row_count_after": len(candidate),
            "affected_columns": list(dict.fromkeys(affected_columns)),
            "affected_row_count": int(affected_row_count),
            "information_loss": bool(information_loss),
        },
    )


def _load_transformation_proposal(path: str) -> dict[str, Any]:
    from pathlib import Path

    try:
        proposal = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("transformation proposal artifact is unavailable") from exc
    if not isinstance(proposal, dict) or proposal.get("contract_version") != "transformation_proposal.v1":
        raise ValueError("transformation proposal artifact is invalid")
    return proposal


def apply_confirmed_transformation(confirmation_id: str, *, session_id: str = "") -> dict[str, Any]:
    """Recompute and promote a proposal only after its canonical receipt resolves."""
    from data_agent.agent.confirmation.models import ConfirmationStatus
    from data_agent.agent.confirmation.runtime import build_action_registry
    from data_agent.agent.confirmation.service import ConfirmationService

    sid = _data_clean_session_id(session_id)
    service = ConfirmationService(_proposal_sessions_root(), action_registry=build_action_registry())
    record = service.get(sid, confirmation_id)
    if record.resolution_action != "approve_dataset_transformation":
        raise ValueError("confirmation is not a dataset transformation receipt")
    if record.status != ConfirmationStatus.RESOLVED or record.response != "approve":
        raise ValueError("dataset transformation was not approved")
    proposal = _load_transformation_proposal(str(record.resolution_params.get("artifact_path") or ""))
    expected_data_version = f"dataset:{proposal['dataset_version_id']}:{proposal['source_fingerprint']}"
    expected_spec_version = f"transformation:{proposal['transformation_fingerprint']}"
    if record.resolution_params.get("proposal_id") != proposal.get("proposal_id"):
        raise ValueError("confirmation receipt does not match the proposal")
    if (
        record.data_version != expected_data_version
        or record.spec_version != expected_spec_version
        or record.resolution_params.get("candidate_fingerprint") != proposal.get("candidate_fingerprint")
    ):
        raise ValueError("confirmation receipt does not match the proposal")
    for version in workspace.list_dataset_versions(str(proposal["logical_dataset"])):
        applied_record = dict(version.get("transformation_record") or {})
        if applied_record.get("approval_confirmation_id") == confirmation_id:
            return {
                "status": "applied",
                "dataset": proposal["logical_dataset"],
                "dataset_id": version["dataset_id"],
                "parent_dataset_id": proposal["dataset_version_id"],
                "transformation_record": applied_record,
            }
    active = workspace.get_active_version_info(str(proposal["logical_dataset"]))
    if active is None or active.get("dataset_id") != proposal["dataset_version_id"]:
        raise ValueError("stale active dataset version")
    params = dict(proposal.get("parameters") or {})
    if proposal.get("operation") == "clean_data":
        result = _clean_data_impl(
            str(proposal["logical_dataset"]),
            **params,
            session_id=sid,
            _approved_confirmation_id=confirmation_id,
            _expected_transformation_fingerprint=str(proposal["transformation_fingerprint"]),
            _expected_candidate_fingerprint=str(proposal["candidate_fingerprint"]),
        )
    elif proposal.get("operation") == "apply_type_conversion":
        result = _apply_type_conversion_impl(
            str(proposal["logical_dataset"]),
            **params,
            session_id=sid,
            _approved_confirmation_id=confirmation_id,
            _expected_transformation_fingerprint=str(proposal["transformation_fingerprint"]),
            _expected_candidate_fingerprint=str(proposal["candidate_fingerprint"]),
        )
    else:
        raise ValueError("unsupported transformation proposal operation")
    payload = json.loads(result)
    if payload.get("error"):
        raise ValueError(str(payload["error"]))
    return payload


def _conversion_is_partial(
    original: pd.Series,
    converted: pd.Series,
    target_type: str,
) -> bool:
    non_null = converted[original.notna()]
    if target_type in {"numeric", "numeric_with_suffix", "percentage_to_float"}:
        return not all(isinstance(value, Number) and not isinstance(value, (bool, np.bool_)) for value in non_null)
    if target_type in {"datetime", "date_int_to_datetime"}:
        return not pd.api.types.is_datetime64_any_dtype(converted)
    if target_type == "bool":
        return not all(isinstance(value, (bool, np.bool_)) for value in non_null)
    if target_type == "category":
        return not isinstance(converted.dtype, pd.CategoricalDtype)
    return True


# ── 工具接口 ──────────────────────────────────────────────

@registry.register(
    name="suggest_column_types",
    description="分析数据集各列的类型，给出智能类型转换建议。在 load_data 之后调用。",
)
def suggest_column_types(name: str) -> str:
    df = workspace.get(name)
    if df is None:
        available = list(workspace.list_datasets().keys())
        return json.dumps({"error": f"数据集 '{name}' 不存在。可用: {available}"}, ensure_ascii=False)

    suggestions = []
    for col in df.columns:
        info = infer_column_type(df[col])
        if info["suggested_type"] != "keep":
            suggestions.append(info)

    return json.dumps({
        "dataset": name,
        "columns_analyzed": len(df.columns),
        "suggestions": suggestions,
    }, ensure_ascii=False, indent=2)


@registry.register(
    name="apply_type_conversion",
    description=(
        "在分析副本上执行类型转换。安全且无损的高置信度单列转换可直接应用；"
        "自动、带单位、部分成功或有信息损失的转换需 confirmed=true 后提升为新版本。"
    ),
    schema_overrides={
        "name": {"description": "数据集名称"},
        "column": {"description": "目标列名"},
        "target_type": {"description": "目标类型", "enum": ["datetime", "numeric", "percentage_to_float", "bool", "category", "date_int_to_datetime", "numeric_with_suffix"]},
        "auto": {"type": "boolean", "description": "是否自动应用所有建议转换"},
        "confirmed": {"type": "boolean", "description": "是否已确认需要人工批准的转换"},
    },
)
def _apply_type_conversion_impl(
    name: str,
    column: str = "",
    target_type: str = "",
    auto: bool = False,
    confirmed: bool = False,
    session_id: str = "",
    _approved_confirmation_id: str = "",
    _expected_transformation_fingerprint: str = "",
    _expected_candidate_fingerprint: str = "",
) -> str:
    auto = _coerce_bool_flag(auto)
    confirmed = _coerce_bool_flag(confirmed)
    current = workspace.get(name)
    if current is None:
        return json.dumps({"error": f"数据集 '{name}' 不存在"}, ensure_ascii=False)

    supported_types = {
        "datetime",
        "numeric",
        "percentage_to_float",
        "bool",
        "category",
        "date_int_to_datetime",
        "numeric_with_suffix",
    }
    if not auto and (not column or not target_type):
        return json.dumps({"error": "手动模式需指定 column 和 target_type"}, ensure_ascii=False)
    if not auto and target_type not in supported_types:
        return json.dumps({"error": f"不支持的目标类型: {target_type}"}, ensure_ascii=False)
    if not auto and column not in current.columns:
        return json.dumps({"error": f"列 '{column}' 不存在。可用: {list(current.columns)}"}, ensure_ascii=False)

    try:
        active_info, before = _ensure_versioned_dataset(name, current)
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)

    candidate = before.copy(deep=True)
    operations: list[dict[str, Any]] = []
    affected_columns: list[str] = []
    affected_row_count = 0
    information_loss = False
    conversion_errors: list[dict[str, str]] = []
    requires_confirmation = bool(auto)

    columns_and_targets: list[tuple[str, str, dict[str, Any]]] = []
    if auto:
        for candidate_column in candidate.columns:
            info = infer_column_type(candidate[candidate_column])
            suggested = info["suggested_type"]
            if suggested == "keep" or info["confidence"] == "low" or suggested == "category_maybe":
                continue
            columns_and_targets.append((candidate_column, suggested, info))
    else:
        info = infer_column_type(candidate[column])
        columns_and_targets.append((column, target_type, info))

    for candidate_column, suggested, info in columns_and_targets:
        original = candidate[candidate_column].copy(deep=True)
        try:
            converted = apply_conversion(original.copy(deep=True), suggested)
        except Exception as exc:
            conversion_errors.append({"column": candidate_column, "error": str(exc)})
            requires_confirmation = True
            continue

        new_nulls = max(0, int(converted.isna().sum() - original.isna().sum()))
        cardinality_loss = max(
            0,
            int(original.nunique(dropna=True) - converted.nunique(dropna=True)),
        )
        partial = _conversion_is_partial(original, converted, suggested)
        changed_rows = int((original.astype(str) != converted.astype(str)).sum())
        changed = not original.equals(converted)
        if not changed:
            continue

        candidate[candidate_column] = converted
        operation_requires_confirmation = (
            auto
            or suggested == "numeric_with_suffix"
            or partial
            or new_nulls > 0
            or cardinality_loss > 0
            or info["confidence"] != "high"
            or info["suggested_type"] != suggested
        )
        requires_confirmation = requires_confirmation or operation_requires_confirmation
        operation_loss = new_nulls > 0 or cardinality_loss > 0 or partial
        information_loss = information_loss or operation_loss
        affected_columns.append(candidate_column)
        affected_row_count += changed_rows
        operations.append({
            "column": candidate_column,
            "action": suggested,
            "from": str(original.dtype),
            "to": str(converted.dtype),
            "new_nulls": new_nulls,
            "cardinality_loss": cardinality_loss,
            "partial_conversion": partial,
            "reason": info["reason"],
            "decision_policy": (
                "confirmation_required" if operation_requires_confirmation else "auto_safe"
            ),
        })

    if not operations:
        payload: dict[str, Any] = {
            "status": "no_changes",
            "dataset": name,
            "dataset_id": active_info["dataset_id"],
            "parent_dataset_id": active_info["dataset_id"],
        }
        if auto:
            payload["auto_applied"] = conversion_errors
        else:
            payload["converted"] = None
        if conversion_errors:
            payload["errors"] = conversion_errors
        return json.dumps(payload, ensure_ascii=False, indent=2)

    if conversion_errors:
        requires_confirmation = True
        information_loss = True

    approved = bool(_approved_confirmation_id)
    confirmation_status = (
        "confirmed" if requires_confirmation and approved
        else "pending" if requires_confirmation
        else "not_required"
    )
    before_after_metrics = {
        "rows": {"before": len(before), "after": len(candidate)},
        "missing_values": {
            "before": int(before.isna().sum().sum()),
            "after": int(candidate.isna().sum().sum()),
        },
        "cardinality": {
            item["column"]: {
                "before": int(before[item["column"]].nunique(dropna=True)),
                "after": int(candidate[item["column"]].nunique(dropna=True)),
            }
            for item in operations
        },
    }
    record = _make_transformation_record(
        active_info=active_info,
        logical_name=name,
        operations=operations,
        affected_columns=affected_columns,
        affected_row_count=affected_row_count,
        before_after_metrics=before_after_metrics,
        information_loss=information_loss,
        decision_policy="confirmation_required" if requires_confirmation else "auto_safe",
        confirmation_status=confirmation_status,
    )
    proposal = None
    if requires_confirmation:
        proposal = _material_proposal(
            name=name,
            active_info=active_info,
            operation="apply_type_conversion",
            parameters={"column": column, "target_type": target_type, "auto": auto},
            before=before,
            candidate=candidate,
            affected_columns=affected_columns,
            affected_row_count=affected_row_count,
            information_loss=information_loss,
        )
        if approved and proposal["transformation_fingerprint"] != _expected_transformation_fingerprint:
            return json.dumps({"error": "transformation proposal changed during recomputation"}, ensure_ascii=False)
        if approved and proposal["candidate_fingerprint"] != _expected_candidate_fingerprint:
            return json.dumps({"error": "candidate fingerprint changed during recomputation"}, ensure_ascii=False)
    response: dict[str, Any] = {
        "status": "confirmation_required" if requires_confirmation and not approved else "applied",
        "dataset": name,
        "parent_dataset_id": active_info["dataset_id"],
        "transformation_record": record,
    }
    if auto:
        response["auto_applied"] = operations + conversion_errors
    else:
        response["converted"] = {
            "column": column,
            "to": target_type,
            "new_dtype": str(candidate[column].dtype),
        }
    if conversion_errors:
        response["errors"] = conversion_errors

    if requires_confirmation and not approved:
        response["dataset_id"] = active_info["dataset_id"]
        ref, confirmation_id = _request_transformation_confirmation(
            proposal,
            session_id=_data_clean_session_id(session_id),
            turn_id=f"data_clean:{proposal['proposal_id']}",
        )
        response.pop("transformation_record", None)
        response["proposal_ref"] = ref
        response["confirmation_id"] = confirmation_id
        if confirmed:
            response["error_type"] = "confirmation_receipt_required"
            response["error"] = "confirmed is deprecated; resolve the confirmation receipt instead"
        return json.dumps(response, ensure_ascii=False, indent=2)

    if _approved_confirmation_id:
        record["approval_confirmation_id"] = _approved_confirmation_id
    try:
        promoted = _promote_candidate(name, candidate, active_info, record)
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)
    response["dataset_id"] = promoted["dataset_id"]
    response["transformation_record"] = promoted["transformation_record"]
    return json.dumps(response, ensure_ascii=False, indent=2)


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
    description=(
        "对数据集执行显式清洗：缺失值处理、去重、异常值处理。"
        "missing_strategy: drop（删除行）/ fill_mean / fill_median / fill_mode / fill_constant。"
        "outlier_strategy: mark（标记不处理）/ cap（截断到IQR边界）/ drop（删除行）。"
        "columns 为空则处理所有列，否则只处理指定列（逗号分隔）。"
    ),
    schema_overrides={
        "name": {"description": "数据集名称"},
        "missing_strategy": {"description": "缺失值处理策略", "enum": ["drop", "fill_mean", "fill_median", "fill_mode", "fill_constant"]},
        "outlier_strategy": {"description": "异常值处理策略", "enum": ["mark", "cap", "drop"]},
        "columns": {"description": "目标列，逗号分隔，为空则处理所有列"},
        "fill_value": {"description": "fill_constant 策略的填充值"},
        "confirmed": {"type": "boolean", "description": "是否已确认会改变数据内容的清洗操作"},
    },
)
def _clean_data_impl(
    name: str,
    missing_strategy: str = "drop",
    outlier_strategy: str = "mark",
    columns: str = "",
    fill_value: str = "",
    confirmed: bool = False,
    session_id: str = "",
    _approved_confirmation_id: str = "",
    _expected_transformation_fingerprint: str = "",
    _expected_candidate_fingerprint: str = "",
) -> str:
    confirmed = _coerce_bool_flag(confirmed)
    current = workspace.get(name)
    if current is None:
        available = list(workspace.list_datasets().keys())
        return json.dumps({"error": f"数据集 '{name}' 不存在。可用: {available}"}, ensure_ascii=False)
    if missing_strategy not in _FILL_STRATEGIES:
        return json.dumps({"error": f"不支持的缺失值策略: {missing_strategy}"}, ensure_ascii=False)
    if outlier_strategy not in _OUTLIER_STRATEGIES:
        return json.dumps({"error": f"不支持的异常值策略: {outlier_strategy}"}, ensure_ascii=False)
    if missing_strategy == "fill_constant" and fill_value == "":
        return json.dumps({"error": "fill_constant 策略必须指定 fill_value"}, ensure_ascii=False)

    requested_columns = [item.strip() for item in columns.split(",") if item.strip()]
    target_columns = requested_columns or list(current.columns)
    unknown_columns = [item for item in target_columns if item not in current.columns]
    if unknown_columns:
        return json.dumps({"error": f"列不存在: {unknown_columns}"}, ensure_ascii=False)

    try:
        active_info, before = _ensure_versioned_dataset(name, current)
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)

    candidate = before.copy(deep=True)
    operations: list[dict[str, Any]] = []
    affected_columns: list[str] = []
    affected_row_count = 0

    duplicate_mask = candidate.duplicated(keep="first")
    removed_duplicates = int(duplicate_mask.sum())
    if removed_duplicates:
        candidate = candidate.loc[~duplicate_mask].copy()
        operations.append({
            "action": "deduplicate",
            "removed_rows": removed_duplicates,
            "decision_policy": "confirmation_required",
        })
        affected_columns.extend(str(item) for item in candidate.columns)
        affected_row_count += removed_duplicates

    missing_by_column = {
        item: int(candidate[item].isna().sum())
        for item in target_columns
    }
    columns_with_missing = [item for item, count in missing_by_column.items() if count > 0]
    if columns_with_missing:
        if missing_strategy == "drop":
            missing_row_mask = candidate[target_columns].isna().any(axis=1)
            removed_rows = int(missing_row_mask.sum())
            if removed_rows:
                candidate = candidate.loc[~missing_row_mask].copy()
                operations.append({
                    "action": "missing_drop",
                    "removed_rows": removed_rows,
                    "columns_affected": {
                        item: missing_by_column[item] for item in columns_with_missing
                    },
                    "decision_policy": "confirmation_required",
                })
                affected_columns.extend(columns_with_missing)
                affected_row_count += removed_rows
        else:
            filled_by_column: dict[str, int] = {}
            for target_column in columns_with_missing:
                series = candidate[target_column]
                replacement: Any = None
                has_replacement = False
                if missing_strategy == "fill_mean" and pd.api.types.is_numeric_dtype(series):
                    replacement = series.mean()
                    has_replacement = pd.notna(replacement)
                elif missing_strategy == "fill_median" and pd.api.types.is_numeric_dtype(series):
                    replacement = series.median()
                    has_replacement = pd.notna(replacement)
                elif missing_strategy == "fill_mode":
                    mode = series.mode()
                    if not mode.empty:
                        replacement = mode.iloc[0]
                        has_replacement = True
                elif missing_strategy == "fill_constant":
                    if pd.api.types.is_numeric_dtype(series):
                        try:
                            replacement = float(fill_value)
                        except ValueError:
                            replacement = fill_value
                    else:
                        replacement = fill_value
                    has_replacement = True

                if not has_replacement:
                    continue
                missing_before_fill = int(series.isna().sum())
                candidate[target_column] = series.fillna(replacement)
                filled = missing_before_fill - int(candidate[target_column].isna().sum())
                if filled:
                    filled_by_column[target_column] = filled

            if filled_by_column:
                total_filled = sum(filled_by_column.values())
                operation: dict[str, Any] = {
                    "action": f"missing_{missing_strategy}",
                    "filled": total_filled,
                    "columns_affected": filled_by_column,
                    "decision_policy": "confirmation_required",
                }
                if missing_strategy == "fill_constant":
                    operation["value"] = fill_value
                operations.append(operation)
                affected_columns.extend(filled_by_column)
                affected_row_count += total_filled

    outlier_details: list[dict[str, Any]] = []
    numeric_columns = [
        item
        for item in target_columns
        if pd.api.types.is_numeric_dtype(candidate[item])
    ]
    for target_column in numeric_columns:
        q1 = candidate[target_column].quantile(0.25)
        q3 = candidate[target_column].quantile(0.75)
        iqr = q3 - q1
        if pd.isna(iqr) or iqr == 0:
            continue
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr
        outlier_mask = (candidate[target_column] < lower) | (candidate[target_column] > upper)
        outlier_count = int(outlier_mask.sum())
        if not outlier_count:
            continue

        if outlier_strategy == "cap":
            candidate[target_column] = candidate[target_column].clip(lower=lower, upper=upper)
            outlier_details.append({
                "column": target_column,
                "capped": outlier_count,
                "range": [float(lower), float(upper)],
            })
            affected_columns.append(target_column)
            affected_row_count += outlier_count
        elif outlier_strategy == "drop":
            candidate = candidate.loc[~outlier_mask].copy()
            outlier_details.append({"column": target_column, "removed": outlier_count})
            affected_columns.append(target_column)
            affected_row_count += outlier_count
        else:
            outlier_details.append({
                "column": target_column,
                "marked": outlier_count,
                "range": [float(lower), float(upper)],
            })
            affected_columns.append(target_column)
            affected_row_count += outlier_count

    if outlier_details:
        operations.append({
            "action": f"outlier_{outlier_strategy}",
            "details": outlier_details,
            "decision_policy": (
                "not_required" if outlier_strategy == "mark" else "confirmation_required"
            ),
        })

    material_actions = {
        "deduplicate",
        "missing_drop",
        "missing_fill_mean",
        "missing_fill_median",
        "missing_fill_mode",
        "missing_fill_constant",
        "outlier_cap",
        "outlier_drop",
    }
    material = any(item["action"] in material_actions for item in operations)
    approved = bool(_approved_confirmation_id)
    confirmation_status = "confirmed" if material and approved else "pending" if material else "not_required"
    metrics = {
        "rows": {"before": len(before), "after": len(candidate)},
        "missing_values": {
            "before": int(before.isna().sum().sum()),
            "after": int(candidate.isna().sum().sum()),
        },
        "missing_by_column": {
            "before": {item: int(value) for item, value in before.isna().sum().items()},
            "after": {item: int(value) for item, value in candidate.isna().sum().items()},
        },
    }
    record = _make_transformation_record(
        active_info=active_info,
        logical_name=name,
        operations=operations,
        affected_columns=affected_columns,
        affected_row_count=affected_row_count,
        before_after_metrics=metrics,
        information_loss=material,
        decision_policy="confirmation_required" if material else "auto_safe" if operations else "none",
        confirmation_status=confirmation_status,
    )
    proposal = None
    if material:
        proposal = _material_proposal(
            name=name,
            active_info=active_info,
            operation="clean_data",
            parameters={
                "missing_strategy": missing_strategy,
                "outlier_strategy": outlier_strategy,
                "columns": columns,
                "fill_value": fill_value,
            },
            before=before,
            candidate=candidate,
            affected_columns=affected_columns,
            affected_row_count=affected_row_count,
            information_loss=True,
        )
        if approved and proposal["transformation_fingerprint"] != _expected_transformation_fingerprint:
            return json.dumps({"error": "transformation proposal changed during recomputation"}, ensure_ascii=False)
        if approved and proposal["candidate_fingerprint"] != _expected_candidate_fingerprint:
            return json.dumps({"error": "candidate fingerprint changed during recomputation"}, ensure_ascii=False)
    response: dict[str, Any] = {
        "status": "confirmation_required" if material and not approved else "applied",
        "dataset": name,
        "dataset_id": active_info["dataset_id"],
        "parent_dataset_id": active_info["dataset_id"],
        "transformation_record": record,
        "original_rows": len(before),
        "final_rows": len(candidate),
        "rows_removed": len(before) - len(candidate),
        "actions": operations,
    }

    if material and not approved:
        ref, confirmation_id = _request_transformation_confirmation(
            proposal,
            session_id=_data_clean_session_id(session_id),
            turn_id=f"data_clean:{proposal['proposal_id']}",
        )
        response.pop("transformation_record", None)
        response["proposal_ref"] = ref
        response["confirmation_id"] = confirmation_id
        if confirmed:
            response["error_type"] = "confirmation_receipt_required"
            response["error"] = "confirmed is deprecated; resolve the confirmation receipt instead"
        return json.dumps(response, ensure_ascii=False, indent=2)
    if not operations:
        response["status"] = "no_changes"
        return json.dumps(response, ensure_ascii=False, indent=2)
    if candidate.equals(before):
        return json.dumps(response, ensure_ascii=False, indent=2)

    if _approved_confirmation_id:
        record["approval_confirmation_id"] = _approved_confirmation_id
    try:
        promoted = _promote_candidate(name, candidate, active_info, record)
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)
    response["dataset_id"] = promoted["dataset_id"]
    response["transformation_record"] = promoted["transformation_record"]
    return json.dumps(response, ensure_ascii=False, indent=2)


def apply_type_conversion(
    name: str,
    column: str = "",
    target_type: str = "",
    auto: bool = False,
    confirmed: bool = False,
) -> str:
    """Public tool entry point; a Boolean can never carry approval authority."""
    return _apply_type_conversion_impl(
        name,
        column=column,
        target_type=target_type,
        auto=auto,
        confirmed=confirmed,
    )


def clean_data(
    name: str,
    missing_strategy: str = "drop",
    outlier_strategy: str = "mark",
    columns: str = "",
    fill_value: str = "",
    confirmed: bool = False,
) -> str:
    """Public tool entry point; apply receipt-bound proposals separately."""
    return _clean_data_impl(
        name,
        missing_strategy=missing_strategy,
        outlier_strategy=outlier_strategy,
        columns=columns,
        fill_value=fill_value,
        confirmed=confirmed,
    )


# The decorators above register the implementations during module import. Keep
# their public schemas and callable surfaces narrow even though the internal
# recomputation functions accept receipt-only arguments.
for _tool_name, _public in {
    "apply_type_conversion": apply_type_conversion,
    "clean_data": clean_data,
}.items():
    _definition = registry._tools[_tool_name]
    _definition.func = _public
    for _private_name in ("session_id", "_approved_confirmation_id", "_expected_transformation_fingerprint", "_expected_candidate_fingerprint"):
        _definition.parameters["properties"].pop(_private_name, None)
