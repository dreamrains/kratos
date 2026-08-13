from __future__ import annotations

import json
import hashlib

import pandas as pd

import data_agent.config as config_module
from data_agent.config import AgentConfig
from data_agent.v2.plan_store import DurablePlanStatus, PlanStore
from data_agent.v2.planner import AnalysisPlan, AnalysisKind, PlanStatus
from data_agent.web.app import create_app


def _events(raw: str):
    parsed = []
    event = ""
    data = ""
    for line in raw.splitlines():
        if line.startswith("event: "):
            event = line.removeprefix("event: ")
        elif line.startswith("data: "):
            data = line.removeprefix("data: ")
        elif not line and event and data:
            parsed.append((event, json.loads(data)))
            event = ""
            data = ""
    return parsed


def _client(monkeypatch, tmp_path):
    workspace = tmp_path / "workspace"
    inbox = workspace / "inbox"
    inbox.mkdir(parents=True)
    pd.DataFrame({"sales": [10, 20, 30]}).to_csv(inbox / "sales.csv", index=False)
    monkeypatch.setattr(
        config_module,
        "_config",
        AgentConfig(WORKSPACE_DIR=workspace, SESSIONS_DIR=tmp_path / "sessions"),
    )
    return create_app().test_client()


class FakePlanner:
    calls = 0

    def plan(self, question, context):
        type(self).calls += 1
        return AnalysisPlan(
            status=PlanStatus.READY,
            user_question=question,
            analysis_kind=AnalysisKind.DESCRIPTIVE,
            parameters={"metric": "sales"},
            rationale="描述当前销售额。",
            questions=(),
            maximum_claim_class="descriptive",
            planner_invocations=1,
            model_id="fake-planner",
        )


class FakeNeedsInputPlanner:
    def plan(self, question, context):
        return AnalysisPlan(
            status=PlanStatus.NEEDS_INPUT,
            user_question=question,
            analysis_kind=None,
            parameters={},
            rationale="缺少分析单位语义。",
            questions=("每行代表订单还是客户？",),
            maximum_claim_class="",
            planner_invocations=1,
            model_id="fake-planner",
        )


class FakeFailedPlanner:
    calls = 0

    def plan(self, question, context):
        type(self).calls += 1
        raise RuntimeError("provider unavailable")


