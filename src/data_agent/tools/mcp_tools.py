"""MCP 相关工具：call_mcp_tool, list_mcp_servers。"""

from __future__ import annotations

import json

from data_agent.tools.registry import registry


@registry.register(
    name="call_mcp_tool",
    description="直接调用 MCP 服务器上的工具。用于调用已连接 MCP 服务器提供的工具能力。",
    parameters={
        "type": "object",
        "properties": {
            "server": {"type": "string", "description": "MCP 服务器名称"},
            "tool": {"type": "string", "description": "服务器上的工具名称"},
            "arguments": {"type": "string", "description": "JSON 格式的工具参数，如 '{\"path\": \"/tmp/file.txt\"}'"},
        },
        "required": ["server", "tool"],
    },
)
def call_mcp_tool(server: str, tool: str, arguments: str = "{}") -> str:
    """直接调用 MCP 工具（匹配 PRD 中 call_mcp_tool(server, tool, args) 要求）。"""
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
    description="列出所有已连接的 MCP 服务器及其提供的工具。",
    parameters={"type": "object", "properties": {}},
)
def list_mcp_servers() -> str:
    """列出所有已连接的 MCP 服务器。"""
    from data_agent.agent.loop import get_mcp_manager

    mcp_mgr = get_mcp_manager()
    if mcp_mgr is None:
        return json.dumps({"servers": [], "message": "MCP not configured"}, ensure_ascii=False)

    status = mcp_mgr.health_check()
    return json.dumps({"servers": status}, ensure_ascii=False, indent=2)
