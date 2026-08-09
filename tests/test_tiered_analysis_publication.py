"""Claim-tier publication tests (Task 10).

These tests cover the deterministic partial renderer that replaces the old
whole-answer English fallback. Verified findings stay; downgraded claims get
the local exploratory suffix; fabricated / contradictory / stale / cross-scope
/ causal-invalid claims are replaced in place with Chinese diagnostics. Strict
mode applies the same rules and never removes the entire answer.
"""

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from data_agent.agent.answer_quality import (
    build_final_answer_audit,
    render_audited_analysis_answer,
)
from data_agent.config import AgentConfig


# ---------------------------------------------------------------------------
# Completion + audit fixtures
# ---------------------------------------------------------------------------


def limited_completion():
    """A terminal answer whose overall plan still has disclosed limits.

    Claim-tier publication must continue to trust the final audit for each
    individual claim: a passed current-evidence claim remains verified while
    other claims may be exploratory or unsupported.
    """

    return SimpleNamespace(
        status="complete_with_limits",
        supported_claim_class="exploratory_association",
        is_terminal=True,
    )


def complete_decision():
    """A CompletionDecision shape where the requested claim class is fully
    supported by current evidence — passed claims stay verified."""

    return SimpleNamespace(
        status="complete",
        supported_claim_class="inferential_associations",
        is_terminal=True,
    )


def mixed_audit():
    """Audit with a verified claim and an unsupported numeric claim.

    The verified claim text matches the structural-preserving fixture draft;
    the unsupported claim's text matches the strict-mode draft so the same
    audit exercises both drafts deterministically.
    """

    return {
        "contract_version": "final_answer_audit.v1",
        "id": "audit_mixed",
        "status": "blocked",
        "public_text": "",
        "claims": [
            {
                "id": "claim_verified",
                "text": "已验证发现",
                # Treated as a material traceable finding so the renderer
                # applies the exploratory suffix when completion is limited.
                "claim_type": "comparison",
                "material": True,
            },
            {
                "id": "claim_unsupported",
                "text": "unsupported exact claim",
                "claim_type": "numeric",
                "material": True,
            },
        ],
        "claim_checks": [
            {
                "claim_id": "claim_verified",
                "status": "passed",
                "reason_codes": [],
            },
            {
                "claim_id": "claim_unsupported",
                "status": "failed",
                "reason_codes": ["numeric_mismatch"],
            },
        ],
    }


_BLOCKER_CLAIM_TEXTS = {
    "fabricated_value": "本月收入增长了 99%。",
    "contradictory_direction": "本月收入相比上月上升了 5%。",
    "stale_dataset": "基于历史口径，本月收入有所增长。",
    "cross_scope_evidence": "另一组实验中观察到的效应在本数据上同样成立。",
    "causal_upgrade": "营销活动导致了收入增长。",
}

_BLOCKER_REASON_CODES = {
    "fabricated_value": ["numeric_mismatch"],
    "contradictory_direction": ["direction_mismatch"],
    "stale_dataset": ["stale_dataset_evidence"],
    "cross_scope_evidence": ["evidence_outside_current_plan"],
    "causal_upgrade": ["unmet_block_claim_requirement"],
}


def audit_for(name: str) -> dict:
    claim_text = _BLOCKER_CLAIM_TEXTS[name]
    return {
        "contract_version": "final_answer_audit.v1",
        "id": f"audit_{name}",
        "status": "blocked",
        "public_text": claim_text,
        "claims": [
            {
                "id": "claim_1",
                "text": claim_text,
                "claim_type": "comparison",
                "material": True,
            },
        ],
        "claim_checks": [
            {
                "claim_id": "claim_1",
                "status": "failed",
                "reason_codes": _BLOCKER_REASON_CODES[name],
            },
        ],
    }


def test_failed_missing_identity_cannot_publish_uncomputed_number_as_exploratory():
    claim_text = "利润在2026-05增长99%。"
    audit = build_final_answer_audit(
        claim_text,
        evidence_records=[],
        current_plan_id="plan_current",
        current_dataset_versions=["dataset_current_v1"],
        measurement_binding_mode="soft",
    )

    assert audit["status"] == "blocked"
    assert audit["claim_checks"][0]["status"] == "failed"
    assert audit["claim_checks"][0]["evidence_ids"] == []

    result = render_audited_analysis_answer(
        draft=claim_text,
        audit=audit,
        completion=limited_completion(),
        mode="tiered",
    )

    assert result.actions == {"claim_1": "unsupported"}
    assert claim_text not in result.text
    assert "99%" not in result.text
    assert "无法发布" in result.text
    assert "探索性，未经独立校验" not in result.text


