from __future__ import annotations

import json
from types import SimpleNamespace

import pandas as pd
import pytest
from jsonschema import Draft202012Validator

import data_agent.llm.client as llm_client_module
from data_agent.llm.client import LLMClient, Response, ToolCall
from data_agent.v2.planner import (
    ColumnRole,
    DatasetColumnContext,
    DatasetPlanningContext,
    PlanStatus,
    PlannerContractError,
    PlannerFailureStage,
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
        confirmed_analysis_unit_column="unit_id",
    )


class FakePlannerClient:
    model_id = "fake-planner"

    def __init__(self, arguments: dict, *, text: str = "") -> None:
        arguments.setdefault("pending_analysis_kind", "")
        arguments.setdefault("missing_prerequisites", [])
        self.arguments = arguments
        self.text = text
        self.calls = []

    def chat_once(self, messages, tools=None, system=None):
        self.calls.append({"messages": messages, "tools": tools, "system": system})
        return Response(
            text=self.text,
            tool_calls=[ToolCall("call_plan", "submit_analysis_plan", self.arguments)],
        )


def _planner_tool_schema(context: DatasetPlanningContext | None = None) -> dict:
    planner = StructuredAnalysisPlanner(FakePlannerClient({}))
    _, request = planner.build_request("分析销售额", context or _context())
    return request.tools[0]["parameters"]


_VALID_READY_PARAMETERS = {
    "descriptive": {"metric": "sales"},
    "factor_relationship": {
        "target": "sales",
        "features": ["marketing"],
        "analysis_unit": "unit_id",
        "time_field": "date",
    },
    "date_transformation": {"date_column": "date"},
    "group_comparison": {
        "metric": "sales",
        "group": "channel",
        "analysis_unit": "unit_id",
    },
    "time_trend": {
        "time_field": "date",
        "metric": "sales",
        "frequency": "daily",
        "aggregation": "sum",
    },
    "forecast": {
        "time_field": "date",
        "metric": "sales",
        "frequency": "weekly",
        "aggregation": "mean",
        "horizon": 7,
    },
    "multi_finding_synthesis": {
        "time_field": "date",
        "metric": "sales",
        "frequency": "monthly",
        "aggregation": "sum",
        "group": "channel",
        "analysis_unit": "unit_id",
    },
}


def _ready_arguments(kind: str, parameters: dict) -> dict:
    return {
        "status": "ready",
        "analysis_kind": kind,
        "parameters": parameters,
        "rationale": "使用受支持的确定性方法。",
        "questions": [],
        "pending_analysis_kind": "",
        "missing_prerequisites": [],
    }


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


def test_planner_cannot_invent_recommendation_policy_from_schema_only_context():
    arguments = _ready_arguments(
        "group_comparison",
        {
            "metric": "sales",
            "group": "channel",
            "analysis_unit": "unit_id",
            "recommendation_intent": "act",
            "action_risk": "low",
            "reversible": True,
        },
    )

    assert list(Draft202012Validator(_planner_tool_schema()).iter_errors(arguments))
    with pytest.raises(PlannerContractError) as caught:
        StructuredAnalysisPlanner(FakePlannerClient(arguments)).plan(
            "比较渠道销售额并建议下一步。", _context()
        )

    assert caught.value.reason_code == "plan_parameter_fields_unexpected"


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
    context = DatasetPlanningContext(
        filename="sales.csv",
        source_fingerprint="sha256:" + "d" * 64,
        row_count=120,
        columns=(
            DatasetColumnContext("sales", "float64", ColumnRole.NUMERIC),
            DatasetColumnContext("unit_id", "object", ColumnRole.IDENTIFIER),
        ),
    )
    client = FakePlannerClient(
        {
            "status": "needs_input",
            "analysis_kind": "",
            "parameters": {},
            "rationale": "趋势分析缺少时间字段。",
            "questions": ["哪个字段表示观测时间？"],
            "pending_analysis_kind": "time_trend",
            "missing_prerequisites": ["time_field"],
        }
    )

    result = StructuredAnalysisPlanner(client).plan("销售如何随时间变化？", context)

    assert result.status is PlanStatus.NEEDS_INPUT
    assert result.analysis_kind is None
    assert result.questions == ("哪个字段表示观测时间？",)


