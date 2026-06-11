"""Deterministic policy for deciding when user confirmation is required."""

from __future__ import annotations

import re
from typing import Any


BLOCKED_SURFACES_ALL = ["direct_recommendation", "analysis_execution", "report_generation"]
BLOCKED_SURFACES_EXECUTION = ["analysis_execution", "report_generation"]

_CONSULTING_INTENTS = {"simple_response", "knowledge_qa", "analysis_consultation", "result_followup"}
_PENDING_RELATIONSHIP_STATUSES = {"possibly_linked", "independent", "insufficient_preview"}
_LATEST_ONLY_PHRASES = (
    "latest only",
    "latest upload only",
    "only analyze latest",
    "only analyze the latest",
    "only latest",
    "only use latest",
    "only use the latest",
    "only the latest",
    "use latest only",
    "exclude historical",
    "exclude history",
    "ignore historical",
    "ignore history",
    "no historical",
    "no history",
    "not historical",
    "without historical",
    "without history",
    "\u53ea\u5206\u6790\u6700\u65b0",
    "\u53ea\u5206\u6790\u65b0\u6587\u4ef6",
    "\u53ea\u770b\u6700\u65b0",
    "\u4ec5\u5206\u6790\u6700\u65b0",
    "\u4ec5\u4f7f\u7528\u6700\u65b0",
    "\u4e0d\u770b\u5386\u53f2",
    "\u4e0d\u8981\u5386\u53f2",
    "\u6392\u9664\u5386\u53f2",
)
_LATEST_ONLY_RELATIONSHIP_SCOPE_TERMS = (
    "compare",
    "comparison",
    "historical",
    "history",
    "previous",
    "with history",
    "merge",
    "join",
    "combine",
    "relate",
    "relationship",
    "对比",
    "比较",
    "历史",
    "之前",
    "关联",
    "结合",
    "合并",
    "一起",
)
_HIGH_RISK_KEYWORDS = (
    "predict",
    "forecast",
    "causal",
    "causality",
    "effect",
    "experiment",
    "ab test",
    "a/b",
    "uplift",
    "roi",
    "simulate",
    "预测",
    "因果",
    "实验",
    "效果",
    "归因",
)
_PERIOD_KEYWORDS = ("compare", "comparison", "period", "环比", "同比", "对比", "比较", "前后")
_WINDOW_KEYWORDS = (
    "today",
    "yesterday",
    "week",
    "month",
    "quarter",
    "year",
    "last",
    "previous",
    "before",
    "after",
    "daily",
    "weekly",
    "monthly",
    "天",
    "周",
    "月",
    "季度",
    "年",
    "最近",
    "之前",
    "之后",
    "前",
    "后",
)
_ROUTE_KEYWORDS = {
    "trend": ("trend", "time series", "趋势", "走势"),
    "period_compare": _PERIOD_KEYWORDS,
    "dimension_decomposition": ("segment", "dimension", "breakdown", "driver", "归因", "分维", "拆解"),
    "cohort": ("cohort", "retention", "留存", "复购"),
    "funnel": ("funnel", "conversion", "漏斗", "转化"),
}