@pytest.fixture
def fabricated_value():
    return _BLOCKER_CLAIM_TEXTS["fabricated_value"]


@pytest.fixture
def contradictory_direction():
    return _BLOCKER_CLAIM_TEXTS["contradictory_direction"]


@pytest.fixture
def stale_dataset():
    return _BLOCKER_CLAIM_TEXTS["stale_dataset"]


@pytest.fixture
def cross_scope_evidence():
    return _BLOCKER_CLAIM_TEXTS["cross_scope_evidence"]


@pytest.fixture
def causal_upgrade():
    return _BLOCKER_CLAIM_TEXTS["causal_upgrade"]


# ---------------------------------------------------------------------------
# Step 1: structure preservation
# ---------------------------------------------------------------------------


def test_tiered_mode_preserves_headings_tables_and_supported_findings():
    draft = "# 结论\n\n- 已验证发现\n- 未验证数字 99%\n\n## 局限\n\n原有局限"
    result = render_audited_analysis_answer(
        draft=draft,
        audit=mixed_audit(),
        completion=limited_completion(),
        mode="tiered",
    )
    assert "# 结论" in result.text
    assert "已验证发现" in result.text
    assert result.actions["claim_verified"] == "verified"
    assert "已验证发现（探索性，未经独立校验）" not in result.text
    assert "无法发布该数值" in result.text
    assert "Some requested analysis claims" not in result.text


def test_strict_mode_still_blocks_only_claims_not_whole_answer():
    result = render_audited_analysis_answer(
        draft="# 结论\n\n已验证描述。\n\nunsupported exact claim",
        audit=mixed_audit(),
        completion=limited_completion(),
        mode="strict",
    )
    assert result.text.startswith("# 结论")
    assert "unsupported exact claim" not in result.text
    assert result.actions["claim_unsupported"] == "unsupported"


@pytest.mark.parametrize("completion", [complete_decision(), limited_completion()])
def test_verified_claim_keeps_original_text_for_terminal_completion(completion):
    """Whole-plan limits cannot downgrade a claim that passed final audit."""

    draft = "已验证发现"
    result = render_audited_analysis_answer(
        draft=draft,
        audit=mixed_audit(),
        completion=completion,
        mode="tiered",
    )
    assert "已验证发现" in result.text
    assert "探索性，未经独立校验" not in result.text
    assert result.actions["claim_verified"] == "verified"


def _structural_audit(*, claims=None, claim_checks=None) -> dict:
    public_text = "Revenue increased 12%."
    return {
        "contract_version": "final_answer_audit.v1",
        "id": "audit_structural_contract",
        "status": "pass",
        "public_text": public_text,
        "claims": claims if claims is not None else [{
            "id": "claim_revenue",
            "text": public_text,
            "claim_type": "comparison",
            "material": True,
        }],
        "claim_checks": claim_checks if claim_checks is not None else [{
            "claim_id": "claim_revenue",
            "status": "passed",
            "reason_codes": [],
        }],
    }


@pytest.mark.parametrize(
    "audit",
    [
        pytest.param(
            _structural_audit(claim_checks=[]),
            id="missing-check",
        ),
        pytest.param(
            _structural_audit(claim_checks=[
                {"claim_id": "claim_revenue", "status": "passed"},
                {"claim_id": "claim_revenue", "status": "passed"},
            ]),
            id="duplicate-check",
        ),
        pytest.param(
            _structural_audit(claim_checks=[
                {"claim_id": "claim_revenue", "status": "passed"},
                {"claim_id": "claim_orphan", "status": "passed"},
            ]),
            id="orphan-check",
        ),
        pytest.param(
            _structural_audit(claims=[
                {
                    "id": "claim_revenue",
                    "text": "Revenue increased 12%.",
                    "claim_type": "comparison",
                    "material": True,
                },
                {
                    "id": "claim_revenue",
                    "text": "Revenue increased 12%.",
                    "claim_type": "comparison",
                    "material": True,
                },
            ]),
            id="duplicate-claim-id",
        ),
        pytest.param(
            _structural_audit(claim_checks=[{
                "claim_id": "claim_revenue",
                "status": "unknown",
            }]),
            id="unknown-check-status",
        ),
        pytest.param(
            _structural_audit(
                claims=[{"id": " ", "text": "Revenue increased 12%."}],
                claim_checks=[{"claim_id": " ", "status": "passed"}],
            ),
            id="blank-claim-id",
        ),
        pytest.param(
            _structural_audit(claim_checks=[{
                "claim_id": " ",
                "status": "passed",
            }]),
            id="blank-check-claim-id",
        ),
    ],
)
def test_structurally_invalid_audit_never_verifies_claims(audit):
    result = render_audited_analysis_answer(
        draft="Revenue increased 12%.",
        audit=audit,
        completion=complete_decision(),
        mode="tiered",
    )

    assert "Revenue increased 12%." not in result.text
    assert "无法发布该结论：缺少当前证据支撑" in result.text
    assert set(result.actions.values()) == {"unsupported"}