def test_plan_api_requires_exact_single_call_authorization(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    for value in (None, 0, 2, True):
        response = client.post(
            "/api/v2/plans",
            json={
                "session_id": "session_plan_auth",
                "filename": "sales.csv",
                "question": "平均销售额？",
                "client_request_id": "client_plan_auth",
                "provider_calls_authorized": value,
                "provider_authorization_ref": "user:explicit",
            },
        )
        assert response.status_code == 400


def test_plan_api_persists_ready_and_idempotent_retry_does_not_reinvoke(
    monkeypatch, tmp_path
):
    client = _client(monkeypatch, tmp_path)
    import data_agent.web.blueprints.v2 as v2_module

    FakePlanner.calls = 0
    monkeypatch.setattr(v2_module, "V2_PLANNER_FACTORY", lambda: FakePlanner())
    request = {
        "session_id": "session_plan_api",
        "filename": "sales.csv",
        "question": "平均销售额？",
        "client_request_id": "client_plan_api",
        "provider_calls_authorized": 1,
        "provider_authorization_ref": "user:explicit:one",
    }
    first = client.post("/api/v2/plans", json=request)
    repeated = client.post("/api/v2/plans", json=request)

    assert first.status_code == 201
    assert repeated.status_code == 200
    assert first.get_json()["status"] == "ready"
    assert repeated.get_json()["plan_id"] == first.get_json()["plan_id"]
    assert FakePlanner.calls == 1
    restored = client.get(
        f"/api/v2/sessions/session_plan_api/plans/{first.get_json()['plan_id']}"
    )
    assert restored.get_json()["status"] == "ready"


def test_analyze_by_plan_id_uses_persisted_parameters_not_consumer_body(
    monkeypatch, tmp_path
):
    client = _client(monkeypatch, tmp_path)
    store = PlanStore(tmp_path / "sessions", "session_plan_execute")
    requested = store.request(
        client_request_id="client_plan_execute",
        question="平均销售额？",
        dataset_context={
            "filename": "sales.csv",
            "source_fingerprint": "sha256:"
            + hashlib.sha256(
                (tmp_path / "workspace" / "inbox" / "sales.csv").read_bytes()
            ).hexdigest(),
            "row_count": 3,
            "columns": [{"name": "sales", "dtype": "int64", "role": "numeric"}],
        },
        provider_authorization_ref="user:explicit:execute",
        provider_calls_authorized=1,
    )
    store.complete(
        requested.plan_id,
        AnalysisPlan(
            status=PlanStatus.READY,
            user_question="平均销售额？",
            analysis_kind=AnalysisKind.DESCRIPTIVE,
            parameters={"metric": "sales"},
            rationale="描述当前销售额。",
            questions=(),
            maximum_claim_class="descriptive",
            planner_invocations=1,
            model_id="fake-planner",
        ),
    )

    response = client.post(
        "/api/v2/analyze",
        json={
            "session_id": "session_plan_execute",
            "turn_id": "turn_plan_execute",
            "plan_id": requested.plan_id,
            "analysis_kind": "magic",
            "metric": "missing_metric",
            "question": "consumer injection",
        },
    )
    events = _events(response.get_data(as_text=True))
    restored = client.get(
        "/api/v2/sessions/session_plan_execute/turns/turn_plan_execute"
    ).get_json()

    assert response.status_code == 200
    assert events[-1][0] == "turn_completed"
    assert restored["request_context"]["analysis_kind"] == "descriptive"
    assert restored["request_context"]["metric"] == "sales"
    assert restored["request_context"]["question"] == "平均销售额？"
    assert restored["request_context"]["plan_id"] == requested.plan_id
    projected = store.get(requested.plan_id)
    assert projected.status is DurablePlanStatus.CONSUMED
    assert projected.target_turn_id == "turn_plan_execute"


def test_analyze_by_plan_rejects_replaced_source_without_consuming_plan(
    monkeypatch, tmp_path
):
    client = _client(monkeypatch, tmp_path)
    source = tmp_path / "workspace" / "inbox" / "sales.csv"
    store = PlanStore(tmp_path / "sessions", "session_plan_changed")
    requested = store.request(
        client_request_id="client_plan_changed",
        question="平均销售额？",
        dataset_context={
            "filename": "sales.csv",
            "source_fingerprint": "sha256:"
            + hashlib.sha256(source.read_bytes()).hexdigest(),
            "row_count": 3,
            "columns": [{"name": "sales", "dtype": "int64", "role": "numeric"}],
        },
        provider_authorization_ref="user:explicit:changed",
        provider_calls_authorized=1,
    )
    store.complete(
        requested.plan_id,
        AnalysisPlan(
            status=PlanStatus.READY,
            user_question="平均销售额？",
            analysis_kind=AnalysisKind.DESCRIPTIVE,
            parameters={"metric": "sales"},
            rationale="描述当前销售额。",
            questions=(),
            maximum_claim_class="descriptive",
            planner_invocations=1,
            model_id="fake-planner",
        ),
    )
    pd.DataFrame({"sales": [999]}).to_csv(source, index=False)

    response = client.post(
        "/api/v2/analyze",
        json={
            "session_id": "session_plan_changed",
            "turn_id": "turn_plan_changed",
            "plan_id": requested.plan_id,
        },
    )

    assert response.status_code == 409
    assert "source has changed" in response.get_json()["error"]
    assert store.get(requested.plan_id).status is DurablePlanStatus.READY


def test_plan_api_persists_needs_input_without_creating_executable_route(
    monkeypatch, tmp_path
):
    client = _client(monkeypatch, tmp_path)
    import data_agent.web.blueprints.v2 as v2_module

    monkeypatch.setattr(
        v2_module, "V2_PLANNER_FACTORY", lambda: FakeNeedsInputPlanner()
    )
    response = client.post(
        "/api/v2/plans",
        json={
            "session_id": "session_plan_needs_input",
            "filename": "sales.csv",
            "question": "比较表现",
            "client_request_id": "client_plan_needs_input",
            "provider_calls_authorized": 1,
            "provider_authorization_ref": "user:explicit:needs-input",
        },
    )

    body = response.get_json()
    assert response.status_code == 201
    assert body["status"] == "needs_input"
    assert body["analysis_kind"] == ""
    assert body["parameters"] == {}
    blocked = client.post(
        "/api/v2/analyze",
        json={
            "session_id": "session_plan_needs_input",
            "plan_id": body["plan_id"],
        },
    )
    assert blocked.status_code == 409


def test_failed_plan_is_durable_and_same_request_does_not_retry_provider(
    monkeypatch, tmp_path
):
    client = _client(monkeypatch, tmp_path)
    import data_agent.web.blueprints.v2 as v2_module

    FakeFailedPlanner.calls = 0
    monkeypatch.setattr(v2_module, "V2_PLANNER_FACTORY", lambda: FakeFailedPlanner())
    request = {
        "session_id": "session_plan_failed",
        "filename": "sales.csv",
        "question": "平均销售额？",
        "client_request_id": "client_plan_failed",
        "provider_calls_authorized": 1,
        "provider_authorization_ref": "user:explicit:failed",
    }
    failed = client.post("/api/v2/plans", json=request)
    repeated = client.post("/api/v2/plans", json=request)

    assert failed.status_code == 502
    assert failed.get_json()["plan"]["status"] == "failed"
    assert failed.get_json()["plan"]["provider_calls"] == 1
    assert repeated.status_code == 200
    assert repeated.get_json()["status"] == "failed"
    assert FakeFailedPlanner.calls == 1


def test_incomplete_requested_plan_requires_new_authorization_and_is_not_retried(
    monkeypatch, tmp_path
):
    client = _client(monkeypatch, tmp_path)
    source = tmp_path / "workspace" / "inbox" / "sales.csv"
    store = PlanStore(tmp_path / "sessions", "session_plan_incomplete")
    store.request(
        client_request_id="client_plan_incomplete",
        question="平均销售额？",
        dataset_context={
            "filename": "sales.csv",
            "source_fingerprint": "sha256:"
            + hashlib.sha256(source.read_bytes()).hexdigest(),
            "row_count": 3,
            "columns": [{"name": "sales", "dtype": "int64", "role": "numeric"}],
        },
        provider_authorization_ref="user:explicit:incomplete",
        provider_calls_authorized=1,
    )
    import data_agent.web.blueprints.v2 as v2_module

    FakePlanner.calls = 0
    monkeypatch.setattr(v2_module, "V2_PLANNER_FACTORY", lambda: FakePlanner())
    response = client.post(
        "/api/v2/plans",
        json={
            "session_id": "session_plan_incomplete",
            "filename": "sales.csv",
            "question": "平均销售额？",
            "client_request_id": "client_plan_incomplete",
            "provider_calls_authorized": 1,
            "provider_authorization_ref": "user:explicit:incomplete",
        },
    )

    assert response.status_code == 409
    assert "new request identity and authorization" in response.get_json()["error"]
    assert FakePlanner.calls == 0
