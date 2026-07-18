import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np
import pandas as pd

from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.intent import TurnIntent
from data_agent.agent.synthesis_policy import SynthesisPolicy, derive_synthesis_policy


def _intent(intent_type="directed_analysis", clarity="clear", action="run_analysis"):
    return TurnIntent(
        intent_type=intent_type,
        clarity=clarity,
        data_state="data_loaded",
        analysis_stage="execute",
        recommended_action=action,
        execution_readiness="ready",
        reason="test",
        ambiguities=[],
    )


def _state_with_evidence(confidence="high"):
    state = AnalysisSessionState(session_id="synthesis_test")
    state.set_analysis_plan({
        "playbook_id": "retention_lifecycle",
        "question_type": "diagnostic",
        "confirmation_policy": {"requires_confirmation": False},
        "limitations": ["aggregate retention data"],
    })
    state.evidence_records = [{
        "id": "ev_1",
        "claim": "Retention follows a power-law curve",
        "result_summary": "R(t)=0.1917*t^(-0.7335), R2=0.9743",
        "confidence": confidence,
        "limitations": "Aggregated data only",
        "method": "log-linear least squares",
    }]
    return state


def _state_with_verification(status):
    state = _state_with_evidence()
    state.verification_reports = [
        {
            "id": "verify_old",
            "overall_status": "pass",
            "created_at": "2026-06-01T00:00:00Z",
        },
        {
            "id": "verify_latest",
            "overall_status": status,
            "created_at": "2026-06-02T00:00:00Z",
        },
    ]
    return state


def _policy(**kwargs):
    return derive_synthesis_policy(**kwargs)


def test_simple_response_gets_direct_policy_without_business_translation():
    policy = _policy(
        intent=_intent(intent_type="simple_response", action="answer_directly"),
        state=AnalysisSessionState(session_id="chat"),
        user_input="hello",
    )

    assert isinstance(policy, SynthesisPolicy)
    assert policy.answer_mode == "direct"
    assert policy.insight_depth == "none"
    assert policy.business_translation == "not_applicable"
    assert "business_meaning" not in policy.required_moves


def test_direct_operation_has_no_business_translation():
    policy = _policy(
        intent=_intent(intent_type="data_operation", action="execute_operation"),
        state=AnalysisSessionState(session_id="direct"),
        user_input="export this table",
    )

    assert isinstance(policy, SynthesisPolicy)
    assert policy.answer_mode == "direct"
    assert policy.insight_depth == "none"
    assert policy.business_translation == "not_applicable"
    assert "business_meaning" not in policy.required_moves


def test_formula_fitting_gets_light_cautious_business_meaning():
    policy = _policy(
        intent=_intent(),
        state=_state_with_evidence(),
        user_input="fit a retention curve formula from the data",
        data_profile="grain=daily_aggregate; no dimensions; retention metrics",
    )

    assert isinstance(policy, SynthesisPolicy)
    assert policy.answer_mode == "analytical"
    assert policy.insight_depth == "light"
    assert policy.business_translation == "cautious"
    assert policy.risk_boundary == "descriptive"
    assert policy.required_moves == [
        "core_answer",
        "evidence",
        "method_note",
        "limitation",
        "business_meaning",
        "next_step",
    ]


def test_ltv_followup_gets_standard_cautious_advisory_policy():
    policy = _policy(
        intent=_intent(),
        state=_state_with_evidence(),
        user_input="use this formula to forecast LTV",
        data_profile="grain=daily_aggregate; retention metrics; no revenue metric",
    )

    assert isinstance(policy, SynthesisPolicy)
    assert policy.answer_mode == "advisory"
    assert policy.insight_depth == "standard"
    assert policy.business_translation == "cautious"
    assert policy.risk_boundary == "predictive"
    assert "assumptions" in policy.required_moves


def test_no_evidence_is_exploratory_and_does_not_advise():
    state = AnalysisSessionState(session_id="no_evidence")
    state.set_analysis_plan({"playbook_id": "retention_lifecycle", "question_type": "diagnostic"})

    policy = _policy(
        intent=_intent(),
        state=state,
        user_input="analyze retention",
    )

    assert isinstance(policy, SynthesisPolicy)
    assert policy.answer_mode == "exploratory"
    assert policy.insight_depth == "none"
    assert policy.business_translation == "not_applicable"
    assert policy.required_moves == ["core_answer", "limitation", "next_step"]