def test_structurally_valid_audit_still_verifies_complete_claim():
    result = render_audited_analysis_answer(
        draft="Revenue increased 12%.",
        audit=_structural_audit(),
        completion=complete_decision(),
        mode="tiered",
    )

    assert result.text == "Revenue increased 12%.\n"
    assert result.actions == {"claim_revenue": "verified"}


def test_structurally_invalid_audit_cannot_replace_draft_public_text():
    audit = _structural_audit(claim_checks=[])
    audit["public_text"] = "Malformed audit replacement 99%."

    result = render_audited_analysis_answer(
        draft="# Conclusion\n\nRevenue increased 12%.\n\n## Limitations\n\nDescriptive only.",
        audit=audit,
        completion=complete_decision(),
        mode="tiered",
    )

    assert result.text.startswith("# Conclusion")
    assert "Revenue increased 12%." not in result.text
    assert "无法发布该结论：缺少当前证据支撑" in result.text
    assert "## Limitations" in result.text
    assert "Descriptive only." in result.text
    assert "Malformed audit replacement" not in result.text
    assert "verified" not in result.actions.values()


def test_empty_valid_audit_cannot_verify_claim_rederived_from_draft():
    audit = _structural_audit(claims=[], claim_checks=[])
    audit["public_text"] = ""

    result = render_audited_analysis_answer(
        draft="Revenue increased 12%.",
        audit=audit,
        completion=complete_decision(),
        mode="tiered",
    )

    assert "Revenue increased 12%." not in result.text
    assert "无法发布该结论：缺少当前证据支撑" in result.text
    assert set(result.actions.values()) == {"unsupported"}


def test_missing_measurement_identity_keeps_complete_answer_structure():
    draft = (
        "# Conclusion\n\n"
        "Revenue increased 12%.\n\n"
        "## Limitation\n\n"
        "This is a descriptive comparison only."
    )
    audit = {
        "contract_version": "final_answer_audit.v1",
        "status": "revise",
        "public_text": draft,
        "claims": [{
            "id": "claim_revenue",
            "text": "Revenue increased 12%.",
            "claim_type": "comparison",
            "material": True,
        }],
        "claim_checks": [{
            "claim_id": "claim_revenue",
            "status": "downgraded",
            "reason_codes": ["measurement_identity_missing"],
        }],
    }

    result = render_audited_analysis_answer(
        draft=draft,
        audit=audit,
        completion=complete_decision(),
        mode="tiered",
    )

    assert result.text.startswith("# Conclusion")
    assert "Revenue increased 12%." in result.text
    assert "## Limitation" in result.text
    assert result.actions["claim_revenue"] == "exploratory"


# ---------------------------------------------------------------------------
# Step 2: deterministic blockers + config
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "claim_fixture",
    [
        "fabricated_value",
        "contradictory_direction",
        "stale_dataset",
        "cross_scope_evidence",
        "causal_upgrade",
    ],
)
def test_minimum_blockers_apply_in_both_modes(claim_fixture, request):
    for mode in ("tiered", "strict"):
        result = render_audited_analysis_answer(
            draft=request.getfixturevalue(claim_fixture),
            audit=audit_for(claim_fixture),
            completion=complete_decision(),
            mode=mode,
        )
        assert result.actions["claim_1"] == "unsupported"
        # The original fabricated / contradictory / stale claim text is gone;
        # a Chinese diagnostic naming the missing evidence/method/data appears.
        assert request.getfixturevalue(claim_fixture) not in result.text
        assert "无法发布" in result.text


