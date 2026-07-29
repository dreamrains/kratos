"""Phase A systemic replay tests (Task 12).

The replay harness drives the REAL ``AgentLoop`` through the Tasks 6-11
pipeline using a scripted fake LLM. These four tests pin the contracts the
release gate relies on:

* Factor-analysis replay reaches the canonical analysis depth, converges to
  a terminal state, and publishes a Chinese, evidence-backed answer with at
  least one safe progress narration preceding it.
* Aggregate-profile replay cannot assert user-level dimensions the data
  does not support, and surfaces the missing-data boundary in the answer.
* Sandbox-heavy replay exercises preloaded imports and missing-dataset
  lookups without cascading through ``__import__``/``NoneType`` errors and
  stays inside the bounded identical-failure budget.
* Unicode replay survives a ``cp936`` console capture, keeping ``⚠️`` intact
  on both the persisted and the streamed/browser text paths.
"""

from __future__ import annotations

import sys
import copy
from pathlib import Path

# Make the harness importable as ``replay_analysis_reliability``.
_SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from replay_analysis_reliability import (  # noqa: E402
    _DIMENSION_OPPORTUNITY_FINAL_TEXT,
    _DIMENSION_OPPORTUNITY_PROMPT,
    _dimension_opportunity_responses,
    _superficial_profile_only_responses,
    run_deterministic_replay,
    run_sandbox_replay,
    run_unicode_replay,
)
from tests.fixtures.analysis_reliability import (  # noqa: E402
    build_aggregate_payment_frame,
    build_factor_relationship_frame,
    factor_relationship_prompt,
)
from tests.replay_assertions import (  # noqa: E402
    assert_bound_projected_measurements,
    assert_reliable_analysis_trace,
)
from data_agent.agent.answer_quality import build_final_answer_audit  # noqa: E402


def test_factor_session_replay_is_deep_bounded_and_publishable(tmp_path):
    result = run_deterministic_replay(
        frame=build_factor_relationship_frame(),
        prompt=factor_relationship_prompt(),
        root=tmp_path,
    )
    assert_reliable_analysis_trace(result.trace, require_inferential_attempt=True)
    assert result.completion_state in {"complete", "complete_with_limits"}
    assert result.evidence_records
    assert result.progress_events[0].sequence < result.final_answer_sequence
    assert result.final_answer.strip()
    assert result.final_answer_language == "zh"
    assert "Some requested analysis claims" not in result.final_answer
    assert result.final_audit_status == "pass"
    assert "5.399135" in result.final_answer
    assert "[[evidence:" not in result.final_answer
    assert_bound_projected_measurements(result.evidence_records)


def test_factor_replay_satisfies_semantic_depth_not_tool_count(tmp_path):
    result = run_deterministic_replay(
        frame=build_factor_relationship_frame(),
        prompt=factor_relationship_prompt(),
        root=tmp_path,
    )
    assert {
        "data.profile",
        "analysis.correlation",
        "analysis.factor_relationship",
    }.issubset(result.successful_capability_ids)
    for name in (
        "grain_definition",
        "target_definition",
        "missingness_assessment",
        "univariate_association",
        "multivariable_adjustment",
        "multiplicity_control",
        "collinearity_assessment",
        "effect_size_or_predictive_contribution",
        "limitations_and_alternatives",
    ):
        assert result.requirement_statuses[name] == "satisfied"
    for name in ("stability_or_validation", "time_dependence_assessment"):
        assert result.requirement_statuses[name] in {"satisfied", "limited"}
    assert result.published_limitations