def test_high_uncertainty_evidence_requires_assumptions_and_limits():
    policy = _policy(
        intent=_intent(),
        state=_state_with_evidence(confidence="low"),
        user_input="forecast LTV from this retention formula",
        data_profile="grain=daily_aggregate; retention metrics; no revenue metric; sparse tail",
    )

    assert isinstance(policy, SynthesisPolicy)
    assert policy.answer_mode == "advisory"
    assert policy.business_translation == "cautious"
    assert "assumptions" in policy.required_moves
    assert "limitation" in policy.required_moves
    assert "low" in policy.reason.lower() or "confidence" in policy.reason.lower()


def test_tool_errors_downgrade_deep_business_translation():
    policy = _policy(
        intent=_intent(),
        state=_state_with_evidence(),
        user_input="forecast LTV and give me decision recommendations",
        tool_error_count=3,
    )

    assert isinstance(policy, SynthesisPolicy)
    assert policy.answer_mode == "advisory"
    assert policy.insight_depth == "standard"
    assert policy.business_translation == "cautious"
    assert "tool errors" in policy.reason.lower()


def test_beginner_proficiency_changes_wording_only_not_depth():
    beginner = _policy(
        intent=_intent(),
        state=_state_with_evidence(),
        user_input="fit a retention curve formula from the data",
        proficiency="beginner",
    )
    advanced = _policy(
        intent=_intent(),
        state=_state_with_evidence(),
        user_input="fit a retention curve formula from the data",
        proficiency="advanced",
    )

    assert isinstance(beginner, SynthesisPolicy)
    assert isinstance(advanced, SynthesisPolicy)
    assert beginner.insight_depth == advanced.insight_depth == "light"
    assert beginner.wording_style == "plain_language"
    assert advanced.wording_style == "technical_concise"


def test_explicit_terse_requirement_suppresses_business_meaning():
    policy = _policy(
        intent=_intent(),
        state=_state_with_evidence(),
        user_input="formula only, no explanation",
        user_requirements="formula only, no explanation",
    )

    assert isinstance(policy, SynthesisPolicy)
    assert policy.answer_mode == "direct"
    assert policy.insight_depth == "none"
    assert "business_meaning" not in policy.required_moves


def test_retention_formula_regression_matches_expected_policy_shape():
    state = _state_with_evidence()
    state.analysis_plan.update({
        "playbook_id": "retention_lifecycle",
        "question_type": "diagnostic",
        "output_sections": [],
    })

    policy = _policy(
        intent=_intent(),
        state=state,
        user_input="fit a formula for new-user retention in this game dataset",
        data_profile="daily_aggregate retention table, no channel dimension",
    )

    assert isinstance(policy, SynthesisPolicy)
    assert policy.answer_mode == "analytical"
    assert policy.insight_depth == "light"
    assert policy.business_translation == "cautious"
    assert policy.risk_boundary == "descriptive"
    assert "business_meaning" in policy.required_moves
    assert "next_step" in policy.required_moves


def test_ltv_regression_requires_assumptions_and_caution():
    policy = _policy(
        intent=_intent(),
        state=_state_with_evidence(),
        user_input="use this retention formula to forecast LTV",
        data_profile="daily_aggregate retention table, no revenue metric",
    )

    assert isinstance(policy, SynthesisPolicy)
    assert policy.answer_mode == "advisory"
    assert policy.risk_boundary == "predictive"
    assert policy.business_translation == "cautious"
    assert "assumptions" in policy.required_moves
    assert "business_meaning" in policy.required_moves
    assert "next_step" in policy.required_moves


def test_pass_with_downgrades_verification_suppresses_decision_recommendations():
    policy = _policy(
        intent=_intent(),
        state=_state_with_verification("pass_with_downgrades"),
        user_input="forecast LTV and give me decision recommendations",
    )

    assert "decision_recommendation" in policy.suppressed_moves
    assert "limitation" in policy.required_moves
    assert policy.business_translation == "cautious"
    assert "pass_with_downgrades" in policy.reason


