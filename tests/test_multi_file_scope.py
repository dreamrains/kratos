from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.multi_file_scope import (
    build_analysis_scope_plan,
    canonical_entity_fields,
    infer_file_grain,
)


def test_canonical_entity_fields_recognize_user_aliases():
    profile = {
        "file_id": "coupon",
        "filename": "代金券明细订单.xlsx",
        "columns": ["主用户ID", "产品用户ID", "优惠券ID", "核销时间"],
        "key_fields": [],
        "time_fields": ["核销时间"],
    }

    fields = canonical_entity_fields(profile)

    assert fields["user"] == ["主用户ID", "产品用户ID"]
    assert fields["coupon"] == ["优惠券ID"]
    assert fields["time"] == ["核销时间"]


def test_infer_file_grain_prefers_order_level_when_order_id_exists():
    profile = {
        "file_id": "orders",
        "columns": ["order_id", "user_id", "paid_at", "amount"],
        "key_fields": ["order_id", "user_id"],
        "time_fields": ["paid_at"],
    }

    assert infer_file_grain(profile)["grain"] == "order_level"


def test_infer_file_grain_prefers_user_level_before_retention_filename_hint():
    profile = {
        "file_id": "retention_detail",
        "filename": "留存明细.csv",
        "columns": ["用户ID", "日期", "是否留存"],
        "key_fields": ["用户ID"],
        "time_fields": ["日期"],
    }

    assert infer_file_grain(profile)["grain"] == "user_level"


def test_scope_plan_includes_relevant_user_files_and_excludes_unrelated_game_file():
    state = AnalysisSessionState(session_id="scope_plan", data_state="data_loaded")
    state.goal = "评估省钱卡是否值得继续运营"
    state.data_pool = [
        {
            "file_id": "orders",
            "filename": "省钱卡订单.xlsx",
            "dataset": "省钱卡订单",
            "columns": ["order_id", "user_id", "支付时间", "实收金额"],
            "key_fields": ["order_id", "user_id"],
            "time_fields": ["支付时间"],
        },
        {
            "file_id": "coupon",
            "filename": "代金券明细订单.xlsx",
            "dataset": "代金券明细订单",
            "columns": ["主用户ID", "产品用户ID", "优惠券ID", "核销时间"],
            "key_fields": [],
            "time_fields": ["核销时间"],
        },
        {
            "file_id": "game",
            "filename": "游戏互推.xlsx",
            "dataset": "游戏互推",
            "columns": ["设备ID", "游戏", "留存"],
            "key_fields": ["设备ID"],
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
        "evidence": ["Coupon user aliases may map to the order user_id."],
    }]

    plan = build_analysis_scope_plan(state, user_goal="评估省钱卡是否值得继续运营")

    assert [item["file_id"] for item in plan["included_files"]] == ["orders"]
    assert [item["file_id"] for item in plan["pending_files"]] == ["coupon"]
    assert [item["file_id"] for item in plan["excluded_files"]] == ["game"]
    assert plan["scope_status"] == "needs_confirmation"
    assert any(
        "candidate" in assumption.lower()
        and "coupon" in assumption
        and "rel_orders_coupon" in assumption
        and "主用户ID" in assumption
        and "产品用户ID" in assumption
        for assumption in plan["assumptions"]
    )


def test_scope_plan_excludes_unrelated_game_file_even_when_active_bundle_includes_it():
    state = AnalysisSessionState(session_id="scope_plan_active_game", data_state="data_loaded")
    state.goal = "评估省钱卡是否值得继续运营"
    state.data_pool = [
        {
            "file_id": "orders",
            "filename": "省钱卡订单.xlsx",
            "dataset": "省钱卡订单",
            "columns": ["order_id", "user_id", "支付时间", "实收金额"],
            "key_fields": ["order_id", "user_id"],
            "time_fields": ["支付时间"],
        },
        {
            "file_id": "game",
            "filename": "游戏互推.xlsx",
            "dataset": "游戏互推",
            "columns": ["设备ID", "游戏", "留存"],
            "key_fields": ["设备ID"],
        },
    ]
    state.set_active_bundle({
        "bundle_id": "bundle_with_game",
        "file_ids": ["orders", "game"],
        "dataset_names": ["省钱卡订单", "游戏互推"],
    })

    plan = build_analysis_scope_plan(state, user_goal="评估省钱卡是否值得继续运营")

    assert [item["file_id"] for item in plan["included_files"]] == ["orders"]
    assert [item["file_id"] for item in plan["excluded_files"]] == ["game"]


