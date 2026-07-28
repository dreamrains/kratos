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


def _audit(text, *, evidence=None, **kwargs):
    current_plan_id = kwargs.pop("current_plan_id", "plan_current")
    return build_final_answer_audit(
        text,
        evidence_records=evidence if evidence is not None else [_evidence()],
        route_proposals=[],
        cleaning_logs=[],
        current_plan_id=current_plan_id,
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


def test_marker_stripping_preserves_markdown_structure():
    draft = (
        "# Conclusion\n\n"
        "| Metric | Change |\n|---|---|\n"
        "| Revenue | 12% [[evidence:ev_1#m_1]] |\n"
    )

    public = strip_internal_evidence_markers(draft)

    assert public.startswith("# Conclusion")
    assert "| Revenue | 12%  |" in public
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
    ) == "Revenue."


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
    assert "missing_evidence_identity" in check["reason_codes"]
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
    assert "missing_evidence_identity" in audit["claim_checks"][0]["reason_codes"]


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
    assert "missing_evidence_identity" in audit["claim_checks"][0]["reason_codes"]


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
    assert "missing_evidence_identity" in audit["claim_checks"][0]["reason_codes"]


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
    assert "missing_evidence_identity" in audit["claim_checks"][0]["reason_codes"]


def test_final_audit_does_not_bind_a_multi_quantity_claim():
    audit = _audit(
        "Revenue increased 12% and 13% in 2026-05 for new users.",
        evidence=[_auto_bind_evidence()],
        current_dataset_versions=["dataset_sales_v1"],
    )

    assert len(audit["claims"][0]["quantities"]) == 2
    assert audit["claims"][0]["evidence_ids"] == []
    assert "missing_evidence_identity" in audit["claim_checks"][0]["reason_codes"]


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
    assert "missing_evidence_identity" in audit["claim_checks"][0]["reason_codes"]


def test_final_audit_does_not_choose_one_measurement_from_multi_measurement_evidence():
    measurement = dict(_auto_bind_evidence()["measurements"][0])
    audit = _audit(
        "Revenue increased 12% in 2026-05 for new users.",
        evidence=[_auto_bind_evidence(measurements=[measurement, dict(measurement)])],
        current_dataset_versions=["dataset_sales_v1"],
    )

    assert audit["claims"][0]["evidence_ids"] == []
    assert "missing_evidence_identity" in audit["claim_checks"][0]["reason_codes"]


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
    assert "missing_evidence_identity" in audit["claim_checks"][0]["reason_codes"]


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


def test_numeric_audit_accepts_effect_and_structured_confidence_interval_values():
    audit = _audit(
        "Revenue increased 12% (95% CI 5% to 19%) in 2026-05 for new users "
        "[[evidence:ev_revenue]].\n"
        "Limitation: this is a descriptive comparison only.",
        evidence=[_evidence(statistical_support={
            "effect_estimate": {"value": 0.12, "unit": "ratio"},
            "confidence_interval": {
                "level": 0.95,
                "lower": 0.05,
                "upper": 0.19,
                "unit": "ratio",
            },
        })],
    )

    assert audit["status"] == "pass"


def test_current_plan_identity_is_required_even_with_an_exact_marker():
    audit = _audit(
        "Revenue increased 12% [[evidence:ev_old]].",
        evidence=[_evidence(id="ev_old", plan_id="plan_old")],
    )

    assert audit["status"] == "blocked"
    assert "evidence_outside_current_plan" in audit["claim_checks"][0]["reason_codes"]


def test_missing_current_dataset_identity_blocks_only_version_bound_evidence():
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
    assert non_versioned["status"] == "pass"


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
        measurements=[],
    )

    audit = _audit(
        "The series shows annual seasonality [[evidence:ev_seasonality]].\n"
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


def test_multiple_exact_evidence_ids_can_collectively_satisfy_claim_requirements():
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

    assert audit["status"] == "pass"
    assert audit["claim_checks"][0]["evidence_ids"] == ["ev_effect", "ev_uncertainty"]


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

    assert strip_internal_evidence_markers(draft) == "Revenue increased 12%."
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
    assert ref["status"] == "pass"
    assert "claim_checks" not in ref
    assert len(ref["artifact_digest"]) == 64
    assert state.verification_reports[-1] == ref
    artifact = json.loads(Path(ref["artifact_path"]).read_text(encoding="utf-8"))
    assert artifact["contract_version"] == "final_answer_audit.v1"
    assert artifact["claim_checks"][0]["evidence_id"] == "ev_revenue"
    assert "[[evidence:" not in artifact["public_text"]
    assert runtime.hydrate_final_answer_audit_ref(ref) == artifact

    artifact["status"] = "blocked"
    Path(ref["artifact_path"]).write_text(json.dumps(artifact), encoding="utf-8")
    assert runtime.hydrate_final_answer_audit_ref(ref) is None
