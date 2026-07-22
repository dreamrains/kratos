"""Scenario-level analysis quality diagnostics.

This module is intentionally not wired into runtime synthesis.
"""

from __future__ import annotations

from typing import Any


def score_analysis_quality(
    *,
    claims: list[dict[str, Any]] | None = None,
    relationship_uses: list[dict[str, Any]] | None = None,
    dimensions: dict[str, Any] | None = None,
    notes: list[str] | None = None,
) -> dict[str, Any]:
    """Report hard delivery blockers alongside non-scoring diagnostics.

    Only unsupported material claims and invalid relationship use close the
    publish gate. Other dimensions remain visible for review without being
    collapsed into a score that could reward breadth while hiding a fatal gap.
    """
    claim_items = [item for item in (claims or []) if isinstance(item, dict)]
    relationship_items = [
        item for item in (relationship_uses or []) if isinstance(item, dict)
    ]
    blockers: list[str] = []

    unsupported_claims: list[str] = []
    blocked_claim_details: list[dict[str, Any]] = []
    for index, claim in enumerate(claim_items):
        if claim.get("material") is True and claim.get("supported") is not True:
            claim_key = str(claim.get("claim_key") or f"claim_{index + 1}")
            unsupported_claims.append(claim_key)
            blockers.append(f"unsupported_material_claim:{claim_key}")
            blocked_claim_details.append({
                "claim_key": claim_key,
                "reason_codes": list(claim.get("reason_codes") or ["unsupported_material_claim"]),
                "safe_action": claim.get("safe_action") or {
                    "action": "remove_or_downgrade_claim",
                    "target_claim_id": claim_key,
                },
            })

    invalid_relationships: list[str] = []
    time_scope_mismatches: list[str] = []
    diagnostic_relationships: list[str] = []
    for index, relationship in enumerate(relationship_items):
        relationship_id = str(
            relationship.get("relationship_id") or f"relationship_{index + 1}"
        )
        used_for_claim = relationship.get("used_for_claim") is True
        validation_status = str(relationship.get("validation_status") or "unknown")
        if not used_for_claim:
            if validation_status != "validated":
                diagnostic_relationships.append(relationship_id)
            continue
        if validation_status != "validated":
            invalid_relationships.append(relationship_id)
            blockers.append(f"invalid_relationship_use:{relationship_id}")
        if relationship.get("time_scope_compatible") is False:
            time_scope_mismatches.append(relationship_id)
            blockers.append(f"relationship_time_scope_mismatch:{relationship_id}")

    reported_dimensions = {
        "evidence_support": {
            "status": "blocked" if unsupported_claims else "pass",
            "material_claim_count": sum(
                claim.get("material") is True for claim in claim_items
            ),
            "unsupported_claims": unsupported_claims,
            "blocked_claim_details": blocked_claim_details,
        },
        "relationship_integrity": {
            "status": (
                "blocked"
                if invalid_relationships or time_scope_mismatches
                else "pass"
            ),
            "invalid_relationships": invalid_relationships,
            "time_scope_mismatches": time_scope_mismatches,
            "diagnostic_only_relationships": diagnostic_relationships,
        },
    }
    if dimensions:
        reported_dimensions.update(
            {
                key: value
                for key, value in dimensions.items()
                if key not in reported_dimensions
            }
        )

    unique_blockers = list(dict.fromkeys(blockers))
    ready = not unique_blockers
    return {
        "claim_delivery_ready": ready,
        "global_publish_gate": ready,
        "blockers": unique_blockers,
        "dimensions": reported_dimensions,
        "notes": list(notes or []),
    }
