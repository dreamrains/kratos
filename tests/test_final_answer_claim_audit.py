import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from data_agent.agent.answer_quality import (
    build_final_answer_audit,
    extract_material_claims,
    strip_internal_evidence_markers,
)
from data_agent.agent.analysis_requirements import compile_analysis_requirements
from data_agent.agent.evidence_contracts import (
    computation_ref_key,
    expand_evidence_alias_markers,
    measurement_key_for,
    validate_evidence_record,
)
from data_agent.agent.verification import verify_analysis_claims
from data_agent.agent import trust_workflow_runtime as runtime


def _evidence(**overrides):
    record = {
        "id": "ev_revenue",
        "plan_id": "plan_current",
        "step_id": "step_compare",
        "claim_key": "revenue_change",
        "claim": "Revenue increased 12% in 2026-05 for new users.",
        "dataset": "sales",
        "method": "period_compare",
        "sample_size": 1200,
        "time_scope": "2026-05-01 to 2026-05-31",
        "calculation_method": "monthly revenue delta",
        "method_detail": "compared May revenue against April revenue",
        "limitations": ["descriptive comparison only"],
        "confidence": "medium",
        "verification_level": "structured_checked",
        "measurements": [{
            "metric": "revenue_change",
            "definition": "May revenue change versus April",
            "value": 0.12,
            "unit": "ratio",
            "grain": "user",
            "population_scope": "new users",
            "time_scope": "2026-05-01 to 2026-05-31",
            "method": "period_compare",
            "denominator": "April revenue",
            "limitations": ["descriptive comparison only"],
        }],
    }
    record.update(overrides)
    return record


def _bind_test_measurement_identity(record):
    bound = copy.deepcopy(record)
    measurements = bound.get("measurements")
    if (
        not isinstance(measurements, list)
        or len(measurements) != 1
        or not isinstance(measurements[0], dict)
        or isinstance(measurements[0].get("identity"), dict)
        or measurements[0].get("identity_status") == "metric_identity_missing"
    ):
        return bound
    measurement = measurements[0]
    direction = str(measurement.get("direction") or "")
    if not direction and "increas" in str(bound.get("claim") or "").lower():
        direction = "increase"
        measurement["direction"] = direction
    refs = [
        item
        for item in bound.get("computation_refs") or []
        if isinstance(item, dict)
    ]
    if not refs:
        refs = [{
            "tool_call_id": "call_test_identity",
            "plan_digest": "test_plan_digest",
            "step_digest": "test_step_digest",
            "dataset_versions": ["dataset_sales_v1"],
        }]
        bound["computation_refs"] = refs
    requirement_ids = [
        str(item)
        for item in bound.get("requirement_ids") or ["req_test_identity"]
    ]
    dataset_versions = [
        str(item)
        for item in (
            bound.get("dataset_versions")
            or refs[0].get("dataset_versions")
            or ["dataset_sales_v1"]
        )
    ]
    bound["requirement_ids"] = requirement_ids
    bound["dataset_versions"] = dataset_versions
    bound.setdefault("allowed_claim_class", "comparison")
    metric = str(measurement.get("metric") or "")
    metric_label = metric.replace("_change", "").replace("_", " ").title()
    identity = {
        "contract_version": "measurement_identity.v1",
        "metric_key": metric,
        "metric_label": metric_label,
        "metric_aliases": [metric.replace("_", " ")],
        "claim_key": str(bound.get("claim_key") or ""),
        "computation_ref_id": computation_ref_key(refs[0]),
        "plan_id": str(bound.get("plan_id") or ""),
        "plan_version": str(refs[0].get("plan_digest") or "test_plan_digest"),
        "step_id": str(bound.get("step_id") or ""),
        "requirement_ids": sorted(requirement_ids),
        "dataset_versions": sorted(dataset_versions),
        "time_scope": str(measurement.get("time_scope") or ""),
        "population_scope": str(measurement.get("population_scope") or ""),
        "value": measurement.get("value"),
        "unit": str(measurement.get("unit") or ""),
        "direction": direction,
        "allowed_claim_class": str(bound.get("allowed_claim_class") or ""),
    }
    identity["measurement_key"] = measurement_key_for(identity)
    measurement["identity"] = identity
    return bound


def _audit(text, *, evidence=None, **kwargs):
    current_plan_id = kwargs.pop("current_plan_id", "plan_current")
    preserve_legacy_marker = kwargs.pop("preserve_legacy_marker", False)
    records = evidence if evidence is not None else [_evidence()]
    records = [_bind_test_measurement_identity(record) for record in records]
    if not preserve_legacy_marker:
        for record in records:
            identity_measurements = [
                measurement
                for measurement in record.get("measurements") or []
                if isinstance(measurement, dict)
                and isinstance(measurement.get("identity"), dict)
            ]
            if len(identity_measurements) != 1:
                continue
            evidence_id = str(record.get("id") or "")
            measurement_key = str(
                identity_measurements[0]["identity"].get("measurement_key") or ""
            )
            if evidence_id and measurement_key:
                text = text.replace(
                    f"[[evidence:{evidence_id}]]",
                    f"[[evidence:{evidence_id}#{measurement_key}]]",
                )
    if "current_dataset_versions" not in kwargs:
        versions = {
            str(item)
            for record in records
            for item in record.get("dataset_versions") or []
        }
        if versions:
            kwargs["current_dataset_versions"] = sorted(versions)
    requirements = [
        item
        for item in kwargs.pop("analysis_requirements", []) or []
        if isinstance(item, dict)
    ]
    active_requirement_ids = {
        str(item.get("id") or "") for item in requirements
    }
    for record in records:
        for requirement_id in record.get("requirement_ids") or []:
            requirement_id = str(requirement_id)
            if requirement_id and requirement_id not in active_requirement_ids:
                requirements.append({
                    "id": requirement_id,
                    "step_id": str(record.get("step_id") or ""),
                    "name": "test_measurement_identity",
                    "necessity": "required",
                })
                active_requirement_ids.add(requirement_id)
    return build_final_answer_audit(
        text,
        evidence_records=records,
        route_proposals=[],
        cleaning_logs=[],
        current_plan_id=current_plan_id,
        analysis_requirements=requirements,
        **kwargs,
    )


@pytest.fixture
def identity_evidence():
    computation_ref = {
        "contract_version": "computation_ref.v1",
        "session_id": "session_current",
        "turn_id": "turn_current",
        "tool_call_id": "call_revenue",
        "tool_name": "period_compare",
        "output_digest": "sha256:revenue",
        "plan_id": "plan_current",
        "plan_digest": "plan_digest_current",
        "step_id": "step_compare",
        "step_digest": "step_digest_current",
        "dataset_versions": ["dataset_sales_v1"],
        "claim_key": "revenue_change",
        "requirement_ids": ["req_revenue"],
    }
    identity = {
        "contract_version": "measurement_identity.v1",
        "metric_key": "revenue_change",
        "metric_label": "Revenue",
        "metric_aliases": ["Monthly revenue"],
        "claim_key": "revenue_change",
        "computation_ref_id": computation_ref_key(computation_ref),
        "plan_id": "plan_current",
        "plan_version": "plan_digest_current",
        "step_id": "step_compare",
        "requirement_ids": ["req_revenue"],
        "dataset_versions": ["dataset_sales_v1"],
        "time_scope": "2026-05",
        "population_scope": "new users",
        "value": 0.12,
        "unit": "ratio",
        "direction": "increase",
        "allowed_claim_class": "comparison",
    }
    identity["measurement_key"] = measurement_key_for(identity)
    measurement = {
        **_evidence()["measurements"][0],
        "time_scope": "2026-05",
        "direction": "increase",
        "identity": identity,
    }
    record = {
        **_evidence(),
        "contract_version": "evidence_record.v2",
        "dataset_contract_id": "contract_sales_v1",
        "tool_calls": ["call_revenue"],
        "result_summary": "Revenue increased 12% in 2026-05 for new users.",
        "evidence_requirement": "req_revenue",
        "source_tool_call_ids": ["call_revenue"],
        "requirement_ids": ["req_revenue"],
        "dataset_versions": ["dataset_sales_v1"],
        "computation_refs": [computation_ref],
        "provenance_status": "bound",
        "verification_level": "structured_checked",
        "allowed_claim_class": "comparison",
        "measurements": [measurement],
    }
    validation = validate_evidence_record(
        record,
        current_plan_id="plan_current",
        require_measurement_identity=True,
    )
    assert validation.ok, (validation.error_type, validation.message)
    return validation.record


