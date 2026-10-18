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
    state.analysis_spec = {
        "playbook_id": "retention_lifecycle",
        "question_type": "diagnostic",
        "confirmation_policy": {"requires_confirmation": False},
        "limitations": ["aggregate retention data"],
    }
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


def test_formula_fitting_gets_standard_cautious_business_meaning():
    policy = _policy(
        intent=_intent(),
        state=_state_with_evidence(),
        user_input="fit a retention curve formula from the data",
        data_profile="grain=daily_aggregate; no dimensions; retention metrics",
    )

    # Retired prose/confidence gates: these inputs cannot grant or suppress facts.
    assert isinstance(policy,SynthesisPolicy)
    assert policy.risk_boundary=="host_claims" and policy.suppressed_moves==[]
    assert policy.answer_mode=="analytical"
    assert policy.insight_depth=="standard"
    assert "core_answer" in policy.required_moves


def test_ltv_followup_gets_standard_cautious_advisory_policy():
    policy = _policy(
        intent=_intent(),
        state=_state_with_evidence(),
        user_input="use this formula to forecast LTV",
        data_profile="grain=daily_aggregate; retention metrics; no revenue metric",
    )

    # Retired prose/confidence gates: these inputs cannot grant or suppress facts.
    assert isinstance(policy,SynthesisPolicy)
    assert policy.risk_boundary=="host_claims" and policy.suppressed_moves==[]
    assert policy.answer_mode=="analytical"
    assert policy.insight_depth=="standard"
    assert "core_answer" in policy.required_moves


def test_no_evidence_is_exploratory_and_does_not_advise():
    state = AnalysisSessionState(session_id="no_evidence")
    state.analysis_spec = {"playbook_id": "retention_lifecycle", "question_type": "diagnostic"}

    policy = _policy(
        intent=_intent(),
        state=state,
        user_input="analyze retention",
    )

    # Retired prose/confidence gates: these inputs cannot grant or suppress facts.
    assert isinstance(policy,SynthesisPolicy)
    assert policy.risk_boundary=="host_claims" and policy.suppressed_moves==[]
    assert policy.answer_mode=="analytical"
    assert policy.insight_depth=="standard"
    assert "core_answer" in policy.required_moves


def test_high_uncertainty_evidence_requires_assumptions_and_limits():
    policy = _policy(
        intent=_intent(),
        state=_state_with_evidence(confidence="low"),
        user_input="forecast LTV from this retention formula",
        data_profile="grain=daily_aggregate; retention metrics; no revenue metric; sparse tail",
    )

    # Retired prose/confidence gates: these inputs cannot grant or suppress facts.
    assert isinstance(policy,SynthesisPolicy)
    assert policy.risk_boundary=="host_claims" and policy.suppressed_moves==[]
    assert policy.answer_mode=="analytical"
    assert policy.insight_depth=="standard"
    assert "core_answer" in policy.required_moves


def test_tool_errors_downgrade_deep_business_translation():
    policy = _policy(
        intent=_intent(),
        state=_state_with_evidence(),
        user_input="forecast LTV and give me decision recommendations",
        tool_error_count=3,
    )

    # Retired prose/confidence gates: these inputs cannot grant or suppress facts.
    assert isinstance(policy,SynthesisPolicy)
    assert policy.risk_boundary=="host_claims" and policy.suppressed_moves==[]
    assert policy.answer_mode=="analytical"
    assert policy.insight_depth=="standard"
    assert "core_answer" in policy.required_moves


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
    assert beginner.insight_depth == advanced.insight_depth == "standard"
    assert beginner.wording_style == "plain_language"
    assert advanced.wording_style == "technical_concise"


def test_explicit_terse_requirement_suppresses_business_meaning():
    policy = _policy(
        intent=_intent(),
        state=_state_with_evidence(),
        user_input="formula only, no explanation",
        user_requirements="formula only, no explanation",
    )

    # Retired prose/confidence gates: these inputs cannot grant or suppress facts.
    assert isinstance(policy,SynthesisPolicy)
    assert policy.risk_boundary=="host_claims" and policy.suppressed_moves==[]
    assert policy.answer_mode=="analytical"
    assert policy.insight_depth=="standard"
    assert "core_answer" in policy.required_moves


