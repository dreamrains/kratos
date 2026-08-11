from __future__ import annotations

import inspect
import json
from enum import Enum

import pytest

import data_agent.tools.registry as registry_module
from data_agent.tools import discover_tools
from data_agent.tools.registry import (
    ANALYSIS_PLAN_TOOL_CAPABILITIES,
    ToolDefinition,
    _build_schema,
    registry,
)


class _Mode(Enum):
    SAFE = "safe"
    FAST = "fast"


def test_analysis_plan_capabilities_include_executable_evidence_step():
    discover_tools()

    definition = registry.get("record_evidence_record")

    assert definition is not None
    assert definition.capability is not None
    assert definition.capability.capability_id == "artifact.evidence_record"
    assert (
        ANALYSIS_PLAN_TOOL_CAPABILITIES["record_evidence_record"]
        == "artifact.evidence_record"
    )


def test_registry_resolves_postponed_integer_annotation():
    discover_tools()
    definition = registry.get("regression_analysis")
    assert definition is not None

    cv = definition.parameters["properties"]["cv_folds"]

    assert cv["type"] == "integer"
    assert cv["default"] == 0


def test_registry_losslessly_normalizes_integer_and_boolean_strings():
    def sample(count: int, flag: bool = False) -> dict[str, object]:
        return {"count": count, "flag": flag}

    definition = ToolDefinition(
        name="sample",
        description="sample",
        func=sample,
        parameters=_build_schema(sample),
    )

    assert registry_module.normalize_tool_arguments(
        definition,
        {"count": "0", "flag": "false"},
    ) == {
        "count": 0,
        "flag": False,
    }


def test_registry_union_preserves_exact_string_type_before_conversion():
    def sample(value: int | str) -> int | str:
        return value

    definition = ToolDefinition(
        name="sample",
        description="sample",
        func=sample,
        parameters=_build_schema(sample),
    )

    assert registry_module.normalize_tool_arguments(
        definition,
        {"value": "001"},
    ) == {"value": "001"}


def test_registry_rejects_ambiguous_union_conversion():
    def sample(value: int | float) -> int | float:
        return value

    definition = ToolDefinition(
        name="sample",
        description="sample",
        func=sample,
        parameters=_build_schema(sample),
    )

    with pytest.raises(registry_module.ToolArgumentValidationError) as exc:
        registry_module.normalize_tool_arguments(
            definition,
            {"value": "1"},
        )

    assert exc.value.to_payload()["issues"][0]["issue"] == (
        "ambiguous_union_conversion"
    )


def test_registry_normalizes_finite_numbers_enums_and_nested_values():
    def sample(
        ratio: float,
        mode: _Mode,
        counts: list[int],
        flags: dict[str, bool],
    ) -> dict[str, object]:
        return {
            "ratio": ratio,
            "mode": mode,
            "counts": counts,
            "flags": flags,
        }

    definition = ToolDefinition(
        name="sample",
        description="sample",
        func=sample,
        parameters=_build_schema(sample),
    )

    assert registry_module.normalize_tool_arguments(
        definition,
        {
            "ratio": "1.5",
            "mode": "safe",
            "counts": ["0", 2],
            "flags": {"included": "yes", "excluded": "off"},
        },
    ) == {
        "ratio": 1.5,
        "mode": "safe",
        "counts": [0, 2],
        "flags": {"included": True, "excluded": False},
    }


@pytest.mark.parametrize("value", ["1.5", "1e2", "", True])
def test_registry_rejects_lossful_integer_values(value):
    def sample(count: int) -> int:
        return count

    definition = ToolDefinition(
        name="sample",
        description="sample",
        func=sample,
        parameters=_build_schema(sample),
    )

    with pytest.raises(registry_module.ToolArgumentValidationError):
        registry_module.normalize_tool_arguments(definition, {"count": value})


