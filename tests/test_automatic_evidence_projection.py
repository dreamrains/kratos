"""Task 9: automatic structured-computation evidence projection.

Eligible structured computations must auto-project ``evidence_record.v2``
evidence without the model calling ``record_evidence_record``. Ineligible
computations (failed runs, ambiguous bindings, free-form python, stale
dataset versions) stay computation-only. The bounded catalog is injected
even when empty, and an existing evidence id attaches to a claim only on
exactly one material-field match.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from data_agent.agent.analysis_execution import StepBindingResult
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
    assert identity["metric_key"] == (
        "pairs.correlation::var1=revenue|var2=cost"
    )
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
    assert f"measurement_key={identity['measurement_key']}" in catalog
    assert (
        "metric_key=pairs.correlation::var1=revenue|var2=cost"
        in catalog
    )
    assert "metric_label=revenue cost correlation" in catalog
    assert f"dataset_versions={DATASET_VERSION}" in catalog


def test_multi_claim_binding_projects_one_valid_record_per_exact_claim(context):
    context.plan["method_plan"][0]["required_claim_keys"] = [
        "significant_factors",
        "effect_estimates",
    ]
    binding = StepBindingResult(
        ok=True,
        plan_id=PLAN_ID,
        step_id=STEP_ID,
        claim_key="significant_factors",
        claim_keys=("significant_factors", "effect_estimates"),
        requirement_ids=("req_corr_effect",),
    )

    result = project_real_correlation(
        context,
        binding=binding,
        ref_overrides={
            "claim_key": "significant_factors",
            "claim_keys": ["significant_factors", "effect_estimates"],
        },
    )

    assert result.projected is True
    assert result.record == result.records[0]
    assert [record["claim_key"] for record in result.records] == [
        "significant_factors",
        "effect_estimates",
    ]
    assert len({record["id"] for record in result.records}) == 2
    for record in result.records:
        assert {
            measurement["identity"]["claim_key"]
            for measurement in record["measurements"]
            if isinstance(measurement.get("identity"), dict)
        } == {record["claim_key"]}


def test_data_quality_projection_emits_nested_missingness_and_duplicate_measurements(context):
    capability = {
        "capability_id": "data.quality",
        "risk_level": "low",
        "evidence_fields": [
            "sample_size",
            "missingness",
            "duplicates",
            "outliers",
            "limitations",
            "allowed_claim_class",
        ],
    }
    output = {
        "summary": "quality result",
        "data": {
            "sample_size": 125,
            "missingness": [
                {"column": "revenue", "count": 3, "percentage": 2.4},
                {"column": "cost", "count": 2, "percentage": 1.6},
            ],
            "duplicates": {"count": 5, "percentage": 4.0},
            "outliers": [],
            "limitations": ["IQR rule"],
            "allowed_claim_class": "descriptive",
        },
    }

    result = project_real_correlation(
        context,
        output=output,
        capability=capability,
    )

    assert result.projected is True
    projected = {
        (
            measurement["metric"],
            measurement["identity"]["metric_label"],
            measurement["value"],
            measurement["unit"],
        )
        for measurement in result.record["measurements"]
    }
    assert ("sample_size", "sample size", 125.0, "value") in projected
    assert ("missingness.count", "revenue count", 3.0, "count") in projected
    assert ("missingness.percentage", "revenue percentage", 2.4, "percent") in projected
    assert ("missingness.count", "cost count", 2.0, "count") in projected
    assert ("missingness.percentage", "cost percentage", 1.6, "percent") in projected
    assert ("duplicates.count", "duplicates count", 5.0, "count") in projected
    assert ("duplicates.percentage", "duplicates percentage", 4.0, "percent") in projected


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


def test_catalog_rejects_partial_and_inconsistent_measurement_identities(context):
    from data_agent.agent.evidence_contracts import build_bounded_evidence_catalog

    projected = project_real_correlation(context).record
    valid_identity = projected["measurements"][0]["identity"]

    partial = copy.deepcopy(projected)
    partial["measurements"][0]["identity"] = {
        field: valid_identity[field]
        for field in ("measurement_key", "metric_key", "metric_label", "claim_key")
    }
    inconsistent = copy.deepcopy(projected)
    inconsistent["measurements"][0]["identity"]["measurement_key"] = "m_fabricated"

    catalog = build_bounded_evidence_catalog(
        [partial, inconsistent], max_records=8, max_chars=2000
    )

    assert catalog.count("unbound_measurement=") == 2
    assert f"measurement_key={valid_identity['measurement_key']}" not in catalog
    assert "measurement_key=m_fabricated" not in catalog


def test_identity_uses_all_trusted_list_item_context_for_uniqueness(context):
    output = {
        "summary": "Two segment correlations",
        "data": {
            "pairs": [
                {
                    "target": "revenue",
                    "dimension": "north",
                    "correlation": 0.4,
                    "effective_sample_size": 50,
                    "p_value": 0.01,
                },
                {
                    "target": "revenue",
                    "dimension": "south",
                    "correlation": 0.4,
                    "effective_sample_size": 50,
                    "p_value": 0.01,
                },
            ],
            "allowed_claim_class": "association",
        },
    }

    result = project_real_correlation(context, output=output)

    assert result.projected is True
    first = result.record["measurements"][0]["identity"]
    second = result.record["measurements"][1]["identity"]
    assert first["metric_key"] == (
        "pairs.correlation::target=revenue|dimension=north"
    )
    assert second["metric_key"] == (
        "pairs.correlation::target=revenue|dimension=south"
    )
    assert first["measurement_key"] != second["measurement_key"]


def test_identity_combines_variables_with_other_trusted_item_context(context):
    output = {
        "summary": "Two dimension-specific correlations",
        "data": {
            "pairs": [
                {
                    "variables": ["revenue", "cost"],
                    "dimension": "north",
                    "correlation": 0.4,
                    "effective_sample_size": 50,
                    "p_value": 0.01,
                },
                {
                    "variables": ["revenue", "cost"],
                    "dimension": "south",
                    "correlation": 0.4,
                    "effective_sample_size": 50,
                    "p_value": 0.01,
                },
            ],
            "allowed_claim_class": "association",
        },
    }

    result = project_real_correlation(context, output=output)

    assert result.projected is True
    first = result.record["measurements"][0]["identity"]
    second = result.record["measurements"][1]["identity"]
    assert first["metric_key"] == (
        "pairs.correlation::revenue|cost|dimension=north"
    )
    assert second["metric_key"] == (
        "pairs.correlation::revenue|cost|dimension=south"
    )
    assert first["measurement_key"] != second["measurement_key"]


def test_reordered_multi_dataset_scope_has_same_computation_and_measurement_keys(
    context,
):
    context.plan["method_plan"][0]["dataset_inputs"] = ["main", "secondary"]
    context.plan["method_plan"][0]["dataset_contract_ids"] = [
        "contract_main_v1",
        "contract_secondary_v1",
    ]
    context.dataset_contracts.append({
        "id": "contract_secondary_v1",
        "dataset": "secondary",
        "dataset_id": "ds_secondary_v1",
        "quality_status": "ready",
    })

    first = project_real_correlation(
        context,
        dataset_versions=[DATASET_VERSION, "ds_secondary_v1"],
    )
    second = project_real_correlation(
        context,
        dataset_versions=["ds_secondary_v1", DATASET_VERSION],
    )

    assert first.projected is True
    assert second.projected is True
    first_identity = first.record["measurements"][0]["identity"]
    second_identity = second.record["measurements"][0]["identity"]
    assert first_identity["computation_ref_id"] == second_identity["computation_ref_id"]
    assert first_identity["measurement_key"] == second_identity["measurement_key"]


def test_unambiguous_nested_scalar_receives_identity(context):
    capability = {
        "capability_id": "analysis.sample_size",
        "category": "descriptive",
        "evidence_fields": [
            "effective_sample_size.total",
            "allowed_claim_class",
        ],
    }
    output = {
        "summary": "Effective sample size is 100",
        "data": {
            "effective_sample_size": {"total": 100},
            "allowed_claim_class": "descriptive",
        },
    }

    result = project_real_correlation(
        context,
        capability=capability,
        output=output,
    )

    assert result.projected is True
    identity = result.record["measurements"][0]["identity"]
    assert identity["metric_key"] == "effective_sample_size.total"
    assert identity["metric_label"] == "effective sample size total"


def test_projector_rejects_stale_plan_digest(context):
    result = project_real_correlation(
        context,
        ref_overrides={"plan_digest": "sha256:stale_plan"},
    )

    assert result.projected is False
    assert result.reason == "stale_plan_revision"


def test_projector_rejects_stale_step_digest(context):
    result = project_real_correlation(
        context,
        ref_overrides={"step_digest": "sha256:stale_step"},
    )

    assert result.projected is False
    assert result.reason == "stale_plan_revision"


@pytest.mark.parametrize(
    ("dataset_versions", "binding", "reason"),
    [
        (
            [DATASET_VERSION, 7],
            None,
            "invalid_dataset_versions",
        ),
        (
            None,
            StepBindingResult(
                ok=True,
                plan_id=PLAN_ID,
                step_id=STEP_ID,
                claim_key="revenue_cost_correlation",
                requirement_ids=("req_corr_effect", 7),
            ),
            "invalid_requirement_ids",
        ),
    ],
)
def test_projector_rejects_malformed_material_identity_scope(
    context,
    dataset_versions,
    binding,
    reason,
):
    result = project_real_correlation(
        context,
        dataset_versions=dataset_versions,
        binding=binding,
    )

    assert result.projected is False
    assert result.reason == reason


def test_present_identity_must_match_measurement_and_bound_provenance(context):
    from data_agent.agent.evidence_contracts import (
        measurement_key_for,
        validate_evidence_record,
    )

    projected = project_real_correlation(context)
    material_mismatch = copy.deepcopy(projected.record)
    material_identity = material_mismatch["measurements"][0]["identity"]
    material_identity["value"] = 999.0
    material_identity["measurement_key"] = measurement_key_for(material_identity)

    validation = validate_evidence_record(
        material_mismatch,
        current_plan_id=PLAN_ID,
    )

    assert validation.ok is False
    assert validation.error_type == "measurement_identity_material_mismatch"

    metric_mismatch = copy.deepcopy(projected.record)
    metric_identity = metric_mismatch["measurements"][0]["identity"]
    metric_identity["metric_key"] = "pairs.profit::revenue|cost"
    metric_identity["measurement_key"] = measurement_key_for(metric_identity)

    validation = validate_evidence_record(
        metric_mismatch,
        current_plan_id=PLAN_ID,
    )

    assert validation.ok is False
    assert validation.error_type == "measurement_identity_material_mismatch"

    provenance_mismatch = copy.deepcopy(projected.record)
    provenance_identity = provenance_mismatch["measurements"][0]["identity"]
    provenance_identity["computation_ref_id"] = "cr_forged"
    provenance_identity["measurement_key"] = measurement_key_for(provenance_identity)

    validation = validate_evidence_record(
        provenance_mismatch,
        current_plan_id=PLAN_ID,
    )

    assert validation.ok is False
    assert validation.error_type == "measurement_identity_provenance_mismatch"


def test_legacy_identity_free_record_loads_but_projector_mode_requires_identity(
    context,
):
    from data_agent.agent.evidence_contracts import (
        validate_evidence_record,
        validate_measurement,
    )

    record = copy.deepcopy(project_real_correlation(context).record)
    for measurement in record["measurements"]:
        measurement.pop("identity", None)

    legacy = validate_evidence_record(record, current_plan_id=PLAN_ID)
    strict = validate_evidence_record(
        record,
        current_plan_id=PLAN_ID,
        require_measurement_identity=True,
    )
    direct = validate_measurement(
        record["measurements"][0],
        require_identity=True,
    )

    assert legacy.ok is True
    assert strict.ok is False
    assert strict.error_type == "missing_measurement_identity"
    assert direct.ok is False
    assert direct.error_type == "missing_measurement_identity"

    partially_stripped = copy.deepcopy(project_real_correlation(context).record)
    partially_stripped["measurements"][0].pop("identity")
    strict = validate_evidence_record(
        partially_stripped,
        current_plan_id=PLAN_ID,
        require_measurement_identity=True,
    )
    assert strict.ok is False
    assert strict.error_type == "missing_measurement_identity"


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
    assert "可用证据测量：0 条" in catalog
    assert "不要重新运行工具来制造证据" in catalog


def test_catalog_caps_measurement_entries_and_chars():
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
    # Header line + up to 4 emitted measurement entries.
    lines = [line for line in catalog.splitlines() if line.strip()]
    assert lines[0].startswith("可用证据测量：")
    # Measurement entries present are capped at 4.
    record_lines = [line for line in lines[1:] if line.startswith("- ")]
    assert len(record_lines) <= 4
    assert len(catalog) <= 800


def test_catalog_deduplicates_measurement_references(context):
    from data_agent.agent.evidence_contracts import build_bounded_evidence_catalog

    record = project_real_correlation(context).record
    identity = record["measurements"][0]["identity"]
    record["measurements"].append(copy.deepcopy(record["measurements"][0]))

    catalog = build_bounded_evidence_catalog([record], max_records=8, max_chars=2000)

    assert catalog.count(f"measurement_key={identity['measurement_key']}") == 1


def test_catalog_never_exceeds_max_chars_when_first_entry_is_too_long(context):
    from data_agent.agent.evidence_contracts import build_bounded_evidence_catalog

    record = project_real_correlation(context).record
    full_catalog = build_bounded_evidence_catalog([record], max_records=8, max_chars=2000)
    header = full_catalog.splitlines()[0]

    catalog = build_bounded_evidence_catalog(
        [record], max_records=8, max_chars=len(header)
    )

    assert catalog == header
    assert len(catalog) <= len(header)


def test_bounded_alias_catalog_emits_ready_markers_and_exact_map(context):
    from data_agent.agent.evidence_contracts import (
        build_bounded_evidence_alias_catalog,
    )

    record = project_real_correlation(context).record
    catalog = build_bounded_evidence_alias_catalog(
        [record], max_records=8, max_chars=2000
    )

    first_key = record["measurements"][0]["identity"]["measurement_key"]
    second_key = record["measurements"][1]["identity"]["measurement_key"]
    assert "marker=[[evidence:ae01#am01]]" in catalog.text
    assert "marker=[[evidence:ae01#am02]]" in catalog.text
    assert (
        "required_verified_core_copy=已验证核心："
        "revenue cost correlation = 0.4 [[evidence:ae01#am01]]。"
    ) in catalog.text
    assert catalog.text.count("required_verified_core_copy=") == 1
    assert catalog.aliases[:2] == (
        ("ae01", "am01", record["id"], first_key),
        ("ae01", "am02", record["id"], second_key),
    )


def test_alias_map_contains_only_entries_emitted_within_bound(context):
    from data_agent.agent.evidence_contracts import (
        build_bounded_evidence_alias_catalog,
    )

    record = project_real_correlation(context).record
    bounded = build_bounded_evidence_alias_catalog(
        [record], max_records=1, max_chars=2000
    )

    first_key = record["measurements"][0]["identity"]["measurement_key"]
    assert bounded.aliases == (("ae01", "am01", record["id"], first_key),)
    assert "ae01#am01" in bounded.text
    assert "ae01#am02" not in bounded.text


def test_alias_catalog_does_not_authorize_unbound_measurement(context):
    from data_agent.agent.evidence_contracts import (
        build_bounded_evidence_alias_catalog,
    )

    record = project_real_correlation(context).record
    record["measurements"][0].pop("identity")

    catalog = build_bounded_evidence_alias_catalog(
        [record], max_records=8, max_chars=2000
    )

    assert "unbound_measurement=" in catalog.text
    bound_keys = {
        measurement["identity"]["measurement_key"]
        for measurement in record["measurements"]
        if isinstance(measurement.get("identity"), dict)
    }
    assert {alias[3] for alias in catalog.aliases} == bound_keys


def test_alias_catalog_without_bound_measurement_has_no_required_core_copy(context):
    from data_agent.agent.evidence_contracts import (
        build_bounded_evidence_alias_catalog,
    )

    record = project_real_correlation(context).record
    for measurement in record["measurements"]:
        measurement.pop("identity", None)

    catalog = build_bounded_evidence_alias_catalog(
        [record], max_records=8, max_chars=2000
    )

    assert catalog.aliases == ()
    assert "required_verified_core_copy=" not in catalog.text


def test_alias_catalog_prioritizes_bound_measurements_over_unbound_diagnostics(context):
    from data_agent.agent.evidence_contracts import (
        build_bounded_evidence_alias_catalog,
    )

    bound = project_real_correlation(context).record
    bound["step_order"] = 2
    unbound = {
        "id": "legacy_unbound",
        "step_order": 1,
        "claim_key": "legacy_note",
        "verification_level": "legacy_unbound",
        "measurements": [],
    }

    catalog = build_bounded_evidence_alias_catalog(
        [unbound, bound], max_records=1, max_chars=2000
    )

    first_key = bound["measurements"][0]["identity"]["measurement_key"]
    assert catalog.aliases == (("ae01", "am01", bound["id"], first_key),)
    assert "marker=[[evidence:ae01#am01]]" in catalog.text
    assert "legacy_note" not in catalog.text


def test_alias_catalog_round_robins_bound_records_before_second_measurement(context):
    from data_agent.agent.evidence_contracts import (
        build_bounded_evidence_alias_catalog,
    )

    first = project_real_correlation(context).record
    second = copy.deepcopy(first)
    second["id"] = "evidence_second_step"
    first["step_order"] = 1
    second["step_order"] = 2

    catalog = build_bounded_evidence_alias_catalog(
        [first, second], max_records=2, max_chars=2000
    )

    assert {alias[2] for alias in catalog.aliases} == {
        first["id"],
        second["id"],
    }
