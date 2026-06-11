"""Session data-pool and active-bundle helpers."""

from __future__ import annotations

import hashlib
from pathlib import PurePath, PureWindowsPath
import re
from datetime import date, datetime
from typing import Any


STRONG_ID_FIELDS = {
    "account_id",
    "customer_id",
    "device_id",
    "member_id",
    "order_id",
    "phone",
    "phone_number",
    "uid",
    "user_id",
    "userid",
    "会员id",
    "会员_id",
    "手机号",
    "用户id",
    "用户_id",
    "订单id",
    "订单_id",
}
GENERIC_ID_FIELDS = {"id", "no", "number", "\u7f16\u53f7", "\u5e8f\u53f7"}
COMMON_THEME_TOKENS = {
    "2020",
    "2021",
    "2022",
    "2023",
    "2024",
    "2025",
    "2026",
    "2027",
    "csv",
    "data",
    "dataset",
    "detail",
    "details",
    "export",
    "file",
    "jan",
    "january",
    "feb",
    "february",
    "mar",
    "march",
    "apr",
    "april",
    "may",
    "jun",
    "june",
    "jul",
    "july",
    "aug",
    "august",
    "sep",
    "sept",
    "september",
    "oct",
    "october",
    "nov",
    "november",
    "dec",
    "december",
    "latest",
    "report",
    "sheet",
    "table",
    "xlsx",
}
CHINESE_THEME_TOKENS = (
    "省钱卡",
    "订单",
    "用户",
    "流水",
    "代金券",
    "游戏",
    "留存",
    "互推",
    "付费",
    "内购",
    "激励视频",
)
LATEST_ONLY_PHRASES = (
    "latest only",
    "latest upload only",
    "only analyze the latest",
    "only latest",
    "only use the latest",
    "only the latest",
    "use latest only",
    "\u53ea\u5206\u6790\u521a\u4e0a\u4f20",
    "\u53ea\u5206\u6790\u6700\u65b0",
    "\u4ec5\u5206\u6790\u6700\u65b0",
    "仅使用最新",
    "只使用最新",
)
LATEST_ONLY_EXCLUSION_TERMS = (
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


def stable_file_id(filename: str, dataset: str = "") -> str:
    """Return a deterministic compact id for a file profile."""

    name = _basename(filename or "").lower()
    payload = f"{name}|{dataset or ''}".encode("utf-8")
    return "file_" + hashlib.sha1(payload).hexdigest()[:10]


def classify_file_relationship(
    new_files: list[dict[str, Any]],
    existing_files: list[dict[str, Any]],
    user_input: str = "",
) -> dict[str, Any]:
    """Classify whether newly uploaded files belong with the current bundle."""

    if not new_files:
        return _relationship(
            status="insufficient_preview",
            confidence="low",
            evidence=[],
            uncertainties=["No new file profile is available."],
            requires_confirmation=True,
        )

    if _latest_only_requested(user_input):
        return _relationship(
            status="user_scoped_latest_only",
            confidence="high",
            evidence=["User explicitly scoped analysis to the latest uploaded file."],
            uncertainties=[],
            relationship_mode="user_scoped_latest_only",
        )

    if not existing_files:
        return _relationship(
            status="linked",
            confidence="high",
            evidence=["First available file set in the session."],
            uncertainties=[],
        )

    shared_strong_ids = _shared_fields(new_files, existing_files, STRONG_ID_FIELDS)
    shared_generic_ids = _shared_fields(new_files, existing_files, GENERIC_ID_FIELDS)
    theme_tokens = _theme_tokens(new_files) & _theme_tokens(existing_files)
    time_overlap = _has_time_overlap(new_files, existing_files)

    evidence: list[str] = []
    uncertainties: list[str] = []
    if shared_strong_ids:
        evidence.append("Shared strong key fields: " + ", ".join(shared_strong_ids))
    if theme_tokens:
        evidence.append("Shared business theme tokens: " + ", ".join(sorted(theme_tokens)))
    if time_overlap:
        evidence.append("Time ranges overlap or are compatible.")
    if shared_generic_ids:
        uncertainties.append("Only weak generic id fields overlap: " + ", ".join(shared_generic_ids))

    if shared_strong_ids and _relationship_scope_requested(user_input):
        return _relationship(
            "possibly_linked",
            "medium",
            evidence,
            ["User requested comparison, history, join, or relationship scope that can change conclusions."],
            requires_confirmation=True,
        )

    if shared_strong_ids and theme_tokens:
        return _relationship("linked", "high", evidence, uncertainties)

    if shared_strong_ids:
        return _relationship(
            "possibly_linked",
            "medium",
            evidence,
            ["Shared IDs exist but business theme evidence is unclear."],
            requires_confirmation=True,
        )

    if shared_generic_ids or theme_tokens:
        return _relationship(
            "possibly_linked",
            "low",
            evidence,
            uncertainties or ["Theme overlap exists without a strong shared key."],
            requires_confirmation=True,
        )

    return _relationship(
        "independent",
        "medium",
        ["No strong shared keys or business theme overlap detected."],
        ["User may know an external relationship not visible in the file profiles."],
        requires_confirmation=True,
        confirmation_type="file_exclusion_confirmation",
    )


def compact_bundle_summary(
    bundle: dict[str, Any],
    data_pool: list[dict[str, Any]],
    limit: int = 5,
) -> str:
    """Render a compact text summary of the active bundle files."""

    file_ids = {str(file_id) for file_id in bundle.get("file_ids", []) if file_id}
    matched_files = [
        item
        for item in data_pool
        if str(item.get("file_id") or item.get("id") or "") in file_ids
    ]

    lines = [
        f"- active_bundle: {bundle.get('bundle_id') or bundle.get('id') or '-'}",
        f"- label: {bundle.get('label') or '-'}",
        f"- version: {bundle.get('version') or 1}",
        f"- relationship_status: {bundle.get('relationship_status') or '-'}",
        "- files:",
    ]
    if not matched_files:
        lines.append("  - none")
        return "\n".join(lines)

    for item in matched_files[: max(0, limit)]:
        name = item.get("filename") or item.get("dataset") or item.get("file_id") or "-"
        rows = item.get("row_count", "?")
        cols = item.get("column_count", "?")
        keys = _ordered_profile_fields([item], ("key_fields",))[:4]
        key_summary = ", ".join(keys) if keys else "-"
        lines.append(f"  - {name}: {rows} rows x {cols} cols; keys={key_summary}")

    remaining = len(matched_files) - max(0, limit)
    if remaining > 0:
        lines.append(f"  - ... {remaining} more files")
    return "\n".join(lines)


def _relationship(
    status: str,
    confidence: str,
    evidence: list[str],
    uncertainties: list[str],
    requires_confirmation: bool = False,
    confirmation_type: str = "file_relationship_confirmation",
    relationship_mode: str = "",
) -> dict[str, Any]:
    return {
        "status": status,
        "confidence": confidence,
        "evidence": evidence,
        "uncertainties": uncertainties,
        "requires_confirmation": requires_confirmation,
        "confirmation_type": confirmation_type if requires_confirmation else "",
        "relationship_mode": relationship_mode,
    }


def _latest_only_requested(text: str) -> bool:
    lowered = (text or "").lower()
    if _relationship_scope_requested(text):
        return False
    if any(phrase in lowered for phrase in LATEST_ONLY_PHRASES):
        return True
    return bool(re.search(r"(只|仅|只用|仅用).{0,8}(最新|刚上传).{0,8}(文件|数据|表)", text or ""))


def _relationship_scope_requested(text: str) -> bool:
    lowered = (text or "").lower()
    lowered = re.sub(r"\bnot\s+(previous|historical|history)\b", "", lowered)
    lowered = re.sub(r"\bwithout\s+(previous|historical|history)\b", "", lowered)
    lowered = lowered.replace("不要历史", "").replace("不看历史", "").replace("不包含历史", "")
    return any(term in lowered for term in LATEST_ONLY_EXCLUSION_TERMS)


def _shared_fields(
    left: list[dict[str, Any]],
    right: list[dict[str, Any]],
    allowed: set[str],
) -> list[str]:
    allowed_normalized = {_normalize_field(field) for field in allowed}
    return sorted((_field_set(left) & _field_set(right)) & allowed_normalized)


def _field_set(items: list[dict[str, Any]]) -> set[str]:
    return set(_ordered_profile_fields(items, ("key_fields", "columns")))


def _ordered_profile_fields(items: list[dict[str, Any]], keys: tuple[str, ...]) -> list[str]:
    fields: list[str] = []
    seen: set[str] = set()
    for item in items:
        for key in keys:
            value = item.get(key)
            if not isinstance(value, list):
                continue
            for field in value:
                normalized = _normalize_field(field)
                if normalized and normalized not in seen:
                    fields.append(normalized)
                    seen.add(normalized)
    return fields


def _normalize_field(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[\s\-]+", "_", text)
    aliases = {
        "用户id": "user_id",
        "用户_id": "user_id",
        "会员id": "member_id",
        "会员_id": "member_id",
        "订单id": "order_id",
        "订单_id": "order_id",
        "手机号": "phone",
    }
    return aliases.get(text, text)


def _theme_tokens(items: list[dict[str, Any]]) -> set[str]:
    tokens: set[str] = set()
    for item in items:
        filename = _basename(str(item.get("filename") or ""))
        dataset = _basename(str(item.get("dataset") or ""))
        text = f"{filename} {dataset}".lower()
        for token in re.split(r"[\W_]+", text):
            if _is_business_theme_token(token):
                tokens.add(token)
        for token in CHINESE_THEME_TOKENS:
            if token in text:
                tokens.add(token)
    return tokens


def _basename(value: str) -> str:
    text = str(value or "").replace("\\", "/")
    name = PurePath(text).name
    return PureWindowsPath(name).name


def _is_business_theme_token(token: str) -> bool:
    if len(token) < 2 or token in COMMON_THEME_TOKENS:
        return False
    if token.isdigit():
        return False
    if re.fullmatch(r"\d{1,2}月", token):
        return False
    if token in {"一月", "二月", "三月", "四月", "五月", "六月", "七月", "八月", "九月", "十月", "十一月", "十二月"}:
        return False
    if re.fullmatch(r"\d{4}年?", token):
        return False
    return True


def _has_time_overlap(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> bool:
    for left_item in left:
        left_range = _time_range(left_item)
        if left_range is None:
            continue
        for right_item in right:
            right_range = _time_range(right_item)
            if right_range is None:
                continue
            left_start, left_end = left_range
            right_start, right_end = right_range
            if left_start <= right_end and right_start <= left_end:
                return True
    return False


def _time_range(item: dict[str, Any]) -> tuple[str, str] | None:
    value = item.get("time_range")
    if not isinstance(value, dict):
        return None
    start = _date_key(value.get("start"))
    end = _date_key(value.get("end"))
    if not start or not end:
        return None
    return start, end


def _date_key(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value or "").strip()


__all__ = [
    "classify_file_relationship",
    "compact_bundle_summary",
    "stable_file_id",
]
