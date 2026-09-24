"""Offline validation of claim-bound semantic audit findings.

This module does not dispatch a model call or decide whether to publish.
Shadow findings are diagnostics only; deterministic publication authority
remains with the existing receipt/binding/renderer path.
"""

from __future__ import annotations

from typing import Any, Mapping


_OVERALL = frozenset({"pass", "pass_with_findings", "inconclusive"})
_DIMENSIONS = frozenset({
    "claim_strength", "causal_inference", "population_scope",
    "validation_status", "requirement_coverage", "recommendation_support",
    "missingness", "clarity",
})
_SEVERITIES = frozenset({"low", "medium", "high"})
_ACTIONS = frozenset({
    "keep", "downgrade", "remove", "mark_unassessed",
    "add_host_disclosure", "request_targeted_revision", "advisory_only",
})


def _invalid(*errors: str) -> dict[str, Any]:
    return {
        "schema_version": "publication_audit.v1",
        "status": "invalid",
        "reported_overall": "",
        "findings": [],
        "errors": list(errors),
        "publication_effect": "none",
    }


def _typed_claim_evidence(packet: Mapping[str, Any]) -> dict[str, set[str]]:
    bindings = packet.get("answer_bindings") or {}
    if (
        not isinstance(bindings, dict)
        or bindings.get("schema_version") != "answer_bindings.v1"
        or bindings.get("packet_digest") != packet.get("snapshot_digest")
    ):
        return {}
    from data_agent.agent.publication_synthesis import (
        _comparison_binding_issue, _derived_binding_issue,
        _descriptive_fit_binding_issue, _observed_binding_issue,
        _scenario_binding_issue,
    )

    validators = {
        "observed_fact": _observed_binding_issue,
        "derived_metric": _derived_binding_issue,
        "comparison": _comparison_binding_issue,
        "descriptive_fit": _descriptive_fit_binding_issue,
        "scenario_extrapolation": _scenario_binding_issue,
    }
    sources = [item for item in packet.get("sources", []) if isinstance(item, dict)]
    claims: dict[str, set[str]] = {}
    for block in bindings.get("blocks", []):
        if not isinstance(block, dict):
            continue
        claim_id = block.get("claim_id")
        validator = validators.get(block.get("claim_type"))
        if not isinstance(claim_id, str) or validator is None or validator(block, packet):
            continue
        refs = {
            ref for key in ("fact_refs", "derived_refs")
            for ref in block.get(key, []) if isinstance(ref, str) and ref
        }
        if block.get("receipt_ref"):
            refs.add(block["receipt_ref"])
        for source in sources:
            if any(fact.get("fact_id") in refs for fact in source.get("facts", []) if isinstance(fact, dict)):
                refs.add(source.get("receipt_id"))
        for evidence in packet.get("evidence", []):
            if not isinstance(evidence, dict):
                continue
            if any(item.get("id") in refs for item in evidence.get("derived_measurements", []) if isinstance(item, dict)):
                refs.update(evidence.get("tool_receipt_ids") or [])
        refs.discard(None)
        refs.discard("")
        claims[claim_id] = refs
    return claims


