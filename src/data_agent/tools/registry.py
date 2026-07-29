from __future__ import annotations

import inspect
import json
import math
import re
import time
from contextvars import copy_context
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from dataclasses import dataclass, field
from enum import Enum
from types import UnionType
from typing import (
    Any,
    Callable,
    Literal,
    Mapping,
    Optional,
    Union,
    get_args,
    get_origin,
    get_type_hints,
)


# === ToolResult: structured return value ===

@dataclass
class ArtifactRef:
    """Reference to a file artifact produced by a tool."""
    path: str
    type: str  # "chart" | "report" | "report_md" | "file" | "analysis"
    description: str = ""


@dataclass
class ToolResult:
    """Structured return value for all tools.

    CLI uses ``summary`` for display; Web uses the full structure
    for rich rendering.  Existing tools that return plain strings
    are auto-wrapped via ``ToolResult.from_str()``.
    """
    summary: str
    data: dict[str, Any] | None = None
    artifacts: list[ArtifactRef] | None = None
    suggested_next: str | None = None

    @staticmethod
    def from_str(s: str) -> "ToolResult":
        return ToolResult(summary=s)

    def to_cli(self) -> str:
        return self.summary

    def to_web(self) -> dict[str, Any]:
        result: dict[str, Any] = {"summary": self.summary}
        if self.data is not None:
            result["data"] = self.data
        if self.artifacts:
            result["artifacts"] = [
                {"path": a.path, "type": a.type, "description": a.description}
                for a in self.artifacts
            ]
        if self.suggested_next:
            result["suggested_next"] = self.suggested_next
        return result

    def __str__(self) -> str:
        return self.to_cli()


def _artifact_from_chart_saved(summary: str) -> ArtifactRef | None:
    match = re.search(r"Chart saved:\s*(sessions\/\S+?\.html|charts\/\S+?\.html)", summary or "")
    if not match:
        return None
    path = match.group(1)
    name = path.rsplit("/", 1)[-1].replace(".html", "")
    name = re.sub(r"_[a-f0-9]{6}$", "", name)
    return ArtifactRef(path=path, type="chart", description=name)


@dataclass
class ToolCapability:
    """Metadata that lets analysis workflows reason about tool abilities."""

    capability_id: str
    category: str = ""
    problem_types: list[str] = field(default_factory=list)
    input_contract: dict[str, Any] = field(default_factory=dict)
    output_contract: dict[str, Any] = field(default_factory=dict)
    evidence_fields: list[str] = field(default_factory=list)
    risk_level: str = "low"
    requires_confirmation: bool = False
    dependencies: list[str] = field(default_factory=list)
    fallback_tools: list[str] = field(default_factory=list)

    @staticmethod
    def from_dict(data: dict[str, Any] | None) -> "ToolCapability | None":
        if not data:
            return None
        return ToolCapability(
            capability_id=str(data.get("capability_id") or ""),
            category=str(data.get("category") or ""),
            problem_types=list(data.get("problem_types") or []),
            input_contract=dict(data.get("input_contract") or {}),
            output_contract=dict(data.get("output_contract") or {}),
            evidence_fields=list(data.get("evidence_fields") or []),
            risk_level=str(data.get("risk_level") or "low"),
            requires_confirmation=bool(data.get("requires_confirmation", False)),
            dependencies=list(data.get("dependencies") or []),
            fallback_tools=list(data.get("fallback_tools") or []),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "category": self.category,
            "problem_types": self.problem_types,
            "input_contract": self.input_contract,
            "output_contract": self.output_contract,
            "evidence_fields": self.evidence_fields,
            "risk_level": self.risk_level,
            "requires_confirmation": self.requires_confirmation,
            "dependencies": self.dependencies,
            "fallback_tools": self.fallback_tools,
        }


def _to_tool_result(result: Any) -> ToolResult:
    """Normalize any tool return to ToolResult."""
    if isinstance(result, ToolResult):
        return result
    summary = str(result)
    artifact = _artifact_from_chart_saved(summary)
    if artifact:
        return ToolResult(summary=summary, artifacts=[artifact])
    return ToolResult.from_str(summary)


class ToolTimeoutError(Exception):
    pass


# === Default error recovery hint ===

_DEFAULT_RECOVERY_HINT = (
    "\n[恢复建议] 工具执行失败。请检查参数正确性或尝试替代方法。"
)


def _classify_error(error_json: str) -> str:
    """Classify error JSON into a category for targeted recovery hints."""
    msg = error_json.lower()
    try:
        data = json.loads(error_json)
        msg = data.get("error", "").lower()
    except (json.JSONDecodeError, ValueError):
        pass

    if any(kw in msg for kw in ("列", "column")) and ("not" in msg or "不" in msg or "不存在" in msg):
        return "missing_column"
    if "not found" in msg or "file not found" in msg:
        return "missing_data"
    if "不存在" in msg:
        return "missing_data"
    if any(kw in msg for kw in ("type", "类型", "cannot", "无法转换", "dtype")):
        return "type_mismatch"
    if any(kw in msg for kw in ("timeout", "超时", "timed out", "exceeded")):
        return "timeout"
    if any(kw in msg for kw in ("parameter", "参数", "invalid", "无效")):
        return "invalid_parameter"
    if any(kw in msg for kw in ("安全", "sandbox", "not allowed", "不允许")):
        return "sandbox_violation"
    if any(kw in msg for kw in ("太少", "too few", "insufficient", "不足", "数据点")):
        return "insufficient_data"
    return "unknown"


_ERROR_HINTS: dict[str, str] = {
    "missing_data": (
        "\n[恢复建议] 数据或文件不存在。"
        "请用 list_data 查看已加载数据集，或检查文件路径是否正确。"
    ),
    "missing_column": (
        "\n[恢复建议] 列名不存在。"
        "请用 preview_data 或 describe_dataset 查看实际列名，注意列名拼写和大小写。"
    ),
    "type_mismatch": (
        "\n[恢复建议] 数据类型不匹配。"
        "请用 describe_dataset 检查列类型，或用 suggest_column_types 获取类型转换建议。"
    ),
    "timeout": (
        "\n[恢复建议] 操作超时，数据量可能过大。"
        "建议先通过 transform_data(filter) 缩小数据范围后再操作。"
    ),
    "invalid_parameter": (
        "\n[恢复建议] 参数无效。"
        "请检查参数格式和取值范围，参考工具描述中的参数说明。"
    ),
    "sandbox_violation": (
        "\n[恢复建议] 代码执行被安全策略阻止。"
        "请优先使用结构化工具（transform_data, describe_dataset 等）替代自由代码。"
    ),
    "insufficient_data": (
        "\n[恢复建议] 数据不足以执行此分析。"
        "请记录此限制，选择对数据量要求更低的分析方法。"
    ),
    "unknown": (
        "\n[恢复建议] 工具执行失败。"
        "请检查参数正确性，或使用 ask_user_question 请求用户提供更多上下文。"
    ),
}