@pytest.fixture
def unbound_projected_evidence(tmp_path):
    from tests.fixtures.measurement_identity import (
        DATASET_VERSION,
        PLAN_DIGEST,
        PLAN_ID,
        SESSION_ID,
        STEP_DIGEST,
        STEP_ID,
        build_projection_context,
        project_real_correlation,
    )

    context = build_projection_context(tmp_path)
    capability = {
        "capability_id": "analysis.correlation",
        "category": "relationship",
        "evidence_fields": [
            "measurements.value",
            "allowed_claim_class",
        ],
    }
    output = {
        "summary": "Revenue result 12; profit result 7.",
        "data": {
            "measurements": [
                {"metric": "revenue", "value": 12.0, "unit": "CNY"},
                {"definition": "profit result", "value": 7.0, "unit": "CNY"},
            ],
            "allowed_claim_class": "numeric",
        },
    }
    result = project_real_correlation(
        context,
        output=output,
        capability=capability,
    )
    assert result.projected is True
    return {
        "record": result.record,
        "sessions_root": context.sessions_root,
        "current_session_id": SESSION_ID,
        "current_plan_id": PLAN_ID,
        "current_plan_digest": PLAN_DIGEST,
        "current_step_digests": {STEP_ID: STEP_DIGEST},
        "current_dataset_versions": [DATASET_VERSION],
        "analysis_requirements": [{
            "id": "req_corr_effect",
            "step_id": STEP_ID,
            "name": "correlation",
            "necessity": "required",
        }],
    }


def _identity_audit(text, evidence, **kwargs):
    return _audit(
        text,
        evidence=[evidence],
        current_dataset_versions=["dataset_sales_v1"],
        current_plan_digest="plan_digest_current",
        current_step_digests={"step_compare": "step_digest_current"},
        analysis_requirements=[{
            "id": "req_revenue",
            "step_id": "step_compare",
            "name": "metric_delta",
            "necessity": "required",
        }],
        **kwargs,
    )


def _auto_bind_evidence(**overrides):
    measurement = dict(_evidence()["measurements"][0])
    measurement.update({
        "direction": "increase",
        "time_scope": "2026-05",
    })
    record = _evidence(
        allowed_claim_class="comparison",
        dataset_versions=["dataset_sales_v1"],
        measurements=[measurement],
    )
    record.update(overrides)
    return record


def _audit_with_exact_marker(identity_evidence, *, measurement_binding_mode):
    measurement_key = identity_evidence["measurements"][0]["identity"][
        "measurement_key"
    ]
    return _audit(
        "Revenue increased 12% in 2026-05 for new users "
        f"[[evidence:{identity_evidence['id']}#{measurement_key}]].\n"
        "Limitation: descriptive comparison only.",
        evidence=[identity_evidence],
        current_dataset_versions=["dataset_sales_v1"],
        current_plan_digest="plan_digest_current",
        current_step_digests={"step_compare": "step_digest_current"},
        analysis_requirements=[{
            "id": "req_revenue",
            "step_id": "step_compare",
            "name": "metric_delta",
            "necessity": "required",
        }],
        measurement_binding_mode=measurement_binding_mode,
    )


def test_exact_alias_expands_to_full_measurement_marker(identity_evidence):
    key = identity_evidence["measurements"][0]["identity"]["measurement_key"]
    expanded = expand_evidence_alias_markers(
        "Revenue increased 12% [[evidence:ae01#am01]].",
        (("ae01", "am01", identity_evidence["id"], key),),
    )

    assert expanded == (
        "Revenue increased 12% "
        f"[[evidence:{identity_evidence['id']}#{key}]]."
    )


def test_unknown_or_stale_alias_is_not_expanded():
    source = "Revenue increased 12% [[evidence:ae99#am99]]."

    assert expand_evidence_alias_markers(source, ()) == source


def test_alias_cannot_cross_bind_equal_value_metric(identity_evidence):
    key = identity_evidence["measurements"][0]["identity"]["measurement_key"]
    expanded = expand_evidence_alias_markers(
        "Profit increased 12% [[evidence:ae01#am01]].",
        (("ae01", "am01", identity_evidence["id"], key),),
    )

    audit = _identity_audit(expanded, identity_evidence)

    assert audit["status"] == "blocked"
    assert "measurement_metric_mismatch" in audit["claim_checks"][0]["reason_codes"]


def test_soft_mode_downgrades_exact_markerless_candidate(identity_evidence):
    audit = _audit(
        "Revenue increased 12% in 2026-05 for new users.\n"
        "Limitation: descriptive comparison only.",
        evidence=[identity_evidence],
        current_dataset_versions=["dataset_sales_v1"],
        current_plan_digest="plan_digest_current",
        current_step_digests={"step_compare": "step_digest_current"},
        measurement_binding_mode="soft",
    )

    check = audit["claim_checks"][0]
    assert audit["status"] == "revise"
    assert check["status"] == "downgraded"
    assert check["strength"] == "exploratory"
    assert check["evidence_ids"] == []
    assert check["measurement_key"] is None
    assert "measurement_identity_missing" in check["reason_codes"]


def test_soft_mode_downgrades_current_auto_projected_unbound_measurement(
    unbound_projected_evidence,
):
    bundle = unbound_projected_evidence
    unbound = [
        item
        for item in bundle["record"]["measurements"]
        if item.get("identity_status") == "metric_identity_missing"
    ]
    assert len(unbound) == 1
    audit = _audit(
        "Profit result was 7 CNY.\n"
        "Limitation: server-projected structured computation.",
        evidence=[bundle["record"]],
        sessions_root=bundle["sessions_root"],
        current_session_id=bundle["current_session_id"],
        current_plan_id=bundle["current_plan_id"],
        current_dataset_versions=bundle["current_dataset_versions"],
        current_plan_digest=bundle["current_plan_digest"],
        current_step_digests=bundle["current_step_digests"],
        analysis_requirements=bundle["analysis_requirements"],
        measurement_binding_mode="soft",
    )

    check = audit["claim_checks"][0]
    assert audit["status"] == "revise"
    assert check["status"] == "downgraded"
    assert check["evidence_ids"] == []
    assert check["measurement_key"] is None
    assert "measurement_identity_missing" in check["reason_codes"]


def test_soft_mode_requires_matching_metric_semantics_for_unbound_candidate(
    unbound_projected_evidence,
):
    bundle = unbound_projected_evidence
    audit = _audit(
        "Revenue result was 7 CNY.",
        evidence=[bundle["record"]],
        sessions_root=bundle["sessions_root"],
        current_session_id=bundle["current_session_id"],
        current_plan_id=bundle["current_plan_id"],
        current_dataset_versions=bundle["current_dataset_versions"],
        current_plan_digest=bundle["current_plan_digest"],
        current_step_digests=bundle["current_step_digests"],
        analysis_requirements=bundle["analysis_requirements"],
        measurement_binding_mode="soft",
    )

    assert audit["status"] == "blocked"
    assert (
        "missing_evidence_identity"
        in audit["claim_checks"][0]["reason_codes"]
    )


