"""Plugin 协议定义：所有插件必须实现的接口。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass
class PluginInfo:
    """插件状态信息。"""
    name: str
    status: str  # "running", "stopped", "error"
    tool_count: int
    description: str = ""
    source: str = ""  # "global" 或 "project"


@runtime_checkable
class Plugin(Protocol):
    """插件协议。所有插件必须实现此接口。"""

    name: str

    def start(self) -> None:
        """启动插件（连接、初始化等）。"""
        ...

    def stop(self) -> None:
        """停止插件（断连、清理等）。"""
        ...

    def discover_tools(self) -> list[dict]:
        """返回此插件提供的工具定义列表（LLM schema 格式）。"""
        ...

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """调用此插件的指定工具。"""
        ...
