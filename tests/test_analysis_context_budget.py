import json
from types import SimpleNamespace

import pandas as pd

from data_agent.agent.analysis_state import (
    AnalysisSessionState,
    build_trust_capsule,
    load_analysis_state,
    render_trust_capsule,
)
from data_agent.agent.compact import CompactState, compact_history
from data_agent.agent.execution_control import ToolExecutionBudget, TurnExecutionState
from data_agent.agent.execution_control import BudgetExceeded
from data_agent.agent.loop import AgentLoop


class _SummaryClient:
    def __init__(self):
        self.calls = 0

    def chat(self, **_kwargs):
        self.calls += 1
        return type("Response", (), {"text": "verbose summary " * 2_000})()


def _assurance_state() -> AnalysisSessionState:
    state = AnalysisSessionState(
        session_id="budget_assurance",
        goal="Compare revenue without overstating causality",
        data_state="data_loaded",
        explicit_user_requirements="Show calculations and disclose statistical limits.",
    )
    state.set_analysis_plan({
        "id": "plan_budget_v1",
        "goal": state.goal,
        "method_plan": [{
            "step_id": "step_compare",
            "goal": "compare revenue",
            "evidence_requirements": ["confidence_interval", "limitations"],
        }],
    })
    state.data_pool = [{
        "dataset": "orders",
        "dataset_version_id": "dataset_orders_v3",
        "raw_fingerprint": "raw_orders_sha256",
        "source_fingerprint": "source_orders_sha256",
    }]
    state.computation_refs = [{
        "id": "comp_compare",
        "output_digest": "computation_output_sha256",
        "dataset_versions": ["dataset_orders_v3"],
    }]
    state.evidence_records = [{
        "id": "ev_revenue_compare",
        "contract_version": "evidence_record.v2",
        "verification_level": "computed_descriptive",
        "computation_refs": [{
            "id": "comp_compare",
            "output_digest": "computation_output_sha256",
        }],
    }]
    state.pending_confirmations = [{
        "id": "confirm_transform",
        "confirmation_id": "confirm_transform",
        "version": 4,
        "status": "pending",
        "proposal_ref": {
            "proposal_id": "proposal_clean_v2",
            "candidate_fingerprint": "candidate_clean_sha256",
        },
    }]
    state.verification_reports = [{
        "id": "final_audit_previous",
        "contract_version": "final_answer_audit.v1",
        "status": "blocked",
        "claim_checks": [{
            "status": "failed",
            "reason_codes": ["missing_confidence_interval"],
            "safe_action": {"action": "remove_or_downgrade_claim"},
        }],
    }]
    return state


def test_component_prompt_accounting_keeps_assurance_reserves_separate():
    turn = TurnExecutionState(ToolExecutionBudget(
        token_budget=1_000,
        synthesis_reserve_tokens=180,
        audit_reserve_tokens=120,
        revision_reserve_tokens=100,
    ))

    turn.record_prompt_assembly(
        {
            "system_rules": "r" * 400,
            "conversation_history": "h" * 800,
            "trust_capsule": "t" * 200,
        },
        assembled_payload="p" * 1_600,
        trust_capsule_digest="capsule_digest",
        phase="exploration",
    )
    turn.record_token_usage(600, phase="exploration")

    diagnostics = turn.budget_diagnostics()
    assert turn.exploration_token_budget == 600
    assert turn.exploration_budget_exhausted is True
    assert turn.can_run_phase("synthesis") is True
    assert turn.can_run_phase("audit") is True
    assert turn.can_run_phase("revision") is True
    assert diagnostics["approximate_prompt_tokens"] == 400
    assert diagnostics["approximate_prompt_component_tokens"]["trust_capsule"] == 50
    assert diagnostics["approximate_runtime_tokens_used"] == 600
    assert diagnostics["trust_capsule_digest"] == "capsule_digest"
    assert diagnostics["phase_prompt_tokens"]["exploration"] == 400
    assert "provider_billed" not in diagnostics