def test_soft_mode_rejects_model_authored_unbound_origin(identity_evidence):
    evidence = copy.deepcopy(identity_evidence)
    measurement = evidence["measurements"][0]
    measurement.pop("identity")
    measurement["identity_status"] = "metric_identity_missing"
    measurement["projection_origin"] = "model_authored"

    audit = _audit(
        "Revenue increased 12% in 2026-05 for new users.",
        evidence=[evidence],
        current_dataset_versions=["dataset_sales_v1"],
        current_plan_digest="plan_digest_current",
        current_step_digests={"step_compare": "step_digest_current"},
        measurement_binding_mode="soft",
    )

    assert audit["status"] == "blocked"
    assert "missing_evidence_identity" in audit["claim_checks"][0]["reason_codes"]


def test_soft_mode_does_not_publish_uncomputed_number_as_exploratory():
    audit = _audit(
        "Profit increased 99% in 2026-05 for new users.",
        evidence=[],
        current_dataset_versions=["dataset_sales_v1"],
        measurement_binding_mode="soft",
    )

    assert audit["status"] == "blocked"


def test_shadow_mode_records_exact_v2_match_without_authorizing_it(
    identity_evidence,
):
    audit = _audit_with_exact_marker(
        identity_evidence,
        measurement_binding_mode="shadow",
    )

    assert audit["status"] == "revise"
    assert audit["claim_checks"][0]["status"] == "downgraded"
    assert audit["measurement_binding_diagnostics"] == {
        "mode": "shadow",
        "v2_exact_match_count": 1,
        "v2_authorized_count": 0,
        "downgrade_count": 1,
        "contradiction_count": 0,
    }


@pytest.mark.parametrize("mode", ["soft", "enforced"])
def test_authorizing_modes_accept_exact_v2_marker(identity_evidence, mode):
    audit = _audit_with_exact_marker(
        identity_evidence,
        measurement_binding_mode=mode,
    )

    assert audit["status"] == "pass"
    assert audit["claim_checks"][0]["status"] == "passed"
    assert audit["measurement_binding_diagnostics"][
        "v2_authorized_count"
    ] == 1


@pytest.mark.parametrize(
    ("claim_text", "reason_code"),
    [
        (
            "Revenue increased 21% in 2026-05 for new users",
            "numeric_mismatch",
        ),
        (
            "Revenue increased 12 CNY in 2026-05 for new users",
            "unit_mismatch",
        ),
        (
            "Revenue decreased 12% in 2026-05 for new users",
            "direction_mismatch",
        ),
        (
            "Revenue increased 12% in 2026-06 for new users",
            "time_scope_mismatch",
        ),
        (
            "Revenue increased 12% in 2026-05 for existing users",
            "population_scope_mismatch",
        ),
        (
            "Revenue increased 12% with high confidence",
            "confidence_mismatch",
        ),
    ],
)
def test_measurement_diagnostics_count_semantic_contradictions(
    identity_evidence,
    claim_text,
    reason_code,
):
    measurement_key = identity_evidence["measurements"][0]["identity"][
        "measurement_key"
    ]
    audit = _audit(
        f"{claim_text} "
        f"[[evidence:{identity_evidence['id']}#{measurement_key}]].",
        evidence=[identity_evidence],
        current_dataset_versions=["dataset_sales_v1"],
        current_plan_digest="plan_digest_current",
        current_step_digests={"step_compare": "step_digest_current"},
        measurement_binding_mode="soft",
    )

    assert audit["status"] == "blocked"
    assert reason_code in audit["claim_checks"][0]["reason_codes"]
    assert audit["measurement_binding_diagnostics"]["contradiction_count"] == 1


def test_enforced_mode_rejects_markerless_exact_candidate(identity_evidence):
    audit = _audit(
        "Revenue increased 12% in 2026-05 for new users.",
        evidence=[identity_evidence],
        current_dataset_versions=["dataset_sales_v1"],
        current_plan_digest="plan_digest_current",
        current_step_digests={"step_compare": "step_digest_current"},
        measurement_binding_mode="enforced",
    )

    assert audit["status"] == "blocked"
    assert (
        "measurement_identity_missing"
        in audit["claim_checks"][0]["reason_codes"]
    )


def test_extractor_classifies_claims_and_extracts_semantics_and_markers():
    text = (
        "Revenue increased 12% in 2026-05 for new users [[evidence:ev_revenue]].\n"
        "We recommend expanding the campaign [[evidence:ev_recommendation]]."
    )

    claims = extract_material_claims(text)

    assert [claim["claim_type"] for claim in claims] == ["comparison", "recommendation"]
    assert claims[0]["quantities"] == [{"raw": "12%", "value": 12.0, "unit": "%"}]
    assert claims[0]["direction"] == "increase"
    assert claims[0]["time_scope"] == "2026-05"
    assert claims[0]["population_scope"] == "new users"
    assert claims[0]["evidence_ids"] == ["ev_revenue"]
    assert claims[0]["confidence_assertion"] == ""
    assert all(claim["material"] for claim in claims)


def test_extractor_retains_measurement_grain_reference():
    claims = extract_material_claims(
        "Revenue increased 12% "
        "[[evidence:ev_revenue#m_revenue_change]]."
    )

    assert claims[0]["evidence_refs"] == [{
        "evidence_id": "ev_revenue",
        "measurement_key": "m_revenue_change",
    }]
    assert claims[0]["evidence_ids"] == ["ev_revenue"]
    assert "[[evidence:" not in claims[0]["text"]


def test_extractor_does_not_treat_markdown_structure_numbers_as_measurements():
    claims = extract_material_claims(
        "## 1️⃣ 数据质量检查\n"
        "1. 建议先清理重复记录。\n"
        "- 平均收入为 514 元。"
    )

    assert claims[0]["text"] == "数据质量检查"
    assert claims[0]["material"] is False
    assert claims[0]["quantities"] == []
    assert claims[1]["claim_type"] == "recommendation"
    assert claims[1]["quantities"] == []
    assert claims[2]["quantities"] == [
        {"raw": "514 元", "value": 514.0, "unit": "元"},
    ]


def test_extractor_treats_recommendation_section_heading_as_structure():
    claims = extract_material_claims(
        "## 六、行动建议\n"
        "建议补充时间字段并通过 A/B 测试验证策略效果。"
    )

    assert claims[0]["text"] == "六、行动建议"
    assert claims[0]["claim_type"] == "recommendation"
    assert claims[0]["material"] is False
    assert claims[0]["requires_evidence"] is False
    assert claims[1]["claim_type"] == "recommendation"
    assert claims[1]["material"] is True
    assert claims[1]["requires_evidence"] is True


def test_extractor_recognizes_row_and_count_units():
    claims = extract_material_claims(
        "revenue 缺失 3 行。\nduplicates count is 5 rows."
    )

    assert claims[0]["quantities"] == [
        {"raw": "3 行", "value": 3.0, "unit": "行"},
    ]
    assert claims[1]["quantities"] == [
        {"raw": "5 rows", "value": 5.0, "unit": "rows"},
    ]