def _build_recovery_hint(error_json: str) -> str:
    """Build a recovery hint based on error type classification."""
    category = _classify_error(error_json)
    return _ERROR_HINTS.get(category, _DEFAULT_RECOVERY_HINT)


# === Tool groups and phases ===

# Write-capability categories that mutate shared state (workspace, state, filesystem).
_WRITE_CATEGORIES: frozenset[str] = frozenset({
    "data_transform", "data_write", "artifact", "evidence",
    "report", "visualization", "fallback", "confirmation",
    "workflow", "interaction.confirmation",
})


def _is_read_only(tool_def) -> bool:
    """Determine if a tool is safe for parallel execution based on its capability metadata.

    A tool is read-only if:
    - Its ToolCapability has risk_level == "low" AND category not in _WRITE_CATEGORIES
    - OR it has no capability defined AND it's not in the known write-tools list
    """
    cap = tool_def.capability
    if cap is not None:
        if cap.risk_level != "low":
            return False
        if cap.category in _WRITE_CATEGORIES:
            return False
        # Tools that require confirmation are never read-only
        if cap.requires_confirmation:
            return False
        return True

    # Fallback: no capability metadata — check against known write-tools
    known_write = {
        "load_data", "load_sql", "export_data", "export_output",
        "transform_data", "derive_field", "run_python",
        "ask_user_question", "create_chart",
        "record_data_requirement", "record_analysis_spec", "record_analysis_plan",
        "record_evidence_record", "record_insight_record",
        "generate_report", "generate_analysis_brief", "generate_formal_report",
        "export_conversation",
        "clean_data", "apply_type_conversion",
        "load_skill", "update_project_rules",
        "task_create", "task_update",
    }
    return tool_def.name not in known_write


def get_read_only_tools(registry_instance: ToolRegistry) -> frozenset[str]:
    """Compute the set of read-only tool names from registry metadata."""
    registry_instance._ensure_discovered()
    return frozenset(
        name for name, tool in registry_instance._tools.items()
        if _is_read_only(tool)
    )


# Lazy-evaluated module-level accessor for read-only tools.
# Use get_read_only_tools(registry) for fresh computation, or READ_ONLY_TOOLS for cached.
READ_ONLY_TOOLS: frozenset[str] = frozenset()  # Populated lazily

TOOL_GROUPS: dict[str, set[str]] = {
    "core": {
        "load_data", "load_sql", "list_data", "export_output",
        "transform_data", "derive_field",
        "run_python", "ask_user_question", "create_chart",
        "tool_search",
        "record_data_requirement", "record_analysis_spec", "record_analysis_plan",
        "record_evidence_record",
        "record_insight_record",
    },
    "eda": {
        "analyze_time_series", "correlation_analysis",
        "distribution_analysis", "segmentation_analysis", "cohort_analysis",
        "quick_profile",
        "describe_dataset", "preview_data",
        "compare_periods", "top_n",
        "contribute_decomposition", "funnel_analysis",
        "interpret_dataset",
    },
    "ml": {
        "regression_analysis", "classification", "forecast",
        "shap_analysis",
        "derive_features",
        "what_if_simulation",
    },
    "stats": {
        "ab_test", "causal_analysis", "attribution_analysis",
        "contribute_decomposition", "factor_relationship_analysis",
    },
    "report": {
        "export_conversation",
    },
    "deprecated_report_artifacts": {
        "generate_report", "generate_analysis_brief", "generate_formal_report",
    },
    "clean": {
        "suggest_column_types", "apply_type_conversion", "clean_data",
    },
    "task": {
        "task_create", "task_update", "task_get", "task_list",
    },
    "knowledge": {
        "show_project_rules", "update_project_rules",
        "load_skill", "list_skills",
    },
    "conversation_query": {
        "get_analysis_summary",
    },
}


def _cap(
    capability_id: str,
    category: str,
    problem_types: list[str],
    *,
    evidence_fields: list[str] | None = None,
    risk_level: str = "low",
    requires_confirmation: bool = False,
    dependencies: list[str] | None = None,
    fallback_tools: list[str] | None = None,
) -> ToolCapability:
    return ToolCapability(
        capability_id=capability_id,
        category=category,
        problem_types=problem_types,
        evidence_fields=evidence_fields or [],
        risk_level=risk_level,
        requires_confirmation=requires_confirmation,
        dependencies=dependencies or [],
        fallback_tools=fallback_tools or [],
    )


