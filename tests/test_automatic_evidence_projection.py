"""Task 9: automatic structured-computation evidence projection.

Eligible structured computations must auto-project ``evidence_record.v2``
evidence without the model calling ``record_evidence_record``. Ineligible
computations (failed runs, ambiguous bindings, free-form python, stale
dataset versions) stay computation-only. The bounded catalog is injected
even when empty, and an existing evidence id attaches to a claim only on
exactly one material-field match.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tests.fixtures.measurement_identity import (
    DATASET_VERSION,
    PLAN_DIGEST,
    PLAN_ID,
    STEP_ID,
    ambiguous_binding,
    build_projection_context,
    exact_step_binding,
    failed_ref,
    free_form_python_ref,
    project_real_correlation,
    stale_dataset_ref,
    structured_correlation_ref,
)


@pytest.fixture
def context(tmp_path):
    return build_projection_context(tmp_path)


@pytest.fixture
def projection_context(tmp_path):
    return build_projection_context(tmp_path)


# ---------------------------------------------------------------------------
# Step 1 tests
# ---------------------------------------------------------------------------


def test_bound_structured_computation_auto_projects_v2_evidence(context):
    from data_agent.agent.evidence_contracts import (
        EVIDENCE_RECORD_CONTRACT_VERSION,
        build_bounded_evidence_catalog,
    )

    result = project_real_correlation(context)

    assert result.projected is True
    assert result.record["contract_version"] == EVIDENCE_RECORD_CONTRACT_VERSION
    assert result.record["plan_id"] == PLAN_ID
    assert result.record["requirement_ids"] == list(exact_step_binding().requirement_ids)
    assert result.record["dataset_versions"] == [DATASET_VERSION]
    measurement = result.record["measurements"][0]
    identity = measurement["identity"]
    assert identity["contract_version"] == "measurement_identity.v1"
    assert identity["measurement_key"].startswith("m_")
    assert identity["metric_key"] == "pairs.correlation::revenue|cost"
    assert identity["metric_label"] == "revenue cost correlation"
    assert identity["metric_aliases"] == [
        "revenue cost correlation",
        "cost revenue correlation",
    ]
    assert identity["claim_key"] == "revenue_cost_correlation"
    assert identity["plan_id"] == PLAN_ID
    assert identity["plan_version"] == PLAN_DIGEST
    assert identity["step_id"] == STEP_ID
    assert identity["requirement_ids"] == ["req_corr_effect"]
    assert identity["dataset_versions"] == [DATASET_VERSION]
    assert identity["computation_ref_id"].startswith("cr_")

    catalog = build_bounded_evidence_catalog(
        [result.record],
        max_records=8,
        max_chars=2000,
    )
    assert f"dataset_versions={DATASET_VERSION}" in catalog


def test_measurement_key_is_stable_and_changes_with_metric_or_version(context):
    first = project_real_correlation(context)
    second = project_real_correlation(context)
    first_identity = first.record["measurements"][0]["identity"]
    second_identity = second.record["measurements"][0]["identity"]
    assert first_identity["measurement_key"] == second_identity["measurement_key"]

    from data_agent.agent.evidence_contracts import measurement_key_for

    changed = dict(first_identity)
    changed.pop("measurement_key")
    changed["metric_key"] = "pairs.correlation::profit|cost"
    assert measurement_key_for(changed) != first_identity["measurement_key"]

    changed["metric_key"] = first_identity["metric_key"]
    changed["dataset_versions"] = ["ds_main_v2"]
    assert measurement_key_for(changed) != first_identity["measurement_key"]


def test_measurement_identity_validator_rejects_tampered_key(context):
    result = project_real_correlation(context)
    identity = dict(result.record["measurements"][0]["identity"])
    identity["metric_key"] = "pairs.correlation::profit|cost"

    from data_agent.agent.evidence_contracts import validate_measurement_identity

    validation = validate_measurement_identity(identity)
    assert validation.ok is False
    assert validation.error_type == "measurement_key_mismatch"


@pytest.mark.parametrize(
    ("ref", "binding", "reason"),
    [
        (failed_ref(), exact_step_binding(), "computation_failed"),
        (free_form_python_ref(), exact_step_binding(), "unstructured_tool"),
        (structured_correlation_ref(), ambiguous_binding(), "ambiguous_analysis_step"),
        (stale_dataset_ref(), exact_step_binding(), "stale_dataset_version"),
    ],
)
def test_ineligible_computation_stays_computation_only(
    projection_context,
    ref,
    binding,
    reason,
):
    from data_agent.agent.evidence_contracts import (
        project_structured_computation_evidence,
    )

    project_real_correlation(projection_context)
    artifact_path = (
        projection_context.sessions_root
        / projection_context.session_id
        / "tool_outputs"
    )
    artifact_path = next(artifact_path.glob("*_computation.json"))
    ref = dict(ref)
    ref["artifact_path"] = artifact_path

    result = project_structured_computation_evidence(
        computation_ref=ref,
        binding=binding,
        plan=projection_context.plan,
        capability=projection_context.capability,
        dataset_contracts=projection_context.dataset_contracts,
        current_session_id=projection_context.session_id,
        current_turn_id=projection_context.turn_id,
        sessions_root=projection_context.sessions_root,
    )
    assert result.projected is False
    assert result.reason == reason


# ---------------------------------------------------------------------------
# Step 2 tests
# ---------------------------------------------------------------------------


def test_empty_evidence_still_injects_catalog_header():
    from data_agent.agent.evidence_contracts import build_bounded_evidence_catalog

    catalog = build_bounded_evidence_catalog([], max_records=8, max_chars=2000)
    assert "可用证据：0 条" in catalog
    assert "不要重新运行工具来制造证据" in catalog


def test_catalog_caps_records_and_chars():
    from data_agent.agent.evidence_contracts import build_bounded_evidence_catalog

    records = []
    for index in range(20):
        records.append({
            "id": f"ev_{index}",
            "claim_key": f"claim_{index}",
            "step_order": index,
            "claim_class": "association",
            "measurements": [{
                "metric": "correlation",
                "value": 0.1 * index,
                "unit": "coefficient",
            }],
            "dataset_versions": ["ds_v1"],
            "verification_level": "structured_checked",
            "limitations": ["descriptive only"],
        })
    catalog = build_bounded_evidence_catalog(records, max_records=4, max_chars=800)
    # Header line + up to 4 record lines.
    lines = [line for line in catalog.splitlines() if line.strip()]
    assert lines[0].startswith("可用证据：")
    # Records present are capped at 4.
    record_lines = [line for line in lines[1:] if line.startswith("- ")]
    assert len(record_lines) <= 4
    assert len(catalog) <= 1500  # generous upper bound; max_chars only bounds the records loop
