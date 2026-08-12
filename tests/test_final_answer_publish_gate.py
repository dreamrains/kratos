from types import SimpleNamespace

import pytest

from data_agent.agent.execution_control import ToolExecutionBudget, TurnExecutionState
from data_agent.agent.loop import AgentLoop
from data_agent.agent import trust_workflow_runtime as runtime
from data_agent.llm.client import Response, StreamComplete, StreamTextDelta, ToolCall


def _intent(intent_type="directed_analysis"):
    return SimpleNamespace(intent_type=intent_type, execution_readiness="ready")


def _state(*, evidence=True):
    state = SimpleNamespace(
        evidence_records=[{"id": "ev_1"}] if evidence else [],
        verification_reports=[],
        turn_diagnostics=[],
    )
    state.append_turn_diagnostic = state.turn_diagnostics.append
    return state


def _audit(status, *, reason_codes=None, public_text="Audited result."):
    check_status = {
        "pass": "passed",
        "revise": "downgraded",
        "blocked": "failed",
    }[status]
    return {
        "contract_version": "final_answer_audit.v1",
        "id": f"audit_{status}",
        "status": status,
        "public_text": public_text,
        "claims": [{
            "id": "claim_1",
            "text": public_text,
            "claim_type": "comparison",
            "material": True,
        }],
        "claim_checks": [{
            "claim_id": "claim_1",
            "claim": "Raw result.",
            "status": check_status,
            "reason_codes": list(reason_codes or []),
            "issues": ["fixture issue"] if reason_codes else [],
        }],
    }


def _patch_runtime_audit(monkeypatch, audit):
    ref = {
        "contract_version": "final_answer_audit.v1",
        "id": audit["id"],
        "status": audit["status"],
        "artifact_path": "fixture.json",
        "artifact_digest": "0" * 64,
    }
    monkeypatch.setattr(runtime, "audit_final_answer_draft", lambda *_args, **_kwargs: ref)
    monkeypatch.setattr(runtime, "hydrate_final_answer_audit_ref", lambda _ref: audit)


def _analysis_loop():
    loop = AgentLoop(client=object(), session_id="publish_gate")
    loop._last_turn_intent = _intent()
    loop.context.analysis_state = _state()
    loop.messages = [{"role": "assistant", "content": "Raw result [[evidence:ev_1]]."}]
    loop._reset_turn_tracking()
    loop._last_turn_intent = _intent()
    # This file exercises the tiered publication gate (revision loops, persisted
    # audit, mixed tiers, streaming buffering). The production default is now
    # ``transparent``, so pin the mode back to ``tiered`` to keep testing that
    # machinery. The default-config behavior is covered in
    # test_tiered_analysis_publication.py.
    loop._publication_mode = lambda: "tiered"
    return loop


def test_non_analysis_chat_skips_final_answer_audit(monkeypatch):
    loop = _analysis_loop()
    loop._last_turn_intent = _intent("simple_response")
    monkeypatch.setattr(
        runtime,
        "audit_final_answer_draft",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("audit should not run")),
    )

    result = loop._gate_final_analysis_answer("hello", "Hello, world.")

    assert result == {"action": "publish", "text": "Hello, world."}


def test_resumed_analysis_state_is_audit_candidate_without_process_local_intent():
    loop = _analysis_loop()
    loop._last_turn_intent = None
    loop._turn_resumed_from_confirmation = True
    loop.context.analysis_state.analysis_plan = {"id": "plan_resumed"}

    assert loop._is_final_answer_audit_candidate() is True


def test_passed_audit_publishes_stripped_text_and_replaces_raw_history(monkeypatch):
    loop = _analysis_loop()
    _patch_runtime_audit(monkeypatch, _audit("pass", public_text="Audited result."))

    result = loop._gate_final_analysis_answer("analyze", "Raw result [[evidence:ev_1]].")

    assert result == {"action": "publish", "text": "Audited result."}
    assert loop.messages[-1]["content"] == "Audited result."
    assert not any("final_answer_audit_repair" in str(message) for message in loop.messages)


def test_gate_passes_only_current_turn_alias_map_to_audit(monkeypatch):
    loop = _analysis_loop()
    aliases = (("ae01", "am01", "ev_1", "m_1"),)
    loop._turn_synthesis_evidence_aliases = aliases
    captured = {}
    audit = _audit("pass", public_text="Audited result.")
    ref = {
        "contract_version": "final_answer_audit.v1",
        "id": audit["id"],
        "status": audit["status"],
        "artifact_path": "fixture.json",
        "artifact_digest": "0" * 64,
    }

    def audit_draft(_text, _state, *, evidence_aliases=(), **_kwargs):
        captured["aliases"] = evidence_aliases
        return ref

    monkeypatch.setattr(runtime, "audit_final_answer_draft", audit_draft)
    monkeypatch.setattr(runtime, "hydrate_final_answer_audit_ref", lambda _ref: audit)

    result = loop._gate_final_analysis_answer(
        "analyze",
        "Raw result [[evidence:ae01#am01]].",
    )

    assert result["action"] == "publish"
    assert captured["aliases"] == aliases


def test_turn_reset_discards_prior_synthesis_aliases():
    loop = _analysis_loop()
    loop._turn_synthesis_evidence_aliases = (("ae01", "am01", "ev_1", "m_1"),)

    loop._reset_turn_tracking()

    assert loop._turn_synthesis_evidence_aliases == ()


