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
    if not isinstance(bindings, dict) or bindings.get("schema_version") != "answer_bindings.v1":
        return {}
    current_receipts = {
        item.get("receipt_id")
        for item in packet.get("sources", [])
        if isinstance(item, dict) and isinstance(item.get("receipt_id"), str)
    }
    claims: dict[str, set[str]] = {}
    for block in bindings.get("blocks", []):
        if not isinstance(block, dict):
            continue
        claim_id = block.get("claim_id")
        # The current validated typed channel is the M02 scenario slice.
        # Generic legacy blocks have no claim ID and cannot authorize an
        # audit action merely because the model invents one in its response.
        if block.get("claim_type") != "scenario_extrapolation" or not isinstance(claim_id, str):
            continue
        receipt_ref = block.get("receipt_ref")
        if receipt_ref not in current_receipts:
            continue
        refs = {receipt_ref}
        for key in ("fact_refs", "derived_refs"):
            value = block.get(key)
            if isinstance(value, list):
                refs.update(item for item in value if isinstance(item, str) and item)
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
        "reported_overall": raw["overall"],
        "findings": normalized,
        "errors": [],
        "publication_effect": "none",
    }