def detect_question_need(user_input: str, intent: Any, state: Any) -> dict[str, Any]:
    """Return a compact gate describing whether the system must ask the user.

    The detector is intentionally conservative about blocking. It only returns
    a hard question when the answer can change the route, method, metric scope,
    time window, or conclusion quality.
    """
    if state is None or _intent_type(intent) in _CONSULTING_INTENTS:
        return empty_question_need()

    text = (user_input or "").lower()
    relationship_gate = _pending_file_relationship_gate(text, state)
    if relationship_gate:
        return relationship_gate

    routes = _scoped_routes(state)

    if _is_vague_route_request(intent) and len(routes) > 1:
        return _hard_gate(
            "route_selection",
            "Multiple data-supported analysis routes are available and the user goal is vague.",
            "请先确认本次最想分析的方向，系统会基于你的选择生成最终推荐。",
            options=_route_options(routes),
            blocking_surfaces=BLOCKED_SURFACES_ALL,
            affected_routes=[_route_direction(route) for route in routes],
        )

    route = _infer_route(text, routes)
    if route:
        risk_fields = _required_field_risks(route, _list_attr(state, "cleaning_logs"))
        if risk_fields:
            return _hard_gate(
                "data_quality_confirmation",
                "A required field has an unresolved cleaning or semantic decision.",
                f"请先确认 {'、'.join(risk_fields)} 的字段含义或清洗方式，再继续分析。",
                blocking_surfaces=BLOCKED_SURFACES_ALL,
                risk_fields=risk_fields,
                affected_routes=[_route_direction(route)],
            )

    if _is_high_risk_request(text):
        return _hard_gate(
            "method_confirmation",
            "High-risk analysis requires method, assumption, and evidence confirmation.",
            "这类分析可能影响决策结论。请先确认分析目标、方法假设和可接受的证据标准。",
            options=[
                {"label": "先确认方法与假设", "value": "confirm_method", "description": "适合预测、因果、实验或 ROI 判断。"},
                {"label": "仅做描述性探索", "value": "descriptive_only", "description": "不输出因果或预测性结论。"},
            ],
            blocking_surfaces=BLOCKED_SURFACES_EXECUTION,
            affected_routes=[_route_direction(route)] if route else [],
        )

    if route and _route_direction(route) == "period_compare" and not _has_time_window(text):
        return _hard_gate(
            "time_window",
            "Period comparison requires explicit comparison windows.",
            "请先确认要对比的时间窗口，例如最近 7 天对比前 7 天、活动前后，或指定两个日期范围。",
            options=[
                {"label": "最近 7 天 vs 前 7 天", "value": "last_7_vs_previous_7", "description": "适合快速判断短期变化。"},
                {"label": "最近 30 天 vs 前 30 天", "value": "last_30_vs_previous_30", "description": "适合降低日波动影响。"},
                {"label": "自定义时间范围", "value": "custom_window", "description": "适合活动前后或业务周期对比。"},
            ],
            blocking_surfaces=BLOCKED_SURFACES_ALL,
            affected_routes=["period_compare"],
        )

    metrics = _metric_candidates(state)
    if route and _route_needs_metric(route) and len(metrics) > 1 and not _mentions_any(text, metrics):
        return _hard_gate(
            "metric_scope",
            "Multiple plausible metrics exist and the user did not name the metric.",
            "请先确认本次分析关注的核心指标。",
            options=[
                {"label": metric, "value": metric, "description": "使用该字段作为本次分析的核心指标。"}
                for metric in metrics[:4]
            ],
            blocking_surfaces=BLOCKED_SURFACES_ALL,
            affected_routes=[_route_direction(route)],
        )

    return empty_question_need()


def empty_question_need() -> dict[str, Any]:
    return {
        "status": "clear",
        "question_type": "",
        "question": "",
        "reason": "",
        "options": [],
        "blocking_surfaces": [],
        "risk_fields": [],
        "affected_routes": [],
    }


