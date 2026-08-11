from __future__ import annotations

from data_agent.agent.analysis_flow_controller import AnalysisFlowController
from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.intent import TurnIntent
from data_agent.agent.execution_control import ToolExecutionBudget, TurnExecutionState
from data_agent.agent.execution_scope import current_execution_scope
from data_agent.agent.confirmation.runtime import (
    build_action_registry,
    build_required_question_candidate,
)
from data_agent.agent.confirmation.service import ConfirmationService
from data_agent.config import get_config
from data_agent.session.task_manager import TaskManager


def _intent() -> TurnIntent:
    return TurnIntent(
        intent_type="directed_analysis",
        clarity="clear",
        data_state="data_loaded",
        analysis_stage="plan",
        recommended_action="run_analysis",
        execution_readiness="ready",
    )


def _state_with_method_confirmation() -> AnalysisSessionState:
    state = AnalysisSessionState(
        session_id="confirmation_transition",
        project_name="project-a",
        data_state="data_loaded",
    )
    state.dataset_contracts = [{
        "id": "contract_orders",
        "dataset": "orders",
        "quality": {"status": "ready"},
    }]
    state.set_analysis_plan({
        "contract_version": "analysis_plan.v1",
        "id": "analysis_plan_forecast",
        "goal": "forecast next month revenue",
        "review_status": "display_only",
        "playbook_id": "forecast_decision_simulation",
        "confirmation_policy": {
            "requires_confirmation": True,
            "confirmation_type": "method_confirmation",
        },
        "method_plan": [{
            "step_id": "step_forecast",
            "goal": "forecast next month revenue",
            "node_type": "analysis",
            "required_capability": "analysis.forecast",
            "expected_output": "forecast with bounded uncertainty",
            "evidence_requirements": [
                "training_window",
                "forecast_window",
                "validation",
            ],
            "required_claim_keys": ["forecast_summary"],
        }],
    })
    state.add_confirmation({
        "id": "confirm_forecast",
        "confirmation_type": "method_confirmation",
        "question": "Confirm the forecast method?",
        "options": [
            {"label": "Continue", "value": "confirm_method"},
            {"label": "Describe only", "value": "descriptive_only"},
        ],
        "related_plan_id": "analysis_plan_forecast",
        "state_updates": {
            "method_confirmation": {
                "playbook_id": "forecast_decision_simulation",
                "analysis_plan_id": "analysis_plan_forecast",
                "allowed_actions": ["confirm_method", "descriptive_only"],
            },
        },
    })
    return state


def _install_manager(monkeypatch, tmp_path) -> TaskManager:
    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    monkeypatch.setattr(
        "data_agent.agent.analysis_flow_controller.task_manager",
        manager,
    )
    return manager


def test_confirmation_resolution_closes_gate_and_atomically_activates_first_task(
    tmp_path,
    monkeypatch,
):
    manager = _install_manager(monkeypatch, tmp_path)
    state = _state_with_method_confirmation()
    controller = AnalysisFlowController(state.session_id, state.project_name)
    confirmation_task = controller.ensure_confirmation_task(state)

    transition = controller.resolve_confirmation_and_activate(
        state,
        confirmation_id="confirm_forecast",
        answer="confirm_method",
        intent=_intent(),
    )

    assert transition["ok"] is True
    assert manager.get(confirmation_task["id"])["status"] == "completed"
    assert state.analysis_plan["review_status"] == "executable"
    plan_tasks = [
        task
        for task in manager.list_active_for_scope(
            session_id=state.session_id,
            project_name=state.project_name,
        )
        if task.get("task_kind") == "plan_task"
    ]
    assert len(plan_tasks) == 1
    assert plan_tasks[0]["status"] == "in_progress"
    assert transition["active_task_id"] == plan_tasks[0]["id"]
    assert not any(item["status"] == "pending" for item in state.pending_confirmations)


