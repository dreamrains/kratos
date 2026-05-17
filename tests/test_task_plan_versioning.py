from data_agent.session.task_manager import TaskManager


def test_completed_execution_plan_hides_legacy_pending_duplicates(tmp_path):
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
    plan = mgr.create_plan(
        session_id="s1",
        goal="Savings card impact analysis",
        source="analysis_spec",
        analysis_spec_id="spec_1",
        workflow_id="wf_1",
    )
    mgr.create(
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
    assert duplicate["subject"] == "Prepare data and calculate baseline metrics"
