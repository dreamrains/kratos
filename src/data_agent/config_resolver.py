"""配置合并逻辑：全局 ~/.data-agent/ + 项目 project/ 的两级配置。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from data_agent.config import get_config


def resolve_skills_dirs() -> list[Path]:
    """返回 skill 目录列表 [全局, 项目]，项目级覆盖全局。"""
    cfg = get_config()
    return [cfg.global_skills_dir, cfg.skills_dir]


def resolve_mcp_config() -> Any:
    """合并全局和项目级 MCP 配置，项目级按 server name 覆盖全局。"""
    from data_agent.mcp.config import MCPConfig, load_mcp_config

    cfg = get_config()

    global_config = load_mcp_config(cfg.global_mcp_config_path)
    project_config = load_mcp_config(cfg.mcp_config_path)

    if not global_config.servers:
        return project_config
    if not project_config.servers:
        return global_config

    return merge_mcp_configs(global_config, project_config)


def merge_mcp_configs(global_config: Any, project_config: Any) -> Any:
    """合并两个 MCPConfig，project 按 server name 覆盖 global。"""
    from data_agent.mcp.config import MCPConfig

    global_servers = {s.name: s for s in global_config.servers}
    project_servers = {s.name: s for s in project_config.servers}

    # 项目级覆盖全局同名项，保留全局独有项
    merged = {**global_servers, **project_servers}
    return MCPConfig(servers=list(merged.values()))


def resolve_settings() -> dict[str, Any]:
    """合并全局和项目级用户设置。"""
    cfg = get_config()
    settings: dict[str, Any] = {}

    for path in (cfg.global_settings_path, cfg.project_resolved / "settings.yaml"):
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            settings.update(data)

    return settings