def test_registry_rejects_ambiguous_number_and_unknown_argument():
    def sample(count: int) -> int:
        return count

    definition = ToolDefinition(
        name="sample",
        description="sample",
        func=sample,
        parameters=_build_schema(sample),
    )

    with pytest.raises(registry_module.ToolArgumentValidationError) as exc:
        registry_module.normalize_tool_arguments(
            definition,
            {"count": "1.5", "extra": 1},
        )

    payload = exc.value.to_payload()
    assert payload["error_type"] == "invalid_tool_arguments"
    assert {issue["field"] for issue in payload["issues"]} == {"count", "extra"}


def test_registry_rejects_missing_required_argument():
    def sample(count: int) -> int:
        return count

    definition = ToolDefinition(
        name="sample",
        description="sample",
        func=sample,
        parameters=_build_schema(sample),
    )

    with pytest.raises(registry_module.ToolArgumentValidationError) as exc:
        registry_module.normalize_tool_arguments(definition, {})

    assert exc.value.to_payload()["issues"] == [
        {
            "field": "count",
            "issue": "missing_required_argument",
        }
    ]


def test_record_analysis_plan_exposes_object_not_opaque_json_string():
    discover_tools()
    definition = registry.get("record_analysis_plan")
    assert definition is not None

    schema = definition.parameters

    assert schema["properties"]["plan"]["type"] == "object"
    assert schema["properties"]["plan"]["required"] == [
        "goal",
        "method_plan",
    ]
    step_schema = schema["properties"]["plan"]["properties"]["method_plan"]["items"]
    assert {
        "goal",
        "dataset_inputs",
        "combination_mode",
        "expected_output",
        "evidence_requirements",
    }.issubset(step_schema["properties"])
    assert "plan" in schema["required"]
    assert "plan_json" not in schema["properties"]


def test_record_analysis_plan_legacy_alias_decodes_only_object_json():
    discover_tools()
    definition = registry.get("record_analysis_plan")
    assert definition is not None
    legacy_plan = {
        "goal": "Check revenue",
        "method_plan": [],
        "visualization_strategy": "table",
    }

    assert registry_module.normalize_tool_arguments(
        definition,
        {"plan_json": json.dumps(legacy_plan)},
    ) == {"plan": legacy_plan}

    with pytest.raises(registry_module.ToolArgumentValidationError):
        registry_module.normalize_tool_arguments(
            definition,
            {"plan": json.dumps(legacy_plan)},
        )
    with pytest.raises(registry_module.ToolArgumentValidationError):
        registry_module.normalize_tool_arguments(
            definition,
            {"plan_json": json.dumps(["not", "an", "object"])},
        )
    with pytest.raises(registry_module.ToolArgumentValidationError):
        registry_module.normalize_tool_arguments(
            definition,
            {"plan": legacy_plan, "plan_json": json.dumps(legacy_plan)},
        )
    with pytest.raises(registry_module.ToolArgumentValidationError) as exc:
        registry_module.normalize_tool_arguments(
            definition,
            {"plan_json": legacy_plan},
        )
    assert exc.value.to_payload()["issues"][0]["issue"] == (
        "compatibility_alias_requires_json_string"
    )


def test_task_create_does_not_expose_plan_body_parameters():
    discover_tools()
    definition = registry.get("task_create")
    assert definition is not None

    properties = definition.parameters["properties"]

    assert "analysis_plan_json" not in properties
    assert "analysis_spec_json" not in properties
    result = registry.execute("task_create", {"analysis_plan_json": "{}"})
    assert result.data is not None
    assert result.data["error_type"] == "invalid_tool_arguments"


def test_definition_contract_requires_closed_object_root_and_explicit_default():
    def sample(count: int = 1) -> int:
        return count

    definition = ToolDefinition(
        name="sample",
        description="sample",
        func=sample,
        parameters={
            "type": "array",
            "properties": {
                "count": {"type": "integer"},
            },
            "required": [],
        },
    )

    issues = registry_module.validate_tool_definition_contract(definition)

    assert {issue["issue"] for issue in issues} == {
        "root_type_mismatch",
        "additional_properties_mismatch",
        "missing_default",
    }