def test_equivalent_cross_step_prerequisite_is_current_and_fail_closed(tmp_path):
    result = run_deterministic_replay(
        frame=build_factor_relationship_frame(),
        prompt=factor_relationship_prompt(),
        root=tmp_path,
        session_id="cross_step_prerequisite",
    )
    factor = next(
        record
        for record in result.evidence_records
        if any(
            call.get("capability_id") == "analysis.factor_relationship"
            for call in record.get("tool_calls") or []
        )
    )
    measurement = next(
        item
        for item in factor["measurements"]
        if item["identity"]["metric_key"].startswith(
            "coefficients.estimate::term=活跃度"
        )
    )
    draft = (
        "活跃度 estimate 为 5.399135 "
        f"[[evidence:{factor['id']}#{measurement['identity']['measurement_key']}]]。"
        "局限：样本量有限、关联不等于因果。"
    )

    def _audit(records, requirements):
        return build_final_answer_audit(
            draft,
            evidence_records=records,
            current_plan_id=result.current_plan_id,
            current_dataset_versions=result.current_dataset_versions,
            sessions_root=Path(result.sessions_root),
            current_session_id=result.current_session_id,
            current_plan_digest=result.current_plan_digest,
            current_step_digests=result.current_step_digests,
            analysis_requirements=requirements,
            measurement_binding_mode="soft",
        )

    assert _audit(
        result.evidence_records,
        result.analysis_requirements,
    )["status"] == "pass"

    def _mutate_requirement_field(records, requirements):
        source = next(
            item
            for item in requirements
            if item["id"] == "req_step_2_univariate_association"
        )
        source["required_evidence_fields"] = ["different_metric_semantics"]

    def _mutate_assumption(records, requirements):
        source = next(
            item
            for item in requirements
            if item["id"] == "req_step_2_univariate_association"
        )
        source["assumption_checks"] = ["different_design_assumption"]

    def _mutate_stale_plan(records, requirements):
        records[1]["computation_refs"][0]["plan_digest"] = "sha256:stale"

    def _mutate_dataset(records, requirements):
        records[1]["dataset_versions"] = ["dataset_other_v1"]

    def _mutate_legacy_provenance(records, requirements):
        records[1]["provenance_status"] = "legacy_unbound"

    for mutation in (
        _mutate_requirement_field,
        _mutate_assumption,
        _mutate_stale_plan,
        _mutate_dataset,
        _mutate_legacy_provenance,
    ):
        records = copy.deepcopy(result.evidence_records)
        requirements = copy.deepcopy(result.analysis_requirements)
        mutation(records, requirements)
        audit = _audit(records, requirements)
        numeric_check = next(
            check
            for check in audit["claim_checks"]
            if "5.399135" in str(check.get("claim") or "")
        )
        assert audit["status"] == "blocked", mutation.__name__
        assert (
            "unmet_block_claim_requirement" in numeric_check["reason_codes"]
        ), mutation.__name__


def test_repeated_superficial_tools_cannot_complete_factor_request(tmp_path):
    result = run_deterministic_replay(
        frame=build_factor_relationship_frame(),
        prompt=factor_relationship_prompt(),
        responses=_superficial_profile_only_responses(repetitions=6),
        fallback_text="活跃度显著影响目标值。",
        root=tmp_path,
        session_id="superficial_replay",
    )
    assert result.requirement_statuses["multivariable_adjustment"] != "satisfied"
    assert result.requirement_statuses["collinearity_assessment"] != "satisfied"
    assert result.completion_state != "complete"
    assert "显著影响" not in result.final_answer


