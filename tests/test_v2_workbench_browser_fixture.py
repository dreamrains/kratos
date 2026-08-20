from __future__ import annotations

import io

from data_agent.v2.workbench_browser_fixture import (
    DeterministicJourneyPlanner,
    build_provider_neutral_fixture,
)
from data_agent.v2.planner import DatasetColumnContext, DatasetPlanningContext, ColumnRole


def test_fixture_exposes_isolated_state_and_never_reports_provider_calls(tmp_path):
    app = build_provider_neutral_fixture(tmp_path)
    client = app.test_client()

    state = client.get("/__acceptance/state").get_json()

    assert client.get("/v2-workbench").status_code == 200
    assert state["fixture_id"] == "v2_workbench_planning_failure_retry.v1"
    assert state["planner_invocations"] == 0
    assert state["authorizations_issued"] == 0
    assert state["authorizations_consumed"] == 0
    assert state["provider_calls"] == 0


def test_fixture_context_overflow_is_explicit_and_never_authorizes(tmp_path):
    app = build_provider_neutral_fixture(tmp_path)
    client = app.test_client()
    upload = client.post(
        "/api/upload",
        data={"file": (io.BytesIO(b"sales\n10\n20\n"), "overflow.csv")},
        content_type="multipart/form-data",
    )

    response = client.post(
        "/api/v2/planning-estimates",
        json={
            "session_id": "session_overflow",
            "filename": upload.get_json()["filename"],
            "question": "[TOO_LARGE] 请完整分析",
        },
    )
    state = client.get("/__acceptance/state").get_json()

    assert response.status_code == 413
    assert response.get_json() == {
        "error": "planning context exceeds the model input budget",
        "error_code": "planning_context_too_large",
        "planning_context": {
            "model_id": "provider-neutral-fixture",
            "estimated_input_tokens": 120001,
            "model_context_window_tokens": 128000,
            "reserved_output_tokens": 8000,
            "available_input_tokens": 120000,
            "fits": False,
        },
    }
    assert state["planner_invocations"] == 0
    assert state["authorizations_issued"] == 0
    assert state["provider_calls"] == 0


def test_fixture_planner_fails_exactly_once_then_requires_explicit_third_call():
    planner = DeterministicJourneyPlanner()
    context = DatasetPlanningContext(
        filename="planning_journey.csv",
        source_fingerprint="sha256:" + "a" * 64,
        row_count=4,
        columns=(DatasetColumnContext("sales", "float64", ColumnRole.NUMERIC),),
    )

    assert planner.plan("销售额如何？", context).status.value == "needs_input"
    try:
        planner.plan("销售额如何？", context, clarifications=())
    except RuntimeError as exc:
        assert str(exc) == "synthetic provider failure"
    else:
        raise AssertionError("fixture did not expose the planned failure")
    assert planner.calls == 2
    assert planner.plan("销售额如何？", context, clarifications=()).status.value == "ready"
    assert planner.calls == 3