def test_passed_audit_cannot_publish_process_narration_as_comprehensive_report(monkeypatch):
    """Evidence correctness alone does not make an unfinished process note a
    complete answer.  The runtime gets one synthesis-only repair, never more
    analysis tools, even when the claim audit itself passed."""
    loop = _analysis_loop()
    loop._last_turn_intent = _intent("comprehensive_report")
    process_note = "现在继续执行 Python 分析：验证成本结构、偏相关与分群净效应。"
    _patch_runtime_audit(
        monkeypatch,
        _audit("pass", public_text=process_note),
    )

    result = loop._gate_final_analysis_answer("analyze", process_note)

    assert result == {"action": "continue", "mode": "synthesis"}
    assert loop._turn_final_audit_revision_used is True
    assert 'mode="synthesis"' in loop._turn_final_audit_instruction
    assert "analysis_answer_incomplete" in loop._turn_final_audit_instruction
    assert "Do not call tools" in loop._turn_final_audit_instruction
    assert not any(message.get("role") == "assistant" for message in loop.messages)


def test_directed_analysis_process_narration_is_repaired_before_audit(monkeypatch):
    loop = _analysis_loop()
    process_note = "复核完成，现在做最后一步：检验分群差异是否显著。"
    monkeypatch.setattr(
        runtime,
        "audit_final_answer_draft",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("incomplete process narration must be repaired before audit")
        ),
    )

    result = loop._gate_final_analysis_answer("analyze", process_note)

    assert result == {"action": "continue", "mode": "synthesis"}
    assert "analysis_answer_incomplete" in loop._turn_final_audit_instruction


def test_audit_runtime_failure_records_bounded_diagnostic(monkeypatch):
    loop = _analysis_loop()
    diagnostics = []
    loop.context.analysis_state.turn_diagnostics = diagnostics
    loop.context.analysis_state.append_turn_diagnostic = diagnostics.append
    monkeypatch.setattr(
        runtime,
        "audit_final_answer_draft",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("secret detail")),
    )

    result = loop._gate_final_analysis_answer("analyze", "分析结果。")

    assert result["action"] == "fallback"
    assert {
        "event": "final_answer_audit_runtime_failure",
        "exception_type": "RuntimeError",
    } in diagnostics


def test_internal_evidence_markers_are_stripped_from_intermediate_analysis_text():
    loop = _analysis_loop()

    public = loop._public_intermediate_text("Working [[evidence:ev_1]] on the next step.")

    assert public == "Working on the next step."


def test_unknown_alias_marker_is_stripped_from_public_intermediate_text():
    loop = _analysis_loop()

    public = loop._public_intermediate_text(
        "Working [[evidence:ae99#am99]] on the next step."
    )

    assert public == "Working on the next step."


def test_current_alias_and_markerless_claim_publish_as_mixed_tiers(
    tmp_path,
    monkeypatch,
):
    from tests.fixtures.measurement_identity import (
        DATASET_VERSION,
        build_projection_context,
        project_real_correlation,
    )

    context = build_projection_context(tmp_path)
    evidence = project_real_correlation(context).record
    key = evidence["measurements"][0]["identity"]["measurement_key"]
    state = SimpleNamespace(
        session_id=context.session_id,
        analysis_plan=context.plan,
        evidence_records=[evidence],
        route_proposals=[],
        cleaning_logs=[],
        verification_reports=[],
        turn_diagnostics=[],
        append_turn_diagnostic=lambda item: state.turn_diagnostics.append(item),
        save=lambda: None,
    )
    loop = _analysis_loop()
    loop.context.analysis_state = state
    monkeypatch.setattr(
        loop,
        "_evaluate_turn_completion",
        lambda: SimpleNamespace(status="complete_with_limits"),
    )
    loop._turn_synthesis_evidence_aliases = (
        ("ae01", "am01", evidence["id"], key),
    )
    draft = (
        "The revenue cost correlation is 0.4 [[evidence:ae01#am01]].\n"
        "Profit increased 25%.\n"
        "Limitation: this is descriptive analysis and the profit claim is not independently verified."
    )
    loop.messages = [{"role": "assistant", "content": draft}]
    monkeypatch.setattr(runtime, "_sessions_root", lambda: context.sessions_root)
    monkeypatch.setattr(runtime, "_active_dataset_versions", lambda: [DATASET_VERSION])

    result = loop._gate_final_analysis_answer(
        "analyze the relationship",
        draft,
        allow_repair=False,
    )

    assert result["action"] == "fallback"
    assert "The revenue cost correlation is 0.4" in result["text"]
    # Task 1 (M1): the loop now always publishes transparently regardless of
    # the configured mode. The markerless claim is relayed (NOT deleted) and no
    # "无法发布" placeholder is emitted; the audit only records per-claim
    # actions for diagnostics.
    assert "Profit increased 25%" in result["text"]
    assert "无法发布" not in result["text"]
    assert "[[evidence:" not in result["text"]
    actions = state.turn_diagnostics[-1]["actions"]
    assert "verified" in actions.values(), [
        (check.get("claim_id"), check.get("status"), check.get("reason_codes"))
        for check in loop._turn_last_final_audit["claim_checks"]
    ]
    assert "unsupported" in actions.values()


