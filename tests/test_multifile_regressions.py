from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.multi_file_scope import build_analysis_scope_plan
from data_agent.agent.route_capabilities import build_route_capabilities
from data_agent.agent.trust_view import build_trust_view


def test_scope_plan_keeps_relationship_evidence_out_of_file_assignment():
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
    state.dataset_contracts = [
        {"id": "duc_orders", "dataset": "省钱卡订单", "quality_status": "ready"},
        {"id": "duc_coupon", "dataset": "优惠券核销", "quality_status": "ready"},
    ]

    plan = build_analysis_scope_plan(state, user_goal="评估省钱卡是否值得继续运营")

    assert [item["file_id"] for item in plan["eligible_files"]] == ["orders", "coupon"]
    assert [item["file_id"] for item in plan["available_files"]] == ["orders", "coupon"]
    assert plan["used_files"] == []
    assert plan["decision_files"] == []
    assert plan["scope_status"] == "ready_with_notes"
    assert all("relationship" not in item for item in plan["file_decisions"])


def test_method_confirmation_remains_in_internal_state_not_workbench_projection():
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

    assert state.pending_confirmations[0]["question"].strip()
    assert build_trust_view(state)["workbench"] == {"verified_conclusions": []}


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

    assert state.file_relationships[0]["relationship_id"] == "rel_orders_coupon"
    assert build_trust_view(state)["workbench"] == {"verified_conclusions": []}


def test_no_file_consulting_state_keeps_a_valid_unverified_workbench_context():
    state = AnalysisSessionState(session_id="no_file_consulting_regression")

    view = build_trust_view(state)

    assert view["status"] == "empty"
    assert view["workbench"] == {"verified_conclusions": []}