def test_planner_rejects_needs_input_when_claimed_prerequisite_is_available():
    client = FakePlannerClient(
        {
            "status": "needs_input",
            "analysis_kind": "",
            "parameters": {},
            "rationale": "声称缺少分析单位。",
            "questions": ["每行代表什么观察单位？"],
            "pending_analysis_kind": "multi_finding_synthesis",
            "missing_prerequisites": ["analysis_unit"],
        }
    )

    with pytest.raises(PlannerContractError) as caught:
        StructuredAnalysisPlanner(client).plan("比较渠道并分析趋势", _context())

    assert caught.value.reason_code == "plan_needs_input_not_justified"


def test_planner_accepts_needs_input_with_exact_missing_time_prerequisite():
    context = DatasetPlanningContext(
        filename="sales.csv",
        source_fingerprint="sha256:" + "b" * 64,
        row_count=120,
        columns=(
            DatasetColumnContext("sales", "float64", ColumnRole.NUMERIC),
            DatasetColumnContext("unit_id", "object", ColumnRole.IDENTIFIER),
        ),
    )
    client = FakePlannerClient(
        {
            "status": "needs_input",
            "analysis_kind": "",
            "parameters": {},
            "rationale": "趋势分析缺少时间字段。",
            "questions": ["哪个字段表示观测时间？"],
            "pending_analysis_kind": "time_trend",
            "missing_prerequisites": ["time_field"],
        }
    )

    result = StructuredAnalysisPlanner(client).plan("销售如何随时间变化？", context)

    assert result.status is PlanStatus.NEEDS_INPUT
    assert result.analysis_kind is None
    assert result.pending_analysis_kind is AnalysisKind.TIME_TREND
    assert result.missing_prerequisites == ("time_field",)


def test_analysis_unit_route_requires_explicit_confirmed_semantic_column():
    columns = (
        DatasetColumnContext("date", "object", ColumnRole.DATETIME),
        DatasetColumnContext("sales", "float64", ColumnRole.NUMERIC),
        DatasetColumnContext("channel", "object", ColumnRole.CATEGORICAL),
        DatasetColumnContext("unit_id", "object", ColumnRole.IDENTIFIER),
    )
    unconfirmed = DatasetPlanningContext(
        filename="sales.csv",
        source_fingerprint="sha256:" + "f" * 64,
        row_count=120,
        columns=columns,
    )
    needs_input = FakePlannerClient(
        {
            "status": "needs_input",
            "analysis_kind": "",
            "parameters": {},
            "rationale": "组间推断需要用户确认独立观察单位。",
            "questions": ["哪一列标识独立观察单位？"],
            "pending_analysis_kind": "group_comparison",
            "missing_prerequisites": ["analysis_unit_semantics"],
        }
    )

    pending = StructuredAnalysisPlanner(needs_input).plan(
        "不同渠道销售额是否有差异？", unconfirmed
    )

    assert pending.status is PlanStatus.NEEDS_INPUT
    assert pending.missing_prerequisites == ("analysis_unit_semantics",)

    confirmed = DatasetPlanningContext(
        filename="sales.csv",
        source_fingerprint="sha256:" + "f" * 64,
        row_count=120,
        columns=columns,
        confirmed_analysis_unit_column="unit_id",
    )
    ready = StructuredAnalysisPlanner(
        FakePlannerClient(
            {
                "status": "ready",
                "analysis_kind": "group_comparison",
                "parameters": {
                    "metric": "sales",
                    "group": "channel",
                    "analysis_unit": "unit_id",
                },
                "rationale": "使用用户确认的独立观察单位。",
                "questions": [],
            }
        )
    ).plan("不同渠道销售额是否有差异？", confirmed)

    assert ready.status is PlanStatus.READY
    assert ready.parameters["analysis_unit"] == "unit_id"


def test_planner_rejects_ready_route_when_context_prerequisite_is_missing():
    context = DatasetPlanningContext(
        filename="sales.csv",
        source_fingerprint="sha256:" + "e" * 64,
        row_count=120,
        columns=(
            DatasetColumnContext("sales", "float64", ColumnRole.NUMERIC),
            DatasetColumnContext("unit_id", "object", ColumnRole.IDENTIFIER),
        ),
    )
    client = FakePlannerClient(
        {
            "status": "ready",
            "analysis_kind": "time_trend",
            "parameters": {
                "time_field": "unit_id",
                "metric": "sales",
                "frequency": "daily",
                "aggregation": "sum",
            },
            "rationale": "错误地声称可执行趋势。",
            "questions": [],
        }
    )

    with pytest.raises(PlannerContractError) as caught:
        StructuredAnalysisPlanner(client).plan("销售如何随时间变化？", context)

    assert caught.value.reason_code == "plan_ready_prerequisites_missing"
    assert list(
        Draft202012Validator(_planner_tool_schema(context)).iter_errors(
            client.arguments
        )
    )


