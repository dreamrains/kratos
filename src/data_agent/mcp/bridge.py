"""MCP 工具桥：将 MCP 发现的工具透明注册到 ToolRegistry。

参考 s_full.py TOOL_HANDLERS 模式，每个 MCP 工具通过闭包包装，
注册后与原生工具无差别地参与 registry 的调度。
"""

from __future__ import annotations

from typing import Callable

from data_agent.mcp.client import MCPClientManager
from data_agent.mcp.models import MCPToolDef
from data_agent.tools.registry import ToolRegistry


class MCPToolBridge:
    """将 MCP 工具桥接到 ToolRegistry。"""

    def __init__(self, manager: MCPClientManager, registry: ToolRegistry):
        self._manager = manager
        self._registry = registry
        self._registered: list[str] = []

    def register_all(self) -> list[str]:
        """发现所有 MCP 工具并注册到 ToolRegistry。返回已注册的工具名列表。"""
        self._registered.clear()
        tools = self._manager.discover_tools()

        for mcp_tool in tools:
            wrapper = self._make_wrapper(mcp_tool)
            self._registry.add(
                name=mcp_tool.full_name,
                description=f"[MCP:{mcp_tool.server_name}] {mcp_tool.description}",
                func=wrapper,
                parameters=mcp_tool.input_schema,
                origin=f"mcp:{mcp_tool.server_name}",
            )
            self._registered.append(mcp_tool.full_name)

        return self._registered

    def _make_wrapper(self, tool_def: MCPToolDef) -> Callable:
        """为 MCP 工具创建同步包装函数（通过闭包捕获 server/tool 名称）。"""
        server_name = tool_def.server_name
        tool_name = tool_def.tool_name

        def wrapper(**kwargs) -> str:
            return self._manager.call_tool(server_name, tool_name, kwargs)

        wrapper.__name__ = tool_def.full_name
        return wrapper

    def unregister_all(self) -> None:
        """移除所有已注册的 MCP 工具。"""
        for name in self._registered:
            tool = self._registry.get(name)
            if tool and tool.origin.startswith("mcp:"):
                del self._registry._tools[name]
        self._registered.clear()

    def register_server(self, server_name: str) -> list[str]:
        """注册单个 MCP 服务器的工具。返回注册的工具名列表。"""
        conn = self._manager._connections.get(server_name)
        if conn is None:
            return []

        registered = []
        for mcp_tool in conn.tools_cache:
            if mcp_tool.full_name not in self._registered:
                wrapper = self._make_wrapper(mcp_tool)
                self._registry.add(
                    name=mcp_tool.full_name,
                    description=f"[MCP:{mcp_tool.server_name}] {mcp_tool.description}",
                    func=wrapper,
                    parameters=mcp_tool.input_schema,
                    origin=f"mcp:{mcp_tool.server_name}",
                )
                self._registered.append(mcp_tool.full_name)
                registered.append(mcp_tool.full_name)

        return registered

    def unregister_server(self, server_name: str) -> list[str]:
        """移除指定 MCP 服务器的所有工具。"""
        prefix = f"mcp:{server_name}"
        removed = []
        to_remove = [n for n in self._registered
                     if n in self._registry._tools
                     and self._registry._tools[n].origin == prefix]
        for name in to_remove:
            del self._registry._tools[name]
            self._registered.remove(name)
            removed.append(name)
        return removed
