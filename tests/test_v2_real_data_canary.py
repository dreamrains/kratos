from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

import data_agent.config as config_module
from data_agent.config import AgentConfig
from data_agent.v2.planner import AnalysisKind, AnalysisPlan, PlanStatus
from data_agent.v2.planning_budget import PlanningContextEstimate
from data_agent.web.app import create_app


REFERENCE_DATA = (
    Path(__file__).resolve().parents[1]
    / "reference"
    / "test_doc"
    / "游戏A内购数据.xlsx"
)


def _events(raw: str) -> list[tuple[str, dict[str, object]]]:
    events: list[tuple[str, dict[str, object]]] = []
    event = ""
    data = ""
    for line in raw.splitlines():
        if line.startswith("event: "):
            event = line.removeprefix("event: ")
        elif line.startswith("data: "):
            data = line.removeprefix("data: ")
        elif not line and event and data:
            events.append((event, json.loads(data)))
            event = ""
            data = ""
    return events


class _OfflinePlanner:
    """A local contract fixture: it is not an LLM or a Provider client."""

    calls = 0
    model_id = "offline/canary-planner"

    def plan(self, question, context):
        type(self).calls += 1
        return AnalysisPlan(
            status=PlanStatus.READY,
            user_question=question,
            analysis_kind=AnalysisKind.TIME_TREND,
            parameters={
                "time_field": "日期",
                "metric": "内购收入",
                "frequency": "daily",
                "aggregation": "sum",
            },
            rationale="按日汇总内购收入，检查时间趋势。",
            questions=(),
            maximum_claim_class="descriptive",
            planner_invocations=1,
            model_id=self.model_id,
        )


class _OfflinePlanningBudget:
    def require_fits(self, question, context, *, clarifications=()):
        return PlanningContextEstimate(
            model_id=_OfflinePlanner.model_id,
            estimated_input_tokens=512,
            model_context_window_tokens=32_768,
            reserved_output_tokens=4_096,
            available_input_tokens=28_672,
            fits=True,
        )


@pytest.mark.skipif(
    not REFERENCE_DATA.exists(), reason="reference/test_doc fixture not found"
)
def test_real_excel_offline_canary_runs_upload_preflight_plan_and_execution(
    monkeypatch, tmp_path
):
    """One representative workbook crosses the V2 boundary without a Provider."""

    workspace = tmp_path / "workspace"
    monkeypatch.setattr(
        config_module,
        "_config",
        AgentConfig(
            WORKSPACE_DIR=workspace,
            SESSIONS_DIR=tmp_path / "sessions",
            MODEL_ID=_OfflinePlanner.model_id,
            MODEL_CONTEXT_WINDOW=32_768,
        ),
    )
    import data_agent.web.blueprints.v2 as v2_module

    _OfflinePlanner.calls = 0
    monkeypatch.setattr(v2_module, "V2_PLANNER_FACTORY", _OfflinePlanner)
    monkeypatch.setattr(
        v2_module, "V2_PLANNING_BUDGET_FACTORY", _OfflinePlanningBudget
    )
    client = create_app().test_client()
    session_id = "real_excel_canary"
    question = "内购收入按日如何变化？"

    upload = client.post(
        "/api/upload",
        data={
            "file": (
                io.BytesIO(REFERENCE_DATA.read_bytes()),
                REFERENCE_DATA.name,
            )
        },
        content_type="multipart/form-data",
    )
    assert upload.status_code == 200
    assert upload.get_json()["filename"] == REFERENCE_DATA.name
    assert upload.get_json()["size"] == REFERENCE_DATA.stat().st_size

    estimate = client.post(
        "/api/v2/planning-estimates",
        json={
            "session_id": session_id,
            "filename": REFERENCE_DATA.name,
            "question": question,
        },
    )
    assert estimate.status_code == 200
    estimate_body = estimate.get_json()
    assert estimate_body["model_id"] == _OfflinePlanner.model_id
    assert estimate_body["fits"] is True
    assert "内购收入" in estimate_body["semantic_options"]["analysis_unit_columns"]

    authorization = client.post(
        "/api/v2/provider-authorizations",
        json={
            "session_id": session_id,
            "filename": REFERENCE_DATA.name,
            "question": question,
            "client_action_id": "real_excel_canary_offline_only",
            "purpose": "analysis_planning",
            "provider_calls_authorized": 1,
            "confirm_provider_call": True,
        },
    )
    assert authorization.status_code == 201

    plan = client.post(
        "/api/v2/plans",
        json={
            "session_id": session_id,
            "filename": REFERENCE_DATA.name,
            "question": question,
            "client_request_id": "real_excel_canary_plan",
            "provider_authorization_id": authorization.get_json()["authorization_id"],
        },
    )
    assert plan.status_code == 201
    plan_body = plan.get_json()
    assert plan_body["status"] == "ready"
    assert plan_body["parameters"]["metric"] == "内购收入"
    assert _OfflinePlanner.calls == 1

    execution = client.post(
        "/api/v2/analyze",
        json={
            "session_id": session_id,
            "turn_id": "real_excel_canary_turn",
            "plan_id": plan_body["plan_id"],
        },
    )
    events = _events(execution.get_data(as_text=True))
    assert execution.status_code == 200
    assert events[0][0] == "turn_started"
    assert events[-1][0] == "turn_completed"

    restored = client.get(
        f"/api/v2/sessions/{session_id}/turns/real_excel_canary_turn"
    ).get_json()
    assert restored["status"] == "finalized"
    assert restored["request_context"]["analysis_kind"] == "time_trend"
    assert restored["blocks"]
    assert restored["artifacts"]