def test_exact_measurement_marker_verifies_revenue_claim(identity_evidence):
    measurement_key = identity_evidence["measurements"][0]["identity"][
        "measurement_key"
    ]
    audit = _identity_audit(
        "Revenue increased 12% in 2026-05 for new users "
        f"[[evidence:{identity_evidence['id']}#{measurement_key}]].\n"
        "Limitation: descriptive comparison only.",
        identity_evidence,
        preserve_legacy_marker=True,
    )

    assert audit["status"] == "pass"
    assert audit["claim_checks"][0]["status"] == "passed"
    assert audit["claim_checks"][0]["measurement_key"] == measurement_key


def test_revenue_measurement_marker_cannot_verify_profit_claim(identity_evidence):
    measurement_key = identity_evidence["measurements"][0]["identity"][
        "measurement_key"
    ]
    audit = _identity_audit(
        "Profit increased 12% in 2026-05 for new users "
        f"[[evidence:{identity_evidence['id']}#{measurement_key}]].",
        identity_evidence,
    )

    assert audit["status"] == "blocked"
    assert (
        "measurement_metric_mismatch"
        in audit["claim_checks"][0]["reason_codes"]
    )


def test_wrong_measurement_key_is_not_resolved(identity_evidence):
    audit = _identity_audit(
        "Revenue increased 12% in 2026-05 for new users "
        f"[[evidence:{identity_evidence['id']}#m_wrong]].",
        identity_evidence,
    )

    assert audit["status"] == "blocked"
    assert "measurement_not_found" in audit["claim_checks"][0]["reason_codes"]


def test_direct_verifier_rejects_profit_claim_for_revenue_measurement(
    identity_evidence,
):
    measurement_key = identity_evidence["measurements"][0]["identity"][
        "measurement_key"
    ]
    report = verify_analysis_claims(
        claims=[{
            "id": "claim_profit",
            "claim": "Profit increased 12% in 2026-05 for new users.",
            "claim_type": "comparison",
            "material": True,
            "requires_evidence": True,
            "quantities": [{"raw": "12%", "value": 12.0, "unit": "%"}],
            "direction": "increase",
            "time_scope": "2026-05",
            "population_scope": "new users",
            "evidence_ids": [identity_evidence["id"]],
            "evidence_refs": [{
                "evidence_id": identity_evidence["id"],
                "measurement_key": measurement_key,
            }],
        }],
        evidence_records=[identity_evidence],
        route_proposals=[],
        cleaning_logs=[],
        current_plan_id="plan_current",
        current_dataset_versions=["dataset_sales_v1"],
        current_plan_digest="plan_digest_current",
        current_step_digests={"step_compare": "step_digest_current"},
        analysis_requirements=[{
            "id": "req_revenue",
            "step_id": "step_compare",
            "name": "metric_delta",
            "necessity": "required",
        }],
        require_explicit_evidence_ids=True,
        strict_claim_semantics=True,
    )

    assert report["overall_status"] == "fail"
    assert (
        "measurement_metric_mismatch"
        in report["claim_checks"][0]["reason_codes"]
    )


def test_measurement_reference_cannot_conflict_with_legacy_evidence_id(
    identity_evidence,
):
    measurement_key = identity_evidence["measurements"][0]["identity"][
        "measurement_key"
    ]
    report = verify_analysis_claims(
        claims=[{
            "id": "claim_conflicting_refs",
            "claim": "Revenue increased 12% in 2026-05 for new users.",
            "claim_type": "comparison",
            "material": True,
            "requires_evidence": True,
            "quantities": [{"raw": "12%", "value": 12.0, "unit": "%"}],
            "direction": "increase",
            "time_scope": "2026-05",
            "population_scope": "new users",
            "evidence_id": "ev_other",
            "evidence_refs": [{
                "evidence_id": identity_evidence["id"],
                "measurement_key": measurement_key,
            }],
        }],
        evidence_records=[identity_evidence, _evidence(id="ev_other")],
        route_proposals=[],
        cleaning_logs=[],
        current_plan_id="plan_current",
        current_dataset_versions=["dataset_sales_v1"],
        current_plan_digest="plan_digest_current",
        current_step_digests={"step_compare": "step_digest_current"},
        analysis_requirements=[{
            "id": "req_revenue",
            "step_id": "step_compare",
            "name": "metric_delta",
            "necessity": "required",
        }],
        require_explicit_evidence_ids=True,
        strict_claim_semantics=True,
    )

    assert report["overall_status"] == "fail"
    assert "measurement_ambiguous" in report["claim_checks"][0]["reason_codes"]


def test_self_consistent_rekeyed_metric_identity_is_rejected(identity_evidence):
    evidence = copy.deepcopy(identity_evidence)
    identity = evidence["measurements"][0]["identity"]
    identity["metric_key"] = "profit_change"
    identity["metric_label"] = "Profit"
    identity["metric_aliases"] = ["Monthly profit"]
    identity["measurement_key"] = measurement_key_for(identity)

    audit = _identity_audit(
        "Profit increased 12% in 2026-05 for new users "
        f"[[evidence:{evidence['id']}#{identity['measurement_key']}]].",
        evidence,
    )

    assert audit["status"] == "blocked"
    assert (
        "measurement_metric_mismatch"
        in audit["claim_checks"][0]["reason_codes"]
    )


def test_structured_metric_suffix_cannot_rekey_revenue_as_profit(
    identity_evidence,
):
    evidence = copy.deepcopy(identity_evidence)
    identity = evidence["measurements"][0]["identity"]
    identity["metric_key"] = "revenue_change::profit_change"
    identity["metric_label"] = "Profit"
    identity["metric_aliases"] = ["Monthly profit"]
    identity["measurement_key"] = measurement_key_for(identity)

    audit = _identity_audit(
        "Profit increased 12% in 2026-05 for new users "
        f"[[evidence:{evidence['id']}#{identity['measurement_key']}]].\n"
        "Limitation: descriptive comparison only.",
        evidence,
    )

    assert audit["status"] == "blocked"
    assert (
        "measurement_metric_mismatch"
        in audit["claim_checks"][0]["reason_codes"]
    )


def test_legitimate_structured_metric_context_suffix_still_verifies(
    identity_evidence,
):
    evidence = copy.deepcopy(identity_evidence)
    measurement = evidence["measurements"][0]
    measurement["metric"] = "pairs.correlation"
    identity = measurement["identity"]
    identity["metric_key"] = "pairs.correlation::revenue|cost"
    identity["metric_label"] = "revenue cost correlation"
    identity["metric_aliases"] = ["cost revenue correlation"]
    identity["allowed_claim_class"] = "association"
    evidence["allowed_claim_class"] = "association"
    identity["measurement_key"] = measurement_key_for(identity)

    audit = _identity_audit(
        "Revenue cost correlation was 12% in 2026-05 for new users "
        f"[[evidence:{evidence['id']}#{identity['measurement_key']}]].\n"
        "Limitation: descriptive association only.",
        evidence,
    )

    assert audit["status"] == "pass"
    assert audit["claim_checks"][0]["status"] == "passed"


def test_selected_measurement_ignores_unrelated_record_level_effect(
    identity_evidence,
):
    evidence = copy.deepcopy(identity_evidence)
    evidence["statistical_support"] = {
        "effect_estimate": {"value": 0.21, "unit": "ratio"},
        "confidence_interval": {
            "level": 0.95,
            "lower": 0.20,
            "upper": 0.22,
            "unit": "ratio",
        },
        "test": {"p_value": 0.21},
    }
    measurement_key = evidence["measurements"][0]["identity"]["measurement_key"]

    audit = _identity_audit(
        "Revenue increased 21% in 2026-05 for new users "
        f"[[evidence:{evidence['id']}#{measurement_key}]].\n"
        "Limitation: descriptive comparison only.",
        evidence,
    )

    assert audit["status"] == "blocked"
    assert "numeric_mismatch" in audit["claim_checks"][0]["reason_codes"]


