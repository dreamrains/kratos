"""Compact multi-file eligibility and assignment planning helpers."""

from __future__ import annotations

import re
from typing import Any


MAX_SCOPE_FILES = 5

REASON_MISSING_FILE_IDENTITY = "missing_file_identity"
REASON_LOAD_FAILED = "load_failed"
REASON_MISSING_DATASET_CONTRACT = "missing_dataset_contract"
REASON_CONTRACT_BLOCKED = "contract_blocked"
REASON_AMBIGUOUS_FILE_REFERENCE = "ambiguous_file_reference"
REASON_EXPLICIT_USER_EXCLUSION = "explicit_user_exclusion"
REASON_PLAN_TASK_BINDING = "plan_task_binding"
REASON_NO_CURRENT_TASK = "no_current_task"
REASON_EXPLICIT_IN_SCOPE_PENDING_PLAN = "explicit_in_scope_pending_plan"
REASON_EXPLICIT_ALL_PENDING_PLAN = "explicit_all_pending_plan"
REASON_ELIGIBLE_NOT_YET_ASSIGNED = "eligible_not_yet_assigned"

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
    """Build a deterministic, bounded eligibility and assignment plan."""
    goal = _text(user_goal) or _text(getattr(state, "goal", ""))
    profiles = _list_items(getattr(state, "data_pool", None))
    contracts_by_id, contracts_by_dataset = _contract_indexes(state)
    profile_contracts = [
        _contract_for_profile(profile, contracts_by_id, contracts_by_dataset)
        for profile in profiles
    ]
    has_binding_contract, input_bindings = _plan_dataset_bindings(state)
    task_refs_by_index, plan_ambiguous_ids, plan_selected_ids = _resolve_plan_bindings(
        profiles,
        profile_contracts,
        input_bindings,
    )

    eligibility_by_file: dict[str, str] = {}
    for profile, contract in zip(profiles, profile_contracts):
        file_id = _file_id(profile)
        eligibility_by_file[file_id] = _eligibility(profile, contract)[0]
    eligible_ids = {
        file_id
        for file_id, eligibility in eligibility_by_file.items()
        if file_id and eligibility == "eligible"
    }
    ambiguous_ids = (
        _ambiguous_file_ids(profiles, eligible_ids, goal, selected_ids=plan_selected_ids)
        | plan_ambiguous_ids
    )

    decisions = []
    for index, (profile, contract) in enumerate(zip(profiles, profile_contracts)):
        decision = _decide_file(
            profile,
            contract=contract,
            goal=goal,
            has_binding_contract=has_binding_contract,
            task_refs=task_refs_by_index.get(index, []),
            ambiguous_file_ids=ambiguous_ids,
        )
        decision["_index"] = index
        decision["_required"] = _is_required(decision, profile, goal)
        decisions.append(decision)

    prioritized = sorted(decisions, key=_decision_priority)
    returned = [
        {key: value for key, value in item.items() if not key.startswith("_")}
        for item in prioritized[:MAX_SCOPE_FILES]
    ]

    eligible_files = [_group_ref(item) for item in returned if item["eligibility"] == "eligible"]
    used_files = [_group_ref(item) for item in returned if item["assignment"] == "used"]
    available_files = [
        _group_ref(item)
        for item in returned
        if item["assignment"] == "available" and item["eligibility"] == "eligible"
    ]
    not_needed_files = [
        _group_ref(item) for item in returned if item["assignment"] == "not_needed"
    ]
    decision_files = [
        _group_ref(item) for item in returned if item["assignment"] == "needs_decision"
    ]
    unavailable_files = [
        _group_ref(item) for item in returned if item["eligibility"] == "unavailable"
    ]

    blocked = any(
        item["eligibility"] == "unavailable"
        and item["assignment"] != "not_needed"
        and item["_required"]
        for item in decisions
    )
    has_decision = any(item["assignment"] == "needs_decision" for item in decisions)
    has_notes = any(
        item["eligibility"] == "unavailable" or item["assignment"] != "used"
        for item in decisions
    )
    if blocked:
        scope_status = "blocked"
    elif has_decision:
        scope_status = "needs_decision"
    elif has_notes:
        scope_status = "ready_with_notes"
    else:
        scope_status = "ready"

    notes = []
    if any(item["eligibility"] == "unavailable" and not item["_required"] for item in decisions):
        notes.append("Some uploaded files are unavailable but are not required by the current analysis.")
    if any(item["assignment"] == "available" and item["eligibility"] == "eligible" for item in decisions):
        notes.append("Some usable files are waiting for an explicit analysis task assignment.")
    if any(item["assignment"] == "not_needed" for item in decisions):
        notes.append("Some files are not needed by the current analysis plan or user scope.")

    total = len(decisions)
    returned_count = len(returned)
    return {
        "scope_status": scope_status,
        "goal": goal,
        "file_decisions": returned,
        "eligible_files": eligible_files,
        "used_files": used_files,
        "available_files": available_files,
        "not_needed_files": not_needed_files,
        "decision_files": decision_files,
        "unavailable_files": unavailable_files,
        "notes": notes,
        "context_budget": {
            "eligible_file_count": sum(item["eligibility"] == "eligible" for item in decisions),
            "used_file_count": sum(item["assignment"] == "used" for item in decisions),
            "available_file_count": sum(
                item["assignment"] == "available" and item["eligibility"] == "eligible"
                for item in decisions
            ),
            "not_needed_file_count": sum(item["assignment"] == "not_needed" for item in decisions),
            "decision_file_count": sum(item["assignment"] == "needs_decision" for item in decisions),
            "unavailable_file_count": sum(item["eligibility"] == "unavailable" for item in decisions),
            "total_file_count": total,
            "returned_file_count": returned_count,
            "omitted_file_count": total - returned_count,
            "max_scope_files": MAX_SCOPE_FILES,
        },
    }


