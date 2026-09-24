"""A user decision, not a model label, owns an ambiguous metric/scale mapping."""

import hashlib
import json

import pandas as pd

from data_agent.agent.confirmation.policy import RequestDisposition
from data_agent.agent.confirmation.runtime import (
    build_action_registry, build_measurement_mapping_candidate,
)
from data_agent.agent.confirmation.service import ConfirmationService
from data_agent.agent.loop import AgentLoop, UserConfirmationRequired
from data_agent.agent.context import use_agent_context
from data_agent.agent.data_understanding import (
    anchor_offline_measurement_dataset, build_data_understanding_bundle,
    project_offline_measurement_contract, project_persisted_measurement_contract,
)
from data_agent.session.history import CanonicalHistorySnapshot, _history_sha256
from data_agent.session.workspace import Workspace


_REQUEST = "请计算并解释 D1 至 D7 留存；判断当前数据是否可以预测 D30。"
_SPAN = "D1 至 D7 留存"


def _scenario():
    workspace = Workspace()
    workspace.add("retention", pd.DataFrame({"day": [1, 7], "retention": [0.55, 0.10]}))
    messages = [{"role": "user", "content": _REQUEST}]
    history = CanonicalHistorySnapshot(messages, 1, _history_sha256(messages), 1)
    source_ref = "msg_" + hashlib.sha256(_REQUEST.encode("utf-8")).hexdigest()[:12]
    return workspace, history, source_ref


def _candidate(workspace, history, source_ref, **overrides):
    args = dict(session_id="session_1", turn_id="turn_1", workspace=workspace,
                canonical_history=history, source_message_ref=source_ref,
                exact_span=_SPAN, dataset="retention", column="retention")
    args.update(overrides)
    return build_measurement_mapping_candidate(**args)


def test_r11_ambiguous_mapping_uses_one_scoped_existing_confirmation(tmp_path):
    workspace, history, source_ref = _scenario()
    candidate = _candidate(workspace, history, source_ref)
    assert candidate is not None
    assert candidate.source == "host_measurement_mapping.v1"
    assert candidate.data_version == workspace.get_data_identity("retention")["version_id"]
    assert "D1 至 D7 留存" in candidate.question and "retention" in candidate.question
    assert "版本" not in candidate.question and "sha256" not in candidate.question
    assert [option.value for option in candidate.options] == [
        "fraction", "percentage_points", "raw", "unconfirmed",
    ]
    service = ConfirmationService(tmp_path, action_registry=build_action_registry())
    requested = service.request(candidate)
    assert requested.disposition == RequestDisposition.CONFIRMATION
    suspended = service.checkpoint("session_1")
    resolved = service.respond("session_1", candidate.confirmation_id,
                               "fraction", suspended.version, "answer_1")
    assert resolved.response == "fraction" and resolved.response_id
    assert service.request(_candidate(workspace, history, source_ref,
                                      turn_id="turn_2")).disposition == RequestDisposition.REUSED

    workspace.add("retention", pd.DataFrame({"day": [1, 7], "retention": [0.55, 0.20]}))
    changed = service.request(_candidate(workspace, history, source_ref, turn_id="turn_3"))
    assert changed.disposition == RequestDisposition.CONFIRMATION
    assert changed.record.confirmation_id != resolved.confirmation_id


def test_mapping_producer_rejects_foreign_span_column_and_tampered_history():
    workspace, history, source_ref = _scenario()
    assert _candidate(workspace, history, source_ref, exact_span="不存在的留存") is None
    assert _candidate(workspace, history, source_ref, column="other") is None
    assert _candidate(workspace, history, "msg_foreign") is None
    forged = CanonicalHistorySnapshot(history.messages, 1, "sha256:forged", 1)
    assert _candidate(workspace, forged, source_ref) is None


