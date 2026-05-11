from __future__ import annotations

import inspect
import json
import re
import time
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


def _to_tool_result(result: Any) -> ToolResult:
    """Normalize any tool return to ToolResult."""
    if isinstance(result, ToolResult):
        return result
    return ToolResult.from_str(str(result))


class ToolTimeoutError(Exception):
    pass


# === Default error recovery hint ===

_DEFAULT_RECOVERY_HINT = (
    "\n[系统提示] 工具执行失败。请按以下策略恢复：\n"
    "1. 检查参数是否正确（列名是否存在、数据类型是否匹配）\n"
    "2. 尝试使用替代工具或方法达到相同分析目标\n"
    "3. 如果是数据质量问题，先用 detect_data_quality 评估数据状态\n"
    "4. 如果无法自行恢复，通过 ask_user_question 请求用户提供更多上下文"
)


# === Tool groups and phases ===

TOOL_GROUPS: dict[str, set[str]] = {
    "core": {
        "load_data", "load_sql", "list_data", "export_output",
        "transform_data", "derive_field",
        "run_python", "ask_user_question", "create_chart",
        "tool_search",
        "record_analysis_spec", "record_evidence_record",
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
        "generate_report",
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
    __slots__ = ("name", "description", "func", "parameters", "origin", "recovery_hint", "requires")

    def __init__(
        self,
        name: str,
        description: str,
        func: Callable,
        parameters: dict,
        origin: str = "native",
        recovery_hint: str = "",
        requires: list[str] | None = None,
    ):
        self.name = name
        self.description = description
        self.func = func
        self.parameters = parameters
        self.origin = origin
        self.recovery_hint = recovery_hint
        self.requires = requires or []

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
        recovery_hint: str = "",
        requires: Optional[list[str]] = None,
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
        )

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
        """Format a tool result for LLM consumption, appending error recovery hints."""
        output = result.to_cli()
        if output.startswith('{"error":') or output.startswith('{"error": '):
            hint = _DEFAULT_RECOVERY_HINT
            tool = self._tools.get(name)
            if tool and tool.recovery_hint:
                hint = f"\n[系统提示] {tool.recovery_hint}"
            return f"{output}{hint}"
        return output

    def _run_with_timeout(self, func: Callable, params: dict, timeout: int) -> Any:
        """在线程池中运行工具函数，超时则取消。Windows 兼容。"""
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(func, **params)
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
    for tool in registry._tools.values():
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