def test_descriptive_only_resolution_projects_recompiled_safe_plan(
    tmp_path,
    monkeypatch,
):
    manager = _install_manager(monkeypatch, tmp_path)
    state = _state_with_method_confirmation()
    controller = AnalysisFlowController(state.session_id, state.project_name)
    confirmation_task = controller.ensure_confirmation_task(state)

    transition = controller.resolve_confirmation_and_activate(
        state,
        confirmation_id="confirm_forecast",
        answer="descriptive_only",
        intent=_intent(),
    )

    assert transition["ok"] is True
    assert manager.get(confirmation_task["id"])["status"] == "completed"
    assert state.analysis_plan["method_confirmation"]["status"] == "descriptive_only"
    assert state.analysis_plan["review_status"] == "executable"
    assert not any(
        step.get("required_capability") in {"analysis.forecast", "analysis.causal"}
        for step in state.analysis_plan["method_plan"]
    )
    active = [
        task
        for task in manager.list_active_for_scope(
            session_id=state.session_id,
            project_name=state.project_name,
        )
        if task.get("status") == "in_progress"
    ]
    assert len(active) == 1
    assert active[0]["analysis_plan_id"] == state.analysis_plan["id"]


def test_confirmation_transition_is_idempotent(tmp_path, monkeypatch):
    manager = _install_manager(monkeypatch, tmp_path)
    state = _state_with_method_confirmation()
    controller = AnalysisFlowController(state.session_id, state.project_name)
    controller.ensure_confirmation_task(state)

    first = controller.resolve_confirmation_and_activate(
        state,
        confirmation_id="confirm_forecast",
        answer="confirm_method",
        intent=_intent(),
    )
    second = controller.resolve_confirmation_and_activate(
        state,
        confirmation_id="confirm_forecast",
        answer="confirm_method",
        intent=_intent(),
    )

    plan_tasks = [
        task
        for task in manager.list_active_for_scope(
            session_id=state.session_id,
            project_name=state.project_name,
        )
        if task.get("task_kind") == "plan_task"
    ]
    assert first["active_task_id"] == second["active_task_id"]
    assert len(plan_tasks) == 1
    assert plan_tasks[0]["status"] == "in_progress"


def test_failed_execution_transition_leaves_confirmation_gate_open(
    tmp_path,
    monkeypatch,
):
    manager = _install_manager(monkeypatch, tmp_path)
    state = _state_with_method_confirmation()
    state.dataset_contracts = []
    controller = AnalysisFlowController(state.session_id, state.project_name)
    confirmation_task = controller.ensure_confirmation_task(state)

    transition = controller.resolve_confirmation_and_activate(
        state,
        confirmation_id="confirm_forecast",
        answer="confirm_method",
        intent=_intent(),
    )

    assert transition["ok"] is False
    assert transition["error_type"] == "analysis_dataset_identity_missing"
    assert manager.get(confirmation_task["id"])["status"] == "pending"
    assert state.pending_confirmations[0]["status"] == "pending"


def test_runtime_confirmation_service_commits_the_execution_transition(
    tmp_path,
    monkeypatch,
):
    manager = _install_manager(monkeypatch, tmp_path)
    config = get_config()
    monkeypatch.setattr(config, "sessions_dir", tmp_path / "sessions")
    state = _state_with_method_confirmation()
    state.save()
    controller = AnalysisFlowController(state.session_id, state.project_name)
    confirmation_task = controller.ensure_confirmation_task(state)
    pending = state.pending_confirmations[0]
    candidate = build_required_question_candidate(
        session_id=state.session_id,
        turn_id="method_confirmation",
        message_version=1,
        request={
            "question": pending["question"],
            "options": pending["options"],
            "confirmation_type": pending["confirmation_type"],
            "blocking_reason": "method gate",
            "state_updates": pending["state_updates"],
            "related_spec_id": pending["related_plan_id"],
        },
        source="pending_confirmation",
        operation="method_confirmation",
    )
    service = ConfirmationService(
        config.sessions_resolved,
        action_registry=build_action_registry(),
    )
    request = service.request(candidate)
    suspended = service.checkpoint(state.session_id)

    resolved = service.respond(
        state.session_id,
        request.record.confirmation_id,
        "confirm_method",
        suspended.version,
        "confirm-method-once",
    )

    reloaded = AnalysisFlowController(
        state.session_id,
        state.project_name,
    ).load_state()
    assert resolved.status.value == "resolved"
    assert manager.get(confirmation_task["id"])["status"] == "completed"
    assert reloaded.analysis_plan["review_status"] == "executable"
    scope = manager.get_analysis_run_scope(state.session_id, state.project_name)
    assert scope is not None
    assert scope["task_id"] > 0


