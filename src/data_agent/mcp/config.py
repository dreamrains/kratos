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


def _parse_mcp_config(content: bytes) -> MCPConfig:
    data = yaml.safe_load(content.decode("utf-8")) or {}
    if data.get("servers") is None:
        data["servers"] = []
    return MCPConfig(**data)


def load_mcp_config(path: Path) -> MCPConfig:
    """Load the configured YAML; an absent file means no configured servers."""
    return _parse_mcp_config(path.read_bytes()) if path.exists() else MCPConfig()


def mcp_config_state(path: Path) -> dict:
    """Bind exact file bytes and the existing parsed configuration together."""
    import hashlib
    path = path.resolve()
    content = path.read_bytes() if path.exists() else None
    config = _parse_mcp_config(content) if content is not None else MCPConfig()
    return {"path": str(path), "exists": content is not None,
            "sha256": "sha256:" + hashlib.sha256(content).hexdigest() if content is not None else None,
            "configuration": config.model_dump(exclude_none=True)}


def save_mcp_config(config: MCPConfig, path: Path) -> dict:
    """Commit one verified YAML snapshot, preserving old bytes on caught failure."""
    from data_agent.utils.atomic_files import rollback_atomic_writes, write_bytes_atomic
    data = config.model_dump(exclude_none=True)
    content = yaml.dump(data, default_flow_style=False, allow_unicode=True).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    with rollback_atomic_writes():
        write_bytes_atomic(path, content)
        state = mcp_config_state(path)
        if state["configuration"] != data or path.read_bytes() != content:
            raise ValueError("Saved MCP configuration does not match the requested snapshot")
        return state