def test_planner_tool_schema_requires_controlled_needs_input_identity():
    context = DatasetPlanningContext(
        filename="sales.csv",
        source_fingerprint="sha256:" + "c" * 64,
        row_count=120,
        columns=(
            DatasetColumnContext("sales", "float64", ColumnRole.NUMERIC),
            DatasetColumnContext("unit_id", "object", ColumnRole.IDENTIFIER),
        ),
    )
    schema = _planner_tool_schema(context)
    validator = Draft202012Validator(schema)
    controlled = {
        "status": "needs_input",
        "analysis_kind": "",
        "parameters": {},
        "rationale": "趋势分析缺少时间字段。",
        "questions": ["哪个字段表示观测时间？"],
        "pending_analysis_kind": "time_trend",
        "missing_prerequisites": ["time_field"],
    }
    legacy_unbounded = {
        "status": "needs_input",
        "analysis_kind": "",
        "parameters": {},
        "rationale": "自由决定追问。",
        "questions": ["还需要什么？"],
    }

    assert list(validator.iter_errors(controlled)) == []
    assert list(validator.iter_errors(legacy_unbounded))


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


@pytest.mark.parametrize(
    "arguments",
    [
        {
            "status": "ready",
            "analysis_kind": "descriptive",
            "parameters": {"metric": "sales"},
            "rationale": "描述销售额。",
            "questions": [],
            "pending_analysis_kind": "",
            "missing_prerequisites": [],
        },
        {
            "status": "unsupported",
            "analysis_kind": "",
            "parameters": {},
            "rationale": "不支持因果识别。",
            "questions": [],
            "pending_analysis_kind": "",
            "missing_prerequisites": [],
        },
    ],
)
def test_planner_tool_schema_accepts_each_compileable_status_variant(arguments):
    Draft202012Validator(_planner_tool_schema()).validate(arguments)


@pytest.mark.parametrize(
    "arguments",
    [
        {
            "status": "ready",
            "analysis_kind": "descriptive",
            "parameters": {"metric": "sales"},
            "rationale": "先追问。",
            "questions": ["是否只看已完成订单？"],
        },
        {
            "status": "needs_input",
            "analysis_kind": "group_comparison",
            "parameters": {
                "metric": "sales",
                "group": "channel",
                "analysis_unit": "unit_id",
            },
            "rationale": "同时给出 route 和问题。",
            "questions": ["每行代表什么？"],
        },
        {
            "status": "needs_input",
            "analysis_kind": "",
            "parameters": {},
            "rationale": "声称缺少输入但没有提问。",
            "questions": [],
        },
        {
            "status": "unsupported",
            "analysis_kind": "",
            "parameters": {},
            "rationale": "不支持但仍然追问。",
            "questions": ["是否改做描述分析？"],
        },
    ],
)
def test_planner_tool_schema_rejects_status_payloads_the_compiler_rejects(arguments):
    errors = list(Draft202012Validator(_planner_tool_schema()).iter_errors(arguments))

    assert errors


@pytest.mark.parametrize(
    ("kind", "valid_parameters"), list(_VALID_READY_PARAMETERS.items())
)
def test_planner_tool_schema_matches_required_and_allowed_parameters_by_kind(
    kind, valid_parameters
):
    validator = Draft202012Validator(_planner_tool_schema())
    validator.validate(_ready_arguments(kind, valid_parameters))

    missing = dict(valid_parameters)
    missing.pop(next(iter(valid_parameters)))
    unexpected = {**valid_parameters, "provider_invented_field": "secret value"}

    assert list(validator.iter_errors(_ready_arguments(kind, missing)))
    assert list(validator.iter_errors(_ready_arguments(kind, unexpected)))


