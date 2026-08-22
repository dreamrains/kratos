from __future__ import annotations

import json
import hashlib

import pandas as pd

import data_agent.config as config_module
from data_agent.config import AgentConfig
from data_agent.v2.plan_store import DurablePlanStatus, PlanStore
from data_agent.v2.planning_input import PlanningInputStore
from data_agent.v2.planner import (
    AnalysisPlan,
    AnalysisKind,
    DatasetPlanningContext,
    PlanStatus,
    PlannerContractError,
    PlannerFailureStage,
)
from data_agent.v2.provider_authorization import (
    ProviderAuthorizationStatus,
    ProviderAuthorizationStore,
)
from data_agent.v2.planning_budget import (
    PlanningContextEstimate,
    PlanningContextTooLarge,
    PlanningContextWindowUnknown,
)
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
    pd.DataFrame(
        {"unit_id": ["u1", "u2", "u3"], "sales": [10, 20, 30]}
    ).to_csv(inbox / "sales.csv", index=False)
    monkeypatch.setattr(
        config_module,
        "_config",
        AgentConfig(
            WORKSPACE_DIR=workspace,
            SESSIONS_DIR=tmp_path / "sessions",
            MODEL_ID="provider/test-model",
            MODEL_CONTEXT_WINDOW=128000,
        ),
    )
    return create_app().test_client()


def _issue_authorization(
    client,
    *,
    session_id: str,
    question: str,
    client_action_id: str,
    planning_input_id: str = "",
) -> str:
    payload = {
        "session_id": session_id,
        "filename": "sales.csv",
        "question": question,
        "client_action_id": client_action_id,
        "purpose": "analysis_planning",
        "provider_calls_authorized": 1,
        "confirm_provider_call": True,
    }
    if planning_input_id:
        payload["planning_input_id"] = planning_input_id
    response = client.post(
        "/api/v2/provider-authorizations",
        json=payload,
    )
    assert response.status_code == 201
    return response.get_json()["authorization_id"]


class FakePlanner:
    calls = 0
    model_id = "provider/test-model"

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
            model_id=self.model_id,
        )


class FakeNeedsInputPlanner:
    model_id = "provider/test-model"

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
            model_id=self.model_id,
            pending_analysis_kind=AnalysisKind.GROUP_COMPARISON,
            missing_prerequisites=("analysis_unit_semantics",),
        )


class FakeFailedPlanner:
    calls = 0
    model_id = "provider/test-model"

    def plan(self, question, context, *, clarifications=()):
        type(self).calls += 1
        raise RuntimeError("provider unavailable")


class FakeClarifiedPlanner:
    calls = 0
    clarifications = ()
    confirmed_analysis_unit_column = ""
    model_id = "provider/test-model"

    def plan(self, question, context, *, clarifications=()):
        type(self).calls += 1
        type(self).clarifications = tuple(clarifications)
        type(self).confirmed_analysis_unit_column = (
            context.confirmed_analysis_unit_column
        )
        return AnalysisPlan(
            status=PlanStatus.READY,
            user_question=question,
            analysis_kind=AnalysisKind.DESCRIPTIVE,
            parameters={"metric": "sales"},
            rationale="根据用户补充选择描述分析。",
            questions=(),
            maximum_claim_class="descriptive",
            planner_invocations=1,
            model_id=self.model_id,
        )


def _estimate(*, estimated=500, available=120000):
    return PlanningContextEstimate(
        model_id="provider/test-model",
        estimated_input_tokens=estimated,
        model_context_window_tokens=128000,
        reserved_output_tokens=8000,
        available_input_tokens=available,
        fits=estimated <= available,
    )


class FakePlanningBudget:
    def __init__(self, estimate=None, error=None):
        self.value = estimate or _estimate()
        self.error = error

    def require_fits(self, question, context, *, clarifications=()):
        if self.error:
            raise self.error
        return self.value


