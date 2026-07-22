"""Deterministic builders for trust workflow analysis contracts."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Mapping

import pandas as pd

from data_agent.agent.analysis_requirements import requirement_ids_for_route


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


def _comparison_profile(df: pd.DataFrame, roles: dict[str, list[str]]) -> dict[str, Any]:
    relevant_columns = [
        column
        for role in ("metrics", "rate_metrics", "dimensions")
        for column in roles.get(role, [])
        if column in df.columns
    ]
    missingness = {
        column: {
            "missing_count": int(df[column].isna().sum()),
            "missing_rate": float(df[column].isna().mean()) if len(df) else 0.0,
        }
        for column in relevant_columns
    }
    group_sizes: dict[str, dict[str, Any]] = {}
    for column in roles.get("dimensions", []):
        if column not in df.columns:
            continue
        counts = df.groupby(column, dropna=False).size()
        if counts.empty:
            continue
        group_sizes[column] = {
            "group_count": int(len(counts)),
            "minimum": int(counts.min()),
            "maximum": int(counts.max()),
            "median": float(counts.median()),
        }
    return {
        "row_count": int(len(df)),
        "missingness": missingness,
        "group_sizes": group_sizes,
    }


def _time_frequency(dates: pd.DatetimeIndex) -> tuple[str, int]:
    if len(dates) < 2:
        return "not_estimable", 0

    month_ordinals = dates.year * 12 + dates.month
    month_deltas = pd.Series(month_ordinals[1:] - month_ordinals[:-1])
    day_deltas = pd.Series((dates[1:] - dates[:-1]).days)

    if (
        len(dates) >= 2
        and len({(value.month, value.day) for value in dates}) == 1
        and bool((month_deltas >= 12).all())
        and bool((month_deltas % 12 == 0).all())
    ):
        expected = int((dates[-1].year - dates[0].year) + 1)
        return "yearly", max(0, expected - len(dates))
    calendar_month_aligned = bool(
        dates.is_month_start.all()
        or dates.is_month_end.all()
        or len(set(int(value) for value in dates.day)) == 1
    )
    if (
        calendar_month_aligned
        and bool((month_deltas >= 3).all())
        and bool((month_deltas % 3 == 0).all())
    ):
        expected = int((month_ordinals[-1] - month_ordinals[0]) // 3 + 1)
        return "quarterly", max(0, expected - len(dates))
    if calendar_month_aligned and bool((month_deltas >= 1).all()):
        expected = int(month_ordinals[-1] - month_ordinals[0] + 1)
        return "monthly", max(0, expected - len(dates))
    if bool((day_deltas >= 7).all()) and bool((day_deltas % 7 == 0).all()):
        expected = int(day_deltas.sum() // 7 + 1)
        return "weekly", max(0, expected - len(dates))
    if bool((dates.weekday < 5).all()):
        expected = len(pd.bdate_range(dates[0].normalize(), dates[-1].normalize()))
        if expected >= len(dates):
            return "business_daily", max(0, expected - len(dates))
    if bool((day_deltas == 1).all()):
        return "daily", 0

    normalized = dates.normalize()
    expected = int((normalized[-1] - normalized[0]).days + 1)
    return "irregular", max(0, expected - len(dates))


_SEASONAL_PERIOD_OBSERVATIONS = {
    "annual": {
        "daily": 365,
        "business_daily": 260,
        "weekly": 52,
        "monthly": 12,
        "quarterly": 4,
    },
    "quarterly": {
        "daily": 91,
        "business_daily": 65,
        "weekly": 13,
        "monthly": 3,
    },
    "monthly": {
        "daily": 30,
        "business_daily": 22,
        "weekly": 4,
    },
    "weekly": {
        "daily": 7,
        "business_daily": 5,
    },
}


def _seasonality_profile(
    frequency: str,
    point_count: int,
    missing_interval_count: int,
    seasonality_period: str,
) -> dict[str, Any]:
    period_observations = _SEASONAL_PERIOD_OBSERVATIONS.get(
        seasonality_period,
        {},
    ).get(frequency)
    minimum_cycles = 2
    period_label = seasonality_period.capitalize()
    if period_observations is None:
        return {
            "period_observations": 0,
            "minimum_complete_cycles": minimum_cycles,
            "complete_cycles": 0,
            "status": "not_estimable",
            "reason": (
                f"{period_label} seasonality requires a regular, recognized time frequency "
                "with finer resolution than the requested cycle."
            ),
        }

    complete_cycles = point_count // period_observations
    required_observations = minimum_cycles * period_observations
    frequency_label = frequency
    if missing_interval_count:
        status = "not_estimable"
        reason = (
            f"{period_label} seasonality is not estimable from a series with "
            f"{missing_interval_count} missing {frequency_label} intervals."
        )
    elif complete_cycles < minimum_cycles:
        status = "not_estimable"
        reason = (
            f"{period_label} seasonality requires at least "
            f"{minimum_cycles} complete cycles ({required_observations} {frequency_label} observations)."
        )
    elif complete_cycles == minimum_cycles:
        status = "estimable_with_limits"
        reason = (
            f"Only {complete_cycles} complete {seasonality_period} cycles are available; "
            "seasonality estimates require explicit uncertainty and limitations."
        )
    else:
        status = "estimable"
        reason = (
            f"At least 3 complete {seasonality_period} cycles are available without missing intervals."
        )
    return {
        "period_observations": period_observations,
        "minimum_complete_cycles": minimum_cycles,
        "complete_cycles": complete_cycles,
        "status": status,
        "reason": reason,
    }


def _time_series_profile(df: pd.DataFrame, roles: dict[str, list[str]]) -> dict[str, Any]:
    date_columns = [column for column in roles.get("date", []) if column in df.columns]
    if not date_columns:
        return {
            "date_column": "",
            "point_count": 0,
            "duplicate_timestamp_count": 0,
            "frequency": "not_estimable",
            "missing_interval_count": 0,
            "regular": False,
            "seasonality": {
                period: _seasonality_profile("not_estimable", 0, 0, period)
                for period in _SEASONAL_PERIOD_OBSERVATIONS
            },
        }

    column = date_columns[0]
    converted = pd.to_datetime(df[column], errors="coerce")
    non_null = converted.dropna()
    dates = pd.DatetimeIndex(non_null.unique()).sort_values()
    frequency, missing_interval_count = _time_frequency(dates)
    return {
        "date_column": column,
        "point_count": int(len(dates)),
        "duplicate_timestamp_count": int(len(non_null) - len(dates)),
        "frequency": frequency,
        "missing_interval_count": int(missing_interval_count),
        "regular": bool(frequency != "irregular" and missing_interval_count == 0),
        "seasonality": {
            period: _seasonality_profile(
                frequency,
                int(len(dates)),
                int(missing_interval_count),
                period,
            )
            for period in _SEASONAL_PERIOD_OBSERVATIONS
        },
    }


def build_time_series_analysis_profile(
    df: pd.DataFrame,
    date_column: str,
) -> dict[str, Any]:
    """Build the canonical computable time-series profile for an analysis tool."""

    return _time_series_profile(df, {"date": [date_column]})


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
        "analysis_profiles": {
            "comparison": _comparison_profile(df, roles),
            "time_series": _time_series_profile(df, roles),
            "time_series_by_column": {
                column: _time_series_profile(df, {"date": [column]})
                for column in roles.get("date", [])
                if column in df.columns
            },
        },
        "cleaning_log_ids": list(cleaning_log_ids or []),
        "preview_digest_id": str(preview_digest_id or ""),
        "detail_path": str(detail_path or ""),
    }
    return {"id": _stable_id("duc", dataset, payload), **payload}


def route_evidence_requirements(route: Mapping[str, Any]) -> list[str]:
    """Read-only compatibility alias for the canonical route projection."""

    return requirement_ids_for_route(dict(route))


def _route_template(direction: str) -> dict[str, Any]:
    templates = {
        "trend": {
            "tool_chain": ["analyze_time_series", "record_evidence_record"],
            "limitations": ["Descriptive trend only unless supported by experimental evidence"],
            "budget_level": "light",
        },
        "period_compare": {
            "tool_chain": ["compare_periods", "record_evidence_record"],
            "limitations": ["Comparison quality depends on period comparability and seasonality"],
            "budget_level": "standard",
        },
        "dimension_decomposition": {
            "tool_chain": ["contribute_decomposition", "record_evidence_record"],
            "limitations": ["Contribution is descriptive and does not prove causality"],
            "budget_level": "standard",
        },
        "rate_analysis": {
            "tool_chain": ["calculate_metrics", "record_evidence_record"],
            "limitations": ["Rate interpretation depends on stable numerator and denominator definitions"],
            "budget_level": "standard",
        },
        "correlation": {
            "tool_chain": ["correlation_analysis", "record_evidence_record"],
            "limitations": ["Correlation does not imply causation"],
            "budget_level": "standard",
        },
        "cohort": {
            "tool_chain": ["cohort_analysis", "record_evidence_record"],
            "limitations": ["Requires stable user IDs and event history"],
            "budget_level": "deep",
        },
        "funnel": {
            "tool_chain": ["funnel_analysis", "record_evidence_record"],
            "limitations": ["Requires valid event steps or aggregate funnel columns"],
            "budget_level": "deep",
        },
    }
    return templates.get(direction, {
        "tool_chain": ["record_evidence_record"],
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
            "evidence_requirements": requirement_ids_for_route({"direction": str(direction)}),
            "limitations": list(template["limitations"]),
            "budget_level": str(template["budget_level"]),
        }
        if str(direction) in {"trend", "period_compare"}:
            time_profile = (
                contract.get("analysis_profiles", {}).get("time_series", {})
                if isinstance(contract.get("analysis_profiles"), dict)
                else {}
            )
            if int(time_profile.get("duplicate_timestamp_count") or 0) > 0:
                payload.update({
                    "estimand_requires_confirmation": True,
                    "estimand_options": [
                        {
                            "label": "按时间点求和",
                            "value": "sum",
                            "description": "同一时间点多行先求和，适合流量和金额总量。",
                        },
                        {
                            "label": "按时间点求均值",
                            "value": "mean",
                            "description": "同一时间点多行先求均值，适合典型水平。",
                        },
                    ],
                })
        proposals.append({"id": _stable_id("route", dataset, payload), **payload})

    preferred = ["trend", "period_compare", "dimension_decomposition"]
    return sorted(
        proposals,
        key=lambda item: (preferred.index(item["direction"]) if item["direction"] in preferred else len(preferred), item["direction"]),
    )