@pytest.mark.parametrize(
    ("kind", "parameters"),
    [
        ("descriptive", {"metric": "channel"}),
        (
            "time_trend",
            {
                "time_field": "channel",
                "metric": "sales",
                "frequency": "daily",
                "aggregation": "sum",
            },
        ),
        (
            "factor_relationship",
            {
                "target": "sales",
                "features": ["channel"],
                "analysis_unit": "unit_id",
            },
        ),
    ],
)
def test_planner_tool_schema_rejects_wrong_role_column_bindings(kind, parameters):
    errors = list(
        Draft202012Validator(_planner_tool_schema()).iter_errors(
            _ready_arguments(kind, parameters)
        )
    )

    assert errors


@pytest.mark.parametrize(
    ("arguments", "reason_code", "parameter_shape"),
    [
        (
            _ready_arguments(
                "group_comparison",
                {"metric": "sales", "group": "channel"},
            ),
            "plan_parameter_fields_missing",
            {
                "recognized_analysis_kind": "group_comparison",
                "recognized_parameter_fields": ["group", "metric"],
                "missing_required_parameter_fields": ["analysis_unit"],
                "unexpected_recognized_parameter_fields": [],
                "unknown_parameter_field_count": 0,
                "invalid_parameter_fields": [],
                "parameter_metadata_truncated": False,
            },
        ),
        (
            _ready_arguments(
                "descriptive",
                {
                    "metric": "sales",
                    "horizon": 7,
                    "provider_invented_field": "secret value",
                },
            ),
            "plan_parameter_fields_unexpected",
            {
                "recognized_analysis_kind": "descriptive",
                "recognized_parameter_fields": ["horizon", "metric"],
                "missing_required_parameter_fields": [],
                "unexpected_recognized_parameter_fields": ["horizon"],
                "unknown_parameter_field_count": 1,
                "invalid_parameter_fields": [],
                "parameter_metadata_truncated": False,
            },
        ),
    ],
)
def test_planner_parameter_contract_failure_is_exact_without_unknown_names_or_values(
    arguments, reason_code, parameter_shape
):
    with pytest.raises(PlannerContractError) as caught:
        StructuredAnalysisPlanner(FakePlannerClient(arguments)).plan(
            "分析销售额", _context()
        )

    assert caught.value.reason_code == reason_code
    assert {
        key: caught.value.diagnostic[key] for key in parameter_shape
    } == parameter_shape
    serialized = json.dumps(caught.value.diagnostic, ensure_ascii=False)
    assert "provider_invented_field" not in serialized
    assert "secret value" not in serialized


@pytest.mark.parametrize(
    ("arguments", "reason_code", "invalid_fields"),
    [
        (
            _ready_arguments("descriptive", {"metric": "channel"}),
            "plan_column_binding_invalid",
            ["metric"],
        ),
        (
            _ready_arguments(
                "time_trend",
                {
                    "time_field": "date",
                    "metric": "sales",
                    "frequency": "hourly",
                    "aggregation": "sum",
                },
            ),
            "plan_parameter_value_invalid",
            ["frequency"],
        ),
        (
            _ready_arguments(
                "factor_relationship",
                {
                    "target": "sales",
                    "features": ["channel"],
                    "analysis_unit": "unit_id",
                },
            ),
            "plan_column_binding_invalid",
            ["features"],
        ),
    ],
)
def test_planner_diagnostic_identifies_controlled_invalid_parameter_fields(
    arguments, reason_code, invalid_fields
):
    with pytest.raises(PlannerContractError) as caught:
        StructuredAnalysisPlanner(FakePlannerClient(arguments)).plan(
            "分析销售额", _context()
        )

    assert caught.value.reason_code == reason_code
    assert caught.value.diagnostic["invalid_parameter_fields"] == invalid_fields
    serialized = json.dumps(caught.value.diagnostic, ensure_ascii=False)
    assert "hourly" not in serialized
    assert "channel" not in serialized


@pytest.mark.parametrize(
    ("kind", "field", "invalid_value"),
    [
        ("time_trend", "frequency", "hourly"),
        ("time_trend", "aggregation", "median"),
        ("forecast", "horizon", 0),
    ],
)
def test_planner_schema_and_compiler_share_finite_parameter_policies(
    kind, field, invalid_value
):
    parameters = {**_VALID_READY_PARAMETERS[kind], field: invalid_value}
    arguments = _ready_arguments(kind, parameters)

    schema_errors = list(
        Draft202012Validator(_planner_tool_schema()).iter_errors(arguments)
    )
    with pytest.raises(PlannerContractError) as caught:
        StructuredAnalysisPlanner(FakePlannerClient(arguments)).plan(
            "分析销售额", _context()
        )

    assert schema_errors
    assert caught.value.reason_code == "plan_parameter_value_invalid"
    assert caught.value.diagnostic["invalid_parameter_fields"] == [field]


