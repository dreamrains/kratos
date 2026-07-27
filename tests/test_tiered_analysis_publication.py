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

from data_agent.agent.answer_quality import render_audited_analysis_answer
from data_agent.config import AgentConfig


# ---------------------------------------------------------------------------
# Completion + audit fixtures
# ---------------------------------------------------------------------------


def limited_completion():
    """A CompletionDecision shape where current evidence cannot fully satisfy
    the requested claim class — claims get the exploratory suffix."""

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
                "reason_codes": ["missing_evidence_identity"],
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
    "fabricated_value": ["missing_evidence_identity"],
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
    assert "探索性，未经独立校验" in result.text
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


def test_verified_claim_keeps_original_text_when_completion_is_complete():
    """When the completion is fully complete and the claim passes audit, the
    renderer must NOT append the exploratory suffix."""

    draft = "已验证发现"
    result = render_audited_analysis_answer(
        draft=draft,
        audit=mixed_audit(),
        completion=complete_decision(),
        mode="tiered",
    )
    assert "已验证发现" in result.text
    assert "探索性，未经独立校验" not in result.text
    assert result.actions["claim_verified"] == "verified"


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
                "reason_codes": ["missing_evidence_identity"],
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


def test_audit_missing_downgrades_to_exploratory_not_verified():
    """Regression for the audit-None docstring: when the audit is missing,
    a material claim must NOT stay ``verified`` even if completion is
    ``complete`` — it downgrades to ``exploratory`` and gets the suffix."""

    draft = "本月收入增长了 5%。"
    for mode in ("tiered", "strict"):
        result = render_audited_analysis_answer(
            draft=draft,
            audit=None,
            completion=complete_decision(),
            mode=mode,
        )
        # Re-derived claim downgrades to exploratory; the suffix appears on
        # the material claim and no action is "verified".
        assert "探索性，未经独立校验" in result.text
        assert "verified" not in result.actions.values()
