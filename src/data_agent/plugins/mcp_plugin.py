"""MCPPlugin：将 MCPClientManager 包装为 Plugin 接口。"""

from __future__ import annotations

from typing import Any

from data_agent.mcp.client import MCPClientManager
from data_agent.mcp.config import MCPServerConfig
from data_agent.utils.logging import get_logger

logger = get_logger("plugins.mcp")


class MCPPlugin:
    """MCP 插件：包装 MCPClientManager 实现 Plugin 协议。"""

    name: str

    def __init__(self, name: str, manager: MCPClientManager, server_config: MCPServerConfig):
        self.name = name
        self._manager = manager
        self._config = server_config

    def start(self) -> None:
        """连接到 MCP 服务器。"""
        self._manager._run_async(self._manager._connect(self._config))
        logger.info("MCPPlugin started", extra={"extra_data": {"server": self.name}})

    def stop(self) -> None:
        """断开 MCP 服务器连接。"""
        conn = self._manager._connections.get(self.name)
        if conn and conn.session:
            try:
                self._manager._run_async(conn.session.__aexit__(None, None, None))
            except Exception:
                pass
            self._manager._connections.pop(self.name, None)
        logger.info("MCPPlugin stopped", extra={"extra_data": {"server": self.name}})

    def discover_tools(self) -> list[dict]:
        """返回此 MCP 服务器提供的工具定义。"""
        conn = self._manager._connections.get(self.name)
        if conn is None or not conn.is_connected:
            return []

        return [
            {
                "name": t.tool_name,
                "description": t.description,
                "parameters": t.input_schema,
            }
            for t in conn.tools_cache
        ]

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """调用 MCP 工具。"""
        return self._manager.call_tool(self.name, tool_name, arguments)
