from types import SimpleNamespace
from data_agent.agent.loop import AgentLoop
from data_agent.agent import trust_workflow_runtime as runtime
from data_agent.llm.client import Response, ToolCall


def _audit_blocked_no_evidence():
    return {
        "contract_version": "final_answer_audit.v1",
        "id": "audit_block",
        "status": "blocked",
        "public_text": "",
        "claims": [{"id": "claim_1", "text": "本月收入增长了 5%。", "claim_type": "numeric", "material": True}],
        "claim_checks": [{"claim_id": "claim_1", "status": "failed", "reason_codes": ["missing_evidence_identity"]}],
    }


def test_publication_is_non_destructive_even_when_config_says_strict(monkeypatch):
    """The loop must publish transparently regardless of assurance_publication_mode."""
    loop = AgentLoop(client=object(), session_id="m1_pub")
    loop._publication_mode = lambda: "strict"  # simulate a strict config
    loop._last_turn_intent = SimpleNamespace(intent_type="directed_analysis", execution_readiness="ready")
    state = SimpleNamespace(evidence_records=[{"id": "ev_1"}], verification_reports=[], turn_diagnostics=[])
    state.append_turn_diagnostic = state.turn_diagnostics.append
    loop.context.analysis_state = state
    monkeypatch.setattr(runtime, "audit_final_answer_draft", lambda *_a, **_k: {
        "contract_version": "final_answer_audit.v1", "id": "ref", "status": "blocked",
        "artifact_path": "f.json", "artifact_digest": "0" * 64})
    monkeypatch.setattr(runtime, "hydrate_final_answer_audit_ref", lambda _r: _audit_blocked_no_evidence())
    monkeypatch.setattr(loop, "_evaluate_turn_completion", lambda: SimpleNamespace(status="complete", is_terminal=True))

    text = loop._render_audited_publication(
        "本月收入增长了 5%。这是完整分析。", _audit_blocked_no_evidence())

    assert "本月收入增长了 5%" in text            # claim relayed, NOT deleted
    assert "这是完整分析" in text
    assert "无法发布" not in text                 # no placeholder, even though config=strict
    assert "当前可追踪证据不足" not in text
    # bookkeeping-only failure produces no alarming footer (Phase 0 refinement)
    assert "局限说明" not in text


def test_out_of_scope_dataset_is_allowed_with_warning(tmp_path):
    """D7: a dataset outside the current task scope must not block a tool call.

    The execution-scope guard records an advisory warning and allows the
    dataset; the workspace write path likewise logs and proceeds instead of
    returning ``Error: dataset_outside_current_task_scope``.
    """
    import pandas as pd
    from data_agent.agent.execution_scope import (
        consume_advisory_scope_warnings,
        ensure_dataset_allowed_for_current_task,
    )
    from data_agent.agent.context import AgentContext, use_agent_context
    from data_agent.session.task_manager import TaskManager
    from data_agent.session.workspace import (
        Workspace,
        consume_scope_advisory_warnings,
        workspace as workspace_proxy,
    )

    # Drain any warnings left by prior tests so the assertion below is precise.
    consume_advisory_scope_warnings()
    consume_scope_advisory_warnings()

    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    plan = manager.create_plan(
        session_id="s1",
        project_name="",
        goal="Analyze banner",
        source="analysis_plan",
    )
    task = manager.create(
        "Analyze banner",
        session_id="s1",
        project_name="",
        plan_id=plan["id"],
        plan_version=plan["version"],
        analysis_plan_id="analysis_plan_banner",
        step_id="step_banner",
        dataset_inputs=["banner"],
        dataset_contract_ids=["contract_banner"],
        combination_mode="single",
    )
    manager.update(task["id"], status="in_progress")

    # The loop-level scope guard: "iap" is not in the active task scope.
    denied = ensure_dataset_allowed_for_current_task(manager, "s1", dataset="iap")
    allowed = ensure_dataset_allowed_for_current_task(manager, "s1", dataset="banner")

    assert allowed.allowed is True
    # Advisory: access succeeds (not blocked) even though the dataset is out of scope.
    assert denied.allowed is True
    assert denied.error_type == ""
    assert "dataset_outside_current_task_scope" not in denied.message

    scope_warnings = consume_advisory_scope_warnings()
    assert any(
        w["warning"] == "dataset_outside_current_task_scope" and w["dataset"] == "iap"
        for w in scope_warnings
    )

    # The workspace write path is advisory too: an out-of-scope write proceeds
    # and records a warning instead of returning the error string.
    store = Workspace()
    store.add("banner", pd.DataFrame({"value": [1]}))
    ctx = AgentContext(session_id="s1", workspace=store)
    from data_agent.agent.execution_scope import WorkspaceScopeSnapshot

    snapshot = WorkspaceScopeSnapshot(
        phase="execution",
        allowed_datasets=frozenset({"banner"}),
    )
    with use_agent_context(ctx):
        with ctx.bind_workspace_scope(snapshot):
            write_result = workspace_proxy.add(
                "out_of_scope", pd.DataFrame({"x": [9]})
            )

    assert "dataset_outside_current_task_scope" not in str(write_result)
    assert "Error:" not in str(write_result)
    workspace_warnings = consume_scope_advisory_warnings()
    assert any(
        w["warning"] == "dataset_outside_current_task_scope"
        and w["dataset"] == "out_of_scope"
        for w in workspace_warnings
    )


