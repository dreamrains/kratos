import json
import sys

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
    assert operation.intent_type == "data_operation"

    from data_agent.agent.intent import _REPORT_KEYWORDS
    report = plan_turn_intent(_REPORT_KEYWORDS[0], loaded)
    assert report.intent_type == "comprehensive_report"

    vague_loaded = plan_turn_intent("review dataset structure and suggest useful analysis paths", loaded)
    assert vague_loaded.intent_type in ("intent_negotiation", "directed_analysis", "analysis_consultation")
    assert vague_loaded.recommended_action in ("guide_analysis", "run_analysis", "answer_directly")


def test_build_system_prompt_escapes_literal_json_examples():
    from data_agent.agent.prompts import build_system_prompt

    loaded = "- main: 10 rows x 3 cols, columns: date, revenue, channel"
    cases = [
        "filter revenue",
        "analyze revenue trend",
        "generate a complete analysis report",
    ]

    for user_input in cases:
        prompt = build_system_prompt(
            tool_list="load_data, create_chart",
            session_context=loaded,
            user_input=user_input,
        )
        assert "Plotly JSON" in prompt


def test_report_prompt_uses_conversation_synthesis_instead_of_report_tools():
    from data_agent.agent.prompts import build_system_prompt

    loaded = "- main: 10 rows x 3 cols, columns: date, revenue, channel"
    prompt = build_system_prompt(
        tool_list="create_chart, record_evidence_record, generate_analysis_brief, generate_formal_report",
        session_context=loaded,
        user_input="generate a complete analysis report",
    )

    assert "record_evidence_record" in prompt
    assert "generate_formal_report" not in prompt
    assert "generate_analysis_brief" not in prompt


def test_complete_analysis_prompt_filters_deprecated_report_tools():
    from data_agent.agent.prompts import build_system_prompt

    prompt = build_system_prompt(
        tool_list="record_evidence_record, create_chart, generate_analysis_brief, generate_formal_report",
        session_context="- main: 10 rows x 3 cols, columns: user_id, revenue, date",
        user_input="请完整分析功能效果，并告诉我还有哪些维度可以分析",
    )

    assert "record_evidence_record" in prompt
    assert "generate_formal_report" not in prompt
    assert "generate_analysis_brief" not in prompt


def test_data_command_parses_multiple_quoted_paths_and_context():
    from data_agent.agent.repl import _format_data_command_prompt, _parse_data_command_args

    args = (
        '"C:\\Users\\duguy\\Desktop\\card_flow.xlsx" '
        '"C:\\Users\\duguy\\Desktop\\card_orders.xlsx"\n'
        "# 概述\n"
        "分析省钱卡收益"
    )

    parsed = _parse_data_command_args(args)

    assert parsed.paths == [
        "C:\\Users\\duguy\\Desktop\\card_flow.xlsx",
        "C:\\Users\\duguy\\Desktop\\card_orders.xlsx",
    ]
    assert parsed.context == "# 概述\n分析省钱卡收益"
    assert parsed.data_file == "C:\\Users\\duguy\\Desktop\\card_flow.xlsx; C:\\Users\\duguy\\Desktop\\card_orders.xlsx"

    prompt = _format_data_command_prompt(parsed)
    assert "card_flow.xlsx" in prompt
    assert "card_orders.xlsx" in prompt
    assert "分析省钱卡收益" in prompt


def test_load_data_does_not_classify_user_desktop_as_system_path():
    if sys.platform != "win32":
        return

    from data_agent.tools.data_io import _resolve_source

    try:
        _resolve_source("C:\\Users\\duguy\\Desktop\\missing_data_file.xlsx")
    except FileNotFoundError:
        pass
    except ValueError as exc:
        raise AssertionError("user Desktop files should not be treated as system paths") from exc


def test_session_project_name_is_canonical(tmp_path):
    from data_agent import config
    from data_agent.config import AgentConfig
    from data_agent.session.history import load_session, list_sessions, save_session

    old_cfg = config._config
    config._config = AgentConfig(WORKSPACE_DIR=tmp_path / "workspace", SESSIONS_DIR=tmp_path / "sessions")
    try:
        sid = save_session(
            [{"role": "user", "content": "hello"}],
            "project_session",
            extra_meta={"project_name": "savings_card"},
        )
        loaded = load_session(sid)
        assert loaded["project_name"] == "savings_card"
        assert "object_name" not in loaded

        sessions = list_sessions(project_name="savings_card")
        assert len(sessions) == 1
        assert sessions[0]["project_name"] == "savings_card"
        assert "object_name" not in sessions[0]
    finally:
        config._config = old_cfg


