"""Deterministic policy for deciding when user confirmation is required."""

from __future__ import annotations

from typing import Any
from datetime import date
import re

from data_agent.agent.multi_file_scope import build_material_ambiguity_groups
from data_agent.agent.request_language import has_affirmative_keyword


BLOCKED_SURFACES_ALL = ["direct_recommendation", "analysis_execution", "report_generation"]
BLOCKED_SURFACES_EXECUTION = ["analysis_execution", "report_generation"]
MAX_SCOPE_SELECTION_OPTIONS = 20
MAX_SCOPE_CANDIDATE_SAMPLE = 5
MAX_SCOPE_ORDINAL_TEXT_LENGTH = 120

_CONSULTING_INTENTS = {"simple_response", "knowledge_qa", "analysis_consultation", "result_followup"}
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

    ambiguity_groups = build_material_ambiguity_groups(state, user_goal=user_input)
    if ambiguity_groups:
        return _file_scope_question(ambiguity_groups[0])

    text = (user_input or "").lower()
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

    if _is_high_risk_request(text) and not _has_confirmed_high_risk_spec(text, state):
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


def _file_scope_question(
    ambiguity_group: dict[str, Any],
) -> dict[str, Any]:
    files = [
        item for item in ambiguity_group.get("files", [])
        if isinstance(item, dict)
    ]
    group_label = _text(ambiguity_group.get("alias")) or "the referenced data"
    file_ids = [_text(item.get("file_id")) for item in files]
    file_ids = [file_id for file_id in file_ids if file_id]
    if len(files) > MAX_SCOPE_SELECTION_OPTIONS:
        ordinals = sorted({
            int(item.get("upload_order"))
            for item in files
            if isinstance(item.get("upload_order"), int)
            and int(item.get("upload_order")) > 0
        })
        ordinal_text = _compress_upload_ordinals(ordinals)
        if ordinal_text and len(ordinal_text) <= MAX_SCOPE_ORDINAL_TEXT_LENGTH:
            answer_instruction = (
                f"当前会话全局上传顺序中的有效序号为：{ordinal_text}。"
                "请回复“第 N 个文件”。"
            )
        else:
            ordinal_range = (
                f"{ordinals[0]}-{ordinals[-1]}" if ordinals else "未知"
            )
            examples = "、".join(str(value) for value in ordinals[:MAX_SCOPE_CANDIDATE_SAMPLE])
            answer_instruction = (
                f"当前会话全局上传序号范围为 {ordinal_range}，"
                f"共 {len(files)} 个候选；并非区间内每个序号都属于本组。"
                "请在文件列表按全局上传顺序选择，并回复“第 N 个文件”。"
                f"例如有效序号：{examples}。"
            )
        return _hard_gate(
            "file_scope_selection",
            "The file reference matches too many usable files for a complete single-select question.",
            (
                f"共有 {len(files)} 个同名候选文件（{group_label}）。"
                f"{answer_instruction}"
            ),
            options=[],
            blocking_surfaces=BLOCKED_SURFACES_ALL,
            state_updates={"stage": "scope"},
            metadata={
                "candidate_count": len(files),
                "candidate_sample": files[:MAX_SCOPE_CANDIDATE_SAMPLE],
                "sample_ordinals": ordinals[:MAX_SCOPE_CANDIDATE_SAMPLE],
            },
        )

    base_labels = [_scope_file_label(item) for item in files]
    label_counts = {
        label.casefold(): sum(other.casefold() == label.casefold() for other in base_labels)
        for label in base_labels
    }
    options = []
    for item, base_label in zip(files, base_labels):
        file_id = _text(item.get("file_id"))
        if not file_id:
            continue
        dataset = _text(item.get("dataset"))
        has_conflict = label_counts.get(base_label.casefold(), 0) > 1
        options.append({
            "label": f"{base_label} [{file_id}]" if has_conflict else base_label,
            "value": file_id,
            "description": (
                f"Dataset: {dataset or 'unknown'}; file_id: {file_id}"
                if has_conflict
                else dataset or f"Use {base_label} for this analysis."
            ),
        })
    return _hard_gate(
        "file_scope_selection",
        "The file reference matches multiple usable files, and the choice changes the analysis scope.",
        f"The request matches multiple files for {group_label}. Which file should be used for this analysis?",
        options=options,
        blocking_surfaces=BLOCKED_SURFACES_ALL,
        state_updates={"stage": "scope"},
        metadata={"file_ids": file_ids},
    )


