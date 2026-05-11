import json

import pandas as pd

from data_agent.agent.analysis_state import load_analysis_state
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
        registry.activate_groups({"report"})
        assert "report" in ctx_a.active_tool_groups

    with use_agent_context(ctx_b):
        registry.reset_groups()
        assert "report" not in ctx_b.active_tool_groups
        assert ctx_b.active_tool_groups == {"core"}


def test_turn_intent_planner_core_cases():
    no_data = ""
    loaded = "- main: 10 rows x 3 cols, columns: date, revenue, channel"

    need_data = plan_turn_intent(
        "I want to evaluate whether a savings card should keep operating. What data do I need?",
        no_data,
    )
    assert need_data.intent_type == "data_requirement"

    operation = plan_turn_intent("filter revenue", loaded)
    assert operation.intent_type == "operation"

    from data_agent.agent.intent import _REPORT_KEYWORDS
    report = plan_turn_intent(_REPORT_KEYWORDS[0], loaded)
    assert report.intent_type == "report"

    vague_loaded = plan_turn_intent("review dataset structure and suggest useful analysis paths", loaded)
    assert vague_loaded.intent_type in ("analysis_guidance", "direct_analysis")
    assert vague_loaded.recommended_action in ("propose_methods", "run_analysis")


def test_session_project_name_is_canonical_and_object_compatible(tmp_path):
    from data_agent import config
    from data_agent.config import AgentConfig
    from data_agent.session.history import load_session, list_sessions, save_session

    old_cfg = config._config
    config._config = AgentConfig(PROJECT_DIR=tmp_path / "project", SESSIONS_DIR=tmp_path / "sessions")
    try:
        sid = save_session(
            [{"role": "user", "content": "hello"}],
            "project_session",
            extra_meta={"project_name": "savings_card"},
        )
        loaded = load_session(sid)
        assert loaded["project_name"] == "savings_card"
        assert loaded["object_name"] == "savings_card"

        sessions = list_sessions(project_name="savings_card")
        assert len(sessions) == 1
        assert sessions[0]["project_name"] == "savings_card"
    finally:
        config._config = old_cfg


def test_unbound_session_state_and_artifacts_use_global_sessions_dir(tmp_path):
    from data_agent import config
    from data_agent.config import AgentConfig
    from data_agent.session.history import load_session, save_session
    from data_agent.tools.analysis_flow import record_data_requirement

    old_cfg = config._config
    config._config = AgentConfig(PROJECT_DIR=tmp_path / "project", SESSIONS_DIR=tmp_path / "sessions")
    ctx = AgentContext(session_id="unbound_session", project_name=None, workspace=Workspace())
    try:
        sid = save_session([{"role": "user", "content": "hello"}], "unbound_session")
        loaded = load_session(sid)
        assert loaded["project_name"] is None
        assert loaded["object_name"] is None

        with use_agent_context(ctx):
            requirement = {
                "goal": "understand available data",
                "must_have_data": ["dataset schema"],
                "recommended_data": ["business definitions"],
                "optional_data": ["benchmarks"],
                "missing_limitations": ["cannot make strong conclusions without real metrics"],
                "minimum_viable_analysis": "profile the loaded datasets",
            }
            result = json.loads(record_data_requirement(json.dumps(requirement)))

        assert result["saved"].startswith("sessions/unbound_session/analysis_flow/")
        assert (tmp_path / "sessions" / "unbound_session" / "analysis_flow").is_dir()
        assert not (tmp_path / "project" / "sessions" / "unbound_session").exists()
    finally:
        config._config = old_cfg


def test_project_binding_does_not_auto_promote_session_knowledge(tmp_path):
    from data_agent import config
    from data_agent.config import AgentConfig
    from data_agent.object_manager import ObjectManager
    from data_agent.session.history import bind_session_to_project, load_session, save_session, session_knowledge_dir

    old_cfg = config._config
    config._config = AgentConfig(PROJECT_DIR=tmp_path / "project", SESSIONS_DIR=tmp_path / "sessions")
    try:
        manager = ObjectManager(objects_dir=config.get_config().objects_dir)
        manager.create_project("analysis_project")
        save_session([{"role": "user", "content": "hello"}], "bind_session")
        knowledge_dir = session_knowledge_dir("bind_session")
        (knowledge_dir / "project_rules.md").write_text("session only rule", encoding="utf-8")

        result = bind_session_to_project("bind_session", "analysis_project")

        assert result["success"] is True
        loaded = load_session("bind_session")
        assert loaded["project_name"] == "analysis_project"
        project_rules = config.get_config().objects_dir / "analysis_project" / "knowledge" / "project_rules.md"
        assert project_rules.read_text(encoding="utf-8") == ""
        assert "bind_session" in manager.get_project("analysis_project")["sessions"]
    finally:
        config._config = old_cfg


