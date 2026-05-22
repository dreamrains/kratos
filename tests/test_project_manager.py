from data_agent.config import AgentConfig
import data_agent.config as config
from data_agent.project_manager import ProjectManager


def test_project_manager_uses_projects_dir(tmp_path):
    config._config = AgentConfig(WORKSPACE_DIR=tmp_path / "workspace", _env_file=None)
    mgr = ProjectManager()
    created = mgr.create("revenue", description="Revenue analysis")
    assert created["name"] == "revenue"
    assert (tmp_path / "workspace" / "projects" / "revenue" / "meta.yaml").exists()


def test_project_bind_unbind_session(tmp_path):
    config._config = AgentConfig(
        WORKSPACE_DIR=tmp_path / "workspace",
        SESSIONS_DIR=tmp_path / "sessions",
        _env_file=None,
    )
    mgr = ProjectManager()
    mgr.create("revenue")
    mgr.bind_session("revenue", "s1")
    assert "s1" in mgr.get("revenue")["sessions"]
    mgr.unbind_session("revenue", "s1")
    assert "s1" not in mgr.get("revenue")["sessions"]
