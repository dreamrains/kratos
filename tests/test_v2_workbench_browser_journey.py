from __future__ import annotations

import hashlib

from data_agent.v2.workbench_browser_journey import (
    PROVIDER_NEUTRAL_CHECKPOINTS,
    validate_provider_neutral_journey,
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
        "source_digest": "sha256:" + "a" * 64,
        "scenario_id": "unified_analysis_entry",
        "provider_calls": 0,
        "console_errors": [],
        "answer_characters": len(answer),
        "answer_before_digest": answer_digest,
        "answer_after_digest": answer_digest,
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
