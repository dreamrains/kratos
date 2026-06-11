from data_agent.agent.data_bundle import (
    classify_file_relationship,
    compact_bundle_summary,
    stable_file_id,
)


def test_related_files_link_on_shared_strong_id_and_theme_time_overlap():
    existing = [
        {
            "file_id": "orders",
            "filename": "coupon_orders_april.xlsx",
            "dataset": "coupon_orders",
            "key_fields": ["user_id"],
            "time_fields": ["paid_at"],
            "time_range": {"start": "2026-04-01", "end": "2026-05-01"},
        }
    ]
    new_files = [
        {
            "file_id": "flow",
            "filename": "coupon_user_flow_april.xlsx",
            "dataset": "coupon_flow",
            "key_fields": ["user_id"],
            "time_fields": ["paid_at"],
            "time_range": {"start": "2026-04-10", "end": "2026-05-10"},
        }
    ]

    result = classify_file_relationship(new_files, existing, user_input="")

    assert result["status"] == "linked"
    assert result["confidence"] in {"medium", "high"}
    assert result["requires_confirmation"] is False
    assert "user_id" in " ".join(result["evidence"])


def test_ambiguous_generic_id_returns_possible_relationship_and_requires_confirmation():
    existing = [{"file_id": "orders", "filename": "orders.xlsx", "key_fields": ["id"]}]
    new_files = [{"file_id": "coupon", "filename": "coupon_details.xlsx", "key_fields": ["id"]}]

    result = classify_file_relationship(new_files, existing, user_input="")

    assert result["status"] == "possibly_linked"
    assert result["requires_confirmation"] is True
    assert result["confirmation_type"] == "file_relationship_confirmation"


def test_independent_files_require_file_exclusion_confirmation():
    existing = [{"file_id": "orders", "filename": "orders.xlsx", "key_fields": ["order_id"]}]
    new_files = [{"file_id": "game", "filename": "game_retention.xlsx", "key_fields": ["device_id"]}]

    result = classify_file_relationship(new_files, existing, user_input="")

    assert result["status"] == "independent"
    assert result["requires_confirmation"] is True
    assert result["confirmation_type"] == "file_exclusion_confirmation"


def test_latest_only_user_request_returns_user_scoped_latest_only():
    existing = [{"file_id": "orders", "filename": "orders.xlsx", "key_fields": ["user_id"]}]
    new_files = [{"file_id": "latest", "filename": "latest.xlsx", "key_fields": ["id"]}]

    result = classify_file_relationship(
        new_files,
        existing,
        user_input="only analyze the latest uploaded file",
    )

    assert result["status"] == "user_scoped_latest_only"
    assert result["requires_confirmation"] is False
    assert result["relationship_mode"] == "user_scoped_latest_only"


def test_latest_file_comparison_does_not_trigger_latest_only_override():
    existing = [{"file_id": "orders", "filename": "orders.xlsx", "key_fields": ["user_id"]}]
    new_files = [{"file_id": "latest", "filename": "latest.xlsx", "key_fields": ["id"]}]

    result = classify_file_relationship(
        new_files,
        existing,
        user_input="compare the latest file with historical orders",
    )

    assert result["status"] != "user_scoped_latest_only"
    assert result["requires_confirmation"] is True


def test_chinese_latest_file_comparison_does_not_trigger_latest_only_override():
    existing = [{"file_id": "orders", "filename": "历史订单.xlsx", "key_fields": ["用户ID"]}]
    new_files = [{"file_id": "latest", "filename": "最新订单.xlsx", "key_fields": ["用户ID"]}]

    result = classify_file_relationship(
        new_files,
        existing,
        user_input="只分析最新文件和历史文件对比",
    )

    assert result["status"] != "user_scoped_latest_only"
    assert result["requires_confirmation"] is True


def test_english_latest_file_comparison_does_not_trigger_latest_only_override():
    existing = [{"file_id": "orders", "filename": "orders.xlsx", "key_fields": ["user_id"]}]
    new_files = [{"file_id": "latest", "filename": "latest.xlsx", "key_fields": ["user_id"]}]

    result = classify_file_relationship(
        new_files,
        existing,
        user_input="only analyze the latest file and compare it with historical orders",
    )

    assert result["status"] != "user_scoped_latest_only"
    assert result["requires_confirmation"] is True


