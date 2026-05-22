"""Web API for global skills and MCP server management."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

capability_admin_bp = Blueprint("capability_admin", __name__)


def _skill_loader():
    from data_agent.config_resolver import resolve_skills_dirs
    from data_agent.skills.loader import SkillLoader

    loader = SkillLoader(resolve_skills_dirs())
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
    from data_agent.config import get_config
    from data_agent.mcp.config import load_mcp_config

    config = load_mcp_config(get_config().global_mcp_config_path)
    return jsonify([server.model_dump(exclude_none=True) for server in config.servers])


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
    return jsonify({"message": message})


@capability_admin_bp.post("/mcp/servers/<path:name>/enable")
def enable_mcp_server(name: str):
    from data_agent.tools.mcp_tools import enable_mcp_server as enable_server

    return jsonify({"message": enable_server(name)})


@capability_admin_bp.post("/mcp/servers/<path:name>/disable")
def disable_mcp_server(name: str):
    from data_agent.tools.mcp_tools import disable_mcp_server as disable_server

    return jsonify({"message": disable_server(name)})


@capability_admin_bp.delete("/mcp/servers/<path:name>")
def delete_mcp_server(name: str):
    from data_agent.tools.mcp_tools import delete_mcp_server as delete_server

    return jsonify({"message": delete_server(name)})