def test_scope_plan_marks_pending_ambiguous_files_as_needing_confirmation():
    state = AnalysisSessionState(session_id="scope_plan_pending", data_state="data_loaded")
    state.goal = "评估省钱卡是否值得继续运营"
    state.data_pool = [
        {
            "file_id": "orders",
            "filename": "省钱卡订单.xlsx",
            "dataset": "省钱卡订单",
            "columns": ["order_id", "user_id", "支付时间", "实收金额"],
            "key_fields": ["order_id", "user_id"],
            "time_fields": ["支付时间"],
        },
        {
            "file_id": "ambiguous",
            "filename": "运营备注.xlsx",
            "dataset": "运营备注",
            "columns": ["备注", "标签"],
            "key_fields": [],
        },
    ]
    state.set_active_bundle({
        "bundle_id": "bundle_orders",
        "file_ids": ["orders"],
        "dataset_names": ["省钱卡订单"],
    })

    plan = build_analysis_scope_plan(state, user_goal="评估省钱卡是否值得继续运营")

    assert [item["file_id"] for item in plan["included_files"]] == ["orders"]
    assert [item["file_id"] for item in plan["pending_files"]] == ["ambiguous"]
    assert plan["scope_status"] == "needs_confirmation"


def test_scope_plan_uses_relationship_evidence_before_canonical_ids():
    state = AnalysisSessionState(session_id="scope_relationship_priority", data_state="data_loaded")
    state.data_pool = [
        {
            "file_id": "historical_orders",
            "filename": "archive.xlsx",
            "columns": ["order_id", "user_id"],
        },
        {
            "file_id": "confirmed_profile",
            "filename": "customer_profile.xlsx",
            "columns": ["user_id", "segment"],
        },
        {
            "file_id": "active_orders",
            "filename": "membership_orders.xlsx",
            "columns": ["order_id", "user_id"],
        },
    ]
    state.set_active_bundle({
        "bundle_id": "bundle_active",
        "file_ids": ["active_orders"],
    })
    state.file_relationships = [{
        "relationship_id": "rel_profile",
        "file_ids": ["active_orders", "confirmed_profile"],
        "status": "linked",
        "requires_confirmation": False,
        "evidence": ["Shared strong key fields: user_id"],
    }]

    plan = build_analysis_scope_plan(state, user_goal="evaluate membership revenue")

    assert [item["file_id"] for item in plan["included_files"]] == [
        "active_orders",
        "confirmed_profile",
    ]
    assert [item["file_id"] for item in plan["pending_files"]] == ["historical_orders"]


def test_scope_plan_enforces_deterministic_five_file_detail_budget():
    state = AnalysisSessionState(session_id="scope_budget", data_state="data_loaded")
    state.data_pool = [
        {"file_id": "candidate_1", "filename": "membership_candidate_1.xlsx"},
        {"file_id": "excluded", "filename": "game_retention.xlsx"},
        {"file_id": "linked", "filename": "customer_profile.xlsx", "columns": ["user_id"]},
        {"file_id": "active_2", "filename": "membership_active_2.xlsx"},
        {"file_id": "candidate_2", "filename": "membership_candidate_2.xlsx"},
        {"file_id": "active_1", "filename": "membership_active_1.xlsx"},
        {"file_id": "candidate_3", "filename": "membership_candidate_3.xlsx"},
    ]
    state.set_active_bundle({
        "bundle_id": "bundle_active",
        "file_ids": ["active_1", "active_2"],
    })
    state.file_relationships = [{
        "relationship_id": "rel_linked",
        "file_ids": ["active_1", "linked"],
        "status": "confirmed",
        "requires_confirmation": False,
    }]

    first = build_analysis_scope_plan(state, user_goal="evaluate membership revenue")
    second = build_analysis_scope_plan(state, user_goal="evaluate membership revenue")

    assert first == second
    assert [item["file_id"] for item in first["included_files"]] == [
        "active_2",
        "active_1",
        "linked",
        "candidate_1",
        "candidate_2",
    ]
    assert first["pending_files"] == []
    assert first["excluded_files"] == []
    assert first["context_budget"] == {
        "included_file_count": 5,
        "excluded_file_count": 0,
        "pending_file_count": 0,
        "total_file_count": 7,
        "returned_file_count": 5,
        "omitted_file_count": 2,
        "max_scope_files": 5,
    }
