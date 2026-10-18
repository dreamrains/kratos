"""Web API for global skills and MCP server management."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

capability_admin_bp = Blueprint("capability_admin", __name__)


def _skill_loader():
    from data_agent.agent.loop import get_global_skill_loader

    loader = get_global_skill_loader()
    loader.discover()
    return loader


@capability_admin_bp.get("/skills")
def list_skills():
    loader = _skill_loader()
    return jsonify(
        [
            {
                "name": skill.name,
                "description": skill.description,
                "enabled": skill.enabled,
                "scope": skill.scope,
            }
            for skill in loader.list_available()
        ]
    )


@capability_admin_bp.post("/skills")
def install_skill():
    data = request.get_json(silent=True) or {}
    source = (data.get("source") or "").strip()
    name = (data.get("name") or "").strip()
    if not source or not name:
        return jsonify({"error": "name and source are required"}), 400
    return jsonify({"message": _skill_loader().install(source, name)})


@capability_admin_bp.post("/skills/<path:name>/enable")
def enable_skill(name: str):
    return jsonify({"message": _skill_loader().set_enabled(name, True)})


@capability_admin_bp.post("/skills/<path:name>/disable")
def disable_skill(name: str):
    return jsonify({"message": _skill_loader().set_enabled(name, False)})


@capability_admin_bp.delete("/skills/<path:name>")
def delete_skill(name: str):
    return jsonify({"message": _skill_loader().uninstall(name)})


@capability_admin_bp.get("/mcp/servers")
def list_mcp_servers():
    from data_agent.tools.mcp_tools import _mcp_catalog_snapshot
    return jsonify(_mcp_catalog_snapshot()[0]["servers"])


def _mcp_operation_response(result):
    failure = getattr(result, "data", None) or {}
    if failure.get("error_type"):
        return jsonify(failure), 400
    return jsonify({"message": str(result)})


@capability_admin_bp.post("/mcp/servers")
def add_mcp_server():
    from data_agent.tools.mcp_tools import add_mcp_server as add_server

    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    transport = (data.get("transport") or "stdio").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400

    try:
        message = add_server(
            name=name,
            transport=transport,
            command=(data.get("command") or "").strip(),
            args=data.get("args") or None,
            url=(data.get("url") or "").strip(),
            enabled=bool(data.get("enabled", True)),
        )
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400
    return _mcp_operation_response(message)


@capability_admin_bp.post("/mcp/servers/<path:name>/enable")
def enable_mcp_server(name: str):
    from data_agent.tools.mcp_tools import enable_mcp_server as enable_server

    return _mcp_operation_response(enable_server(name))


@capability_admin_bp.post("/mcp/servers/<path:name>/disable")
def disable_mcp_server(name: str):
    from data_agent.tools.mcp_tools import disable_mcp_server as disable_server

    return _mcp_operation_response(disable_server(name))


@capability_admin_bp.delete("/mcp/servers/<path:name>")
def delete_mcp_server(name: str):
    from data_agent.tools.mcp_tools import delete_mcp_server as delete_server

    return _mcp_operation_response(delete_server(name))