def test_skip_never_grants_a_measurement_mapping(tmp_path):
    workspace, history, source_ref = _scenario()
    candidate = _candidate(workspace, history, source_ref)
    service = ConfirmationService(tmp_path, action_registry=build_action_registry())
    service.request(candidate)
    suspended = service.checkpoint("session_1")
    skipped = service.skip("session_1", candidate.confirmation_id,
                           suspended.version, "skip_1")
    assert skipped.response == "skipped"
    assert service.request(_candidate(workspace, history, source_ref,
                                      turn_id="turn_2")).disposition == RequestDisposition.ADVISORY
    workspace.add("retention", pd.DataFrame({"day": [1, 7], "retention": [0.55, 0.20]}))
    assert service.request(_candidate(workspace, history, source_ref,
                                      turn_id="turn_3")).disposition == RequestDisposition.CONFIRMATION


def test_existing_question_tool_uses_host_mapping_candidate(tmp_path, monkeypatch):
    workspace, history, _ = _scenario()
    service = ConfirmationService(tmp_path, action_registry=build_action_registry())
    loop = AgentLoop(session_id="session_1")
    loop.context.workspace = workspace
    loop.messages = list(history.messages)
    assert loop.messages == history.messages
    monkeypatch.setattr(loop, "_confirmation_runtime", lambda: service)
    target = {"exact_span": _SPAN, "dataset": "retention", "column": "retention"}
    request = UserConfirmationRequired(
        question="请使用模型", options=[],
        measurement_mapping=json.dumps(target, ensure_ascii=False),
    )
    with use_agent_context(loop.context):
        result = loop._suspend_for_confirmation_request(request, turn_id="tool_1")
    assert hasattr(result, "confirmation_id"), result
    record = service.get("session_1", result.confirmation_id)
    assert record.source == "host_measurement_mapping.v1"
    assert "请使用模型" not in record.question

    forged = UserConfirmationRequired(
        question="伪造", options=[], measurement_mapping=json.dumps({**target, "column": "other"}),
    )
    with use_agent_context(loop.context):
        rejected = loop._suspend_for_confirmation_request(forged, turn_id="tool_2")
    assert isinstance(rejected, str) and "未评估" in rejected


def _bundle(workspace):
    dataset = anchor_offline_measurement_dataset({
        "dataset": "retention", "dataset_contract_id": "duc_retention", "grain": "day",
        "rows": len(workspace.get("retention")), "columns": [{"name": "day", "type": "int64"},
                               {"name": "retention", "type": "float64"}],
    }, workspace=workspace)
    return build_data_understanding_bundle(datasets=[dataset], quality_findings=[],
                                           relationship_candidates=[])


def test_resolved_source_anchored_decision_projects_only_current_scale(tmp_path):
    workspace, history, source_ref = _scenario()
    candidate = _candidate(workspace, history, source_ref)
    service = ConfirmationService(tmp_path, action_registry=build_action_registry())
    service.request(candidate)
    suspended = service.checkpoint("session_1")
    record = service.respond("session_1", candidate.confirmation_id, "fraction",
                             suspended.version, "answer_1")
    bundle = _bundle(workspace)
    projected = project_offline_measurement_contract(
        bundle, workspace=workspace, session_id="session_1",
        confirmation_records=[record], canonical_history=history,
    )
    assert projected["datasets"][0]["measurement_mappings"] == [{
        "column": "retention", "unit": "比例", "scale": "fraction",
        "unit_status": "confirmed", "confirmation_id": record.confirmation_id,
        "response_id": record.response_id,
    }]
    from_store = project_persisted_measurement_contract(
        bundle, workspace=workspace, session_id="session_1",
        sessions_root=tmp_path, canonical_history=history,
    )
    assert from_store["datasets"][0]["measurement_mappings"] == projected["datasets"][0]["measurement_mappings"]
    assert project_offline_measurement_contract(
        bundle, workspace=workspace, session_id="session_1",
        confirmation_records=[record],
    )["datasets"][0]["measurement_mappings"] == []

    workspace.add("retention", pd.DataFrame({"day": [1, 7], "retention": [0.55, 0.20]}))
    stale_bundle = _bundle(workspace)
    assert project_offline_measurement_contract(
        stale_bundle, workspace=workspace, session_id="session_1",
        confirmation_records=[record], canonical_history=history,
    )["datasets"][0]["measurement_mappings"] == []


