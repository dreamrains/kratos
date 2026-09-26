"""Deterministic hypothesis records for supported analysis routes."""

from __future__ import annotations

import json
import math
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from data_agent.agent.artifact_refs import hydrate_refs
from data_agent.config import get_config


# Relation vocabulary for model-proposed, host-validated evidence relations.
_RELATION_TYPES = ("supports", "refutes")
_OBSERVED_DIRECTIONS = ("increased", "decreased", "flat")
_TAG_CLAIM_TYPES = {"primary": "descriptive", "alternative": "causal", "baseline": "statistical"}
_DECIDED_STATUSES = {"supported", "refuted", "contested"}


def build_hypothesis_set(user_input: str, entry_decision: Any, state: Any) -> dict[str, Any]:
    """Build a deterministic hypothesis set from entry routing and trust state."""
    decision = entry_decision if isinstance(entry_decision, dict) else {}
    contracts = hydrate_refs(_list_attr(state, "dataset_contracts"))
    dataset = _text(decision.get("dataset")) or _first_dataset(contracts)
    route = _text(decision.get("route"))
    if not route and _text(decision.get("decision")) == "request_data":
        route = "user_level_retention"
    plan_id = _current_plan_id(state)
    contract = _contract_for_dataset(contracts, dataset)
    field_roles = _field_roles(contract)
    limitations = _text_list(decision.get("limitations"))
    set_id = f"hypotheses_{_slug(dataset or 'dataset')}_{_slug(route or 'analysis')}"
    if plan_id:
        # Hypothesis identity is plan-scoped: a new analysis plan on the same
        # dataset/route must start from fresh statuses instead of inheriting
        # the previous plan's conclusions.
        set_id = f"{set_id}_{_slug(plan_id)}"

    if _text(decision.get("decision")) == "request_data" or route == "user_level_retention":
        hypotheses = [_unsupported_hypothesis(set_id, dataset, route, limitations, field_roles)]
    else:
        hypotheses = _route_templates(set_id, dataset, route, field_roles, limitations)

    payload = {
        "id": set_id,
        "user_input": _text(user_input),
        "dataset": dataset,
        "route": route,
        "plan_id": plan_id,
        "hypotheses": hypotheses,
    }
    payload["status_summary"] = _status_summary(hypotheses)
    return payload


def persist_hypothesis_set(session_id: str, hypothesis_set: dict[str, Any]) -> dict[str, Any]:
    """Persist a full hypothesis set artifact and return a compact ref."""
    hypothesis_set_id = _text(hypothesis_set.get("id")) or "hypotheses_analysis"
    path = _artifact_path(session_id, hypothesis_set_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(hypothesis_set, ensure_ascii=False, indent=2), encoding="utf-8")
    hypotheses = _list_items(hypothesis_set.get("hypotheses"))
    return {
        "id": hypothesis_set_id,
        "dataset": _text(hypothesis_set.get("dataset")),
        "route": _text(hypothesis_set.get("route")),
        "plan_id": _text(hypothesis_set.get("plan_id")),
        "count": len(hypotheses),
        "status_summary": _status_summary(hypotheses),
        "artifact_path": str(path),
    }


