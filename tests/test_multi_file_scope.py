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

    plan = build_analysis_scope_plan(state, user_goal="评估省钱卡是否值得继续运营")

    assert [item["file_id"] for item in plan["included_files"]] == ["orders", "coupon"]
    assert [item["file_id"] for item in plan["excluded_files"]] == ["game"]
    assert plan["scope_status"] == "needs_confirmation"
    assert any("主用户ID" in assumption for assumption in plan["assumptions"])


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
