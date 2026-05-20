from __future__ import annotations

import inspect
import json
import re
import time
from contextvars import copy_context
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


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
        "load_skill", "update_project_rules", "set_domain", "confirm_experience",
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
        "contribute_decomposition",
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
        "show_domain_knowledge", "set_domain",
        "show_experience_log", "confirm_experience",
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
    "quick_profile": _cap("data.profile", "profile", ["data_understanding", "quality"], evidence_fields=["schema", "missingness", "distribution"]),
    "detect_data_quality": _cap("data.quality", "quality", ["quality"], evidence_fields=["missingness", "duplicates", "outliers"]),
    "compare_periods": _cap("analysis.period_compare", "trend", ["trend", "attribution"], evidence_fields=["periods", "metric_delta"]),
    "analyze_time_series": _cap("analysis.time_series", "trend", ["trend", "monitoring"], evidence_fields=["trend", "seasonality"]),
    "contribute_decomposition": _cap("analysis.dimension_decomposition", "decomposition", ["attribution", "diagnosis"], evidence_fields=["drivers", "contribution"]),
    "top_n": _cap("analysis.top_n", "decomposition", ["ranking", "diagnosis"], evidence_fields=["dimension", "metric"]),
    "funnel_analysis": _cap("analysis.funnel", "funnel", ["funnel", "conversion"], evidence_fields=["steps", "conversion_rate", "dropoff"]),
    "cohort_analysis": _cap("analysis.cohort", "retention", ["retention", "lifecycle"], evidence_fields=["cohort", "retention_rate"]),
    "correlation_analysis": _cap("analysis.correlation", "relationship", ["drivers", "relationship"], evidence_fields=["correlation", "p_value"]),
    "ab_test": _cap("analysis.experiment", "experiment", ["evaluation", "causal"], evidence_fields=["effect_size", "significance"], risk_level="medium", requires_confirmation=True),
    "causal_analysis": _cap("analysis.causal", "causal", ["causal", "evaluation"], evidence_fields=["effect", "assumptions"], risk_level="high", requires_confirmation=True),
    "attribution_analysis": _cap("analysis.attribution", "attribution", ["attribution", "diagnosis"], evidence_fields=["drivers", "limitations"]),
    "forecast": _cap("analysis.forecast", "prediction", ["prediction", "monitoring"], evidence_fields=["forecast", "interval"], risk_level="medium", requires_confirmation=True),
    "regression_analysis": _cap("analysis.regression", "modeling", ["drivers", "prediction"], evidence_fields=["coefficients", "fit"]),
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
    __slots__ = ("name", "description", "func", "parameters", "origin", "recovery_hint", "requires", "capability")

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
    ):
        self.name = name
        self.description = description
        self.func = func
        self.parameters = parameters
        self.origin = origin
        self.recovery_hint = recovery_hint
        self.requires = requires or []
        self.capability = ToolCapability.from_dict(capability) if isinstance(capability, dict) else capability

    def to_llm_schema(self) -> dict:
        desc = self.description
        if self.origin != "native":
            desc = f"[{self.origin}] {desc}"
        return {
            "name": self.name,
            "description": desc,
            "parameters": self.parameters,
        }


def _python_type_to_json(py_type: type) -> str:
    mapping = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        list: "array",
        dict: "object",
    }
    return mapping.get(py_type, "string")


def _build_schema(func: Callable) -> dict:
    """从函数签名自动构建 JSON Schema parameters。"""
    sig = inspect.signature(func)
    properties: dict[str, Any] = {}
    required: list[str] = []

    for pname, param in sig.parameters.items():
        if pname in ("self", "cls"):
            continue

        annotation = param.annotation
        if annotation is inspect.Parameter.empty:
            json_type = "string"
        else:
            json_type = _python_type_to_json(annotation)

        prop: dict[str, Any] = {"type": json_type}
        properties[pname] = prop

        if param.default is inspect.Parameter.empty:
            required.append(pname)

    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
    }
    if required:
        schema["required"] = required
    return schema


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
