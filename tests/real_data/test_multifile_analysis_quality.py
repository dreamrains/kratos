from __future__ import annotations

from data_agent.agent.analysis_quality_rubric import score_analysis_quality


def test_unsupported_material_claim_blocks_delivery_without_magic_total() -> None:
    result = score_analysis_quality(
        claims=[
            {
                "claim_key": "revenue_driver",
                "material": True,
                "supported": False,
            }
        ]
    )

    assert result["claim_delivery_ready"] is False
    assert result["global_publish_gate"] is False
    assert "unsupported_material_claim:revenue_driver" in result["blockers"]
    assert "total" not in result


def test_invalid_relationship_use_blocks_only_when_used_for_a_claim() -> None:
    diagnostic = {
        "relationship_id": "orders_to_flow",
        "validation_status": "rejected",
        "used_for_claim": False,
    }
    diagnostic_only = score_analysis_quality(relationship_uses=[diagnostic])
    used_for_claim = score_analysis_quality(
        relationship_uses=[{**diagnostic, "used_for_claim": True}]
    )

    assert diagnostic_only["global_publish_gate"] is True
    assert used_for_claim["claim_delivery_ready"] is False
    assert used_for_claim["global_publish_gate"] is False
    assert "invalid_relationship_use:orders_to_flow" in used_for_claim["blockers"]


def test_time_scope_mismatch_blocks_relationship_based_claim() -> None:
    result = score_analysis_quality(
        relationship_uses=[
            {
                "relationship_id": "orders_to_flow",
                "validation_status": "validated",
                "used_for_claim": True,
                "time_scope_compatible": False,
            }
        ]
    )

    assert result["global_publish_gate"] is False
    assert "relationship_time_scope_mismatch:orders_to_flow" in result["blockers"]


def test_soft_dimension_warning_is_reported_but_does_not_decide_readiness() -> None:
    result = score_analysis_quality(
        claims=[{"claim_key": "trend", "material": True, "supported": True}],
        dimensions={
            "breadth": {
                "status": "warning",
                "note": "Only one plausible alternative explanation was evaluated.",
            }
        },
        notes=["Human review remains appropriate for high-impact decisions."],
    )

    assert result["claim_delivery_ready"] is True
    assert result["global_publish_gate"] is True
    assert result["dimensions"]["breadth"]["status"] == "warning"
    assert result["notes"]
    assert "total" not in result


def test_custom_dimensions_cannot_overwrite_hard_integrity_diagnostics() -> None:
    result = score_analysis_quality(
        claims=[{"claim_key": "unsupported", "material": True, "supported": False}],
        dimensions={"evidence_support": {"status": "pass"}},
    )

    assert result["dimensions"]["evidence_support"]["status"] == "blocked"
    assert result["global_publish_gate"] is False
