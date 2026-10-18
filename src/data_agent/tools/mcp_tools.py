"""MCP runtime and configuration management tools."""

from __future__ import annotations

import json

from data_agent.config import get_config
from data_agent.mcp.config import MCPConfig, MCPServerConfig, load_mcp_config, save_mcp_config, mcp_config_state
from data_agent.tools.registry import registry, ToolResult


def _config_path():
    return get_config().global_mcp_config_path


def _load_config():
    return load_mcp_config(_config_path())


def _save_config(config) -> dict:
    return save_mcp_config(config, _config_path())


def _next_mcp_config(config, action, arguments):
    """The single existing add/replace, toggle and delete transition."""
    updated = config.model_copy(deep=True)
    name = arguments["name"]
    if action == "add_mcp_server":
        server = MCPServerConfig(name=name, transport=arguments["transport"],
            command=arguments.get("command") or None, args=arguments.get("args") or None,
            url=arguments.get("url") or None, enabled=arguments.get("enabled", True))
        updated.servers = [s for s in updated.servers if s.name != name] + [server]
    elif action == "delete_mcp_server":
        updated.servers = [s for s in updated.servers if s.name != name]
        if len(updated.servers) == len(config.servers):
            return None
    elif action in {"enable_mcp_server", "disable_mcp_server"}:
        server = next((s for s in updated.servers if s.name == name), None)
        if server is None:
            return None
        server.enabled = action == "enable_mcp_server"
    else:
        raise ValueError("Unknown MCP configuration operation")
    return updated


def _mutate_mcp_config(action, arguments):
    before = mcp_config_state(_config_path())
    config = _next_mcp_config(MCPConfig(**before["configuration"]), action, arguments)
    if config is None:
        failure = {"error": "MCP server not found: " + arguments["name"], "error_type": "mcp_server_not_found"}
        return ToolResult(summary=json.dumps(failure, ensure_ascii=False), data=failure)
    try:
        state = _save_config(config)
    except (OSError, ValueError, RuntimeError) as exc:
        try:
            preserved = mcp_config_state(_config_path()) == before
        except (OSError, ValueError, TypeError):
            preserved = False
        failure = {"error": "MCP配置保存失败：" + str(exc) + ("；旧配置已核保留。" if preserved else "；旧配置是否完整恢复尚无法核实。"),
                   "error_type": "mcp_config_write_failed"}
        return ToolResult(summary=json.dumps(failure, ensure_ascii=False), data=failure)
    verb = {"add_mcp_server": "saved globally", "enable_mcp_server": "enabled",
            "disable_mcp_server": "disabled", "delete_mcp_server": "deleted"}[action]
    return ToolResult(summary=f"MCP server '{arguments['name']}' {verb}.",
        data={"path": state["path"], "before": before, "state": state})