def test_definition_contract_rejects_default_that_runtime_schema_rejects():
    def sample(agg_func: str = "") -> str:
        return agg_func

    definition = ToolDefinition(
        name="sample",
        description="sample",
        func=sample,
        parameters={
            "type": "object",
            "properties": {
                "agg_func": {
                    "type": "string",
                    "enum": ["sum", "mean"],
                    "default": "",
                },
            },
            "required": [],
            "additionalProperties": False,
        },
    )

    issues = registry_module.validate_tool_definition_contract(definition)

    assert issues == [{
        "field": "agg_func",
        "issue": "default_schema_mismatch",
        "default": "",
        "schema_issue": "value_not_in_enum",
    }]


def test_definition_contract_normalizes_signature_default_after_default_mismatch():
    def sample(agg_func: str = "") -> str:
        return agg_func

    definition = ToolDefinition(
        name="sample",
        description="sample",
        func=sample,
        parameters={
            "type": "object",
            "properties": {
                "agg_func": {
                    "type": "string",
                    "enum": ["sum", "mean"],
                    "default": "sum",
                },
            },
            "required": [],
            "additionalProperties": False,
        },
    )

    issues = registry_module.validate_tool_definition_contract(definition)

    assert {issue["issue"] for issue in issues} == {
        "default_mismatch",
        "default_schema_mismatch",
    }


def test_every_native_optional_default_matches_visible_runtime_schema():
    registry._ensure_discovered()
    failures: dict[str, dict[str, str]] = {}
    for definition in registry._tools.values():
        if definition.origin != "native":
            continue
        signature = inspect.signature(definition.func)
        properties = definition.parameters["properties"]
        for name, parameter in signature.parameters.items():
            if (
                parameter.default is inspect.Parameter.empty
                or name not in properties
            ):
                continue
            try:
                registry_module._normalize_schema_value(
                    parameter.default,
                    properties[name],
                )
            except registry_module._ArgumentValueError as exc:
                failures[f"{definition.name}.{name}"] = {
                    "issue": exc.issue,
                }

    assert failures == {}


@pytest.mark.parametrize(
    ("tool_name", "parameter_name"),
    [
        ("apply_type_conversion", "target_type"),
        ("analyze_time_series", "agg_func"),
        ("compare_periods", "agg_func"),
        ("transform_data", "freq"),
    ],
)
def test_optional_empty_string_sentinels_normalize_losslessly(
    tool_name,
    parameter_name,
):
    registry._ensure_discovered()
    definition = registry.get(tool_name)
    assert definition is not None
    schema = definition.parameters["properties"][parameter_name]

    assert registry_module._normalize_schema_value("", schema) == ""


@pytest.mark.parametrize(
    ("tool_name", "parameter_name"),
    [
        ("transform_data", "columns"),
        ("transform_data", "rename_mapping"),
        ("transform_data", "sort_by"),
        ("transform_data", "group_by"),
        ("transform_data", "aggregations"),
        ("transform_data", "resample_agg"),
        ("transform_data", "melt_id_vars"),
        ("transform_data", "melt_value_vars"),
        ("ask_user_question", "options"),
        ("add_mcp_server", "args"),
    ],
)
def test_optional_collection_defaults_normalize_as_absent(
    tool_name,
    parameter_name,
):
    registry._ensure_discovered()
    definition = registry.get(tool_name)
    assert definition is not None
    schema = definition.parameters["properties"][parameter_name]

    assert registry_module._normalize_schema_value(None, schema) is None


def test_every_native_tool_schema_matches_signature():
    registry._ensure_discovered()
    failures = {
        definition.name: issues
        for definition in registry._tools.values()
        if definition.origin == "native"
        and (
            issues
            := registry_module.validate_tool_definition_contract(definition)
        )
    }

    assert failures == {}
