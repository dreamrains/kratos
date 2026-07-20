import json

from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.context import AgentContext, use_agent_context
from data_agent.session.task_manager import TaskManager, task_manager
from data_agent.session.workspace import Workspace
from data_agent.tools.task_tools import task_create


def test_task_create_rejects_malformed_required_claim_keys_before_writing(tmp_path):
    old_task_dir = task_manager._dir
    old_next_id = task_manager._next_id_val
    task_manager._dir = tmp_path / "tasks"
    task_manager._next_id_val = 0

    try:
        result = json.loads(task_create(tasks=json.dumps([{
            "subject": "Analyze banner click rate",
            "analysis_plan_id": "plan_abc",
            "step_id": "step_banner",
            "evidence_requirements": ["metric"],
            "required_claim_keys": "click_rate",
        }])))

        assert result["error_type"] == "invalid_required_claim_keys"
        assert task_manager.list_all(include_stale=True) == []
    finally:
        task_manager._dir = old_task_dir
        task_manager._next_id_val = old_next_id


def test_completed_execution_plan_hides_superseded_legacy_duplicates(tmp_path):
    mgr = TaskManager(tasks_dir=tmp_path / "tasks")

    candidate_plan = mgr.create_plan(
        session_id="38465eb4172f",
        goal="Candidate retention plan",
        source="recommended_playbook",
        analysis_spec_id="candidate_spec",
        workflow_id="wf_candidate",
    )
    mgr.create(
        "build cohorts and calculate retention curve",
        session_id="38465eb4172f",
        plan_id=candidate_plan["id"],
        plan_version=candidate_plan["version"],
        workflow_id="wf_candidate",
        analysis_spec_id="candidate_spec",
        source="recommended_playbook",
    )

    spec_plan = mgr.create_plan(
        session_id="38465eb4172f",
        goal="Savings card impact analysis",
        source="analysis_spec",
        analysis_spec_id="spec_active",
        workflow_id="wf_active",
    )
    stale_spec_task = mgr.create(
        "Analysis step 1",
        description='{"task":"Prepare data and calculate baseline metrics"}',
        session_id="38465eb4172f",
        plan_id=spec_plan["id"],
        plan_version=spec_plan["version"],
        workflow_id="wf_active",
        analysis_spec_id="spec_active",
        source="analysis_spec",
    )
    execution_task = mgr.create(
        "Prepare data and calculate baseline metrics",
        session_id="38465eb4172f",
        plan_id=spec_plan["id"],
        plan_version=spec_plan["version"],
        workflow_id="wf_active",
        analysis_spec_id="spec_active",
        source="llm_plan",
    )
    mgr.update(stale_spec_task["id"], status="superseded")
    mgr.update(execution_task["id"], status="completed", result_summary="Evidence recorded")

    active = mgr.list_active_for_scope(session_id="38465eb4172f")

    assert [t["id"] for t in active] == [execution_task["id"]]
    assert active[0]["status"] == "completed"


def test_active_plan_reuse_skips_duplicate_subjects(tmp_path):
    mgr = TaskManager(tasks_dir=tmp_path / "tasks")
    other_plan = mgr.create_plan(
        session_id="s1",
        goal="Different scoped analysis",
        source="analysis_spec",
        analysis_spec_id="spec_2",
        workflow_id="wf_2",
    )
    mgr.create(
        "Prepare data and calculate baseline metrics",
        session_id="s1",
        plan_id=other_plan["id"],
        plan_version=other_plan["version"],
        workflow_id="wf_2",
        analysis_spec_id="spec_2",
    )

    plan = mgr.create_plan(
        session_id="s1",
        goal="Savings card impact analysis",
        source="analysis_spec",
        analysis_spec_id="spec_1",
        workflow_id="wf_1",
    )
    current_plan_task = mgr.create(
        "Prepare data and calculate baseline metrics",
        session_id="s1",
        plan_id=plan["id"],
        plan_version=plan["version"],
        workflow_id="wf_1",
        analysis_spec_id="spec_1",
    )

    duplicate = mgr.find_duplicate_task(
        session_id="s1",
        plan_id=plan["id"],
        subject="Prepare data and calculate baseline metrics",
        analysis_spec_id="spec_1",
    )

    assert duplicate is not None
    assert duplicate["id"] == current_plan_task["id"]
    assert duplicate["subject"] == "Prepare data and calculate baseline metrics"


