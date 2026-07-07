"""Deterministic hypothesis records for supported analysis routes."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from data_agent.agent.artifact_refs import hydrate_refs
from data_agent.config import get_config


def build_hypothesis_set(user_input: str, entry_decision: Any, state: Any) -> dict[str, Any]:
    """Build a deterministic hypothesis set from entry routing and trust state."""
    decision = entry_decision if isinstance(entry_decision, dict) else {}
    contracts = hydrate_refs(_list_attr(state, "dataset_contracts"))
    dataset = _text(decision.get("dataset")) or _first_dataset(contracts)
    route = _text(decision.get("route"))
    if not route and _text(decision.get("decision")) == "request_data":
        route = "user_level_retention"
    contract = _contract_for_dataset(contracts, dataset)
    field_roles = _field_roles(contract)
    limitations = _text_list(decision.get("limitations"))
    set_id = f"hypotheses_{_slug(dataset or 'dataset')}_{_slug(route or 'analysis')}"

    if _text(decision.get("decision")) == "request_data" or route == "user_level_retention":
        hypotheses = [_unsupported_hypothesis(set_id, dataset, route, limitations, field_roles)]
    else:
        hypotheses = _route_templates(set_id, dataset, route, field_roles, limitations)

    payload = {
        "id": set_id,
        "user_input": _text(user_input),
        "dataset": dataset,
        "route": route,
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
        "count": len(hypotheses),
        "status_summary": _status_summary(hypotheses),
        "artifact_path": str(path),
    }


def hydrate_hypothesis_refs(refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Hydrate compact hypothesis refs from their JSON artifacts."""
    return hydrate_refs(refs)


def update_hypotheses_from_evidence(
    hypothesis_set: dict[str, Any],
    evidence_records: list[dict[str, Any]],
) -> dict[str, Any]:
    """Update hypothesis statuses from deterministic evidence text overlap."""
    updated = dict(hypothesis_set)
    evidence = [item for item in evidence_records if isinstance(item, dict)]
    hypotheses: list[dict[str, Any]] = []
    for hypothesis in _list_items(hypothesis_set.get("hypotheses")):
        item = dict(hypothesis)
        supporting_ids = list(item.get("supporting_evidence_ids") or [])
        if item.get("status") == "unsupported_by_data":
            hypotheses.append(item)
            continue

        matches = [
            _text(record.get("id"))
            for record in evidence
            if _evidence_supports_claim(item.get("claim"), record)
        ]
        for evidence_id in matches:
            if evidence_id and evidence_id not in supporting_ids:
                supporting_ids.append(evidence_id)
        item["supporting_evidence_ids"] = supporting_ids
        if supporting_ids:
            item["status"] = "supported"
        elif item.get("verification_level") in {"verifiable", "partially_verifiable"}:
            item["status"] = "inconclusive"
        hypotheses.append(item)

    updated["hypotheses"] = hypotheses
    updated["status_summary"] = _status_summary(hypotheses)
    return updated


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
    return {
        "id": f"{set_id}_h{index}",
        "dataset": dataset,
        "route": route,
        "claim": claim,
        "status": status,
        "verification_level": _verification_level(requirements, field_roles),
        "evidence_requirements": requirements,
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


def _evidence_supports_claim(claim: Any, evidence: dict[str, Any]) -> bool:
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