def test_unavailable_dataset_is_advisory_not_blocking(tmp_path, monkeypatch):
    """M2-B Task 1: when the scope layer believes a dataset is 'bound to the
    current task but not loaded' (the stale-binding race on terminal task
    state), the guard must ALLOW access with a recorded warning, not block —
    so mid-analysis tool calls (e.g. create_chart) don't abort the turn.

    Mirrors ``test_out_of_scope_dataset_is_allowed_with_warning`` (M1 D7) but
    triggers the separate ``current_task_dataset_unavailable`` path: the task
    scope STILL lists the dataset as bound, but the workspace no longer reports
    it as loaded.
    """
    import data_agent.session.task_manager as task_manager_module
    from data_agent.agent.context import use_agent_context
    from data_agent.agent.execution_scope import consume_advisory_scope_warnings
    from data_agent.agent.loop import AgentLoop
    from data_agent.session.task_manager import TaskManager
    from data_agent.tools import visualization  # noqa: F401  -- registers create_chart

    # Drain any warnings left by prior tests so the assertion below is precise.
    consume_advisory_scope_warnings()

    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    plan = manager.create_plan(
        session_id="s1",
        project_name="",
        goal="Analyze banner",
        source="analysis_plan",
    )
    task = manager.create(
        "Analyze banner",
        session_id="s1",
        project_name="",
        plan_id=plan["id"],
        plan_version=plan["version"],
        analysis_plan_id="analysis_plan_banner",
        step_id="step_banner",
        dataset_inputs=["banner"],
        dataset_contract_ids=["contract_banner"],
        combination_mode="single",
    )
    manager.update(task["id"], status="in_progress")
    # Bind the manager as the process-global task_manager so the loop's
    # authoritative scope resolver sees the staged task. This mirrors
    # ``test_create_chart_cannot_fall_back_when_scoped_dataset_unavailable``.
    monkeypatch.setattr(task_manager_module, "task_manager", manager)

    # Stale-binding race: task scope says "banner" is bound, but the loop's
    # workspace (the default empty workspace from the test isolation fixture)
    # does NOT have it loaded. ``create_chart`` references it by name.
    loop = AgentLoop(client=object(), session_id="s1")

    with use_agent_context(loop.context):
        error = loop._current_task_scope_guard(
            "create_chart",
            {"chart_type": "bar", "data": "banner"},
        )

    # Advisory contract: the guard returns "" (allowed) instead of the
    # blocking JSON error, and records a warning with the
    # ``current_task_dataset_unavailable`` symbol for observability.
    assert error == ""
    warnings = consume_advisory_scope_warnings()
    assert any(
        w["warning"] == "current_task_dataset_unavailable"
        and w["dataset"] == "banner"
        for w in warnings
    )


# ── Task 3: non-destructive derived versions apply without a confirmation receipt ──

def _versioned_dataset_store(frame):
    """Build a workspace backed by a registered raw snapshot + analysis copy."""
    import pandas as pd
    from data_agent.agent.data_lineage import frame_fingerprint
    from data_agent.session.workspace import Workspace

    store = Workspace()
    raw_info = store.register_raw_snapshot("orders", frame, frame_fingerprint(frame))
    active_info = store.promote_analysis_copy(
        "orders", frame.copy(), raw_info["dataset_id"], {"id": "prepare"}
    )
    return store, raw_info, active_info