DEFAULT_TOOL_CAPABILITIES: dict[str, ToolCapability] = {
    "list_data": _cap("data.list", "data_view", ["data_understanding"]),
    "preview_data": _cap("data.preview", "data_view", ["data_understanding"]),
    "describe_dataset": _cap("data.describe", "profile", ["data_understanding"], evidence_fields=["schema", "rows", "columns"]),
    "quick_profile": _cap(
        "data.profile",
        "profile",
        ["data_understanding", "quality"],
        evidence_fields=[
            "grain",
            "quality.missing",
            "quality.outliers",
            "quality.duplicates",
        ],
    ),
    "detect_data_quality": _cap("data.quality", "quality", ["quality"], evidence_fields=["missingness", "duplicates", "outliers"]),
    "compare_periods": _cap(
        "analysis.period_compare",
        "trend",
        ["trend", "attribution"],
        evidence_fields=[
            "periods", "metric_delta", "effective_sample_size", "denominator",
            "missingness", "estimand", "effect_estimate", "assumptions",
            "sample_adequacy", "period_definition", "period_comparability",
            "time_frequency", "missing_intervals", "window_comparability",
            "multiplicity_handling",
        ],
    ),
    "analyze_time_series": _cap(
        "analysis.time_series",
        "trend",
        ["trend", "monitoring"],
        evidence_fields=[
            "trend", "trend_statistics", "seasonality", "time_frequency", "missing_intervals",
            "window_comparability", "autocorrelation_awareness",
            "effective_sample_size", "missingness", "seasonality_estimability",
            "assumptions",
        ],
    ),
    "contribute_decomposition": _cap(
        "analysis.dimension_decomposition",
        "decomposition",
        ["attribution", "diagnosis"],
        evidence_fields=[
            "metric",
            "dimension",
            "decomposition.contribution",
            "multiplicity_handling",
            "top_positive",
            "top_negative",
            "allowed_claim_class",
        ],
    ),
    "top_n": _cap("analysis.top_n", "decomposition", ["ranking", "diagnosis"], evidence_fields=["dimension", "metric"]),
    "funnel_analysis": _cap("analysis.funnel", "funnel", ["funnel", "conversion"], evidence_fields=["steps", "conversion_rate", "dropoff"]),
    "cohort_analysis": _cap("analysis.cohort", "retention", ["retention", "lifecycle"], evidence_fields=["cohort", "retention_rate"]),
    "correlation_analysis": _cap(
        "analysis.correlation",
        "relationship",
        ["drivers", "relationship"],
        evidence_fields=[
            "pairs.correlation",
            "pairs.effective_sample_size",
            "pairs.p_value",
            "assumptions",
            "allowed_claim_class",
        ],
        fallback_tools=["factor_relationship_analysis"],
    ),
    "ab_test": _cap(
        "analysis.experiment",
        "experiment",
        ["evaluation", "causal"],
        evidence_fields=[
            "effective_sample_size", "denominator", "missingness", "estimand",
            "effect_estimate", "confidence_interval", "test", "assumptions",
            "sample_adequacy",
        ],
        risk_level="medium",
        requires_confirmation=True,
    ),
    "causal_analysis": _cap("analysis.causal", "causal", ["causal", "evaluation"], evidence_fields=["effect", "assumptions"], risk_level="high", requires_confirmation=True),
    "attribution_analysis": _cap(
        "analysis.attribution",
        "attribution",
        ["attribution", "diagnosis"],
        evidence_fields=[
            "top_drivers",
            "effective_sample_size",
            "allowed_claim_class",
            "limitations",
        ],
        fallback_tools=["factor_relationship_analysis"],
    ),
    "forecast": _cap("analysis.forecast", "prediction", ["prediction", "monitoring"], evidence_fields=["forecast", "interval"], risk_level="medium", requires_confirmation=True),
    "regression_analysis": _cap(
        "analysis.regression",
        "modeling",
        ["drivers", "prediction"],
        evidence_fields=[
            "feature_importance",
            "effective_sample_size",
            "metrics.r2",
            "allowed_claim_class",
            "limitations",
        ],
        fallback_tools=["factor_relationship_analysis"],
    ),
    "factor_relationship_analysis": _cap(
        "analysis.factor_relationship",
        "relationship",
        ["drivers", "relationship"],
        evidence_fields=[
            "effective_sample_size",
            "coefficients.estimate",
            "coefficients.std_error",
            "coefficients.confidence_interval",
            "coefficients.p_value",
            "coefficients.adjusted_p_value",
            "collinearity",
            "time_dependence",
            "assumptions",
            "allowed_claim_class",
            "limitations",
        ],
        fallback_tools=["regression_analysis"],
    ),
    "classification": _cap("analysis.classification", "modeling", ["prediction", "segmentation"], evidence_fields=["metrics", "features"], risk_level="medium", requires_confirmation=True),
    "run_python": _cap("fallback.python", "fallback", ["custom"], risk_level="medium"),
    "ask_user_question": _cap("interaction.confirmation", "confirmation", ["confirmation"], risk_level="low"),
    "record_data_requirement": _cap("artifact.data_requirement", "analysis_artifact", ["planning"], evidence_fields=["required_data", "limitations"]),
    "record_analysis_spec": _cap("artifact.analysis_spec", "analysis_artifact", ["planning"], evidence_fields=["method_plan", "limitations"]),
    "record_analysis_plan": _cap("artifact.analysis_plan", "analysis_artifact", ["planning"], evidence_fields=["method_plan", "visualization_strategy", "statistical_validation_plan"]),
    "record_evidence_record": _cap("artifact.evidence_record", "evidence", ["evidence"], evidence_fields=["claim", "method", "confidence"]),
    "record_insight_record": _cap("artifact.insight_record", "insight", ["evidence", "report"], evidence_fields=["evidence_ids", "chart_ids", "limitations"]),
    "task_create": _cap("workflow.task_create", "workflow", ["planning", "execution"]),
    "task_update": _cap("workflow.task_update", "workflow", ["execution"]),
    "generate_report": _cap("report.generate", "report", ["report"], evidence_fields=["evidence_records", "limitations"]),
    "generate_analysis_brief": _cap("report.brief", "report", ["report", "summary"], evidence_fields=["evidence_records", "limitations"]),
    "generate_formal_report": _cap("report.formal", "report", ["report"], evidence_fields=["evidence_records", "chart_artifacts", "limitations"]),
    "export_conversation": _cap("report.conversation_export", "report", ["export"], evidence_fields=["conversation"]),
    "create_chart": _cap("visual.chart", "visualization", ["report", "exploration"], evidence_fields=["chart"]),
}


def _resolve_dotted_path(payload: Mapping[str, Any], field: str) -> Any:
    """Resolve a dotted evidence field path through nested mappings.

    Each path segment must be present in a mapping at the previous level.
    Returns the located value, or ``None`` if any segment is missing or the
    traversal encounters a non-mapping before the path is consumed.
    """

    value: Any = payload
    for segment in field.split("."):
        if not isinstance(value, Mapping) or segment not in value:
            return None
        value = value[segment]
    return value


def _evidence_field_is_present(payload: Mapping[str, Any], field: str) -> bool:
    """Return True when the dotted evidence field exists with a non-empty value.

    A field path that traverses into a list (e.g. ``pairs.correlation``) is
    considered present when at least one list record exposes the trailing key.
    Numeric ``0``/``0.0`` and explicit ``None`` inside list records are
    accepted as evidence; only structural absence or a fully-empty traversal
    counts as missing.
    """

    segments = field.split(".")
    if not segments:
        return False

    value: Any = payload
    for index, segment in enumerate(segments):
        if isinstance(value, Mapping):
            if segment not in value:
                return False
            value = value[segment]
        elif isinstance(value, list):
            tail = ".".join(segments[index:])
            return any(
                isinstance(item, Mapping)
                and _resolve_dotted_path(item, tail) is not None
                for item in value
            )
        else:
            return False
    return value is not None


