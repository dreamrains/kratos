"""Compact multi-file analysis scope planning helpers."""

from __future__ import annotations

from typing import Any


USER_ALIASES = {
    "user_id",
    "userid",
    "uid",
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

    included_files: list[dict[str, Any]] = []
    excluded_files: list[dict[str, Any]] = []
    pending_files: list[dict[str, Any]] = []
    assumptions: list[str] = []

    for profile in data_pool:
        summary = _file_summary(profile)
        file_id = summary["file_id"]
        if _is_explicitly_unrelated(profile, goal):
            excluded_files.append(summary)
        elif file_id in active_file_ids or _is_relevant_file(profile, goal):
            included_files.append(summary)
            assumptions.extend(_alias_assumptions(profile))
        else:
            pending_files.append(summary)

    assumptions = _dedupe(assumptions)
    return {
        "scope_status": "needs_confirmation" if assumptions else "ready",
        "goal": goal,
        "included_files": included_files,
        "excluded_files": excluded_files,
        "pending_files": pending_files,
        "assumptions": assumptions,
        "context_budget": {
            "included_file_count": len(included_files),
            "excluded_file_count": len(excluded_files),
            "pending_file_count": len(pending_files),
            "max_included_files": 5,
        },
    }


def _file_summary(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "file_id": _text(profile.get("file_id") or profile.get("id")),
        "filename": _text(profile.get("filename") or profile.get("name")),
        "dataset": _text(profile.get("dataset") or profile.get("dataset_name")),
        "grain": infer_file_grain(profile)["grain"],
        "canonical_fields": canonical_entity_fields(profile),
    }


def _is_relevant_file(profile: dict[str, Any], goal: str) -> bool:
    text = _profile_text(profile)
    fields = canonical_entity_fields(profile)
    if _is_explicitly_unrelated(profile, goal):
        return False
    if _has_any(goal, MEMBERSHIP_GOAL_TERMS):
        return bool(fields["order"] or fields["coupon"] or fields["user"] or _has_any(text, ("订单", "coupon", "优惠券", "代金券")))
    return bool(fields["order"] or fields["coupon"] or fields["user"])


def _is_explicitly_unrelated(profile: dict[str, Any], goal: str) -> bool:
    text = _profile_text(profile)
    return _has_any(text, EXCLUDED_GAME_TERMS) and not _has_any(goal, GAME_GOAL_TERMS)


def _alias_assumptions(profile: dict[str, Any]) -> list[str]:
    user_fields = canonical_entity_fields(profile)["user"]
    alias_fields = [field for field in user_fields if field != "user_id"]
    if not alias_fields:
        return []
    label = _text(profile.get("dataset") or profile.get("filename") or profile.get("file_id"))
    aliases = ", ".join(alias_fields)
    return [f"Assume {label} uses {aliases} as user identifiers."]


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