def test_planner_reports_first_invalid_field_in_stable_policy_order():
    arguments = _ready_arguments(
        "time_trend",
        {
            "time_field": "channel",
            "metric": "channel",
            "frequency": "hourly",
            "aggregation": "median",
        },
    )

    with pytest.raises(PlannerContractError) as caught:
        StructuredAnalysisPlanner(FakePlannerClient(arguments)).plan(
            "分析销售额", _context()
        )

    assert caught.value.reason_code == "plan_column_binding_invalid"
    assert caught.value.diagnostic["invalid_parameter_fields"] == ["metric"]


@pytest.mark.parametrize(
    ("kind", "parameters", "invalid_fields"),
    [
        (
            "group_comparison",
            {"metric": "sales", "group": "channel", "analysis_unit": "channel"},
            ["analysis_unit", "group"],
        ),
        (
            "multi_finding_synthesis",
            {
                "time_field": "date",
                "metric": "sales",
                "frequency": "weekly",
                "aggregation": "sum",
                "group": "channel",
                "analysis_unit": "channel",
            },
            ["analysis_unit", "group"],
        ),
    ],
)
def test_planner_schema_and_compiler_reject_duplicate_group_field_identities(
    kind, parameters, invalid_fields
):
    arguments = _ready_arguments(kind, parameters)

    assert list(Draft202012Validator(_planner_tool_schema()).iter_errors(arguments))
    with pytest.raises(PlannerContractError) as caught:
        StructuredAnalysisPlanner(FakePlannerClient(arguments)).plan(
            "比较渠道销售额", _context()
        )

    assert caught.value.reason_code == "plan_parameter_relation_invalid"
    assert caught.value.diagnostic["invalid_parameter_fields"] == invalid_fields


@pytest.mark.parametrize(
    ("kind", "parameters"),
    [
        (
            "group_comparison",
            {"metric": "sales", "group": "channel", "analysis_unit": "date"},
        ),
        (
            "multi_finding_synthesis",
            {
                "time_field": "date",
                "metric": "sales",
                "frequency": "daily",
                "aggregation": "sum",
                "group": "channel",
                "analysis_unit": "date",
            },
        ),
    ],
)
def test_planner_schema_and_compiler_reject_datetime_analysis_units(
    kind, parameters
):
    arguments = _ready_arguments(kind, parameters)

    assert list(Draft202012Validator(_planner_tool_schema()).iter_errors(arguments))
    with pytest.raises(PlannerContractError) as caught:
        StructuredAnalysisPlanner(FakePlannerClient(arguments)).plan(
            "比较渠道销售额", _context()
        )

    if kind == "multi_finding_synthesis":
        assert caught.value.reason_code == "plan_parameter_relation_invalid"
        assert caught.value.diagnostic["invalid_parameter_fields"] == [
            "analysis_unit",
            "time_field",
        ]
    else:
        assert caught.value.reason_code == "plan_column_binding_invalid"
        assert caught.value.diagnostic["invalid_parameter_fields"] == [
            "analysis_unit"
        ]


@pytest.mark.parametrize(
    ("parameters", "invalid_fields"),
    [
        (
            {
                "target": "sales",
                "features": ["sales"],
                "analysis_unit": "unit_id",
            },
            ["features", "target"],
        ),
        (
            {
                "target": "sales",
                "features": ["marketing"],
                "analysis_unit": "marketing",
            },
            ["analysis_unit", "features"],
        ),
        (
            {
                "target": "sales",
                "features": ["marketing"],
                "analysis_unit": "date",
                "time_field": "date",
            },
            ["analysis_unit", "time_field"],
        ),
        (
            {
                "target": "sales",
                "features": ["marketing"],
                "analysis_unit": "sales",
            },
            ["analysis_unit", "target"],
        ),
    ],
)
def test_planner_schema_and_compiler_reject_factor_identity_collisions(
    parameters, invalid_fields
):
    arguments = _ready_arguments("factor_relationship", parameters)

    assert list(Draft202012Validator(_planner_tool_schema()).iter_errors(arguments))
    with pytest.raises(PlannerContractError) as caught:
        StructuredAnalysisPlanner(FakePlannerClient(arguments)).plan(
            "分析销售因素", _context()
        )

    assert caught.value.reason_code == "plan_parameter_relation_invalid"
    assert caught.value.diagnostic["invalid_parameter_fields"] == invalid_fields


