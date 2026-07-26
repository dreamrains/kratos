"""MCP runtime and configuration management tools."""

from __future__ import annotations

import json

from data_agent.config import get_config
from data_agent.mcp.config import MCPServerConfig, load_mcp_config, save_mcp_config
from data_agent.tools.registry import registry


def _config_path():
    return get_config().global_mcp_config_path


def _load_config():
    return load_mcp_config(_config_path())


def _save_config(config) -> None:
    save_mcp_config(config, _config_path())


@registry.register(
    name="call_mcp_tool",
    description="Call a tool exposed by a connected MCP server.",
    parameters={
        "type": "object",
        "properties": {
            "server": {"type": "string", "description": "MCP server name"},
            "tool": {"type": "string", "description": "Tool name on the server"},
            "arguments": {
                "type": "string",
                "description": "JSON-formatted tool arguments",
                "default": "{}",
            },
        },
        "required": ["server", "tool"],
        "additionalProperties": False,
    },
)
def call_mcp_tool(server: str, tool: str, arguments: str = "{}") -> str:
    from data_agent.agent.loop import get_mcp_manager

    mcp_mgr = get_mcp_manager()
    if mcp_mgr is None:
        return json.dumps({"error": "MCP not configured or not enabled"}, ensure_ascii=False)

    try:
        args = json.loads(arguments) if isinstance(arguments, str) else arguments
    except json.JSONDecodeError:
        return json.dumps({"error": "Invalid JSON in arguments"}, ensure_ascii=False)

    return mcp_mgr.call_tool(server, tool, args)


@registry.register(
    name="list_mcp_servers",
    description="List configured global MCP servers and current connection health.",
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
)
def list_mcp_servers() -> str:
    from data_agent.agent.loop import get_mcp_manager

    config = _load_config()
    configured = [server.model_dump(exclude_none=True) for server in config.servers]
    mcp_mgr = get_mcp_manager()
    health = [] if mcp_mgr is None else mcp_mgr.health_check()
    return json.dumps({"servers": configured, "health": health}, ensure_ascii=False, indent=2)


@registry.register(
    name="add_mcp_server",
    description="Add or replace a global MCP server configuration.",
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "transport": {"type": "string", "enum": ["stdio", "sse", "streamable-http"]},
            "command": {"type": "string", "default": ""},
            "args": {
                "type": "array",
                "items": {"type": "string"},
                "default": None,
                "nullable": True,
            },
            "url": {"type": "string", "default": ""},
            "enabled": {"type": "boolean", "default": True},
        },
        "required": ["name", "transport"],
        "additionalProperties": False,
    },
)
def add_mcp_server(
    name: str,
    transport: str,
    command: str = "",
    args: list[str] | None = None,
    url: str = "",
    enabled: bool = True,
) -> str:
    config = _load_config()
    server = MCPServerConfig(
        name=name,
        transport=transport,
        command=command or None,
        args=args or None,
        url=url or None,
        enabled=enabled,
    )
    config.servers = [s for s in config.servers if s.name != name] + [server]
    _save_config(config)
    return f"MCP server '{name}' saved globally."


@registry.register(
    name="enable_mcp_server",
    description="Enable a global MCP server configuration.",
    parameters={
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
        "additionalProperties": False,
    },
)
def enable_mcp_server(name: str) -> str:
    return _set_mcp_server_enabled(name, True)


@registry.register(
    name="disable_mcp_server",
    description="Disable a global MCP server configuration.",
    parameters={
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
        "additionalProperties": False,
    },
)
def disable_mcp_server(name: str) -> str:
    return _set_mcp_server_enabled(name, False)


def _set_mcp_server_enabled(name: str, enabled: bool) -> str:
    config = _load_config()
    for server in config.servers:
        if server.name == name:
            server.enabled = enabled
            _save_config(config)
            return f"MCP server '{name}' {'enabled' if enabled else 'disabled'}."
    return f"MCP server '{name}' not found."


@registry.register(
    name="delete_mcp_server",
    description="Delete a global MCP server configuration.",
    parameters={
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
        "additionalProperties": False,
    },
)
def delete_mcp_server(name: str) -> str:
    config = _load_config()
    original_count = len(config.servers)
    config.servers = [server for server in config.servers if server.name != name]
    if len(config.servers) == original_count:
        return f"MCP server '{name}' not found."
    _save_config(config)
    return f"MCP server '{name}' deleted."
