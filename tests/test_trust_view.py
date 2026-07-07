import json

from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.trust_view import build_trust_view


def test_empty_trust_view_is_only_an_empty_workbench_contract() -> None:
    view = build_trust_view(None, session_id="missing")

    assert set(view) == {"status", "session_id", "updated_at", "workbench"}
    assert view["status"] == "empty"
    assert view["session_id"] == "missing"
    assert set(view["workbench"]) == {"multifile_analysis", "details"}
    assert set(view["workbench"]["multifile_analysis"]) == {
        "data_understanding",
        "relationships",
        "analysis_directions",
        "answer_coverage",
    }


def test_workbench_projects_scope_confirmation_and_verification_without_internal_ids() -> None:
    state = AnalysisSessionState(session_id="bounded_details", data_state="data_loaded")
    state.goal = "Evaluate savings-card performance"
    state.data_pool = [{
        "file_id": "orders_file",
        "filename": "orders.xlsx",
        "dataset": "orders",
        "status": "loaded",
    }]
    state.dataset_contracts = [{
        "id": "duc_orders",
        "dataset": "orders",
        "quality_status": "ready",
    }]
    state.analysis_plan = {
        "method_plan": [{"step_id": "step_orders", "dataset_inputs": ["orders"]}]
    }
    state.pending_confirmations = [{
        "id": "confirm_method",
        "status": "pending",
        "confirmation_type": "method_confirmation",
        "question": "Use a 30-day comparison window?",
        "blocking_reason": "The window changes the interpretation.",
    }]
    state.verification_reports = [{
        "overall_status": "pass_with_downgrades",
        "claim_count": 3,
        "failed_count": 0,
        "downgraded_count": 1,
        "evidence_signature": "private-signature",
        "artifact_path": "sessions/private/verification.json",
    }]

    before = state.to_dict()
    view = build_trust_view(state)

    assert state.to_dict() == before
    details = view["workbench"]["details"]
    assert details["scope"]["goal"] == "Evaluate savings-card performance"
    assert details["scope"]["files"][0]["assignment"] == "used"
    assert details["scope"]["files"][0]["task_count"] == 1
    assert details["confirmation"]["status"] == "needs_confirmation"
    assert details["verification"] == {
        "status": "pass_with_downgrades",
        "claim_count": 3,
        "failed_count": 0,
        "downgraded_count": 1,
        "created_at": "",
    }
    rendered = json.dumps(view, ensure_ascii=False)
    assert "task_refs" not in rendered
    assert "evidence_signature" not in rendered
    assert "artifact_path" not in rendered


def test_relationships_remain_diagnostic_and_keep_bounded_supporting_detail() -> None:
    state = AnalysisSessionState(session_id="relationship_details", data_state="data_loaded")
    state.file_relationships = [{
        "relationship_id": "rel_orders_flow",
        "status": "rejected",
        "file_ids": ["orders", "flow"],
        "value": "Can compare user coverage.",
        "risk": "Many-to-many row multiplication.",
        "evidence": ["shared user_id", "high key coverage", "extra evidence", "fourth", "fifth"],
        "uncertainties": ["different time windows"],
        "requires_confirmation": True,
    }]

    relationship = build_trust_view(state)["workbench"]["multifile_analysis"]["relationships"][0]

    assert relationship["diagnostic_only"] is True
    assert relationship["status"] == "rejected"
    assert relationship["evidence"] == [
        "shared user_id",
        "high key coverage",
        "extra evidence",
        "fourth",
    ]
    assert relationship["uncertainties"] == ["different time windows"]


def test_analysis_directions_are_suggestions_and_never_auto_submit() -> None:
    state = AnalysisSessionState(session_id="directions", data_state="data_loaded")
    state.active_scope.update({"active_dataset": "orders", "active_mode": "data_loaded"})
    state.dataset_contracts = [{
        "id": "duc_orders",
        "dataset": "orders",
        "field_roles": {"date": ["date"], "metrics": ["gmv"]},
        "quality_status": "ready",
    }]
    state.route_proposals = [{
        "id": "route_trend",
        "dataset": "orders",
        "direction": "trend",
        "label": "GMV trend",
        "reason": "Date and GMV are available.",
        "evidence_requirements": ["daily GMV"],
    }]

    directions = build_trust_view(state)["workbench"]["multifile_analysis"]["analysis_directions"]

    assert directions
    assert all(item["auto_submit"] is False for item in directions)


def test_loaded_state_is_ready_even_before_evidence_exists() -> None:
    state = AnalysisSessionState(session_id="loaded", data_state="data_loaded")

    view = build_trust_view(state)

    assert view["status"] == "ready"
    assert view["workbench"]["multifile_analysis"]["answer_coverage"]["status"] == "not_started"