def test_phase_accounting_caps_exploration_without_consuming_reserves():
    turn = TurnExecutionState(ToolExecutionBudget(
        token_budget=1_000,
        synthesis_reserve_tokens=180,
        audit_reserve_tokens=120,
        revision_reserve_tokens=100,
    ))

    turn.record_token_usage(10_000, phase="exploration")

    assert turn.phase_token_usage["exploration"] == 600
    assert turn.phase_overflow_tokens["exploration"] == 9_400
    assert turn.can_run_phase("synthesis") is True
    assert turn.can_run_phase("audit") is True
    turn.record_token_usage(80, phase="synthesis")
    turn.record_token_usage(1, phase="audit")
    assert turn.phase_token_usage["synthesis"] == 80
    assert turn.phase_token_usage["audit"] == 1
    try:
        turn.ensure_can_call("generate_report", {})
    except BudgetExceeded as exc:
        assert "exploration" in str(exc).lower()
    else:
        raise AssertionError("non-assurance meta work must not bypass exhausted exploration")
    turn.ensure_can_call("record_evidence_record", {})


def test_llm_output_limit_is_the_remaining_phase_capacity(tmp_path, monkeypatch):
    from data_agent.config import get_config

    class _LimitClient:
        max_tokens = 8_000

        def chat(self, **_kwargs):
            return SimpleNamespace(text="bounded")

    monkeypatch.setattr(get_config(), "sessions_dir", tmp_path / "sessions")
    loop = AgentLoop(client=_LimitClient(), session_id="output_limit")
    turn = TurnExecutionState(ToolExecutionBudget(
        token_budget=1_000,
        synthesis_reserve_tokens=180,
        audit_reserve_tokens=120,
        revision_reserve_tokens=100,
    ))
    loop.context.turn_state = turn
    turn.record_token_usage(turn.exploration_token_budget - 1, phase="exploration")

    kwargs = loop._llm_output_limit_kwargs(loop.client.chat, phase="exploration")

    assert kwargs == {"max_tokens": 1}
    assert turn.budget_diagnostics()["requested_max_output_tokens"]["exploration"] == 1


def test_nearly_empty_exploration_switches_to_reserved_synthesis_before_draft(
    tmp_path,
    monkeypatch,
):
    from data_agent.config import get_config
    from data_agent.llm.client import Response

    class _FinalClient:
        max_tokens = 8_000

        def __init__(self):
            self.output_limits = []

        def chat(self, **kwargs):
            self.output_limits.append(kwargs["max_tokens"])
            return Response(text="bounded candidate")

    monkeypatch.setattr(get_config(), "sessions_dir", tmp_path / "sessions")
    client = _FinalClient()
    loop = AgentLoop(client=client, session_id="reserved_synthesis")
    loop.context.analysis_state = _assurance_state()
    loop._last_turn_intent = SimpleNamespace(
        intent_type="directed_analysis",
        execution_readiness="ready",
    )
    turn = TurnExecutionState(ToolExecutionBudget(
        token_budget=1_000,
        synthesis_reserve_tokens=180,
        audit_reserve_tokens=120,
        revision_reserve_tokens=100,
    ))
    loop.context.turn_state = turn
    turn.record_token_usage(turn.exploration_token_budget - 1, phase="exploration")
    loop._maybe_inject_synthesis_policy = lambda _user_input: setattr(
        loop,
        "_turn_synthesis_policy_instruction",
        "<synthesis_policy>use current evidence</synthesis_policy>",
    )
    loop._ensure_mcp_initialized = lambda: None
    loop._runtime_confirmation_checkpoint = lambda: None
    loop._get_system_prompt = lambda: ""
    loop._should_continue_for_analysis_quality = lambda *_args: False
    loop._gate_final_analysis_answer = lambda *_args, **_kwargs: {
        "action": "publish",
        "text": "bounded candidate",
    }

    result = loop._loop_impl("analyze")

    assert result.content == "bounded candidate"
    assert loop._current_prompt_phase() == "synthesis"
    assert client.output_limits == [180]
    assert turn.phase_token_usage["exploration"] == turn.exploration_token_budget - 1
    assert turn.phase_token_usage["synthesis"] > 0


def test_llm_client_forwards_the_bounded_output_limit_to_provider(monkeypatch):
    from data_agent.llm import client as client_module

    captured = {}

    def fake_completion(**kwargs):
        captured.update(kwargs)
        message = SimpleNamespace(content="bounded", tool_calls=None, reasoning_content="")
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message, finish_reason="stop")]
        )

    monkeypatch.setattr(client_module, "completion", fake_completion)
    client = client_module.LLMClient(model_id="test/model", max_tokens=100)

    response = client.chat(
        messages=[{"role": "user", "content": "analyze"}],
        max_tokens=7,
    )

    assert response.text == "bounded"
    assert captured["max_tokens"] == 7