def test_agent_loop_reloads_resolved_state_and_refreshes_execution_scope(
    tmp_path,
    monkeypatch,
):
    import data_agent.agent.loop as loop_module
    import data_agent.session.task_manager as task_manager_module

    manager = _install_manager(monkeypatch, tmp_path)
    monkeypatch.setattr(task_manager_module, "task_manager", manager)
    config = get_config()
    monkeypatch.setattr(config, "sessions_dir", tmp_path / "sessions")
    monkeypatch.setattr(config, "skill_auto_discover", False)
    monkeypatch.setattr(loop_module, "get_config", lambda: config)
    state = _state_with_method_confirmation()
    state.save()
    loop = loop_module.AgentLoop(
        client=None,
        session_id=state.session_id,
        project_name=state.project_name,
    )
    loop.context.analysis_state = state
    loop.context.turn_intent = _intent()
    loop._last_turn_intent = _intent()
    loop._turn_existing_pending_ids = set()
    loop._turn_question_need = None
    controller = AnalysisFlowController(state.session_id, state.project_name)
    controller.ensure_confirmation_task(state)
    suspension = loop._maybe_auto_suspend_for_required_question()

    loop._resolve_runtime_confirmation(
        suspension,
        "confirm_method",
        expected_version=suspension.version,
        idempotency_key="loop-confirm-method-once",
    )

    assert loop.context.analysis_state.analysis_plan["review_status"] == "executable"
    assert not any(
        item["status"] == "pending"
        for item in loop.context.analysis_state.pending_confirmations
    )
    assert loop.context.workspace_scope.active is True
    assert loop.context.workspace_scope.task_id > 0


def test_zero_current_legacy_transition_activates_ready_task_without_error(tmp_path):
    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    plan = manager.create_plan(
        session_id="session-a",
        project_name="project-a",
        goal="analyze orders",
        source="analysis_plan",
    )
    task = manager.create(
        "Analyze orders",
        session_id="session-a",
        project_name="project-a",
        plan_id=plan["id"],
        plan_version=plan["version"],
        task_kind="plan_task",
        analysis_plan_id="analysis_plan_orders",
        step_id="step_orders",
        dataset_inputs=["orders"],
        dataset_contract_ids=["contract_orders"],
        combination_mode="single",
    )

    scope = current_execution_scope(manager, "session-a", "project-a")

    assert scope.error_type == ""
    assert scope.active is True
    assert scope.task_id == task["id"]
    assert manager.get(task["id"])["status"] == "in_progress"


def test_scope_recovery_does_not_consume_analysis_error_budget(tmp_path):
    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    plan = manager.create_plan(
        session_id="session-a",
        project_name="project-a",
        goal="analyze orders",
        source="analysis_plan",
    )
    manager.create(
        "Analyze orders",
        session_id="session-a",
        project_name="project-a",
        plan_id=plan["id"],
        plan_version=plan["version"],
        task_kind="plan_task",
        analysis_plan_id="analysis_plan_orders",
        step_id="step_orders",
        dataset_inputs=["orders"],
        combination_mode="single",
    )
    turn_state = TurnExecutionState(ToolExecutionBudget(max_consecutive_errors=3))
    for index in range(3):
        turn_state.record_tool_error(
            "describe_dataset",
            {"attempt": index},
            '{"error_type":"stage3c0b_current_task_missing"}',
        )

    scope = current_execution_scope(manager, "session-a", "project-a")

    assert scope.error_type == ""
    assert scope.active is True
    assert turn_state.consecutive_errors == 3
    assert turn_state.consecutive_error_recovery_attempted is False