def hydrate_hypothesis_refs(refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Hydrate compact hypothesis refs from their JSON artifacts."""
    return hydrate_refs(refs)


def _measurement_direction(measurement: dict[str, Any]) -> str:
    """Deterministic direction from structured measurement fields.

    Non-finite deltas (NaN/inf) carry no comparable direction and count as
    unknown, so no relation can be decided from them.
    """
    import math

    for key in ("delta", "change", "total_change", "pct_change"):
        value = measurement.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if not math.isfinite(value):
                return "unknown"
            if value > 0:
                return "increased"
            if value < 0:
                return "decreased"
            return "flat"
    direction = measurement.get("direction")
    if isinstance(direction, str) and direction.strip().lower() in _OBSERVED_DIRECTIONS:
        return direction.strip().lower()
    return "unknown"


def _relation_proposals(record: dict[str, Any]) -> list[dict[str, Any]]:
    proposals = []
    for entry in record.get("competing_hypotheses") or []:
        if (
            isinstance(entry, dict)
            and str(entry.get("hypothesis_id") or "") .strip()
            and entry.get("relation") in _RELATION_TYPES
        ):
            proposals.append(entry)
    return proposals


def _validate_relation(
    entry: dict[str, Any],
    hypothesis: dict[str, Any],
    record: dict[str, Any],
    verified_measurements: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any] | None, str]:
    """Host-side gate for a model-proposed evidence relation.

    The relation label is only a proposal. The host decides from the
    hypothesis's frozen decision rule and this evidence: the metric must be
    one of the hypothesis's target metrics, the claimed direction must match
    the measured direction, the claim type must be decidable from this
    evidence's method, and for a directional ("changed") predicate the label
    must equal what the measurement implies. A rejected proposal returns
    (None, reason) and is retained as an undetermined candidate.
    """
    metric = _text(entry.get("metric"))
    observed = _text(entry.get("observed")).lower()
    if not metric or observed not in _OBSERVED_DIRECTIONS:
        return None, "invalid_relation_shape"
    rule = hypothesis.get("decision_rule") if isinstance(hypothesis.get("decision_rule"), dict) else {}
    target_metrics = {
        _text(item) for item in (rule.get("metrics") or []) if _text(item)
    }
    if target_metrics and metric not in target_metrics:
        # Another metric's movement can never decide this hypothesis.
        return None, "metric_not_target"
    measurements = [
        measurement
        for measurement in (record.get("measurements") or [])
        if isinstance(measurement, dict) and _text(measurement.get("metric")) == metric
    ]
    if not measurements:
        return None, "metric_missing_in_evidence"
    # Model fields can disqualify a contradictory proposal, but never prove
    # one true. Keep the old direction-conflict RED without granting support.
    if "delta" in measurements[0] and _finite_decimal(measurements[0]["delta"]) is None:
        return None, "direction_unknown"
    reported_direction = _measurement_direction(measurements[0])
    if reported_direction != "unknown" and reported_direction != observed:
        return None, "direction_mismatch"
    predicate = _text(rule.get("predicate"))
    if predicate == "changed" and reported_direction != "unknown":
        implied = "supports" if reported_direction in {"increased", "decreased"} else "refutes"
        if str(entry.get("relation")) != implied:
            return None, f"relation_predicate_mismatch:changed_implies_{implied}"
    verified = verified_measurements.get(metric)
    if not isinstance(verified, dict):
        return None, "measurement_not_receipt_verified"
    candidate = measurements[0]
    reported = _finite_decimal(candidate.get("delta") if "delta" in candidate else candidate.get("value"))
    actual = _finite_decimal(verified.get("value"))
    if reported is None or actual is None or abs(reported - actual) > Decimal("0.00015"):
        return None, "measurement_value_mismatch"
    computed = verified.get("direction")
    if candidate.get("direction") not in (None, "", computed):
        return None, "direction_mismatch"
    if computed == "unknown":
        return None, "direction_unknown"
    if computed != observed:
        return None, "direction_mismatch"
    claim_type = _text(hypothesis.get("claim_type")) or "descriptive"
    if claim_type != "descriptive":
        # A descriptive slope/difference receipt cannot validate a causal or
        # inferential hypothesis merely because the model labels its method so.
        return None, "inferential_relation_not_receipt_verified"
    if predicate == "changed":
        # A changed/trend claim: any non-flat comparable delta supports it,
        # only a flat delta refutes it. The model's label must agree.
        implied = "supports" if computed in {"increased", "decreased"} else "refutes"
        if str(entry.get("relation")) != implied:
            return None, f"relation_predicate_mismatch:changed_implies_{implied}"
    return {
        "evidence_id": _text(record.get("id")),
        "relation": str(entry.get("relation")),
        "metric": metric,
        "observed": observed,
        "receipt_id": verified.get("receipt_id"),
        "basis": f"receipt-verified {metric} direction = {observed}",
    }, ""


def _finite_decimal(value: Any) -> Decimal | None:
    if isinstance(value, bool):
        return None
    if len(str(value)) > 80:
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return number if number.is_finite() else None


def receipt_verified_hypothesis_measurements(
    state: Any, evidence_records: list[dict[str, Any]],
) -> dict[str, dict[str, dict[str, Any]]]:
    """Verify descriptive relation values against current immutable tool results.

    This reads the existing receipt detail through its digest/version checker;
    model-filled EvidenceRecord values only become comparable candidates.
    Missing context, stale data, ambiguous receipts and unsupported methods
    leave the relation unassessed rather than inventing a new result source.
    """
    from data_agent.agent.context import get_current_context
    from data_agent.tools.result_reference import load_result_reference

    context = get_current_context()
    if context is None or getattr(context, "analysis_state", None) is not state:
        return {}
    receipts = {
        str(receipt.get("id")): receipt for receipt in getattr(state, "tool_receipts", []) or []
        if isinstance(receipt, dict) and receipt.get("id")
    }
    verified: dict[str, dict[str, dict[str, Any]]] = {}
    seen_evidence_ids: set[str] = set()
    for record in evidence_records:
        if not isinstance(record, dict):
            continue
        evidence_id = str(record.get("id") or "")
        ids = record.get("tool_receipt_ids")
        bindings = record.get("result_bindings")
        if evidence_id in seen_evidence_ids:
            verified.pop(evidence_id, None)
            continue
        seen_evidence_ids.add(evidence_id)
        if (not evidence_id or not isinstance(ids, list) or not ids
                or any(not isinstance(item, str) for item in ids) or len(ids) != len(set(ids))
                or not isinstance(bindings, list) or len(bindings) != len(ids)):
            continue
        binding_by_id = {
            str(binding.get("receipt_id")): binding for binding in bindings
            if isinstance(binding, dict) and binding.get("receipt_id")
        }
        if len(binding_by_id) != len(ids) or set(binding_by_id) != set(ids):
            continue
        checked: dict[str, dict[str, Any]] = {}
        ambiguous: set[str] = set()
        for receipt_id in ids:
            receipt = receipts.get(receipt_id)
            if not receipt or receipt.get("tool_name") not in {"compare_periods", "analyze_time_series"}:
                continue
            identity = receipt.get("structured_result_sha256")
            binding = binding_by_id[receipt_id]
            args = receipt.get("arguments")
            if (not identity or binding.get("result_sha256") != identity
                    or binding.get("data_identities") != receipt.get("data_identities")
                    or not isinstance(args, dict) or args.get("name") != record.get("dataset")):
                continue
            reference = str((receipt.get("detail_ref") or {}).get("path") or "")
            if not reference:
                continue
            try:
                result, loaded = load_result_reference(reference, expected_receipt_id=receipt_id)
            except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError):
                continue
            if (not isinstance(result, dict) or loaded.get("result_sha256") != identity
                    or loaded.get("data_identities") != receipt.get("data_identities")):
                continue
            measurements = record.get("measurements")
            if not isinstance(measurements, list):
                continue
            for measurement in measurements:
                if not isinstance(measurement, dict):
                    continue
                metric = measurement.get("metric")
                if not isinstance(metric, str) or not metric or metric in ambiguous:
                    continue
                value = None
                direction = None
                if receipt["tool_name"] == "compare_periods":
                    metrics = result.get("metrics")
                    item = metrics.get(metric) if isinstance(metrics, dict) else None
                    if isinstance(item, dict):
                        a, b, diff = (_finite_decimal(item.get(key)) for key in ("period_a", "period_b", "diff"))
                        if (a is not None and b is not None and diff is not None
                                and abs(b - a - diff) <= Decimal("0.00015")):
                            value = diff
                else:
                    inferred = result.get("inferred_columns")
                    selected_col = args.get("target_col") or args.get("value_col") or (
                        inferred if isinstance(inferred, dict) else {}
                    ).get("value_col")
                    trend = result.get("trend")
                    if metric == selected_col and isinstance(trend, dict):
                        value = _finite_decimal(trend.get("slope"))
                        direction = {"up": "increased", "down": "decreased", "flat": "flat"}.get(trend.get("direction"))
                if value is None:
                    continue
                inferred_direction = "increased" if value > 0 else "decreased" if value < 0 else "flat"
                if direction is not None and direction != inferred_direction:
                    continue
                direction = inferred_direction
                reported = _finite_decimal(measurement.get("delta") if "delta" in measurement else measurement.get("value"))
                if reported is None or abs(reported - value) > Decimal("0.00015"):
                    continue
                if measurement.get("direction") not in (None, "", direction):
                    continue
                if metric in checked:
                    ambiguous.add(metric)
                    checked.pop(metric, None)
                    continue
                checked[metric] = {"value": str(value), "direction": direction, "receipt_id": receipt_id}
        if checked:
            verified[evidence_id] = checked
    return verified


def update_hypotheses_from_evidence(
    hypothesis_set: dict[str, Any],
    evidence_records: list[dict[str, Any]],
    *,
    verified_measurements: dict[str, dict[str, dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Recompute hypothesis relations from the current evidence snapshot.

    Text overlap only marks a candidate association (``related_evidence_ids``).
    A hypothesis changes state only through structured, host-validated
    relations: metric present, measured direction matching the proposal, and
    the claim type decidable from this evidence's method. Supporting and
    conflicting ids are recomputed on every call; a previously decided
    hypothesis whose relations all disappear becomes ``stale`` instead of
    silently reverting.
    """
    updated = dict(hypothesis_set)
    verified_measurements = verified_measurements or {}
    set_plan = _text(hypothesis_set.get("plan_id"))
    set_dataset = _text(hypothesis_set.get("dataset"))
    scoped = [
        record
        for record in evidence_records
        if isinstance(record, dict)
        and _evidence_in_scope(record, set_plan, set_dataset)
    ]
    hypotheses: list[dict[str, Any]] = []
    for hypothesis in _list_items(hypothesis_set.get("hypotheses")):
        item = dict(hypothesis)
        if item.get("status") == "unsupported_by_data":
            hypotheses.append(item)
            continue

        related_ids = [
            evidence_id
            for evidence_id in (
                _text(record.get("id"))
                for record in scoped
                if _evidence_relates_to_claim(item.get("claim"), record)
            )
            if evidence_id
        ]
        relations = []
        candidates = []
        for record in scoped:
            for proposal in _relation_proposals(record):
                if _text(proposal.get("hypothesis_id")) != _text(item.get("id")):
                    continue
                validated, reason = _validate_relation(
                    proposal, item, record, verified_measurements.get(_text(record.get("id")), {}),
                )
                if validated is not None:
                    relations.append(validated)
                else:
                    # A well-formed but rejected proposal stays visible as an
                    # undetermined candidate with its rejection reason.
                    candidates.append({
                        "evidence_id": _text(record.get("id")),
                        "relation": str(proposal.get("relation") or ""),
                        "metric": _text(proposal.get("metric")),
                        "observed": _text(proposal.get("observed")),
                        "reason": reason,
                    })
        supporting_ids = [relation["evidence_id"] for relation in relations if relation["relation"] == "supports"]
        conflicting_ids = [relation["evidence_id"] for relation in relations if relation["relation"] == "refutes"]

        previous_status = _text(item.get("status"))
        item["related_evidence_ids"] = related_ids
        item["relation_candidates"] = candidates
        item["evidence_relations"] = relations
        # Recomputed from scratch: ids from a previous run never survive on
        # their own.
        item["supporting_evidence_ids"] = supporting_ids
        item["conflicting_evidence_ids"] = conflicting_ids
        if supporting_ids and conflicting_ids:
            item["status"] = "contested"
        elif supporting_ids:
            item["status"] = "supported"
        elif conflicting_ids:
            item["status"] = "refuted"
        elif related_ids or relations or item.get("verification_level") in {"verifiable", "partially_verifiable"}:
            item["status"] = "inconclusive"
        else:
            item["status"] = "proposed"
        if (
            previous_status in _DECIDED_STATUSES
            and not supporting_ids
            and not conflicting_ids
            and not related_ids
        ):
            # 依赖证据全部失效：保留历史语义，标记失效而不是退回候选。
            item["status"] = "stale"
        hypotheses.append(item)

    updated["hypotheses"] = hypotheses
    updated["status_summary"] = _status_summary(hypotheses)
    return updated


_STATUS_LABELS = {
    "supported": "已获结构化证据支持",
    "refuted": "被结构化证据反驳",
    "contested": "支持与反证冲突未决",
    "inconclusive": "未决",
    "proposed": "候选",
    "stale": "失效（依赖证据不再存在）",
    "unsupported_by_data": "当前数据不能检验",
}


def hypotheses_prompt_brief(state: Any, hydrated: list[dict[str, Any]] | None = None) -> str:
    """Bounded competing-hypothesis brief for answer synthesis.

    Each hypothesis carries its current status, its structured evidence, and
    for undecided explanations the distinguishing evidence still required.
    No entry may claim an exclusion that the statuses do not support.
    """
    if hydrated is None:
        hydrated = hydrate_hypothesis_refs(_list_attr(state, "hypothesis_sets"))
    lines: list[str] = []
    for hypothesis_set in hydrated[:2]:
        heading = _text(hypothesis_set.get("id")) or "hypotheses"
        lines.append(f"- 假设集 {heading}（{_text(hypothesis_set.get('dataset'))}/{_text(hypothesis_set.get('route'))}）：")
        for hypothesis in _list_items(hypothesis_set.get("hypotheses"))[:4]:
            hypothesis_id = _text(hypothesis.get("id"))
            status = _text(hypothesis.get("status")) or "proposed"
            label = _STATUS_LABELS.get(status, status)
            claim = _text(hypothesis.get("claim"))[:120]
            detail = ""
            if status in {"supported", "contested"}:
                ids = ", ".join(_text_list(hypothesis.get("supporting_evidence_ids"))[:3])
                detail = f"；支持证据: {ids or '-'}"
            if status in {"refuted", "contested"}:
                ids = ", ".join(_text_list(hypothesis.get("conflicting_evidence_ids"))[:3])
                detail += f"；反证: {ids or '-'}"
            if status in {"inconclusive", "proposed", "unsupported_by_data"}:
                required_fields = [
                    _text(requirement.get("field"))
                    for requirement in _list_items(hypothesis.get("evidence_requirements"))
                    if _text(requirement.get("field"))
                ][:3]
                required = ", ".join(required_fields)
                detail = f"；未决，需区分性证据：{required or '按假设要求补齐字段/方法'}"
                # Give the one-shot repair round the validator's exact metric
                # mismatch; a generic "no relation" message hid this in R3 M04.
                for candidate in _list_items(hypothesis.get("relation_candidates"))[:2]:
                    if candidate.get("reason") != "metric_missing_in_evidence":
                        continue
                    record = next((
                        record for record in _list_attr(state, "evidence_records")
                        if isinstance(record, dict)
                        and _text(record.get("id")) == _text(candidate.get("evidence_id"))
                        and _text(record.get("plan_id")) == _text(hypothesis_set.get("plan_id"))
                        and _text(record.get("dataset")) == _text(hypothesis_set.get("dataset"))
                    ), None)
                    if record is None:
                        continue
                    measured = sorted({
                        _text(value.get("metric"))[:80]
                        for value in _list_items(record.get("measurements"))
                        if _text(value.get("metric"))
                    })[:3]
                    detail += (
                        f"；metric_missing_in_evidence: proposal={_text(candidate.get('metric'))[:80]}, "
                        f"evidence_metrics={','.join(measured) or '-'}；关系仍为未决"
                    )
            lines.append(f"  - id={hypothesis_id} [{label}|{status}] {claim}{detail}")
    if not lines:
        return ""
    lines.append(
        "  未决的解释必须如实标注并说明所需区分性证据；不得虚构排除结论。"
    )
    return "<competing_hypotheses>\n" + "\n".join(lines) + "\n</competing_hypotheses>"


def _route_templates(
    set_id: str,
    dataset: str,
    route: str,
    field_roles: dict[str, list[str]],
    limitations: list[str],
) -> list[dict[str, Any]]:
    metric = _first_role(field_roles, "metrics") or _first_role(field_roles, "rate_metrics") or "metric"
    date = _first_role(field_roles, "date") or "date"
    dimension = _first_role(field_roles, "dimensions")
    secondary_metric = _secondary_role(field_roles, "metrics", metric)
    rate_metric = _first_role(field_roles, "rate_metrics")

    if route == "period_compare":
        specs = [
            (
                f"{metric} changed between the compared periods in {dataset}.",
                [{"kind": "metric", "field": metric, "required": True}, {"kind": "date", "field": date, "required": True}],
                ["primary"],
            ),
            (
                f"{metric} changed because {secondary_metric or rate_metric or 'volume'} moved between periods.",
                _requirements([
                    ("metric", metric, True),
                    ("metric", secondary_metric or rate_metric or "", bool(secondary_metric or rate_metric)),
                    ("date", date, True),
                ]),
                ["alternative"],
            ),
            (
                f"{metric} changed because {dimension or 'a segment'} mix shifted between periods.",
                _requirements([
                    ("metric", metric, True),
                    ("dimension", dimension or "", bool(dimension)),
                    ("date", date, True),
                ]),
                ["alternative"],
            ),
            (
                f"{metric} movement is consistent with normal baseline variation between periods.",
                [{"kind": "metric", "field": metric, "required": True}, {"kind": "date", "field": date, "required": True}],
                ["baseline"],
            ),
        ]
    elif route == "trend":
        specs = [
            (
                f"{metric} has a directional trend over time in {dataset}.",
                [{"kind": "metric", "field": metric, "required": True}, {"kind": "date", "field": date, "required": True}],
                ["primary"],
            ),
            (
                f"{metric} trend is explained by {secondary_metric or rate_metric or 'another metric'} movement over time.",
                _requirements([
                    ("metric", metric, True),
                    ("metric", secondary_metric or rate_metric or "", bool(secondary_metric or rate_metric)),
                    ("date", date, True),
                ]),
                ["alternative"],
            ),
            (
                f"{metric} trend is concentrated in {dimension or 'one segment'} rather than broad-based.",
                _requirements([
                    ("metric", metric, True),
                    ("dimension", dimension or "", bool(dimension)),
                    ("date", date, True),
                ]),
                ["alternative"],
            ),
            (
                f"{metric} changes are consistent with baseline noise over time.",
                [{"kind": "metric", "field": metric, "required": True}, {"kind": "date", "field": date, "required": True}],
                ["baseline"],
            ),
        ]
    else:
        specs = [
            (
                f"{metric} can be evaluated for the requested {route or 'analysis'} route.",
                [{"kind": "metric", "field": metric, "required": True}],
                ["primary"],
            ),
            (
                f"{metric} may vary by {dimension or 'available segment'}.",
                _requirements([("metric", metric, True), ("dimension", dimension or "", bool(dimension))]),
                ["alternative"],
            ),
            (
                f"{metric} movement may reflect baseline variation.",
                [{"kind": "metric", "field": metric, "required": True}],
                ["baseline"],
            ),
        ]

    hypotheses = []
    for index, (claim, requirements, tags) in enumerate(specs[:4], 1):
        hypotheses.append(_hypothesis(
            set_id,
            index,
            dataset,
            route,
            claim,
            requirements,
            field_roles,
            "proposed",
            limitations,
            tags,
        ))
    return hypotheses


def _unsupported_hypothesis(
    set_id: str,
    dataset: str,
    route: str,
    limitations: list[str],
    field_roles: dict[str, list[str]],
) -> dict[str, Any]:
    requirements = [
        {"kind": "id", "field": "user_id", "required": True},
    ]
    return _hypothesis(
        set_id,
        1,
        dataset,
        route or "user_level_retention",
        "User-level retention is not verifiable from the current aggregate dataset.",
        requirements,
        field_roles,
        "unsupported_by_data",
        limitations,
        ["primary", "unsupported"],
    )


def _decision_rule(
    claim: str,
    claim_type: str,
    tags: list[str],
    requirements: list[dict[str, Any]],
) -> dict[str, Any]:
    """Frozen, host-computable decision inputs for this hypothesis.

    ``metrics`` are the target metrics this hypothesis is about: a relation
    on any other metric can never change its state. ``predicate`` states the
    directional claim where applicable ("changed"): the relation label must
    match what the measured direction implies, so a model-proposed label
    alone cannot decide the hypothesis.
    """
    metrics = [
        _text(requirement.get("field"))
        for requirement in requirements
        if isinstance(requirement, dict)
        and requirement.get("kind") in {"metric", "rate_metric"}
        and requirement.get("required") is True
        and _text(requirement.get("field"))
    ]
    predicate = ""
    if claim_type == "descriptive" and tags and tags[0] == "primary":
        claim_lower = claim.lower()
        if "changed" in claim_lower or "trend" in claim_lower:
            predicate = "changed"
    return {"metrics": metrics, "predicate": predicate}


def _hypothesis(
    set_id: str,
    index: int,
    dataset: str,
    route: str,
    claim: str,
    requirements: list[dict[str, Any]],
    field_roles: dict[str, list[str]],
    status: str,
    limitations: list[str],
    tags: list[str],
) -> dict[str, Any]:
    claim_type = _TAG_CLAIM_TYPES.get(tags[0], "descriptive") if tags else "descriptive"
    return {
        "id": f"{set_id}_h{index}",
        "dataset": dataset,
        "route": route,
        "claim": claim,
        "status": status,
        "claim_type": claim_type,
        "decision_rule": _decision_rule(claim, claim_type, tags, requirements),
        "verification_level": _verification_level(requirements, field_roles),
        "evidence_requirements": requirements,
        "related_evidence_ids": [],
        "evidence_relations": [],
        "supporting_evidence_ids": [],
        "conflicting_evidence_ids": [],
        "limitations": limitations,
        "tags": tags,
    }


def _field_roles(contract: dict[str, Any]) -> dict[str, list[str]]:
    roles = contract.get("field_roles") if isinstance(contract, dict) else {}
    if not isinstance(roles, dict):
        return {}
    return {str(key): _text_list(value) for key, value in roles.items()}


def _verification_level(requirements: list[dict[str, Any]], field_roles: dict[str, list[str]]) -> str:
    required_fields = [
        _text(requirement.get("field"))
        for requirement in requirements
        if isinstance(requirement, dict) and requirement.get("required") is True and _text(requirement.get("field"))
    ]
    if not required_fields:
        return "not_verifiable"
    available = {field for fields in field_roles.values() for field in fields}
    present = sum(1 for field in required_fields if field in available)
    if present == len(required_fields):
        return "verifiable"
    if present:
        return "partially_verifiable"
    return "not_verifiable"


def _status_summary(hypotheses: list[dict[str, Any]]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for hypothesis in hypotheses:
        status = _text(hypothesis.get("status")) or "unknown"
        summary[status] = summary.get(status, 0) + 1
    return summary


def _artifact_path(session_id: str, hypothesis_set_id: str) -> Path:
    return get_config().sessions_resolved / session_id / "tool_outputs" / f"{hypothesis_set_id}.json"


def _current_plan_id(state: Any) -> str:
    for attr_name in ("analysis_plan", "analysis_spec"):
        plan = getattr(state, attr_name, None)
        if isinstance(plan, dict):
            plan_id = _text(plan.get("id"))
            if plan_id:
                return plan_id
    return ""


def _evidence_in_scope(record: dict[str, Any], set_plan: str, set_dataset: str) -> bool:
    """Evidence must belong to this hypothesis set's plan and dataset.

    Records from another plan or dataset stay untouched by this set, even when
    their text matches a hypothesis claim verbatim.
    """
    if set_plan and _text(record.get("plan_id")) != set_plan:
        return False
    evidence_dataset = _text(record.get("dataset"))
    if set_dataset and evidence_dataset and evidence_dataset != set_dataset:
        return False
    return True


def _evidence_relates_to_claim(claim: Any, evidence: dict[str, Any]) -> bool:
    """Candidate association signal only; never a support verdict."""
    claim_text = _text(claim).lower()
    evidence_text = " ".join([
        _text(evidence.get("claim")),
        _text(evidence.get("summary")),
        _text(evidence.get("result_summary")),
    ]).lower()
    if not claim_text or not evidence_text:
        return False
    if claim_text in evidence_text:
        return True
    claim_tokens = _tokens(claim_text)
    evidence_tokens = _tokens(evidence_text)
    if not claim_tokens:
        return False
    overlap = len(claim_tokens & evidence_tokens) / len(claim_tokens)
    return overlap >= 0.75


def _requirements(items: list[tuple[str, str, bool]]) -> list[dict[str, Any]]:
    return [
        {"kind": kind, "field": field, "required": required}
        for kind, field, required in items
        if field
    ]


def _contract_for_dataset(contracts: list[dict[str, Any]], dataset: str) -> dict[str, Any]:
    for contract in contracts:
        if _text(contract.get("dataset")) == dataset:
            return contract
    return contracts[0] if contracts else {}


def _first_dataset(contracts: list[dict[str, Any]]) -> str:
    return _text(contracts[0].get("dataset")) if contracts else ""


def _first_role(field_roles: dict[str, list[str]], role: str) -> str:
    values = field_roles.get(role) or []
    return values[0] if values else ""


def _secondary_role(field_roles: dict[str, list[str]], role: str, primary: str) -> str:
    for value in field_roles.get(role) or []:
        if value != primary:
            return value
    return ""


def _list_attr(state: Any, name: str) -> list[dict[str, Any]]:
    value = getattr(state, name, None)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _list_items(value: Any) -> list[dict[str, Any]]:
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


def _tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9_]+", value.lower()) if len(token) > 2}


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_]+", "_", value.strip().lower()).strip("_")
    return slug or "item"