def test_latest_only_with_negative_previous_context_still_scopes_latest_only():
    existing = [{"file_id": "orders", "filename": "orders.xlsx", "key_fields": ["user_id"]}]
    new_files = [{"file_id": "latest", "filename": "latest.xlsx", "key_fields": ["user_id"]}]

    result = classify_file_relationship(
        new_files,
        existing,
        user_input="only use the latest file, not previous exports",
    )

    assert result["status"] == "user_scoped_latest_only"
    assert result["requires_confirmation"] is False


def test_short_latest_only_with_negative_previous_context_still_scopes_latest_only():
    existing = [{"file_id": "orders", "filename": "orders.xlsx", "key_fields": ["user_id"]}]
    new_files = [{"file_id": "latest", "filename": "latest.xlsx", "key_fields": ["user_id"]}]

    result = classify_file_relationship(
        new_files,
        existing,
        user_input="only latest, not previous",
    )

    assert result["status"] == "user_scoped_latest_only"
    assert result["requires_confirmation"] is False


def test_shared_strong_id_and_time_without_theme_requires_confirmation():
    existing = [
        {
            "file_id": "orders",
            "filename": "orders.xlsx",
            "dataset": "orders",
            "key_fields": ["user_id"],
            "time_range": {"start": "2026-04-01", "end": "2026-04-30"},
        }
    ]
    new_files = [
        {
            "file_id": "activity",
            "filename": "activity.xlsx",
            "dataset": "activity",
            "key_fields": ["user_id"],
            "time_range": {"start": "2026-04-10", "end": "2026-04-20"},
        }
    ]

    result = classify_file_relationship(new_files, existing, user_input="")

    assert result["status"] == "possibly_linked"
    assert result["requires_confirmation"] is True


def test_shared_time_tokens_do_not_count_as_business_theme():
    existing = [
        {
            "file_id": "orders",
            "filename": "orders_april_2026.xlsx",
            "dataset": "orders",
            "key_fields": ["user_id"],
            "time_range": {"start": "2026-04-01", "end": "2026-04-30"},
        }
    ]
    new_files = [
        {
            "file_id": "activity",
            "filename": "activity_april_2026.xlsx",
            "dataset": "activity",
            "key_fields": ["user_id"],
            "time_range": {"start": "2026-04-10", "end": "2026-04-20"},
        }
    ]

    result = classify_file_relationship(new_files, existing, user_input="")

    assert result["status"] == "possibly_linked"
    assert result["requires_confirmation"] is True


def test_numeric_month_tokens_do_not_count_as_business_theme():
    existing = [
        {
            "file_id": "orders",
            "filename": "orders_04_2026.xlsx",
            "dataset": "orders",
            "key_fields": ["user_id"],
        }
    ]
    new_files = [
        {
            "file_id": "activity",
            "filename": "activity_04_2026.xlsx",
            "dataset": "activity",
            "key_fields": ["user_id"],
        }
    ]

    result = classify_file_relationship(new_files, existing, user_input="")

    assert result["status"] == "possibly_linked"
    assert result["requires_confirmation"] is True


def test_chinese_month_tokens_do_not_count_as_business_theme():
    existing = [
        {"file_id": "orders", "filename": "订单_4月.xlsx", "dataset": "订单", "key_fields": ["用户ID"]}
    ]
    new_files = [
        {"file_id": "activity", "filename": "活动_4月.xlsx", "dataset": "活动", "key_fields": ["用户ID"]}
    ]

    result = classify_file_relationship(new_files, existing, user_input="")

    assert result["status"] == "possibly_linked"
    assert result["requires_confirmation"] is True


def test_chinese_named_month_tokens_do_not_count_as_business_theme():
    existing = [
        {"file_id": "orders", "filename": "orders_四月_2026.xlsx", "dataset": "orders", "key_fields": ["user_id"]}
    ]
    new_files = [
        {"file_id": "activity", "filename": "activity_四月_2026.xlsx", "dataset": "activity", "key_fields": ["user_id"]}
    ]

    result = classify_file_relationship(new_files, existing, user_input="")

    assert result["status"] == "possibly_linked"
    assert result["requires_confirmation"] is True


