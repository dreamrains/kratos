"""Deterministic builders for trust workflow analysis contracts."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Mapping

import pandas as pd


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, set):
        safe_values = [_json_safe(v) for v in value]
        return sorted(safe_values, key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True))
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (pd.Series, pd.Index)):
        return [_json_safe(v) for v in value.tolist()]
    if hasattr(value, "tolist"):
        listed = value.tolist()
        if listed is not value:
            return _json_safe(listed)
    if hasattr(value, "item"):
        try:
            return _json_safe(value.item())
        except (TypeError, ValueError):
            pass
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _stable_id(prefix: str, dataset: str, payload: Any) -> str:
    safe_payload = json.dumps(_json_safe(payload), ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha1(safe_payload.encode("utf-8")).hexdigest()[:8]
    return f"{prefix}_{dataset}_{digest}" if dataset else f"{prefix}_{digest}"


def _column_names(items: Any) -> list[str]:
    if items is None:
        return []
    names: list[str] = []
    for item in _json_safe(items):
        if isinstance(item, dict):
            value = item.get("column") or item.get("name")
        else:
            value = item
        if value not in (None, ""):
            names.append(str(value))
    return names


def _cleaning_decision_type(item: dict[str, Any], action: str) -> str:
    if item.get("blocked") or action in {"blocked", "cannot_parse", "invalid_schema"}:
        return "blocked"
    if (
        item.get("requires_confirmation")
        or item.get("decision_policy") == "confirmation_required"
        or action in {"category_maybe", "ambiguous_date", "ambiguous_numeric"}
    ):
        return "needs_confirmation"
    if action in {"datetime", "date_int_to_datetime", "percentage_to_float", "bool", "strip_whitespace"}:
        return "safe_auto"
    if action in {"numeric", "numeric_with_suffix", "object_to_numeric", "fill_missing", "deduplicate"}:
        return "notify_auto"
    return "needs_confirmation"


def _cleaning_impact(action: str, decision_type: str) -> str:
    impacts = {
        "datetime": "Enables time-aware analysis",
        "date_int_to_datetime": "Enables time-aware analysis",
        "percentage_to_float": "Enables rate analysis",
        "bool": "Enables binary segmentation",
        "strip_whitespace": "Reduces category fragmentation",
        "numeric": "Enables numeric metric analysis",
        "numeric_with_suffix": "Enables numeric metric analysis after unit parsing",
        "object_to_numeric": "Enables numeric metric analysis after coercion",
        "fill_missing": "May change aggregate values or sample coverage",
        "deduplicate": "May change row counts and denominator logic",
        "category_maybe": "Requires confirmation before treating as a dimension",
        "ambiguous_date": "Requires confirmation before time-aware analysis",
        "ambiguous_numeric": "Requires confirmation before metric analysis",
    }
    if decision_type == "blocked":
        return "Blocks dependent analysis until the data issue is resolved"
    return impacts.get(action, "May affect downstream analysis interpretation")


def build_cleaning_decision_log(
    dataset: str,
    applied: list[dict[str, Any]] | None,
    needs_confirm: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Build a deterministic record of automatic and pending cleaning choices."""

    decisions: list[dict[str, Any]] = []
    summary = {"safe_auto": 0, "notify_auto": 0, "needs_confirmation": 0, "blocked": 0}

    for item in applied or []:
        action = str(item.get("action") or "")
        decision_type = _cleaning_decision_type(item, action)
        summary[decision_type] += 1
        decisions.append({
            "column": str(item.get("column") or ""),
            "decision_type": decision_type,
            "from_dtype": _json_safe(item.get("from")),
            "to_dtype": _json_safe(item.get("to")),
            "action": action,
            "reason": str(item.get("reason") or ""),
            "impact": _cleaning_impact(action, decision_type),
        })

    for item in needs_confirm or []:
        action = str(item.get("suggested_type") or item.get("action") or "")
        decision_type = _cleaning_decision_type(item, action)
        summary[decision_type] += 1
        decisions.append({
            "column": str(item.get("column") or ""),
            "decision_type": decision_type,
            "from_dtype": _json_safe(item.get("current_dtype")),
            "suggested_type": action or "needs_confirmation",
            "reason": str(item.get("reason") or ""),
            "sample": _json_safe(item["sample"] if "sample" in item else []),
            "impact": _cleaning_impact(action, decision_type),
        })

    payload = {"dataset": dataset, "decisions": decisions, "summary": summary}
    return {"id": _stable_id("clean", dataset, payload), **payload}


