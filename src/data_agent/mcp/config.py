"""MCP 服务器配置模型与加载。"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional

import yaml
from pydantic import BaseModel, model_validator


class MCPServerConfig(BaseModel):
    """单个 MCP 服务器配置。"""
    name: str
    transport: Literal["stdio", "sse", "streamable-http"]
    # stdio 字段
    command: Optional[str] = None
    args: Optional[list[str]] = None
    env: Optional[dict[str, str]] = None
    # sse / streamable-http 字段
    url: Optional[str] = None
    headers: Optional[dict[str, str]] = None
    # 行为配置
    auto_start: bool = True
    tool_prefix: str = ""
    enabled: bool = True

    @model_validator(mode="after")
    def validate_transport(self) -> "MCPServerConfig":
        if self.transport == "stdio" and not self.command:
            raise ValueError(f"stdio transport requires 'command' (server: {self.name})")
        if self.transport in ("sse", "streamable-http") and not self.url:
            raise ValueError(f"{self.transport} transport requires 'url' (server: {self.name})")
        return self


class MCPConfig(BaseModel):
    """MCP 全局配置。"""
    servers: list[MCPServerConfig] = []


def load_mcp_config(path: Path) -> MCPConfig:
    """从 YAML 文件加载 MCP 服务器配置。"""
    if not path.exists():
        return MCPConfig()

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    # 处理 servers 为 None 的情况（YAML 文件中 servers 为空列表）
    if data.get("servers") is None:
        data["servers"] = []

    return MCPConfig(**data)


def save_mcp_config(config: MCPConfig, path: Path) -> None:
    """将 MCP 配置保存到 YAML 文件。"""
    data = {
        "servers": [
            s.model_dump(exclude_none=True) for s in config.servers
        ]
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
