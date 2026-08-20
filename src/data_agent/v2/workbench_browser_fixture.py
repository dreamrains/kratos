from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from flask import jsonify

import data_agent.config as config_module
from data_agent.config import AgentConfig
from data_agent.v2.planner import AnalysisKind, AnalysisPlan, PlanStatus
from data_agent.v2.planning_budget import (
    PlanningContextEstimate,
    PlanningContextTooLarge,
)
from data_agent.v2.provider_authorization import ProviderAuthorizationStatus
from data_agent.web.app import create_app


class DeterministicJourneyPlanner:
    """Three-call fake Planner: needs input, fails, then succeeds."""

    def __init__(self) -> None:
        self.calls = 0

    def plan(self, question, context, *, clarifications=()):
        self.calls += 1
        if self.calls == 1:
            return AnalysisPlan(
                status=PlanStatus.NEEDS_INPUT,
                user_question=question,
                analysis_kind=None,
                parameters={},
                rationale="需要确认每行数据所代表的分析单位。",
                questions=("每行代表订单还是客户？",),
                maximum_claim_class="",
                planner_invocations=1,
                model_id="provider-neutral-fixture",
            )
        if self.calls == 2:
            raise RuntimeError("synthetic provider failure")
        if self.calls == 3:
            return AnalysisPlan(
                status=PlanStatus.READY,
                user_question=question,
                analysis_kind=AnalysisKind.DESCRIPTIVE,
                parameters={"metric": "sales"},
                rationale="根据已持久化的业务语义执行描述分析。",
                questions=(),
                maximum_claim_class="descriptive",
                planner_invocations=1,
                model_id="provider-neutral-fixture",
            )
        raise AssertionError("browser fixture observed an unexpected hidden retry")


class DeterministicPlanningBudget:
    def require_fits(self, question, context, *, clarifications=()):
        estimated = 320 + sum(
            len(item["question"]) + len(item["answer"])
            for item in clarifications
        )
        estimate = PlanningContextEstimate(
            model_id="provider-neutral-fixture",
            estimated_input_tokens=estimated,
            model_context_window_tokens=128_000,
            reserved_output_tokens=8_000,
            available_input_tokens=120_000,
            fits=True,
        )
        if str(question).startswith("[TOO_LARGE]"):
            raise PlanningContextTooLarge(
                PlanningContextEstimate(
                    model_id=estimate.model_id,
                    estimated_input_tokens=120_001,
                    model_context_window_tokens=estimate.model_context_window_tokens,
                    reserved_output_tokens=estimate.reserved_output_tokens,
                    available_input_tokens=estimate.available_input_tokens,
                    fits=False,
                )
            )
        return estimate


def build_provider_neutral_fixture(root: Path):
    """Build an isolated actual-HTTP fixture that can never call a Provider."""

    root = Path(root).resolve()
    workspace = root / "workspace"
    sessions = root / "sessions"
    workspace.mkdir(parents=True, exist_ok=True)
    sessions.mkdir(parents=True, exist_ok=True)
    repository_fixture = (
        Path(__file__).resolve().parents[3]
        / "tests"
        / "fixtures"
        / "v2_slice1_sales.csv"
    )
    fixture_csv = repository_fixture if repository_fixture.is_file() else root / "planning_journey.csv"
    if not fixture_csv.is_file():
        pd.DataFrame(
            {
                "order_id": ["o1", "o2", "o3", "o4"],
                "sales": [10.0, 20.0, 30.0, 40.0],
            }
        ).to_csv(fixture_csv, index=False)

    config_module._config = AgentConfig(
        WORKSPACE_DIR=workspace,
        SESSIONS_DIR=sessions,
        MODEL_CONTEXT_WINDOW=128_000,
    )
    planner = DeterministicJourneyPlanner()
    budget = DeterministicPlanningBudget()
    import data_agent.web.blueprints.v2 as v2_module

    v2_module.V2_PLANNER_FACTORY = lambda: planner
    v2_module.V2_PLANNING_BUDGET_FACTORY = lambda: budget
    app = create_app()
    app.config.update(
        TESTING=False,
        PROVIDER_NEUTRAL_FIXTURE=True,
        PROVIDER_NEUTRAL_FIXTURE_CSV=str(fixture_csv),
    )

    @app.get("/__acceptance/state")
    def acceptance_state():
        issued = 0
        consumed = 0
        for path in sessions.glob("*/v2/provider_authorizations.jsonl"):
            records: dict[str, str] = {}
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                event = json.loads(line)
                records[event["authorization_id"]] = event["event_type"]
            issued += len(records)
            consumed += sum(
                status == ProviderAuthorizationStatus.CONSUMED.value
                for status in records.values()
            )
        return jsonify(
            {
                "fixture_id": "v2_workbench_planning_failure_retry.v1",
                "fixture_csv": str(fixture_csv),
                "planner_invocations": planner.calls,
                "authorizations_issued": issued,
                "authorizations_consumed": consumed,
                "provider_calls": 0,
            }
        )

    return app