def test_failed_verification_suppresses_decision_recommendations():
    policy = _policy(
        intent=_intent(),
        state=_state_with_verification("fail"),
        user_input="fit a retention curve formula from the data",
    )

    assert "decision_recommendation" in policy.suppressed_moves
    assert "limitation" in policy.required_moves
    assert policy.business_translation == "cautious"
    assert "fail" in policy.reason


def test_pass_verification_does_not_add_extra_suppression_to_advisory_policy():
    policy = _policy(
        intent=_intent(),
        state=_state_with_verification("pass"),
        user_input="forecast LTV and give me decision recommendations",
    )

    assert policy.answer_mode == "advisory"
    assert policy.suppressed_moves == []
    assert "verification status" not in policy.reason.lower()


def test_direct_policy_with_failed_verification_applies_verification_limits():
    policy = _policy(
        intent=_intent(intent_type="simple_response", action="answer_directly"),
        state=_state_with_verification("fail"),
        user_input="hello",
    )

    assert policy.answer_mode == "direct"
    assert "decision_recommendation" in policy.suppressed_moves
    assert "limitation" in policy.required_moves
    assert policy.business_translation == "cautious"
    assert "fail" in policy.reason


def test_terse_policy_with_downgraded_verification_applies_verification_limits():
    policy = _policy(
        intent=_intent(),
        state=_state_with_verification("pass_with_downgrades"),
        user_input="formula only, no explanation",
    )

    assert policy.answer_mode == "direct"
    assert "decision_recommendation" in policy.suppressed_moves
    assert "limitation" in policy.required_moves
    assert policy.business_translation == "cautious"
    assert "pass_with_downgrades" in policy.reason


def test_no_evidence_with_failed_verification_stays_cautious_and_limited():
    state = AnalysisSessionState(session_id="no_evidence_failed_verification")
    state.verification_reports = [{"overall_status": "fail"}]

    policy = _policy(intent=_intent(), state=state, user_input="analyze retention")

    assert policy.answer_mode == "exploratory"
    assert policy.business_translation == "cautious"
    assert "decision_recommendation" in policy.suppressed_moves
    assert "limitation" in policy.required_moves
    assert "fail" in policy.reason


def test_state_none_does_not_crash_or_change_base_policy():
    policy = _policy(intent=_intent(), state=None, user_input="analyze retention")

    assert policy.answer_mode == "exploratory"
    assert policy.business_translation == "not_applicable"
    assert "verification status" not in policy.reason.lower()


def test_dict_state_reads_verification_reports():
    state = {
        "evidence_records": _state_with_evidence().evidence_records,
        "verification_reports": [{"overall_status": "fail"}],
    }

    policy = _policy(intent=_intent(), state=state, user_input="fit retention curve")

    assert "decision_recommendation" in policy.suppressed_moves
    assert policy.business_translation == "cautious"
    assert "fail" in policy.reason


def test_malformed_verification_reports_do_not_change_policy():
    base_kwargs = {
        "intent": _intent(),
        "state": _state_with_evidence(),
        "user_input": "forecast LTV and give me decision recommendations",
    }
    base = _policy(**base_kwargs)

    for reports in ("fail", [], [{"overall_status": "fail"}, "latest is malformed"]):
        state = _state_with_evidence()
        state.verification_reports = reports
        policy = _policy(intent=_intent(), state=state, user_input=base_kwargs["user_input"])

        assert policy.suppressed_moves == base.suppressed_moves
        assert policy.business_translation == base.business_translation
        assert "verification status" not in policy.reason.lower()


def test_pandas_or_numpy_verification_reports_do_not_raise_truth_value_ambiguity():
    for reports in (pd.Series([{"overall_status": "fail"}]), np.array([{"overall_status": "fail"}])):
        state = _state_with_evidence()
        state.verification_reports = reports

        policy = _policy(intent=_intent(), state=state, user_input="fit retention curve")

        assert policy.answer_mode == "analytical"
        assert "verification status" not in policy.reason.lower()