def test_gate_runs_real_persisted_audit_before_tiered_publication(
    tmp_path,
    monkeypatch,
):
    evidence = {
        "id": "ev_1",
        "plan_id": "plan_current",
        "step_id": "step_1",
        "claim": "Revenue increased 12%.",
        "dataset": "sales",
        "method": "period_compare",
        "sample_size": 100,
        "time_scope": "2026-05",
        "calculation_method": "period delta",
        "method_detail": "compared May with April",
        "limitations": ["descriptive only"],
        "confidence": "medium",
        "verification_level": "structured_checked",
        "measurements": [{
            "metric": "revenue_change",
            "value": 0.12,
            "unit": "ratio",
            "population_scope": "all users",
            "time_scope": "2026-05",
        }],
    }
    state = SimpleNamespace(
        session_id="publish_real_audit",
        analysis_plan={"id": "plan_current", "analysis_requirements": {}},
        evidence_records=[evidence],
        route_proposals=[],
        cleaning_logs=[],
        verification_reports=[],
        save=lambda: None,
    )
    loop = _analysis_loop()
    loop.context.analysis_state = state
    loop.messages = [{
        "role": "assistant",
        "content": "Revenue increased 12% [[evidence:ev_1]].\nLimitation: descriptive only.",
    }]
    monkeypatch.setattr(runtime, "_sessions_root", lambda: tmp_path / "sessions")
    monkeypatch.setattr(runtime, "_active_dataset_versions", lambda: None)

    result = loop._gate_final_analysis_answer(
        "analyze",
        "Revenue increased 12% [[evidence:ev_1]].\nLimitation: descriptive only.",
    )

    assert result["action"] == "fallback"
    assert "[[evidence:" not in result["text"]
    assert "Revenue increased 12%" in result["text"]
    # Task 1 (M1): transparent publication relays the draft without the
    # per-claim exploratory suffix; the draft's own limitation disclosure is
    # preserved verbatim.
    assert "探索性，未经独立校验" not in result["text"]
    assert "Limitation: descriptive only." in result["text"]
    assert "无法发布" not in result["text"]
    assert state.verification_reports[-1]["contract_version"] == "final_answer_audit.v1"


def test_revise_gets_one_synthesis_only_retry_then_bounded_fallback(monkeypatch):
    loop = _analysis_loop()
    _patch_runtime_audit(monkeypatch, _audit("revise", reason_codes=["missing_limitation"]))

    first = loop._gate_final_analysis_answer("analyze", "Raw result [[evidence:ev_1]].")

    assert first == {"action": "continue", "mode": "synthesis"}
    assert loop._turn_final_audit_revision_used is True
    assert "mode=\"synthesis\"" in loop._turn_final_audit_instruction
    assert not any(message.get("role") == "assistant" for message in loop.messages)

    loop.messages.append({"role": "assistant", "content": "Still incomplete [[evidence:ev_1]]."})
    second = loop._gate_final_analysis_answer("analyze", "Still incomplete [[evidence:ev_1]].")

    # Old behavior emitted a generic English "could not be published" fallback
    # that destroyed useful structure. Task 1 (M1): transparent publication
    # relays the draft verbatim (no whole-answer wipe) and strips internal
    # evidence markers; the audit only records per-claim actions for diagnostics.
    assert second["action"] == "fallback"
    assert "Still incomplete" in second["text"]
    assert "could not be published" not in second["text"]
    assert "[[evidence:" not in second["text"]
    assert loop._turn_final_audit_instruction == ""


def test_measurement_identity_missing_gets_at_most_one_synthesis_only_revision(
    monkeypatch,
):
    loop = _analysis_loop()
    loop._turn_synthesis_evidence_aliases = (
        ("ae01", "am01", "ev_1", "m_1"),
    )
    _patch_runtime_audit(
        monkeypatch,
        _audit("blocked", reason_codes=["measurement_identity_missing"]),
    )

    first = loop._gate_final_analysis_answer("analyze", "Markerless result.")

    assert first == {"action": "continue", "mode": "synthesis"}
    assert loop._turn_final_audit_revision_used is True
    assert loop._turn_final_audit_analysis_retry_used is False
    assert 'mode="synthesis"' in loop._turn_final_audit_instruction
    assert "Do not call tools" in loop._turn_final_audit_instruction

    loop.messages.append({"role": "assistant", "content": "Still markerless."})
    second = loop._gate_final_analysis_answer("analyze", "Still markerless.")

    assert second["action"] == "fallback"
    assert loop._turn_final_audit_analysis_retry_used is False
    assert 'mode="analysis"' not in loop._turn_final_audit_instruction


def test_missing_evidence_identity_with_failed_check_gets_synthesis_revision(
    monkeypatch,
):
    """The verifier emits ``evidence_check_failed`` as the generic companion
    to the actionable missing-identity code.  That companion must not suppress
    the one bounded synthesis repair which can carry current catalog markers."""

    loop = _analysis_loop()
    loop._turn_synthesis_evidence_aliases = (
        ("ae01", "am01", "ev_1", "m_1"),
    )
    _patch_runtime_audit(
        monkeypatch,
        _audit(
            "blocked",
            reason_codes=["missing_evidence_identity", "evidence_check_failed"],
        ),
    )

    result = loop._gate_final_analysis_answer("analyze", "Markerless result.")

    assert result == {"action": "continue", "mode": "synthesis"}
    assert loop._turn_final_audit_revision_used is True
    assert loop._turn_final_audit_analysis_retry_used is False
    assert "[[evidence:aeNN#amNN]]" in loop._turn_final_audit_instruction
    assert "record_id#measurement_key" not in loop._turn_final_audit_instruction
    # Sound parts of the synthesis-repair instruction are retained: the marker
    # is carried with its identity tokens, unsupported claims are downgraded,
    # the answer stays complete with findings/recommendations/limitations, and
    # the repair calls no tools.
    assert "exact identity tokens" in loop._turn_final_audit_instruction
    assert "exploratory" in loop._turn_final_audit_instruction
    assert "Do not call tools" in loop._turn_final_audit_instruction
    assert "findings" in loop._turn_final_audit_instruction
    assert "recommendations" in loop._turn_final_audit_instruction
    assert "limitations" in loop._turn_final_audit_instruction
    # The rigid marker-regeneration ceremony is gone.
    assert "required_verified_core_copy" not in loop._turn_final_audit_instruction
    assert "standalone verified-core sentence" not in loop._turn_final_audit_instruction
    assert "verbatim" not in loop._turn_final_audit_instruction