@registry.register(
    name="call_mcp_tool",
    description="Call a tool exposed by a connected MCP server.",
    parameters={
        "type": "object",
        "properties": {
            "server": {"type": "string", "description": "MCP server name"},
            "tool": {"type": "string", "description": "Tool name on the server"},
            "arguments": {"type": "string", "description": "JSON-formatted tool arguments"},
        },
        "required": ["server", "tool"],
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


def _mcp_runtime_snapshot():
    """Read existing local connection records; never start or probe a server."""
    from dataclasses import asdict
    from data_agent.agent.loop import get_mcp_manager
    from data_agent.mcp.client import MCPClientManager
    manager = get_mcp_manager()
    if manager is None:
        return {"manager_available": False}, {"availability": "unavailable", "connections": None}
    if not isinstance(manager, MCPClientManager):
        raise ValueError("MCP runtime snapshot requires the existing client manager")
    connections = [{"name": name, "configuration": conn.config.model_dump(exclude_none=True),
                    "session_identity": id(conn.session) if conn.session is not None else None,
                    "failure_count": conn._failure_count,
                    "tools_cache": [asdict(tool) for tool in conn.tools_cache]}
                   for name, conn in manager._connections.items()]
    raw = {"manager_available": True, "manager_identity": id(manager),
           "configuration": manager._config.model_dump(exclude_none=True), "connections": connections}
    health = {"availability": "available", "connections": manager.health_check()}
    return raw, health


def _mcp_catalog_snapshot(context=None):
    import os
    from data_agent.agent.context import get_current_context
    from data_agent.agent.publication.contracts import encode, digest
    if context is not None and get_current_context() is not context:
        raise ValueError("MCP catalogue requires the current session")
    configuration = mcp_config_state(_config_path())
    runtime, health = _mcp_runtime_snapshot()
    result = {"servers": configuration["configuration"]["servers"], "health": health}
    if configuration != mcp_config_state(_config_path()) or (runtime, health) != _mcp_runtime_snapshot():
        raise ValueError("MCP catalogue changed during read")
    binding = {"schema_version": "mcp_catalog_binding.v1",
               "session_id": context.session_id if context is not None else None,
               "permission_scope": "configured_global_mcp_catalog",
               "configuration": configuration,
               "runtime": {"process_id": os.getpid(), "manager_available": runtime["manager_available"],
                           "snapshot_sha256": digest(encode(runtime))},
               "snapshot_sha256": digest(encode(result))}
    return result, binding


def _capture_mcp_catalog_binding(context):
    try:
        return _mcp_catalog_snapshot(context)[1]
    except (OSError, ValueError, TypeError, RuntimeError):
        return None


def _verify_mcp_catalog_binding(context, receipt, result):
    from data_agent.agent.publication.contracts import validate_mcp_catalog_binding, encode
    binding = receipt.get("mcp_binding")
    validate_mcp_catalog_binding(binding, context.session_id)
    if receipt["tool_name"] != "list_mcp_servers" or receipt["arguments"] or receipt.get("data_identities") or receipt.get("dataset_refs"):
        raise ValueError("MCP catalogue invocation or source scope changed")
    actual, current = _mcp_catalog_snapshot(context)
    if current != binding or encode(result) != encode(actual):
        raise ValueError("MCP configuration or current-process connection records changed")
    return binding


@registry.register(
    name="list_mcp_servers",
    description="List global MCP configuration and separate current-process cached connection records. An unavailable manager means connection state is unknown; this does not connect, probe, or call a remote server.",
    output_contract={"version":"native_business_product.v1","adapter":"data_agent.agent.publication.native.resolve_native_claims","kinds":["table"]},
    parameters={"type": "object", "properties": {}},
)
def list_mcp_servers() -> str:
    from data_agent.agent.context import get_current_context
    return json.dumps(_mcp_catalog_snapshot(get_current_context())[0], ensure_ascii=False, indent=2)


@registry.register(
    name="add_mcp_server",
    capability={"capability_id":"system.add_mcp_server","category":"data_write"},
    output_contract={"version":"native_operation_effect.v1","adapter":"data_agent.agent.publication.native.resolve_operation_effect","kinds":["operation"]},
    description="Add or replace a global MCP server configuration.",
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "transport": {"type": "string", "enum": ["stdio", "sse", "streamable-http"]},
            "command": {"type": "string"},
            "args": {"type": ["array", "null"], "items": {"type": "string"}},
            "url": {"type": "string"},
            "enabled": {"type": "boolean"},
        },
        "required": ["name", "transport"],
    },
)
def add_mcp_server(
    name: str,
    transport: str,
    command: str = "",
    args: list[str] | None = None,
    url: str = "",
    enabled: bool = True,
) -> ToolResult:
    return _mutate_mcp_config("add_mcp_server", {"name": name, "transport": transport,
        "command": command, "args": args, "url": url, "enabled": enabled})


@registry.register(
    name="enable_mcp_server",
    capability={"capability_id":"system.enable_mcp_server","category":"data_write"},
    output_contract={"version":"native_operation_effect.v1","adapter":"data_agent.agent.publication.native.resolve_operation_effect","kinds":["operation"]},
    description="Enable a global MCP server configuration.",
    parameters={"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
)
def enable_mcp_server(name: str) -> ToolResult:
    return _set_mcp_server_enabled(name, True)


@registry.register(
    name="disable_mcp_server",
    capability={"capability_id":"system.disable_mcp_server","category":"data_write"},
    output_contract={"version":"native_operation_effect.v1","adapter":"data_agent.agent.publication.native.resolve_operation_effect","kinds":["operation"]},
    description="Disable a global MCP server configuration.",
    parameters={"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
)
def disable_mcp_server(name: str) -> ToolResult:
    return _set_mcp_server_enabled(name, False)


def _set_mcp_server_enabled(name: str, enabled: bool) -> ToolResult:
    return _mutate_mcp_config("enable_mcp_server" if enabled else "disable_mcp_server", {"name": name})


@registry.register(
    name="delete_mcp_server",
    capability={"capability_id":"system.delete_mcp_server","category":"data_write"},
    output_contract={"version":"native_operation_effect.v1","adapter":"data_agent.agent.publication.native.resolve_operation_effect","kinds":["operation"]},
    description="Delete a global MCP server configuration.",
    parameters={"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
)
def delete_mcp_server(name: str) -> ToolResult:
    return _mutate_mcp_config("delete_mcp_server", {"name": name})