def test_plan_api_rejects_client_asserted_or_unknown_authorization(
    monkeypatch, tmp_path
):
    client = _client(monkeypatch, tmp_path)
    asserted = client.post(
        "/api/v2/plans",
        json={
            "session_id": "session_plan_auth",
            "filename": "sales.csv",
            "question": "平均销售额？",
            "client_request_id": "client_plan_auth",
            "provider_calls_authorized": 1,
            "provider_authorization_ref": "user:explicit",
        },
    )
    unknown = client.post(
        "/api/v2/plans",
        json={
            "session_id": "session_plan_auth",
            "filename": "sales.csv",
            "question": "平均销售额？",
            "client_request_id": "client_plan_auth",
            "provider_authorization_id": "provider_auth_unknown",
        },
    )

    assert asserted.status_code == 400
    assert unknown.status_code == 404


def test_authorization_api_is_explicit_idempotent_and_does_not_call_planner(
    monkeypatch, tmp_path
):
    client = _client(monkeypatch, tmp_path)
    import data_agent.web.blueprints.v2 as v2_module

    monkeypatch.setattr(
        v2_module,
        "V2_PLANNER_FACTORY",
        lambda: (_ for _ in ()).throw(AssertionError("planner must not be created")),
    )
    payload = {
        "session_id": "session_auth_api",
        "filename": "sales.csv",
        "question": "平均销售额？",
        "client_action_id": "action_auth_api",
        "purpose": "analysis_planning",
        "provider_calls_authorized": 1,
        "confirm_provider_call": True,
    }

    first = client.post("/api/v2/provider-authorizations", json=payload)
    repeated = client.post("/api/v2/provider-authorizations", json=payload)
    rejected = client.post(
        "/api/v2/provider-authorizations",
        json={
            **payload,
            "client_action_id": "action_auth_rejected",
            "confirm_provider_call": False,
        },
    )

    assert first.status_code == 201
    assert repeated.status_code == 200
    assert rejected.status_code == 400
    assert (
        first.get_json()["authorization_id"]
        == repeated.get_json()["authorization_id"]
    )
    assert first.get_json()["status"] == "issued"
    assert first.get_json()["planning_context"]["estimated_input_tokens"] > 0


def test_planning_estimate_reports_full_model_budget_without_authorization(
    monkeypatch, tmp_path
):
    client = _client(monkeypatch, tmp_path)
    import data_agent.web.blueprints.v2 as v2_module

    estimate = _estimate(estimated=1234, available=120000)
    monkeypatch.setattr(
        v2_module,
        "V2_PLANNING_BUDGET_FACTORY",
        lambda: FakePlanningBudget(estimate=estimate),
    )
    response = client.post(
        "/api/v2/planning-estimates",
        json={
            "session_id": "session_estimate",
            "filename": "sales.csv",
            "question": "平均销售额？",
        },
    )

    assert response.status_code == 200
    assert response.get_json() == estimate.to_dict()
    auth_path = (
        tmp_path
        / "sessions"
        / "session_estimate"
        / "v2"
        / "provider_authorizations.jsonl"
    )
    assert not auth_path.exists()


def test_planning_context_too_large_is_explicit_and_does_not_issue_authorization(
    monkeypatch, tmp_path
):
    client = _client(monkeypatch, tmp_path)
    import data_agent.web.blueprints.v2 as v2_module

    estimate = _estimate(estimated=120001, available=120000)
    monkeypatch.setattr(
        v2_module,
        "V2_PLANNING_BUDGET_FACTORY",
        lambda: FakePlanningBudget(error=PlanningContextTooLarge(estimate)),
    )
    response = client.post(
        "/api/v2/provider-authorizations",
        json={
            "session_id": "session_estimate_large",
            "filename": "sales.csv",
            "question": "long context",
            "client_action_id": "action_estimate_large",
            "purpose": "analysis_planning",
            "provider_calls_authorized": 1,
            "confirm_provider_call": True,
        },
    )

    body = response.get_json()
    assert response.status_code == 413
    assert body["error_code"] == "planning_context_too_large"
    assert body["planning_context"] == estimate.to_dict()
    assert not (
        tmp_path
        / "sessions"
        / "session_estimate_large"
        / "v2"
        / "provider_authorizations.jsonl"
    ).exists()