def test_audit_repair_instruction_has_no_char_cap_and_no_rigid_ceremony(monkeypatch):
    """The audit-repair instruction must not cap answer length and must not
    force the rigid marker-regeneration ceremony that choked the draft.

    The 2400-char cap directly explained the ~2318-char M1 answer; the
    verbatim-copy / ``required_verified_core_copy`` / standalone-verified-core
    rules crowded out content.  Both are removed.  Sound parts stay:
    a complete answer with findings/limitations, downgrade of unsupported
    claims, markers retained for re-audit, and (synthesis branch) no tools.
    """

    loop = _analysis_loop()
    loop._inject_final_answer_audit_repair(
        mode="synthesis", reason_codes=["provider_output_truncated"]
    )
    instr = loop._turn_final_audit_instruction
    # D3: 2400-char cap removed
    assert "2400" not in instr
    assert "within 2400" not in instr
    # D4: rigid marker ceremony removed
    assert "required_verified_core_copy" not in instr
    assert "standalone verified-core sentence" not in instr
    # Sound parts kept
    assert "findings" in instr and "limitations" in instr  # complete answer
    assert "downgrade" in instr or "unsupported" in instr.lower()  # downgrade
    # synthesis branch keeps no-tools
    loop._inject_final_answer_audit_repair(
        mode="synthesis", reason_codes=["missing_evidence_identity"]
    )
    assert (
        "Do not call tools" in loop._turn_final_audit_instruction
        or "do not call" in loop._turn_final_audit_instruction.lower()
    )


@pytest.mark.parametrize(
    ("reason_code", "expected_action"),
    [
        ("measurement_marker_invalid", "continue"),
        ("measurement_not_found", "fallback"),
        ("measurement_metric_mismatch", "continue"),
        ("measurement_claim_key_mismatch", "fallback"),
        ("measurement_scope_mismatch", "fallback"),
        ("measurement_dataset_version_mismatch", "fallback"),
        ("measurement_ambiguous", "continue"),
    ],
)
def test_measurement_bookkeeping_never_requests_analysis_retry(
    monkeypatch,
    reason_code,
    expected_action,
):
    loop = _analysis_loop()
    loop._turn_synthesis_evidence_aliases = (
        ("ae01", "am01", "ev_1", "m_1"),
    )
    _patch_runtime_audit(
        monkeypatch,
        _audit("blocked", reason_codes=[reason_code]),
    )

    result = loop._gate_final_analysis_answer("analyze", "Measured result.")

    assert result["action"] == expected_action
    assert result.get("mode") != "analysis"
    assert loop._turn_final_audit_analysis_retry_used is False
    assert 'mode="analysis"' not in loop._turn_final_audit_instruction


def test_live_provider_copy_failures_get_one_synthesis_revision(monkeypatch):
    loop = _analysis_loop()
    loop._turn_synthesis_evidence_aliases = (
        ("ae01", "am01", "ev_1", "m_1"),
    )
    _patch_runtime_audit(
        monkeypatch,
        _audit(
            "blocked",
            reason_codes=[
                "evidence_check_failed",
                "measurement_ambiguous",
                "measurement_metric_mismatch",
                "missing_evidence_identity",
                "numeric_mismatch",
                "unit_mismatch",
            ],
        ),
    )

    first = loop._gate_final_analysis_answer("analyze", "Imprecise result.")

    assert first == {"action": "continue", "mode": "synthesis"}
    assert loop._turn_final_audit_revision_used is True
    assert loop._turn_final_audit_analysis_retry_used is False
    assert "[[evidence:aeNN#amNN]]" in loop._turn_final_audit_instruction
    assert "Do not call tools" in loop._turn_final_audit_instruction
    assert "required_verified_core_copy" not in loop._turn_final_audit_instruction
    assert 'mode="analysis"' not in loop._turn_final_audit_instruction

    loop.messages.append({"role": "assistant", "content": "Still imprecise."})
    second = loop._gate_final_analysis_answer("analyze", "Still imprecise.")

    assert second["action"] == "fallback"
    assert loop._turn_final_audit_analysis_retry_used is False


def test_measurement_contradiction_suppresses_mixed_generic_analysis_retry(
    monkeypatch,
):
    loop = _analysis_loop()
    loop.context.turn_state = TurnExecutionState(
        budget=ToolExecutionBudget(max_tool_calls=1),
    )
    _patch_runtime_audit(
        monkeypatch,
        _audit(
            "blocked",
            reason_codes=["measurement_not_found", "unsupported_claim"],
        ),
    )

    result = loop._gate_final_analysis_answer("analyze", "Measured result.")

    assert result["action"] == "fallback"
    assert loop._turn_final_audit_analysis_retry_used is False
    assert 'mode="analysis"' not in loop._turn_final_audit_instruction


