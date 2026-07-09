from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pandas as pd

from data_agent.agent.analysis_quality_rubric import score_analysis_quality
from data_agent.agent.relationship_validation import validate_relationship


MANIFEST_PATH = Path(__file__).with_name("scenario_manifest.json")
SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "run_multifile_quality_scenarios.py"


def _data_dir() -> Path:
    worktree_root = Path(__file__).resolve().parents[2]
    candidates = (
        worktree_root / "reference" / "test_doc",
        worktree_root.parents[1] / "reference" / "test_doc",
    )
    return next(path for path in candidates if path.is_dir())


def _manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_manifest_declares_safe_multifile_modes_and_existing_files() -> None:
    manifest = _manifest()
    required_names = {
        "游戏Abanner汇总数据.xlsx",
        "游戏A内购数据.xlsx",
        "游戏A激励视频汇总数据报表.xlsx",
        "游戏B留存.xlsx",
        "省钱卡订单.xlsx",
        "省钱卡0201到0510购卡用户付费数据.xlsx",
    }
    declared_names = {
        name
        for scenario in manifest["scenarios"]
        for name in scenario.get("required_files", [])
    }

    assert manifest["forbidden_modes"] == ["joint", "aggregate_then_join"]
    assert required_names <= declared_names
    assert all(not scenario["executed_join"] for scenario in manifest["scenarios"])
    assert all((_data_dir() / name).is_file() for name in required_names)


def test_real_savings_card_relationship_is_diagnostic_not_join_authority() -> None:
    data_dir = _data_dir()
    orders = pd.read_excel(data_dir / "省钱卡订单.xlsx")
    flow = pd.read_excel(data_dir / "省钱卡0201到0510购卡用户付费数据.xlsx")

    relationship = validate_relationship(
        orders,
        flow,
        left_key="user_id",
        right_key="user_id",
        left_dataset="savings_card_orders",
        right_dataset="recent_user_flow",
    ).to_record()

    assert relationship["cardinality"] == "many_to_many"
    assert relationship["status"] == "rejected"
    assert relationship["left_row_coverage"] > 0.9
    assert relationship["right_row_coverage"] > 0.9
    assert relationship["row_multiplier"] > 1
    assert "many_to_many_join_explosion" in relationship["risks"]

    order_times = pd.to_datetime(orders["支付时间"], errors="coerce")
    flow_times = pd.to_datetime(flow["支付时间"], errors="coerce")
    assert order_times.notna().all() and flow_times.notna().all()
    assert flow_times.min() < order_times.min()
    assert flow_times.max() > order_times.max()
    assert orders.groupby("user_id").size().max() > 1
    assert flow.groupby("user_id").size().max() > 1

    diagnostic = score_analysis_quality(
        relationship_uses=[
            {
                "relationship_id": relationship["id"],
                "validation_status": relationship["status"],
                "used_for_claim": False,
            }
        ]
    )
    assert diagnostic["global_publish_gate"] is True


def test_fault_injection_rejects_missing_key_and_many_to_many_claim_use() -> None:
    left = pd.DataFrame({"user_id": [1, 1, None], "period": ["A", "A", "B"]})
    right = pd.DataFrame({"user_id": [1, 1, 2], "period": ["B", "B", "B"]})

    missing_key = validate_relationship(
        left,
        right,
        left_key="missing_key",
        right_key="user_id",
    ).to_record()
    many_to_many = validate_relationship(
        left,
        right,
        left_key="user_id",
        right_key="user_id",
    ).to_record()

    assert missing_key["status"] == "rejected"
    assert "missing_left_key" in missing_key["risks"]
    assert many_to_many["status"] == "rejected"
    assert many_to_many["cardinality"] == "many_to_many"

    result = score_analysis_quality(
        relationship_uses=[
            {
                "relationship_id": many_to_many["id"],
                "validation_status": many_to_many["status"],
                "used_for_claim": True,
                "time_scope_compatible": False,
            }
        ]
    )
    assert result["claim_delivery_ready"] is False
    assert result["global_publish_gate"] is False


def test_scenario_runner_writes_report_without_modifying_source_files(tmp_path: Path) -> None:
    data_dir = _data_dir()
    before = {
        path.name: (path.stat().st_size, path.stat().st_mtime_ns)
        for path in data_dir.glob("*.xlsx")
    }

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--data-dir",
            str(data_dir),
            "--output-root",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result_path = Path(completed.stdout.strip())
    result = json.loads(result_path.read_text(encoding="utf-8"))
    after = {
        path.name: (path.stat().st_size, path.stat().st_mtime_ns)
        for path in data_dir.glob("*.xlsx")
    }

    assert result_path.is_file()
    assert result["schema_version"] == "multifile_quality_results.v1"
    assert result["global_publish_gate"] is None
    assert all(item["status"] == "ready_for_execution" for item in result["scenarios"])
    assert before == after


def test_scenario_runner_rejects_malformed_manifest(tmp_path: Path) -> None:
    malformed = tmp_path / "bad.json"
    malformed.write_text('{"scenarios": "not-a-list"}', encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--manifest",
            str(malformed),
            "--data-dir",
            str(_data_dir()),
            "--output-root",
            str(tmp_path / "output"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode != 0
    assert "malformed manifest" in completed.stderr.lower()