@pytest.mark.parametrize(
    ("field", "value", "reason_code"),
    [
        ("claim_key", "profit_change", "measurement_claim_key_mismatch"),
        ("plan_id", "plan_other", "measurement_marker_invalid"),
        ("plan_version", "plan_digest_other", "measurement_marker_invalid"),
        ("step_id", "step_other", "measurement_marker_invalid"),
        ("requirement_ids", ["req_other"], "measurement_claim_key_mismatch"),
        (
            "dataset_versions",
            ["dataset_sales_v0"],
            "measurement_dataset_version_mismatch",
        ),
        ("computation_ref_id", "cr_other", "measurement_marker_invalid"),
        ("value", 0.21, "numeric_mismatch"),
        ("unit", "CNY", "unit_mismatch"),
        ("direction", "decrease", "direction_mismatch"),
        ("time_scope", "2026-06", "measurement_scope_mismatch"),
        ("population_scope", "existing users", "measurement_scope_mismatch"),
    ],
)
def test_self_consistent_identity_mutation_is_independently_rejected(
    identity_evidence,
    field,
    value,
    reason_code,
):
    evidence = copy.deepcopy(identity_evidence)
    identity = evidence["measurements"][0]["identity"]
    identity[field] = value
    identity["measurement_key"] = measurement_key_for(identity)

    audit = _identity_audit(
        "Revenue increased 12% in 2026-05 for new users "
        f"[[evidence:{evidence['id']}#{identity['measurement_key']}]].",
        evidence,
    )

    assert audit["status"] == "blocked"
    assert reason_code in audit["claim_checks"][0]["reason_codes"]


@pytest.mark.parametrize(
    ("claim", "reason_code"),
    [
        (
            "Campaign caused Revenue to increase 12% in 2026-05 for new users",
            "causal_claim_not_identified",
        ),
        (
            "Revenue was associated with a 12% increase in 2026-05 for new users",
            "verification_level_overclaim",
        ),
    ],
)
def test_claim_class_cannot_exceed_measurement_permission(
    identity_evidence,
    claim,
    reason_code,
):
    measurement_key = identity_evidence["measurements"][0]["identity"][
        "measurement_key"
    ]
    audit = _identity_audit(
        f"{claim} "
        f"[[evidence:{identity_evidence['id']}#{measurement_key}]].",
        identity_evidence,
    )

    assert audit["status"] == "blocked"
    assert reason_code in audit["claim_checks"][0]["reason_codes"]


def test_selected_measurement_cannot_use_unrelated_measurement_value(
    identity_evidence,
):
    evidence = copy.deepcopy(identity_evidence)
    profit = copy.deepcopy(evidence["measurements"][0])
    profit["metric"] = "profit_change"
    profit["definition"] = "May profit change versus April"
    profit["value"] = 0.21
    profit_identity = profit["identity"]
    profit_identity["metric_key"] = "profit_change"
    profit_identity["metric_label"] = "Profit"
    profit_identity["metric_aliases"] = ["Monthly profit"]
    profit_identity["value"] = 0.21
    profit_identity["measurement_key"] = measurement_key_for(profit_identity)
    evidence["measurements"].append(profit)
    revenue_key = evidence["measurements"][0]["identity"]["measurement_key"]

    audit = _identity_audit(
        "Revenue increased 21% in 2026-05 for new users "
        f"[[evidence:{evidence['id']}#{revenue_key}]].",
        evidence,
    )

    assert audit["status"] == "blocked"
    assert "numeric_mismatch" in audit["claim_checks"][0]["reason_codes"]


def test_duplicate_measurement_key_is_ambiguous(identity_evidence):
    evidence = copy.deepcopy(identity_evidence)
    evidence["measurements"].append(copy.deepcopy(evidence["measurements"][0]))
    measurement_key = evidence["measurements"][0]["identity"]["measurement_key"]

    audit = _identity_audit(
        "Revenue increased 12% in 2026-05 for new users "
        f"[[evidence:{evidence['id']}#{measurement_key}]].",
        evidence,
    )

    assert audit["status"] == "blocked"
    assert "measurement_ambiguous" in audit["claim_checks"][0]["reason_codes"]


def test_enforced_legacy_record_marker_never_authorizes_by_number_first(
    identity_evidence,
):
    audit = _identity_audit(
        "Revenue increased 12% in 2026-05 for new users "
        f"[[evidence:{identity_evidence['id']}]].\n"
        "Limitation: descriptive comparison only.",
        identity_evidence,
        preserve_legacy_marker=True,
    )

    assert audit["status"] == "blocked"
    assert audit["claim_checks"][0]["measurement_key"] is None
    assert (
        "measurement_identity_missing"
        in audit["claim_checks"][0]["reason_codes"]
    )


def test_marker_stripping_preserves_markdown_structure():
    draft = (
        "# Conclusion\n\n"
        "| Metric | Change |\n|---|---|\n"
        "| Revenue | 12% [[evidence:ev_1#m_1]] |\n"
    )

    public = strip_internal_evidence_markers(draft)

    assert public.startswith("# Conclusion")
    assert "| Revenue | 12% |" in public
    assert "[[evidence:" not in public


def test_marker_stripping_preserves_hard_breaks_and_indentation():
    draft = "Summary  \n[[evidence:ev_1#m_1]]\n    nested detail\n"

    public = strip_internal_evidence_markers(draft)

    assert public == "Summary  \n\n    nested detail\n"


def test_marker_stripping_separates_adjacent_prose_and_handles_marker_only_text():
    assert strip_internal_evidence_markers(
        "Alpha[[evidence:ev_1#m_1]]Beta"
    ) == "Alpha Beta"
    assert strip_internal_evidence_markers("[[evidence:ev_1#m_1]]") == ""


def test_marker_stripping_preserves_trailing_whitespace_before_terminal_marker():
    assert strip_internal_evidence_markers(
        "Summary  [[evidence:ev_1#m_1]]"
    ) == "Summary  "


def test_marker_stripping_normalizes_only_marker_created_gap_before_punctuation():
    assert strip_internal_evidence_markers(
        "Revenue [[evidence:ev_1#m_1]] ."
    ) == "Revenue ."


def test_marker_stripping_preserves_marker_left_list_indentation_before_punctuation():
    assert strip_internal_evidence_markers(
        "-   [[evidence:ev_1#m_1]] ."
    ) == "-   ."


def test_marker_stripping_separates_markdown_tokens_across_a_marker():
    assert strip_internal_evidence_markers(
        "**Revenue**[[evidence:ev_1#m_1]]**increased**"
    ) == "**Revenue** **increased**"


def test_marker_stripping_separates_prose_across_adjacent_marker_run():
    assert strip_internal_evidence_markers(
        "Alpha[[evidence:ev_1#m_1]][[evidence:ev_2#m_2]]Beta"
    ) == "Alpha Beta"


def test_fuzzy_text_similarity_without_exact_marker_cannot_authorize_publication():
    audit = _audit("Revenue increased 12% in 2026-05 for new users.")

    assert audit["contract_version"] == "final_answer_audit.v1"
    assert audit["status"] == "blocked"
    check = audit["claim_checks"][0]
    assert "measurement_identity_missing" in check["reason_codes"]
    assert check["safe_action"]["action"] == "remove_or_downgrade_claim"


def test_same_value_revenue_evidence_cannot_verify_profit_claim():
    audit = _audit(
        "Profit increased 12% in 2026-05 for new users.\n"
        "Limitation: this is a descriptive comparison only.",
        evidence=[_auto_bind_evidence()],
        current_dataset_versions=["dataset_sales_v1"],
    )

    assert audit["status"] == "blocked"
    assert audit["claims"][0]["evidence_ids"] == []
    assert "measurement_identity_missing" in audit["claim_checks"][0]["reason_codes"]