def test_downgraded_measurement_bookkeeping_suppresses_failed_claim_retry(
    monkeypatch,
):
    loop = _analysis_loop()
    loop.context.turn_state = TurnExecutionState(
        budget=ToolExecutionBudget(max_tool_calls=1),
    )
    audit = {
        "contract_version": "final_answer_audit.v1",
        "id": "audit_two_checks",
        "status": "blocked",
        "public_text": "Measured result. Unsupported result.",
        "claims": [
            {
                "id": "claim_measurement",
                "text": "Measured result.",
                "claim_type": "comparison",
                "material": True,
            },
            {
                "id": "claim_unsupported",
                "text": "Unsupported result.",
                "claim_type": "comparison",
                "material": True,
            },
        ],
        "claim_checks": [
            {
                "claim_id": "claim_measurement",
                "claim": "Measured result.",
                "status": "downgraded",
                "reason_codes": ["measurement_identity_missing"],
                "issues": ["missing measurement-grain marker"],
            },
            {
                "claim_id": "claim_unsupported",
                "claim": "Unsupported result.",
                "status": "failed",
                "reason_codes": ["unsupported_claim"],
                "issues": ["no computation evidence"],
            },
        ],
    }
    _patch_runtime_audit(monkeypatch, audit)

    result = loop._gate_final_analysis_answer(
        "analyze",
        "Measured result. Unsupported result.",
    )

    assert result["action"] == "fallback"
    assert loop._turn_final_audit_analysis_retry_used is False
    assert 'mode="analysis"' not in loop._turn_final_audit_instruction


def test_missing_computation_evidence_continues_analysis_only_when_budget_remains(monkeypatch):
    loop = _analysis_loop()
    loop.context.turn_state = TurnExecutionState(
        budget=ToolExecutionBudget(max_tool_calls=1),
    )
    _patch_runtime_audit(monkeypatch, _audit("blocked", reason_codes=["unsupported_claim"]))

    first = loop._gate_final_analysis_answer("analyze", "Unsupported result.")

    assert first == {"action": "continue", "mode": "analysis"}
    assert loop._turn_final_audit_analysis_retry_used is True
    assert "mode=\"analysis\"" in loop._turn_final_audit_instruction

    loop.messages.append({"role": "assistant", "content": "Still unsupported."})
    second = loop._gate_final_analysis_answer("analyze", "Still unsupported.")

    assert second["action"] == "fallback"


def test_exhausted_budget_returns_safe_partial_instead_of_requesting_reanalysis(monkeypatch):
    loop = _analysis_loop()
    turn_state = TurnExecutionState(budget=ToolExecutionBudget(max_tool_calls=1))
    turn_state.tool_calls = 1
    loop.context.turn_state = turn_state
    _patch_runtime_audit(monkeypatch, _audit("blocked", reason_codes=["unsupported_claim"]))

    result = loop._gate_final_analysis_answer("analyze", "Unsupported result.")

    assert result["action"] == "fallback"
    assert loop._turn_final_audit_analysis_retry_used is False


def test_renderer_keeps_passed_claims_and_replaces_failed_with_chinese_diagnostic():
    """Replaces the deleted `_safe_final_answer_fallback` test.

    The renderer keeps verified passed claims (including limitations) in
    their original order and replaces the failed claim's span with a Chinese
    diagnostic. It must not emit the legacy English whole-answer fallback.
    """

    from data_agent.agent.answer_quality import render_audited_analysis_answer

    public_text = (
        "Revenue increased 12%.\n"
        "Limitation: this is a descriptive comparison only.\n"
        "The campaign caused the increase."
    )
    audit = {
        "contract_version": "final_answer_audit.v1",
        "public_text": public_text,
        "claims": [
            {"id": "claim_1", "text": "Revenue increased 12%."},
            {"id": "claim_2", "text": "Limitation: this is a descriptive comparison only."},
            {"id": "claim_3", "text": "The campaign caused the increase."},
        ],
        "claim_checks": [
            {"claim_id": "claim_1", "status": "passed"},
            {"claim_id": "claim_2", "status": "passed"},
            {
                "claim_id": "claim_3",
                "status": "failed",
                "reason_codes": ["unmet_block_claim_requirement"],
            },
        ],
    }
    completion = SimpleNamespace(status="complete")

    result = render_audited_analysis_answer(
        draft=public_text,
        audit=audit,
        completion=completion,
        mode="tiered",
    )

    assert "Revenue increased 12%." in result.text
    assert "Limitation: this is a descriptive comparison only." in result.text
    assert result.text.index("Revenue increased 12%.") < result.text.index("Limitation:")
    assert "campaign caused" not in result.text
    assert "无法发布" in result.text
    assert result.actions["claim_3"] == "unsupported"
    assert "Some requested analysis claims" not in result.text


def test_sync_loop_returns_only_audited_text(monkeypatch):
    loop = _analysis_loop()
    loop.client = SimpleNamespace(chat=lambda **_kwargs: Response(text="Raw streamed result."))
    loop._get_system_prompt = lambda: ""
    loop._runtime_confirmation_checkpoint = lambda: None
    loop._maybe_inject_synthesis_policy = lambda _user_input: None
    loop._should_continue_for_analysis_quality = lambda *_args: False
    monkeypatch.setattr(
        loop,
        "_gate_final_analysis_answer",
        lambda *_args, **_kwargs: {"action": "publish", "text": "Audited sync result."},
    )

    result = loop._loop_impl("analyze")

    assert result.content == "Audited sync result."