def test_plan_rechecks_context_before_consuming_authorization_or_calling_planner(
    monkeypatch, tmp_path
):
    client = _client(monkeypatch, tmp_path)
    import data_agent.web.blueprints.v2 as v2_module

    monkeypatch.setattr(
        v2_module,
        "V2_PLANNING_BUDGET_FACTORY",
        lambda: FakePlanningBudget(estimate=_estimate()),
    )
    authorization_id = _issue_authorization(
        client,
        session_id="session_budget_recheck",
        question="average sales",
        client_action_id="action_budget_recheck",
    )
    too_large = _estimate(estimated=120001, available=120000)
    monkeypatch.setattr(
        v2_module,
        "V2_PLANNING_BUDGET_FACTORY",
        lambda: FakePlanningBudget(error=PlanningContextTooLarge(too_large)),
    )
    FakePlanner.calls = 0
    monkeypatch.setattr(v2_module, "V2_PLANNER_FACTORY", lambda: FakePlanner())

    response = client.post(
        "/api/v2/plans",
        json={
            "session_id": "session_budget_recheck",
            "filename": "sales.csv",
            "question": "average sales",
            "client_request_id": "client_budget_recheck",
            "provider_authorization_id": authorization_id,
        },
    )

    assert response.status_code == 413
    assert response.get_json()["error_code"] == "planning_context_too_large"
    assert FakePlanner.calls == 0
    authorization = ProviderAuthorizationStore(
        tmp_path / "sessions", "session_budget_recheck"
    ).get(authorization_id)
    assert authorization.status is ProviderAuthorizationStatus.ISSUED


def test_plan_rejects_fit_but_changed_authorized_context_before_provider_call(
    monkeypatch, tmp_path
):
    client = _client(monkeypatch, tmp_path)
    import data_agent.web.blueprints.v2 as v2_module

    issued_estimate = _estimate(estimated=500, available=120000)
    monkeypatch.setattr(
        v2_module,
        "V2_PLANNING_BUDGET_FACTORY",
        lambda: FakePlanningBudget(estimate=issued_estimate),
    )
    authorization_id = _issue_authorization(
        client,
        session_id="session_context_drift",
        question="average sales",
        client_action_id="action_context_drift",
    )
    changed_estimate = _estimate(estimated=501, available=120000)
    monkeypatch.setattr(
        v2_module,
        "V2_PLANNING_BUDGET_FACTORY",
        lambda: FakePlanningBudget(estimate=changed_estimate),
    )
    FakePlanner.calls = 0
    monkeypatch.setattr(v2_module, "V2_PLANNER_FACTORY", lambda: FakePlanner())

    response = client.post(
        "/api/v2/plans",
        json={
            "session_id": "session_context_drift",
            "filename": "sales.csv",
            "question": "average sales",
            "client_request_id": "client_context_drift",
            "provider_authorization_id": authorization_id,
        },
    )

    assert response.status_code == 409
    assert "planning context" in response.get_json()["error"]
    assert FakePlanner.calls == 0
    authorization = ProviderAuthorizationStore(
        tmp_path / "sessions", "session_context_drift"
    ).get(authorization_id)
    assert authorization.status is ProviderAuthorizationStatus.ISSUED