def _contract_indexes(
    state: Any,
) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    by_id: dict[str, dict[str, Any]] = {}
    by_dataset: dict[str, list[dict[str, Any]]] = {}
    for contract in _contract_items(getattr(state, "dataset_contracts", None)):
        contract_id = _contract_id(contract)
        dataset = _text(contract.get("dataset"))
        if contract_id:
            by_id[contract_id] = contract
        if dataset:
            by_dataset.setdefault(dataset, []).append(contract)
    return by_id, by_dataset


def _contract_for_profile(
    profile: dict[str, Any],
    contracts_by_id: dict[str, dict[str, Any]],
    contracts_by_dataset: dict[str, list[dict[str, Any]]],
) -> dict[str, Any] | None:
    explicit_contract_id = _text(profile.get("dataset_contract_id"))
    if explicit_contract_id:
        return contracts_by_id.get(explicit_contract_id)
    candidates = contracts_by_dataset.get(_dataset(profile), [])
    file_id = _file_id(profile)
    owned = [contract for contract in candidates if _contract_owns_file(contract, file_id)]
    if len(owned) == 1:
        return owned[0]
    if len(candidates) == 1:
        return candidates[0]
    return None


def _plan_dataset_bindings(state: Any) -> tuple[bool, dict[str, list[str]]]:
    plan = getattr(state, "analysis_plan", None)
    if not isinstance(plan, dict):
        return False, {}
    method_plan = plan.get("method_plan")
    if not isinstance(method_plan, list):
        return False, {}
    has_binding_contract = False
    bindings: dict[str, list[str]] = {}
    for index, step in enumerate(method_plan, start=1):
        if not isinstance(step, dict) or "dataset_inputs" not in step:
            continue
        has_binding_contract = True
        step_id = _text(step.get("step_id")) or f"step_{index}"
        for dataset in _text_list(step.get("dataset_inputs")):
            bindings.setdefault(dataset, []).append(step_id)
    return has_binding_contract, bindings