def test_synthesis_only_revision_cannot_escape_into_tool_execution():
    loop = _analysis_loop()
    loop.messages = []
    loop._turn_final_audit_instruction = (
        '<final_answer_audit_repair mode="synthesis">revise only</final_answer_audit_repair>'
    )
    loop._turn_last_final_audit = _audit(
        "revise",
        reason_codes=["missing_limitation"],
    )
    loop.client = SimpleNamespace(chat=lambda **_kwargs: Response(
        text="Synthesis draft answer.",
        tool_calls=[
            ToolCall(id="forbidden", name="run_python", arguments={"code": "print(1)"}),
        ],
    ))
    loop._get_system_prompt = lambda: ""
    loop._runtime_confirmation_checkpoint = lambda: None

    result = loop._loop_impl("analyze")

    # The tool call is rejected and the draft is published via transparent
    # rendering (Task 1 / M1: the loop never selects a destructive renderer).
    # The legacy English "could not be published" wording is gone — that is the
    # regression we are guarding against.
    assert "Synthesis draft answer" in result.content
    assert "could not be published" not in result.content
    assert not any(message.get("tool_calls") for message in loop.messages)
    assert loop._turn_final_audit_instruction == ""


def test_truncation_revision_tool_call_falls_back_to_original_candidate(monkeypatch):
    original = (
        "发现：收入在客户分群之间存在明显差异。" * 20
        + "\n建议：优先验证分群定价和渠道策略。" * 12
        + "\n局限：当前结果是描述性关联，不能解释为因果关系。" * 12
    )

    class Client:
        max_tokens = 8_000

        def __init__(self):
            self.round = 0

        def chat(self, **_kwargs):
            self.round += 1
            if self.round == 1:
                return Response(text=original, finish_reason="length")
            return Response(
                text="我再运行一次计算。",
                tool_calls=[
                    ToolCall(id="forbidden", name="run_python", arguments={"code": "print(1)"}),
                ],
            )

    client = Client()
    loop = AgentLoop(client=client, session_id="publish_gate_truncation_tool_revision")
    loop._last_turn_intent = _intent("comprehensive_report")
    loop.context.analysis_state = _state()
    loop.context.turn_state = TurnExecutionState(ToolExecutionBudget(
        token_budget=40_000,
        synthesis_reserve_tokens=8_000,
        audit_reserve_tokens=4_000,
        revision_reserve_tokens=8_000,
    ))
    loop._get_system_prompt = lambda: getattr(loop, "_turn_final_audit_instruction", "")
    loop._runtime_confirmation_checkpoint = lambda: None
    loop._maybe_inject_synthesis_policy = lambda _user_input: None
    loop._should_continue_for_analysis_quality = lambda *_args: False
    captured = {}
    ref = {
        "contract_version": "final_answer_audit.v1",
        "id": "audit_tool_revision_fallback",
        "status": "pass",
        "artifact_path": "fixture.json",
        "artifact_digest": "0" * 64,
    }

    def audit_draft(text, *_args, **_kwargs):
        captured["text"] = text
        return ref

    monkeypatch.setattr(runtime, "audit_final_answer_draft", audit_draft)
    monkeypatch.setattr(
        runtime,
        "hydrate_final_answer_audit_ref",
        lambda _ref: _audit("pass", public_text=captured["text"]),
    )

    result = loop._loop_impl("analyze comprehensively")

    assert client.round == 2
    assert result.content == original
    assert captured["text"] == original
    assert not any(message.get("tool_calls") for message in loop.messages)


def test_streaming_analysis_buffers_raw_deltas_until_audit_passes(monkeypatch):
    class Client:
        def stream_chat_structured(self, **_kwargs):
            yield StreamTextDelta("UNAUDITED RAW")
            yield StreamComplete(Response(text="UNAUDITED RAW"))

    loop = AgentLoop(client=Client(), session_id="publish_gate_stream")
    loop._get_system_prompt = lambda: ""
    loop._prepare_analysis_turn = lambda _user_input: setattr(loop, "_last_turn_intent", _intent()) or []
    loop._maybe_auto_suspend_for_required_question = lambda: None
    loop._runtime_confirmation_checkpoint = lambda: None
    loop._maybe_inject_synthesis_policy = lambda _user_input: None
    loop._should_continue_for_analysis_quality = lambda *_args: False
    loop._maybe_archive = lambda *_args: None
    loop._auto_save = lambda: None
    loop.context.analysis_state = _state()
    monkeypatch.setattr(
        loop,
        "_gate_final_analysis_answer",
        lambda *_args, **_kwargs: {"action": "publish", "text": "AUDITED PUBLIC"},
    )

    events = list(loop.stream_turn("analyze"))
    text = "".join(event.get("text", "") for event in events if event["type"] == "text_delta")

    assert text == "AUDITED PUBLIC"
    assert "UNAUDITED RAW" not in text


