from __future__ import annotations

import hashlib

from data_agent.v2.workbench_browser_journey import (
    INTERACTION_JOURNEY_VERSION,
    PROVIDER_NEUTRAL_CHECKPOINTS,
    UNIFIED_DATASET_FIXTURE,
    compose_provider_neutral_workbench_release_receipts,
    validate_provider_neutral_interaction_journey,
    validate_provider_neutral_journey,
)
from data_agent.v2.release import (
    ValidationLayer,
    evaluate_release_readiness,
    load_release_matrix,
)


def _receipt():
    answer = "每行代表订单；这是完整业务语义。" * 160
    answer_digest = "sha256:" + hashlib.sha256(answer.encode("utf-8")).hexdigest()
    counts = {
        "loaded": (0, 0, 0, "idle"),
        "estimated": (0, 0, 0, "estimate_ready"),
        "needs_input": (1, 1, 1, "needs_input"),
        "answer_estimated": (1, 1, 1, "answer_estimate_ready"),
        "failed": (2, 2, 2, "failed"),
        "failure_stable": (2, 2, 2, "failed"),
        "retry_estimated": (2, 2, 2, "retry_estimate_ready"),
        "completed": (3, 3, 3, "completed"),
        "refreshed": (3, 3, 3, "restored"),
    }
    return {
        "version": "v2_provider_neutral_browser_journey.v1",
        "observer": "actual_browser",
        "fixture_id": "v2_workbench_planning_failure_retry.v1",
        "fixture_path": UNIFIED_DATASET_FIXTURE,
        "source_digest": "sha256:" + "a" * 64,
        "scenario_id": "unified_analysis_entry",
        "provider_calls": 0,
        "console_errors": [],
        "answer_characters": len(answer),
        "answer_before_digest": answer_digest,
        "answer_after_digest": answer_digest,
        "chart_observation": "rendered",
        "chart_count": 2,
        "checkpoints": [
            {
                "name": name,
                "planner_invocations": values[0],
                "authorizations_issued": values[1],
                "authorizations_consumed": values[2],
                "visible_state": values[3],
            }
            for name, values in counts.items()
        ],
    }


def test_provider_neutral_browser_journey_requires_exact_failure_retry_sequence():
    result = validate_provider_neutral_journey(
        _receipt(), expected_source_digest="sha256:" + "a" * 64
    )

    assert result.passed is True
    assert result.reason_codes == ()
    assert result.observed_interactions == (
        "upload",
        "planning_estimate_without_authorization",
        "explicit_planning_confirmation",
        "needs_input",
        "planning_answer_persisted",
        "planning_failure_stable",
        "explicit_planning_retry",
        "live_progress",
        "task_overlay_collapsed",
        "refresh_restore",
    )
    assert tuple(item[0] for item in PROVIDER_NEUTRAL_CHECKPOINTS) == tuple(
        item["name"] for item in _receipt()["checkpoints"]
    )


def test_provider_neutral_browser_journey_rejects_hidden_retry_or_provider_use():
    receipt = _receipt()
    receipt["provider_calls"] = 1
    receipt["checkpoints"][5]["planner_invocations"] = 3

    result = validate_provider_neutral_journey(
        receipt, expected_source_digest="sha256:" + "a" * 64
    )

    assert result.passed is False
    assert "real_provider_call_in_provider_neutral_journey" in result.reason_codes
    assert "invalid_checkpoint_counts" in result.reason_codes


def test_provider_neutral_browser_journey_rejects_truncated_answer_and_stale_source():
    receipt = _receipt()
    receipt["answer_after_digest"] = "sha256:" + "c" * 64

    result = validate_provider_neutral_journey(
        receipt, expected_source_digest="sha256:" + "b" * 64
    )

    assert result.passed is False
    assert "stale_browser_journey" in result.reason_codes
    assert "full_planning_answer_not_observed" in result.reason_codes


