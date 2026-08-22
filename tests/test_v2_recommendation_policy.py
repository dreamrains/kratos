from data_agent.v2.models import ClaimClass, FindingKind, OutcomeStatus
from data_agent.v2.recommendation import (
    ActionRisk,
    RecommendationContext,
    RecommendationIntent,
    RecommendationMode,
    decide_recommendation,
)


def _context(**overrides):
    values = {
        "intent": RecommendationIntent.NONE,
        "outcome_status": OutcomeStatus.SUPPORTED,
        "finding_kind": FindingKind.GROUP_COMPARISON,
        "maximum_claim_class": ClaimClass.INFERENTIAL,
        "action_risk": ActionRisk.LOW,
        "reversible": True,
    }
    values.update(overrides)
    return RecommendationContext(**values)


def test_fact_only_question_has_no_forced_recommendation():
    decision = decide_recommendation(_context())

    assert decision.mode is RecommendationMode.NONE
    assert decision.reason_code == "user_did_not_request_recommendation"


def test_observational_difference_never_becomes_causal_operational_action():
    decision = decide_recommendation(
        _context(intent=RecommendationIntent.ACT, action_risk=ActionRisk.LOW, reversible=True)
    )

    assert decision.mode is RecommendationMode.INVESTIGATIVE_NEXT_STEP
    assert decision.reason_code == "observational_evidence_requires_validation"
    assert "验证" in decision.narrative


def test_null_result_requested_action_proposes_measurement_not_no_action_claim():
    decision = decide_recommendation(
        _context(
            intent=RecommendationIntent.ACT,
            outcome_status=OutcomeStatus.NULL_RESULT,
            finding_kind=FindingKind.NULL_RESULT,
        )
    )

    assert decision.mode is RecommendationMode.INVESTIGATIVE_NEXT_STEP
    assert decision.reason_code == "null_result_requires_more_information"
    assert "没有差异" not in decision.narrative


def test_high_risk_or_irreversible_action_is_not_operationalized():
    decision = decide_recommendation(
        _context(intent=RecommendationIntent.ACT, action_risk=ActionRisk.HIGH, reversible=False)
    )

    assert decision.mode is RecommendationMode.INVESTIGATIVE_NEXT_STEP
    assert decision.reason_code == "action_risk_requires_stronger_evidence"


def test_unknown_action_risk_fails_closed_to_investigation():
    decision = decide_recommendation(
        _context(intent=RecommendationIntent.ACT, action_risk=ActionRisk.UNKNOWN)
    )

    assert decision.mode is RecommendationMode.INVESTIGATIVE_NEXT_STEP
    assert decision.reason_code == "action_risk_requires_stronger_evidence"


def test_limited_outcome_suppresses_operational_recommendation():
    decision = decide_recommendation(
        _context(intent=RecommendationIntent.ACT, outcome_status=OutcomeStatus.LIMITED)
    )

    assert decision.mode is RecommendationMode.INVESTIGATIVE_NEXT_STEP
    assert decision.reason_code == "analysis_limit_requires_resolution"
