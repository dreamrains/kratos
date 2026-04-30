from __future__ import annotations

import inspect
import json
import re
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
        return result

    def __str__(self) -> str:
        return self.to_cli()


def _to_tool_result(result: Any) -> ToolResult:
    """Normalize any tool return to ToolResult."""
    if isinstance(result, ToolResult):
        return result
    return ToolResult.from_str(str(result))


class ToolTimeoutError(Exception):
    pass


# === Tool groups and phases ===

TOOL_GROUPS: dict[str, set[str]] = {
    "core": {
        "load_data", "load_sql", "list_data", "export_data",
        "describe_dataset", "preview_data",
        "transform_data", "derive_field",
        "run_python", "ask_user_question", "create_chart",
        "task_create", "task_update", "task_get", "task_list",
    },
    "eda": {
        "analyze_time_series", "correlation_analysis",
        "distribution_analysis", "segmentation_analysis", "cohort_analysis",
        "quick_profile",
    },
    "ml": {
        "regression_analysis", "classification", "forecast",
        "shap_analysis",
    },
    "stats": {
        "ab_test", "causal_analysis", "attribution_analysis",
    },
    "report": {
        "generate_report", "export_report_markdown", "export_report_pdf",
    },
    "clean": {
        "suggest_column_types", "apply_type_conversion", "clean_data",
    },
    "knowledge": {
        "show_project_rules", "update_project_rules",
        "show_domain_knowledge", "add_domain_knowledge",
        "show_experience", "search_experience",
        "load_skill", "list_skills",
    },
}

# Keywords that trigger group activation
_GROUP_KEYWORDS: dict[str, list[str]] = {
    "report": ["报告", "完整分析", "全面分析", "综合分析", "分析报告", "完整报告"],
    "eda": ["趋势", "分布", "相关性", "时间序列", "探索", "分析", "为什么", "原因", "洞察"],
    "ml": ["预测", "forecast", "回归", "分类", "建模"],
    "stats": ["比较", "对比", "A-B", "AB测试", "A/B", "归因", "因果关系", "显著性", "为什么", "原因"],
    "clean": ["清洗", "清理", "缺失值", "异常值", "数据质量"],
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
    __slots__ = ("name", "description", "func", "parameters", "origin")

    def __init__(
        self,
        name: str,
        description: str,
        func: Callable,
        parameters: dict,
        origin: str = "native",
    ):
        self.name = name
        self.description = description
        self.func = func
        self.parameters = parameters
        self.origin = origin

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
    """工具注册中心，管理所有可用工具。支持按需加载。"""

    def __init__(self):
        self._tools: dict[str, ToolDefinition] = {}
        self._timeouts: dict[str, int] = {}
        self._default_timeout: int = 60
        self._discovered: bool = False
        # 按需加载状态
        self._active_groups: set[str] = {"core"}

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

    def activate_groups(self, groups: set[str]) -> None:
        """激活指定的工具分组。"""
        self._active_groups.update(groups - {"core"})

    def activate_groups_for_text(self, text: str) -> set[str]:
        """根据文本内容推断并激活需要的工具分组，返回新激活的分组。"""
        new_groups = infer_groups_from_text(text) - self._active_groups
        if new_groups:
            self._active_groups.update(new_groups)
        return new_groups

    def _active_tool_names(self) -> set[str]:
        """获取当前活跃的所有工具名称。"""
        self._ensure_discovered()
        lookup = _build_tool_to_group()
        names: set[str] = set()
        for tool_name in self._tools:
            group = lookup.get(tool_name, "core")
            if group in self._active_groups:
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
        # 如果工具不在活跃列表中但已注册，确保其分组被激活
        lookup = _build_tool_to_group()
        group = lookup.get(tool_name)
        if group and group not in self._active_groups:
            self._active_groups.add(group)

    def register(
        self,
        name: Optional[str] = None,
        description: Optional[str] = None,
        parameters: Optional[dict] = None,
    ) -> Callable:
        """装饰器，注册一个工具函数。"""

        def decorator(func: Callable) -> Callable:
            tool_name = name or func.__name__
            tool_desc = description or func.__doc__ or "No description"
            tool_params = parameters or _build_schema(func)
            self._tools[tool_name] = ToolDefinition(
                name=tool_name,
                description=tool_desc,
                func=func,
                parameters=tool_params,
                origin="native",
            )
            return func

        return decorator

    def add(
        self,
        name: str,
        description: str,
        func: Callable,
        parameters: Optional[dict] = None,
        origin: str = "native",
    ):
        """直接注册一个工具函数。"""
        tool_params = parameters or _build_schema(func)
        self._tools[name] = ToolDefinition(
            name=name,
            description=description,
            func=func,
            parameters=tool_params,
            origin=origin,
        )

    def set_timeout(self, name: str, seconds: int) -> None:
        """设置指定工具的超时时间（秒）。"""
        self._timeouts[name] = seconds

    def get(self, name: str) -> Optional[ToolDefinition]:
        return self._tools.get(name)

    def execute(self, name: str, params: dict[str, Any]) -> ToolResult:
        """执行指定工具，返回 ToolResult。带超时保护。"""
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(summary=json.dumps({"error": f"Unknown tool: {name}"}, ensure_ascii=False))

        timeout = self._timeouts.get(name, self._default_timeout)

        try:
            if timeout > 0:
                result = self._run_with_timeout(tool.func, params, timeout)
            else:
                result = tool.func(**params)

            return _to_tool_result(result)

        except ToolTimeoutError:
            return ToolResult(
                summary=json.dumps(
                    {"error": f"Tool '{name}' timed out after {timeout}s"},
                    ensure_ascii=False,
                )
            )
        except Exception as e:
            return ToolResult(
                summary=json.dumps({"error": str(e)}, ensure_ascii=False)
            )

    def _run_with_timeout(self, func: Callable, params: dict, timeout: int) -> Any:
        """在线程池中运行工具函数，超时则取消。Windows 兼容。"""
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(func, **params)
            try:
                return future.result(timeout=timeout)
            except FuturesTimeout:
                raise ToolTimeoutError(f"Execution exceeded {timeout}s")

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
