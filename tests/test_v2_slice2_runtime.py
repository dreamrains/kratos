import json

import numpy as np
import pandas as pd

from data_agent.v2.models import ClaimClass, FindingKind
from data_agent.v2.slice2 import Slice2FactorRuntime
from data_agent.v2.store import V2FactStore


def _factor_frame(rows: int = 48) -> pd.DataFrame:
    index = np.arange(rows, dtype=float)
    marketing = ((index * 7) % 31) + 10
    service = ((index * 11) % 23) + 60
    target = 0.8 * marketing + 0.35 * service + np.sin(index * 1.7) * 3
    return pd.DataFrame(
        {
            "unit_id": [f"u{i:03d}" for i in range(rows)],
            "target": target,
            "marketing": marketing,
            "service": service,
            "noise_feature": np.cos(index * 0.9),
        }
    )


def test_slice2_supported_path_persists_feature_findings_chart_and_calibrated_answer(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    _factor_frame().to_csv(inbox / "factors.csv", index=False)
    runtime = Slice2FactorRuntime(tmp_path / "sessions", inbox)

    events = list(
        runtime.stream(
            session_id="session_factor",
            turn_id="turn_factor",
            filename="factors.csv",
            target="target",
            features=("marketing", "service", "noise_feature"),
            analysis_unit="unit_id",
            time_field="",
            question="哪些因素与 target 存在可靠关系？",
        )
    )
    store = V2FactStore(tmp_path / "sessions", "session_factor")
    findings = store.read_findings()
    turn = store.read_turn_blocks("turn_factor")

    positive = [item for item in findings if item.finding_kind is FindingKind.ASSOCIATION]
    assert {item.feature_identity for item in positive} >= {
        "column:marketing",
        "column:service",
    }
    assert all(item.maximum_claim_class is ClaimClass.INFERENTIAL for item in positive)
    assert "artifact_created" in [item.event for item in events]
    journal_events = [item.event_type.value for item in store.read_events()]
    assert "artifact_created" in journal_events
    event_names = [item.event for item in events]
    assert event_names.index("artifact_created") < event_names.index("outcome_snapshot")
    assert events[-1].event == "turn_completed"
    assert turn["status"] == "finalized"
    assert turn["request_context"]["target"] == "target"
    assert turn["request_context"]["features"] == "marketing,service,noise_feature"
    assert turn["blocks"][0]["chart_refs"] == [turn["artifacts"][0]["chart_id"]]
    serialized = json.dumps(turn, ensure_ascii=False)
    assert "调整后统计关联" in serialized
    assert "Holm" in serialized
    assert "p<0.001" in serialized
    assert "因果影响" in serialized
    assert "[[evidence:" not in serialized


def test_slice2_no_reliable_factor_publishes_null_result(tmp_path):
    rows = 40
    frame = pd.DataFrame(
        {
            "unit_id": [f"u{i}" for i in range(rows)],
            "target": np.tile([1.0, -1.0], rows // 2),
            "factor_a": np.repeat([0.0, 1.0], rows // 2),
        }
    )
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    frame.to_csv(inbox / "null.csv", index=False)

    events = list(
        Slice2FactorRuntime(tmp_path / "sessions", inbox).stream(
            session_id="session_null_factor",
            turn_id="turn_null_factor",
            filename="null.csv",
            target="target",
            features=("factor_a",),
            analysis_unit="unit_id",
            time_field="",
            question="factor_a 是否与 target 有可靠关系？",
        )
    )
    store = V2FactStore(tmp_path / "sessions", "session_null_factor")
    findings = store.read_findings()
    turn = store.read_turn_blocks("turn_null_factor")

    assert any(item.finding_kind is FindingKind.NULL_RESULT for item in findings)
    assert events[-1].event == "turn_completed"
    assert turn["artifacts"] == []
    assert "未发现" in turn["blocks"][0]["narrative"]


def test_slice2_repeated_units_without_time_publish_limited_answer(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    pd.DataFrame(
        {
            "unit_id": ["a", "a", "b", "b", "c", "c"],
            "target": [1, 2, 2, 3, 3, 4],
            "factor": [2, 3, 3, 4, 4, 5],
        }
    ).to_csv(inbox / "repeated.csv", index=False)

    events = list(
        Slice2FactorRuntime(tmp_path / "sessions", inbox).stream(
            session_id="session_limited_factor",
            turn_id="turn_limited_factor",
            filename="repeated.csv",
            target="target",
            features=("factor",),
            analysis_unit="unit_id",
            time_field="",
            question="哪些因素与 target 有关系？",
        )
    )
    store = V2FactStore(tmp_path / "sessions", "session_limited_factor")
    findings = store.read_findings()
    turn = store.read_turn_blocks("turn_limited_factor")

    assert any(item.finding_kind is FindingKind.LIMITATION for item in findings)
    assert events[-1].event == "turn_completed"
    assert "重复观测" in turn["blocks"][0]["narrative"]
