"""Compact multi-file analysis scope planning helpers."""

from __future__ import annotations

import re
from typing import Any


MAX_SCOPE_FILES = 5
MAX_RELATIONSHIP_EVIDENCE = 3

USER_ALIASES = {
    "user_id",
    "userid",
    "uid",
    "customer_id",
    "member_id",
    "account_id",
    "用户id",
    "用户ID",
    "用户_id",
    "主用户ID",
    "产品用户ID",
    "会员ID",
    "会员id",
}
ORDER_ALIASES = {"order_id", "订单ID", "订单id", "订单号", "订单编号"}
COUPON_ALIASES = {"coupon_id", "优惠券ID", "优惠券id", "代金券ID", "代金券id"}
TIME_ALIASES = {"paid_at", "pay_time", "event_time", "支付时间", "下单时间", "核销时间", "日期", "时间"}

EXCLUDED_GAME_TERMS = ("game", "游戏", "互推")
GAME_GOAL_TERMS = ("game", "游戏", "互推", "留存", "retention")
MEMBERSHIP_GOAL_TERMS = ("省钱卡", "会员", "membership", "member", "card")
GOAL_THEME_GROUPS = (
    MEMBERSHIP_GOAL_TERMS,
    GAME_GOAL_TERMS,
    ("订单", "order"),
    ("优惠券", "代金券", "coupon"),
    ("收入", "营收", "revenue", "sales"),
    ("留存", "retention", "cohort"),
)


def canonical_entity_fields(profile: dict[str, Any]) -> dict[str, list[str]]:
    """Return known entity fields from a data-pool profile."""
    fields = _profile_fields(profile)
    return {
        "user": _matching_fields(fields, USER_ALIASES),
        "order": _matching_fields(fields, ORDER_ALIASES),
        "coupon": _matching_fields(fields, COUPON_ALIASES),
        "time": _matching_fields(fields, TIME_ALIASES),
    }


def infer_file_grain(profile: dict[str, Any]) -> dict[str, str]:
    """Infer a compact file grain from canonical fields and filename hints."""
    entities = canonical_entity_fields(profile)
    filename = _text(profile.get("filename") or profile.get("name"))
    if entities["order"]:
        return {"grain": "order_level", "reason": f"order id field: {entities['order'][0]}"}
    if entities["coupon"] and entities["user"]:
        return {
            "grain": "coupon_usage_level",
            "reason": f"coupon and user fields: {entities['coupon'][0]}, {entities['user'][0]}",
        }
    if entities["user"]:
        return {"grain": "user_level", "reason": f"user id field: {entities['user'][0]}"}
    if _has_any(filename, ("retention", "留存")):
        return {"grain": "cohort_aggregate", "reason": "filename suggests retention/cohort aggregate"}
    return {"grain": "unknown", "reason": "no canonical entity fields detected"}


def build_analysis_scope_plan(state: Any, user_goal: str = "") -> dict[str, Any]:
    """Build a deterministic, compact scope plan from state.data_pool."""
    goal = _text(user_goal) or _text(getattr(state, "goal", ""))
    data_pool = _list_items(getattr(state, "data_pool", None))
    active_file_ids = _active_bundle_file_ids(state)
    relationships = _relationships_by_file(state)

    classified = [
        _classify_scope_file(profile, index, goal, active_file_ids, relationships)
        for index, profile in enumerate(data_pool)
    ]
    prioritized = sorted(classified, key=lambda item: (item["priority"], item["index"]))
    returned = prioritized[:MAX_SCOPE_FILES]
    if any(item["scope"] == "pending" for item in classified) and not any(
        item["scope"] == "pending" for item in returned
    ):
        pending_item = next(item for item in prioritized if item["scope"] == "pending")
        returned[-1] = pending_item
        returned.sort(key=lambda item: (item["priority"], item["index"]))
    included_files = [item["summary"] for item in returned if item["scope"] == "included"]
    excluded_files = [item["summary"] for item in returned if item["scope"] == "excluded"]
    pending_files = [item["summary"] for item in returned if item["scope"] == "pending"]
    assumptions = _dedupe([
        assumption
        for item in returned
        if item["scope"] == "pending"
        for assumption in _alias_candidate_assumptions(item["profile"], item["relationship"])
    ])
    has_pending = any(item["scope"] == "pending" for item in classified)
    returned_file_count = len(returned)
    return {
        "scope_status": "needs_confirmation" if has_pending else "ready",
        "goal": goal,
        "included_files": included_files,
        "excluded_files": excluded_files,
        "pending_files": pending_files,
        "assumptions": assumptions,
        "context_budget": {
            "included_file_count": len(included_files),
            "excluded_file_count": len(excluded_files),
            "pending_file_count": len(pending_files),
            "total_file_count": len(classified),
            "returned_file_count": returned_file_count,
            "omitted_file_count": len(classified) - returned_file_count,
            "max_scope_files": MAX_SCOPE_FILES,
        },
    }


