import json

import pandas as pd

from data_agent.v2.models import FindingKind
from data_agent.v2.slice1 import Slice1DescriptiveRuntime
from data_agent.v2.store import V2FactStore


def test_slice1_stream_is_fact_driven_persisted_and_refreshable(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    pd.DataFrame({"date": ["2026-01-01", "2026-01-02"], "sales": [100, 200]}).to_csv(
        inbox / "sales.csv", index=False
    )
    runtime = Slice1DescriptiveRuntime(tmp_path / "sessions", inbox)

    events = list(
        runtime.stream(
            session_id="session_1",
            turn_id="turn_1",
            filename="sales.csv",
            metric="sales",
            question="平均销售额是多少？",
        )
    )

    event_names = [item.event for item in events]
    assert event_names == [
        "turn_started",
        "commitment_snapshot",
        "tool_started",
        "tool_finished",
        "outcome_snapshot",
        "final_block_delta",
        "final_block_delta",
        "final_block_delta",
        "turn_completed",
    ]
    assert event_names.index("tool_started") < event_names.index("final_block_delta")
    assert events[-1].data["status"] == "completed"

    store = V2FactStore(tmp_path / "sessions", "session_1")
    findings = store.read_findings()
    persisted = store.read_turn_blocks("turn_1")

    assert findings[0].estimate == 150.0
    assert findings[0].effective_sample == 2
    assert persisted["status"] == "finalized"
    assert persisted["blocks"][0]["block_type"] == "executive_answer"
    assert "平均值为 150" in persisted["blocks"][0]["narrative"]
    assert "[[evidence:" not in json.dumps(persisted, ensure_ascii=False)


def test_slice1_rejects_path_traversal(tmp_path):
    runtime = Slice1DescriptiveRuntime(tmp_path / "sessions", tmp_path / "inbox")

    try:
        list(
            runtime.stream(
                session_id="session_1",
                turn_id="turn_1",
                filename="../secret.csv",
                metric="sales",
                question="平均销售额是多少？",
            )
        )
    except ValueError as exc:
        assert "filename" in str(exc)
    else:
        raise AssertionError("path traversal must be rejected")


def test_slice1_publishes_null_result_when_metric_has_no_numeric_observations(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    pd.DataFrame({"sales": [None, "not-a-number"]}).to_csv(
        inbox / "empty_sales.csv", index=False
    )
    runtime = Slice1DescriptiveRuntime(tmp_path / "sessions", inbox)

    events = list(
        runtime.stream(
            session_id="session_null",
            turn_id="turn_null",
            filename="empty_sales.csv",
            metric="sales",
            question="平均销售额是多少？",
        )
    )

    store = V2FactStore(tmp_path / "sessions", "session_null")
    finding = store.read_findings()[0]
    persisted = store.read_turn_blocks("turn_null")
    outcome = next(item for item in events if item.event == "outcome_snapshot")

    assert finding.finding_kind is FindingKind.NULL_RESULT
    assert finding.estimate is None
    assert outcome.data["publishable"] is True
    assert "没有可用于计算平均值的数值观测" in persisted["blocks"][0]["narrative"]
    assert events[-1].event == "turn_completed"
