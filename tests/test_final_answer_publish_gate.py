from types import SimpleNamespace

import pytest

from data_agent.agent.execution_control import ToolExecutionBudget, TurnExecutionState
from data_agent.agent.loop import AgentLoop
from data_agent.agent import trust_workflow_runtime as runtime
from data_agent.llm.client import Response, StreamComplete, StreamTextDelta, ToolCall


def _intent(intent_type="directed_analysis"):
    return SimpleNamespace(intent_type=intent_type, execution_readiness="ready")


def _state(*, evidence=True):
    return SimpleNamespace(
        evidence_records=[{"id": "ev_1"}] if evidence else [],
        verification_reports=[],
    )


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


def test_internal_evidence_markers_are_stripped_from_intermediate_analysis_text():
    loop = _analysis_loop()

    public = loop._public_intermediate_text("Working [[evidence:ev_1]] on the next step.")

    assert public == "Working on the next step."


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
    assert "Revenue increased 12%" not in result["text"]
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
    # that destroyed useful structure. The new renderer publishes the audit's
    # public_text with downgraded claims kept (no whole-answer wipe), and
    # strips internal evidence markers.
    assert second["action"] == "fallback"
    assert "Audited result" in second["text"]
    assert "could not be published" not in second["text"]
    assert "[[evidence:" not in second["text"]
    assert loop._turn_final_audit_instruction == ""


def test_measurement_identity_missing_gets_at_most_one_synthesis_only_revision(
    monkeypatch,
):
    loop = _analysis_loop()
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


@pytest.mark.parametrize(
    ("reason_code", "expected_action"),
    [
        ("measurement_marker_invalid", "continue"),
        ("measurement_not_found", "fallback"),
        ("measurement_metric_mismatch", "fallback"),
        ("measurement_claim_key_mismatch", "fallback"),
        ("measurement_scope_mismatch", "fallback"),
        ("measurement_dataset_version_mismatch", "fallback"),
        ("measurement_ambiguous", "fallback"),
    ],
)
def test_measurement_bookkeeping_never_requests_analysis_retry(
    monkeypatch,
    reason_code,
    expected_action,
):
    loop = _analysis_loop()
    _patch_runtime_audit(
        monkeypatch,
        _audit("blocked", reason_codes=[reason_code]),
    )

    result = loop._gate_final_analysis_answer("analyze", "Measured result.")

    assert result["action"] == expected_action
    assert result.get("mode") != "analysis"
    assert loop._turn_final_audit_analysis_retry_used is False
    assert 'mode="analysis"' not in loop._turn_final_audit_instruction


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
    loop.client = SimpleNamespace(chat=lambda **_kwargs: Response(tool_calls=[
        ToolCall(id="forbidden", name="run_python", arguments={"code": "print(1)"}),
    ]))
    loop._get_system_prompt = lambda: ""
    loop._runtime_confirmation_checkpoint = lambda: None

    result = loop._loop_impl("analyze")

    # The tool call is rejected and the audit's public_text is published via
    # claim-tier rendering. The legacy English "could not be published" wording
    # is gone — that is the regression we are guarding against.
    assert "Audited result" in result.content
    assert "could not be published" not in result.content
    assert not any(message.get("tool_calls") for message in loop.messages)
    assert loop._turn_final_audit_instruction == ""


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