def test_registry_exposes_tool_capability_metadata():
    from data_agent.tools import analysis_flow as _analysis_flow
    from data_agent.tools import task_tools as _task_tools
    from data_agent.tools.registry import registry

    spec_cap = registry.capability_for("record_analysis_spec")
    assert spec_cap["capability_id"] == "artifact.analysis_spec"

    python_cap = registry.capability_for("run_python")
    assert python_cap["category"] == "fallback"

    funnel_tools = registry.tools_for_capability("analysis.funnel")
    assert "funnel_analysis" in funnel_tools or registry.capability_for("funnel_analysis")["capability_id"] == "analysis.funnel"


def test_analysis_state_records_requirement_and_spec(tmp_path):
    from data_agent import config
    from data_agent.config import AgentConfig
    from data_agent.session.task_manager import task_manager
    from data_agent.tools.analysis_flow import record_analysis_spec, record_data_requirement

    old_cfg = config._config
    old_task_dir = task_manager._dir
    old_next_id = task_manager._next_id_val
    config._config = AgentConfig(PROJECT_DIR=tmp_path / "project", SESSIONS_DIR=tmp_path / "sessions")
    task_manager._dir = tmp_path / "tasks"
    task_manager._next_id_val = 0

    ctx = AgentContext(session_id="analysis_state_test", project_name="savings_card", workspace=Workspace())
    try:
        with use_agent_context(ctx):
            requirement = {
                "goal": "evaluate savings card operations",
                "must_have_data": ["card_users", "orders", "costs"],
                "recommended_data": ["channel", "city"],
                "optional_data": ["survey"],
                "missing_limitations": ["without a comparable control group, causal claims are limited"],
                "minimum_viable_analysis": "compare before and after purchase",
            }
            requirement_result = json.loads(record_data_requirement(json.dumps(requirement)))
            assert requirement_result["type"] == "data_requirement"
            assert requirement_result["requirement_id"]

            spec = {
                "goal": "evaluate savings card operations",
                "question_type": "evaluation",
                "metrics": ["revenue", "retention"],
                "dimensions": ["channel"],
                "time_scope": "30 days before and after purchase",
                "required_data": ["orders"],
                "method_plan": [
                    {
                        "step": "check data quality",
                        "node_type": "data_check",
                        "required_capability": "data.profile",
                        "expected_output": "profile summary",
                        "evidence_requirements": ["missingness"],
                    },
                    {
                        "step": "compare revenue before and after purchase",
                        "node_type": "analysis",
                        "required_capability": "analysis.period_compare",
                        "expected_output": "period comparison",
                        "confirmation_policy": {"requires_confirmation": False},
                    },
                ],
                "limitations": ["non-randomized data"],
            }
            spec_result = json.loads(record_analysis_spec(json.dumps(spec)))
            assert spec_result["type"] == "analysis_spec"
            assert spec_result["analysis_spec_id"]
            assert spec_result["workflow"]["created"] == 2

        state = load_analysis_state("analysis_state_test", "savings_card")
        assert len(state.data_requirements) == 1
        assert state.analysis_spec is not None
        assert state.stage == "plan"
    finally:
        config._config = old_cfg
        task_manager._dir = old_task_dir
        task_manager._next_id_val = old_next_id


def test_task_workflow_fields_are_backward_compatible(tmp_path):
    from data_agent.session.task_manager import TaskManager

    tm = TaskManager(tasks_dir=tmp_path)
    old = tm.create("legacy task", "desc")
    loaded = tm.get(old["id"])
    assert loaded["workflow_id"] == ""

    updated = tm.update(
        old["id"],
        status="completed",
        workflow_id="wf_1",
        node_type="analysis",
        required_capability="analysis.period_compare",
        evidence_ids=["ev_1"],
        result_summary="done",
    )
    assert updated["workflow_id"] == "wf_1"
    assert updated["evidence_ids"] == ["ev_1"]
    assert updated["required_capability"] == "analysis.period_compare"
    assert "evidence=1" in tm.format_list()
    assert "capability=analysis.period_compare" in tm.format_list()
