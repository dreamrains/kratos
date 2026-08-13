from __future__ import annotations

import json

import pandas as pd
import pytest

import data_agent.llm.client as llm_client_module
from data_agent.llm.client import LLMClient, Response, ToolCall
from data_agent.v2.planner import (
    ColumnRole,
    DatasetColumnContext,
    DatasetPlanningContext,
    PlanStatus,
    PlannerContractError,
    StructuredAnalysisPlanner,
)
from data_agent.v2.router import AnalysisKind


def _context() -> DatasetPlanningContext:
    return DatasetPlanningContext(
        filename="sales.csv",
        source_fingerprint="sha256:" + "a" * 64,
        row_count=120,
        columns=(
            DatasetColumnContext("date", "object", ColumnRole.DATETIME),
            DatasetColumnContext("sales", "float64", ColumnRole.NUMERIC),
            DatasetColumnContext("channel", "object", ColumnRole.CATEGORICAL),
            DatasetColumnContext("unit_id", "object", ColumnRole.IDENTIFIER),
            DatasetColumnContext("marketing", "float64", ColumnRole.NUMERIC),
        ),
    )


class FakePlannerClient:
    model_id = "fake-planner"

    def __init__(self, arguments: dict, *, text: str = "") -> None:
        self.arguments = arguments
        self.text = text
        self.calls = []

    def chat_once(self, messages, tools=None, system=None):
        self.calls.append({"messages": messages, "tools": tools, "system": system})
        return Response(
            text=self.text,
            tool_calls=[ToolCall("call_plan", "submit_analysis_plan", self.arguments)],
        )


def test_planner_compiles_ready_group_plan_from_one_structured_call():
    client = FakePlannerClient(
        {
            "status": "ready",
            "analysis_kind": "group_comparison",
            "parameters": {
                "metric": "sales",
                "group": "channel",
                "analysis_unit": "unit_id",
            },
            "rationale": "比较渠道间销售额分布并报告不确定性。",
            "questions": [],
        }
    )
    planner = StructuredAnalysisPlanner(client)

    result = planner.plan("不同渠道的销售额是否有差异？", _context())

    assert result.status is PlanStatus.READY
    assert result.analysis_kind is AnalysisKind.GROUP_COMPARISON
    assert result.user_question == "不同渠道的销售额是否有差异？"
    assert result.parameters["metric"] == "sales"
    assert result.maximum_claim_class == "inferential"
    assert result.planner_invocations == 1
    assert result.model_id == "fake-planner"
    assert len(client.calls) == 1
    assert client.calls[0]["tools"][0]["name"] == "submit_analysis_plan"
    assert "原始行" not in str(client.calls[0]["messages"])


def test_planner_rejects_nonexistent_or_wrong_role_columns():
    missing = FakePlannerClient(
        {
            "status": "ready",
            "analysis_kind": "time_trend",
            "parameters": {
                "metric": "profit",
                "time_field": "date",
                "frequency": "daily",
                "aggregation": "sum",
            },
            "rationale": "估计趋势。",
            "questions": [],
        }
    )
    wrong_role = FakePlannerClient(
        {
            "status": "ready",
            "analysis_kind": "descriptive",
            "parameters": {"metric": "channel"},
            "rationale": "描述指标。",
            "questions": [],
        }
    )

    with pytest.raises(PlannerContractError, match="unknown column: profit"):
        StructuredAnalysisPlanner(missing).plan("利润趋势？", _context())
    with pytest.raises(PlannerContractError, match="metric must be numeric"):
        StructuredAnalysisPlanner(wrong_role).plan("渠道均值？", _context())


def test_planner_needs_input_does_not_create_executable_route():
    client = FakePlannerClient(
        {
            "status": "needs_input",
            "analysis_kind": "",
            "parameters": {},
            "rationale": "用户没有说明每行代表订单还是客户。",
            "questions": ["每行数据代表一笔订单，还是一个客户？"],
        }
    )

    result = StructuredAnalysisPlanner(client).plan("比较不同渠道表现", _context())

    assert result.status is PlanStatus.NEEDS_INPUT
    assert result.analysis_kind is None
    assert result.questions == ("每行数据代表一笔订单，还是一个客户？",)


