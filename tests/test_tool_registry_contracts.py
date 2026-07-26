from __future__ import annotations

import json
from enum import Enum

import pytest

import data_agent.tools.registry as registry_module
from data_agent.tools import discover_tools
from data_agent.tools.registry import ToolDefinition, _build_schema, registry


class _Mode(Enum):
    SAFE = "safe"
    FAST = "fast"


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
        "visualization_strategy",
    ]
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
