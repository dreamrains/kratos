from __future__ import annotations

import json
import subprocess
from pathlib import Path

from data_agent.v2.release import (
    LayerStatus,
    ReadinessStatus,
    ReleaseReceipt,
    ValidationLayer,
    HUMAN_REVIEW_DIMENSIONS,
    compute_release_source_digest,
    evaluate_release_readiness,
    load_release_matrix,
)


MATRIX_PATH = Path("tests/release/v2_release_matrix.json")


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def test_source_digest_is_line_ending_portable_and_source_sensitive(tmp_path):
    _git(tmp_path, "init", "-q")
    (tmp_path / ".gitattributes").write_text("*.py text eol=lf\n", encoding="utf-8")
    source = tmp_path / "src" / "example.py"
    source.parent.mkdir()
    source.write_bytes(b"value = 1\n")
    _git(tmp_path, "add", ".gitattributes", "src/example.py")

    lf = compute_release_source_digest(tmp_path)
    source.write_bytes(b"value = 1\r\n")
    crlf = compute_release_source_digest(tmp_path)
    assert crlf.source_digest == lf.source_digest

    source.write_bytes(b"value = 2\r\n")
    modified = compute_release_source_digest(tmp_path)
    assert modified.source_digest != lf.source_digest

    extra = tmp_path / "tests" / "new_contract.py"
    extra.parent.mkdir()
    extra.write_text("assert True\n", encoding="utf-8")
    with_untracked = compute_release_source_digest(tmp_path)
    assert with_untracked.source_digest != modified.source_digest
    assert "tests/new_contract.py" in with_untracked.files

    source.unlink()
    deleted = compute_release_source_digest(tmp_path)
    assert deleted.source_digest != with_untracked.source_digest
    assert "src/example.py" not in deleted.files


def test_release_matrix_has_unique_scenarios_and_all_seven_layers():
    matrix = load_release_matrix(MATRIX_PATH)

    assert matrix.version == "v2_release_matrix.v1"
    assert len(matrix.scenarios) == 9
    assert len({item.scenario_id for item in matrix.scenarios}) == 9
    expected = set(ValidationLayer)
    assert all(set(item.required_layers) == expected for item in matrix.scenarios)
    assert all("turn_completed" in item.required_semantic_events for item in matrix.scenarios)
    assert all("executive_answer" in item.required_block_types for item in matrix.scenarios)
    assert all(item.forbidden_behaviors for item in matrix.scenarios)
    assert all(item.required_interactions for item in matrix.scenarios)
    unified = next(item for item in matrix.scenarios if item.scenario_id == "unified_analysis_entry")
    assert unified.entry == "/v2-workbench"
    assert "stop" in unified.required_interactions
    assert "draft_while_running" in unified.required_interactions
    assert "planning_estimate_without_authorization" in unified.required_interactions
    assert "explicit_planning_confirmation" in unified.required_interactions
    assert "planning_answer_persisted" in unified.required_interactions
    assert "planning_failure_stable" in unified.required_interactions
    assert "explicit_planning_retry" in unified.required_interactions
    assert "queued_steer" in unified.required_interactions
    assert "implicit_provider_retry" in unified.forbidden_behaviors
    assert "planning_answer_truncation" in unified.forbidden_behaviors
    assert "silent_planning_context_trim" in unified.forbidden_behaviors
    assert "turn_interrupted" in unified.required_semantic_events
    assert "turn_completed_after_interrupt" in unified.forbidden_behaviors


def test_browser_pass_cannot_stand_in_for_other_layers():
    matrix = load_release_matrix(MATRIX_PATH)
    digest = "sha256:" + "a" * 64
    receipt = ReleaseReceipt(
        receipt_id="receipt_browser",
        source_digest=digest,
        scenario_id=matrix.scenarios[0].scenario_id,
        layer=ValidationLayer.BROWSER_INTERACTION_JOURNEY,
        status=LayerStatus.PASS,
        evidence_refs=("browser:observation:1",),
        oracle_identity="oracle:v1",
    )

    decision = evaluate_release_readiness(matrix, [receipt], current_source_digest=digest)

    assert decision.status is ReadinessStatus.NOT_READY
    assert decision.provider_calls == 0
    assert len(decision.missing_requirements) == 62
    assert decision.incomplete_receipt_ids == ("receipt_browser",)
    assert "product_pass" not in json.dumps(decision.to_dict())


def test_stale_and_conflicting_receipts_never_satisfy_requirement():
    matrix = load_release_matrix(MATRIX_PATH)
    scenario = matrix.scenarios[0]
    current = "sha256:" + "b" * 64
    stale = ReleaseReceipt(
        receipt_id="receipt_stale",
        source_digest="sha256:" + "a" * 64,
        scenario_id=scenario.scenario_id,
        layer=ValidationLayer.OWNER_CONTRACT,
        status=LayerStatus.PASS,
        evidence_refs=("pytest:old",),
        oracle_identity="oracle:v1",
    )
    passed = ReleaseReceipt(
        receipt_id="receipt_pass",
        source_digest=current,
        scenario_id=scenario.scenario_id,
        layer=ValidationLayer.OWNER_CONTRACT,
        status=LayerStatus.PASS,
        evidence_refs=("pytest:new",),
        oracle_identity="oracle:v1",
    )
    failed = ReleaseReceipt(
        receipt_id="receipt_fail",
        source_digest=current,
        scenario_id=scenario.scenario_id,
        layer=ValidationLayer.OWNER_CONTRACT,
        status=LayerStatus.FAIL,
        evidence_refs=("pytest:failure",),
        oracle_identity="oracle:v1",
        first_failure_stage="owner assertion",
    )

    stale_decision = evaluate_release_readiness(matrix, [stale], current_source_digest=current)
    conflict_decision = evaluate_release_readiness(
        matrix, [passed, failed], current_source_digest=current
    )

    assert stale_decision.stale_receipt_ids == ("receipt_stale",)
    assert conflict_decision.status is ReadinessStatus.NOT_READY
    assert conflict_decision.conflicting_requirements == (
        f"{scenario.scenario_id}:{ValidationLayer.OWNER_CONTRACT.value}",
    )


