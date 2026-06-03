from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent import trust_workflow_runtime as runtime
from data_agent.agent.intent import TurnIntent
from data_agent.agent.trust_workflow_runtime import maybe_verify_turn_claims, refine_turn_intent_with_state


def _intent(intent_type="intent_negotiation", **overrides):
    values = {
        "intent_type": intent_type,
        "clarity": "vague",
        "data_state": "data_loaded",
        "analysis_stage": "discover",
        "recommended_action": "guide_analysis",
        "execution_readiness": "ready",
        "reason": "test",
        "ambiguities": [],
    }
    values.update(overrides)
    return TurnIntent(**values)


def test_runtime_refines_vague_intent_with_state_routes():
    state = AnalysisSessionState(session_id="runtime_refine_routes")
    state.route_proposals = [
        {"id": "route_trend", "label": "Revenue trend", "direction": "trend"},
        {"id": "route_compare", "label": "Period compare", "direction": "period_compare"},
    ]

    refined = refine_turn_intent_with_state("help me explore this dataset", _intent(), state)

    assert refined.recommended_action == "guide_analysis"
    assert refined.ambiguities[-1]["field"] == "analysis_route"
    assert refined.ambiguities[-1]["routes"] == [
        {"label": "Revenue trend", "direction": "trend"},
        {"label": "Period compare", "direction": "period_compare"},
    ]


def test_runtime_marks_unsupported_retention_request_as_insufficient_data():
    state = AnalysisSessionState(session_id="runtime_refine_retention")
    state.dataset_contracts = [{
        "id": "contract_orders",
        "unsupported_analyses": [
            {"type": "user_level_retention", "reason": "missing user id"},
        ],
    }]
    base = _intent(
        "directed_analysis",
        clarity="clear",
        analysis_stage="execute",
        recommended_action="run_analysis",
    )

    refined = refine_turn_intent_with_state("analyze cohort retention", base, state)

    assert refined.clarity == "clarification_needed"
    assert refined.recommended_action == "request_data"
    assert refined.execution_readiness == "insufficient_data"
    assert refined.ambiguities[-1]["field"] == "unsupported_analysis"


def test_runtime_refinement_falls_back_when_state_refs_are_malformed():
    class MalformedState:
        dataset_contracts = {"not": "a list"}
        route_proposals = {"not": "a list"}

    base = _intent()

    refined = refine_turn_intent_with_state("help me explore", base, MalformedState())

    assert refined is base


def test_runtime_generates_compact_verification_report_from_evidence_records():
    state = AnalysisSessionState(session_id="runtime_verify")
    state.evidence_records = [{
        "id": "ev_1",
        "claim": "Revenue increased 12%",
        "result_summary": "Revenue increased 12% from 100 to 112",
        "confidence": "high",
        "dataset": "sales",
        "method": "period_compare",
        "sample_size": 1200,
        "time_scope": "2026-05-01 to 2026-05-31",
        "calculation_method": "monthly revenue delta",
        "method_detail": "compared current revenue against prior revenue",
        "limitations": ["descriptive comparison only"],
    }]
    state.route_proposals = [{"id": "route_trend", "direction": "trend"}]

    ref = maybe_verify_turn_claims("summarize revenue", state)

    assert ref is not None
    assert ref["id"].startswith("verify_")
    assert ref["overall_status"] == "pass"
    assert ref["claim_count"] == 1
    assert ref["failed_count"] == 0
    assert ref["downgraded_count"] == 0
    assert ref["evidence_signature"] == "ev_1|routes:route_trend|cleaning:"
    assert state.verification_reports[-1] == ref


def test_runtime_verification_deduplicates_latest_evidence_signature():
    state = AnalysisSessionState(session_id="runtime_verify_dedupe")
    state.evidence_records = [{
        "id": "ev_1",
        "claim": "Revenue increased 12%",
        "result_summary": "Revenue increased 12%",
        "confidence": "high",
    }]

    first = maybe_verify_turn_claims("summarize revenue", state)
    second = maybe_verify_turn_claims("summarize revenue again", state)

    assert first is not None
    assert second is None
    assert len(state.verification_reports) == 1


def test_runtime_verification_skips_when_no_claims_are_available():
    state = AnalysisSessionState(session_id="runtime_verify_empty")
    state.evidence_records = [{"id": "ev_no_claim", "result_summary": "summary only"}]

    ref = maybe_verify_turn_claims("summarize", state)

    assert ref is None
    assert state.verification_reports == []


def test_runtime_verification_force_overrides_signature_dedupe():
    state = AnalysisSessionState(session_id="runtime_verify_force")
    state.evidence_records = [{
        "id": "ev_1",
        "claim": "Revenue increased 12%",
        "result_summary": "Revenue increased 12%",
        "confidence": "high",
    }]

    first = maybe_verify_turn_claims("summarize revenue", state)
    second = maybe_verify_turn_claims("summarize revenue again", state, force=True)

    assert first is not None
    assert second is not None
    assert len(state.verification_reports) == 1
    assert state.verification_reports[-1]["id"] == second["id"]


def test_runtime_verification_counts_failed_claim_checks(monkeypatch):
    state = AnalysisSessionState(session_id="runtime_verify_failed")
    state.evidence_records = [{
        "id": "ev_1",
        "claim": "Revenue increased 12%",
        "result_summary": "Revenue increased 12%",
        "confidence": "high",
    }]

    def fake_verify_analysis_claims(**_kwargs):
        return {
            "id": "failed_report",
            "claim_checks": [{
                "claim_id": "claim_1",
                "claim": "Revenue increased 12%",
                "evidence_id": None,
                "status": "failed",
                "strength": "unsupported",
                "issues": ["No evidence record supports this claim"],
            }],
            "route_proposal_ids": [],
            "overall_status": "fail",
        }

    monkeypatch.setattr(runtime, "verify_analysis_claims", fake_verify_analysis_claims)

    ref = maybe_verify_turn_claims("summarize revenue", state)

    assert ref is not None
    assert ref["overall_status"] == "fail"
    assert ref["claim_count"] == 1
    assert ref["failed_count"] == 1