def to_confirmation_gate(question_need: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(question_need, dict) or question_need.get("status") != "hard_question":
        return {
            "status": "clear",
            "confirmation_type": "",
            "question": "",
            "blocking_reason": "",
            "risk_fields": [],
            "affected_routes": [],
            "blocked_surfaces": [],
        }
    return {
        "status": "needs_confirmation",
        "confirmation_type": _text(question_need.get("question_type")),
        "question": _text(question_need.get("question")),
        "blocking_reason": _text(question_need.get("reason")),
        "risk_fields": _text_list(question_need.get("risk_fields")),
        "affected_routes": _text_list(question_need.get("affected_routes")),
        "blocked_surfaces": _text_list(question_need.get("blocking_surfaces")),
    }


def _hard_gate(
    question_type: str,
    reason: str,
    question: str,
    *,
    options: list[dict[str, str]] | None = None,
    blocking_surfaces: list[str] | None = None,
    risk_fields: list[str] | None = None,
    affected_routes: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "status": "hard_question",
        "question_type": question_type,
        "question": question,
        "reason": reason,
        "options": options or [],
        "blocking_surfaces": blocking_surfaces or BLOCKED_SURFACES_ALL,
        "risk_fields": _dedupe(risk_fields or []),
        "affected_routes": _dedupe(affected_routes or []),
    }


def _pending_file_relationship_gate(text: str, state: Any) -> dict[str, Any] | None:
    if _explicit_latest_only_without_relationship_scope(text):
        return None
    for relationship in _list_attr(state, "file_relationships"):
        if not relationship.get("requires_confirmation"):
            continue
        status = _text(relationship.get("status"))
        if status not in _PENDING_RELATIONSHIP_STATUSES:
            continue
        confirmation_type = _text(relationship.get("confirmation_type")) or "file_relationship_confirmation"
        return _hard_gate(
            confirmation_type,
            _relationship_reason(relationship),
            _relationship_question(relationship, confirmation_type),
            options=_relationship_options(confirmation_type),
            blocking_surfaces=BLOCKED_SURFACES_ALL,
        )
    return None


def _explicit_latest_only_without_relationship_scope(text: str) -> bool:
    lowered = (text or "").lower()
    if _relationship_scope_requested(lowered):
        return False
    if any(phrase in lowered for phrase in _LATEST_ONLY_PHRASES):
        return True
    return bool(
        re.search(r"\bonly\s+(analy[sz]e|use|look at)\s+(the\s+)?(latest|newest)\s+(file|upload|data|dataset)\b", lowered)
        or re.search(r"\b(exclude|ignore|skip|without)\s+(previous|historical|history|old)\s+(file|upload|data|dataset|files|uploads|datasets)?\b", lowered)
    )


def _relationship_scope_requested(text: str) -> bool:
    lowered = (text or "").lower()
    lowered = re.sub(r"\bnot\s+(previous|historical|history)\b", "", lowered)
    lowered = re.sub(r"\bwithout\s+(previous|historical|history)\b", "", lowered)
    lowered = re.sub(r"\b(exclude|ignore|skip|no)\s+(previous|historical|history|old)\b", "", lowered)
    lowered = lowered.replace("不要历史", "").replace("不看历史", "").replace("不包含历史", "").replace("排除历史", "")
    return any(term in lowered for term in _LATEST_ONLY_RELATIONSHIP_SCOPE_TERMS)


def _relationship_reason(relationship: dict[str, Any]) -> str:
    uncertainties = _text_list(relationship.get("uncertainties"))
    if uncertainties:
        return uncertainties[0]
    return "多个数据文件之间的关系尚未确认，可能影响本次分析范围。"


def _relationship_question(relationship: dict[str, Any], confirmation_type: str) -> str:
    file_summary = _relationship_file_summary(relationship)
    if confirmation_type == "file_exclusion_confirmation":
        if file_summary:
            return f"新上传的数据文件看起来可能不属于当前分析目标。请确认是否要纳入本轮分析。{file_summary}"
        return "新上传的数据文件看起来可能不属于当前分析目标。请确认是否要纳入本轮分析。"
    if file_summary:
        return f"新上传的数据文件可能与当前分析目标有关，但关系尚不确定。请确认这些文件是否应一起分析。{file_summary}"
    return "新上传的数据文件可能与当前分析目标有关，但关系尚不确定。请确认这些文件是否应一起分析。"


def _relationship_file_summary(relationship: dict[str, Any]) -> str:
    new_files = _text_list(relationship.get("new_files") or relationship.get("new_file_ids") or relationship.get("new_file_names"))
    existing_files = _text_list(
        relationship.get("existing_files")
        or relationship.get("existing_file_ids")
        or relationship.get("existing_file_names")
    )
    parts = []
    if new_files:
        parts.append("新文件：" + ", ".join(new_files[:3]))
    if existing_files:
        parts.append("已有文件：" + ", ".join(existing_files[:3]))
    return "；".join(parts)


def _relationship_options(confirmation_type: str) -> list[dict[str, str]]:
    if confirmation_type == "file_exclusion_confirmation":
        return [
            {
                "label": "纳入当前分析",
                "value": "include_in_active_bundle",
                "description": "将新文件视为当前分析目标的一部分。",
            },
            {
                "label": "暂不纳入",
                "value": "exclude_from_active_bundle",
                "description": "本轮分析先不使用该文件，保持当前分析范围。",
            },
        ]
    return [
        {
            "label": "一起分析",
            "value": "include_in_active_bundle",
            "description": "把这些文件放入同一分析范围，后续综合判断。",
        },
        {
            "label": "分开分析",
            "value": "separate_bundle",
            "description": "将新文件与当前分析范围分开处理。",
        },
        {
            "label": "只分析最新文件",
            "value": "latest_only",
            "description": "本轮只使用最新上传的数据文件，不纳入历史文件。",
        },
    ]


def _intent_type(intent: Any) -> str:
    return _text(getattr(intent, "intent_type", ""))


def _is_vague_route_request(intent: Any) -> bool:
    return (
        _intent_type(intent) == "intent_negotiation"
        or _text(getattr(intent, "clarity", "")) == "vague"
        or _text(getattr(intent, "recommended_action", "")) == "guide_analysis"
    )


def _scoped_routes(state: Any) -> list[dict[str, Any]]:
    active_dataset = _active_dataset(state)
    routes = []
    for route in _list_attr(state, "route_proposals"):
        dataset = _text(route.get("dataset"))
        if active_dataset and dataset and dataset != active_dataset:
            continue
        if _route_direction(route):
            routes.append(route)
    return routes


def _active_dataset(state: Any) -> str:
    scope = getattr(state, "active_scope", None)
    if not isinstance(scope, dict):
        return ""
    return _text(scope.get("active_dataset"))


def _infer_route(text: str, routes: list[dict[str, Any]]) -> dict[str, Any] | None:
    for route in routes:
        direction = _route_direction(route)
        keywords = _ROUTE_KEYWORDS.get(direction, (direction,))
        if any(keyword and keyword.lower() in text for keyword in keywords):
            return route
    if len(routes) == 1:
        return routes[0]
    return None


def _route_options(routes: list[dict[str, Any]]) -> list[dict[str, str]]:
    options = []
    for route in routes[:4]:
        direction = _route_direction(route)
        label = _text(route.get("label") or route.get("user_facing_label") or direction)
        options.append({
            "label": label,
            "value": direction,
            "description": _text(route.get("reason")) or f"Use the {direction} route.",
        })
    return options


def _required_field_risks(route: dict[str, Any], cleaning_logs: list[dict[str, Any]]) -> list[str]:
    required = set(_required_fields(route))
    if not required:
        return []
    route_dataset = _text(route.get("dataset"))
    risks: list[str] = []
    for log in cleaning_logs:
        log_dataset = _text(log.get("dataset"))
        if route_dataset and log_dataset and route_dataset != log_dataset:
            continue
        decisions = log.get("decisions")
        if not isinstance(decisions, list):
            decisions = [log] if _text(log.get("decision_type")) else []
        for decision in decisions:
            if not isinstance(decision, dict) or _text(decision.get("decision_type")) != "needs_confirmation":
                continue
            field = _text(decision.get("column") or decision.get("field"))
            if field in required:
                risks.append(field)
    return _dedupe(risks)


def _required_fields(route: dict[str, Any]) -> list[str]:
    fields = _text_list(route.get("evidence_requirements"))
    roles = route.get("field_roles") if isinstance(route.get("field_roles"), dict) else {}
    direction = _route_direction(route)
    if direction in {"trend", "period_compare", "cohort"}:
        fields.extend(_text_list(roles.get("date")))
    if direction in {"trend", "period_compare", "dimension_decomposition", "funnel"}:
        fields.extend(_text_list(roles.get("metrics")))
        fields.extend(_text_list(roles.get("rate_metrics")))
    return _dedupe(fields)


def _metric_candidates(state: Any) -> list[str]:
    metrics: list[str] = []
    active_dataset = _active_dataset(state)
    for contract in _list_attr(state, "dataset_contracts"):
        dataset = _text(contract.get("dataset"))
        if active_dataset and dataset and dataset != active_dataset:
            continue
        roles = contract.get("field_roles") if isinstance(contract.get("field_roles"), dict) else {}
        metrics.extend(_text_list(roles.get("metrics")))
        metrics.extend(_text_list(roles.get("rate_metrics")))
    return _dedupe(metrics)


def _route_needs_metric(route: dict[str, Any]) -> bool:
    direction = _route_direction(route)
    return direction in {"trend", "period_compare", "dimension_decomposition", "funnel"}


def _is_high_risk_request(text: str) -> bool:
    return any(keyword in text for keyword in _HIGH_RISK_KEYWORDS)


def _has_time_window(text: str) -> bool:
    return any(keyword in text for keyword in _WINDOW_KEYWORDS)


def _mentions_any(text: str, values: list[str]) -> bool:
    lowered = text.lower()
    return any(value.lower() in lowered for value in values if value)


def _route_direction(route: dict[str, Any]) -> str:
    return _text(route.get("direction") or route.get("route"))


def _list_attr(state: Any, name: str) -> list[dict[str, Any]]:
    value = getattr(state, name, None)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_text(item) for item in value if _text(item)]


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, (int, float, bool)):
        return str(value)
    return ""


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