def test_plan_rejects_planner_model_drift_before_consuming_or_calling(
    monkeypatch, tmp_path
):
    client = _client(monkeypatch, tmp_path)
    import data_agent.web.blueprints.v2 as v2_module

    monkeypatch.setattr(
        v2_module,
        "V2_PLANNING_BUDGET_FACTORY",
        lambda: FakePlanningBudget(estimate=_estimate()),
    )
    authorization_id = _issue_authorization(
        client,
        session_id="session_model_drift",
        question="average sales",
        client_action_id="action_model_drift",
    )

    class DriftedPlanner(FakePlanner):
        model_id = "provider/other-model"

    DriftedPlanner.calls = 0
    monkeypatch.setattr(v2_module, "V2_PLANNER_FACTORY", lambda: DriftedPlanner())
    response = client.post(
        "/api/v2/plans",
        json={
            "session_id": "session_model_drift",
            "filename": "sales.csv",
            "question": "average sales",
            "client_request_id": "client_model_drift",
            "provider_authorization_id": authorization_id,
        },
    )

    assert response.status_code == 409
    assert "planner model" in response.get_json()["error"]
    assert DriftedPlanner.calls == 0
    authorization = ProviderAuthorizationStore(
        tmp_path / "sessions", "session_model_drift"
    ).get(authorization_id)
    assert authorization.status is ProviderAuthorizationStatus.ISSUED


def test_unknown_model_window_is_not_replaced_by_an_arbitrary_limit(
    monkeypatch, tmp_path
):
    client = _client(monkeypatch, tmp_path)
    import data_agent.web.blueprints.v2 as v2_module

    monkeypatch.setattr(
        v2_module,
        "V2_PLANNING_BUDGET_FACTORY",
        lambda: FakePlanningBudget(
            error=PlanningContextWindowUnknown("configure MODEL_CONTEXT_WINDOW")
        ),
    )
    response = client.post(
        "/api/v2/planning-estimates",
        json={
            "session_id": "session_estimate_unknown",
            "filename": "sales.csv",
            "question": "average sales",
        },
    )

    assert response.status_code == 422
    assert response.get_json()["error_code"] == "planning_context_window_unknown"


def test_planning_json_routes_keep_a_one_megabyte_transport_safety_limit(
    monkeypatch, tmp_path
):
    client = _client(monkeypatch, tmp_path)
    oversized = "x" * (1024 * 1024)

    response = client.post(
        "/api/v2/sessions/session_large/plans/plan_large/answers",
        json={
            "client_reply_id": "reply_large",
            "answers": [{"question_id": "question_large", "answer": oversized}],
        },
    )

    assert response.status_code == 413
    assert response.get_json()["error_code"] == "planning_request_too_large"
    assert response.get_json()["max_request_bytes"] == 1024 * 1024