@pytest.mark.parametrize(
    ("arguments", "reason_code", "shape"),
    [
        (
            {
                "status": "ready",
                "analysis_kind": "descriptive",
                "parameters": {"metric": "sales"},
                "rationale": "先追问。",
                "questions": ["是否只看已完成订单？"],
            },
            "plan_ready_questions_present",
            {
                "recognized_status": "ready",
                "analysis_kind_present": True,
                "parameters_empty_object": False,
                "questions_present": True,
            },
        ),
        (
            {
                "status": "needs_input",
                "analysis_kind": "group_comparison",
                "parameters": {
                    "metric": "sales",
                    "group": "channel",
                    "analysis_unit": "unit_id",
                },
                "rationale": "同时给出 route 和问题。",
                "questions": ["每行代表什么？"],
            },
            "plan_needs_input_route_present",
            {
                "recognized_status": "needs_input",
                "analysis_kind_present": True,
                "parameters_empty_object": False,
                "questions_present": True,
            },
        ),
        (
            {
                "status": "needs_input",
                "analysis_kind": "",
                "parameters": {},
                "rationale": "声称缺少输入但没有提问。",
                "questions": [],
            },
            "plan_needs_input_questions_missing",
            {
                "recognized_status": "needs_input",
                "analysis_kind_present": False,
                "parameters_empty_object": True,
                "questions_present": False,
            },
        ),
        (
            {
                "status": "unsupported",
                "analysis_kind": "",
                "parameters": {},
                "rationale": "不支持但仍然追问。",
                "questions": ["是否改做描述分析？"],
            },
            "plan_unsupported_payload_present",
            {
                "recognized_status": "unsupported",
                "analysis_kind_present": False,
                "parameters_empty_object": True,
                "questions_present": True,
            },
        ),
    ],
)
def test_planner_classifies_each_status_payload_failure_without_values(
    arguments, reason_code, shape
):
    with pytest.raises(PlannerContractError) as caught:
        StructuredAnalysisPlanner(FakePlannerClient(arguments)).plan(
            "分析销售额", _context()
        )

    assert caught.value.reason_code == reason_code
    assert {
        key: caught.value.diagnostic[key]
        for key in (
            "recognized_status",
            "analysis_kind_present",
            "parameters_empty_object",
            "questions_present",
        )
    } == shape
    serialized = json.dumps(caught.value.diagnostic, ensure_ascii=False)
    assert "每行代表什么" not in serialized
    assert "是否改做描述分析" not in serialized


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


