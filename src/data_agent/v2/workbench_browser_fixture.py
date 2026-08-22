from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import pandas as pd
from flask import jsonify

import data_agent.config as config_module
from data_agent.config import AgentConfig
from data_agent.v2.planner import AnalysisKind, AnalysisPlan, PlanStatus
from data_agent.v2.planning_input import PlanningInputStore
from data_agent.v2.planning_budget import (
    PlanningContextEstimate,
    PlanningContextTooLarge,
)
from data_agent.v2.provider_authorization import ProviderAuthorizationStatus
from data_agent.v2.router import AnalysisRouter, PreparedAnalysis
from data_agent.web.app import create_app


class DeterministicJourneyPlanner:
    """Three-call fake Planner: needs input, fails, then succeeds."""

    model_id = "provider-neutral-fixture"

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
                pending_analysis_kind=AnalysisKind.MULTI_FINDING_SYNTHESIS,
                missing_prerequisites=("compatible_column_binding",),
            )
        if self.calls == 2:
            raise RuntimeError("synthetic provider failure")
        if self.calls == 3:
            return AnalysisPlan(
                status=PlanStatus.READY,
                user_question=question,
                analysis_kind=AnalysisKind.MULTI_FINDING_SYNTHESIS,
                parameters={
                    "time_field": "date",
                    "metric": "sales",
                    "frequency": "daily",
                    "aggregation": "mean",
                    "group": "channel",
                    "analysis_unit": "unit_id",
                },
                rationale="根据已持久化的业务语义执行趋势与双组综合分析。",
                questions=(),
                maximum_claim_class="inferential",
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


class DelayedPreparedAnalysis:
    """Preserve the real runtime while opening deterministic UI interaction gaps."""

    def __init__(self, prepared: PreparedAnalysis, delay_seconds: float) -> None:
        self.prepared = prepared
        self.delay_seconds = max(0.0, float(delay_seconds))

    def stream(self):
        for event in self.prepared.stream():
            yield event
            if self.delay_seconds:
                time.sleep(self.delay_seconds)


class DelayedAnalysisRouter(AnalysisRouter):
    def __init__(self, sessions_root, inbox_root, *, delay_seconds: float = 1.0):
        super().__init__(sessions_root, inbox_root)
        self.delay_seconds = delay_seconds

    def prepare(self, **kwargs):
        return DelayedPreparedAnalysis(
            super().prepare(**kwargs), self.delay_seconds
        )


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
        / "v2_slice4d_combined.csv"
    )
    fixture_csv = repository_fixture if repository_fixture.is_file() else root / "planning_journey.csv"
    if not fixture_csv.is_file():
        pd.DataFrame(
            {
                "date": ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"],
                "unit_id": ["u1", "u2", "u3", "u4"],
                "channel": ["A", "B", "A", "B"],
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
    v2_module.V2_ROUTER_FACTORY = lambda sessions_root, inbox_root: DelayedAnalysisRouter(
        sessions_root, inbox_root
    )
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
        turns = []
        for path in sessions.glob("*/v2/turns/*.json"):
            value = json.loads(path.read_text(encoding="utf-8"))
            turns.append(
                {
                    "session_id": path.parents[2].name,
                    "turn_id": path.stem,
                    "status": value.get("status"),
                    "block_count": len(value.get("blocks") or ()),
                    "question": (value.get("request_context") or {}).get("question", ""),
                }
            )
        planning_inputs = []
        for path in sessions.glob("*/v2/planning_inputs.jsonl"):
            session_id = path.parents[1].name
            for record in PlanningInputStore(sessions, session_id).list_all():
                answers = []
                for answer in record.answers:
                    text = answer["answer"]
                    answers.append(
                        {
                            "question_id": answer["question_id"],
                            "characters": len(text),
                            "digest": "sha256:"
                            + hashlib.sha256(text.encode("utf-8")).hexdigest(),
                        }
                    )
                planning_inputs.append(
                    {
                        "session_id": session_id,
                        "planning_input_id": record.planning_input_id,
                        "answers": answers,
                    }
                )
        return jsonify(
            {
                "fixture_id": "v2_workbench_planning_failure_retry.v1",
                "fixture_csv": str(fixture_csv),
                "planner_invocations": planner.calls,
                "authorizations_issued": issued,
                "authorizations_consumed": consumed,
                "provider_calls": 0,
                "planning_inputs": sorted(
                    planning_inputs,
                    key=lambda item: (item["session_id"], item["planning_input_id"]),
                ),
                "turns": sorted(
                    turns, key=lambda item: (item["session_id"], item["turn_id"])
                ),
            }
        )

    return app