def test_non_destructive_derived_version_applies_without_confirmation(monkeypatch):
    """A copy-on-write derived version with no risk signals (no new nulls,
    no cardinality loss, no partial conversion, high confidence, no type
    mismatch) applies directly without an approved confirmation receipt.

    This covers the auto-mode batch path that previously initialized
    ``requires_confirmation = bool(auto)``, hanging the live session
    fee2e889e37f on a "creates a new analysis dataset version" prompt even
    when every conversion was benign. Raw is retained by the existing
    copy-on-write lineage, so the operation is non-destructive.
    """
    import json
    import pandas as pd
    from data_agent.tools import data_clean

    # Two columns, both safe to convert: percentage strings and numeric strings.
    # Neither introduces nulls, cardinality loss, or a partial conversion.
    store, raw_info, first = _versioned_dataset_store(
        pd.DataFrame({"rate": ["10%", "20%", "30%"], "id": ["1", "2", "3"]})
    )
    monkeypatch.setattr(data_clean, "workspace", store)

    result = json.loads(
        data_clean._apply_type_conversion_impl("orders", auto=True)
    )

    # Non-destructive: applies without a receipt...
    assert result["status"] == "applied"
    assert result.get("error_type", "") in (None, "")
    assert "confirmation_id" not in result
    assert "confirmation_required" not in json.dumps(result)
    # ...a new derived version was promoted...
    assert result["dataset_id"] != first["dataset_id"]
    assert result["parent_dataset_id"] == first["dataset_id"]
    # ...and the conversion actually happened.
    assert store.get("orders")["rate"].tolist() == [0.1, 0.2, 0.3]
    assert store.get("orders")["id"].tolist() == [1, 2, 3]
    # Raw snapshot is retained unchanged (copy-on-write lineage).
    assert store.get_raw_snapshot(raw_info["dataset_id"])["rate"].tolist() == ["10%", "20%", "30%"]


def test_destructive_cleaning_still_requires_confirmation(monkeypatch):
    """A meaning-changing conversion (cardinality loss) still requires an
    approved confirmation receipt. The non-destructive carve-out must not
    weaken the gate for genuinely destructive operations.
    """
    import json
    import pandas as pd
    from data_agent.tools import data_clean

    # "1", "01", "2" -> 1, 1, 2 collapses cardinality (3 distinct -> 2).
    store, raw_info, first = _versioned_dataset_store(
        pd.DataFrame({"code": ["1", "01", "2"]})
    )
    monkeypatch.setattr(data_clean, "workspace", store)

    result = json.loads(
        data_clean._apply_type_conversion_impl(
            "orders", column="code", target_type="numeric", _approved_confirmation_id=""
        )
    )

    assert result["status"] == "confirmation_required"
    assert "confirmation_id" in result
    # No mutation occurred: active version unchanged, raw retained.
    assert store.get_active_version_info("orders")["dataset_id"] == first["dataset_id"]
    assert store.get("orders")["code"].tolist() == ["1", "01", "2"]


# ── Task 4: advance the task list from real tool execution, not binding ──

def _eight_step_coordinator(tmp_path):
    """Build a coordinator with a materialized 8-step plan.

    Mirrors the production setup: an active AnalysisRun with one IN_PROGRESS
    step (step_1) and seven PENDING steps. ``legacy_projection`` exposes the
    step statuses back to legacy tasks exactly as the front-end ``任务 N/M``
    counter consumes them.
    """
    from data_agent.agent.analysis_run_coordinator import AnalysisRunCoordinator
    from data_agent.session.analysis_run_store import AnalysisRunStore

    store = AnalysisRunStore(
        tmp_path / "analysis-runs.sqlite3",
        state_root=tmp_path,
    )
    coordinator = AnalysisRunCoordinator(store)
    tasks = [
        {
            "id": 100 + idx,
            "subject": f"Step {idx + 1}",
            "plan_id": "plan-task4",
            "analysis_plan_id": "ap-task4",
            "step_id": f"step_{idx + 1}",
            "dataset_inputs": ["data"],
            "dataset_contract_ids": ["c-1"],
            "combination_mode": "single",
            "required_capability": "analysis.relationship",
        }
        for idx in range(8)
    ]
    coordinator.materialize_plan(
        session_id="sess-task4",
        project_name="proj-task4",
        plan_id="plan-task4",
        tasks=tasks,
    )
    return coordinator