def _interaction_receipt():
    return {
        "version": INTERACTION_JOURNEY_VERSION,
        "observer": "actual_browser",
        "fixture_id": "v2_workbench_interactions.v1",
        "fixture_path": UNIFIED_DATASET_FIXTURE,
        "source_digest": "sha256:" + "d" * 64,
        "scenario_id": "unified_analysis_entry",
        "provider_calls": 0,
        "console_errors": [],
        "sessions": {
            "steer": "session_steer",
            "stop": "session_stop",
            "isolation": "session_isolation",
        },
        "observations": {
            "upload": True,
            "live_progress": True,
            "draft_while_running": True,
            "queued_steer_persisted": True,
            "queued_steer_completed": True,
            "stop_receipt_persisted": True,
            "turn_interrupted": True,
            "no_final_after_interrupt": True,
            "task_overlay_collapsed": True,
            "refresh_completed_restore": True,
            "refresh_interrupted_restore": True,
            "session_isolation": True,
            "error_recovery": True,
        },
    }


def test_interaction_journey_requires_stop_steer_refresh_and_isolation():
    result = validate_provider_neutral_interaction_journey(
        _interaction_receipt(), expected_source_digest="sha256:" + "d" * 64
    )

    assert result.passed is True
    assert result.observed_interactions == (
        "upload",
        "live_progress",
        "draft_while_running",
        "queued_steer",
        "stop",
        "error_recovery",
        "session_isolation",
        "task_overlay_collapsed",
        "refresh_restore",
    )


def test_interaction_journey_rejects_session_reuse_final_after_stop_and_stale_source():
    receipt = _interaction_receipt()
    receipt["sessions"]["stop"] = "session_steer"
    receipt["observations"]["no_final_after_interrupt"] = False

    result = validate_provider_neutral_interaction_journey(
        receipt, expected_source_digest="sha256:" + "e" * 64
    )

    assert result.passed is False
    assert "stale_browser_journey" in result.reason_codes
    assert "browser_sessions_not_isolated" in result.reason_codes
    assert "missing_browser_interaction:no_final_after_interrupt" in result.reason_codes


def test_unified_composer_requires_both_current_fixture_bound_journeys():
    planning = _receipt()
    interaction = _interaction_receipt()
    digest = "sha256:" + "f" * 64
    planning["source_digest"] = digest
    interaction["source_digest"] = digest
    scenario = next(
        item
        for item in load_release_matrix("tests/release/v2_release_matrix.json").scenarios
        if item.scenario_id == "unified_analysis_entry"
    )

    result = compose_provider_neutral_workbench_release_receipts(
        planning,
        interaction,
        scenario=scenario,
        expected_source_digest=digest,
    )

    assert result.passed is True
    assert result.reason_codes == ()
    assert tuple(item.layer for item in result.receipts) == (
        ValidationLayer.BROWSER_INTERACTION_JOURNEY,
        ValidationLayer.REFRESH_PERSISTENCE_JOURNEY,
    )
    browser, refresh = result.receipts
    assert set(browser.observed_interactions) >= set(scenario.required_interactions)
    assert browser.chart_observation == "rendered"
    assert len(browser.evidence_refs) == 2
    assert refresh.observed_interactions == ("refresh_restore",)
    assert refresh.evidence_refs == browser.evidence_refs
    decision = evaluate_release_readiness(
        load_release_matrix("tests/release/v2_release_matrix.json"),
        result.receipts,
        current_source_digest=digest,
    )
    assert browser.receipt_id not in decision.incomplete_receipt_ids
    assert refresh.receipt_id not in decision.incomplete_receipt_ids


def test_unified_composer_rejects_wrong_dataset_missing_chart_and_partial_journey():
    planning = _receipt()
    interaction = _interaction_receipt()
    digest = planning["source_digest"]
    scenario = next(
        item
        for item in load_release_matrix("tests/release/v2_release_matrix.json").scenarios
        if item.scenario_id == "unified_analysis_entry"
    )
    planning["fixture_path"] = "tests/fixtures/v2_slice1_sales.csv"
    planning["chart_count"] = 0
    interaction["observations"]["queued_steer_completed"] = False

    result = compose_provider_neutral_workbench_release_receipts(
        planning,
        interaction,
        scenario=scenario,
        expected_source_digest=digest,
    )

    assert result.passed is False
    assert result.receipts == ()
    assert "wrong_browser_dataset_fixture" in result.reason_codes
    assert "required_inline_chart_not_observed" in result.reason_codes
    assert "missing_browser_interaction:queued_steer_completed" in result.reason_codes
