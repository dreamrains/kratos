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
    assert set(view["workbench"]) == {"action_board", "multifile_analysis", "details", "full_answer"}
    assert set(view["workbench"]["action_board"]) == {"confirmed", "uncertain", "next_steps", "trust_basis"}
    assert set(view["workbench"]["details"]) == {
        "scope",
        "confirmation",
        "verification",
    }
    rendered = json.dumps(view, ensure_ascii=False)
    assert "artifact_path" not in rendered
    assert "evidence_signature" not in rendered
    assert "task_refs" not in rendered


from types import SimpleNamespace

from data_agent.agent.workbench_view import build_action_board


def _ab_state(evidence, verification=None, route_proposals=None, bundles=None):
    return SimpleNamespace(
        evidence_records=evidence,
        verification_reports=verification or [],
        route_proposals=route_proposals or [],
        data_understanding_bundles=bundles or [],
        file_relationships=[],
        goal="评估省钱卡业务",
        data_state="data_loaded",
    )


def test_action_board_confirmed_and_uncertain_by_confidence():
    state = _ab_state(
        [
            {"claim": "购卡后消费下降30%", "confidence": "high", "dataset": "orders",
             "result_summary": "-30%", "limitations": []},
            {"claim": "复购意愿弱", "confidence": "medium", "dataset": "orders",
             "result_summary": "复购低", "limitations": ["样本仅1月"]},
            {"claim": "优惠券驱动复购", "confidence": "speculative", "dataset": "vouchers",
             "result_summary": "不确定", "limitations": []},
        ],
        verification=[{"overall_status": "pass_with_downgrades", "claim_count": 3,
                       "failed_count": 0, "downgraded_count": 1}],
    )
    ab = build_action_board(state)
    confirmed_claims = [c["claim"] for c in ab["confirmed"]]
    assert confirmed_claims == ["购卡后消费下降30%", "复购意愿弱"]  # high before medium
    assert ab["confirmed"][0]["confidence"] == "high"
    uncertain_labels = [u["label"] for u in ab["uncertain"]]
    assert "优惠券驱动复购" in uncertain_labels          # low/speculative claim
    assert any(u["reason"] == "limitation" for u in ab["uncertain"])  # limitation surfaced
    assert ab["uncertain"][-1]["label"] == "样本仅1月"
    tb = ab["trust_basis"]
    assert tb["evidence_count"] == 3
    assert tb["verification_status"] == "pass_with_downgrades"
    assert tb["downgraded_count"] == 1
    assert tb["failed_count"] == 0


def test_action_board_next_steps_from_routes_and_confirmations():
    state = _ab_state(
        [{"claim": "x", "confidence": "high", "dataset": "d", "result_summary": "", "limitations": []}],
        bundles=[{"id": "b1", "data_fingerprint": "f", "datasets": [{"dataset": "d"}],
                  "supported_questions": [], "unsupported_questions": ["还需渠道成本"],
                  "needed_confirmations": ["确认对比口径"]}],
        route_proposals=[],  # build_route_capabilities returns empty without real route shape
    )
    ab = build_action_board(state)
    # datasets_used derived from the brief; confirmations surface as next_steps
    assert "d" in ab["trust_basis"]["datasets_used"]
    kinds = {n["kind"] for n in ab["next_steps"]}
    assert "confirmation" in kinds


def test_action_board_empty_when_state_none():
    ab = build_action_board(None)
    assert ab["confirmed"] == [] and ab["uncertain"] == [] and ab["next_steps"] == []
    assert ab["trust_basis"]["verification_status"] == "not_run"
    assert ab["trust_basis"]["evidence_count"] == 0