def _scope_file_label(item: dict[str, Any]) -> str:
    return _text(item.get("filename") or item.get("dataset") or item.get("file_id"))


def _compress_upload_ordinals(values: list[int]) -> str:
    if not values:
        return ""
    ranges = []
    start = previous = values[0]
    for value in values[1:]:
        if value == previous + 1:
            previous = value
            continue
        ranges.append(str(start) if start == previous else f"{start}-{previous}")
        start = previous = value
    ranges.append(str(start) if start == previous else f"{start}-{previous}")
    return "、".join(ranges)


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
    state_updates: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    gate = {
        "status": "hard_question",
        "question_type": question_type,
        "question": question,
        "reason": reason,
        "options": options or [],
        "blocking_surfaces": blocking_surfaces or BLOCKED_SURFACES_ALL,
        "risk_fields": _dedupe(risk_fields or []),
        "affected_routes": _dedupe(affected_routes or []),
    }
    if state_updates:
        gate["state_updates"] = state_updates
    if metadata:
        gate["metadata"] = metadata
    return gate


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
    grouped = bool(re.search(
        r"按[^。；\n]{1,100}(?:组合|分组|汇总)|\bgroup(?:ed)? by\b|"
        r"\bby (?:channel|company|product|segment|category)\b", text, re.IGNORECASE,
    ))
    if grouped:
        dimensional = next((r for r in routes if _route_direction(r) == "dimension_decomposition"), None)
        if dimensional is not None:
            return dimensional
    for route in routes:
        direction = _route_direction(route)
        if direction == "period_compare" and grouped and not _has_time_window(text):
            # Comparing named groups does not imply comparing two periods.
            continue
        keywords = _ROUTE_KEYWORDS.get(direction, (direction,))
        if any(keyword and keyword.lower() in text for keyword in keywords):
            return route
    if len(routes) == 1 and not (grouped and _route_direction(routes[0]) == "period_compare"):
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
    return has_affirmative_keyword(text, _HIGH_RISK_KEYWORDS)


def _has_confirmed_high_risk_spec(text: str, state: Any) -> bool:
    spec = getattr(state, "analysis_spec", None)
    if not isinstance(spec, dict):
        return False
    confirmation = spec.get("method_confirmation")
    if not isinstance(confirmation, dict) or confirmation.get("status") != "approved":
        return False
    return (
        _text(confirmation.get("analysis_spec_id")) == _text(spec.get("id"))
        and _text(confirmation.get("playbook_id")) == _text(spec.get("playbook_id"))
        and _material_request_identity(text) == _text(confirmation.get("request_identity"))
    )


def _material_request_identity(value: Any) -> str:
    return " ".join(_text(value).casefold().split())


def _has_time_window(text: str) -> bool:
    # Numeric dates carry window semantics even without words such as 月/天.
    # Require two valid ordered ranges, rather than treating arbitrary numbers
    # or a single date as a complete period comparison.
    date_pattern = r"(\d{4}[-/]\d{1,2}[-/]\d{1,2})"
    ranges = re.findall(date_pattern + r"\s*(?:至|到|~|～|—|–|\bto\b)\s*" + date_pattern, text)
    valid_ranges = 0
    for start, end in ranges:
        try:
            first = date(*map(int, re.split(r"[-/]", start)))
            last = date(*map(int, re.split(r"[-/]", end)))
        except ValueError:
            continue
        valid_ranges += first <= last
    return valid_ranges >= 2 or any(keyword in text for keyword in _WINDOW_KEYWORDS)


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