@pytest.mark.parametrize(
    ("response", "reason_code", "failure_stage", "tool_count", "tool_names", "fields"),
    [
        (
            Response(text="untrusted free text", finish_reason="stop"),
            "provider_response_missing_tool_call",
            PlannerFailureStage.PROVIDER_RESPONSE_SHAPE,
            0,
            [],
            [],
        ),
        (
            Response(
                tool_calls=[
                    ToolCall("one", "submit_analysis_plan", {}),
                    ToolCall("two", "submit_analysis_plan", {}),
                ],
                finish_reason="tool_calls",
            ),
            "provider_response_unexpected_tool_call_count",
            PlannerFailureStage.PROVIDER_RESPONSE_SHAPE,
            2,
            ["submit_analysis_plan", "submit_analysis_plan"],
            [],
        ),
        (
            Response(
                tool_calls=[ToolCall("one", "unapproved_tool", {})],
                finish_reason="tool_calls",
            ),
            "provider_response_unexpected_tool_name",
            PlannerFailureStage.PROVIDER_RESPONSE_SHAPE,
            1,
            ["unapproved_tool"],
            [],
        ),
        (
            Response(
                tool_calls=[
                    ToolCall(
                        "one",
                        "submit_analysis_plan",
                        {"raw": "must never be persisted"},
                        arguments_parse_error="invalid_json",
                    )
                ],
                finish_reason="tool_calls",
            ),
            "provider_response_tool_arguments_invalid_json",
            PlannerFailureStage.PROVIDER_RESPONSE_SHAPE,
            1,
            ["submit_analysis_plan"],
            ["raw"],
        ),
        (
            Response(
                tool_calls=[ToolCall("one", "submit_analysis_plan", "not-an-object")],
                finish_reason="tool_calls",
            ),
            "provider_response_tool_arguments_not_object",
            PlannerFailureStage.PROVIDER_RESPONSE_SHAPE,
            1,
            ["submit_analysis_plan"],
            [],
        ),
    ],
)
def test_planner_classifies_provider_response_shape_failures_without_raw_content(
    response, reason_code, failure_stage, tool_count, tool_names, fields
):
    class Client:
        model_id = "provider/test-model"

        def chat_once(self, messages, tools=None, system=None):
            return response

    with pytest.raises(PlannerContractError) as caught:
        StructuredAnalysisPlanner(Client()).plan("描述销售额", _context())

    error = caught.value
    assert error.reason_code == reason_code
    assert error.failure_stage is failure_stage
    assert error.diagnostic == {
        "failure_stage": failure_stage.value,
        "finish_reason": response.finish_reason,
        "tool_call_count": tool_count,
        "tool_names": tool_names,
        "tool_argument_types": [
            type(item.arguments).__name__ for item in response.tool_calls
        ],
        "argument_top_level_fields": fields,
        "metadata_truncated": False,
    }
    assert "untrusted free text" not in json.dumps(error.diagnostic)
    assert "must never be persisted" not in json.dumps(error.diagnostic)


@pytest.mark.parametrize(
    ("arguments", "reason_code"),
    [
        (
            {
                "status": "ready",
                "analysis_kind": "descriptive",
                "parameters": {"metric": "sales"},
                "rationale": "describe",
                "questions": [],
                "finding": "must not become evidence",
            },
            "plan_unexpected_fields",
        ),
        (
            {
                "status": "invented",
                "analysis_kind": "descriptive",
                "parameters": {"metric": "sales"},
                "rationale": "describe",
                "questions": [],
            },
            "plan_invalid_status",
        ),
        (
            {
                "status": "ready",
                "analysis_kind": "descriptive",
                "parameters": {"metric": "channel"},
                "rationale": "describe",
                "questions": [],
            },
            "plan_column_binding_invalid",
        ),
    ],
)
def test_planner_classifies_local_plan_compilation_failures(arguments, reason_code):
    client = FakePlannerClient(arguments)
    with pytest.raises(PlannerContractError) as caught:
        StructuredAnalysisPlanner(client).plan("描述销售额", _context())

    error = caught.value
    assert error.reason_code == reason_code
    assert error.failure_stage is PlannerFailureStage.PLAN_COMPILATION
    assert error.diagnostic["failure_stage"] == "plan_compilation"
    assert error.diagnostic["argument_top_level_fields"] == sorted(arguments)
    assert "must not become evidence" not in json.dumps(error.diagnostic)


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


def test_llm_invalid_tool_argument_json_is_classified_without_raw_or_reasoning(
    monkeypatch,
):
    attempts = []

    def invalid_json_once(**kwargs):
        attempts.append(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    finish_reason="tool_calls",
                    message=SimpleNamespace(
                        content="untrusted model text",
                        reasoning_content="private reasoning",
                        tool_calls=[
                            SimpleNamespace(
                                id="call_invalid_json",
                                function=SimpleNamespace(
                                    name="submit_analysis_plan",
                                    arguments='{not-json:"secret value"',
                                ),
                            )
                        ],
                    ),
                )
            ]
        )

    monkeypatch.setattr(llm_client_module, "completion", invalid_json_once)
    planner = StructuredAnalysisPlanner(LLMClient(model_id="fake-model"))

    with pytest.raises(PlannerContractError) as caught:
        planner.plan("描述销售额", _context())

    assert caught.value.reason_code == "provider_response_tool_arguments_invalid_json"
    serialized = json.dumps(caught.value.diagnostic)
    assert "secret value" not in serialized
    assert "private reasoning" not in serialized
    assert "untrusted model text" not in serialized
    assert len(attempts) == 1