def build_preview_digest(dataset: str, df: pd.DataFrame, max_rows: int = 5) -> dict[str, Any]:
    """Create a compact preview that survives prompt compression."""

    bounded_rows = max(0, int(max_rows))
    sample = df.head(bounded_rows)
    column_examples: dict[str, list[Any]] = {}
    notable_patterns: list[str] = []
    risks: list[str] = []

    for column in df.columns:
        name = str(column)
        series = df[column]
        examples = [_json_safe(value) for value in series.dropna().head(3).tolist()]
        column_examples[name] = examples

        missing_count = int(series.isna().sum())
        missing_rate = missing_count / len(df) if len(df) else 0
        unique_count = int(series.nunique(dropna=True))
        notable_patterns.append(f"{name}: {unique_count} distinct values")

        if missing_count:
            risks.append(f"{name}: {missing_count} missing values ({missing_rate:.1%})")
        if len(df) and unique_count == len(df):
            notable_patterns.append(f"{name}: unique for every row")
        if unique_count == 1 and len(df) > 1:
            risks.append(f"{name}: constant value limits segmentation")

    sample_rows = [
        {str(key): _json_safe(value) for key, value in row.items()}
        for row in sample.to_dict(orient="records")
    ]
    payload = {
        "dataset": dataset,
        "row_count": int(len(df)),
        "column_count": int(len(df.columns)),
        "sample_rows_count": int(len(sample_rows)),
        "sample_rows": sample_rows,
        "column_examples": column_examples,
        "notable_patterns": notable_patterns[:12],
        "risks": risks[:12],
    }
    return {"id": _stable_id("preview", dataset, payload), **payload}


def _quality_status(quality: dict[str, Any]) -> str:
    if quality.get("block_issues"):
        return "blocked"
    if quality.get("warnings"):
        return "ready_with_warnings"
    score = quality.get("quality_score")
    if isinstance(score, (int, float)) and score < 70:
        return "ready_with_warnings"
    return "ready"


def _field_roles(classified: dict[str, Any]) -> dict[str, list[str]]:
    return {
        "date": _column_names(classified.get("time_columns")),
        "metrics": _column_names(classified.get("key_metrics")),
        "rate_metrics": _column_names(classified.get("rate_metrics")),
        "dimensions": _column_names(classified.get("dimensions")),
        "ids": _column_names(classified.get("id_columns")),
        "text": _column_names(classified.get("other_text")),
        "unknown": _column_names(classified.get("unknown") or classified.get("other_columns")),
    }


def _supported_analyses(roles: dict[str, list[str]], signals: dict[str, Any]) -> list[str]:
    supported: list[str] = []
    has_time = bool(signals.get("has_time") or roles["date"])
    has_dimensions = bool(signals.get("has_dimensions") or roles["dimensions"])
    has_ids = bool(signals.get("has_ids") or roles["ids"])
    has_rates = bool(signals.get("has_rates") or roles["rate_metrics"])
    metric_count = int(signals.get("metric_count") or len(roles["metrics"]) + len(roles["rate_metrics"]))

    if has_time and metric_count:
        supported.extend(["trend", "period_compare"])
    if has_dimensions and metric_count:
        supported.append("dimension_decomposition")
    if has_rates:
        supported.append("rate_analysis")
    if has_ids:
        supported.extend(["cohort", "funnel"])
    if metric_count >= 2:
        supported.append("correlation")
    return sorted(set(supported))


def _unsupported_analyses(roles: dict[str, list[str]], signals: dict[str, Any], grain: str) -> list[dict[str, str]]:
    unsupported: list[dict[str, str]] = []
    has_time = bool(signals.get("has_time") or roles["date"])
    has_ids = bool(signals.get("has_ids") or roles["ids"])
    metric_count = int(signals.get("metric_count") or len(roles["metrics"]) + len(roles["rate_metrics"]))

    if not has_time:
        unsupported.append({"type": "trend", "reason": "No time column was identified"})
        unsupported.append({"type": "period_compare", "reason": "No time column was identified"})
    if not roles["dimensions"]:
        unsupported.append({"type": "dimension_decomposition", "reason": "No dimension column was identified"})
    if not metric_count:
        unsupported.append({"type": "metric_analysis", "reason": "No metric column was identified"})
    is_aggregate = "aggregate" in grain
    if not has_ids or is_aggregate:
        if not has_ids and is_aggregate:
            reason = "Data is aggregate grain and missing user or entity id columns"
        elif not has_ids:
            reason = "Data is missing user or entity id columns"
        else:
            reason = "Data is aggregate grain, so row-level user retention cannot be reconstructed"
        unsupported.append({
            "type": "user_level_retention",
            "reason": reason,
        })
    return unsupported