def test_stream_fallback_uses_only_the_phase_capacity_left_after_partial_output():
    from data_agent.llm.client import Response, StreamTextDelta

    class _FailingStreamClient:
        max_tokens = 100

        def __init__(self):
            self.stream_limits = []
            self.fallback_limits = []

        def stream_chat_structured(self, **kwargs):
            self.stream_limits.append(kwargs["max_tokens"])
            yield StreamTextDelta("partial-stream-output-" * 3)
            error = RuntimeError("stream disconnected")
            error.unreported_output_tokens = 0
            raise error

        def chat(self, **kwargs):
            self.fallback_limits.append(kwargs["max_tokens"])
            return Response(text="bounded fallback")

    client = _FailingStreamClient()
    loop = AgentLoop(client=client, session_id="aggregate_stream_budget")
    turn = TurnExecutionState(ToolExecutionBudget(
        token_budget=100,
        synthesis_reserve_tokens=50,
        audit_reserve_tokens=25,
        revision_reserve_tokens=25,
    ))
    loop.context.turn_state = turn
    loop._turn_synthesis_policy_instruction = "<synthesis_policy>bounded</synthesis_policy>"
    loop._get_system_prompt = lambda: ""

    events = list(loop._stream_llm_round(1))

    assert events[-1]["type"] == "_response"
    assert client.stream_limits == [50]
    assert 0 < client.fallback_limits[0] < client.stream_limits[0]
    assert turn.phase_token_usage["synthesis"] <= 50
    assert turn.phase_overflow_tokens.get("synthesis", 0) == 0


def test_unknown_hidden_stream_usage_fails_closed_before_sync_fallback():
    class _UnknownHiddenFailureClient:
        max_tokens = 100

        def __init__(self):
            self.fallback_calls = 0

        def stream_chat_structured(self, **_kwargs):
            if False:
                yield None
            raise RuntimeError("provider failed after hidden output")

        def chat(self, **_kwargs):
            self.fallback_calls += 1
            raise AssertionError("fallback must not reuse an unknown stream reserve")

    client = _UnknownHiddenFailureClient()
    loop = AgentLoop(client=client, session_id="unknown_hidden_stream_budget")
    turn = TurnExecutionState(ToolExecutionBudget(
        token_budget=100,
        synthesis_reserve_tokens=50,
        audit_reserve_tokens=25,
        revision_reserve_tokens=25,
    ))
    loop.context.turn_state = turn
    loop._turn_synthesis_policy_instruction = "<synthesis_policy>bounded</synthesis_policy>"
    loop._get_system_prompt = lambda: ""

    events = list(loop._stream_llm_round(1))

    assert events[-1] == {"type": "_response", "response": None, "streamed_text": ""}
    assert client.fallback_calls == 0
    assert turn.phase_token_usage["synthesis"] == 50


def test_llm_stream_retry_reduces_the_provider_limit_by_emitted_output(monkeypatch):
    import litellm
    from data_agent.llm import client as client_module

    limits = []

    def chunk(text):
        delta = SimpleNamespace(content=text, reasoning_content=None, tool_calls=None)
        return SimpleNamespace(choices=[SimpleNamespace(delta=delta)])

    def fake_completion(**kwargs):
        limits.append(kwargs["max_tokens"])

        def stream():
            yield chunk("x" * 20)
            if len(limits) == 1:
                raise litellm.APIConnectionError(
                    message="disconnected",
                    llm_provider="test",
                    model="test/model",
                )

        return stream()

    monkeypatch.setattr(client_module, "completion", fake_completion)
    client = client_module.LLMClient(model_id="test/model", max_tokens=100)
    client._MAX_RETRIES = 1
    client._RETRY_BASE_DELAY = 0

    events = list(client.stream_chat_structured(messages=[], max_tokens=20))

    assert limits == [20, 15]
    assert events[-1].response.text == "x" * 20
    assert events[-1].response.unreported_output_tokens == 0


