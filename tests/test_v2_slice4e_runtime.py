from __future__ import annotations

import json

import pandas as pd

from data_agent.v2.models import CalibrationAction
from data_agent.v2.slice4e import Slice4EExploratoryRuntime
from data_agent.v2.store import V2FactStore


def _runtime(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    pd.DataFrame({"sales": [10, 20, 30, 40]}).to_csv(inbox / "sales.csv", index=False)
    return Slice4EExploratoryRuntime(tmp_path / "sessions", inbox)


def test_slice4e_publishes_core_finding_and_exploratory_artifact_without_promotion(tmp_path):
    runtime = _runtime(tmp_path)
    events = list(
        runtime.stream(
            session_id="session_py",
            turn_id="turn_py",
            filename="sales.csv",
            metric="sales",
            question="销售额的总体水平如何？",
            purpose="检查中位数作为补充",
            code='result = data["sales"].median()',
        )
    )

    store = V2FactStore(tmp_path / "sessions", "session_py")
    findings = store.read_findings()
    turn = store.read_turn_blocks("turn_py")

    assert len(findings) == 1
    assert findings[0].method_capability == "analysis.describe"
    assert all(item.method_capability != "exploration.python" for item in findings)
    assert len(turn["supplemental_artifacts"]) == 1
    assert turn["supplemental_artifacts"][0]["status"] == "succeeded"
    assert turn["blocks"][-1]["calibration"] == CalibrationAction.EXPLORATORY.value
    assert turn["blocks"][-1]["claim_class"] is None
    assert turn["blocks"][-1]["canonical_values"] == []
    assert [item.event for item in events][-1] == "turn_completed"


def test_slice4e_exploration_failure_does_not_remove_publishable_core_answer(tmp_path):
    runtime = _runtime(tmp_path)
    list(
        runtime.stream(
            session_id="session_py_fail",
            turn_id="turn_py_fail",
            filename="sales.csv",
            metric="sales",
            question="销售额的总体水平如何？",
            purpose="尝试读取文件",
            code='result = open("secret.txt").read()',
        )
    )

    store = V2FactStore(tmp_path / "sessions", "session_py_fail")
    turn = store.read_turn_blocks("turn_py_fail")
    assert len(store.read_findings()) == 1
    assert turn["status"] == "finalized"
    assert turn["supplemental_artifacts"][0]["status"] == "rejected"
    assert "未作为结论证据" in turn["blocks"][-1]["narrative"]


def test_exploratory_artifact_is_immutable(tmp_path):
    runtime = _runtime(tmp_path)
    list(
        runtime.stream(
            session_id="session_py_immutable",
            turn_id="turn_py_immutable",
            filename="sales.csv",
            metric="sales",
            question="总体水平？",
            purpose="补充",
            code='result = data["sales"].median()',
        )
    )
    store = V2FactStore(tmp_path / "sessions", "session_py_immutable")
    turn = store.read_turn_blocks("turn_py_immutable")
    artifact = turn["supplemental_artifacts"][0]
    artifact_path = store.root / "supplemental" / f"{artifact['artifact_id']}.json"
    persisted = json.loads(artifact_path.read_text(encoding="utf-8"))
    persisted["result"] = "999"
    artifact_path.write_text(json.dumps(persisted), encoding="utf-8")

    # The persisted identity is content-bound, so tampering is detected on read.
    try:
        store.read_exploratory_artifact(artifact["artifact_id"])
    except ValueError as exc:
        assert "fingerprint" in str(exc)
    else:
        raise AssertionError("tampered exploratory artifact was accepted")
