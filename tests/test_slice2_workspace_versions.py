"""Slice 2: raw datasets and derived analysis datasets have distinct identities."""

from __future__ import annotations

import pandas as pd

from data_agent.session.workspace import Workspace
from data_agent.agent.context import AgentContext, use_agent_context
from data_agent.tools.data_clean import apply_type_conversion, auto_clean, clean_data
from data_agent.tools.data_io import load_data
from data_agent.tools.eda import top_n
from data_agent.tools.statistics import ab_test
from data_agent.tools.chart_contract import validate_chart_request


def test_raw_identity_survives_a_copy_on_write_derived_dataset():
    workspace = Workspace()
    raw = pd.DataFrame({"revenue": ["12.5", "-", "8"], "campaign": ["a", "b", "a"]})

    workspace.add("cross_promotion", raw)
    raw_identity = workspace.get_data_identity("cross_promotion")
    parsed = raw.assign(revenue=pd.to_numeric(raw["revenue"], errors="coerce"))
    workspace.derive(
        "cross_promotion",
        "cross_promotion__analysis",
        parsed,
        expression="revenue: object -> numeric; '-' -> missing",
    )

    analysis_identity = workspace.get_data_identity("cross_promotion__analysis")

    assert raw_identity["role"] == "raw"
    assert raw_identity["fingerprint"].startswith("sha256:")
    assert workspace.get("cross_promotion").equals(raw)
    assert workspace.get("cross_promotion__analysis")["revenue"].isna().sum() == 1
    assert analysis_identity["role"] == "analysis"
    assert analysis_identity["parent_version_ids"] == [raw_identity["version_id"]]
    assert analysis_identity["source_fingerprint"] == raw_identity["fingerprint"]
    assert analysis_identity["fingerprint"] != raw_identity["fingerprint"]


def test_list_datasets_exposes_version_identity_without_leaking_values():
    workspace = Workspace()
    workspace.add("orders", pd.DataFrame({"user_id": [101, 102], "amount": [10, 20]}))

    listed = workspace.list_datasets()["orders"]

    assert listed["data_identity"]["role"] == "raw"
    assert listed["data_identity"]["version_id"]
    assert "101" not in str(listed["data_identity"])


def test_safe_type_conversion_creates_an_analysis_version_without_replacing_raw():
    workspace = Workspace()
    context = AgentContext(session_id="slice2-cow", workspace=workspace)
    raw = pd.DataFrame({"revenue": ["12.5", "-", "8"]})

    with use_agent_context(context):
        workspace.add("cross_promotion", raw)
        result = apply_type_conversion("cross_promotion", column="revenue", target_type="numeric")

    payload = __import__("json").loads(result)
    assert "dataset" in payload, payload
    analysis_name = payload["dataset"]
    assert payload["source_dataset"] == "cross_promotion"
    assert workspace.get("cross_promotion").equals(raw)
    assert workspace.get(analysis_name)["revenue"].isna().sum() == 1
    assert workspace.get_data_identity(analysis_name)["role"] == "analysis"


def test_d04_before_after_orders_use_the_paired_user_level_path():
    data_path = __import__("pathlib").Path("reference/test_doc/省钱卡购卡前后订单.xlsx")
    workspace = Workspace()
    context = AgentContext(session_id="slice2-r02", workspace=workspace)
    group_col = "用户类型（1是购卡前30天内，2是购卡后30天内）"

    with use_agent_context(context):
        workspace.add("d04_orders", pd.read_excel(data_path))
        result = __import__("json").loads(ab_test("d04_orders", group_col, "实收金额"))

    assert result["design"] == "paired"
    assert result["analysis_unit"] == "user_id"
    assert result["unit_aggregation"] == "sum"
    assert result["paired_sample_size"] == 61
    assert result["excluded_unpaired_units"] == 1
    assert result["difference"]["absolute"] == -1220.1311
    assert result["test"]["p_value"] == 0.0186
    assert result["wilcoxon_signed_rank"]["p_value"] == 0.027699


