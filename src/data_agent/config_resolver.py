"""Resolve configuration locations.

Skills and MCP servers are user-level capabilities. Workspace-level paths are
kept on AgentConfig for migration and review only, but they are not part of the
active runtime resolution.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from data_agent.config import get_config


def resolve_skills_dirs() -> list[Path]:
    """Return the global skill directory used by the runtime."""
    cfg = get_config()
    return [cfg.global_skills_dir]


def resolve_mcp_config() -> Any:
    """Load the global MCP configuration used by the runtime."""
    from data_agent.mcp.config import load_mcp_config

    cfg = get_config()
    return load_mcp_config(cfg.global_mcp_config_path)


def merge_mcp_configs(global_config: Any, project_config: Any) -> Any:
    """Compatibility helper for legacy callers.

    The active runtime no longer merges workspace/project MCP configs. Keeping
    this helper avoids breaking old imports during the pre-release rename.
    """
    from data_agent.mcp.config import MCPConfig

    global_servers = {s.name: s for s in global_config.servers}
    project_servers = {s.name: s for s in project_config.servers}
    merged = {**global_servers, **project_servers}
    return MCPConfig(servers=list(merged.values()))


def resolve_settings() -> dict[str, Any]:
    """Merge user settings with optional workspace settings."""
    cfg = get_config()
    settings: dict[str, Any] = {}

    for path in (cfg.global_settings_path, cfg.project_resolved / "settings.yaml"):
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            settings.update(data)

    return settings