def test_plan_api_persists_ready_and_idempotent_retry_does_not_reinvoke(
    monkeypatch, tmp_path
):
    client = _client(monkeypatch, tmp_path)
    import data_agent.web.blueprints.v2 as v2_module

    FakePlanner.calls = 0
    monkeypatch.setattr(v2_module, "V2_PLANNER_FACTORY", lambda: FakePlanner())
    question = "平均销售额？"
    authorization_id = _issue_authorization(
        client,
        session_id="session_plan_api",
        question=question,
        client_action_id="action_plan_api",
    )
    request = {
        "session_id": "session_plan_api",
        "filename": "sales.csv",
        "question": question,
        "client_request_id": "client_plan_api",
        "provider_authorization_id": authorization_id,
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


def test_analyze_by_plan_persists_failed_turn_when_runtime_rejects_parameters(
    monkeypatch, tmp_path
):
    client = _client(monkeypatch, tmp_path)
    store = PlanStore(tmp_path / "sessions", "session_plan_runtime_failure")
    source = tmp_path / "workspace" / "inbox" / "sales.csv"
    requested = store.request(
        client_request_id="client_plan_runtime_failure",
        question="比较销售额",
        dataset_context={
            "filename": "sales.csv",
            "source_fingerprint": "sha256:"
            + hashlib.sha256(source.read_bytes()).hexdigest(),
            "row_count": 3,
            "columns": [{"name": "sales", "dtype": "int64", "role": "numeric"}],
        },
        provider_authorization_ref="user:explicit:runtime-failure",
        provider_calls_authorized=1,
    )
    store.complete(
        requested.plan_id,
        AnalysisPlan(
            status=PlanStatus.READY,
            user_question="比较销售额",
            analysis_kind=AnalysisKind.GROUP_COMPARISON,
            parameters={
                "metric": "sales",
                "group": "sales",
                "analysis_unit": "sales",
            },
            rationale="历史计划包含运行时不接受的字段关系。",
            questions=(),
            maximum_claim_class="inferential",
            planner_invocations=1,
            model_id="fake-planner",
        ),
    )

    response = client.post(
        "/api/v2/analyze",
        json={
            "session_id": "session_plan_runtime_failure",
            "turn_id": "turn_plan_runtime_failure",
            "plan_id": requested.plan_id,
        },
    )
    events = _events(response.get_data(as_text=True))
    restored = client.get(
        "/api/v2/sessions/session_plan_runtime_failure/turns/turn_plan_runtime_failure"
    )

    assert response.status_code == 200
    assert events[-1][0] == "turn_failed"
    assert restored.status_code == 200
    assert restored.get_json()["status"] == "failed"
    assert restored.get_json()["request_context"]["plan_id"] == requested.plan_id
    assert store.get(requested.plan_id).status is DurablePlanStatus.CONSUMED


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
    question = "比较表现"
    authorization_id = _issue_authorization(
        client,
        session_id="session_plan_needs_input",
        question=question,
        client_action_id="action_plan_needs_input",
    )
    response = client.post(
        "/api/v2/plans",
        json={
            "session_id": "session_plan_needs_input",
            "filename": "sales.csv",
            "question": question,
            "client_request_id": "client_plan_needs_input",
            "provider_authorization_id": authorization_id,
        },
    )

    body = response.get_json()
    assert response.status_code == 201
    assert body["status"] == "needs_input"
    assert body["pending_analysis_kind"] == "group_comparison"
    assert body["missing_prerequisites"] == ["analysis_unit_semantics"]
    assert body["analysis_kind"] == ""
    assert body["parameters"] == {}
    assert body["message_blocks"] == [
        {
            "type": "planning_question",
            "plan_id": body["plan_id"],
            "question_id": f"{body['plan_id']}_question_1",
            "text": "每行代表订单还是客户？",
        }
    ]
    blocked = client.post(
        "/api/v2/analyze",
        json={
            "session_id": "session_plan_needs_input",
            "plan_id": body["plan_id"],
        },
    )
    assert blocked.status_code == 409


def test_needs_input_answer_is_refreshable_and_derives_new_authorized_plan(
    monkeypatch, tmp_path
):
    client = _client(monkeypatch, tmp_path)
    import data_agent.web.blueprints.v2 as v2_module

    session_id = "session_plan_answer"
    question = "比较表现"
    monkeypatch.setattr(
        v2_module, "V2_PLANNER_FACTORY", lambda: FakeNeedsInputPlanner()
    )
    initial_authorization = _issue_authorization(
        client,
        session_id=session_id,
        question=question,
        client_action_id="action_plan_answer_initial",
    )
    needs_input = client.post(
        "/api/v2/plans",
        json={
            "session_id": session_id,
            "filename": "sales.csv",
            "question": question,
            "client_request_id": "client_plan_answer_initial",
            "provider_authorization_id": initial_authorization,
        },
    ).get_json()
    question_block = needs_input["message_blocks"][0]

    answer = client.post(
        f"/api/v2/sessions/{session_id}/plans/{needs_input['plan_id']}/answers",
        json={
            "client_reply_id": "reply_plan_answer",
            "answers": [
                {
                    "question_id": question_block["question_id"],
                    "answer": "每行代表订单；比较销售额。",
                }
            ],
            "semantic_resolutions": [
                {
                    "prerequisite_code": "analysis_unit_semantics",
                    "column": "unit_id",
                }
            ],
        },
    )
    planning_input = answer.get_json()
    restored = client.get(
        f"/api/v2/sessions/{session_id}/planning-inputs/"
        f"{planning_input['planning_input_id']}"
    )

    assert answer.status_code == 201
    assert restored.status_code == 200
    assert restored.get_json() == planning_input
    assert PlanStore(tmp_path / "sessions", session_id).get(
        needs_input["plan_id"]
    ).status is DurablePlanStatus.NEEDS_INPUT
    assert planning_input["semantic_resolutions"] == [
        {
            "prerequisite_code": "analysis_unit_semantics",
            "column": "unit_id",
        }
    ]

    FakeClarifiedPlanner.calls = 0
    FakeClarifiedPlanner.clarifications = ()
    monkeypatch.setattr(
        v2_module, "V2_PLANNER_FACTORY", lambda: FakeClarifiedPlanner()
    )
    derived_authorization = _issue_authorization(
        client,
        session_id=session_id,
        question=question,
        client_action_id="action_plan_answer_derived",
        planning_input_id=planning_input["planning_input_id"],
    )
    derived_request = {
        "session_id": session_id,
        "filename": "sales.csv",
        "question": question,
        "client_request_id": "client_plan_answer_derived",
        "provider_authorization_id": derived_authorization,
        "planning_input_id": planning_input["planning_input_id"],
    }
    derived = client.post("/api/v2/plans", json=derived_request)
    repeated = client.post("/api/v2/plans", json=derived_request)

    assert derived.status_code == 201
    assert repeated.status_code == 200
    assert derived.get_json()["status"] == "ready"
    assert derived.get_json()["parent_plan_id"] == needs_input["plan_id"]
    assert (
        derived.get_json()["planning_input_id"]
        == planning_input["planning_input_id"]
    )
    assert FakeClarifiedPlanner.calls == 1
    assert FakeClarifiedPlanner.clarifications == (
        {
            "question": "每行代表订单还是客户？",
            "answer": "每行代表订单；比较销售额。",
        },
    )
    assert FakeClarifiedPlanner.confirmed_analysis_unit_column == "unit_id"


def test_semantic_needs_input_rejects_missing_or_unknown_column_resolution(
    monkeypatch, tmp_path
):
    client = _client(monkeypatch, tmp_path)
    import data_agent.web.blueprints.v2 as v2_module

    session_id = "session_plan_semantic_resolution"
    question = "比较表现"
    monkeypatch.setattr(
        v2_module, "V2_PLANNER_FACTORY", lambda: FakeNeedsInputPlanner()
    )
    authorization_id = _issue_authorization(
        client,
        session_id=session_id,
        question=question,
        client_action_id="action_semantic_resolution",
    )
    needs_input = client.post(
        "/api/v2/plans",
        json={
            "session_id": session_id,
            "filename": "sales.csv",
            "question": question,
            "client_request_id": "client_semantic_resolution",
            "provider_authorization_id": authorization_id,
        },
    ).get_json()
    answer = {
        "question_id": needs_input["message_blocks"][0]["question_id"],
        "answer": "unit_id 表示独立观察单位。",
    }

    missing = client.post(
        f"/api/v2/sessions/{session_id}/plans/{needs_input['plan_id']}/answers",
        json={
            "client_reply_id": "reply_semantic_missing",
            "answers": [answer],
        },
    )
    unknown = client.post(
        f"/api/v2/sessions/{session_id}/plans/{needs_input['plan_id']}/answers",
        json={
            "client_reply_id": "reply_semantic_unknown",
            "answers": [answer],
            "semantic_resolutions": [
                {
                    "prerequisite_code": "analysis_unit_semantics",
                    "column": "customer_id",
                }
            ],
        },
    )

    assert missing.status_code == 400
    assert "exactly match" in missing.get_json()["error"]
    assert unknown.status_code == 400
    assert "existing column" in unknown.get_json()["error"]
    assert PlanningInputStore(tmp_path / "sessions", session_id).list_all() == []


def test_failed_plan_is_durable_and_same_request_does_not_retry_provider(
    monkeypatch, tmp_path
):
    client = _client(monkeypatch, tmp_path)
    import data_agent.web.blueprints.v2 as v2_module

    FakeFailedPlanner.calls = 0
    monkeypatch.setattr(v2_module, "V2_PLANNER_FACTORY", lambda: FakeFailedPlanner())
    question = "平均销售额？"
    authorization_id = _issue_authorization(
        client,
        session_id="session_plan_failed",
        question=question,
        client_action_id="action_plan_failed",
    )
    request = {
        "session_id": "session_plan_failed",
        "filename": "sales.csv",
        "question": question,
        "client_request_id": "client_plan_failed",
        "provider_authorization_id": authorization_id,
    }
    failed = client.post("/api/v2/plans", json=request)
    repeated = client.post("/api/v2/plans", json=request)

    assert failed.status_code == 502
    assert failed.get_json()["plan"]["status"] == "failed"
    assert failed.get_json()["plan"]["provider_calls"] == 1
    assert repeated.status_code == 200
    assert repeated.get_json()["status"] == "failed"
    assert FakeFailedPlanner.calls == 1


def test_planner_contract_failure_returns_stable_safe_http_error_and_persists_diagnostic(
    monkeypatch, tmp_path
):
    client = _client(monkeypatch, tmp_path)
    import data_agent.web.blueprints.v2 as v2_module

    class ContractFailedPlanner:
        calls = 0
        model_id = "provider/test-model"

        def plan(self, question, context, *, clarifications=()):
            type(self).calls += 1
            raise PlannerContractError(
                "unexpected planner fields: finding",
                reason_code="plan_unexpected_fields",
                failure_stage=PlannerFailureStage.PLAN_COMPILATION,
                diagnostic={
                    "failure_stage": "plan_compilation",
                    "finish_reason": "tool_calls",
                    "tool_call_count": 1,
                    "tool_names": ["submit_analysis_plan"],
                    "tool_argument_types": ["dict"],
                    "argument_top_level_fields": ["finding", "parameters"],
                    "metadata_truncated": False,
                },
            )

    monkeypatch.setattr(
        v2_module, "V2_PLANNER_FACTORY", lambda: ContractFailedPlanner()
    )
    authorization_id = _issue_authorization(
        client,
        session_id="session_contract_diagnostic",
        question="average sales",
        client_action_id="action_contract_diagnostic",
    )
    response = client.post(
        "/api/v2/plans",
        json={
            "session_id": "session_contract_diagnostic",
            "filename": "sales.csv",
            "question": "average sales",
            "client_request_id": "client_contract_diagnostic",
            "provider_authorization_id": authorization_id,
        },
    )

    body = response.get_json()
    assert response.status_code == 502
    assert body["error"] == "planning failed"
    assert body["error_code"] == "planner_contract_error"
    assert body["reason_code"] == "plan_unexpected_fields"
    assert body["failure_stage"] == "plan_compilation"
    assert "finding" not in json.dumps(body)
    restored = PlanStore(
        tmp_path / "sessions", "session_contract_diagnostic"
    ).get(body["plan"]["plan_id"])
    assert restored.error_reason_code == "plan_unexpected_fields"
    assert restored.diagnostic["argument_top_level_fields"] == [
        "finding",
        "parameters",
    ]


def test_failed_derived_plan_retries_only_with_new_explicit_authorization(
    monkeypatch, tmp_path
):
    client = _client(monkeypatch, tmp_path)
    import data_agent.web.blueprints.v2 as v2_module

    session_id = "session_plan_derived_retry"
    question = "比较表现"
    monkeypatch.setattr(
        v2_module, "V2_PLANNER_FACTORY", lambda: FakeNeedsInputPlanner()
    )
    initial_authorization = _issue_authorization(
        client,
        session_id=session_id,
        question=question,
        client_action_id="action_derived_retry_initial",
    )
    needs_input = client.post(
        "/api/v2/plans",
        json={
            "session_id": session_id,
            "filename": "sales.csv",
            "question": question,
            "client_request_id": "client_derived_retry_initial",
            "provider_authorization_id": initial_authorization,
        },
    ).get_json()
    planning_input = client.post(
        f"/api/v2/sessions/{session_id}/plans/{needs_input['plan_id']}/answers",
        json={
            "client_reply_id": "reply_derived_retry",
            "answers": [
                {
                    "question_id": needs_input["message_blocks"][0]["question_id"],
                    "answer": "每行代表订单；比较销售额。",
                }
            ],
            "semantic_resolutions": [
                {
                    "prerequisite_code": "analysis_unit_semantics",
                    "column": "unit_id",
                }
            ],
        },
    ).get_json()

    FakeFailedPlanner.calls = 0
    monkeypatch.setattr(v2_module, "V2_PLANNER_FACTORY", lambda: FakeFailedPlanner())
    failed_authorization = _issue_authorization(
        client,
        session_id=session_id,
        question=question,
        client_action_id="action_derived_retry_failed",
        planning_input_id=planning_input["planning_input_id"],
    )
    failed_request = {
        "session_id": session_id,
        "filename": "sales.csv",
        "question": question,
        "client_request_id": "client_derived_retry_failed",
        "provider_authorization_id": failed_authorization,
        "planning_input_id": planning_input["planning_input_id"],
    }
    failed = client.post("/api/v2/plans", json=failed_request)
    replayed = client.post("/api/v2/plans", json=failed_request)

    assert failed.status_code == 502
    assert replayed.status_code == 200
    assert replayed.get_json()["status"] == "failed"
    assert FakeFailedPlanner.calls == 1

    FakeClarifiedPlanner.calls = 0
    monkeypatch.setattr(
        v2_module, "V2_PLANNER_FACTORY", lambda: FakeClarifiedPlanner()
    )
    retry_authorization = _issue_authorization(
        client,
        session_id=session_id,
        question=question,
        client_action_id="action_derived_retry_explicit",
        planning_input_id=planning_input["planning_input_id"],
    )
    retried = client.post(
        "/api/v2/plans",
        json={
            **failed_request,
            "client_request_id": "client_derived_retry_explicit",
            "provider_authorization_id": retry_authorization,
        },
    )

    assert retried.status_code == 201
    assert retried.get_json()["status"] == "ready"
    assert FakeClarifiedPlanner.calls == 1
    records = ProviderAuthorizationStore(
        tmp_path / "sessions", session_id
    ).list_all()
    assert len(records) == 3
    assert all(item.status is ProviderAuthorizationStatus.CONSUMED for item in records)


def test_incomplete_requested_plan_requires_new_authorization_and_is_not_retried(
    monkeypatch, tmp_path
):
    client = _client(monkeypatch, tmp_path)
    source = tmp_path / "workspace" / "inbox" / "sales.csv"
    question = "平均销售额？"
    authorization_id = _issue_authorization(
        client,
        session_id="session_plan_incomplete",
        question=question,
        client_action_id="action_plan_incomplete",
    )
    authorization_store = ProviderAuthorizationStore(
        tmp_path / "sessions", "session_plan_incomplete"
    )
    authorization = authorization_store.get(authorization_id)
    authorization_store.consume(
        authorization_id,
        client_request_id="client_plan_incomplete",
        purpose="analysis_planning",
        filename="sales.csv",
        source_fingerprint=(
            "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()
        ),
        question=question,
        model_id=authorization.model_id,
        planning_context=authorization.planning_context,
    )
    store = PlanStore(tmp_path / "sessions", "session_plan_incomplete")
    store.request(
        client_request_id="client_plan_incomplete",
        question=question,
        dataset_context=DatasetPlanningContext.from_frame(
            filename="sales.csv",
            source_fingerprint=(
                "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()
            ),
            frame=pd.read_csv(source),
        ).to_prompt_dict(),
        provider_authorization_ref=authorization_id,
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
            "question": question,
            "client_request_id": "client_plan_incomplete",
            "provider_authorization_id": authorization_id,
        },
    )

    assert response.status_code == 409
    assert "new request identity and authorization" in response.get_json()["error"]
    assert FakePlanner.calls == 0
