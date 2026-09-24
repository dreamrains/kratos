"""Offline protocol tests; these fixtures are not historical user decisions."""

from dataclasses import replace

import pandas as pd
import pytest

from data_agent.agent.confirmation.models import (
    AnswerMode,
    ConfirmationOption,
    ConfirmationRecord,
    ConfirmationStatus,
)
from data_agent.agent.data_understanding import (
    anchor_offline_measurement_dataset,
    build_data_understanding_bundle,
    project_offline_measurement_contract,
    validate_data_understanding_bundle,
)
from data_agent.session.workspace import Workspace


def _scenario(*, anchored=True):
    workspace = Workspace()
    frame = pd.DataFrame({"day": [1, 7], "retention": [0.8, 0.1]})
    workspace.add("retention", frame)
    identity = workspace.get_data_identity("retention")
    dataset = {
            "dataset": "retention",
            "dataset_contract_id": "duc_retention",
            "grain": "day",
            "rows": 2,
            "columns": [
                {"name": "day", "type": "int64"},
                {"name": "retention", "type": "float64"},
            ],
        }
    if anchored:
        dataset = anchor_offline_measurement_dataset(dataset, workspace=workspace)
    bundle = build_data_understanding_bundle(
        datasets=[dataset],
        quality_findings=[],
        relationship_candidates=[],
    )
    return workspace, identity["version_id"], bundle


def _decision(version_id: str, **overrides):
    record = ConfirmationRecord(
        confirmation_id="conf_unit_1",
        session_id="session_1",
        turn_id="turn_1",
        decision_key=f"measurement:{version_id}:retention:retention",
        source="host_measurement_mapping.v1",
        operation="confirm_measurement",
        question=f"请确认数据集 retention（版本 {version_id}）中 retention 列的单位与数值尺度。",
        decision_impact="Controls the presentation scale for this column.",
        answer_mode=AnswerMode.SINGLE_SELECT,
        options=(
            ConfirmationOption(label="比例 / fraction", value="ratio"),
            ConfirmationOption(label="百分数 / percentage_points", value="percentage_points"),
        ),
        blocking_surfaces=("measurement_mapping",),
        skippable=True,
        resolution_action="record_confirmation_answer",
        resolution_params={"measurement_mapping": {
            "dataset": "retention",
            "column": "retention",
            "choices": [
                {"value": "ratio", "unit": "比例", "scale": "fraction"},
                {"value": "percentage_points", "unit": "百分数", "scale": "percentage_points"},
            ],
        }},
        data_version=version_id,
        status=ConfirmationStatus.RESOLVED,
        created_at="2026-09-24T00:00:00Z",
        updated_at="2026-09-24T00:00:01Z",
        response="ratio",
        response_id="response_1",
    )
    return replace(record, **overrides)


def test_real_shape_without_decision_does_not_infer_percent_from_values_or_metadata():
    workspace, _, bundle = _scenario()
    workspace.set_metadata("retention", "unit", "percent")
    workspace.set_metadata("retention", "context", "retention is in percent")

    projected = project_offline_measurement_contract(bundle, workspace=workspace, session_id="session_1")

    assert projected["datasets"][0]["measurement_mappings"] == []
    assert projected["datasets"][0]["dataset_version_id"] == workspace.get_data_identity("retention")["version_id"]
    assert projected["id"] != bundle["id"]
    assert validate_data_understanding_bundle(projected).ok


def test_upstream_anchor_rejects_stale_or_mislabeled_schema():
    workspace, _, bundle = _scenario()
    dataset = bundle["datasets"][0]
    with pytest.raises(ValueError, match="unverified_dataset_identity"):
        anchor_offline_measurement_dataset({**dataset, "rows": 3}, workspace=workspace)
    with pytest.raises(ValueError, match="unverified_dataset_identity"):
        anchor_offline_measurement_dataset({**dataset, "columns": ["day", "rate"]}, workspace=workspace)


def test_existing_data_understanding_producer_is_default_off(monkeypatch):
    from data_agent.tools import data_io

    workspace, version_id, _ = _scenario()
    monkeypatch.setattr(data_io, "workspace", workspace)
    monkeypatch.setattr(data_io, "_save_trust_state", lambda *_: None)

    class State:
        def __init__(self):
            self.bundles = []

        def add_data_understanding_bundle_ref(self, bundle):
            self.bundles.append(bundle)

    state = State()
    arguments = {
        "state": state,
        "session_id": "session_1",
        "dataset": "retention",
        "df": workspace.get("retention"),
        "contract": {"id": "duc_retention", "grain": "day", "field_roles": {"metrics": ["retention"]}},
        "quality": {},
    }
    data_io._record_data_understanding_bundle(**arguments)
    data_io._record_data_understanding_bundle(**arguments, offline_measurement_scope=True)

    assert "dataset_version_id" not in state.bundles[0]["datasets"][0]
    assert state.bundles[1]["datasets"][0]["dataset_version_id"] == version_id
    assert "measurement_mappings" not in state.bundles[1]["datasets"][0]