def _classify_scope_file(
    profile: dict[str, Any],
    index: int,
    goal: str,
    active_file_ids: set[str],
    relationships: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    file_id = _text(profile.get("file_id") or profile.get("id"))
    relationship = _best_relationship(relationships.get(file_id, []))
    summary = _file_summary(profile, relationship)

    if _is_explicitly_unrelated(profile, goal):
        scope, priority = "excluded", 5
    elif file_id in active_file_ids:
        scope, priority = "included", 0
    elif _relationship_is_confirmed(relationship):
        scope, priority = "included", 1
    elif _relationship_is_pending(relationship):
        scope, priority = "pending", 3
    elif _relationship_is_excluded(relationship):
        scope, priority = "excluded", 5
    elif _has_strong_goal_theme_overlap(profile, goal):
        scope, priority = "included", 2
    else:
        scope, priority = "pending", 4

    return {
        "index": index,
        "priority": priority,
        "scope": scope,
        "summary": summary,
        "profile": profile,
        "relationship": relationship,
    }


def _file_summary(
    profile: dict[str, Any],
    relationship: dict[str, Any] | None = None,
) -> dict[str, Any]:
    summary = {
        "file_id": _text(profile.get("file_id") or profile.get("id")),
        "filename": _text(profile.get("filename") or profile.get("name")),
        "dataset": _text(profile.get("dataset") or profile.get("dataset_name")),
        "grain": infer_file_grain(profile)["grain"],
        "canonical_fields": canonical_entity_fields(profile),
    }
    if relationship:
        summary["relationship"] = {
            "relationship_id": _relationship_id(relationship),
            "status": _relationship_status(relationship),
            "requires_confirmation": bool(relationship.get("requires_confirmation")),
            "evidence": _text_list(relationship.get("evidence"))[:MAX_RELATIONSHIP_EVIDENCE],
        }
    return summary


def _has_strong_goal_theme_overlap(profile: dict[str, Any], goal: str) -> bool:
    profile_theme = " ".join([
        _text(profile.get("filename") or profile.get("name")),
        _text(profile.get("dataset") or profile.get("dataset_name")),
    ])
    if not goal or not profile_theme:
        return False
    if any(_has_any(goal, group) and _has_any(profile_theme, group) for group in GOAL_THEME_GROUPS):
        return True
    goal_tokens = _theme_tokens(goal)
    profile_tokens = _theme_tokens(profile_theme)
    return bool(goal_tokens & profile_tokens)


def _is_explicitly_unrelated(profile: dict[str, Any], goal: str) -> bool:
    text = _profile_text(profile)
    return _has_any(text, EXCLUDED_GAME_TERMS) and not _has_any(goal, GAME_GOAL_TERMS)


def _alias_candidate_assumptions(
    profile: dict[str, Any],
    relationship: dict[str, Any] | None,
) -> list[str]:
    user_fields = canonical_entity_fields(profile)["user"]
    alias_fields = [field for field in user_fields if field != "user_id"]
    if not alias_fields:
        return []
    file_id = _text(profile.get("file_id") or profile.get("id"))
    relationship_id = _relationship_id(relationship) if relationship else "no relationship record"
    aliases = ", ".join(alias_fields)
    return [
        f"Candidate mapping for pending file {file_id} ({relationship_id}): "
        f"{aliases} may represent user identifiers; confirm before using them as join keys."
    ]


def _relationships_by_file(state: Any) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for relationship in _list_items(getattr(state, "file_relationships", None)):
        for file_id in _text_list(relationship.get("file_ids")):
            result.setdefault(file_id, []).append(relationship)
    return result


def _best_relationship(relationships: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not relationships:
        return None
    return min(relationships, key=_relationship_priority)


def _relationship_priority(relationship: dict[str, Any]) -> int:
    if _relationship_is_pending(relationship):
        return 0
    if _relationship_is_confirmed(relationship):
        return 1
    if _relationship_is_excluded(relationship):
        return 2
    return 3


def _relationship_is_confirmed(relationship: dict[str, Any] | None) -> bool:
    if not relationship or relationship.get("requires_confirmation"):
        return False
    status = _relationship_status(relationship)
    mode = _normalize_alias(_text(relationship.get("relationship_mode")))
    return status in {"linked", "confirmed", "include_in_active_bundle"} or mode == "include_in_active_bundle"


def _relationship_is_pending(relationship: dict[str, Any] | None) -> bool:
    if not relationship:
        return False
    status = _relationship_status(relationship)
    return bool(relationship.get("requires_confirmation")) or status == "possibly_linked" or status.startswith("insufficient")


def _relationship_is_excluded(relationship: dict[str, Any] | None) -> bool:
    if not relationship:
        return False
    status = _relationship_status(relationship)
    mode = _normalize_alias(_text(relationship.get("relationship_mode")))
    return status == "excluded" or mode == "exclude_from_active_bundle"


def _relationship_status(relationship: dict[str, Any]) -> str:
    return _normalize_alias(_text(relationship.get("status") or relationship.get("relationship_status")))


def _relationship_id(relationship: dict[str, Any] | None) -> str:
    if not relationship:
        return ""
    return _text(relationship.get("relationship_id") or relationship.get("id"))


def _theme_tokens(value: str) -> set[str]:
    return {
        token.casefold()
        for token in re.findall(r"[a-zA-Z0-9_]+", value)
        if len(token) >= 3
    }


def _active_bundle_file_ids(state: Any) -> set[str]:
    active_bundle_id = _text(getattr(state, "active_bundle_id", ""))
    if not active_bundle_id:
        return set()
    for bundle in _list_items(getattr(state, "dataset_bundles", None)):
        if _text(bundle.get("bundle_id") or bundle.get("id")) == active_bundle_id:
            return set(_text_list(bundle.get("file_ids")))
    return set()


def _profile_fields(profile: dict[str, Any]) -> list[str]:
    fields: list[str] = []
    for key in ("columns", "key_fields", "time_fields"):
        fields.extend(_text_list(profile.get(key)))
    return _dedupe(fields)


def _matching_fields(fields: list[str], aliases: set[str]) -> list[str]:
    normalized_aliases = {_normalize_alias(alias) for alias in aliases}
    return [field for field in fields if _normalize_alias(field) in normalized_aliases]


def _profile_text(profile: dict[str, Any]) -> str:
    pieces = [
        _text(profile.get("file_id") or profile.get("id")),
        _text(profile.get("filename") or profile.get("name")),
        _text(profile.get("dataset") or profile.get("dataset_name")),
    ]
    pieces.extend(_profile_fields(profile))
    return " ".join(piece for piece in pieces if piece)


def _has_any(text: str, terms: tuple[str, ...]) -> bool:
    normalized = _normalize_alias(text)
    return any(_normalize_alias(term) in normalized for term in terms)


def _normalize_alias(value: str) -> str:
    return "".join(value.split()).casefold()


def _list_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_text(item) for item in value if _text(item)]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, (int, float, bool)):
        return str(value)
    return ""