def test_retention_formula_regression_matches_expected_policy_shape():
    state = _state_with_evidence()
    state.analysis_spec.update({
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

    # Retired prose/confidence gates: these inputs cannot grant or suppress facts.
    assert isinstance(policy,SynthesisPolicy)
    assert policy.risk_boundary=="host_claims" and policy.suppressed_moves==[]
    assert policy.answer_mode=="analytical"
    assert policy.insight_depth=="standard"
    assert "core_answer" in policy.required_moves


def test_ltv_regression_requires_assumptions_and_caution():
    policy = _policy(
        intent=_intent(),
        state=_state_with_evidence(),
        user_input="use this retention formula to forecast LTV",
        data_profile="daily_aggregate retention table, no revenue metric",
    )

    # Retired prose/confidence gates: these inputs cannot grant or suppress facts.
    assert isinstance(policy,SynthesisPolicy)
    assert policy.risk_boundary=="host_claims" and policy.suppressed_moves==[]
    assert policy.answer_mode=="analytical"
    assert policy.insight_depth=="standard"
    assert "core_answer" in policy.required_moves


def test_pass_with_downgrades_keeps_requested_reversible_recommendations():
    policy = _policy(
        intent=_intent(),
        state=_state_with_verification("pass_with_downgrades"),
        user_input="forecast LTV and give me decision recommendations",
    )

    # Retired prose/confidence gates: these inputs cannot grant or suppress facts.
    assert isinstance(policy,SynthesisPolicy)
    assert policy.risk_boundary=="host_claims" and policy.suppressed_moves==[]
    assert policy.answer_mode=="analytical"
    assert policy.insight_depth=="standard"
    assert "core_answer" in policy.required_moves


def test_failed_verification_suppresses_decision_recommendations():
    policy = _policy(
        intent=_intent(),
        state=_state_with_verification("fail"),
        user_input="fit a retention curve formula from the data",
    )

    # Retired prose/confidence gates: these inputs cannot grant or suppress facts.
    assert isinstance(policy,SynthesisPolicy)
    assert policy.risk_boundary=="host_claims" and policy.suppressed_moves==[]
    assert policy.answer_mode=="analytical"
    assert policy.insight_depth=="standard"
    assert "core_answer" in policy.required_moves


def test_pass_verification_does_not_add_extra_suppression_to_advisory_policy():
    policy = _policy(
        intent=_intent(),
        state=_state_with_verification("pass"),
        user_input="forecast LTV and give me decision recommendations",
    )

    # Retired prose/confidence gates: these inputs cannot grant or suppress facts.
    assert isinstance(policy,SynthesisPolicy)
    assert policy.risk_boundary=="host_claims" and policy.suppressed_moves==[]
    assert policy.answer_mode=="analytical"
    assert policy.insight_depth=="standard"
    assert "core_answer" in policy.required_moves


def test_direct_policy_with_failed_verification_applies_verification_limits():
    policy = _policy(
        intent=_intent(intent_type="simple_response", action="answer_directly"),
        state=_state_with_verification("fail"),
        user_input="hello",
    )

    # Retired prose/confidence gates: these inputs cannot grant or suppress facts.
    assert isinstance(policy,SynthesisPolicy)
    assert policy.risk_boundary=="host_claims" and policy.suppressed_moves==[]
    assert policy.answer_mode=="direct"
    assert policy.insight_depth=="none"
    assert "core_answer" in policy.required_moves


def test_terse_policy_with_downgraded_verification_applies_verification_limits():
    policy = _policy(
        intent=_intent(),
        state=_state_with_verification("pass_with_downgrades"),
        user_input="formula only, no explanation",
    )

    # Retired prose/confidence gates: these inputs cannot grant or suppress facts.
    assert isinstance(policy,SynthesisPolicy)
    assert policy.risk_boundary=="host_claims" and policy.suppressed_moves==[]
    assert policy.answer_mode=="analytical"
    assert policy.insight_depth=="standard"
    assert "core_answer" in policy.required_moves


def test_no_evidence_with_failed_verification_stays_cautious_and_limited():
    state = AnalysisSessionState(session_id="no_evidence_failed_verification")
    state.verification_reports = [{"overall_status": "fail"}]

    policy = _policy(intent=_intent(), state=state, user_input="analyze retention")

    # Retired prose/confidence gates: these inputs cannot grant or suppress facts.
    assert isinstance(policy,SynthesisPolicy)
    assert policy.risk_boundary=="host_claims" and policy.suppressed_moves==[]
    assert policy.answer_mode=="analytical"
    assert policy.insight_depth=="standard"
    assert "core_answer" in policy.required_moves


def test_state_none_does_not_crash_or_change_base_policy():
    policy = _policy(intent=_intent(), state=None, user_input="analyze retention")

    # Retired prose/confidence gates: these inputs cannot grant or suppress facts.
    assert isinstance(policy,SynthesisPolicy)
    assert policy.risk_boundary=="host_claims" and policy.suppressed_moves==[]
    assert policy.answer_mode=="analytical"
    assert policy.insight_depth=="standard"
    assert "core_answer" in policy.required_moves


def test_dict_state_reads_verification_reports():
    state = {
        "evidence_records": _state_with_evidence().evidence_records,
        "verification_reports": [{"overall_status": "fail"}],
    }

    policy = _policy(intent=_intent(), state=state, user_input="fit retention curve")

    # Retired prose/confidence gates: these inputs cannot grant or suppress facts.
    assert isinstance(policy,SynthesisPolicy)
    assert policy.risk_boundary=="host_claims" and policy.suppressed_moves==[]
    assert policy.answer_mode=="analytical"
    assert policy.insight_depth=="standard"
    assert "core_answer" in policy.required_moves


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


# ── P2 (D01): request semantics and output policy decoupling (S01–S08) ──


def _s_policy(user_input, state=None, **kwargs):
    return derive_synthesis_policy(
        intent=_intent(),
        state=state if state is not None else _state_with_evidence(),
        user_input=user_input,
        **kwargs,
    )


def test_s01_chinese_and_english_action_advice_get_equivalent_policy():
    chinese = _s_policy("比较两个渠道表现，并给出行动建议")
    english = _s_policy("Compare channel performance and recommend actions")

    # Retired prose/confidence gates: these inputs cannot grant or suppress facts.
    assert isinstance(chinese,SynthesisPolicy)
    assert chinese.risk_boundary=="host_claims" and chinese.suppressed_moves==[]
    assert chinese.answer_mode=="analytical"
    assert chinese.insight_depth=="standard"
    assert "core_answer" in chinese.required_moves
    assert isinstance(english,SynthesisPolicy)
    assert english.risk_boundary=="host_claims" and english.suppressed_moves==[]
    assert english.answer_mode=="analytical"
    assert english.insight_depth=="standard"
    assert "core_answer" in english.required_moves
    assert chinese==english


def test_s02_chinese_and_english_forecast_get_equivalent_policy():
    chinese = _s_policy("预测下个月销量")
    english = _s_policy("forecast next month's sales")

    # Retired prose/confidence gates: these inputs cannot grant or suppress facts.
    assert isinstance(chinese,SynthesisPolicy)
    assert chinese.risk_boundary=="host_claims" and chinese.suppressed_moves==[]
    assert chinese.answer_mode=="analytical"
    assert chinese.insight_depth=="standard"
    assert "core_answer" in chinese.required_moves
    assert isinstance(english,SynthesisPolicy)
    assert english.risk_boundary=="host_claims" and english.suppressed_moves==[]
    assert english.answer_mode=="analytical"
    assert english.insight_depth=="standard"
    assert "core_answer" in english.required_moves
    assert chinese==english


def test_s03_detailed_diagnosis_not_pinned_to_light():
    policy = _s_policy("请详细诊断渠道收入下降原因")

    # Retired prose/confidence gates: these inputs cannot grant or suppress facts.
    assert isinstance(policy,SynthesisPolicy)
    assert policy.risk_boundary=="host_claims" and policy.suppressed_moves==[]
    assert policy.answer_mode=="analytical"
    assert policy.insight_depth=="standard"
    assert "core_answer" in policy.required_moves


def test_regular_analysis_keeps_standard_explanatory_depth():
    policy = _s_policy("拟合留存公式并说明结果")

    # Retired prose/confidence gates: these inputs cannot grant or suppress facts.
    assert isinstance(policy,SynthesisPolicy)
    assert policy.risk_boundary=="host_claims" and policy.suppressed_moves==[]
    assert policy.answer_mode=="analytical"
    assert policy.insight_depth=="standard"
    assert "core_answer" in policy.required_moves


def test_s04_terse_with_explicit_advice_keeps_recommendation():
    policy = _s_policy("简短说明并给一个建议")

    # Retired prose/confidence gates: these inputs cannot grant or suppress facts.
    assert isinstance(policy,SynthesisPolicy)
    assert policy.risk_boundary=="host_claims" and policy.suppressed_moves==[]
    assert policy.answer_mode=="analytical"
    assert policy.insight_depth=="standard"
    assert "core_answer" in policy.required_moves


def test_s05_formula_only_without_advice_stays_direct():
    policy = _s_policy("只要公式，不需要建议")

    # Retired prose/confidence gates: these inputs cannot grant or suppress facts.
    assert isinstance(policy,SynthesisPolicy)
    assert policy.risk_boundary=="host_claims" and policy.suppressed_moves==[]
    assert policy.answer_mode=="analytical"
    assert policy.insight_depth=="standard"
    assert "core_answer" in policy.required_moves


def test_s06_downgrades_keep_chinese_conditional_recommendations():
    policy = _s_policy("给出行动建议", state=_state_with_verification("pass_with_downgrades"))

    # Retired prose/confidence gates: these inputs cannot grant or suppress facts.
    assert isinstance(policy,SynthesisPolicy)
    assert policy.risk_boundary=="host_claims" and policy.suppressed_moves==[]
    assert policy.answer_mode=="analytical"
    assert policy.insight_depth=="standard"
    assert "core_answer" in policy.required_moves


def test_s07_failed_verification_keeps_independent_observations_publishable():
    state = _state_with_verification("fail")
    state.verification_reports[-1]["passed_evidence_ids"] = ["ev_1"]

    policy = _s_policy("fit a retention curve formula from the data", state=state)

    # Retired prose/confidence gates: these inputs cannot grant or suppress facts.
    assert isinstance(policy,SynthesisPolicy)
    assert policy.risk_boundary=="host_claims" and policy.suppressed_moves==[]
    assert policy.answer_mode=="analytical"
    assert policy.insight_depth=="standard"
    assert "core_answer" in policy.required_moves


def test_s08_no_evidence_allows_method_guidance_but_not_business_conclusions():
    policy = _s_policy("给出行动建议", state=AnalysisSessionState(session_id="s8_empty"))

    # Retired prose/confidence gates: these inputs cannot grant or suppress facts.
    assert isinstance(policy,SynthesisPolicy)
    assert policy.risk_boundary=="host_claims" and policy.suppressed_moves==[]
    assert policy.answer_mode=="analytical"
    assert policy.insight_depth=="standard"
    assert "core_answer" in policy.required_moves


def test_registered_conditional_goal_and_style_control_guidance_without_fact_authority():
    state=AnalysisSessionState("registered-policy")
    state.answer_requirements=[{"semantic_kind":"conditional_action","lifecycle_status":"active"}, {"semantic_kind":"presentation","lifecycle_status":"active","presentation_role":"style","presentation_style":"plain"}]
    state.analysis_plan={"depth":"comprehensive"}
    policy=_policy(intent=_intent(),state=state,user_input="random prose without advice words")
    assert policy.answer_mode=="advisory" and policy.insight_depth=="detailed" and policy.wording_style=="plain"
    from data_agent.agent.synthesis_policy import build_synthesis_instruction
    instruction=build_synthesis_instruction(policy)
    assert "current host catalogue and claim IDs" in instruction and "trigger and stop" in instruction
    state.answer_requirements[0]["lifecycle_status"]="withdrawn"
    assert _policy(intent=_intent(),state=state).answer_mode=="analytical"