def _contains_number(value):
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, dict):
        return any(_contains_number(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_number(item) for item in value)
    return False


def test_dimension_replay_proves_observed_segments_and_hypothesis_only_opportunities(
    tmp_path,
):
    csv_path = tmp_path / "opportunity_data.csv"
    frame = build_factor_relationship_frame()
    frame.to_csv(csv_path, index=False, encoding="utf-8-sig")
    result = run_deterministic_replay(
        frame=frame,
        prompt=_DIMENSION_OPPORTUNITY_PROMPT,
        responses=_dimension_opportunity_responses(csv_path),
        fallback_text=_DIMENSION_OPPORTUNITY_FINAL_TEXT,
        root=tmp_path,
        session_id="dimension_opportunity",
        project_name="dimension_opportunity",
        dataset_name="opportunity_data",
    )

    assert "analysis.dimension_decomposition" in result.successful_capability_ids
    assert result.requirement_statuses["segment_coverage"] == "satisfied"
    assert result.requirement_statuses["opportunity_candidates"] == "satisfied"
    evidence = next(
        record
        for record in result.evidence_records
        if any(
            call.get("capability_id") == "analysis.dimension_decomposition"
            for call in record.get("tool_calls") or []
        )
    )
    segment = evidence["segment_coverage"]
    opportunity = evidence["opportunity_candidates"]
    assert segment["status"] == "observed"
    assert opportunity["status"] == "hypothesis_only"
    assert opportunity["claim_class"] == "exploratory"
    assert opportunity["basis"] == "observed_dimension_contribution"
    assert opportunity["causal_authorization"] == "none"
    assert not _contains_number(segment)
    assert not _contains_number(opportunity)


def test_same_driver_plan_without_decomposition_leaves_semantic_requirements_unmet(
    tmp_path,
):
    csv_path = tmp_path / "opportunity_data.csv"
    frame = build_factor_relationship_frame()
    frame.to_csv(csv_path, index=False, encoding="utf-8-sig")
    result = run_deterministic_replay(
        frame=frame,
        prompt=_DIMENSION_OPPORTUNITY_PROMPT,
        responses=_dimension_opportunity_responses(
            csv_path,
            include_decomposition=False,
        ),
        fallback_text=_DIMENSION_OPPORTUNITY_FINAL_TEXT,
        root=tmp_path,
        session_id="dimension_opportunity_without_decomposition",
        project_name="dimension_opportunity_without_decomposition",
        dataset_name="opportunity_data",
    )

    requirement_names = {
        requirement["name"] for requirement in result.analysis_requirements
    }
    assert {"segment_coverage", "opportunity_candidates"} <= requirement_names
    assert result.requirement_statuses["segment_coverage"] != "satisfied"
    assert result.requirement_statuses["opportunity_candidates"] != "satisfied"


def test_aggregate_profile_replay_blocks_unavailable_user_claims(tmp_path):
    csv_root = tmp_path / "aggregate_data.csv"
    build_aggregate_payment_frame().to_csv(csv_root, index=False, encoding="utf-8-sig")
    from replay_analysis_reliability import _aggregate_responses, _AGGREGATE_FINAL_TEXT

    result = run_deterministic_replay(
        frame=build_aggregate_payment_frame(),
        prompt="请分析用户画像、复购和消费分布",
        responses=_aggregate_responses(csv_root),
        fallback_text=_AGGREGATE_FINAL_TEXT,
        root=tmp_path,
        session_id="aggregate_replay",
        project_name="aggregate_replay",
        dataset_name="aggregate_data",
    )
    assert "年龄" not in result.asserted_dimensions
    assert "个人复购" not in result.asserted_dimensions
    assert result.completion_state in {"complete_with_limits", "blocked_by_data"}
    assert "需要用户级字段" in result.final_answer


def test_sandbox_heavy_replay_has_no_import_or_none_cascade(tmp_path):
    result = run_sandbox_replay(tmp_path)
    # Negative: the sandbox boundary must not leak opaque cascades.
    assert "__import__ not found" not in result.serialized_trace
    assert "NoneType" not in result.serialized_trace
    # Positive: the failing run_python ACTUALLY executed inside the loop's
    # fallback budget and returned a STRUCTURED error token (Task 3), instead
    # of being silently blocked and leaving these assertions vacuously true.
    assert "dataset_not_found" in result.serialized_trace
    # The identical missing-dataset retry must be bounded (1..2): the lower
    # bound proves a real failure was traversed, the upper bound proves the
    # bounded-retry contract held.
    assert 1 <= result.max_identical_failure_attempts <= 2


def test_unicode_progress_replay_survives_cp936_and_keeps_browser_unicode(tmp_path):
    result = run_unicode_replay(tmp_path, console_encoding="cp936")
    assert result.turn_completed is True
    assert "⚠️" in result.persisted_text
    assert "⚠️" in result.browser_text
