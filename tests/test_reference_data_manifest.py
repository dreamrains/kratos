from __future__ import annotations

from pathlib import Path

import pytest

from scripts.acceptance.real_data_manifest import (
    PROJECT_ROOT,
    REFERENCE_DATA,
    REFERENCE_DATA_AVAILABLE,
    ReferenceDataManifestError,
    load_reference_data_manifest,
    reference_data_path,
    validate_reference_data,
)


CANONICAL_FILENAMES = {
    "省钱卡0201到0510购卡用户付费数据.xlsx",
    "省钱卡代金券明细订单.xlsx",
    "省钱卡订单.xlsx",
    "省钱卡购卡前后订单.xlsx",
    "游戏互推.xlsx",
    "游戏A激励视频汇总数据报表.xlsx",
    "游戏A内购数据.xlsx",
    "游戏Abanner汇总数据.xlsx",
    "游戏B留存.xlsx",
}


def test_reference_data_manifest_is_checkout_relative_and_complete():
    assert REFERENCE_DATA.root == PROJECT_ROOT / "reference" / "test_doc"
    assert set(REFERENCE_DATA.by_filename) == CANONICAL_FILENAMES
    assert len(REFERENCE_DATA.files) == 9
    assert len(REFERENCE_DATA.by_id) == 9
    assert reference_data_path("game_b_retention").name == "游戏B留存.xlsx"
    assert reference_data_path("省钱卡订单.xlsx").name == "省钱卡订单.xlsx"


def test_reference_data_manifest_rejects_absolute_root(tmp_path: Path):
    bad = tmp_path / "bad.json"
    bad.write_text(
        '{"schema_version":"reference_data_manifest.v1","root":"D:/external","files":[]}',
        encoding="utf-8",
    )
    with pytest.raises(ReferenceDataManifestError, match="root must stay within the checkout"):
        load_reference_data_manifest(bad)


@pytest.mark.skipif(not REFERENCE_DATA_AVAILABLE, reason="canonical reference data is not installed")
def test_installed_reference_data_matches_manifest_exactly():
    assert validate_reference_data() == []


def test_real_data_tests_do_not_reintroduce_stale_paths_or_aliases():
    forbidden = {
        "D:/Project/Daily/data-agent/reference/test_doc",
        "D:/Project/Daily/备用/20260512测试",
        "省钱卡订单_20260507.xlsx",
        "省钱卡用户最近流水_20260511.xlsx",
    }
    offenders: list[str] = []
    for path in sorted((PROJECT_ROOT / "tests").rglob("*.py")):
        if path == Path(__file__).resolve():
            continue
        text = path.read_text(encoding="utf-8")
        matched = sorted(value for value in forbidden if value in text)
        if matched:
            offenders.append(f"{path.relative_to(PROJECT_ROOT)}: {matched}")
    assert offenders == []