def test_missing_evidence_identity_is_published_as_exploratory_in_both_modes():
    """Missing projection is a confidence limitation, not proof that the
    claim is false; hard numeric contradictions remain covered above."""
    claim_text = "收入均值为 514.5 元。"
    audit = {
        "contract_version": "final_answer_audit.v1",
        "id": "audit_missing_identity",
        "status": "blocked",
        "public_text": claim_text,
        "claims": [{
            "id": "claim_mean",
            "text": claim_text,
            "claim_type": "numeric",
            "material": True,
        }],
        "claim_checks": [{
            "claim_id": "claim_mean",
            "status": "failed",
            "evidence_id": "ev_traceable_mean",
            "evidence_ids": ["ev_traceable_mean"],
            "reason_codes": ["missing_evidence_identity", "evidence_check_failed"],
        }],
    }

    for mode in ("tiered", "strict"):
        result = render_audited_analysis_answer(
            draft=claim_text,
            audit=audit,
            completion=complete_decision(),
            mode=mode,
        )
        assert claim_text in result.text
        assert "探索性，未经独立校验" in result.text
        assert "无法发布" not in result.text
        assert result.actions["claim_mean"] == "exploratory"


def test_generic_failed_check_with_evidence_id_is_not_exploratory():
    """A generic failure code is not proof of a safe identity-only gap."""

    claim_text = "Revenue increased 91%."
    audit = {
        "contract_version": "final_answer_audit.v1",
        "id": "audit_generic_failure",
        "status": "blocked",
        "public_text": claim_text,
        "claims": [{
            "id": "claim_revenue",
            "text": claim_text,
            "claim_type": "numeric",
            "material": True,
        }],
        "claim_checks": [{
            "claim_id": "claim_revenue",
            "status": "failed",
            "evidence_id": "ev_present_but_unresolved",
            "evidence_ids": ["ev_present_but_unresolved"],
            "reason_codes": ["evidence_check_failed"],
        }],
    }

    result = render_audited_analysis_answer(
        draft=claim_text,
        audit=audit,
        completion=complete_decision(),
        mode="tiered",
    )

    assert result.actions == {"claim_revenue": "unsupported"}
    assert claim_text not in result.text


def test_markerless_nonnumeric_recommendation_is_exploratory():
    claim_text = "建议补充时间字段并通过 A/B 测试验证策略效果。"
    audit = {
        "contract_version": "final_answer_audit.v1",
        "id": "audit_markerless_recommendation",
        "status": "blocked",
        "public_text": claim_text,
        "claims": [{
            "id": "claim_recommendation",
            "text": claim_text,
            "claim_type": "recommendation",
            "material": True,
            "requires_evidence": True,
            "quantities": [],
        }],
        "claim_checks": [{
            "claim_id": "claim_recommendation",
            "status": "failed",
            "evidence_id": None,
            "evidence_ids": [],
            "reason_codes": [
                "missing_evidence_identity",
                "evidence_check_failed",
            ],
        }],
    }

    result = render_audited_analysis_answer(
        draft=claim_text,
        audit=audit,
        completion=complete_decision(),
        mode="tiered",
    )

    assert result.actions == {"claim_recommendation": "exploratory"}
    assert claim_text in result.text
    assert "探索性，未经独立校验" in result.text
    assert "无法发布" not in result.text


def test_markerless_numeric_recommendation_remains_unsupported():
    claim_text = "建议将预算提高 91%。"
    audit = {
        "contract_version": "final_answer_audit.v1",
        "id": "audit_markerless_numeric_recommendation",
        "status": "blocked",
        "public_text": claim_text,
        "claims": [{
            "id": "claim_recommendation",
            "text": claim_text,
            "claim_type": "recommendation",
            "material": True,
            "requires_evidence": True,
            "quantities": [{"raw": "91%", "value": 91.0, "unit": "%"}],
        }],
        "claim_checks": [{
            "claim_id": "claim_recommendation",
            "status": "failed",
            "evidence_id": None,
            "evidence_ids": [],
            "reason_codes": [
                "missing_evidence_identity",
                "evidence_check_failed",
            ],
        }],
    }

    result = render_audited_analysis_answer(
        draft=claim_text,
        audit=audit,
        completion=complete_decision(),
        mode="tiered",
    )

    assert result.actions == {"claim_recommendation": "unsupported"}
    assert claim_text not in result.text
    assert "无法发布" in result.text


def test_publication_mode_has_no_off_value():
    with pytest.raises(ValidationError):
        AgentConfig(ASSURANCE_PUBLICATION_MODE="off", _env_file=None)


def test_publication_mode_defaults_to_tiered():
    cfg = AgentConfig(_env_file=None)
    assert cfg.assurance_publication_mode == "tiered"
    assert cfg.auto_evidence_projection_enabled is True
    assert cfg.analysis_live_progress_enabled is True


# ---------------------------------------------------------------------------
# Step 3: strict vs tiered — fail-safe rollback net (strict-only behavior)
# ---------------------------------------------------------------------------


