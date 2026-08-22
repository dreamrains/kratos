from __future__ import annotations

from data_agent.llm.client import Response, ToolCall
from data_agent.v2.planner import (
    ColumnRole,
    DatasetColumnContext,
    DatasetPlanningContext,
    StructuredAnalysisPlanner,
)
from data_agent.v2.planning_budget import (
    PlanningContextBudget,
    PlanningContextTooLarge,
    PlanningTokenEstimateUnavailable,
    resolve_model_context_window,
)

import pytest


class FakeClient:
    model_id = "provider/model"

    def chat_once(self, messages, tools=None, system=None):
        return Response(
            tool_calls=[
                ToolCall(
                    "call",
                    "submit_analysis_plan",
                    {
                        "status": "ready",
                        "analysis_kind": "descriptive",
                        "parameters": {"metric": "sales"},
                        "rationale": "describe",
                        "questions": [],
                    },
                )
            ]
        )


def _context() -> DatasetPlanningContext:
    return DatasetPlanningContext(
        filename="sales.csv",
        source_fingerprint="sha256:" + "a" * 64,
        row_count=3,
        columns=(DatasetColumnContext("sales", "int64", ColumnRole.NUMERIC),),
    )


def test_budget_counts_full_system_messages_tools_and_clarifications():
    calls = []

    def counter(**kwargs):
        calls.append(kwargs)
        if "tools" in kwargs:
            return 41
        if "messages" in kwargs:
            return 37
        if "text" in kwargs:
            return 113
        raise AssertionError("unexpected token counter call")

    budget = PlanningContextBudget(
        StructuredAnalysisPlanner(FakeClient()),
        model_id="provider/model",
        context_window_tokens=1000,
        reserved_output_tokens=100,
        token_counter=counter,
    )
    estimate = budget.require_fits(
        "compare sales",
        _context(),
        clarifications=({"question": "unit?", "answer": "order"},),
    )

    assert estimate.estimated_input_tokens == 150
    assert estimate.available_input_tokens == 900
    native, messages_only, tools_only = calls
    assert native["messages"][0]["role"] == "system"
    assert "clarifications" in native["messages"][0]["content"]
    assert native["tools"][0]["type"] == "function"
    assert native["tools"][0]["function"]["name"] == "submit_analysis_plan"
    assert messages_only["messages"] == native["messages"]
    assert "tools" not in messages_only
    assert "submit_analysis_plan" in tools_only["text"]


def test_budget_fails_closed_when_canonical_tool_schema_cannot_be_counted():
    def counter(**kwargs):
        if "text" in kwargs:
            raise RuntimeError("tool schema tokenizer unavailable")
        return 100

    budget = PlanningContextBudget(
        StructuredAnalysisPlanner(FakeClient()),
        model_id="provider/model",
        context_window_tokens=1000,
        reserved_output_tokens=100,
        token_counter=counter,
    )

    with pytest.raises(
        PlanningTokenEstimateUnavailable, match="token estimate is unavailable"
    ):
        budget.require_fits("compare sales", _context())


def test_budget_reports_exact_window_and_output_reserve_when_too_large():
    def counter(**kwargs):
        if "tools" in kwargs:
            return 801
        if "messages" in kwargs:
            return 400
        return 300

    budget = PlanningContextBudget(
        StructuredAnalysisPlanner(FakeClient()),
        model_id="provider/model",
        context_window_tokens=1000,
        reserved_output_tokens=200,
        token_counter=counter,
    )

    with pytest.raises(PlanningContextTooLarge) as raised:
        budget.require_fits("compare sales", _context())

    estimate = raised.value.estimate
    assert estimate.fits is False
    assert estimate.model_context_window_tokens == 1000
    assert estimate.reserved_output_tokens == 200
    assert estimate.available_input_tokens == 800
    assert estimate.estimated_input_tokens == 801


def test_explicit_context_window_overrides_missing_model_metadata():
    assert resolve_model_context_window("unmapped/model", 131072) == 131072


def test_official_deepseek_v4_context_window_is_used_when_litellm_is_unmapped():
    assert resolve_model_context_window(
        "openai/deepseek-v4-flash",
        None,
        api_base="https://api.deepseek.com",
    ) == 1_000_000
