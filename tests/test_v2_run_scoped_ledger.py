from __future__ import annotations

import pandas as pd
import pytest

from data_agent.v2.models import (
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
from data_agent.v2.slice1 import Slice1DescriptiveRuntime
from data_agent.v2.store import FactConflictError, V2FactStore


def _commitment(commitment_id: str, dataset_version_id: str) -> Commitment:
    return Commitment(
        commitment_id=commitment_id,
        priority=CommitmentPriority.CORE,
        question="平均值是多少？",
        dataset_version_ids=(dataset_version_id,),
        accepted_result_kinds=(FindingKind.ESTIMATE,),
        accepted_method_capabilities=("analysis.describe",),
    )


def test_run_scoped_facts_prevent_interrupted_history_from_blocking_next_run(tmp_path):
    store = V2FactStore(tmp_path, "session_multi_turn")
    first = _commitment("commitment_first", "dv_first")
    second = _commitment("commitment_second", "dv_second")
    store.append_commitments("run_first", "turn_first", [first])
    store.append_commitments("run_second", "turn_second", [second])
    store.append_event(
        ExecutionEvent(
            event_id="event_first_interrupted",
            run_id="run_first",
            commitment_id=first.commitment_id,
            event_type=EventType.USER_INTERRUPTED,
        )
    )
    store.append_finding(
        Finding(
            finding_id="finding_second",
            commitment_id=second.commitment_id,
            finding_kind=FindingKind.ESTIMATE,
            dataset_version_ids=("dv_second",),
            metric_identity="sales.mean",
            method_capability="analysis.describe",
            maximum_claim_class=ClaimClass.DESCRIPTIVE,
            computation_ref="computation:second",
            estimate=25.0,
        )
    )

    first_projection = project_run(*store.read_run_facts("run_first"))
    second_projection = project_run(*store.read_run_facts("run_second"))

    assert first_projection.outcomes[first.commitment_id].status is OutcomeStatus.INTERRUPTED
    assert first_projection.publishable is False
    assert second_projection.outcomes[second.commitment_id].status is OutcomeStatus.SUPPORTED
    assert second_projection.publishable is True
    assert len(store.read_commitments()) == 2
    assert store.read_commitments(run_id="run_first") == [first]
    assert store.read_commitments(turn_id="turn_second") == [second]


def test_commitment_binding_is_immutable_across_runs(tmp_path):
    store = V2FactStore(tmp_path, "session_conflict")
    commitment = _commitment("commitment_same", "dv_same")
    store.append_commitments("run_one", "turn_one", [commitment])

    with pytest.raises(FactConflictError, match="commitment_same"):
        store.append_commitments("run_two", "turn_two", [commitment])


def test_same_session_can_complete_two_runtime_turns_without_losing_history(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    pd.DataFrame({"sales": [10, 20, 30]}).to_csv(inbox / "first.csv", index=False)
    pd.DataFrame({"sales": [40, 50, 60]}).to_csv(inbox / "second.csv", index=False)
    runtime = Slice1DescriptiveRuntime(tmp_path / "sessions", inbox)

    first_events = list(
        runtime.stream(
            session_id="session_runtime_multi",
            turn_id="turn_runtime_first",
            filename="first.csv",
            metric="sales",
            question="第一轮平均值？",
        )
    )
    second_events = list(
        runtime.stream(
            session_id="session_runtime_multi",
            turn_id="turn_runtime_second",
            filename="second.csv",
            metric="sales",
            question="第二轮平均值？",
        )
    )
    store = V2FactStore(tmp_path / "sessions", "session_runtime_multi")
    first_run_id = first_events[0].data["run_id"]
    second_run_id = second_events[0].data["run_id"]

    assert first_events[-1].event == "turn_completed"
    assert second_events[-1].event == "turn_completed"
    assert len(store.read_commitments()) == 2
    assert len(store.read_commitments(run_id=first_run_id)) == 1
    assert len(store.read_commitments(run_id=second_run_id)) == 1
    assert store.read_turn_blocks("turn_runtime_first")["status"] == "finalized"
    assert store.read_turn_blocks("turn_runtime_second")["status"] == "finalized"