def test_successful_stream_retry_charges_prior_hidden_usage_to_turn(monkeypatch):
    import litellm
    from data_agent.llm import client as client_module

    limits = []

    def fake_completion(**kwargs):
        limits.append(kwargs["max_tokens"])

        def stream():
            if len(limits) == 1:
                delta = SimpleNamespace(
                    content=None,
                    reasoning_content="r" * 40,
                    tool_calls=None,
                )
                yield SimpleNamespace(choices=[SimpleNamespace(delta=delta)])
                raise litellm.APIConnectionError(
                    message="disconnected",
                    llm_provider="test",
                    model="test/model",
                )
            delta = SimpleNamespace(
                content="x" * 20,
                reasoning_content=None,
                tool_calls=None,
            )
            yield SimpleNamespace(choices=[SimpleNamespace(delta=delta)])

        return stream()

    monkeypatch.setattr(client_module, "completion", fake_completion)
    client = client_module.LLMClient(model_id="test/model", max_tokens=100)
    client._MAX_RETRIES = 1
    client._RETRY_BASE_DELAY = 0
    loop = AgentLoop(client=client, session_id="successful_hidden_retry")
    turn = TurnExecutionState(ToolExecutionBudget(
        token_budget=40,
        synthesis_reserve_tokens=20,
        audit_reserve_tokens=10,
        revision_reserve_tokens=10,
    ))
    loop.context.turn_state = turn
    loop._turn_synthesis_policy_instruction = "<synthesis_policy>bounded</synthesis_policy>"
    loop._get_system_prompt = lambda: ""

    events = list(loop._stream_llm_round(1))

    assert limits == [20, 10]
    assert events[-1]["response"].unreported_output_tokens == 10
    assert turn.phase_token_usage["synthesis"] >= 15
    assert turn.remaining_phase_tokens("synthesis") <= 5


def test_llm_stream_failure_reports_hidden_reasoning_usage(monkeypatch):
    import litellm
    from data_agent.llm import client as client_module

    limits = []

    def fake_completion(**kwargs):
        limits.append(kwargs["max_tokens"])

        def stream():
            delta = SimpleNamespace(
                content=None,
                reasoning_content="r" * 40,
                tool_calls=None,
            )
            yield SimpleNamespace(choices=[SimpleNamespace(delta=delta)])
            raise litellm.APIConnectionError(
                message="disconnected",
                llm_provider="test",
                model="test/model",
            )

        return stream()

    monkeypatch.setattr(client_module, "completion", fake_completion)
    client = client_module.LLMClient(model_id="test/model", max_tokens=100)
    client._MAX_RETRIES = 1
    client._RETRY_BASE_DELAY = 0

    try:
        list(client.stream_chat_structured(messages=[], max_tokens=20))
    except litellm.APIConnectionError as exc:
        assert exc.unreported_output_tokens == 20
    else:
        raise AssertionError("hidden-output exhaustion must surface the stream failure")

    assert limits == [20, 10]


def test_trust_capsule_is_deterministic_bounded_and_survives_state_restore():
    state = _assurance_state()

    first = build_trust_capsule(state, max_chars=4_000)
    restored = AnalysisSessionState.from_dict(state.to_dict(), state.session_id)
    second = build_trust_capsule(restored, max_chars=4_000)

    assert first == second
    assert len(render_trust_capsule(first)) <= 4_000
    assert first["goal"] == state.goal
    assert first["explicit_user_requirements"] == state.explicit_user_requirements
    assert first["plan"] == {"id": "plan_budget_v1", "contract_version": "analysis_plan.v1"}
    assert first["datasets"] == [{
        "name": "orders",
        "version_ids": ["dataset_orders_v3"],
        "raw_fingerprint": "raw_orders_sha256",
        "source_fingerprint": "source_orders_sha256",
    }]
    assert first["unresolved_hard_requirements"] == [{
        "id": "req_step_compare_confidence_interval",
        "unmet_action": "block_claim",
    }]
    assert first["evidence_bindings"] == [{
        "id": "ev_revenue_compare",
        "verification_level": "computed_descriptive",
        "computation_ref_digests": ["computation_output_sha256"],
    }]
    assert first["active_confirmation"]["id"] == "confirm_transform"
    assert first["active_confirmation"]["version"] == 4
    assert first["active_confirmation"]["proposal_id"] == "proposal_clean_v2"
    assert first["latest_audit"]["id"] == "final_audit_previous"
    assert first["latest_audit"]["blockers"] == ["missing_confidence_interval"]
    assert first["latest_audit"]["permitted_downgrade_actions"] == [
        {"action": "remove_or_downgrade_claim"}
    ]
    assert len(first["digest"]) == 64

    checkpoint_capsule = build_trust_capsule(
        restored,
        active_confirmation={
            "confirmation_id": "confirm_from_durable_store",
            "version": 7,
            "proposal_ref": {
                "proposal_id": "proposal_from_durable_store",
                "candidate_fingerprint": "candidate_from_durable_store",
            },
        },
    )
    assert checkpoint_capsule["active_confirmation"]["id"] == "confirm_from_durable_store"
    assert checkpoint_capsule["active_confirmation"]["version"] == 7
    assert checkpoint_capsule["active_confirmation"]["proposal_id"] == (
        "proposal_from_durable_store"
    )


