from __future__ import annotations

import copy

import pytest

from data_agent.agent.answer_quality import (
    build_final_answer_audit,
    render_audited_analysis_answer,
)
from data_agent.agent.evidence_contracts import (
    _project_requirement_semantics,
    build_bounded_evidence_catalog,
    measurement_key_for,
)
from data_agent.agent.analysis_requirements import evaluate_requirement_satisfaction
from data_agent.agent.verification import _unmet_block_claim_requirements
from data_agent.agent.execution_control import CompletionDecision
from tests.fixtures.measurement_identity import (
    DATASET_VERSION,
    PLAN_DIGEST,
    PLAN_ID,
    SESSION_ID,
    STEP_DIGEST,
    STEP_ID,
    build_projection_context,
    correlation_output,
    project_real_correlation,
)


@pytest.fixture
def projection_context(tmp_path):
    return build_projection_context(tmp_path)


def _complete_with_limits() -> CompletionDecision:
    return CompletionDecision(
        status="complete_with_limits",
        is_terminal=True,
        supported_claim_class="exploratory_association",
        satisfied_requirement_ids=("req_corr_effect",),
        unmet_requirement_ids=("req_corr_interval",),
        recoverable_requirement_ids=(),
        allow_analysis_continuation=False,
        reason_code="bounded_limitations",
        diagnostics=(),
    )


def _audit_with_marker(
    context,
    evidence: dict,
    *,
    measurement_key: str,
    claim: str = "Revenue cost correlation is 0.4",
) -> dict:
    draft = (
        "# 结论\n\n"
        f"{claim} [[evidence:{evidence['id']}#{measurement_key}]].\n\n"
        "## 局限\n\n"
        "This is an association, not a causal estimate."
    )
    return build_final_answer_audit(
        draft,
        evidence_records=[evidence],
        current_plan_id=PLAN_ID,
        current_dataset_versions=[DATASET_VERSION],
        sessions_root=context.sessions_root,
        current_session_id=SESSION_ID,
        current_plan_digest=PLAN_DIGEST,
        current_step_digests={STEP_ID: STEP_DIGEST},
        analysis_requirements=context.analysis_requirements,
        measurement_binding_mode="soft",
    )


def _check_for_claim(audit: dict, claim: str) -> dict:
    matches = [
        check
        for check in audit["claim_checks"]
        if str(check.get("claim") or "").startswith(claim)
    ]
    assert len(matches) == 1
    return matches[0]


def test_real_computation_projects_and_publishes_exact_measurement(
    projection_context,
):
    projection = project_real_correlation(projection_context)
    evidence = projection.record
    identity = evidence["measurements"][0]["identity"]
    catalog = build_bounded_evidence_catalog([evidence])

    assert identity["measurement_key"] in catalog
    draft = (
        "# 结论\n\n"
        "Revenue cost correlation is 0.4 "
        f"[[evidence:{evidence['id']}#{identity['measurement_key']}]].\n\n"
        "## 局限\n\n"
        "This is an association, not a causal estimate."
    )
    audit = build_final_answer_audit(
        draft,
        evidence_records=[evidence],
        current_plan_id=PLAN_ID,
        current_dataset_versions=[DATASET_VERSION],
        sessions_root=projection_context.sessions_root,
        current_session_id=SESSION_ID,
        current_plan_digest=PLAN_DIGEST,
        current_step_digests={STEP_ID: STEP_DIGEST},
        analysis_requirements=projection_context.analysis_requirements,
        measurement_binding_mode="soft",
    )
    assert audit["status"] == "pass"

    publication = render_audited_analysis_answer(
        draft=draft,
        audit=audit,
        completion=_complete_with_limits(),
        mode="tiered",
    )
    assert "# 结论" in publication.text
    assert "Revenue cost correlation is 0.4" in publication.text
    assert "[[evidence:" not in publication.text


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ("metric_key", "measurement_metric_mismatch"),
        ("claim_key", "measurement_claim_key_mismatch"),
        ("plan_id", "measurement_marker_invalid"),
        ("plan_version", "measurement_marker_invalid"),
        ("step_id", "measurement_marker_invalid"),
        ("requirement_ids", "measurement_claim_key_mismatch"),
        ("dataset_versions", "measurement_dataset_version_mismatch"),
        ("computation_ref_id", "measurement_marker_invalid"),
        ("value", "numeric_mismatch"),
        ("unit", "unit_mismatch"),
        ("direction", "direction_mismatch"),
        ("time_scope", "measurement_scope_mismatch"),
        ("population_scope", "measurement_scope_mismatch"),
    ],
)
def test_tampered_measurement_identity_never_publishes_verified(
    projection_context,
    mutation,
    reason,
):
    evidence = copy.deepcopy(project_real_correlation(projection_context).record)
    identity = evidence["measurements"][0]["identity"]
    changed_values = {
        "dataset_versions": ["stale_v0"],
        "requirement_ids": ["req_wrong"],
        "value": 999,
    }
    identity[mutation] = changed_values.get(mutation, "wrong")
    if mutation == "metric_key":
        identity["metric_label"] = "profit cost correlation"
        identity["metric_aliases"] = [
            "profit cost correlation",
            "cost profit correlation",
        ]
    identity["measurement_key"] = measurement_key_for(identity)

    audit = _audit_with_marker(
        projection_context,
        evidence,
        measurement_key=identity["measurement_key"],
    )

    assert audit["status"] == "blocked"
    assert reason in _check_for_claim(
        audit,
        "Revenue cost correlation is 0.4",
    )["reason_codes"]