def validate_capability_output(
    capability: Mapping[str, Any] | None,
    payload: Mapping[str, Any],
) -> list[str]:
    """Return the dotted evidence fields declared by ``capability`` that are
    not present in a successful tool ``payload``.

    Capability metadata owns the evidence contract: every entry in
    ``evidence_fields`` MUST be resolvable through a real payload, otherwise
    the tool is advertising fields it does not produce. The resolver
    traverses dotted paths through nested mappings and (for one level only)
    list records, so declarations like ``pairs.effective_sample_size`` and
    ``coefficients.confidence_interval`` validate against the structured
    payloads emitted by the corresponding tools.

    Returns the list of missing field names in declaration order. An empty
    list means every declared field is observable in the payload.
    """

    if not capability:
        return []
    raw_fields = capability.get("evidence_fields") if isinstance(capability, Mapping) else None
    if not isinstance(raw_fields, list):
        return []
    missing: list[str] = []
    for field in raw_fields:
        if not isinstance(field, str) or not field:
            continue
        if not _evidence_field_is_present(payload, field):
            missing.append(field)
    return missing


# Keywords that trigger group activation
_GROUP_KEYWORDS: dict[str, list[str]] = {
    "report": ["报告", "完整分析", "全面分析", "综合分析", "分析报告", "完整报告"],
    "eda": ["趋势", "分布", "相关性", "时间序列", "探索", "分析", "为什么", "原因", "洞察", "对比", "Top", "排名", "最高", "最低", "漏斗", "转化", "贡献", "归因", "拆解", "分解"],
    "ml": ["预测", "forecast", "回归", "分类", "建模", "模拟", "what-if", "whatif", "如果", "假设"],
    "stats": ["比较", "对比", "A-B", "AB测试", "A/B", "归因", "因果关系", "显著性", "为什么", "原因", "贡献", "拆解", "分解"],
    "clean": ["清洗", "清理", "缺失值", "异常值", "数据质量"],
    "task": ["报告", "完整分析", "全面分析", "综合分析"],
}

# Tool name → group mapping (reverse lookup, built lazily)
_TOOL_TO_GROUP: dict[str, str] = {}


def _build_tool_to_group() -> dict[str, str]:
    if not _TOOL_TO_GROUP:
        for group, tools in TOOL_GROUPS.items():
            for t in tools:
                _TOOL_TO_GROUP[t] = group
    return _TOOL_TO_GROUP


def infer_groups_from_text(text: str) -> set[str]:
    """根据用户输入文本推断需要激活的工具分组。"""
    groups: set[str] = set()
    for group, keywords in _GROUP_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in text.lower():
                groups.add(group)
                break
    return groups


class ToolDefinition:
    __slots__ = (
        "name",
        "description",
        "func",
        "parameters",
        "origin",
        "recovery_hint",
        "requires",
        "capability",
        "argument_aliases",
        "compatibility_json_object_parameters",
    )

    def __init__(
        self,
        name: str,
        description: str,
        func: Callable,
        parameters: dict,
        origin: str = "native",
        recovery_hint: str = "",
        requires: list[str] | None = None,
        capability: ToolCapability | dict[str, Any] | None = None,
        argument_aliases: Mapping[str, str] | None = None,
        compatibility_json_object_parameters: set[str] | None = None,
    ):
        self.name = name
        self.description = description
        self.func = func
        self.parameters = parameters
        self.origin = origin
        self.recovery_hint = recovery_hint
        self.requires = requires or []
        self.capability = ToolCapability.from_dict(capability) if isinstance(capability, dict) else capability
        self.argument_aliases = dict(argument_aliases or {})
        self.compatibility_json_object_parameters = set(
            compatibility_json_object_parameters or set()
        )

    def to_llm_schema(self) -> dict:
        desc = self.description
        if self.origin != "native":
            desc = f"[{self.origin}] {desc}"
        return {
            "name": self.name,
            "description": desc,
            "parameters": self.parameters,
        }


def _python_type_to_json(py_type: Any) -> str:
    mapping = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        list: "array",
        dict: "object",
        type(None): "null",
    }
    return mapping.get(py_type, "string")


def _annotation_schema(annotation: Any) -> dict[str, Any]:
    if annotation is Any:
        return {}
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin in (Union, UnionType):
        non_none = [arg for arg in args if arg is not type(None)]
        schema = (
            _annotation_schema(non_none[0])
            if len(non_none) == 1
            else {"anyOf": [_annotation_schema(arg) for arg in non_none]}
        )
        if len(non_none) != len(args):
            schema["nullable"] = True
        return schema
    if origin is Literal:
        values = list(args)
        return {
            "type": _python_type_to_json(type(values[0])),
            "enum": values,
        }
    if origin in (list, tuple, set):
        item = args[0] if args else Any
        return {"type": "array", "items": _annotation_schema(item)}
    if origin is dict:
        value = args[1] if len(args) == 2 else Any
        return {
            "type": "object",
            "additionalProperties": _annotation_schema(value),
        }
    if inspect.isclass(annotation) and issubclass(annotation, Enum):
        values = [member.value for member in annotation]
        return {
            "type": _python_type_to_json(type(values[0])),
            "enum": values,
        }
    return {"type": _python_type_to_json(annotation)}


def _build_schema(func: Callable) -> dict:
    """从函数签名自动构建 JSON Schema parameters。"""
    signature = inspect.signature(func)
    hints = get_type_hints(func)
    properties: dict[str, Any] = {}
    required: list[str] = []

    for name, parameter in signature.parameters.items():
        if name in {"self", "cls"}:
            continue
        properties[name] = _annotation_schema(hints.get(name, str))
        if parameter.default is inspect.Parameter.empty:
            required.append(name)
        else:
            properties[name]["default"] = parameter.default
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


class ToolArgumentValidationError(ValueError):
    def __init__(self, *, issues: list[dict[str, Any]]):
        self.issues = issues
        super().__init__("invalid tool arguments")

    def to_payload(self) -> dict[str, Any]:
        return {
            "error": "工具参数不符合已声明契约。",
            "error_type": "invalid_tool_arguments",
            "issues": self.issues,
        }


class _ArgumentValueError(ValueError):
    def __init__(self, issue: str):
        self.issue = issue
        super().__init__(issue)