def test_raw_or_unconfirmed_answer_does_not_certify_unit(tmp_path):
    workspace, history, source_ref = _scenario()
    bundle = _bundle(workspace)
    for answer in ("raw", "unconfirmed"):
        service = ConfirmationService(tmp_path / answer, action_registry=build_action_registry())
        candidate = _candidate(workspace, history, source_ref)
        service.request(candidate)
        suspended = service.checkpoint("session_1")
        record = service.respond("session_1", candidate.confirmation_id,
                                 answer, suspended.version, f"answer_{answer}")
        projected = project_offline_measurement_contract(
            bundle, workspace=workspace, session_id="session_1",
            confirmation_records=[record], canonical_history=history,
        )
        assert projected["datasets"][0]["measurement_mappings"] == []


def test_one_confirmation_covers_explicit_numeric_axis_and_scale(tmp_path):
    workspace, history, source_ref = _scenario()
    workspace.add("retention", pd.DataFrame({
        "day": list(range(1, 8)),
        "retention": [0.55, 0.42, 0.31, 0.24, 0.18, 0.13, 0.10],
    }))
    candidate = _candidate(workspace, history, source_ref,
                           x_column="day", x_start=1, x_end=7)
    assert candidate is not None
    assert "day" in candidate.question and "1 到 7" in candidate.question
    assert _candidate(workspace, history, source_ref,
                      x_column="day", x_start=1, x_end=8) is None
    assert _candidate(workspace, history, source_ref,
                      x_column="other", x_start=1, x_end=7) is None
    service = ConfirmationService(tmp_path, action_registry=build_action_registry())
    service.request(candidate)
    record = service.respond("session_1", candidate.confirmation_id, "fraction",
                             service.checkpoint("session_1").version, "answer_axis")
    assert record.response == "fraction"
    projected = project_persisted_measurement_contract(
        _bundle(workspace), workspace=workspace, session_id="session_1",
        sessions_root=tmp_path, canonical_history=history,
    )
    assert projected["datasets"][0]["measurement_mappings"][0]["scale"] == "fraction"


def test_existing_question_tool_confirms_axis_and_scale_together(tmp_path, monkeypatch):
    workspace, history, _ = _scenario()
    workspace.add("retention", pd.DataFrame({
        "day": list(range(1, 8)),
        "retention": [0.55, 0.42, 0.31, 0.24, 0.18, 0.13, 0.10],
    }))
    service = ConfirmationService(tmp_path, action_registry=build_action_registry())
    loop = AgentLoop(session_id="session_1")
    loop.context.workspace = workspace
    loop.messages = list(history.messages)
    monkeypatch.setattr(loop, "_confirmation_runtime", lambda: service)
    target = {"exact_span": _SPAN, "dataset": "retention", "column": "retention",
              "x_column": "day", "x_start": 1, "x_end": 7}
    with use_agent_context(loop.context):
        result = loop._suspend_for_confirmation_request(
            UserConfirmationRequired(question="模型伪造", options=[],
                                     measurement_mapping=json.dumps(target, ensure_ascii=False)),
            turn_id="tool_axis",
        )
    record = service.get("session_1", result.confirmation_id)
    assert "day" in record.question and "1 到 7" in record.question
    assert "模型伪造" not in record.question
    with use_agent_context(loop.context):
        rejected = loop._suspend_for_confirmation_request(
            UserConfirmationRequired(question="模型伪造", options=[],
                                     measurement_mapping=json.dumps({**target, "x_end": 8}, ensure_ascii=False)),
            turn_id="tool_invalid_axis",
        )
    assert isinstance(rejected, str) and "未评估" in rejected