def _resolve_plan_bindings(
    profiles: list[dict[str, Any]],
    profile_contracts: list[dict[str, Any] | None],
    input_bindings: dict[str, list[str]],
) -> tuple[dict[int, list[str]], set[str], set[str]]:
    task_refs_by_index: dict[int, list[str]] = {}
    ambiguous_file_ids: set[str] = set()
    selected_file_ids: set[str] = set()
    for dataset_input, task_refs in input_bindings.items():
        candidates = [
            index for index, profile in enumerate(profiles)
            if _file_id(profile) == dataset_input
        ]
        if not candidates:
            candidates = [
                index
                for index, (profile, contract) in enumerate(zip(profiles, profile_contracts))
                if _profile_contract_id(profile, contract) == dataset_input
            ]
        if not candidates:
            candidates = [
                index for index, profile in enumerate(profiles)
                if _dataset(profile) == dataset_input
            ]
        if len(candidates) == 1:
            task_refs_by_index.setdefault(candidates[0], []).extend(task_refs)
            selected_file_ids.add(_file_id(profiles[candidates[0]]))
        elif len(candidates) > 1:
            for index in candidates:
                task_refs_by_index.setdefault(index, []).extend(task_refs)
                file_id = _file_id(profiles[index])
                if file_id:
                    ambiguous_file_ids.add(file_id)
    return task_refs_by_index, ambiguous_file_ids, selected_file_ids


def _decide_file(
    profile: dict[str, Any],
    *,
    contract: dict[str, Any] | None,
    goal: str,
    has_binding_contract: bool,
    task_refs: list[str],
    ambiguous_file_ids: set[str],
) -> dict[str, Any]:
    file_id = _file_id(profile)
    eligibility, eligibility_reason_code, eligibility_reason = _eligibility(profile, contract)
    decision = _file_summary(profile, contract)
    assignment = "available"
    reason_code = eligibility_reason_code
    reason = eligibility_reason
    confidence = "high" if eligibility == "unavailable" else "medium"

    if _goal_excludes_profile(profile, goal):
        assignment = "not_needed"
        reason_code = REASON_EXPLICIT_USER_EXCLUSION
        reason = "The user explicitly excluded this file from the current analysis."
        confidence = "high"
    elif eligibility == "eligible" and file_id in ambiguous_file_ids:
        assignment = "needs_decision"
        reason_code = REASON_AMBIGUOUS_FILE_REFERENCE
        reason = "The request matches multiple usable files and needs one explicit selection."
        confidence = "high"
    elif eligibility == "eligible" and task_refs:
        assignment = "used"
        reason_code = REASON_PLAN_TASK_BINDING
        reason = "The current AnalysisPlan binds this file to an analysis task."
        confidence = "high"
    elif eligibility == "eligible" and has_binding_contract:
        assignment = "not_needed"
        reason_code = REASON_NO_CURRENT_TASK
        reason = "The current AnalysisPlan does not need this usable file."
        confidence = "high"
    elif eligibility == "eligible" and _goal_mentions_profile(profile, goal):
        reason_code = REASON_EXPLICIT_IN_SCOPE_PENDING_PLAN
        reason = "The file is explicitly in scope and is waiting for an analysis task binding."
        confidence = "high"
    elif eligibility == "eligible" and _goal_requests_all_files(goal):
        reason_code = REASON_EXPLICIT_ALL_PENDING_PLAN
        reason = "The user requested all files; this usable file is waiting for a task binding."
        confidence = "high"

    decision.update({
        "eligibility": eligibility,
        "assignment": assignment,
        "reason_code": reason_code,
        "reason": reason,
        "confidence": confidence,
        "task_refs": list(task_refs),
    })
    return decision