def _unmatched_unsupported_audit() -> dict:
    """Audit whose unsupported claim text is NOT present in the draft, so the
    renderer cannot replace it in place and must append it as a trailing
    diagnostic block — the (a) branch of "cannot safely recover"."""

    return {
        "contract_version": "final_answer_audit.v1",
        "id": "audit_unmatched_unsupported",
        "status": "blocked",
        "public_text": "",
        "claims": [
            {
                "id": "claim_unmatched",
                "text": "an unsupported exact claim that is absent from the draft",
                "claim_type": "numeric",
                "material": True,
            },
        ],
        "claim_checks": [
            {
                "claim_id": "claim_unmatched",
                "status": "failed",
                "reason_codes": ["numeric_mismatch"],
            },
        ],
    }


def test_strict_emits_recovery_banner_when_unsupported_claim_is_unmatched():
    """Strict emits the recovery banner when an unsupported claim cannot be
    cleanly replaced in place; tiered recovers silently on the same input."""

    draft = "# 结论\n\n已验证描述。"

    strict_result = render_audited_analysis_answer(
        draft=draft,
        audit=_unmatched_unsupported_audit(),
        completion=complete_decision(),
        mode="strict",
    )
    # Banner is visible at the top of the published text and recorded in
    # PublicationResult.diagnostics.
    assert "严格发布模式" in strict_result.text
    assert any(
        isinstance(d, dict) and d.get("event") == "strict_recovery_diagnostic"
        for d in strict_result.diagnostics
    )

    tiered_result = render_audited_analysis_answer(
        draft=draft,
        audit=_unmatched_unsupported_audit(),
        completion=complete_decision(),
        mode="tiered",
    )
    # Same input, but tiered never emits the banner.
    assert "严格发布模式" not in tiered_result.text
    assert not any(
        isinstance(d, dict) and d.get("event") == "strict_recovery_diagnostic"
        for d in tiered_result.diagnostics
    )


def test_strict_emits_recovery_banner_when_audit_is_missing():
    """Strict emits the recovery banner when the audit is missing (claims are
    re-derived from the draft text); tiered recovers silently."""

    draft = "# 结论\n\n本月收入增长了 5%。"

    strict_result = render_audited_analysis_answer(
        draft=draft,
        audit=None,
        completion=complete_decision(),
        mode="strict",
    )
    assert "严格发布模式" in strict_result.text
    assert any(
        isinstance(d, dict) and d.get("event") == "strict_recovery_diagnostic"
        for d in strict_result.diagnostics
    )

    tiered_result = render_audited_analysis_answer(
        draft=draft,
        audit=None,
        completion=complete_decision(),
        mode="tiered",
    )
    assert "严格发布模式" not in tiered_result.text
    assert not any(
        isinstance(d, dict) and d.get("event") == "strict_recovery_diagnostic"
        for d in tiered_result.diagnostics
    )


def test_strict_no_banner_when_recovery_is_clean():
    """Strict must NOT emit the banner when every unsupported claim is cleanly
    replaced in place AND the audit is present — recovery is clean, so strict
    publishes identically to tiered."""

    # Same blocker audit used by the parametrized blocker test: the claim
    # text IS in public_text, so it is replaced in place (no trailing block).
    draft = _BLOCKER_CLAIM_TEXTS["fabricated_value"]
    strict_result = render_audited_analysis_answer(
        draft=draft,
        audit=audit_for("fabricated_value"),
        completion=complete_decision(),
        mode="strict",
    )
    assert "严格发布模式" not in strict_result.text
    assert not any(
        isinstance(d, dict) and d.get("event") == "strict_recovery_diagnostic"
        for d in strict_result.diagnostics
    )
    # Blocker still fires in strict mode.
    assert strict_result.actions["claim_1"] == "unsupported"


def test_audit_missing_removes_unaudited_material_claim():
    """Audit infrastructure failure must not publish analytical assertions.

    An exploratory disclaimer cannot make an unaudited number safe.  The
    renderer preserves the surrounding answer structure, but replaces every
    re-derived material claim with a deterministic diagnostic.
    """

    draft = "本月收入增长了 5%。"
    for mode in ("tiered", "strict"):
        result = render_audited_analysis_answer(
            draft=draft,
            audit=None,
            completion=complete_decision(),
            mode=mode,
        )
        assert "本月收入增长了 5%" not in result.text
        assert "无法发布该结论：缺少当前证据支撑" in result.text
        assert "探索性，未经独立校验" not in result.text
        assert set(result.actions.values()) == {"unsupported"}
