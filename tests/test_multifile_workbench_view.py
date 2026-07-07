import json

from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.data_understanding import build_data_understanding_bundle


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
    }]
    return state


def test_multifile_workbench_view_has_four_user_value_sections():
    from data_agent.agent.workbench_view import build_multifile_workbench_view

    view = build_multifile_workbench_view(_state_with_multifile_context())

    assert set(view) == {
        "data_understanding",
        "relationships",
        "analysis_directions",
        "answer_coverage",
    }
    assert view["analysis_directions"][0]["source"] == "route_capabilities"
    assert view["answer_coverage"]["evidence_count"] == 1
    assert view["relationships"][0]["evidence"] == ["shared user_id"]
    assert view["relationships"][0]["uncertainties"] == ["different time windows"]
    assert view["relationships"][0]["diagnostic_only"] is True
    rendered = json.dumps(view, ensure_ascii=False)
    assert "artifact_path" not in rendered
    assert "scheduler" not in rendered.lower()


def test_trust_view_embeds_multifile_workbench_read_model():
    from data_agent.agent.trust_view import build_trust_view

    view = build_trust_view(_state_with_multifile_context())

    assert view["workbench"]["multifile_analysis"]["data_understanding"]["datasets"][0]["dataset"] == "orders"


def test_trust_view_exposes_only_workbench_and_bounded_validation_details():
    from data_agent.agent.trust_view import build_trust_view

    view = build_trust_view(_state_with_multifile_context())

    assert set(view) == {"status", "session_id", "updated_at", "workbench"}
    assert set(view["workbench"]) == {"multifile_analysis", "details"}
    assert set(view["workbench"]["details"]) == {
        "scope",
        "confirmation",
        "verification",
    }
    rendered = json.dumps(view, ensure_ascii=False)
    assert "artifact_path" not in rendered
    assert "evidence_signature" not in rendered
    assert "task_refs" not in rendered