def test_planner_receives_clarifications_as_bounded_data():
    client = FakePlannerClient(
        {
            "status": "ready",
            "analysis_kind": "descriptive",
            "parameters": {"metric": "sales"},
            "rationale": "用户确认分析单位后描述销售额。",
            "questions": [],
        }
    )

    result = StructuredAnalysisPlanner(client).plan(
        "比较表现",
        _context(),
        clarifications=(
            {
                "question": "每行代表订单还是客户？",
                "answer": "每行代表订单。",
            },
        ),
    )

    payload = json.loads(client.calls[0]["messages"][0]["content"])
    assert result.status is PlanStatus.READY
    assert payload["clarifications"] == [
        {
            "question": "每行代表订单还是客户？",
            "answer": "每行代表订单。",
        }
    ]
    assert "clarifications" in client.calls[0]["system"]


def test_planner_can_report_unsupported_without_inventing_a_fallback():
    client = FakePlannerClient(
        {
            "status": "unsupported",
            "analysis_kind": "",
            "parameters": {},
            "rationale": "当前方法目录不支持从观察数据识别因果效应。",
            "questions": [],
        }
    )

    result = StructuredAnalysisPlanner(client).plan(
        "渠道是否导致销售额上升？", _context()
    )

    assert result.status is PlanStatus.UNSUPPORTED
    assert result.analysis_kind is None
    assert result.maximum_claim_class == ""


def test_planner_rejects_free_text_or_exploratory_python_as_execution_plan():
    text_only = FakePlannerClient({}, text='{"analysis_kind":"descriptive"}')
    text_only.chat_once = lambda messages, tools=None, system=None: Response(
        text='{"analysis_kind":"descriptive"}'
    )
    exploratory = FakePlannerClient(
        {
            "status": "ready",
            "analysis_kind": "exploratory_python",
            "parameters": {"metric": "sales", "code": "print(data)"},
            "rationale": "自由探索。",
            "questions": [],
        }
    )

    with pytest.raises(PlannerContractError, match="exactly one submit_analysis_plan"):
        StructuredAnalysisPlanner(text_only).plan("描述销售额", _context())
    with pytest.raises(PlannerContractError, match="not available to automatic planning"):
        StructuredAnalysisPlanner(exploratory).plan("随便探索", _context())


def test_planner_rejects_hidden_result_fields_in_tool_arguments():
    client = FakePlannerClient(
        {
            "status": "ready",
            "analysis_kind": "descriptive",
            "parameters": {"metric": "sales"},
            "rationale": "描述销售额。",
            "questions": [],
            "finding": "销售额增长",
        }
    )

    with pytest.raises(PlannerContractError, match="unexpected planner fields: finding"):
        StructuredAnalysisPlanner(client).plan("描述销售额", _context())


def test_planning_context_infers_roles_without_sending_raw_rows():
    context = DatasetPlanningContext.from_frame(
        filename="orders.csv",
        source_fingerprint="sha256:" + "b" * 64,
        frame=pd.DataFrame(
            {
                "order_date": ["2026-01-01", "2026-01-02", "2026-01-03"],
                "sales": [10.0, 20.0, 30.0],
                "channel": ["web", "store", "web"],
                "order_id": ["o1", "o2", "o3"],
            }
        ),
    )

    assert {item.name: item.role for item in context.columns} == {
        "order_date": ColumnRole.DATETIME,
        "sales": ColumnRole.NUMERIC,
        "channel": ColumnRole.CATEGORICAL,
        "order_id": ColumnRole.IDENTIFIER,
    }
    prompt = context.to_prompt_dict()
    assert "o1" not in json.dumps(prompt)


def test_llm_chat_once_makes_one_provider_attempt_without_hidden_retry(monkeypatch):
    attempts = []

    def fail_once(**kwargs):
        attempts.append(kwargs)
        raise RuntimeError("provider failed")

    monkeypatch.setattr(llm_client_module, "completion", fail_once)
    client = LLMClient(model_id="fake-model")

    with pytest.raises(RuntimeError, match="provider failed"):
        client.chat_once([{"role": "user", "content": "plan"}])

    assert len(attempts) == 1
