import json

import pytest

from data_agent.v2.models import (
    AnswerBlockDraft,
    AnswerBlockType,
    ClaimClass,
    Commitment,
    CommitmentPriority,
    EventType,
    ExecutionEvent,
    Finding,
    FindingKind,
    OutcomeStatus,
)
from data_agent.v2.projection import project_run
from data_agent.v2.store import FactConflictError, V2FactStore


def _commitment() -> Commitment:
    return Commitment(
        commitment_id="c1",
        priority=CommitmentPriority.CORE,
        question="平均销售额是多少？",
        dataset_version_ids=("dv1",),
        accepted_result_kinds=(FindingKind.ESTIMATE,),
        accepted_method_capabilities=("analysis.describe",),
    )


def _event(message: str = "") -> ExecutionEvent:
    return ExecutionEvent(
        event_id="ev1",
        run_id="run1",
        commitment_id="c1",
        event_type=EventType.TOOL_SUCCEEDED,
        tool_call_id="tc1",
        tool_name="describe_dataset",
        capability="analysis.describe",
        dataset_version_ids=("dv1",),
        result_ref="artifact:comp1",
        message=message,
    )


def _finding(estimate: float = 120.0) -> Finding:
    return Finding(
        finding_id="f1",
        commitment_id="c1",
        finding_kind=FindingKind.ESTIMATE,
        dataset_version_ids=("dv1",),
        metric_identity="sales.mean",
        method_capability="analysis.describe",
        estimate=estimate,
        unit="CNY",
        maximum_claim_class=ClaimClass.DESCRIPTIVE,
        computation_ref="artifact:comp1",
    )


def test_fact_store_round_trip_recomputes_same_projection(tmp_path):
    store = V2FactStore(tmp_path, "session_1")
    store.write_commitments([_commitment()])
    store.append_event(_event())
    store.append_finding(_finding())

    restored = V2FactStore(tmp_path, "session_1")
    projection = project_run(
        restored.read_commitments(),
        restored.read_events(),
        restored.read_findings(),
    )

    assert projection.publishable is True
    assert projection.outcomes["c1"].status is OutcomeStatus.SUPPORTED
    assert projection.outcomes["c1"].finding_ids == ("f1",)


def test_same_fact_is_idempotent_but_conflicting_content_is_rejected(tmp_path):
    store = V2FactStore(tmp_path, "session_1")

    assert store.append_event(_event()) is True
    assert store.append_event(_event()) is False
    with pytest.raises(FactConflictError, match="ev1"):
        store.append_event(_event(message="different content"))

    assert store.append_finding(_finding()) is True
    assert store.append_finding(_finding()) is False
    with pytest.raises(FactConflictError, match="f1"):
        store.append_finding(_finding(estimate=121.0))


def test_store_uses_record_ids_not_timestamp_filenames(tmp_path):
    store = V2FactStore(tmp_path, "session_1")
    store.append_event(_event())
    store.append_finding(_finding())

    files = sorted(path.name for path in store.root.iterdir())

    assert files == ["execution_events.jsonl", "findings.jsonl"]
    assert json.loads((store.root / "execution_events.jsonl").read_text(encoding="utf-8").strip())["event_id"] == "ev1"
    assert json.loads((store.root / "findings.jsonl").read_text(encoding="utf-8").strip())["finding_id"] == "f1"


def test_answer_turn_is_persisted_as_blocks_before_completion(tmp_path):
    store = V2FactStore(tmp_path, "session_1")
    draft = AnswerBlockDraft(
        block_id="b1",
        block_type=AnswerBlockType.EXECUTIVE_ANSWER,
        support_refs=("f1",),
        headline="直接回答",
        narrative="平均销售额为 120 元。",
        claim_class=ClaimClass.DESCRIPTIVE,
        canonical_values=(120.0,),
    )
    store.write_turn_blocks("turn_1", [draft], status="finalized")

    turn = store.read_turn_blocks("turn_1")

    assert turn["status"] == "finalized"
    assert turn["blocks"][0]["block_id"] == "b1"
    assert turn["blocks"][0]["support_refs"] == ["f1"]


@pytest.mark.parametrize("invalid_id", ["..", "session:1", "session 1", "a/b", "a\\b"])
def test_store_rejects_nonportable_storage_ids(tmp_path, invalid_id):
    with pytest.raises(ValueError, match="session_id"):
        V2FactStore(tmp_path, invalid_id)


def test_store_validates_turn_id_on_read_and_write(tmp_path):
    store = V2FactStore(tmp_path, "session_1")

    with pytest.raises(ValueError, match="turn_id"):
        store.write_turn_blocks("../turn", [], status="finalized")
    with pytest.raises(ValueError, match="turn_id"):
        store.read_turn_blocks("turn:1")
