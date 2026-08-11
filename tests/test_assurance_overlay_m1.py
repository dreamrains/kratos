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
