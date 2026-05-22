import json
from pathlib import Path


def _reset_config(monkeypatch, tmp_path):
    import data_agent.config as config

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.setattr(config, "_config", None)


def test_skill_resolution_is_global_only(tmp_path, monkeypatch):
    _reset_config(monkeypatch, tmp_path)

    from data_agent.config import get_config
    from data_agent.config_resolver import resolve_skills_dirs
    from data_agent.skills.loader import SkillLoader

    cfg = get_config()
    (cfg.global_skills_dir / "global_skill").mkdir(parents=True)
    (cfg.global_skills_dir / "global_skill" / "SKILL.md").write_text(
        "---\nname: global_skill\ndescription: Global skill\n---\nUse global behavior.",
        encoding="utf-8",
    )
    (cfg.skills_dir / "workspace_skill").mkdir(parents=True)
    (cfg.skills_dir / "workspace_skill" / "SKILL.md").write_text(
        "---\nname: workspace_skill\ndescription: Workspace skill\n---\nUse workspace behavior.",
        encoding="utf-8",
    )

    assert resolve_skills_dirs() == [cfg.global_skills_dir]

    loader = SkillLoader(resolve_skills_dirs())
    loader.discover()
    assert loader.get("global_skill") is not None
    assert loader.get("workspace_skill") is None


def test_disabled_skill_is_not_loaded_or_injected(tmp_path, monkeypatch):
    _reset_config(monkeypatch, tmp_path)

    from data_agent.config import get_config
    from data_agent.config_resolver import resolve_skills_dirs
    from data_agent.skills.loader import SkillLoader

    cfg = get_config()
    skill_dir = cfg.global_skills_dir / "disabled_skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: disabled_skill\ndescription: Disabled\nenabled: false\n---\nSecret instructions.",
        encoding="utf-8",
    )

    loader = SkillLoader(resolve_skills_dirs())
    loader.discover()

    assert loader.get("disabled_skill").enabled is False
    assert "disabled" in loader.load("disabled_skill").lower()
    assert loader.get_prompt_injections() == ""


def test_mcp_resolution_is_global_only(tmp_path, monkeypatch):
    _reset_config(monkeypatch, tmp_path)

    from data_agent.config import get_config
    from data_agent.config_resolver import resolve_mcp_config

    cfg = get_config()
    cfg.global_mcp_config_path.write_text(
        "servers:\n"
        "  - name: global_server\n"
        "    transport: stdio\n"
        "    command: global-cmd\n",
        encoding="utf-8",
    )
    cfg.mcp_config_path.write_text(
        "servers:\n"
        "  - name: workspace_server\n"
        "    transport: stdio\n"
        "    command: workspace-cmd\n",
        encoding="utf-8",
    )

    resolved = resolve_mcp_config()
    assert [server.name for server in resolved.servers] == ["global_server"]


def test_mcp_management_tools_edit_global_config(tmp_path, monkeypatch):
    _reset_config(monkeypatch, tmp_path)

    import data_agent.tools.mcp_tools as mcp_tools
    from data_agent.config import get_config
    from data_agent.mcp.config import load_mcp_config

    cfg = get_config()
    assert "saved globally" in mcp_tools.add_mcp_server("fs", "stdio", command="npx")

    config = load_mcp_config(cfg.global_mcp_config_path)
    assert config.servers[0].name == "fs"
    assert config.servers[0].enabled is True

    mcp_tools.disable_mcp_server("fs")
    config = load_mcp_config(cfg.global_mcp_config_path)
    assert config.servers[0].enabled is False

    listed = json.loads(mcp_tools.list_mcp_servers())
    assert listed["servers"][0]["name"] == "fs"

    mcp_tools.delete_mcp_server("fs")
    config = load_mcp_config(cfg.global_mcp_config_path)
    assert config.servers == []


def test_web_capability_admin_uses_global_scope(tmp_path, monkeypatch):
    _reset_config(monkeypatch, tmp_path)

    from data_agent.config import get_config
    from data_agent.web.app import create_app

    cfg = get_config()
    skill_dir = cfg.global_skills_dir / "web_skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: web_skill\ndescription: Web Skill\n---\nUse web skill.",
        encoding="utf-8",
    )

    app = create_app()
    client = app.test_client()

    skills = client.get("/api/skills")
    assert skills.status_code == 200
    assert skills.get_json()[0]["name"] == "web_skill"

    disabled = client.post("/api/skills/web_skill/disable")
    assert disabled.status_code == 200
    assert "disabled" in disabled.get_json()["message"].lower()

    added = client.post(
        "/api/mcp/servers",
        json={"name": "web_mcp", "transport": "stdio", "command": "npx"},
    )
    assert added.status_code == 200

    servers = client.get("/api/mcp/servers")
    assert servers.status_code == 200
    assert servers.get_json()[0]["name"] == "web_mcp"