_BOOLEAN_STRINGS: dict[str, bool] = {
    "true": True,
    "false": False,
    "1": True,
    "0": False,
    "yes": True,
    "no": False,
    "on": True,
    "off": False,
}
_INTEGER_PATTERN = re.compile(r"^[+-]?\d+$")


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, Mapping):
        return "object"
    return type(value).__name__


def _matches_json_type_without_conversion(
    value: Any,
    schema: Mapping[str, Any],
) -> bool:
    expected_type = schema.get("type")
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "object":
        return isinstance(value, Mapping)
    if expected_type == "null":
        return value is None
    return False


def _distinct_normalized_values(values: list[Any]) -> list[Any]:
    distinct: list[Any] = []
    for value in values:
        if any(
            type(value) is type(existing) and value == existing
            for existing in distinct
        ):
            continue
        distinct.append(value)
    return distinct


def _normalize_schema_value(value: Any, schema: Mapping[str, Any]) -> Any:
    if value is None:
        if schema.get("nullable") is True or schema.get("type") == "null":
            return None
        raise _ArgumentValueError("null_not_allowed")

    variants = schema.get("anyOf")
    if isinstance(variants, list):
        exact_variants = [
            variant
            for variant in variants
            if _matches_json_type_without_conversion(value, variant)
        ]
        candidates = exact_variants or variants
        normalized_candidates: list[Any] = []
        for variant in candidates:
            try:
                normalized_candidates.append(
                    _normalize_schema_value(value, variant)
                )
            except _ArgumentValueError:
                continue
        distinct = _distinct_normalized_values(normalized_candidates)
        if len(distinct) == 1:
            return distinct[0]
        if len(distinct) > 1:
            issue = (
                "ambiguous_union_type"
                if exact_variants
                else "ambiguous_union_conversion"
            )
            raise _ArgumentValueError(issue)
        raise _ArgumentValueError("no_matching_union_type")

    expected_type = schema.get("type")
    if expected_type == "boolean":
        if isinstance(value, bool):
            normalized = value
        elif isinstance(value, str) and value in _BOOLEAN_STRINGS:
            normalized = _BOOLEAN_STRINGS[value]
        elif isinstance(value, int) and not isinstance(value, bool) and value in (0, 1):
            normalized = bool(value)
        else:
            raise _ArgumentValueError("invalid_boolean")
    elif expected_type == "integer":
        if isinstance(value, int) and not isinstance(value, bool):
            normalized = value
        elif isinstance(value, str) and _INTEGER_PATTERN.fullmatch(value):
            normalized = int(value)
        else:
            raise _ArgumentValueError("invalid_integer")
    elif expected_type == "number":
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if not math.isfinite(value):
                raise _ArgumentValueError("non_finite_number")
            normalized = value
        elif isinstance(value, str):
            try:
                normalized = float(value)
            except ValueError as exc:
                raise _ArgumentValueError("invalid_number") from exc
            if not math.isfinite(normalized):
                raise _ArgumentValueError("non_finite_number")
        else:
            raise _ArgumentValueError("invalid_number")
    elif expected_type == "string":
        if not isinstance(value, str):
            raise _ArgumentValueError("invalid_string")
        normalized = value
    elif expected_type == "array":
        if not isinstance(value, list):
            raise _ArgumentValueError("invalid_array")
        item_schema = schema.get("items")
        if not isinstance(item_schema, Mapping):
            normalized = list(value)
        else:
            normalized = [
                _normalize_schema_value(item, item_schema)
                for item in value
            ]
    elif expected_type == "object":
        if not isinstance(value, Mapping):
            raise _ArgumentValueError("invalid_object")
        properties = schema.get("properties")
        required = set(schema.get("required") or [])
        if not isinstance(properties, Mapping):
            properties = {}
        normalized_object: dict[str, Any] = {}
        for required_name in required:
            if required_name not in value:
                raise _ArgumentValueError(
                    f"missing_required_object_property:{required_name}"
                )
        additional = schema.get("additionalProperties", True)
        for key, item in value.items():
            if key in properties:
                normalized_object[key] = _normalize_schema_value(
                    item,
                    properties[key],
                )
            elif additional is False:
                raise _ArgumentValueError(f"unknown_object_property:{key}")
            elif isinstance(additional, Mapping):
                normalized_object[key] = _normalize_schema_value(
                    item,
                    additional,
                )
            else:
                normalized_object[key] = item
        normalized = normalized_object
    elif expected_type == "null":
        raise _ArgumentValueError("invalid_null")
    else:
        normalized = value

    enum_values = schema.get("enum")
    if isinstance(enum_values, list) and normalized not in enum_values:
        raise _ArgumentValueError("value_not_in_enum")
    return normalized