def build_dataset_understanding_contract(
    dataset: str,
    df: pd.DataFrame,
    quality: dict[str, Any],
    interpretation_data: dict[str, Any],
    cleaning_log_ids: list[str],
    preview_digest_id: str,
    detail_path: str = "",
) -> dict[str, Any]:
    """Summarize data readiness and valid analysis directions."""

    classified = dict(interpretation_data.get("columns_classified") or {})
    signals = dict(interpretation_data.get("analysis_signals") or {})
    roles = _field_roles(classified)
    grain = str(interpretation_data.get("grain") or "unknown")
    quality_summary = {
        "status": _quality_status(quality),
        "score": _json_safe(quality.get("quality_score")),
        "block_issues": _json_safe(quality.get("block_issues") or []),
        "warnings": _json_safe(quality.get("warnings") or []),
    }
    payload = {
        "dataset": dataset,
        "row_count": int(len(df)),
        "column_count": int(len(df.columns)),
        "grain": grain,
        "field_roles": roles,
        "quality": quality_summary,
        "time_range": _json_safe(interpretation_data.get("time_range") or {}),
        "supported_analyses": _supported_analyses(roles, signals),
        "unsupported_analyses": _unsupported_analyses(roles, signals, grain),
        "cleaning_log_ids": list(cleaning_log_ids or []),
        "preview_digest_id": str(preview_digest_id or ""),
        "detail_path": str(detail_path or ""),
    }
    return {"id": _stable_id("duc", dataset, payload), **payload}


def route_evidence_requirements(route: Mapping[str, Any]) -> list[str]:
    """Read canonical route requirements with legacy proposal compatibility."""

    value = route.get("evidence_requirements")
    if not isinstance(value, list):
        value = route.get("expected_evidence")
    return [str(item).strip() for item in (value or []) if str(item).strip()]


def _route_template(direction: str) -> dict[str, Any]:
    templates = {
        "trend": {
            "tool_chain": ["analyze_time_series", "record_evidence_record"],
            "evidence_requirements": ["time_scope", "sample_size", "trend_statistics", "limitations"],
            "limitations": ["Descriptive trend only unless supported by experimental evidence"],
            "budget_level": "light",
        },
        "period_compare": {
            "tool_chain": ["compare_periods", "record_evidence_record"],
            "evidence_requirements": ["period_definition", "period_comparability", "metric_delta", "limitations"],
            "limitations": ["Comparison quality depends on period comparability and seasonality"],
            "budget_level": "standard",
        },
        "dimension_decomposition": {
            "tool_chain": ["contribute_decomposition", "record_evidence_record"],
            "evidence_requirements": ["dimension_scope", "contribution_table", "metric_delta", "limitations"],
            "limitations": ["Contribution is descriptive and does not prove causality"],
            "budget_level": "standard",
        },
        "rate_analysis": {
            "tool_chain": ["calculate_metrics", "record_evidence_record"],
            "evidence_requirements": ["rate_definition", "denominator", "sample_size", "limitations"],
            "limitations": ["Rate interpretation depends on stable numerator and denominator definitions"],
            "budget_level": "standard",
        },
        "correlation": {
            "tool_chain": ["correlation_analysis", "record_evidence_record"],
            "evidence_requirements": ["variables", "correlation_method", "sample_size", "limitations"],
            "limitations": ["Correlation does not imply causation"],
            "budget_level": "standard",
        },
        "cohort": {
            "tool_chain": ["cohort_analysis", "record_evidence_record"],
            "evidence_requirements": ["id_scope", "cohort_definition", "retention_metric", "limitations"],
            "limitations": ["Requires stable user IDs and event history"],
            "budget_level": "deep",
        },
        "funnel": {
            "tool_chain": ["funnel_analysis", "record_evidence_record"],
            "evidence_requirements": ["step_definition", "denominator", "conversion_rates", "limitations"],
            "limitations": ["Requires valid event steps or aggregate funnel columns"],
            "budget_level": "deep",
        },
    }
    return templates.get(direction, {
        "tool_chain": ["record_evidence_record"],
        "evidence_requirements": ["method", "sample_size", "limitations"],
        "limitations": ["Analysis route requires additional scoping"],
        "budget_level": "standard",
    })


def build_route_proposals(contract: dict[str, Any]) -> list[dict[str, Any]]:
    """Create evidence-aware analysis routes from a dataset contract."""

    dataset = str(contract.get("dataset") or "")
    contract_id = str(contract.get("id") or "")
    roles = dict(contract.get("field_roles") or {})
    proposals: list[dict[str, Any]] = []

    for direction in contract.get("supported_analyses") or []:
        template = _route_template(str(direction))
        payload = {
            "dataset": dataset,
            "dataset_contract_id": contract_id,
            "direction": str(direction),
            "field_roles": _json_safe(roles),
            "tool_chain": list(template["tool_chain"]),
            "evidence_requirements": list(template["evidence_requirements"]),
            "limitations": list(template["limitations"]),
            "budget_level": str(template["budget_level"]),
        }
        proposals.append({"id": _stable_id("route", dataset, payload), **payload})

    preferred = ["trend", "period_compare", "dimension_decomposition"]
    return sorted(
        proposals,
        key=lambda item: (preferred.index(item["direction"]) if item["direction"] in preferred else len(preferred), item["direction"]),
    )