def test_streaming_length_truncation_gets_one_complete_revision_before_audit(monkeypatch):
    class Client:
        max_tokens = 8_000

        def __init__(self):
            self.round = 0
            self.system_prompts = []

        def stream_chat_structured(self, **kwargs):
            self.round += 1
            self.system_prompts.append(kwargs.get("system", ""))
            if self.round == 1:
                yield StreamTextDelta("TRUNCATED DRAFT")
                yield StreamComplete(Response(
                    text="TRUNCATED DRAFT",
                    finish_reason="length",
                ))
                return
            complete = "发现：收入存在分群差异。\n建议：验证定价策略。\n局限：仅为描述性分析。"
            yield StreamTextDelta(complete)
            yield StreamComplete(Response(text=complete, finish_reason="stop"))

    client = Client()
    loop = AgentLoop(client=client, session_id="publish_gate_truncation")
    loop._get_system_prompt = lambda: getattr(loop, "_turn_final_audit_instruction", "")
    loop._prepare_analysis_turn = lambda _user_input: setattr(
        loop,
        "_last_turn_intent",
        _intent("comprehensive_report"),
    ) or []
    loop._maybe_auto_suspend_for_required_question = lambda: None
    loop._runtime_confirmation_checkpoint = lambda: None
    loop._maybe_inject_synthesis_policy = lambda _user_input: None
    loop._should_continue_for_analysis_quality = lambda *_args: False
    loop._maybe_archive = lambda *_args: None
    loop._auto_save = lambda: None
    loop.context.analysis_state = _state()
    loop.context.turn_state = TurnExecutionState(ToolExecutionBudget(
        token_budget=40_000,
        synthesis_reserve_tokens=8_000,
        audit_reserve_tokens=4_000,
        revision_reserve_tokens=8_000,
    ))
    audited = []

    def publish(_user_input, text, **_kwargs):
        audited.append(text)
        loop._turn_final_audit_instruction = ""
        return {"action": "publish", "text": "AUDITED COMPLETE"}

    monkeypatch.setattr(loop, "_gate_final_analysis_answer", publish)

    events = list(loop.stream_turn("analyze comprehensively"))
    text = "".join(
        event.get("text", "")
        for event in events
        if event["type"] == "text_delta"
    )

    assert client.round == 2
    assert "provider_output_truncated" in client.system_prompts[-1]
    assert audited == ["发现：收入存在分群差异。\n建议：验证定价策略。\n局限：仅为描述性分析。"]
    assert text == "AUDITED COMPLETE"
    assert "TRUNCATED DRAFT" not in text


def test_quality_continuation_reclassifies_discarded_synthesis_budget(monkeypatch):
    class Client:
        max_tokens = 8_000

        def __init__(self):
            self.round = 0
            self.output_limits = []

        def stream_chat_structured(self, **kwargs):
            self.round += 1
            self.output_limits.append(kwargs.get("max_tokens"))
            if self.round == 1:
                draft = "正在继续分析。" * 200
                yield StreamTextDelta(draft)
                yield StreamComplete(Response(text=draft, finish_reason="stop"))
                return
            complete = "发现：收入存在分群差异。\n建议：验证定价策略。\n局限：仅为描述性分析。"
            yield StreamTextDelta(complete)
            yield StreamComplete(Response(text=complete, finish_reason="stop"))

    client = Client()
    loop = AgentLoop(client=client, session_id="publish_gate_quality_budget")

    def prepare(_user_input):
        loop._last_turn_intent = _intent("comprehensive_report")
        loop._turn_synthesis_policy_instruction = "synthesize"
        return []

    loop._prepare_analysis_turn = prepare
    loop._get_system_prompt = lambda: loop._turn_synthesis_policy_instruction
    loop._maybe_auto_suspend_for_required_question = lambda: None
    loop._runtime_confirmation_checkpoint = lambda: None
    loop._maybe_inject_synthesis_policy = lambda _user_input: None
    continuation_calls = 0

    def continue_once(*_args):
        nonlocal continuation_calls
        continuation_calls += 1
        return continuation_calls == 1

    loop._should_continue_for_analysis_quality = continue_once
    loop._maybe_archive = lambda *_args: None
    loop._auto_save = lambda: None
    loop.context.analysis_state = _state()
    loop.context.turn_state = TurnExecutionState(ToolExecutionBudget(
        token_budget=40_000,
        synthesis_reserve_tokens=8_000,
        audit_reserve_tokens=4_000,
        revision_reserve_tokens=8_000,
    ))
    monkeypatch.setattr(
        loop,
        "_gate_final_analysis_answer",
        lambda _user_input, text, **_kwargs: {"action": "publish", "text": text},
    )

    events = list(loop.stream_turn("analyze comprehensively"))
    text = "".join(event.get("text", "") for event in events if event["type"] == "text_delta")

    assert client.output_limits == [8_000, 8_000]
    assert "发现：收入存在分群差异" in text
    diagnostics = loop.context.analysis_state.turn_diagnostics
    assert any(item.get("event") == "discarded_candidate_budget_reclassified" for item in diagnostics)


def test_structured_quality_continuation_reclassifies_discarded_synthesis_budget(monkeypatch):
    class Client:
        max_tokens = 8_000

        def __init__(self):
            self.round = 0
            self.output_limits = []

        def chat(self, **kwargs):
            self.round += 1
            self.output_limits.append(kwargs.get("max_tokens"))
            if self.round == 1:
                return Response(text="正在继续分析。" * 200, finish_reason="stop")
            return Response(
                text="发现：收入存在分群差异。\n建议：验证定价策略。\n局限：仅为描述性分析。",
                finish_reason="stop",
            )

    client = Client()
    loop = AgentLoop(client=client, session_id="publish_gate_quality_budget_sync")

    def prepare(_user_input):
        loop._last_turn_intent = _intent("comprehensive_report")
        loop._turn_synthesis_policy_instruction = "synthesize"
        return []

    loop._prepare_analysis_turn = prepare
    loop._get_system_prompt = lambda: loop._turn_synthesis_policy_instruction
    loop._maybe_auto_suspend_for_required_question = lambda: None
    loop._runtime_confirmation_checkpoint = lambda: None
    loop._maybe_inject_synthesis_policy = lambda _user_input: None
    continuation_calls = 0

    def continue_once(*_args):
        nonlocal continuation_calls
        continuation_calls += 1
        return continuation_calls == 1

    loop._should_continue_for_analysis_quality = continue_once
    loop._maybe_archive = lambda *_args: None
    loop._auto_save = lambda: None
    loop.context.analysis_state = _state()
    loop.context.turn_state = TurnExecutionState(ToolExecutionBudget(
        token_budget=40_000,
        synthesis_reserve_tokens=8_000,
        audit_reserve_tokens=4_000,
        revision_reserve_tokens=8_000,
    ))
    monkeypatch.setattr(
        loop,
        "_gate_final_analysis_answer",
        lambda _user_input, text, **_kwargs: {"action": "publish", "text": text},
    )

    result = loop.run_turn_structured("analyze comprehensively")

    assert result.content.startswith("发现：收入存在分群差异")
    assert client.output_limits == [8_000, 8_000]
    assert any(
        item.get("event") == "discarded_candidate_budget_reclassified"
        for item in loop.context.analysis_state.turn_diagnostics
    )