def test_capsule_overflow_is_strictly_bounded_and_manifest_hydrates_requested_ids(
    tmp_path,
    monkeypatch,
):
    from data_agent.agent.artifact_refs import hydrate_trust_capsule_manifest
    from data_agent.config import get_config

    monkeypatch.setattr(get_config(), "sessions_dir", tmp_path / "sessions")
    state = _assurance_state()
    state.analysis_plan["analysis_requirements"]["step_compare"] = [
        {
            "id": f"req_hard_{index:02d}",
            "necessity": "required",
            "status": "pending",
            "unmet_action": "block_claim",
        }
        for index in range(30)
    ]
    state.evidence_records = [
        {
            "id": f"ev_material_{index:02d}",
            "verification_level": "computed_descriptive",
            "computation_refs": [{"output_digest": f"sha256:{index:064d}"}],
        }
        for index in range(30)
    ]
    state.pending_confirmations[-1]["proposal_ref"] = {
        "proposal_id": "proposal_" + ("p" * 1_500),
        "candidate_fingerprint": "candidate_" + ("c" * 1_500),
        "data_version": "data_" + ("d" * 1_500),
        "spec_version": "spec_" + ("s" * 1_500),
    }

    capsule = build_trust_capsule(state, max_items_per_component=8, max_chars=2_000)

    assert len(render_trust_capsule(capsule)) <= 2_000
    assert capsule["status"] == "requires_hydration"
    assert capsule["required_action"] == "hydrate_or_downgrade"
    assert capsule["active_confirmation"]["id"] == "confirm_transform"
    assert capsule["active_confirmation"]["version"] == 4
    assert capsule["active_confirmation"]["proposal_id"].startswith("sha256:")
    assert capsule["active_confirmation"]["candidate_fingerprint"].startswith("sha256:")
    manifest_ref = capsule["trust_manifest"]
    hydrated = hydrate_trust_capsule_manifest(
        manifest_ref,
        expected_session_id=state.session_id,
        expected_plan_id="plan_budget_v1",
        expected_body_digest=manifest_ref["body_digest"],
        requested_ids={
            "unresolved_hard_requirements": [f"req_hard_{index:02d}" for index in range(30)],
            "evidence_bindings": [f"ev_material_{index:02d}" for index in range(30)],
        },
        per_component_limit=30,
        include_confirmation=True,
    )
    assert {item["id"] for item in hydrated["unresolved_hard_requirements"]} == {
        f"req_hard_{index:02d}" for index in range(30)
    }
    assert {item["id"] for item in hydrated["evidence_bindings"]} == {
        f"ev_material_{index:02d}" for index in range(30)
    }
    assert hydrated["active_confirmation"]["candidate_fingerprint"].endswith("c" * 1_500)
    assert hydrate_trust_capsule_manifest(
        manifest_ref,
        expected_session_id="wrong_session",
        expected_plan_id="plan_budget_v1",
        expected_body_digest=manifest_ref["body_digest"],
        requested_ids={"evidence_bindings": ["ev_material_00"]},
    ) == {}

    loop = AgentLoop(client=_SummaryClient(), session_id=state.session_id)
    loop.context.analysis_state = state
    hydrated_prompt = json.loads(loop._hydrate_overflow_trust_context(capsule))
    assert hydrated_prompt["status"] == "hydrated_with_limits"
    assert hydrated_prompt["active_confirmation"]["id"] == "confirm_transform"
    assert hydrated_prompt["active_confirmation"]["version"] == 4
    assert hydrated_prompt["active_confirmation"]["proposal_id"].startswith("sha256:")
    assert [item["id"] for item in hydrated_prompt["evidence_bindings"]] == [
        f"ev_material_{index:02d}" for index in range(8)
    ]
    assert hydrated_prompt["omitted_counts"]["evidence_bindings"] == 22