def test_complete_current_receipts_only_reach_human_decision():
    matrix = load_release_matrix(MATRIX_PATH)
    digest = "sha256:" + "c" * 64
    receipts = []
    for scenario in matrix.scenarios:
        for layer in scenario.required_layers:
            receipts.append(
                ReleaseReceipt(
                    receipt_id=f"receipt_{scenario.scenario_id}_{layer.value}",
                    source_digest=digest,
                    scenario_id=scenario.scenario_id,
                    layer=layer,
                    status=LayerStatus.PASS,
                    evidence_refs=(f"evidence:{scenario.scenario_id}:{layer.value}",),
                    oracle_identity="oracle:v1",
                    provider_calls=(1 if layer is ValidationLayer.REAL_PROVIDER_ANALYSIS_JOURNEY else 0),
                    provider_authorization_ref=(
                        "authorization:explicit:one-call"
                        if layer is ValidationLayer.REAL_PROVIDER_ANALYSIS_JOURNEY else ""
                    ),
                    semantic_dimensions=(
                        tuple((dimension, LayerStatus.PASS) for dimension in HUMAN_REVIEW_DIMENSIONS)
                        if layer is ValidationLayer.HUMAN_SEMANTIC_REVIEW else ()
                    ),
                    observed_semantic_events=scenario.required_semantic_events,
                    observed_block_types=scenario.required_block_types,
                    observed_interactions=scenario.required_interactions,
                    chart_observation=(
                        "rendered" if scenario.chart_policy in {"required", "conditional"}
                        else "forbidden_absent"
                    ),
                )
            )

    decision = evaluate_release_readiness(matrix, receipts, current_source_digest=digest)

    assert decision.status is ReadinessStatus.READY_FOR_HUMAN_DECISION
    assert decision.missing_requirements == ()
    assert decision.provider_calls == 9
    assert decision.root_switch_authorized is False


def test_non_pass_receipt_requires_first_failure_stage():
    try:
        ReleaseReceipt(
            receipt_id="receipt_blocked",
            source_digest="sha256:" + "d" * 64,
            scenario_id="descriptive_analysis",
            layer=ValidationLayer.REAL_PROVIDER_ANALYSIS_JOURNEY,
            status=LayerStatus.BLOCKED,
            evidence_refs=("provider:not-authorized",),
            oracle_identity="oracle:v1",
        )
    except ValueError as exc:
        assert "first_failure_stage" in str(exc)
    else:
        raise AssertionError("blocked receipt without first_failure_stage was accepted")


def test_provider_receipt_requires_explicit_authorization_reference():
    try:
        ReleaseReceipt(
            receipt_id="receipt_provider",
            source_digest="sha256:" + "e" * 64,
            scenario_id="descriptive_analysis",
            layer=ValidationLayer.REAL_PROVIDER_ANALYSIS_JOURNEY,
            status=LayerStatus.PASS,
            evidence_refs=("provider:session:1",),
            oracle_identity="oracle:v1",
            provider_calls=1,
        )
    except ValueError as exc:
        assert "provider_authorization_ref" in str(exc)
    else:
        raise AssertionError("provider receipt without authorization was accepted")


def test_human_review_cannot_hide_a_failed_dimension_in_overall_pass():
    dimensions = [
        (dimension, LayerStatus.PASS) for dimension in HUMAN_REVIEW_DIMENSIONS
    ]
    dimensions[-1] = (dimensions[-1][0], LayerStatus.FAIL)
    try:
        ReleaseReceipt(
            receipt_id="receipt_human",
            source_digest="sha256:" + "f" * 64,
            scenario_id="descriptive_analysis",
            layer=ValidationLayer.HUMAN_SEMANTIC_REVIEW,
            status=LayerStatus.PASS,
            evidence_refs=("review:form:1",),
            oracle_identity="rubric:v1",
            semantic_dimensions=tuple(dimensions),
        )
    except ValueError as exc:
        assert "every dimension" in str(exc)
    else:
        raise AssertionError("human review hid a failed dimension")


def test_pass_receipt_is_incomplete_when_required_sse_evidence_is_missing():
    matrix = load_release_matrix(MATRIX_PATH)
    scenario = matrix.scenarios[0]
    digest = "sha256:" + "1" * 64
    receipt = ReleaseReceipt(
        receipt_id="receipt_incomplete_sse",
        source_digest=digest,
        scenario_id=scenario.scenario_id,
        layer=ValidationLayer.SSE_TRANSPORT_CONTRACT,
        status=LayerStatus.PASS,
        evidence_refs=("sse:trace:1",),
        oracle_identity="oracle:v1",
        observed_semantic_events=("turn_started", "turn_completed"),
    )

    decision = evaluate_release_readiness(matrix, [receipt], current_source_digest=digest)

    assert decision.status is ReadinessStatus.NOT_READY
    assert decision.incomplete_receipt_ids == ("receipt_incomplete_sse",)