def test_session_meta_uses_project_name_only(tmp_path):
    from data_agent import config
    from data_agent.config import AgentConfig
    from data_agent.session.history import load_session, save_session

    old_cfg = config._config
    config._config = AgentConfig(WORKSPACE_DIR=tmp_path / "workspace", SESSIONS_DIR=tmp_path / "sessions")
    try:
        save_session([{"role": "user", "content": "hello"}], "s1", extra_meta={"project_name": "revenue"})
        loaded = load_session("s1")
        assert loaded["project_name"] == "revenue"
        assert "object_name" not in loaded
    finally:
        config._config = old_cfg


def test_unbound_session_state_and_artifacts_use_global_sessions_dir(tmp_path):
    from data_agent import config
    from data_agent.config import AgentConfig
    from data_agent.session.history import load_session, save_session
    from data_agent.tools.analysis_flow import record_data_requirement

    old_cfg = config._config
    config._config = AgentConfig(WORKSPACE_DIR=tmp_path / "workspace", SESSIONS_DIR=tmp_path / "sessions")
    ctx = AgentContext(session_id="unbound_session", project_name=None, workspace=Workspace())
    try:
        sid = save_session([{"role": "user", "content": "hello"}], "unbound_session")
        loaded = load_session(sid)
        assert loaded["project_name"] is None
        assert "object_name" not in loaded

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
        assert not (tmp_path / "workspace" / "sessions" / "unbound_session").exists()
    finally:
        config._config = old_cfg


def test_project_binding_does_not_auto_promote_session_knowledge(tmp_path):
    from data_agent import config
    from data_agent.config import AgentConfig
    from data_agent.project_manager import ProjectManager
    from data_agent.session.history import bind_session_to_project, load_session, save_session, session_knowledge_dir

    old_cfg = config._config
    config._config = AgentConfig(WORKSPACE_DIR=tmp_path / "workspace", SESSIONS_DIR=tmp_path / "sessions")
    try:
        manager = ProjectManager()
        manager.create("analysis_project")
        save_session([{"role": "user", "content": "hello"}], "bind_session")
        knowledge_dir = session_knowledge_dir("bind_session")
        (knowledge_dir / "project_rules.md").write_text("session only rule", encoding="utf-8")

        result = bind_session_to_project("bind_session", "analysis_project")

        assert result["success"] is True
        loaded = load_session("bind_session")
        assert loaded["project_name"] == "analysis_project"
        project_rules = config.get_config().projects_dir / "analysis_project" / "knowledge" / "project_rules.md"
        assert not project_rules.exists()
        assert "bind_session" in manager.get("analysis_project")["sessions"]
    finally:
        config._config = old_cfg


def test_system_prompt_does_not_load_project_knowledge(tmp_path, monkeypatch):
    import data_agent.agent.loop as loop_module
    from data_agent import config
    from data_agent.config import AgentConfig

    old_cfg = config._config
    config._config = AgentConfig(WORKSPACE_DIR=tmp_path / "workspace", SESSIONS_DIR=tmp_path / "sessions")
    monkeypatch.setattr(loop_module, "_skill_loader", None)

    calls = []

    class FakeRules:
        def get_rules_for_prompt(self, object_name=None, session_id=None):
            calls.append(("rules", object_name, session_id))
            return "rules"

    class FakeDomain:
        def get_for_prompt(self, object_name=None, session_id=None):
            calls.append(("domain", object_name, session_id))
            return "domain"

    class FakeExperience:
        def get_for_prompt(self, object_name=None, session_id=None):
            calls.append(("experience", object_name, session_id))
            return "experience"

    monkeypatch.setattr(
        "data_agent.tools.knowledge_tools.get_knowledge_instances",
        lambda: (FakeRules(), FakeDomain(), FakeExperience()),
    )

    try:
        agent = loop_module.AgentLoop(client=object(), session_id="s1", project_name="project_a")
        agent.messages.append({"role": "user", "content": "hello"})
        agent._build_system_prompt()
    finally:
        config._config = old_cfg

    assert calls
    assert all(object_name is None for _, object_name, _ in calls)
    assert all(session_id == "s1" for _, _, session_id in calls)


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


def test_analysis_state_records_requirement_but_legacy_spec_is_display_only(tmp_path):
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
            assert spec_result["workflow"] == {
                "created": 0,
                "task_ids": [],
                "display_only": True,
                "reason": "deprecated_analysis_spec_adapter_display_only",
            }

        state = load_analysis_state("analysis_state_test", "savings_card")
        assert len(state.data_requirements) == 1
        assert state.analysis_plan is None
        assert state.stage == "scope"
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