def _task_progress(coordinator) -> str:
    """Return ``done/total`` over the coordinator's active run.

    Matches the front-end ``taskProgress`` getter: ``done`` counts steps whose
    legacy projection is ``completed``.
    """
    run = coordinator.store.get_active_run("sess-task4")
    projection = coordinator.legacy_projection(run)
    done = sum(1 for status in projection.values() if status == "completed")
    return f"{done}/{len(projection)}"


def test_task_advances_on_tool_execution_without_binding(tmp_path):
    """The task list advances when a tool executes against the active step,
    even when plan-step binding failed (analysis_step_not_found). Advancement
    must not depend on binding success.

    The M1 contract: a non-error tool execution against the active step
    advances the task list past 0/N. Fixing ``bind_tool_call_to_plan_step``
    itself is M2; this task only changes how *advancement* reacts to tool
    execution.
    """
    coordinator = _eight_step_coordinator(tmp_path)

    # Initial state: 0/8, step_1 is the active (first incomplete) step.
    assert _task_progress(coordinator) == "0/8"
    run_before = coordinator.store.get_active_run("sess-task4")
    assert run_before.current_step.payload["external_step_id"] == "step_1"

    # A tool executes against the active step. In production the capability
    # binder returns ``ok=False, error_type="analysis_step_not_found"`` for
    # ~100% of substantive calls. The coordinator advances the active step
    # on execution alone, independent of that binding outcome.
    coordinator.advance_active_step_on_tool_execution(
        session_id="sess-task4",
        tool_call_id="tc-task4-1",
        tool_succeeded=True,
    )

    # The task list advanced past 0/8: step_1 is complete, step_2 is active.
    progress = _task_progress(coordinator)
    assert progress != "0/8"
    assert int(progress.split("/")[0]) >= 1
    run_after = coordinator.store.get_active_run("sess-task4")
    assert run_after.current_step.payload["external_step_id"] == "step_2"


def test_task_advancement_is_idempotent_and_skips_failed_tools(tmp_path):
    """A failed tool execution must not advance the step, and a repeated
    advancement call for the same tool_call_id is a no-op (idempotent)."""
    coordinator = _eight_step_coordinator(tmp_path)

    # A failed tool execution does not advance the active step.
    coordinator.advance_active_step_on_tool_execution(
        session_id="sess-task4",
        tool_call_id="tc-failed",
        tool_succeeded=False,
    )
    assert _task_progress(coordinator) == "0/8"

    # A non-error execution advances step_1 → step_2.
    coordinator.advance_active_step_on_tool_execution(
        session_id="sess-task4",
        tool_call_id="tc-ok",
        tool_succeeded=True,
    )
    assert _task_progress(coordinator) == "1/8"

    # Replaying the same tool_call_id does not advance a second time.
    coordinator.advance_active_step_on_tool_execution(
        session_id="sess-task4",
        tool_call_id="tc-ok",
        tool_succeeded=True,
    )
    assert _task_progress(coordinator) == "1/8"


def test_task_advancement_does_not_double_advance_after_binder_path(tmp_path):
    """When the binder-gated path already completed the active step (committed
    evidence satisfied the step's claims), the execution-driven advancement
    must not advance a second step. This guards against the active pointer
    skipping a step when both paths run in the same turn.

    The caller passes ``expected_active_step_id`` (the store-level step
    identity from ``analysis_run_binding["step_id"]``); the coordinator
    compares it against the current active step and no-ops on mismatch.
    """
    coordinator = _eight_step_coordinator(tmp_path)
    run = coordinator.store.get_active_run("sess-task4")
    step_1_id = run.current_step.step_id

    # Simulate the binder-gated path: committed evidence completes step_1.
    coordinator.store.complete_and_activate_next(
        run_id=run.run_id,
        step_id=step_1_id,
        session_id="sess-task4",
        idempotency_key=f"computation:tc-task4-binder",
    )
    # step_1 completed, step_2 is now the active step.
    assert _task_progress(coordinator) == "1/8"

    # The execution-driven advancement now runs for the same tool call. The
    # caller passes the step_1 identity it bound to; the coordinator detects
    # that the active pointer has moved on and does NOT advance step_2.
    coordinator.advance_active_step_on_tool_execution(
        session_id="sess-task4",
        tool_call_id="tc-task4-binder",
        tool_succeeded=True,
        expected_active_step_id=step_1_id,
    )
    assert _task_progress(coordinator) == "1/8"
    run_after = coordinator.store.get_active_run("sess-task4")
    assert run_after.current_step.payload["external_step_id"] == "step_2"