def test_same_value_for_different_metric_fails_metric_identity_not_key_lookup(
    projection_context,
):
    evidence = project_real_correlation(projection_context).record
    identity = evidence["measurements"][0]["identity"]

    audit = _audit_with_marker(
        projection_context,
        evidence,
        measurement_key=identity["measurement_key"],
        claim="Profit cost correlation is 0.4",
    )

    assert audit["status"] == "blocked"
    check = _check_for_claim(audit, "Profit cost correlation is 0.4")
    assert "measurement_metric_mismatch" in check["reason_codes"]
    assert "measurement_not_found" not in check["reason_codes"]


def test_real_correlation_pairs_have_unique_variable_bound_identities(
    projection_context,
):
    output = copy.deepcopy(correlation_output())
    output["data"]["pairs"].append(
        {
            "var1": "profit",
            "var2": "cost",
            "correlation": 0.4,
            "effective_sample_size": 100,
            "p_value": 0.001,
        }
    )
    evidence = project_real_correlation(
        projection_context,
        output=output,
    ).record
    identities = [
        item["identity"]
        for item in evidence["measurements"]
        if item["identity"]["metric_key"].startswith("pairs.correlation")
    ]

    assert len(identities) == 2
    assert len({item["measurement_key"] for item in identities}) == 2
    assert {
        item["metric_key"].split("::", 1)[1]
        for item in identities
    } == {
        "var1=revenue|var2=cost",
        "var1=profit|var2=cost",
    }


@pytest.mark.parametrize(
    "mutation",
    [
        "stale_plan",
        "stale_step",
        "dataset_mismatch",
        "legacy_unbound",
        "invalid_hydration",
    ],
)
def test_same_id_prerequisite_uses_only_current_hydratable_evidence(
    projection_context,
    mutation,
):
    evidence = copy.deepcopy(project_real_correlation(projection_context).record)
    if mutation == "stale_plan":
        evidence["computation_refs"][0]["plan_digest"] = "sha256:stale"
    elif mutation == "stale_step":
        evidence["computation_refs"][0]["step_digest"] = "sha256:stale"
    elif mutation == "dataset_mismatch":
        evidence["dataset_versions"] = ["dataset_other_v1"]
    elif mutation == "legacy_unbound":
        evidence["provenance_status"] = "legacy_unbound"
    elif mutation == "invalid_hydration":
        evidence["computation_refs"][0]["artifact_path"] = str(
            projection_context.sessions_root / "missing.json"
        )

    unmet = _unmet_block_claim_requirements(
        [evidence],
        projection_context.analysis_requirements,
        satisfaction_evidence_records=[evidence],
        current_plan_id=PLAN_ID,
        current_plan_digest=PLAN_DIGEST,
        current_step_digests={STEP_ID: STEP_DIGEST},
        current_dataset_versions={DATASET_VERSION},
        active_requirement_ids={
            item["id"] for item in projection_context.analysis_requirements
        },
        sessions_root=projection_context.sessions_root,
        current_session_id=SESSION_ID,
    )

    assert unmet == ["req_corr_effect"]


def test_same_id_prerequisite_accepts_current_hydratable_evidence(
    projection_context,
):
    evidence = project_real_correlation(projection_context).record

    assert _unmet_block_claim_requirements(
        [evidence],
        projection_context.analysis_requirements,
        satisfaction_evidence_records=[evidence],
        current_plan_id=PLAN_ID,
        current_plan_digest=PLAN_DIGEST,
        current_step_digests={STEP_ID: STEP_DIGEST},
        current_dataset_versions={DATASET_VERSION},
        active_requirement_ids={
            item["id"] for item in projection_context.analysis_requirements
        },
        sessions_root=projection_context.sessions_root,
        current_session_id=SESSION_ID,
    ) == []


def test_correlation_method_name_alone_does_not_pass_design_assumption(
    projection_context,
):
    evidence = project_real_correlation(projection_context).record
    requirement = copy.deepcopy(projection_context.analysis_requirements[0])
    requirement["required_evidence_fields"] = ["univariate_association"]
    requirement["assumption_checks"] = ["method_appropriate_for_design"]

    evaluated = evaluate_requirement_satisfaction([requirement], [evidence])

    assert evaluated[0]["status"] == "unmet"


def test_requirement_semantics_do_not_duplicate_numeric_authority():
    semantics = _project_requirement_semantics(
        capability_id="analysis.factor_relationship",
        output_data={
            "effective_sample_size": 80,
            "target_col": "outcome",
            "features_requested": ["feature"],
            "features_included": ["feature"],
            "coefficients": [
                {
                    "term": "feature",
                    "estimate": 1.25,
                    "p_value": 0.01,
                    "confidence_interval": {"lower": 0.5, "upper": 2.0},
                }
            ],
            "correction_method": "fdr_bh",
            "alpha": 0.05,
            "collinearity": {
                "status": "assessed",
                "method": "variance_inflation_factor",
                "terms": [{"term": "feature", "variance_inflation_factor": 1.2}],
            },
            "time_dependence": {
                "status": "assessed",
                "lag_1": 0.2,
            },
            "r_squared": 0.7,
            "adjusted_r_squared": 0.68,
        },
    )

    def _contains_number(value):
        if isinstance(value, bool):
            return False
        if isinstance(value, (int, float)):
            return True
        if isinstance(value, dict):
            return any(_contains_number(item) for item in value.values())
        if isinstance(value, list):
            return any(_contains_number(item) for item in value)
        return False

    for field in (
        "effective_sample_size",
        "effect_size_or_predictive_contribution",
        "multivariable_adjustment",
        "multiplicity_control",
        "collinearity_assessment",
        "time_dependence_assessment",
        "stability_or_validation",
    ):
        assert not _contains_number(semantics[field]), field