def normalize_tool_arguments(
    definition: ToolDefinition,
    params: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(params, Mapping):
        raise ToolArgumentValidationError(issues=[{
            "field": "$",
            "issue": "arguments_must_be_an_object",
        }])

    incoming = dict(params)
    issues: list[dict[str, Any]] = []
    aliased_targets: set[str] = set()
    for alias, target in definition.argument_aliases.items():
        if alias not in incoming:
            continue
        alias_value = incoming.pop(alias)
        if target in incoming:
            issues.append({
                "field": alias,
                "issue": "conflicting_alias",
                "target": target,
            })
            continue
        if (
            target in definition.compatibility_json_object_parameters
            and not isinstance(alias_value, str)
        ):
            issues.append({
                "field": alias,
                "issue": "compatibility_alias_requires_json_string",
                "target": target,
            })
            continue
        incoming[target] = alias_value
        aliased_targets.add(target)

    properties = definition.parameters.get("properties") or {}
    required = set(definition.parameters.get("required") or [])
    for key in incoming:
        if key not in properties:
            issues.append({
                "field": key,
                "issue": "unknown_argument",
            })
    for key in required:
        if key not in incoming:
            issues.append({
                "field": key,
                "issue": "missing_required_argument",
            })

    normalized: dict[str, Any] = {}
    for key, value in incoming.items():
        schema = properties.get(key)
        if not isinstance(schema, Mapping):
            continue
        if (
            key in aliased_targets
            and key in definition.compatibility_json_object_parameters
            and isinstance(value, str)
        ):
            try:
                decoded = json.loads(value)
            except json.JSONDecodeError:
                issues.append({
                    "field": key,
                    "issue": "invalid_compatibility_json_object",
                })
                continue
            if not isinstance(decoded, dict):
                issues.append({
                    "field": key,
                    "issue": "compatibility_json_must_decode_to_object",
                })
                continue
            value = decoded
        try:
            normalized[key] = _normalize_schema_value(value, schema)
        except _ArgumentValueError as exc:
            issues.append({
                "field": key,
                "issue": exc.issue,
                "expected_type": schema.get("type") or "union",
                "received_type": _type_name(value),
            })

    if issues:
        raise ToolArgumentValidationError(issues=issues)
    return normalized


def _schema_matches_annotation(
    visible_schema: Mapping[str, Any],
    annotation_schema: Mapping[str, Any],
) -> bool:
    if not annotation_schema:
        return True
    variants = annotation_schema.get("anyOf")
    if isinstance(variants, list):
        return any(
            _schema_matches_annotation(visible_schema, variant)
            for variant in variants
        )
    if visible_schema.get("type") != annotation_schema.get("type"):
        return False
    expected_enum = annotation_schema.get("enum")
    visible_enum = visible_schema.get("enum")
    if isinstance(expected_enum, list):
        if not isinstance(visible_enum, list):
            return False
        if any(value not in expected_enum for value in visible_enum):
            return False
    if annotation_schema.get("type") == "array":
        expected_items = annotation_schema.get("items")
        if isinstance(expected_items, Mapping) and expected_items:
            visible_items = visible_schema.get("items")
            if not isinstance(visible_items, Mapping):
                return False
            if not _schema_matches_annotation(visible_items, expected_items):
                return False
    if annotation_schema.get("type") == "object":
        expected_additional = annotation_schema.get("additionalProperties")
        if isinstance(expected_additional, Mapping) and expected_additional:
            visible_additional = visible_schema.get("additionalProperties")
            if isinstance(visible_additional, Mapping):
                if not _schema_matches_annotation(
                    visible_additional,
                    expected_additional,
                ):
                    return False
            else:
                visible_nested = visible_schema.get("properties")
                if not isinstance(visible_nested, Mapping) or any(
                    not _schema_matches_annotation(item, expected_additional)
                    for item in visible_nested.values()
                ):
                    return False
    return True


def validate_tool_definition_contract(
    definition: ToolDefinition,
) -> list[dict[str, Any]]:
    if definition.origin != "native":
        return []

    expected = _build_schema(definition.func)
    visible_properties = definition.parameters.get("properties") or {}
    expected_properties = expected["properties"]
    issues: list[dict[str, Any]] = []

    if definition.parameters.get("type") != expected["type"]:
        issues.append({
            "issue": "root_type_mismatch",
            "expected": expected["type"],
            "actual": definition.parameters.get("type"),
        })
    if definition.parameters.get("additionalProperties") is not False:
        issues.append({
            "issue": "additional_properties_mismatch",
            "expected": False,
            "actual": definition.parameters.get("additionalProperties"),
        })

    visible_names = set(visible_properties)
    expected_names = set(expected_properties)
    if visible_names != expected_names:
        issues.append({
            "issue": "parameter_names_mismatch",
            "missing": sorted(expected_names - visible_names),
            "extra": sorted(visible_names - expected_names),
        })

    visible_required = set(definition.parameters.get("required") or [])
    expected_required = set(expected["required"])
    if visible_required != expected_required:
        issues.append({
            "issue": "required_parameters_mismatch",
            "expected": sorted(expected_required),
            "actual": sorted(visible_required),
        })

    signature = inspect.signature(definition.func)
    for name in sorted(visible_names & expected_names):
        visible_schema = visible_properties[name]
        expected_schema = expected_properties[name]
        if not _schema_matches_annotation(visible_schema, expected_schema):
            issues.append({
                "field": name,
                "issue": "annotation_schema_mismatch",
                "expected": expected_schema,
                "actual": visible_schema,
            })
        parameter = signature.parameters[name]
        if parameter.default is not inspect.Parameter.empty:
            if "default" not in visible_schema:
                issues.append({
                    "field": name,
                    "issue": "missing_default",
                    "expected": parameter.default,
                })
            elif visible_schema["default"] != parameter.default:
                issues.append({
                    "field": name,
                    "issue": "default_mismatch",
                    "expected": parameter.default,
                    "actual": visible_schema["default"],
                })
            try:
                _normalize_schema_value(
                    parameter.default,
                    visible_schema,
                )
            except _ArgumentValueError as exc:
                issues.append({
                    "field": name,
                    "issue": "default_schema_mismatch",
                    "default": parameter.default,
                    "schema_issue": exc.issue,
                })

    for alias, target in definition.argument_aliases.items():
        if alias in visible_names or alias in expected_names:
            issues.append({
                "field": alias,
                "issue": "alias_must_be_hidden",
            })
        if target not in expected_names:
            issues.append({
                "field": alias,
                "issue": "alias_target_missing",
                "target": target,
            })

    compatibility_targets = definition.compatibility_json_object_parameters
    alias_targets = set(definition.argument_aliases.values())
    for target in sorted(compatibility_targets):
        if target not in expected_names:
            issues.append({
                "field": target,
                "issue": "compatibility_target_missing",
            })
        if target not in alias_targets:
            issues.append({
                "field": target,
                "issue": "compatibility_decoder_requires_alias",
            })
        target_schema = visible_properties.get(target)
        if not isinstance(target_schema, Mapping) or target_schema.get("type") != "object":
            issues.append({
                "field": target,
                "issue": "compatibility_decoder_requires_object_schema",
            })
    if compatibility_targets and not (
        definition.name == "record_analysis_plan"
        and definition.argument_aliases == {"plan_json": "plan"}
        and compatibility_targets == {"plan"}
    ):
        issues.append({
            "issue": "unsupported_compatibility_json_object_decoder",
        })

    return issues


class ToolRegistry:
    """工具注册中心，管理所有可用工具。支持按需加载和中间件钩子。"""

    def __init__(self):
        self._tools: dict[str, ToolDefinition] = {}
        self._timeouts: dict[str, int] = {}
        self._default_timeout: int = 60
        self._discovered: bool = False
        # 按需加载状态
        self._active_groups: set[str] = {"core"}
        # Middleware hooks
        self._before_hooks: list[Callable] = []
        self._after_hooks: list[Callable] = []
        self._executed_tools: set[str] = set()
        self._capabilities: dict[str, ToolCapability] = {}

    def _ensure_discovered(self) -> None:
        """惰性发现：首次访问工具列表时自动扫描 tools 包。"""
        if self._discovered:
            return
        self._discovered = True
        try:
            from data_agent.tools import discover_tools
            discover_tools()
        except Exception:
            pass

    # === Middleware ===

    def add_before_hook(self, hook: Callable) -> None:
        """注册工具执行前钩子。hook(name: str, params: dict) -> None"""
        self._before_hooks.append(hook)

    def add_after_hook(self, hook: Callable) -> None:
        """注册工具执行后钩子。hook(name: str, params: dict, result: ToolResult, duration_ms: float) -> None"""
        self._after_hooks.append(hook)

    # === Group activation ===

    def activate_groups(self, groups: set[str]) -> None:
        """激活指定的工具分组。"""
        self._get_active_groups().update(groups - {"core"})

    def activate_groups_for_text(self, text: str) -> set[str]:
        """根据文本内容推断并激活需要的工具分组，返回新激活的分组。"""
        active = self._get_active_groups()
        new_groups = infer_groups_from_text(text) - active
        if new_groups:
            active.update(new_groups)
        return new_groups

    def reset_groups(self) -> None:
        """重置活跃工具分组为默认状态（仅 core）。应在每轮 turn 开始时调用。"""
        ctx = self._current_context()
        if ctx is not None:
            ctx.reset_turn_state()
            return
        self._active_groups = {"core"}
        self._executed_tools.clear()

    def _current_context(self):
        try:
            from data_agent.agent.context import get_current_context
            return get_current_context()
        except Exception:
            return None

    def _get_active_groups(self) -> set[str]:
        ctx = self._current_context()
        if ctx is not None:
            return ctx.active_tool_groups
        return self._active_groups

    def _get_executed_tools(self) -> set[str]:
        ctx = self._current_context()
        if ctx is not None:
            return ctx.executed_tools
        return self._executed_tools

    def _active_tool_names(self) -> set[str]:
        """获取当前活跃的所有工具名称。"""
        self._ensure_discovered()
        lookup = _build_tool_to_group()
        active_groups = self._get_active_groups()
        names: set[str] = set()
        for tool_name in self._tools:
            group = lookup.get(tool_name, "core")
            if group in active_groups:
                names.add(tool_name)
        # 未在分组中定义的工具默认包含（如 MCP 工具）
        for tool_name in self._tools:
            if tool_name not in lookup:
                names.add(tool_name)
        return names

    def active_definitions(self) -> list[dict]:
        """返回当前活跃工具的 LLM schema 定义列表。"""
        active_names = self._active_tool_names()
        return [
            t.to_llm_schema()
            for t in self._tools.values()
            if t.name in active_names
        ]

    def expand_from_tool_call(self, tool_name: str) -> None:
        """根据 LLM 调用的工具名称，自动扩展相关工具分组。"""
        lookup = _build_tool_to_group()
        group = lookup.get(tool_name)
        active = self._get_active_groups()
        if group and group not in active:
            active.add(group)

    # === Registration ===

    def register(
        self,
        name: Optional[str] = None,
        description: Optional[str] = None,
        parameters: Optional[dict] = None,
        schema_overrides: Optional[dict[str, dict]] = None,
        recovery_hint: Optional[str] = None,
        requires: Optional[list[str]] = None,
        capability: ToolCapability | dict[str, Any] | None = None,
        argument_aliases: Mapping[str, str] | None = None,
        compatibility_json_object_parameters: set[str] | None = None,
    ) -> Callable:
        """装饰器，注册一个工具函数。

        schema_overrides: 可选的参数增强，格式 {"param_name": {"description": "...", "enum": [...]}}
        仅在未手动提供 parameters 时生效，会 merge 到自动生成的 schema 中。
        recovery_hint: 可选的工具自定义错误恢复提示。
        requires: 可选的前置条件，列出必须先执行的工具名。
        """

        def decorator(func: Callable) -> Callable:
            tool_name = name or func.__name__
            tool_desc = description or func.__doc__ or "No description"
            tool_params = parameters or _build_schema(func)
            # 将 schema_overrides merge 到自动生成的 properties 中
            if schema_overrides and not parameters:
                props = tool_params.get("properties", {})
                for pname, override in schema_overrides.items():
                    if pname in props:
                        props[pname].update(override)
            self._tools[tool_name] = ToolDefinition(
                name=tool_name,
                description=tool_desc,
                func=func,
                parameters=tool_params,
                origin="native",
                recovery_hint=recovery_hint or "",
                requires=requires or [],
                capability=capability or DEFAULT_TOOL_CAPABILITIES.get(tool_name),
                argument_aliases=argument_aliases,
                compatibility_json_object_parameters=(
                    compatibility_json_object_parameters
                ),
            )
            if self._tools[tool_name].capability is not None:
                self._capabilities[tool_name] = self._tools[tool_name].capability
            return func

        return decorator

    def add(
        self,
        name: str,
        description: str,
        func: Callable,
        parameters: Optional[dict] = None,
        origin: str = "native",
        recovery_hint: str = "",
        requires: Optional[list[str]] = None,
        capability: ToolCapability | dict[str, Any] | None = None,
        argument_aliases: Mapping[str, str] | None = None,
        compatibility_json_object_parameters: set[str] | None = None,
    ):
        """直接注册一个工具函数。"""
        tool_params = parameters or _build_schema(func)
        self._tools[name] = ToolDefinition(
            name=name,
            description=description,
            func=func,
            parameters=tool_params,
            origin=origin,
            recovery_hint=recovery_hint,
            requires=requires or [],
            capability=capability or DEFAULT_TOOL_CAPABILITIES.get(name),
            argument_aliases=argument_aliases,
            compatibility_json_object_parameters=(
                compatibility_json_object_parameters
            ),
        )
        if self._tools[name].capability is not None:
            self._capabilities[name] = self._tools[name].capability

    def set_capability(self, tool_name: str, capability: ToolCapability | dict[str, Any]) -> None:
        cap = ToolCapability.from_dict(capability) if isinstance(capability, dict) else capability
        if cap is None:
            return
        self._capabilities[tool_name] = cap
        if tool_name in self._tools:
            self._tools[tool_name].capability = cap

    def capability_for(self, tool_name: str) -> dict[str, Any] | None:
        cap = self._capabilities.get(tool_name)
        if cap is None and tool_name in DEFAULT_TOOL_CAPABILITIES:
            cap = DEFAULT_TOOL_CAPABILITIES[tool_name]
        return cap.to_dict() if cap else None

    def capability_definitions(self, active_only: bool = False) -> list[dict[str, Any]]:
        self._ensure_discovered()
        names = self._active_tool_names() if active_only else set(self._tools)
        results = []
        for name in sorted(names):
            cap = self.capability_for(name)
            if cap:
                cap = dict(cap)
                cap["tool_name"] = name
                results.append(cap)
        return results

    def tools_for_capability(self, capability_id: str) -> list[str]:
        matches = []
        for cap in self.capability_definitions(active_only=False):
            if cap.get("capability_id") == capability_id:
                matches.append(cap["tool_name"])
        return matches

    # === Execution ===

    def set_timeout(self, name: str, seconds: int) -> None:
        """设置指定工具的超时时间（秒）。"""
        self._timeouts[name] = seconds

    def get(self, name: str) -> Optional[ToolDefinition]:
        return self._tools.get(name)

    def execute(self, name: str, params: dict[str, Any]) -> ToolResult:
        """执行指定工具，返回 ToolResult。带前置条件检查、超时保护和中间件钩子。"""
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(summary=json.dumps({"error": f"Unknown tool: {name}"}, ensure_ascii=False))

        try:
            params = normalize_tool_arguments(tool, params)
        except ToolArgumentValidationError as exc:
            payload = exc.to_payload()
            return ToolResult(
                summary=json.dumps(payload, ensure_ascii=False),
                data=payload,
            )

        # 前置条件检查
        if tool.requires:
            executed = self._get_executed_tools()
            missing = [r for r in tool.requires if r not in executed]
            if missing:
                return ToolResult(
                    summary=json.dumps({
                        "error": f"前置条件未满足: 需要先执行 {missing}",
                        "requires": tool.requires,
                        "missing": missing,
                    }, ensure_ascii=False),
                    suggested_next=missing[0],
                )

        # Before hooks
        for hook in self._before_hooks:
            try:
                hook(name, params)
            except Exception:
                pass

        timeout = self._timeouts.get(name, self._default_timeout)
        t0 = time.monotonic()

        try:
            if timeout > 0:
                result = self._run_with_timeout(tool.func, params, timeout)
            else:
                result = tool.func(**params)

            tool_result = _to_tool_result(result)
            self._get_executed_tools().add(name)

        except ToolTimeoutError:
            tool_result = ToolResult(
                summary=json.dumps(
                    {"error": f"Tool '{name}' timed out after {timeout}s"},
                    ensure_ascii=False,
                )
            )
        except Exception as e:
            # UserConfirmationRequired 必须透传给 AgentLoop 的 suspension 机制
            from data_agent.agent.loop import UserConfirmationRequired as _UCC
            if isinstance(e, _UCC):
                raise
            tool_result = ToolResult(
                summary=json.dumps({"error": str(e)}, ensure_ascii=False)
            )

        duration_ms = (time.monotonic() - t0) * 1000

        # After hooks
        for hook in self._after_hooks:
            try:
                hook(name, params, tool_result, duration_ms)
            except Exception:
                pass

        return tool_result

    def format_result(self, name: str, result: ToolResult) -> str:
        """Format a tool result for LLM consumption, appending context-aware recovery hints."""
        output = result.to_cli()
        if not (output.startswith('{"error":') or output.startswith('{"error": ')):
            return output

        tool = self._tools.get(name)

        # Priority 1: tool-specific recovery_hint
        if tool and tool.recovery_hint:
            hint = f"\n[恢复建议] {tool.recovery_hint}"
        else:
            # Priority 2: exception-type based hint
            hint = _build_recovery_hint(output)

        # Append fallback tool recommendations
        if tool and tool.capability and tool.capability.fallback_tools:
            fallbacks = ", ".join(tool.capability.fallback_tools)
            hint += f"\n替代工具: {fallbacks}"

        return f"{output}{hint}"

    def _run_with_timeout(self, func: Callable, params: dict, timeout: int) -> Any:
        """在线程池中运行工具函数，超时则取消。Windows 兼容。"""
        ctx = copy_context()
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(lambda: ctx.run(func, **params))
            try:
                return future.result(timeout=timeout)
            except FuturesTimeout:
                raise ToolTimeoutError(f"Execution exceeded {timeout}s")

    # === Introspection ===

    def all_definitions(self) -> list[dict]:
        """返回所有工具的 LLM schema 定义列表。"""
        self._ensure_discovered()
        return [t.to_llm_schema() for t in self._tools.values()]

    def tool_names_by_origin(self, origin: str) -> list[str]:
        """按来源筛选工具名称。"""
        return [t.name for t in self._tools.values() if t.origin == origin]

    @property
    def tool_names(self) -> list[str]:
        self._ensure_discovered()
        return list(self._tools.keys())


# 全局注册中心
registry = ToolRegistry()


@registry.register(
    name="tool_search",
    description=(
        "搜索可用工具。当当前工具列表中没有需要的工具时，"
        "用关键词搜索所有已注册工具的名称和描述，返回匹配结果。"
        "返回的工具会自动激活其所在分组。"
    ),
    schema_overrides={
        "keyword": {"description": "搜索关键词（中文或英文）"},
    },
)
def tool_search(keyword: str) -> str:
    """搜索工具注册中心，返回名称或描述匹配的工具。"""
    if not keyword.strip():
        return json.dumps({"error": "请提供搜索关键词"}, ensure_ascii=False)

    kw = keyword.lower().strip()
    matches = []
    deprecated_tools = TOOL_GROUPS.get("deprecated_report_artifacts", set())
    for tool in registry._tools.values():
        if tool.name in deprecated_tools:
            continue
        score = 0
        if kw in tool.name.lower():
            score += 2
        if kw in tool.description.lower():
            score += 1
        if score > 0:
            matches.append({
                "name": tool.name,
                "description": tool.description[:200],
                "relevance": score,
            })

    matches.sort(key=lambda x: -x["relevance"])

    # 自动激活匹配工具所在分组
    for m in matches:
        registry.expand_from_tool_call(m["name"])

    result = {
        "keyword": keyword,
        "matches": len(matches),
        "tools": matches[:20],
    }
    return json.dumps(result, ensure_ascii=False, indent=2)
