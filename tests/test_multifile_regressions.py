from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.multi_file_scope import build_analysis_scope_plan
from data_agent.agent.route_capabilities import build_route_capabilities
from data_agent.agent.trust_view import build_trust_view


def test_scope_plan_keeps_orders_and_coupon_profiles_linkable_by_user_aliases():
    state = AnalysisSessionState(session_id="a4237f2cee72_regression", data_state="data_loaded")
    state.data_pool = [
        {
            "file_id": "orders",
            "filename": "省钱卡订单.xlsx",
            "dataset": "省钱卡订单",
            "columns": ["order_id", "user_id", "paid_at", "revenue"],
            "key_fields": ["order_id", "user_id"],
            "time_fields": ["paid_at"],
        },
        {
            "file_id": "coupon",
            "filename": "优惠券核销.xlsx",
            "dataset": "优惠券核销",
            "columns": ["主用户ID", "产品用户ID", "优惠券ID", "核销时间"],
            "key_fields": [],
            "time_fields": ["核销时间"],
        },
    ]
    state.set_active_bundle({
        "bundle_id": "bundle_orders",
        "file_ids": ["orders"],
        "dataset_names": ["省钱卡订单"],
    })
    state.file_relationships = [{
        "relationship_id": "rel_orders_coupon",
        "file_ids": ["orders", "coupon"],
        "status": "possibly_linked",
        "requires_confirmation": True,
        "evidence": ["User alias fields may connect coupon usage to orders."],
    }]

    plan = build_analysis_scope_plan(state, user_goal="评估省钱卡是否值得继续运营")

    assert [item["file_id"] for item in plan["included_files"]] == ["orders", "coupon"]
    assert plan["decision_files"] == []
    assert plan["pending_files"] == []
    assert plan["scope_status"] == "ready_with_notes"
    assert any(
        "coupon" in note
        and "join" in note.lower()
        and "rel_orders_coupon" in note
        for note in plan["notes"]
    )
    assert "coupon" not in {item["file_id"] for item in plan["excluded_files"]}


def test_method_confirmation_surfaces_an_answerable_question_across_trust_view():
    state = AnalysisSessionState(session_id="6ed6b0a043fb_regression", data_state="data_loaded")
    state.active_scope["active_mode"] = "data_loaded"
    state.pending_confirmations = [
        {
            "id": "confirm_roi_method",
            "status": "pending",
            "confirmation_type": "method_confirmation",
            "question": "是否按未来 90 天收入与优惠成本评估省钱卡 ROI？",
            "blocking_reason": "需要先确认评估周期和 ROI 口径。",
        }
    ]

    view = build_trust_view(state)

    gate = view["recommendations"]["confirmation_gate"]
    confirmations = view["workbench"]["confirmations"]
    assert gate["status"] == "needs_confirmation"
    assert gate["confirmation_type"] == "method_confirmation"
    assert gate["question"] == "是否按未来 90 天收入与优惠成本评估省钱卡 ROI？"
    assert gate["blocking_reason"] == "需要先确认评估周期和 ROI 口径。"
    assert confirmations == {
        "status": "needs_confirmation",
        "question": gate["question"],
        "blocking_reason": gate["blocking_reason"],
    }
    assert confirmations["question"].strip()


def test_unsupported_retention_route_is_exploratory_when_identity_fields_are_missing():
    state = AnalysisSessionState(session_id="retention_route_regression", data_state="data_loaded")
    state.active_scope.update({"active_dataset": "orders", "active_mode": "data_loaded"})
    state.dataset_contracts = [
        {
            "dataset": "orders",
            "field_roles": {"date": ["order_date"], "metrics": ["revenue"]},
        }
    ]
    state.route_proposals = [
        {
            "id": "route_retention",
            "dataset": "orders",
            "direction": "cohort",
            "label": "Retention",
            "evidence_requirements": ["user_id", "event_date"],
        }
    ]

    capabilities = build_route_capabilities(state)

    assert capabilities["executable"] == []
    assert len(capabilities["exploratory"]) == 1
    assert capabilities["exploratory"][0]["support_status"] == "needs_more_data"
    assert capabilities["exploratory"][0]["missing_requirements"] == [
        "user_id",
        "event_date",
    ]


def test_orphan_relationship_flag_does_not_create_an_actionable_confirmation_gate():
    state = AnalysisSessionState(session_id="orphan_relationship_regression", data_state="data_loaded")
    state.active_scope["active_mode"] = "data_loaded"
    state.file_relationships = [
        {
            "relationship_id": "rel_orders_coupon",
            "status": "possibly_linked",
            "requires_confirmation": True,
            "confirmation_type": "file_relationship_confirmation",
        }
    ]

    view = build_trust_view(state)

    assert view["file_relationships"][0]["requires_confirmation"] is True
    assert view["recommendations"]["confirmation_gate"]["status"] == "clear"
    assert view["workbench"]["confirmations"] == {
        "status": "clear",
        "question": "",
        "blocking_reason": "",
    }
    context = view["workbench"]["current_context"]
    assert context["decision_files"] == []
    assert context["pending_files"] == []
    assert view["workbench"]["relationship_diagnostics"][0]["actionable"] is False
    assert "active confirmation" in view["workbench"]["relationship_diagnostics"][0]["note"]


def test_no_file_consulting_state_keeps_a_valid_unverified_workbench_context():
    state = AnalysisSessionState(session_id="no_file_consulting_regression")

    view = build_trust_view(state)

    assert view["active_scope"]["active_mode"] == "consulting"
    assert view["recommendations"]["active_mode"] == "consulting"
    assert view["recommendations"]["executable"] == []
    assert view["workbench"]["current_context"] == {
        "goal": "",
        "scope_status": "ready",
        "included_files": [],
        "available_files": [],
        "unused_files": [],
        "decision_files": [],
        "unavailable_files": [],
        "excluded_files": [],
        "pending_files": [],
        "notes": [],
        "assumptions": [],
    }
    assert view["workbench"]["trust_evidence"] == {
        "status": "not_run",
        "claim_count": 0,
        "failed_count": 0,
        "downgraded_count": 0,
    }