def test_forced_compaction_embeds_capsule_outside_untrusted_llm_summary(tmp_path, monkeypatch):
    from data_agent.config import get_config

    monkeypatch.setattr(get_config(), "sessions_dir", tmp_path / "sessions")
    capsule = build_trust_capsule(_assurance_state(), max_chars=4_000)
    messages = [
        {"role": "user", "content": "original explicit requirement"},
        *[
            {"role": "assistant", "content": f"analysis {index}"}
            for index in range(15)
        ],
    ]
    compact_state = CompactState()

    compacted = compact_history(
        "budget_assurance",
        _SummaryClient(),
        messages,
        compact_state,
        token_threshold=0,
        trust_capsule=capsule,
        summary_max_chars=500,
    )

    compressed = compacted[0]["content"]
    assert len(compact_state.last_summary) == 500
    assert f'digest="{capsule["digest"]}"' in compressed
    assert "req_step_compare_confidence_interval" in compressed
    assert "ev_revenue_compare" in compressed
    assert "confirm_transform" in compressed
    assert compact_state.trust_capsule_digest == capsule["digest"]
    assert json.loads(compact_state.trust_capsule_json)["digest"] == capsule["digest"]


def test_short_history_with_huge_recent_messages_is_bounded_without_repeat_transcript(
    tmp_path,
    monkeypatch,
):
    from data_agent.config import get_config

    monkeypatch.setattr(get_config(), "sessions_dir", tmp_path / "sessions")
    client = _SummaryClient()
    capsule = build_trust_capsule(_assurance_state(), max_chars=2_000)
    messages = [
        {"role": "user", "content": "question " + ("q" * 20_000)},
        {"role": "assistant", "content": "answer " + ("a" * 20_000)},
    ]
    compact_state = CompactState()

    first = compact_history(
        "short_huge",
        client,
        messages,
        compact_state,
        token_threshold=1_000,
        trust_capsule=capsule,
        summary_max_chars=400,
        recent_max_chars=1_200,
    )
    second = compact_history(
        "short_huge",
        client,
        first,
        compact_state,
        token_threshold=1_000,
        trust_capsule=capsule,
        summary_max_chars=400,
        recent_max_chars=1_200,
    )

    assert len(json.dumps(first, ensure_ascii=False)) < 6_000
    assert second == first
    assert compact_state.compaction_count == 1
    assert client.calls == 0
    transcript_dir = tmp_path / "sessions" / "short_huge" / "transcripts"
    assert len(list(transcript_dir.glob("transcript_*.jsonl"))) == 1


def test_recent_bound_covers_reasoning_and_arbitrary_message_fields():
    from data_agent.agent.compact import _bounded_recent_messages

    bounded = _bounded_recent_messages([{
        "role": "assistant",
        "content": "short",
        "reasoning_content": "r" * 50_000,
        "provider_payload": {"hidden": "z" * 50_000},
        "tool_calls": [
            {
                "id": f"call_{index}",
                "type": "function",
                "function": {"name": "preview_data", "arguments": "x" * 5_000},
            }
            for index in range(100)
        ],
    }], max_chars=1_200)

    assert len(json.dumps(bounded, ensure_ascii=False)) <= 1_200
    assert "reasoning_content" not in bounded[0]
    assert "provider_payload" not in bounded[0]


def test_low_budget_reserves_one_revision_and_terminates_predictably():
    turn = TurnExecutionState(ToolExecutionBudget(
        token_budget=500,
        synthesis_reserve_tokens=100,
        audit_reserve_tokens=75,
        revision_reserve_tokens=75,
    ))
    turn.record_token_usage(250, phase="exploration")

    assert turn.exploration_budget_exhausted is True
    assert turn.claim_revision_attempt() is True
    assert turn.claim_revision_attempt() is False
    assert turn.can_run_phase("audit") is True