def _eligibility(
    profile: dict[str, Any],
    contract: dict[str, Any] | None,
) -> tuple[str, str, str]:
    if not _file_id(profile) or not _dataset(profile):
        return (
            "unavailable",
            REASON_MISSING_FILE_IDENTITY,
            "The file cannot be identified as a usable dataset.",
        )
    status = _normalize_alias(_text(profile.get("status")))
    if status in {"failed", "error", "unavailable", "unreadable"}:
        return (
            "unavailable",
            REASON_LOAD_FAILED,
            "The file could not be loaded or inspected.",
        )
    if contract is None:
        return (
            "unavailable",
            REASON_MISSING_DATASET_CONTRACT,
            "The file has no usable dataset contract.",
        )
    quality = contract.get("quality") if isinstance(contract.get("quality"), dict) else {}
    contract_status = _normalize_alias(
        _text(contract.get("quality_status") or quality.get("status"))
    )
    if contract_status == "blocked":
        return (
            "unavailable",
            REASON_CONTRACT_BLOCKED,
            "The dataset contract blocks analysis until data quality is repaired.",
        )
    return (
        "eligible",
        REASON_ELIGIBLE_NOT_YET_ASSIGNED,
        "The file is loaded and has a usable dataset contract.",
    )


def _file_summary(
    profile: dict[str, Any],
    contract: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "file_id": _file_id(profile),
        "filename": _text(profile.get("filename") or profile.get("name")),
        "dataset": _dataset(profile),
        "dataset_contract_id": _profile_contract_id(profile, contract),
        "grain": infer_file_grain(profile)["grain"],
        "canonical_fields": canonical_entity_fields(profile),
    }


def _decision_priority(item: dict[str, Any]) -> tuple[int, int]:
    if item["assignment"] == "needs_decision":
        priority = 0
    elif item["eligibility"] == "unavailable" and item["_required"]:
        priority = 1
    elif item["assignment"] == "used":
        priority = 2
    elif item["assignment"] == "available" and item["eligibility"] == "eligible":
        priority = 3
    elif item["assignment"] == "not_needed":
        priority = 4
    else:
        priority = 5
    return priority, item["_index"]


def _is_required(decision: dict[str, Any], profile: dict[str, Any], goal: str) -> bool:
    if decision["assignment"] == "not_needed":
        return False
    return bool(decision["task_refs"]) or _goal_mentions_profile(profile, goal) or _goal_requests_all_files(goal)


def _ambiguous_file_ids(
    profiles: list[dict[str, Any]],
    eligible_ids: set[str],
    goal: str,
    *,
    selected_ids: set[str] | None = None,
) -> set[str]:
    uniquely_named = {
        _file_id(profile)
        for profile in profiles
        if _file_id(profile) in eligible_ids
        and _goal_contains_alias(goal, _file_id(profile))
    }
    uniquely_named.update(selected_ids or set())
    aliases: dict[str, list[str]] = {}
    for profile in profiles:
        file_id = _file_id(profile)
        if file_id not in eligible_ids:
            continue
        for alias in _profile_aliases(profile):
            if alias and _goal_contains_alias(goal, alias):
                aliases.setdefault(_normalize_alias(alias), []).append(file_id)
    result: set[str] = set()
    for file_ids in aliases.values():
        candidate_ids = set(file_ids)
        if len(candidate_ids) > 1 and not candidate_ids.intersection(uniquely_named):
            result.update(candidate_ids)
    return result


def _profile_aliases(profile: dict[str, Any]) -> list[str]:
    filename = _text(profile.get("filename") or profile.get("name"))
    stem = re.sub(r"\.[^.]+$", "", filename)
    values = [_file_id(profile), filename, stem, _dataset(profile)]
    return _dedupe([value for value in values if value])


def _goal_mentions_profile(profile: dict[str, Any], goal: str) -> bool:
    return any(_goal_contains_alias(goal, alias) for alias in _profile_aliases(profile))


def _goal_requests_all_files(goal: str) -> bool:
    phrases = (
        "all uploaded files",
        "all files",
        "all uploaded data",
        "uploaded files",
        "uploaded data",
        "全部上传文件",
        "所有上传文件",
        "全部文件",
        "所有文件",
    )
    return any(_goal_contains_alias(goal, phrase) for phrase in phrases)