def test_markerless_same_value_claim_is_not_automatically_verified():
    audit = _audit(
        "Revenue increased 12% in 2026-05 for new users.",
        evidence=[_auto_bind_evidence()],
        current_dataset_versions=["dataset_sales_v1"],
    )

    assert audit["status"] != "pass"
    assert audit["claims"][0]["evidence_ids"] == []


def test_final_audit_does_not_bind_when_both_claim_context_and_evidence_lack_plan():
    audit = _audit(
        "Revenue increased 12% in 2026-05 for new users.",
        evidence=[_auto_bind_evidence(plan_id="")],
        current_plan_id="",
        current_dataset_versions=["dataset_sales_v1"],
    )

    assert audit["status"] == "blocked"
    assert audit["claims"][0]["evidence_ids"] == []
    assert "measurement_identity_missing" in audit["claim_checks"][0]["reason_codes"]


@pytest.mark.parametrize(
    "evidence",
    [
        _auto_bind_evidence(plan_id="plan_old"),
        _auto_bind_evidence(plan_id="PLAN_CURRENT"),
        _auto_bind_evidence(dataset_versions=["dataset_sales_v0"]),
        _auto_bind_evidence(dataset_versions=["DATASET_SALES_V1"]),
        _auto_bind_evidence(
            dataset_versions=["dataset_sales_v1", "dataset_other_v1"],
        ),
    ],
    ids=[
        "wrong-plan",
        "case-changed-plan",
        "wrong-version",
        "case-changed-version",
        "non-exact-version-set",
    ],
)
def test_final_audit_does_not_bind_wrong_plan_or_dataset_version(evidence):
    audit = _audit(
        "Revenue increased 12% in 2026-05 for new users.",
        evidence=[evidence],
        current_dataset_versions=["dataset_sales_v1"],
    )

    assert audit["status"] == "blocked"
    assert audit["claims"][0]["evidence_ids"] == []
    assert "measurement_identity_missing" in audit["claim_checks"][0]["reason_codes"]


@pytest.mark.parametrize(
    "evidence",
    [
        [],
        [_auto_bind_evidence(id="ev_1"), _auto_bind_evidence(id="ev_2")],
    ],
    ids=["zero-match", "multiple-matches"],
)
def test_final_audit_does_not_guess_on_zero_or_multiple_exact_matches(evidence):
    audit = _audit(
        "Revenue increased 12% in 2026-05 for new users.",
        evidence=evidence,
        current_dataset_versions=["dataset_sales_v1"],
    )

    assert audit["status"] == "blocked"
    assert audit["claims"][0]["evidence_ids"] == []
    assert "measurement_identity_missing" in audit["claim_checks"][0]["reason_codes"]


def test_final_audit_does_not_bind_a_multi_quantity_claim():
    audit = _audit(
        "Revenue increased 12% and 13% in 2026-05 for new users.",
        evidence=[_auto_bind_evidence()],
        current_dataset_versions=["dataset_sales_v1"],
    )

    assert len(audit["claims"][0]["quantities"]) == 2
    assert audit["claims"][0]["evidence_ids"] == []
    assert "measurement_identity_missing" in audit["claim_checks"][0]["reason_codes"]


@pytest.mark.parametrize(
    ("draft", "evidence_overrides", "claim_field"),
    [
        (
            "Revenue was 12% in 2026-05 for new users.",
            {"allowed_claim_class": "numeric"},
            "direction",
        ),
        (
            "Revenue increased 12 in 2026-05 for new users.",
            {},
            "units",
        ),
        (
            "Revenue increased 12% for new users.",
            {},
            "time_scope",
        ),
        (
            "Revenue increased 12% in 2026-05.",
            {},
            "population_scope",
        ),
    ],
    ids=["direction", "unit", "time-scope", "population-scope"],
)
def test_final_audit_fails_closed_when_claim_identity_is_incomplete(
    draft,
    evidence_overrides,
    claim_field,
):
    audit = _audit(
        draft,
        evidence=[_auto_bind_evidence(**evidence_overrides)],
        current_dataset_versions=["dataset_sales_v1"],
    )

    assert not audit["claims"][0][claim_field]
    assert audit["claims"][0]["evidence_ids"] == []
    assert "measurement_identity_missing" in audit["claim_checks"][0]["reason_codes"]


def test_final_audit_does_not_choose_one_measurement_from_multi_measurement_evidence():
    measurement = dict(_auto_bind_evidence()["measurements"][0])
    audit = _audit(
        "Revenue increased 12% in 2026-05 for new users.",
        evidence=[_auto_bind_evidence(measurements=[measurement, dict(measurement)])],
        current_dataset_versions=["dataset_sales_v1"],
    )

    assert audit["claims"][0]["evidence_ids"] == []
    assert "measurement_identity_missing" in audit["claim_checks"][0]["reason_codes"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"allowed_claim_class": ""},
        {"dataset_versions": []},
        {"measurements": [{
            **_auto_bind_evidence()["measurements"][0],
            "direction": "",
        }]},
        {"measurements": [{
            **_auto_bind_evidence()["measurements"][0],
            "unit": "",
        }]},
        {"measurements": [{
            **_auto_bind_evidence()["measurements"][0],
            "time_scope": "",
        }]},
        {"measurements": [{
            **_auto_bind_evidence()["measurements"][0],
            "population_scope": "",
        }]},
    ],
    ids=[
        "claim-class",
        "dataset-version-scope",
        "direction",
        "unit",
        "time-scope",
        "population-scope",
    ],
)
def test_final_audit_fails_closed_when_evidence_identity_is_incomplete(overrides):
    audit = _audit(
        "Revenue increased 12% in 2026-05 for new users.",
        evidence=[_auto_bind_evidence(**overrides)],
        current_dataset_versions=["dataset_sales_v1"],
    )

    assert audit["claims"][0]["evidence_ids"] == []
    assert "measurement_identity_missing" in audit["claim_checks"][0]["reason_codes"]


@pytest.mark.parametrize(
    ("draft", "reason_code"),
    [
        ("Revenue increased 21% in 2026-05 for new users [[evidence:ev_revenue]].", "numeric_mismatch"),
        ("Revenue decreased 12% in 2026-05 for new users [[evidence:ev_revenue]].", "direction_mismatch"),
        ("Revenue increased 12 CNY in 2026-05 for new users [[evidence:ev_revenue]].", "unit_mismatch"),
        ("Revenue increased 12 percentage points in 2026-05 for new users [[evidence:ev_revenue]].", "unit_mismatch"),
        ("Revenue increased 12% in 2026-06 for new users [[evidence:ev_revenue]].", "time_scope_mismatch"),
        ("Revenue increased 12% in 2026-05 for existing users [[evidence:ev_revenue]].", "population_scope_mismatch"),
        ("Revenue increased 12% with high confidence [[evidence:ev_revenue]].", "confidence_mismatch"),
    ],
)
def test_material_semantic_mismatches_block(draft, reason_code):
    audit = _audit(draft)

    assert audit["status"] == "blocked"
    assert reason_code in audit["claim_checks"][0]["reason_codes"]


def test_later_revision_findings_cannot_weaken_a_deterministic_block():
    audit = _audit(
        "Revenue increased 21% [[evidence:ev_revenue]].",
        evidence=[_evidence(sample_size=None, method_detail="")],
    )

    assert audit["status"] == "blocked"
    assert audit["claim_checks"][0]["status"] == "failed"
    assert "numeric_mismatch" in audit["claim_checks"][0]["reason_codes"]