def test_directory_names_do_not_count_as_business_theme():
    existing = [
        {
            "file_id": "orders",
            "filename": r"D:\tmp\exports\orders.xlsx",
            "dataset": "orders",
            "key_fields": ["user_id"],
        }
    ]
    new_files = [
        {
            "file_id": "activity",
            "filename": r"D:\tmp\exports\activity.xlsx",
            "dataset": "activity",
            "key_fields": ["user_id"],
        }
    ]

    result = classify_file_relationship(new_files, existing, user_input="")

    assert result["status"] == "possibly_linked"
    assert result["requires_confirmation"] is True


def test_dataset_paths_do_not_count_as_business_theme():
    existing = [
        {
            "file_id": "orders",
            "filename": "orders.xlsx",
            "dataset": r"D:\tmp\exports\orders",
            "key_fields": ["user_id"],
        }
    ]
    new_files = [
        {
            "file_id": "activity",
            "filename": "activity.xlsx",
            "dataset": r"D:\tmp\exports\activity",
            "key_fields": ["user_id"],
        }
    ]

    result = classify_file_relationship(new_files, existing, user_input="")

    assert result["status"] == "possibly_linked"
    assert result["requires_confirmation"] is True


def test_chinese_business_fields_and_theme_can_link_files():
    existing = [
        {
            "file_id": "orders",
            "filename": "省钱卡订单.xlsx",
            "dataset": "省钱卡订单",
            "key_fields": ["用户ID"],
            "time_range": {"start": "2026-04-01", "end": "2026-04-30"},
        }
    ]
    new_files = [
        {
            "file_id": "flow",
            "filename": "省钱卡用户流水.xlsx",
            "dataset": "用户流水",
            "key_fields": ["用户_id"],
            "time_range": {"start": "2026-04-10", "end": "2026-05-10"},
        }
    ]

    result = classify_file_relationship(new_files, existing, user_input="")

    assert result["status"] == "linked"
    assert any("user_id" in item for item in result["evidence"])


def test_stable_file_id_uses_basename_not_absolute_path():
    assert stable_file_id(r"D:\tmp\orders.xlsx", "orders") == stable_file_id("orders.xlsx", "orders")


def test_compact_bundle_summary_includes_active_bundle_file_summary():
    bundle = {
        "bundle_id": "bundle_latest",
        "label": "latest upload only",
        "file_ids": ["latest"],
        "dataset_names": ["latest_dataset"],
        "relationship_status": "user_scoped",
        "version": 1,
    }

    summary = compact_bundle_summary(
        bundle,
        data_pool=[
            {
                "file_id": "latest",
                "filename": "latest.xlsx",
                "row_count": 20,
                "column_count": 5,
            }
        ],
    )

    assert "bundle_latest" in summary
    assert "latest.xlsx" in summary
    assert "20 rows x 5 cols" in summary


def test_stable_file_id_is_deterministic_and_dataset_sensitive():
    same = stable_file_id("orders.xlsx", "orders")

    assert same == stable_file_id("orders.xlsx", "orders")
    assert same != stable_file_id("orders.xlsx", "flow")
    assert same.startswith("file_")


def test_loaded_dataset_registers_data_pool_and_active_bundle(tmp_path):
    import pandas as pd

    from data_agent import config
    from data_agent.agent.analysis_state import AnalysisSessionState
    from data_agent.agent.context import AgentContext, use_agent_context
    from data_agent.config import AgentConfig
    from data_agent.session.workspace import Workspace
    from data_agent.tools.data_io import load_data

    old_cfg = config._config
    config._config = AgentConfig(
        PROJECT_DIR=tmp_path / "project",
        SESSIONS_DIR=tmp_path / "sessions",
    )
    try:
        csv_path = tmp_path / "orders.csv"
        pd.DataFrame(
            {
                "user_id": [1, 2],
                "paid_at": ["2026-04-01", "2026-04-02"],
                "amount": [12, 45],
            }
        ).to_csv(csv_path, index=False)

        state = AnalysisSessionState(session_id="load_bundle")
        ctx = AgentContext(
            session_id="load_bundle",
            workspace=Workspace(),
            analysis_state=state,
        )

        with use_agent_context(ctx):
            result = load_data(str(csv_path), name="orders")

        assert "Error" not in result
        assert state.data_pool
        assert state.active_bundle_id
        assert state.active_bundle()["dataset_names"] == ["orders"]
    finally:
        config._config = old_cfg
