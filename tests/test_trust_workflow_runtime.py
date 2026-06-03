from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.intent import TurnIntent
from data_agent.agent.trust_workflow_runtime import refine_turn_intent_with_state


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