def test_migrate_legacy_completed_plan_archives_pending_duplicates(tmp_path):
    mgr = TaskManager(tasks_dir=tmp_path / "tasks")
    mgr.create("build cohorts and calculate retention curve", session_id="s1", analysis_spec_id="candidate")
    mgr.create("Analysis step 1", session_id="s1", analysis_spec_id="spec_1")
    completed = mgr.create("Prepare data and calculate baseline metrics", session_id="s1", analysis_spec_id="spec_1")
    mgr.update(completed["id"], status="completed", result_summary="done")

    result = mgr.migrate_legacy_session_active_plan(session_id="s1")

    active = mgr.list_active_for_scope(session_id="s1")
    history = mgr.list_history_for_scope(session_id="s1")
    assert result["active_plan_id"]
    assert [t["id"] for t in active] == [completed["id"]]
    assert {t["status"] for t in history} == {"superseded"}


def test_llm_batch_plan_supersedes_analysis_plan_candidate_tasks(tmp_path):
    old_task_dir = task_manager._dir
    old_next_id = task_manager._next_id_val
    task_manager._dir = tmp_path / "tasks"
    task_manager._next_id_val = 0

    candidate_plan = task_manager.create_plan(
        session_id="s1",
        goal="Candidate retention plan",
        source="analysis_plan",
        analysis_spec_id="plan_1",
        workflow_id="wf_1",
    )
    candidate = task_manager.create(
        "build cohorts and calculate retention curve",
        session_id="s1",
        workflow_id="wf_1",
        analysis_spec_id="plan_1",
        analysis_plan_id="plan_1",
        plan_id=candidate_plan["id"],
        plan_version=candidate_plan["version"],
        plan_status="active",
        source="analysis_plan",
    )
    confirmation = task_manager.create(
        "Confirm analysis method and metric scope",
        session_id="s1",
        workflow_id="wf_1",
        analysis_spec_id="plan_1",
        analysis_plan_id="plan_1",
        plan_id=candidate_plan["id"],
        plan_version=candidate_plan["version"],
        plan_status="active",
        task_kind="confirmation",
        source="system_confirmation",
    )
    ctx = AgentContext(session_id="s1", workspace=Workspace())
    ctx.analysis_state = AnalysisSessionState(
        session_id="s1",
        analysis_plan={
            "id": "plan_1",
            "workflow_id": "wf_1",
            "goal": "Fit retention formula",
            "confirmation_policy": {"requires_confirmation": True},
        },
    )

    try:
        with use_agent_context(ctx):
            result = json.loads(task_create(tasks=json.dumps([
                {
                    "subject": "Explore retention columns",
                    "description": "Profile day retention columns and value ranges",
                    "source": "llm_plan",
                },
                {
                    "subject": "Fit retention curve",
                    "description": "Compare power, exponential, and logarithmic models",
                },
            ])))

        active = task_manager.list_active_for_scope(session_id="s1")

        assert result["created"] == 2
        assert result["plan_id"] != candidate_plan["id"]
        assert [t["subject"] for t in active] == [
            "Explore retention columns",
            "Fit retention curve",
        ]
        assert {t["source"] for t in active} == {"llm_plan"}
        assert task_manager.get(candidate["id"])["status"] == "superseded"
        assert task_manager.get(confirmation["id"])["status"] == "superseded"
    finally:
        task_manager._dir = old_task_dir
        task_manager._next_id_val = old_next_id
