"""MCP 工具定义数据模型。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MCPToolDef:
    """MCP 工具定义。"""
    server_name: str
    tool_name: str
    description: str
    input_schema: dict

    @property
    def full_name(self) -> str:
        return f"{self.server_name}__{self.tool_name}"
