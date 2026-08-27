from __future__ import annotations

from pathlib import Path

import pandas as pd

from data_agent.agent.relationship_validation import validate_relationship
from data_agent.session.workspace import workspace
from data_agent.tools.multifile import synthesize_time_series
from data_agent.tools.registry import registry


ROOT = Path("reference/test_doc")


def _load(name: str, filename: str) -> None:
    workspace.remove(name)
    workspace.add(name, pd.read_excel(ROOT / filename, sheet_name="数据"))


def test_r04_aligns_three_real_game_files_with_explicit_coverage_and_lineage():
    _load("r04_rewarded", "游戏A激励视频汇总数据报表.xlsx")
    _load("r04_iap", "游戏A内购数据.xlsx")
    _load("r04_banner", "游戏Abanner汇总数据.xlsx")
    result = synthesize_time_series(
        "r04_rewarded,r04_iap,r04_banner",
        metrics="r04_rewarded:视频广告收入,r04_iap:内购收入,r04_banner:BN_广告收入",
        save_as="r04_aligned_daily",
    )
    assert result.data["status"] == "supported"
    assert result.data["aligned_rows"] == 248
    assert all(item["distinct_dates"] == 248 for item in result.data["coverage"].values())
    identity = result.data["derived_identity"]
    assert len(identity["parent_version_ids"]) == 3
    assert all(value == 0 for value in result.data["missing_aligned_dates"].values())


def test_many_to_many_r05_style_relationship_remains_diagnostic_not_materialized():
    orders = pd.read_excel(ROOT / "省钱卡订单.xlsx")
    flow = pd.read_excel(ROOT / "省钱卡0201到0510购卡用户付费数据.xlsx")
    relationship = validate_relationship(orders, flow, left_key="user_id", right_key="user_id").to_record()
    assert relationship["status"] == "rejected"
    assert relationship["cardinality"] == "many_to_many"
    assert "many_to_many_join_explosion" in relationship["risks"]


def test_multifile_requires_every_explicit_metric_and_dataset():
    _load("r04_only_banner", "游戏Abanner汇总数据.xlsx")
    result = synthesize_time_series("r04_only_banner,missing", metrics="r04_only_banner:BN_广告收入")
    assert "每个数据集必须指定一个 metric" in result.summary


def test_multifile_synthesis_is_registered_for_provider_neutral_routing():
    registry._ensure_discovered()
    assert registry.get("synthesize_time_series") is not None
    assert registry.capability_for("synthesize_time_series")["capability_id"] == "analysis.multi_file_time_synthesis"