def test_legacy_direct_verifier_accepts_structured_confidence_interval_values():
    report = verify_analysis_claims(
        claims=[{
            "id": "claim_legacy_interval",
            "claim": (
                "Revenue increased 12% (95% CI 5% to 19%) "
                "in 2026-05 for new users."
            ),
            "claim_type": "comparison",
            "material": True,
            "requires_evidence": True,
            "quantities": [
                {"raw": "12%", "value": 12.0, "unit": "%"},
                {"raw": "95%", "value": 95.0, "unit": "%"},
                {"raw": "5%", "value": 5.0, "unit": "%"},
                {"raw": "19%", "value": 19.0, "unit": "%"},
            ],
            "direction": "increase",
            "time_scope": "2026-05",
            "population_scope": "new users",
            "evidence_id": "ev_revenue",
        }],
        evidence_records=[_evidence(statistical_support={
            "effect_estimate": {"value": 0.12, "unit": "ratio"},
            "confidence_interval": {
                "level": 0.95,
                "lower": 0.05,
                "upper": 0.19,
                "unit": "ratio",
            },
        })],
        route_proposals=[],
        cleaning_logs=[],
        current_plan_id="plan_current",
        strict_claim_semantics=True,
    )

    assert report["overall_status"] == "pass"


def test_current_plan_identity_is_required_even_with_an_exact_marker():
    audit = _audit(
        "Revenue increased 12% [[evidence:ev_old]].",
        evidence=[_evidence(id="ev_old", plan_id="plan_old")],
    )

    assert audit["status"] == "blocked"
    assert "evidence_outside_current_plan" in audit["claim_checks"][0]["reason_codes"]


def test_missing_current_dataset_identity_blocks_identity_bound_evidence():
    draft = (
        "Revenue increased 12% in 2026-05 for new users [[evidence:ev_revenue]].\n"
        "Limitation: this is a descriptive comparison only."
    )
    version_bound = _audit(
        draft,
        evidence=[_evidence(computation_refs=[{
            "tool_call_id": "call_revenue",
            "dataset_versions": ["dataset_sales_v1"],
        }])],
        current_dataset_versions=None,
    )
    non_versioned = _audit(
        draft,
        evidence=[_evidence(computation_refs=[])],
        current_dataset_versions=None,
    )

    assert version_bound["status"] == "blocked"
    assert (
        "current_dataset_identity_unavailable"
        in version_bound["claim_checks"][0]["reason_codes"]
    )
    assert non_versioned["status"] == "blocked"
    assert (
        "current_dataset_identity_unavailable"
        in non_versioned["claim_checks"][0]["reason_codes"]
    )


def test_unmet_block_claim_requirement_blocks_and_supplies_safe_action():
    requirements = compile_analysis_requirements(
        plan={
            "id": "plan_current",
            "goal": "estimate a population difference",
            "method_plan": [{
                "step_id": "step_compare",
                "goal": "estimate a population difference",
                "node_type": "analysis",
                "required_capability": "analysis.group_compare",
                "claim_type": "inferential",
                "sampling_structure": "independent_groups",
                "evidence_requirements": ["confidence_interval"],
            }],
        },
        route=None,
        playbook=None,
        dataset_contracts=[],
        user_intent="estimate a population difference",
    )
    audit = _audit(
        "Revenue increased 12% in 2026-05 for new users [[evidence:ev_revenue]].",
        analysis_requirements=requirements,
    )

    assert audit["status"] == "blocked"
    check = audit["claim_checks"][0]
    assert "unmet_block_claim_requirement" in check["reason_codes"]
    assert check["safe_action"]["action"] == "remove_or_downgrade_claim"


@pytest.mark.parametrize("diagnostic", ["年季节性不可估计。", "年季节性无法估计。"])
def test_not_estimable_seasonality_blocks_only_the_positive_seasonality_claim(
    diagnostic,
):
    requirements = compile_analysis_requirements(
        plan={
            "id": "plan_current",
            "goal": "assess annual seasonality",
            "method_plan": [{
                "step_id": "step_seasonality",
                "goal": "assess annual seasonality",
                "node_type": "analysis",
                "required_capability": "analysis.time_series",
                "claim_type": "seasonality",
                "seasonality_period": "annual",
            }],
        },
        route={"direction": "trend"},
        playbook=None,
        dataset_contracts=[{
            "dataset": "sales",
            "analysis_profiles": {
                "time_series": {
                    "frequency": "monthly",
                    "seasonality": {
                        "annual": {
                            "period_observations": 12,
                            "minimum_complete_cycles": 2,
                            "complete_cycles": 0,
                            "status": "not_estimable",
                            "reason": "Annual seasonality requires 24 monthly observations.",
                        },
                    },
                },
            },
        }],
        user_intent="assess annual seasonality",
    )
    seasonality = next(
        item for item in requirements if item["name"] == "seasonality_estimability"
    )
    evidence = _evidence(
        id="ev_seasonality",
        step_id="step_seasonality",
        claim="Annual seasonality is not estimable from the available history.",
        method="time_series",
        requirement_ids=[seasonality["id"]],
        seasonality_estimability={
            "status": "not_estimable",
            "period": "annual",
            "reason": "Annual seasonality requires 24 monthly observations.",
        },
        measurements=[{
            "metric": "annual_seasonality",
            "definition": "Annual seasonality estimability status.",
            "value": 1.0,
            "unit": "status",
            "grain": "time_series",
            "population_scope": "sales series",
            "time_scope": "available history",
            "method": "time_series",
            "denominator": "not_applicable",
            "limitations": ["Annual seasonality is not estimable."],
            "direction": "",
        }],
    )
    evidence = _bind_test_measurement_identity(evidence)
    measurement_key = evidence["measurements"][0]["identity"]["measurement_key"]

    audit = _audit(
        "The series shows annual seasonality "
        f"[[evidence:ev_seasonality#{measurement_key}]].\n"
        + diagnostic,
        evidence=[evidence],
        analysis_requirements=[seasonality],
    )

    assert audit["status"] == "blocked"
    assert "claim_guard_blocked" in audit["claim_checks"][0]["reason_codes"]
    assert audit["claim_checks"][1]["status"] == "passed"
    assert (
        "diagnostic_without_positive_claim"
        in audit["claim_checks"][1]["reason_codes"]
    )


def test_multiple_record_level_markers_are_measurement_ambiguous():
    requirements = compile_analysis_requirements(
        plan={
            "id": "plan_current",
            "goal": "estimate a population difference",
            "method_plan": [{
                "step_id": "step_compare",
                "goal": "estimate a population difference",
                "node_type": "analysis",
                "required_capability": "analysis.group_compare",
                "claim_type": "inferential",
                "sampling_structure": "independent_groups",
            }],
        },
        route=None,
        playbook=None,
        dataset_contracts=[],
        user_intent="estimate a population difference",
    )
    confidence_interval = next(
        item for item in requirements if item["name"] == "confidence_interval"
    )
    effect = _evidence(
        id="ev_effect",
        requirement_ids=[],
    )
    uncertainty = _evidence(
        id="ev_uncertainty",
        requirement_ids=[confidence_interval["id"]],
        confidence_interval={"level": 0.95, "lower": 0.05, "upper": 0.19},
        assumption_checks=[{
            "name": "method_appropriate_for_design",
            "status": "passed",
            "evidence": "period comparison matches the declared design",
        }],
        measurements=[],
    )

    audit = _audit(
        "Revenue increased 12% in 2026-05 for new users "
        "[[evidence:ev_effect]] [[evidence:ev_uncertainty]].\n"
        "Limitation: this is a descriptive comparison only.",
        evidence=[effect, uncertainty],
        analysis_requirements=[confidence_interval],
    )

    assert audit["status"] == "blocked"
    assert "measurement_ambiguous" in audit["claim_checks"][0]["reason_codes"]


