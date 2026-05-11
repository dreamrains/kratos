import pandas as pd

from data_agent.agent.context import AgentContext, use_agent_context
from data_agent.agent.intent import plan_turn_intent
from data_agent.session.workspace import Workspace, workspace
from data_agent.tools.registry import registry


def test_workspace_is_isolated_by_agent_context():
    ctx_a = AgentContext(session_id="ctx_a", workspace=Workspace())
    ctx_b = AgentContext(session_id="ctx_b", workspace=Workspace())

    with use_agent_context(ctx_a):
        workspace.add("a_only", pd.DataFrame({"a": [1]}))
        assert "a_only" in workspace.list_datasets()

    with use_agent_context(ctx_b):
        workspace.add("b_only", pd.DataFrame({"b": [2]}))
        datasets = workspace.list_datasets()
        assert "b_only" in datasets
        assert "a_only" not in datasets

    with use_agent_context(ctx_a):
        datasets = workspace.list_datasets()
        assert "a_only" in datasets
        assert "b_only" not in datasets


def test_tool_groups_are_isolated_by_agent_context():
    ctx_a = AgentContext(session_id="tools_a", workspace=Workspace())
    ctx_b = AgentContext(session_id="tools_b", workspace=Workspace())

    with use_agent_context(ctx_a):
        registry.reset_groups()
        registry.activate_groups_for_text("请出完整报告")
        names_a = {d["name"] for d in registry.active_definitions()}
        assert "generate_report" in names_a

    with use_agent_context(ctx_b):
        registry.reset_groups()
        names_b = {d["name"] for d in registry.active_definitions()}
        assert "generate_report" not in names_b
        assert "load_data" in names_b


def test_turn_intent_planner_core_cases():
    no_data = ""
    loaded = "- main: 10 rows x 3 cols, columns: 日期, 收入, 渠道"

    assert plan_turn_intent("我想分析省钱卡是否值得长期运营，需要哪些数据", no_data).intent_type == "data_requirement"
    assert plan_turn_intent("按月汇总收入", loaded).intent_type == "operation"
    assert plan_turn_intent("出完整报告", loaded).intent_type == "report"

    vague_loaded = plan_turn_intent("帮我看看这份数据", loaded)
    assert vague_loaded.intent_type in ("analysis_guidance", "direct_analysis")
    assert vague_loaded.recommended_action in ("propose_methods", "run_analysis")


def test_session_project_name_is_canonical_and_object_compatible(tmp_path, monkeypatch):
    from data_agent import config
    from data_agent.config import AgentConfig
    from data_agent.session.history import load_session, list_sessions, save_session

    old_cfg = config._config
    config._config = AgentConfig(PROJECT_DIR=tmp_path / "project", SESSIONS_DIR=tmp_path / "sessions")
    try:
        sid = save_session(
            [{"role": "user", "content": "hello"}],
            "project_session",
            extra_meta={"project_name": "省钱卡项目"},
        )
        loaded = load_session(sid)
        assert loaded["project_name"] == "省钱卡项目"
        assert loaded["object_name"] == "省钱卡项目"

        sessions = list_sessions(project_name="省钱卡项目")
        assert len(sessions) == 1
        assert sessions[0]["project_name"] == "省钱卡项目"
    finally:
        config._config = old_cfg