def test_only_exact_resolved_and_visible_decision_projects_mapping():
    workspace, version_id, bundle = _scenario()

    projected = project_offline_measurement_contract(
        bundle, workspace=workspace, session_id="session_1",
        confirmation_records=[_decision(version_id)],
    )

    assert projected["datasets"][0]["measurement_mappings"] == [{
        "column": "retention",
        "unit": "比例",
        "scale": "fraction",
        "unit_status": "confirmed",
        "confirmation_id": "conf_unit_1",
        "response_id": "response_1",
    }]


def test_legacy_bundle_without_version_anchor_cannot_upgrade_from_record():
    workspace, version_id, bundle = _scenario(anchored=False)

    projected = project_offline_measurement_contract(
        bundle, workspace=workspace, session_id="session_1",
        confirmation_records=[_decision(version_id)],
    )

    assert projected["datasets"][0]["measurement_mappings"] == []


@pytest.mark.parametrize("overrides", [
    {"source": "model"},
    {"status": ConfirmationStatus.PENDING},
    {"data_version": "dv_stale"},
    {"question": "请确认单位。"},
    {"response_id": ""},
    {"options": (ConfirmationOption(label="10%", value="ratio"),)},
])
def test_untrusted_or_unresolved_record_does_not_grant_unit(overrides):
    workspace, version_id, bundle = _scenario()

    projected = project_offline_measurement_contract(
        bundle, workspace=workspace, session_id="session_1",
        confirmation_records=[_decision(version_id, **overrides)],
    )

    assert projected["datasets"][0]["measurement_mappings"] == []


def test_two_conflicting_resolved_records_do_not_choose_one():
    workspace, version_id, bundle = _scenario()
    second = _decision(version_id, confirmation_id="conf_unit_2", response_id="response_2", response="percentage_points")

    projected = project_offline_measurement_contract(
        bundle, workspace=workspace, session_id="session_1",
        confirmation_records=[_decision(version_id), second],
    )

    assert projected["datasets"][0]["measurement_mappings"] == []


def test_malformed_confirmation_payload_fails_closed_without_exception():
    workspace, version_id, bundle = _scenario()
    malformed = [
        _decision(version_id, resolution_params={"measurement_mapping": {
            "dataset": "retention", "column": ["retention"], "choices": [],
        }}),
        _decision(version_id, resolution_params={"measurement_mapping": {
            "dataset": "retention", "column": "retention",
            "choices": [{"value": ["ratio"], "unit": "比例", "scale": []}],
        }}),
    ]

    projected = project_offline_measurement_contract(
        bundle, workspace=workspace, session_id="session_1", confirmation_records=malformed,
    )

    assert projected["datasets"][0]["measurement_mappings"] == []


def test_stale_understanding_or_forged_mapping_fails_closed():
    workspace, _, bundle = _scenario()
    workspace.add("retention", pd.DataFrame({"day": [1, 7], "retention": [0.8, 0.2]}))
    with pytest.raises(ValueError, match="stale_dataset_understanding"):
        project_offline_measurement_contract(bundle, workspace=workspace, session_id="session_1")

    fresh_workspace, _, fresh_bundle = _scenario()
    forged = dict(fresh_bundle)
    forged["datasets"] = [dict(fresh_bundle["datasets"][0], measurement_mappings=[{
        "column": "retention", "unit": "percent", "scale": "percentage_points",
        "unit_status": "confirmed", "confirmation_id": "conf_x", "response_id": "response_x",
    }])]
    forged.pop("id")
    forged.pop("data_fingerprint")
    # Shape validation cannot authenticate a decision; the offline projector
    # re-derives mappings from records instead of trusting embedded claims.
    assert validate_data_understanding_bundle(forged).ok
    projected = project_offline_measurement_contract(forged, workspace=fresh_workspace, session_id="session_1")
    assert projected["datasets"][0]["measurement_mappings"] == []
    forged["datasets"][0]["measurement_mappings"][0]["scale"] = []
    assert not validate_data_understanding_bundle(forged).ok