def _goal_excludes_profile(profile: dict[str, Any], goal: str) -> bool:
    for alias in _profile_aliases(profile):
        alias_pattern = _alias_pattern(alias)
        if not alias_pattern:
            continue
        prefix = (
            r"(?:exclude|ignore|skip|do\s+not\s+use|don't\s+use|"
            r"do\s+not\s+analy[sz]e|don't\s+analy[sz]e)"
            r"(?:\s+(?:the|this|that|uploaded|named|called|data|dataset|file))*\s+"
        )
        suffix = (
            r"(?:\s+(?:file|dataset|data))?\s+"
            r"(?:should\s+be\s+)?(?:excluded|ignored|skipped)"
        )
        if re.search(prefix + alias_pattern, goal, flags=re.IGNORECASE):
            return True
        if re.search(alias_pattern + suffix, goal, flags=re.IGNORECASE):
            return True

        normalized_goal = _normalize_alias(goal)
        normalized_alias = _normalize_alias(alias)
        position = normalized_goal.find(normalized_alias)
        while position >= 0:
            before = normalized_goal[max(0, position - 24):position]
            after_start = position + len(normalized_alias)
            after = normalized_goal[after_start:after_start + 16]
            if before.endswith(("排除", "忽略", "不要使用", "不分析")):
                return True
            if after.startswith(("排除", "忽略", "不分析")):
                return True
            position = normalized_goal.find(normalized_alias, position + 1)
    return False


def _goal_contains_alias(goal: str, alias: str) -> bool:
    pattern = _alias_pattern(alias)
    if not pattern:
        return False
    if _contains_cjk(alias):
        return _normalize_alias(alias) in _normalize_alias(goal)
    return re.search(pattern, goal, flags=re.IGNORECASE) is not None


def _alias_pattern(alias: str) -> str:
    value = _text(alias)
    if not value:
        return ""
    escaped = re.escape(value)
    escaped = re.sub(r"\\\s+", r"\\s+", escaped)
    return rf"(?<![A-Za-z0-9_]){escaped}(?![A-Za-z0-9_])"


def _contains_cjk(value: str) -> bool:
    return re.search(r"[\u3400-\u9fff]", value) is not None


def _group_ref(item: dict[str, Any]) -> dict[str, str]:
    return {
        "file_id": _text(item.get("file_id")),
        "filename": _text(item.get("filename")),
        "dataset": _text(item.get("dataset")),
        "reason_code": _text(item.get("reason_code")),
    }


def _file_id(profile: dict[str, Any]) -> str:
    return _text(profile.get("file_id") or profile.get("id"))


def _dataset(profile: dict[str, Any]) -> str:
    return _text(profile.get("dataset") or profile.get("dataset_name"))


def _contract_id(contract: dict[str, Any] | None) -> str:
    contract = contract or {}
    return _text(
        contract.get("id")
        or contract.get("contract_id")
        or contract.get("dataset_contract_id")
    )


def _profile_contract_id(
    profile: dict[str, Any],
    contract: dict[str, Any] | None,
) -> str:
    return _text(profile.get("dataset_contract_id")) or _contract_id(contract)


def _contract_owns_file(contract: dict[str, Any], file_id: str) -> bool:
    if not file_id:
        return False
    owner = _text(
        contract.get("file_id")
        or contract.get("source_file_id")
        or contract.get("data_file_id")
    )
    return owner == file_id or file_id in _text_list(contract.get("file_ids"))


def _contract_items(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if not isinstance(value, dict):
        return []
    if any(key in value for key in ("dataset", "id", "contract_id", "quality_status")):
        return [value]
    result = []
    for key, item in value.items():
        if not isinstance(item, dict):
            continue
        contract = dict(item)
        contract.setdefault("id", _text(key))
        result.append(contract)
    return result


def _profile_fields(profile: dict[str, Any]) -> list[str]:
    fields: list[str] = []
    for key in ("columns", "key_fields", "time_fields"):
        fields.extend(_text_list(profile.get(key)))
    return _dedupe(fields)


def _matching_fields(fields: list[str], aliases: set[str]) -> list[str]:
    normalized_aliases = {_normalize_alias(alias) for alias in aliases}
    return [field for field in fields if _normalize_alias(field) in normalized_aliases]


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
