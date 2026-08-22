"""Planner contract integration for curve_fitting (B1.3b)."""

from __future__ import annotations

from jsonschema import Draft202012Validator
import pytest

from data_agent.llm.client import Response, ToolCall
from data_agent.v2.planner import (
    ColumnRole,
    DatasetColumnContext,
    DatasetPlanningContext,
    PlanStatus,
    PlannerContractError,
    StructuredAnalysisPlanner,
    build_planner_contract_gate,
)
from data_agent.v2.router import AnalysisKind


def _context(numeric_count: int = 6) -> DatasetPlanningContext:
    columns = [DatasetColumnContext("date", "object", ColumnRole.DATETIME)]
    columns += [
        DatasetColumnContext(f"d{index}天后", "float64", ColumnRole.NUMERIC)
        for index in range(1, numeric_count + 1)
    ]
    columns.append(
        DatasetColumnContext("unit_id", "object", ColumnRole.IDENTIFIER)
    )
    return DatasetPlanningContext(
        filename="retention.csv",
        source_fingerprint="sha256:" + "a" * 64,
        row_count=60,
        columns=tuple(columns),
    )


class FakePlannerClient:
    model_id = "fake-planner"

    def __init__(self, arguments: dict) -> None:
        arguments.setdefault("pending_analysis_kind", "")
        arguments.setdefault("missing_prerequisites", [])
        self.arguments = arguments

    def chat_once(self, messages, tools=None, system=None):
        return Response(
            text="",
            tool_calls=[
                ToolCall("call_curve", "submit_analysis_plan", self.arguments)
            ],
        )


def _planner_tool_schema(context: DatasetPlanningContext) -> dict:
    planner = StructuredAnalysisPlanner(FakePlannerClient({}))
    _, request = planner.build_request("拟合留存公式", context)
    tool = request.tools[0]
    return next(
        variant
        for variant in tool["parameters"]["anyOf"]
        if variant["properties"]["status"]["enum"] == [PlanStatus.READY.value]
        and variant["properties"]["analysis_kind"]["enum"] == [AnalysisKind.CURVE_FITTING.value]
    )


def _arguments(parameters: dict) -> dict:
    return {
        "status": "ready",
        "analysis_kind": AnalysisKind.CURVE_FITTING.value,
        "parameters": parameters,
        "rationale": "wide retention series fit",
        "questions": [],
    }


def test_wide_context_offers_curve_ready_variant_with_series_branch():
    variant = _planner_tool_schema(_context(numeric_count=6))

    schema = variant["properties"]["parameters"]
    assert "series_columns" in schema["properties"]
    branches = {tuple(branch["required"]) for branch in schema["anyOf"]}
    assert ("series_columns",) in branches
    assert ("x_column", "y_column") in branches
    gate = build_planner_contract_gate(_context(numeric_count=6))
    assert gate["passed"], gate


def test_narrow_context_omits_series_branch_but_keeps_long_binding():
    variant = _planner_tool_schema(_context(numeric_count=2))

    schema = variant["properties"]["parameters"]
    assert "series_columns" not in schema["properties"]
    branches = {tuple(branch["required"]) for branch in schema["anyOf"]}
    assert branches == {("x_column", "y_column")}


def test_schema_rejects_both_binding_modes_and_duplicate_xy():
    variant = _planner_tool_schema(_context(numeric_count=6))
    validator = Draft202012Validator(variant["properties"]["parameters"])

    assert list(
        validator.iter_errors(
            {
                "series_columns": ["d1天后", "d2天后", "d3天后", "d4天后", "d5天后"],
                "x_column": "d1天后",
            }
        )
    )
    assert list(
        validator.iter_errors({"x_column": "d1天后", "y_column": "d1天后"})
    )
    assert not list(
        validator.iter_errors(
            {
                "series_columns": [
                    "d1天后",
                    "d2天后",
                    "d3天后",
                    "d4天后",
                    "d5天后",
                ]
            }
        )
    )


def test_compile_accepts_series_binding_and_normalizes_columns():
    planner = StructuredAnalysisPlanner(
        FakePlannerClient(
            _arguments(
                {"series_columns": ["d1天后", "d2天后", "d3天后", "d4天后", "d5天后"]}
            )
        )
    )

    plan = planner.plan("拟合留存公式", _context(numeric_count=6))

    assert plan.status is PlanStatus.READY
    assert plan.analysis_kind is AnalysisKind.CURVE_FITTING
    assert plan.parameters["series_columns"] == [
        "d1天后",
        "d2天后",
        "d3天后",
        "d4天后",
        "d5天后",
    ]
    assert plan.maximum_claim_class == "descriptive"


def test_compile_rejects_mixed_modes_and_short_series_and_duplicate_xy():
    context = _context(numeric_count=6)
    cases = [
        (
            _arguments(
                {
                    "series_columns": ["d1天后", "d2天后", "d3天后", "d4天后", "d5天后"],
                    "x_column": "d1天后",
                }
            ),
            "plan_parameter_relation_invalid",
        ),
        (
            _arguments({"series_columns": ["d1天后", "d2天后"]}),
            "plan_parameter_value_invalid",
        ),
        (
            _arguments({"x_column": "d1天后", "y_column": "d1天后"}),
            "plan_parameter_relation_invalid",
        ),
        (
            _arguments({"zero_values": "keep"}),
            "plan_parameter_fields_missing",
        ),
    ]
    for arguments, reason_code in cases:
        planner = StructuredAnalysisPlanner(FakePlannerClient(arguments))
        with pytest.raises(PlannerContractError) as excinfo:
            planner.plan("拟合留存公式", context)
        assert excinfo.value.reason_code == reason_code


def test_numeric_poor_context_gates_curve_behind_needs_input():
    planner = StructuredAnalysisPlanner(FakePlannerClient({}))
    _, request = planner.build_request("拟合公式", _context(numeric_count=1))
    needs_input_variants = [
        variant
        for variant in request.tools[0]["parameters"]["anyOf"]
        if variant["properties"]["status"]["enum"] == [PlanStatus.NEEDS_INPUT.value]
        and variant["properties"]["pending_analysis_kind"]["enum"]
        == [AnalysisKind.CURVE_FITTING.value]
    ]
    assert needs_input_variants, "curve needs_input variant must exist when unbindable"
    assert needs_input_variants[0]["properties"]["missing_prerequisites"]["const"] == [
        "curve_binding"
    ]
