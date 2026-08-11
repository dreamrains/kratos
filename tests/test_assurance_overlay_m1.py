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