def test_d04_exact_duplicates_are_retained_until_deduplication_is_explicit():
    data_path = __import__("pathlib").Path("reference/test_doc/省钱卡购卡前后订单.xlsx")
    workspace = Workspace()
    context = AgentContext(session_id="slice2-r02-dedup", workspace=workspace)
    raw = pd.read_excel(data_path)

    with use_agent_context(context):
        workspace.add("d04_orders", raw)
        retained = __import__("json").loads(clean_data("d04_orders"))
        deduplicated = __import__("json").loads(clean_data("d04_orders", deduplicate=True))

    assert raw.duplicated().sum() == 468
    assert retained["final_rows"] == 7206
    assert not any(action["action"] == "deduplicate" for action in retained["actions"])
    assert deduplicated["final_rows"] == 6738
    assert any(action["action"] == "deduplicate" and action["removed"] == 468 for action in deduplicated["actions"])


def test_d05_mixed_revenue_is_parsed_in_a_derived_analysis_version_with_failures_visible():
    data_path = __import__("pathlib").Path("reference/test_doc/游戏互推.xlsx")
    raw = pd.read_excel(data_path)
    cleaned, applied, _ = auto_clean(raw)
    revenue_conversion = next(item for item in applied if item["column"] == "卖量收入")

    assert raw["卖量收入"].eq("-").sum() == 59
    assert cleaned["卖量收入"].notna().sum() == 1926
    assert cleaned["卖量收入"].isna().sum() == 59
    assert revenue_conversion["conversion_failures"] == 59
    assert revenue_conversion["conversion_failure_rate"] == 0.029723


def test_load_data_keeps_d05_upload_as_raw_and_uses_named_analysis_dataset():
    from data_agent.session.workspace import workspace

    raw_name = "slice2_d05_upload"
    raw_snapshot_name = f"{raw_name}__raw"
    analysis_name = raw_name
    workspace.remove(raw_name)
    workspace.remove(raw_snapshot_name)
    try:
        data_path = __import__("pathlib").Path("reference/test_doc/游戏互推.xlsx").resolve()
        output = load_data(str(data_path), name=raw_name)
        assert analysis_name in output
        assert raw_snapshot_name in output
        assert workspace.get(raw_snapshot_name)["卖量收入"].eq("-").sum() == 59
        assert workspace.get(analysis_name)["卖量收入"].isna().sum() == 59
        raw_identity = workspace.get_data_identity(raw_snapshot_name)
        analysis_identity = workspace.get_data_identity(analysis_name)
        assert raw_identity["role"] == "raw"
        assert analysis_identity["role"] == "analysis"
        assert analysis_identity["parent_version_ids"] == [raw_identity["version_id"]]
    finally:
        workspace.remove(analysis_name)
        workspace.remove(raw_snapshot_name)


def test_top_n_can_create_a_copy_on_write_dataset_for_a_following_chart():
    workspace = Workspace()
    context = AgentContext(session_id="slice2-top-n", workspace=workspace)
    raw = pd.DataFrame({"game": ["a", "b", "c"], "revenue": [10, 30, 20]})

    with use_agent_context(context):
        workspace.add("cross", raw)
        result = __import__("json").loads(top_n("cross", sort_by="revenue", n=2, save_as="cross_top2"))

    assert result["dataset"] == "cross_top2"
    assert result["source_dataset"] == "cross"
    assert workspace.get("cross").equals(raw)
    assert workspace.get("cross_top2")["revenue"].tolist() == [30, 20]
    assert workspace.get_data_identity("cross_top2")["parent_version_ids"] == [
        workspace.get_data_identity("cross")["version_id"]
    ]


def test_low_cardinality_numeric_group_is_explicitly_safe_for_a_bar_chart_axis():
    contract = validate_chart_request(
        pd.DataFrame({"window_code": [1, 1, 2, 2], "revenue": [10, 20, 15, 25]}),
        chart_type="bar",
        x_col="window_code",
        y_cols=["revenue"],
        aggregation="sum",
    )

    assert contract.valid
    assert contract.semantic_roles["window_code"] == "category"
    assert contract.dataframe["window_code"].tolist() == ["1", "1", "2", "2"]
    assert "low_cardinality_numeric_to_category" in contract.transformations
