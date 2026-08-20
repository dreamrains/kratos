from __future__ import annotations

import hashlib
import io
from pathlib import Path

import pandas as pd
import pytest

import data_agent.config as config_module

from data_agent.v2.workbench_browser_fixture import (
    DelayedAnalysisRouter,
    DeterministicJourneyPlanner,
    build_provider_neutral_fixture,
)
from data_agent.v2.router import AnalysisKind
from data_agent.v2.planner import DatasetColumnContext, DatasetPlanningContext, ColumnRole
from data_agent.v2.planning_input import PlanningInputStore


@pytest.fixture(autouse=True)
def _restore_provider_neutral_fixture_globals():
    import data_agent.web.blueprints.v2 as v2_module

    original_config = config_module._config
    original_planner_factory = v2_module.V2_PLANNER_FACTORY
    original_budget_factory = v2_module.V2_PLANNING_BUDGET_FACTORY
    original_router_factory = v2_module.V2_ROUTER_FACTORY
    try:
        yield
    finally:
        config_module._config = original_config
        v2_module.V2_PLANNER_FACTORY = original_planner_factory
        v2_module.V2_PLANNING_BUDGET_FACTORY = original_budget_factory
        v2_module.V2_ROUTER_FACTORY = original_router_factory


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
    assert state["fixture_csv"].replace("\\", "/").endswith(
        "tests/fixtures/v2_slice4d_combined.csv"
    )


def test_fixture_planning_model_identity_reaches_needs_input(tmp_path):
    app = build_provider_neutral_fixture(tmp_path)
    client = app.test_client()
    fixture = Path(app.config["PROVIDER_NEUTRAL_FIXTURE_CSV"])
    question = "销售如何变化？"
    session_id = "session_fixture_planning_identity"
    upload = client.post(
        "/api/upload",
        data={"file": (io.BytesIO(fixture.read_bytes()), fixture.name)},
        content_type="multipart/form-data",
    )
    estimate = client.post(
        "/api/v2/planning-estimates",
        json={
            "session_id": session_id,
            "filename": fixture.name,
            "question": question,
        },
    )
    authorization = client.post(
        "/api/v2/provider-authorizations",
        json={
            "session_id": session_id,
            "filename": fixture.name,
            "question": question,
            "client_action_id": "action_fixture_planning_identity",
            "purpose": "analysis_planning",
            "provider_calls_authorized": 1,
            "confirm_provider_call": True,
        },
    )
    plan = client.post(
        "/api/v2/plans",
        json={
            "session_id": session_id,
            "filename": fixture.name,
            "question": question,
            "client_request_id": "request_fixture_planning_identity",
            "provider_authorization_id": authorization.get_json()["authorization_id"],
        },
    )
    state = client.get("/__acceptance/state").get_json()

    assert upload.status_code == 200
    assert estimate.status_code == 200
    assert estimate.get_json()["model_id"] == "provider-neutral-fixture"
    assert authorization.status_code == 201
    assert plan.status_code == 201
    assert plan.get_json()["status"] == "needs_input"
    assert state["planner_invocations"] == 1
    assert state["authorizations_issued"] == 1
    assert state["authorizations_consumed"] == 1
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


def test_fixture_exposes_only_digest_and_length_for_persisted_planning_answers(tmp_path):
    app = build_provider_neutral_fixture(tmp_path)
    answer = "完整业务语义" * 400
    PlanningInputStore(tmp_path / "sessions", "session_answer").record(
        source_plan_id="plan_source",
        client_reply_id="reply_source",
        questions=({"question_id": "question_one", "text": "每行代表什么？"},),
        answers=({"question_id": "question_one", "answer": answer},),
    )

    state = app.test_client().get("/__acceptance/state").get_json()

    observed = state["planning_inputs"][0]
    assert observed["session_id"] == "session_answer"
    assert observed["answers"] == [
        {
            "question_id": "question_one",
            "characters": len(answer),
            "digest": "sha256:" + hashlib.sha256(answer.encode("utf-8")).hexdigest(),
        }
    ]


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


def test_fixture_router_preserves_real_runtime_and_only_delays_events(tmp_path):
    workspace = tmp_path / "workspace"
    inbox = workspace / "inbox"
    inbox.mkdir(parents=True)
    pd.DataFrame({"sales": [10, 20, 30]}).to_csv(inbox / "sales.csv", index=False)
    router = DelayedAnalysisRouter(tmp_path / "sessions", inbox, delay_seconds=0)

    prepared = router.prepare(
        analysis_kind=AnalysisKind.DESCRIPTIVE,
        session_id="session_fixture_router",
        turn_id="turn_fixture_router",
        payload={
            "filename": "sales.csv",
            "metric": "sales",
            "question": "平均销售额？",
        },
    )
    events = list(prepared.stream())

    assert events[0].event == "turn_started"
    assert events[-1].event == "turn_completed"
    assert any(item.event == "final_block_delta" for item in events)