def test_traceable_lineage_cannot_support_independent_correctness_wording():
    audit = _audit(
        "The 12% increase was independently verified as statistically correct "
        "[[evidence:ev_revenue]].",
        evidence=[_evidence(verification_level="traceable")],
    )

    assert audit["status"] == "blocked"
    assert "verification_level_overclaim" in audit["claim_checks"][0]["reason_codes"]


def test_diagnostic_missing_evidence_statement_may_pass_without_marker():
    audit = _audit(
        "The assignment unit is unavailable, so a causal effect cannot be determined.",
        evidence=[],
    )

    assert audit["status"] == "pass"
    assert audit["claim_checks"][0]["status"] == "passed"
    assert audit["claim_checks"][0]["evidence_id"] is None


def test_internal_markers_are_removed_from_public_text():
    draft = "Revenue increased 12% [[evidence:ev_revenue]]."

    assert strip_internal_evidence_markers(draft) == "Revenue increased 12% ."
    assert "evidence:" not in _audit(draft)["public_text"]


def test_missing_limitation_requires_revision_not_publication_pass():
    audit = _audit(
        "Revenue increased 12% in 2026-05 for new users [[evidence:ev_revenue]]."
    )

    assert audit["status"] == "revise"
    assert "missing_limitation" in audit["claim_checks"][0]["reason_codes"]
    assert audit["claim_checks"][0]["safe_action"]["action"] == "revise_with_limitations"


def test_low_confidence_prediction_requires_exploratory_label():
    audit = _audit(
        "Revenue will increase [[evidence:ev_revenue]].\n"
        "Limitation: the forecast is based on a descriptive comparison.",
        evidence=[_evidence(confidence="low")],
    )

    assert audit["status"] == "revise"
    assert "missing_exploratory_label" in audit["claim_checks"][0]["reason_codes"]


def test_optional_llm_critique_cannot_override_deterministic_block():
    audit = _audit(
        "Revenue increased 12%.",
        llm_critique={"status": "pass", "notes": ["Looks clear"]},
    )

    assert audit["status"] == "blocked"
    assert audit["llm_critique"]["status"] == "pass"


def test_runtime_persists_full_audit_and_keeps_only_compact_ref_in_state(tmp_path, monkeypatch):
    state = SimpleNamespace(
        session_id="audit_session",
        analysis_plan={"id": "plan_current", "analysis_requirements": {}},
        evidence_records=[_evidence()],
        route_proposals=[],
        cleaning_logs=[],
        verification_reports=[],
        save=lambda: None,
    )
    monkeypatch.setattr(runtime, "_sessions_root", lambda: tmp_path / "sessions")
    monkeypatch.setattr(runtime, "_active_dataset_versions", lambda: None)

    ref = runtime.audit_final_answer_draft(
        "Revenue increased 12% in 2026-05 for new users [[evidence:ev_revenue]].\n"
        "Limitation: this is a descriptive comparison only.",
        state,
    )

    assert ref["contract_version"] == "final_answer_audit.v1"
    assert ref["status"] == "blocked"
    assert "claim_checks" not in ref
    assert len(ref["artifact_digest"]) == 64
    assert state.verification_reports[-1] == ref
    artifact = json.loads(Path(ref["artifact_path"]).read_text(encoding="utf-8"))
    assert artifact["contract_version"] == "final_answer_audit.v1"
    assert artifact["claim_checks"][0]["evidence_id"] == "ev_revenue"
    assert "missing_evidence_identity" in artifact["claim_checks"][0]["reason_codes"]
    assert "[[evidence:" not in artifact["public_text"]
    assert runtime.hydrate_final_answer_audit_ref(ref) == artifact

    artifact["status"] = "blocked"
    Path(ref["artifact_path"]).write_text(json.dumps(artifact), encoding="utf-8")
    assert runtime.hydrate_final_answer_audit_ref(ref) is None


def test_runtime_expands_current_alias_before_unchanged_audit(tmp_path, monkeypatch):
    from tests.fixtures.measurement_identity import (
        DATASET_VERSION,
        build_projection_context,
        project_real_correlation,
    )

    context = build_projection_context(tmp_path)
    evidence = project_real_correlation(context).record
    key = evidence["measurements"][0]["identity"]["measurement_key"]
    state = SimpleNamespace(
        session_id=context.session_id,
        analysis_plan=context.plan,
        evidence_records=[evidence],
        route_proposals=[],
        cleaning_logs=[],
        verification_reports=[],
        save=lambda: None,
    )
    monkeypatch.setattr(runtime, "_sessions_root", lambda: context.sessions_root)
    monkeypatch.setattr(
        runtime,
        "_active_dataset_versions",
        lambda: [DATASET_VERSION],
    )

    ref = runtime.audit_final_answer_draft(
        "The revenue cost correlation is 0.4 "
        "[[evidence:ae01#am01]].\n"
        "Limitation: this is a descriptive association, not a causal effect.",
        state,
        evidence_aliases=(("ae01", "am01", evidence["id"], key),),
    )
    artifact = json.loads(Path(ref["artifact_path"]).read_text(encoding="utf-8"))

    assert artifact["status"] == "pass", [
        check.get("reason_codes") for check in artifact["claim_checks"]
    ]
    assert artifact["claim_checks"][0]["evidence_id"] == evidence["id"]
    assert artifact["claim_checks"][0]["measurement_key"] == key
    assert "[[evidence:" not in artifact["public_text"]


def test_runtime_rejects_digest_valid_structurally_incomplete_audit(tmp_path):
    artifact = {
        "contract_version": "final_answer_audit.v1",
        "id": "audit_incomplete",
        "status": "pass",
        "public_text": "Revenue increased 12%.",
        "claims": [{
            "id": "claim_revenue",
            "text": "Revenue increased 12%.",
            "claim_type": "comparison",
            "material": True,
        }],
        "claim_checks": [],
    }
    path = tmp_path / "audit_incomplete.json"
    artifact_bytes = json.dumps(artifact).encode("utf-8")
    path.write_bytes(artifact_bytes)
    ref = {
        "contract_version": "final_answer_audit.v1",
        "id": artifact["id"],
        "artifact_path": str(path),
        "artifact_digest": hashlib.sha256(artifact_bytes).hexdigest(),
    }

    assert runtime.hydrate_final_answer_audit_ref(ref) is None


def test_runtime_uses_validated_cached_measurement_binding_mode(
    tmp_path,
    monkeypatch,
):
    from data_agent import config as config_module
    from data_agent.config import AgentConfig

    cached = AgentConfig(
        MEASUREMENT_EVIDENCE_BINDING_MODE="shadow",
        _env_file=None,
    )
    monkeypatch.setattr(config_module, "_config", cached)
    monkeypatch.setattr(runtime, "_sessions_root", lambda: tmp_path / "sessions")
    monkeypatch.setattr(runtime, "_active_dataset_versions", lambda: None)
    state = SimpleNamespace(
        session_id="audit_shadow_config",
        analysis_plan={"id": "plan_current", "analysis_requirements": {}},
        evidence_records=[_evidence()],
        route_proposals=[],
        cleaning_logs=[],
        verification_reports=[],
        save=lambda: None,
    )

    ref = runtime.audit_final_answer_draft(
        "Revenue increased 12% [[evidence:ev_revenue]].",
        state,
    )
    artifact = json.loads(Path(ref["artifact_path"]).read_text(encoding="utf-8"))

    assert artifact["measurement_binding_diagnostics"]["mode"] == "shadow"
