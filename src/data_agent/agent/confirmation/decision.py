"""Business-decision semantics for confirmation candidates (IC1).

Pure functions: normalize a decision context from a candidate's resolution
params, decide whether a candidate represents a real business gap, and build
the stable logical decision identity used for reuse. No I/O, no model calls.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

# Design §3: the decision kinds that can justify asking the user. A method
# name is deliberately absent - method choice is the system's own decision.
DECISION_KINDS = frozenset({
    "time_window",
    "metric_definition",
    "denominator",
    "file_scope",
    "field_semantics",
    "goal_choice",
})

# Legacy gate question types mapped onto decision kinds so existing internal
# producers satisfy the decision contract without changing their payloads.
_GATE_KIND_MAP = {
    "time_window": "time_window",
    "metric_scope": "metric_definition",
    "data_quality_confirmation": "field_semantics",
    "file_scope": "file_scope",
    "file_scope_selection": "file_scope",
    "route_selection": "goal_choice",
    "scope_confirmation": "goal_choice",
    "metric_window": "time_window",
}

METHOD_DECISION_KINDS = frozenset({"method_confirmation", "method", "method_approval"})

# Design §3: a truthy safe_default alone is not an advisory basis. The default
# must originate from a host-verifiable source; model-claimed defaults are
# explicitly excluded.
HOST_VERIFIED_DEFAULT_ORIGINS = frozenset({
    "user_request",
    "schema",
    "confirmed_data",
    "exploration_scope",
})

# Method-approval wording: a permission question about a method/model, not a
# business value. "是否按 30 天窗口对比" must NOT match - the object there is
# a business window, not a method.
_METHOD_QUESTION_PATTERN = None  # compiled lazily in is_method_approval_shaped
# 仅匹配"许可式"方法措辞：动词＋方法/模型/算法名词；"分析方法"“换个方法分析”
# 这类业务表述不得命中。
_METHOD_PERMISSION_MARKERS = (
    "是否使用", "是否采用", "是否按此", "要不要用", "要不要换",
    "use this method", "proceed with this method", "use the method",
    "confirm the method", "该方法继续", "此方法继续", "这个方法继续",
)


def normalized_business_scope(value: Any) -> str:
    """Whitespace/case normalization that keeps numbers and negations.

    Design §6: negations, numbers, dates, units, and denominators must survive
    normalization - "包含成本" vs "不包含成本" and 30 天 vs 7 天 are different
    business scopes and must never collapse onto one reuse key.
    """
    text = str(value or "")
    return " ".join(text.split()).casefold()


def decision_context_from_candidate(candidate: Any) -> dict[str, Any]:
    """Extract and normalize the decision context carried by a candidate.

    Reads resolution_params first (new producers), then falls back to the
    well-known gate payload fields so internal deterministic producers keep
    working unchanged. Returns a plain dict with decision_kind / missing_value
    / affected_operations / business_scope (any of which may be empty).
    """
    params: Mapping[str, Any] = getattr(candidate, "resolution_params", {}) or {}
    confirmation_type = str(params.get("confirmation_type") or "").strip()

    decision_kind = str(params.get("decision_kind") or "").strip()
    if decision_kind in METHOD_DECISION_KINDS:
        decision_kind = ""
    if not decision_kind:
        if confirmation_type in _GATE_KIND_MAP:
            decision_kind = _GATE_KIND_MAP[confirmation_type]
        elif confirmation_type in DECISION_KINDS:
            decision_kind = confirmation_type

    missing_value = str(params.get("missing_value") or "").strip()
    if not missing_value:
        missing_value = _first_text(params.get("risk_fields"))

    affected_raw = params.get("affected_operations") or params.get("affected_routes")
    affected_operations = [str(item).strip() for item in _as_list(affected_raw) if str(item).strip()]

    business_scope = normalized_business_scope(
        params.get("business_scope") or missing_value or params.get("question")
    )
    return {
        "decision_kind": decision_kind if decision_kind in DECISION_KINDS else "",
        "missing_value": missing_value,
        "affected_operations": affected_operations,
        "business_scope": business_scope,
        "confirmation_type": confirmation_type,
    }


def is_method_approval_shaped(candidate: Any) -> bool:
    """True when a candidate only asks for permission to use a method.

    Covers the retired producer sources and method-shaped wording in the
    question itself (Q09: model-initiated "是否使用留存方法继续" asks).
    """
    params: Mapping[str, Any] = getattr(candidate, "resolution_params", {}) or {}
    confirmation_type = str(params.get("confirmation_type") or "").strip()
    if confirmation_type in METHOD_DECISION_KINDS:
        return True
    source = str(getattr(candidate, "source", "") or "").strip()
    if source in {"method_playbook"}:
        return True
    question = normalized_business_scope(params.get("question"))
    if not question:
        return False
    if any(marker in question for marker in _METHOD_PERMISSION_MARKERS):
        method_words = ("方法", "模型", "算法", "method", "model")
        return any(word in question for word in method_words)
    return False


def default_is_host_verified(candidate: Any) -> bool:
    """A safe_default only counts when its origin is host-verifiable (Q12)."""
    params: Mapping[str, Any] = getattr(candidate, "resolution_params", {}) or {}
    origin = str(params.get("default_origin") or "").strip()
    return origin in HOST_VERIFIED_DEFAULT_ORIGINS


def represents_business_gap(candidate: Any) -> bool:
    """Minimal decision contract (design §10.2): a real, material gap.

    A candidate may suspend the user only when it names a business decision
    kind, the concrete missing value, and the operations that depend on it.
    """
    if is_method_approval_shaped(candidate):
        return False
    context = decision_context_from_candidate(candidate)
    return bool(
        context["decision_kind"]
        and context["missing_value"]
        and context["affected_operations"]
    )


def stable_decision_key(candidate: Any, *, session_id: str) -> str:
    """Logical reuse key: session + decision kind + normalized scope.

    Deliberately excludes turn id, message counts, and display text churn
    (R01/R02). Without a semantic scope the key falls back to the candidate's
    per-occurrence identity so nothing unverifiable is reused (§6: no
    text-hash equivalence for unstructured old answers).
    """
    context = decision_context_from_candidate(candidate)
    if not context["decision_kind"] or not context["business_scope"]:
        return str(getattr(candidate, "decision_key", "") or "")
    option_values = sorted(
        str(option.value)
        for option in (getattr(candidate, "options", None) or ())
    )
    scope_payload = f"{context['decision_kind']}|{context['business_scope']}|{option_values}"
    return f"{session_id}:decision:{_stable_hash(scope_payload)}"


def scope_data_version(candidate: Any) -> str:
    """Relevant data identity for reuse (R05); empty means unversioned.

    Callers pass a host-computed fingerprint of only the datasets the
    decision depends on; unrelated file changes leave it untouched.
    """
    params: Mapping[str, Any] = getattr(candidate, "resolution_params", {}) or {}
    return str(params.get("scope_data_version") or "").strip()


def _as_list(value: Any) -> Iterable[Any]:
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        return value
    return (value,)


def _first_text(value: Any) -> str:
    for item in _as_list(value):
        text = str(item or "").strip()
        if text:
            return text
    return ""


def _stable_hash(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def decision_context_from_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Decision context from a plain request payload (pre-candidate stage).

    Used by the runtime adapter to enrich resolution_params before the
    QuestionCandidate is built, so internal gate payloads (risk fields,
    affected routes) become explicit decision context.
    """
    confirmation_type = str(payload.get("confirmation_type") or "").strip()
    decision_kind = str(payload.get("decision_kind") or "").strip()
    if decision_kind in METHOD_DECISION_KINDS:
        decision_kind = ""
    if not decision_kind:
        if confirmation_type in _GATE_KIND_MAP:
            decision_kind = _GATE_KIND_MAP[confirmation_type]
        elif confirmation_type in DECISION_KINDS:
            decision_kind = confirmation_type

    missing_value = str(payload.get("missing_value") or "").strip()
    if not missing_value:
        missing_value = _first_text(payload.get("risk_fields"))
    if not missing_value and decision_kind:
        # 语义类型已确认（方法类已在更早的形状检查排除）时，问题文本
        # 本身指明缺口；仅用于上下文推导，不构成放行依据。
        missing_value = str(payload.get("question") or "").strip()

    affected_operations = [
        str(item).strip()
        for item in _as_list(
            payload.get("affected_operations") or payload.get("affected_routes")
        )
        if str(item).strip()
    ]

    business_scope = normalized_business_scope(
        payload.get("business_scope") or missing_value or payload.get("question")
    )
    return {
        "decision_kind": decision_kind if decision_kind in DECISION_KINDS else "",
        "missing_value": missing_value,
        "affected_operations": affected_operations,
        "business_scope": business_scope,
        "confirmation_type": confirmation_type,
    }
