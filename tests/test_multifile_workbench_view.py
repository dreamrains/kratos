import json

from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.data_understanding import build_data_understanding_bundle
from data_agent.agent.trust_workflow_runtime import _evidence_fingerprint


def _state_with_multifile_context() -> AnalysisSessionState:
    state = AnalysisSessionState(session_id="workbench_read_model", data_state="data_loaded")
    bundle = build_data_understanding_bundle(
        datasets=[{
            "dataset": "orders",
            "dataset_contract_id": "duc_orders",
            "rows": 20,
            "columns": [
                {"name": "date", "type": "datetime"},
                {"name": "order_id", "type": "string"},
                {"name": "gmv", "type": "number"},
            ],
            "grain": "one row per order",
            "artifact_path": "sessions/s1/private.json",
        }],
        quality_findings=[{"dataset": "orders", "finding": "ready for trend analysis"}],
        relationship_candidates=[],
        supported_questions=["What is GMV trend?"],
        unsupported_questions=["What is CAC?"],
        analysis_constraints=["No acquisition cost dataset loaded."],
    )
    state.add_data_understanding_bundle_ref(bundle)
    state.dataset_contracts = [{
        "id": "duc_orders",
        "dataset": "orders",
        "field_roles": {"date": ["date"], "metrics": ["gmv"], "ids": ["order_id"]},
        "columns": ["date", "order_id", "gmv"],
        "quality": {"status": "ready"},
    }]
    state.route_proposals = [{
        "id": "route_trend",
        "dataset": "orders",
        "direction": "trend",
        "label": "GMV trend",
        "reason": "Time and GMV fields are available.",
        "evidence_requirements": ["daily GMV trend"],
        "artifact_path": "sessions/s1/route.json",
    }]
    state.file_relationships = [{
        "relationship_id": "rel_orders_payments",
        "file_ids": ["orders", "payments"],
        "status": "proposed",
        "relationship_status": "diagnostic_only",
        "requires_confirmation": False,
        "evidence": ["shared user_id"],
        "uncertainties": ["different time windows"],
    }]
    state.evidence_records = [{
        "id": "ev_gmv",
        "claim": "GMV increased in the final two days.",
        "confidence": "medium",
        "result_summary": "Daily GMV moved from 100 to 150.",
        "artifact_path": "sessions/s1/evidence.json",
    }]
    state.verification_reports = [{
        "id": "verify_1",
        "overall_status": "passed",
        "claim_count": 1,
        "failed_count": 0,
        "passed_evidence_ids": ["ev_gmv"],
    }]
    state.verification_reports[0]["evidence_fingerprint"] = _evidence_fingerprint(
        state, state.evidence_records
    )
    return state


def test_multifile_context_does_not_expand_the_minimal_workbench_projection():
    from data_agent.agent.workbench_view import build_workbench_view

    view = build_workbench_view(_state_with_multifile_context())

    assert set(view) == {"verified_conclusions"}
    rendered = json.dumps(view, ensure_ascii=False)
    assert "relationships" not in rendered
    assert "artifact_path" not in rendered


def test_trust_view_embeds_multifile_workbench_read_model():
    from data_agent.agent.trust_view import build_trust_view

    view = build_trust_view(_state_with_multifile_context())

    assert view["workbench"] == {"verified_conclusions": [
        {
            "id": "ev_gmv",
            "claim": "GMV increased in the final two days.",
            "summary": "Daily GMV moved from 100 to 150.",
            "confidence": "medium",
            "dataset": "",
        }
    ]}


def test_trust_view_exposes_only_workbench_and_bounded_validation_details():
    from data_agent.agent.trust_view import build_trust_view

    view = build_trust_view(_state_with_multifile_context())

    assert set(view) == {"status", "session_id", "updated_at", "workbench"}
    assert set(view["workbench"]) == {"verified_conclusions"}
    rendered = json.dumps(view, ensure_ascii=False)
    assert "artifact_path" not in rendered
    assert "evidence_signature" not in rendered
    assert "task_refs" not in rendered
# The file intentionally ends on this assertion to avoid a blank EOF line.