def test_loop_measures_assembled_prompt_and_compacts_with_current_capsule(tmp_path, monkeypatch):
    from data_agent.config import get_config

    monkeypatch.setattr(get_config(), "sessions_dir", tmp_path / "sessions")
    client = _SummaryClient()
    loop = AgentLoop(client=client, session_id="loop_budget_assurance")
    loop.context.analysis_state = _assurance_state()
    loop.context.user_quality_requirements = "Show calculations and limits."
    loop.context.turn_state = TurnExecutionState(ToolExecutionBudget(
        token_budget=1_000,
        synthesis_reserve_tokens=180,
        audit_reserve_tokens=120,
        revision_reserve_tokens=100,
    ))
    loop.messages = [
        {"role": "user", "content": "analyze " + ("x" * 400)},
        *[
            {"role": "assistant", "content": f"round {index} " + ("y" * 400)}
            for index in range(15)
        ],
    ]

    loop._compact_context_if_needed()
    loop._compact_context_if_needed()
    loop._compact_context_if_needed()

    assert loop._compact_state.trust_capsule_digest
    assert loop._compact_state.compaction_count == 1
    assert client.calls == 1
    assert "ev_revenue_compare" in loop.messages[0]["content"]
    assert len(loop.context.analysis_state.evidence_records) == 1
    transcript_dir = tmp_path / "sessions" / "loop_budget_assurance" / "transcripts"
    assert list(transcript_dir.glob("transcript_*.jsonl"))
    restarted = load_analysis_state("budget_assurance")
    assert restarted.budget_diagnostics["trust_capsule_digest"] == (
        loop._compact_state.trust_capsule_digest
    )

    capsule = build_trust_capsule(loop.context.analysis_state)

    def _fake_build_prompt():
        loop._prompt_component_payloads = {
            "system_rules": "rules",
            "trust_capsule": render_trust_capsule(capsule),
        }
        loop._turn_trust_capsule = capsule
        return "assembled system prompt"

    monkeypatch.setattr(loop, "_build_system_prompt", _fake_build_prompt)
    loop._prompt_cache_dirty = True
    assert "assembled system prompt" in loop._get_system_prompt()
    diagnostics = loop.context.turn_state.budget_diagnostics()
    assert diagnostics["prompt_assembly_count"] == 1
    assert diagnostics["trust_capsule_digest"] == capsule["digest"]
    assert diagnostics["approximate_prompt_component_tokens"]["conversation_history"] > 0


def test_loop_capsule_uses_canonical_workspace_version_and_refreshes_on_trust_change(
    tmp_path,
    monkeypatch,
):
    from data_agent.agent.data_lineage import TransformationRecord, frame_fingerprint
    from data_agent.config import get_config

    monkeypatch.setattr(get_config(), "sessions_dir", tmp_path / "sessions")
    loop = AgentLoop(client=_SummaryClient(), session_id="workspace_capsule")
    frame = pd.DataFrame({"group": ["A", "B"], "revenue": [10.0, 12.0]})
    source_fingerprint = frame_fingerprint(frame)
    raw = loop.context.workspace.register_raw_snapshot("orders", frame, source_fingerprint)
    proposal = TransformationRecord(
        parent_dataset_id=raw["dataset_id"],
        raw_dataset_id=raw["dataset_id"],
        source_fingerprint=source_fingerprint,
        logical_name="orders",
        operations=[],
    ).to_dict()
    active = loop.context.workspace.promote_analysis_copy(
        "orders", frame.copy(), raw["dataset_id"], proposal
    )
    loop.context.analysis_state = AnalysisSessionState(
        session_id="workspace_capsule",
        goal="compare real orders",
    )
    loop.context.turn_state = TurnExecutionState(ToolExecutionBudget(token_budget=10_000))

    active_inputs = loop._active_dataset_capsule_inputs()
    capsule = build_trust_capsule(
        loop.context.analysis_state,
        active_datasets=active_inputs,
    )
    assert capsule["datasets"] == [{
        "name": "orders",
        "version_ids": [active["dataset_id"]],
        "raw_dataset_id": raw["dataset_id"],
        "raw_fingerprint": source_fingerprint,
        "source_fingerprint": source_fingerprint,
    }]

    calls = {"count": 0}

    def _fake_build_prompt():
        calls["count"] += 1
        current = build_trust_capsule(
            loop.context.analysis_state,
            active_datasets=loop._active_dataset_capsule_inputs(),
        )
        loop._turn_trust_capsule = current
        loop._prompt_component_payloads = {"trust_capsule": render_trust_capsule(current)}
        return f"prompt {current['digest']}"

    monkeypatch.setattr(loop, "_build_system_prompt", _fake_build_prompt)
    first_prompt = loop._get_system_prompt()
    assert loop._get_system_prompt() == first_prompt
    assert calls["count"] == 1
    loop.context.analysis_state.evidence_records.append({
        "id": "ev_new_after_first_prompt",
        "verification_level": "computed_descriptive",
        "computation_refs": [],
    })
    refreshed_prompt = loop._get_system_prompt()
    assert calls["count"] == 2
    assert refreshed_prompt != first_prompt