def test_short_truncation_revision_falls_back_to_better_original_candidate(monkeypatch):
    original = (
        "发现：收入在客户分群之间存在明显差异。" * 20
        + "\n建议：优先验证分群定价和渠道策略。" * 12
        + "\n局限：当前结果是描述性关联，不能解释为因果关系。" * 12
    )

    class Client:
        max_tokens = 8_000

        def __init__(self):
            self.round = 0

        def stream_chat_structured(self, **_kwargs):
            self.round += 1
            if self.round == 1:
                yield StreamTextDelta(original)
                yield StreamComplete(Response(text=original, finish_reason="length"))
                return
            short = "图表已生成。"
            yield StreamTextDelta(short)
            yield StreamComplete(Response(text=short, finish_reason="stop"))

    client = Client()
    loop = AgentLoop(client=client, session_id="publish_gate_best_candidate")
    loop._get_system_prompt = lambda: getattr(loop, "_turn_final_audit_instruction", "")
    loop._prepare_analysis_turn = lambda _user_input: setattr(
        loop,
        "_last_turn_intent",
        _intent("comprehensive_report"),
    ) or []
    loop._maybe_auto_suspend_for_required_question = lambda: None
    loop._runtime_confirmation_checkpoint = lambda: None
    loop._maybe_inject_synthesis_policy = lambda _user_input: None
    loop._should_continue_for_analysis_quality = lambda *_args: False
    loop._maybe_archive = lambda *_args: None
    loop._auto_save = lambda: None
    loop.context.analysis_state = _state()
    loop.context.turn_state = TurnExecutionState(ToolExecutionBudget(
        token_budget=40_000,
        synthesis_reserve_tokens=8_000,
        audit_reserve_tokens=4_000,
        revision_reserve_tokens=8_000,
    ))
    captured = {}
    ref = {
        "contract_version": "final_answer_audit.v1",
        "id": "audit_best_candidate",
        "status": "pass",
        "artifact_path": "fixture.json",
        "artifact_digest": "0" * 64,
    }

    def audit_draft(text, *_args, **_kwargs):
        captured["text"] = text
        return ref

    monkeypatch.setattr(runtime, "audit_final_answer_draft", audit_draft)
    monkeypatch.setattr(
        runtime,
        "hydrate_final_answer_audit_ref",
        lambda _ref: _audit("pass", public_text=captured["text"]),
    )

    events = list(loop.stream_turn("analyze comprehensively"))
    text = "".join(event.get("text", "") for event in events if event["type"] == "text_delta")

    assert client.round == 2
    assert captured["text"] == original
    assert text == original
    assert "图表已生成" not in text
    assert any(
        item.get("event") == "final_answer_candidate_fallback"
        for item in loop.context.analysis_state.turn_diagnostics
    )


def test_streaming_result_followup_hides_tool_call_claims_until_terminal_audit(monkeypatch):
    class Client:
        def __init__(self):
            self.round = 0

        def stream_chat_structured(self, **_kwargs):
            self.round += 1
            if self.round == 1:
                yield StreamTextDelta("UNAUDITED INTERMEDIATE CLAIM")
                yield StreamComplete(Response(
                    text="UNAUDITED INTERMEDIATE CLAIM",
                    tool_calls=[
                        ToolCall(id="lookup", name="describe_dataset", arguments={"name": "sales"}),
                    ],
                ))
                return
            yield StreamTextDelta("UNAUDITED FOLLOWUP ANSWER")
            yield StreamComplete(Response(text="UNAUDITED FOLLOWUP ANSWER"))

    loop = AgentLoop(client=Client(), session_id="publish_gate_followup")
    loop._get_system_prompt = lambda: ""
    loop._prepare_analysis_turn = lambda _user_input: setattr(
        loop,
        "_last_turn_intent",
        _intent("result_followup"),
    ) or []
    loop._maybe_auto_suspend_for_required_question = lambda: None
    loop._runtime_confirmation_checkpoint = lambda: None
    loop._maybe_inject_synthesis_policy = lambda _user_input: None
    loop._should_continue_for_analysis_quality = lambda *_args: False
    loop._process_tool_calls = lambda *_args, **_kwargs: iter(())
    loop._maybe_archive = lambda *_args: None
    loop._auto_save = lambda: None
    loop.context.analysis_state = _state()
    monkeypatch.setattr(
        loop,
        "_gate_final_analysis_answer",
        lambda *_args, **_kwargs: {"action": "publish", "text": "AUDITED FOLLOWUP"},
    )

    events = list(loop.stream_turn("why did the metric change?"))
    text = "".join(event.get("text", "") for event in events if event["type"] == "text_delta")

    assert text == "AUDITED FOLLOWUP"
    assert "UNAUDITED INTERMEDIATE CLAIM" not in text
    assert "UNAUDITED FOLLOWUP ANSWER" not in text