def validate_shadow_audit(raw: Any, packet: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize one audit reply without applying any recommended action.

    Unbound or foreign references become advisory-only. Malformed protocol or
    stale answer identity invalidates the *audit*, never the accepted answer.
    Reason text remains explicitly untrusted diagnostic data; it is never a
    source of numeric/business facts or a publishable disclosure.
    """
    if not isinstance(raw, dict) or not isinstance(packet, Mapping):
        return _invalid("audit_or_packet_not_object")
    if raw.get("schema_version") != "publication_audit.v1":
        return _invalid("invalid_schema_version")
    if (
        not packet.get("snapshot_digest")
        or not packet.get("answer_sha256")
        or raw.get("packet_digest") != packet.get("snapshot_digest")
        or raw.get("answer_sha256") != packet.get("answer_sha256")
    ):
        return _invalid("stale_audit_identity")
    if raw.get("overall") not in _OVERALL:
        return _invalid("invalid_overall")
    findings = raw.get("findings")
    if not isinstance(findings, list) or len(findings) > 50:
        return _invalid("invalid_findings")
    # The first typed slice has no host-validated requirement/contradiction
    # reference protocol yet. Reject free-form additions instead of allowing
    # them to bypass claim/evidence validation.
    if raw.get("missing_requirements") != [] or raw.get("contradictions") != []:
        return _invalid("unscoped_audit_assertions")

    claims = _typed_claim_evidence(packet)
    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for item in findings:
        if not isinstance(item, dict):
            return _invalid("invalid_finding")
        finding_id = item.get("finding_id")
        claim_id = item.get("claim_id")
        refs = item.get("evidence_refs")
        reason = item.get("reason")
        if (
            not isinstance(finding_id, str) or not finding_id or len(finding_id) > 64
            or finding_id in seen_ids
            or not isinstance(claim_id, str) or not claim_id or len(claim_id) > 96
            or item.get("dimension") not in _DIMENSIONS
            or item.get("severity") not in _SEVERITIES
            or item.get("recommended_action") not in _ACTIONS
            or not isinstance(refs, list) or len(refs) > 20
            or not all(isinstance(ref, str) and ref for ref in refs)
            or not isinstance(reason, str) or len(reason) > 500
        ):
            return _invalid("invalid_finding_fields")
        seen_ids.add(finding_id)
        bound = bool(refs) and set(refs) <= claims.get(claim_id, set())
        normalized.append({
            "finding_id": finding_id,
            "claim_id": claim_id,
            "dimension": item["dimension"],
            "severity": item["severity"],
            "evidence_refs": list(refs),
            "suggested_action": item["recommended_action"] if bound else "advisory_only",
            "binding_status": "claim_evidence_bound" if bound else "unbound_advisory",
            "reason_untrusted": reason,
        })
    return {
        "schema_version": "publication_audit.v1",
        "status": "valid",
        "packet_digest": packet["snapshot_digest"],
        "answer_sha256": packet["answer_sha256"],
        "reported_overall": raw["overall"],
        "findings": normalized,
        "errors": [],
        "publication_effect": "none",
    }


def simulate_shadow_actions(packet: Mapping[str, Any], audit: Mapping[str, Any]) -> dict[str, Any]:
    """Offline claim-level disposition preview; no publication or model call."""
    from data_agent.agent.publication_synthesis import render_trusted_core_preview

    claims = _typed_claim_evidence(packet)
    order = {"keep": 0, "downgrade": 1, "mark_unassessed": 2, "remove": 3}
    actions: dict[str, str] = {}
    revisions: list[str] = []
    current_audit = (
        isinstance(audit, Mapping)
        and audit.get("status") == "valid"
        and audit.get("publication_effect") == "none"
        and audit.get("packet_digest") == packet.get("snapshot_digest")
        and audit.get("answer_sha256") == packet.get("answer_sha256")
    )
    if current_audit:
        for finding in audit.get("findings", []):
            if not isinstance(finding, dict):
                continue
            claim_id = finding.get("claim_id")
            refs = finding.get("evidence_refs")
            if (not isinstance(claim_id, str) or claim_id not in claims
                    or finding.get("binding_status") != "claim_evidence_bound"
                    or not isinstance(refs, list) or not refs
                    or not all(isinstance(ref, str) for ref in refs)
                    or not set(refs) <= claims[claim_id]):
                continue
            action = finding.get("suggested_action")
            if isinstance(action, str) and action in order and (
                claim_id not in actions or order[action] > order[actions[claim_id]]
            ):
                actions[claim_id] = action
            elif action == "request_targeted_revision" and not revisions:
                revisions.append(claim_id)
    excluded = frozenset(
        claim_id for claim_id, action in actions.items()
        if action in {"mark_unassessed", "remove"}
    )
    preview = render_trusted_core_preview(dict(packet), packet.get("answer_bindings"), excluded_claim_ids=excluded)
    return {
        "status": "simulated_only" if current_audit else "audit_unavailable",
        "claim_actions": actions,
        "targeted_revision_claim_ids": revisions,
        "trusted_core_preview": preview["text"],
        "publication_effect": "none",
    }
