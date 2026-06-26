import pytest

from data_agent.agent.confirmation import (
    AnswerMode,
    ConfirmationContractError,
)
from data_agent.agent.loop import AgentLoop, FinalResponse, UserConfirmationRequired


def test_direct_question_candidate_uses_stable_identity():
    from data_agent.agent.confirmation.runtime import build_direct_question_candidate

    request = UserConfirmationRequired(
        question="Which metric should be used?",
        options=[
            {"label": "Revenue", "value": "revenue"},
            {"label": "Orders", "value": "orders"},
        ],
        confirmation_type="metric_scope",
        blocking_reason="Metric choice changes the calculation.",
        related_spec_id="spec_1",
    )

    first = build_direct_question_candidate(
        session_id="session_1",
        turn_id="turn_1",
        message_version=3,
        request=request,
    )
    second = build_direct_question_candidate(
        session_id="session_1",
        turn_id="turn_1",
        message_version=3,
        request=request,
    )

    assert first.confirmation_id == second.confirmation_id
    assert first.decision_key == second.decision_key
    assert first.operation == "direct_user_question"
    assert first.resolution_action == "record_confirmation_answer"
    assert first.blocking_surfaces == ("agent_turn",)
    assert first.options[0].label == "Revenue"
    assert first.options[0].value == "revenue"
    assert first.decision_impact == "Metric choice changes the calculation."
    assert first.resolution_params["confirmation_type"] == "metric_scope"
    assert first.resolution_params["related_spec_id"] == "spec_1"


def test_multi_select_candidate_uses_multi_select_answer_mode():
    from data_agent.agent.confirmation.runtime import build_direct_question_candidate

    candidate = build_direct_question_candidate(
        session_id="session_1",
        turn_id="turn_1",
        message_version=1,
        request=UserConfirmationRequired(
            question="Pick analyses",
            options=[{"label": "Trend", "value": "trend"}],
            multi_select=True,
            confirmation_type="follow_up_choice",
        ),
    )

    assert candidate.answer_mode == AnswerMode.MULTI_SELECT


def test_free_text_candidate_uses_free_text_mode_without_options():
    from data_agent.agent.confirmation.runtime import build_direct_question_candidate

    candidate = build_direct_question_candidate(
        session_id="session_1",
        turn_id="turn_1",
        message_version=1,
        request=UserConfirmationRequired(
            question="Describe the business rule.",
            options=[],
            confirmation_type="scope_confirmation",
        ),
    )

    assert candidate.answer_mode == AnswerMode.FREE_TEXT
    assert candidate.options == ()


def test_free_text_candidate_rejects_missing_question():
    from data_agent.agent.confirmation.runtime import build_direct_question_candidate

    with pytest.raises(ConfirmationContractError):
        build_direct_question_candidate(
            session_id="session_1",
            turn_id="turn_1",
            message_version=1,
            request=UserConfirmationRequired(question="", options=[]),
        )


def test_candidate_identity_changes_with_message_version():
    from data_agent.agent.confirmation.runtime import build_direct_question_candidate

    request = UserConfirmationRequired(
        question="Which metric should be used?",
        options=[{"label": "Revenue", "value": "revenue"}],
        confirmation_type="metric_scope",
    )

    first = build_direct_question_candidate(
        session_id="session_1",
        turn_id="turn_1",
        message_version=1,
        request=request,
    )
    second = build_direct_question_candidate(
        session_id="session_1",
        turn_id="turn_1",
        message_version=2,
        request=request,
    )

    assert first.confirmation_id != second.confirmation_id


def test_required_question_candidate_uses_runtime_source_and_operation():
    from data_agent.agent.confirmation.runtime import build_required_question_candidate

    candidate = build_required_question_candidate(
        session_id="session_1",
        turn_id="turn_auto",
        message_version=2,
        request={
            "question": "Choose an analysis route.",
            "options": [
                {"label": "Trend", "value": "trend"},
                {"label": "Compare", "value": "period_compare"},
            ],
            "confirmation_type": "route_selection",
            "blocking_reason": "Different routes change the analysis output.",
            "state_updates": {"stage": "scope"},
        },
        source="question_need_detector",
        operation="auto_required_question",
    )

    assert candidate.confirmation_id.startswith("auto_")
    assert candidate.source == "question_need_detector"
    assert candidate.operation == "auto_required_question"
    assert candidate.resolution_action == "set_analysis_stage"
    assert candidate.resolution_params["state_updates"] == {"stage": "scope"}


def test_runtime_registers_record_confirmation_answer_action():
    from data_agent.agent.confirmation.actions import ResolutionContext
    from data_agent.agent.confirmation.runtime import build_action_registry

    registry = build_action_registry()

    receipt = registry.apply(
        "record_confirmation_answer",
        ResolutionContext("session_1", "cf_1", {"question": "Metric?"}),
        "revenue",
        "cf_1:answer_1",
    )
    repeated = registry.apply(
        "record_confirmation_answer",
        ResolutionContext("session_1", "cf_1", {"question": "Metric?"}),
        "revenue",
        "cf_1:answer_1",
    )

    assert receipt == repeated
    assert receipt.status == "succeeded"
    assert receipt.output["answer"] == "revenue"
    assert receipt.output["question"] == "Metric?"


def test_runtime_rejects_unsafe_state_update_action():
    from data_agent.agent.confirmation.runtime import build_direct_question_candidate

    candidate = build_direct_question_candidate(
        session_id="session_1",
        turn_id="turn_1",
        message_version=1,
        request=UserConfirmationRequired(
            question="Proceed?",
            options=[{"label": "Yes", "value": "yes"}],
            state_updates='{"arbitrary": {"nested": "write"}}',
        ),
    )

    assert candidate.resolution_action == "record_confirmation_answer"
    assert candidate.resolution_params["state_updates"] == {}


class _ToolCall:
    id = "tc_confirm"
    name = "ask_user_question"
    arguments = {"question": "Which metric?", "options": ["Revenue", "Orders"]}


class _ToolResponse:
    tool_calls = [_ToolCall()]


def _raise_direct_question(_name, _arguments):
    raise UserConfirmationRequired(
        question="Which metric?",
        options=[
            {"label": "Revenue", "value": "revenue"},
            {"label": "Orders", "value": "orders"},
        ],
        context="Choose the metric used by the next calculation.",
        confirmation_type="metric_scope",
        blocking_reason="The next calculation depends on this metric.",
    )


def _patch_direct_question_tool(monkeypatch, tmp_path):
    import data_agent.agent.loop as loop_module

    cfg = loop_module.get_config()
    monkeypatch.setattr(cfg, "sessions_dir", tmp_path)
    monkeypatch.setattr(cfg, "skill_auto_discover", False)
    monkeypatch.setattr(loop_module, "get_config", lambda: cfg)
    monkeypatch.setattr(loop_module.registry, "expand_from_tool_call", lambda _name: None)
    monkeypatch.setattr(loop_module.registry, "execute", _raise_direct_question)


def test_agent_loop_direct_question_uses_confirmation_runtime(tmp_path, monkeypatch):
    _patch_direct_question_tool(monkeypatch, tmp_path)
    loop = AgentLoop(client=None, session_id="loop_direct_question")

    result = loop._execute_single_tool(_ToolCall(), [_ToolCall()], 0)

    assert result.confirmation_id == result.suspension_id
    assert result.version >= 2
    assert result.question == "Which metric?"
    assert (
        tmp_path
        / "loop_direct_question"
        / "confirmations"
        / "events.jsonl"
    ).exists()
    assert list(tmp_path.glob("suspension_*.json")) == []


def test_streaming_direct_question_event_exposes_confirmation_identity(tmp_path, monkeypatch):
    _patch_direct_question_tool(monkeypatch, tmp_path)
    loop = AgentLoop(client=None, session_id="stream_direct_question")

    events = list(loop._process_tool_calls(_ToolResponse(), round_num=1))
    suspended = [event for event in events if event["type"] == "suspended"][0]

    assert suspended["confirmation_id"] == suspended["suspension_id"]
    assert suspended["version"] >= 2
    assert suspended["question"] == "Which metric?"
    assert (
        tmp_path
        / "stream_direct_question"
        / "confirmations"
        / "events.jsonl"
    ).exists()
    assert list(tmp_path.glob("suspension_*.json")) == []


def test_direct_question_does_not_write_legacy_pending_confirmation(tmp_path, monkeypatch):
    _patch_direct_question_tool(monkeypatch, tmp_path)
    loop = AgentLoop(client=None, session_id="loop_no_legacy_pending")

    class _LegacyState:
        pending_confirmations = []

        def add_confirmation(self, _payload):
            raise AssertionError("direct questions must not use legacy pending_confirmations")

        def save(self):
            raise AssertionError("direct questions must not save legacy confirmation state")

    loop.context.analysis_state = _LegacyState()

    result = loop._execute_single_tool(_ToolCall(), [_ToolCall()], 0)

    assert result.confirmation_id
    assert loop.context.analysis_state.pending_confirmations == []


def test_resume_turn_answers_runtime_confirmation(tmp_path, monkeypatch):
    from data_agent.agent.confirmation.models import ConfirmationStatus

    _patch_direct_question_tool(monkeypatch, tmp_path)
    loop = AgentLoop(client=None, session_id="resume_runtime_question")
    suspended = loop._execute_single_tool(_ToolCall(), [_ToolCall()], 0)
    loop._loop = lambda _user_input: FinalResponse(content="done")

    result = loop.resume_turn(
        suspended.confirmation_id,
        "revenue",
        expected_version=suspended.version,
        idempotency_key="answer_key",
    )
    record = loop._confirmation_runtime().get(
        "resume_runtime_question",
        suspended.confirmation_id,
    )

    assert result == FinalResponse(content="done")
    assert record.status == ConfirmationStatus.RESOLVED
    assert record.response == "revenue"
    assert list(tmp_path.glob("suspension_*.json")) == []


def test_resume_turn_is_idempotent_for_same_runtime_answer(tmp_path, monkeypatch):
    _patch_direct_question_tool(monkeypatch, tmp_path)
    loop = AgentLoop(client=None, session_id="resume_runtime_idempotent")
    suspended = loop._execute_single_tool(_ToolCall(), [_ToolCall()], 0)
    loop._loop = lambda _user_input: FinalResponse(content="done")

    loop.resume_turn(
        suspended.confirmation_id,
        "revenue",
        expected_version=suspended.version,
        idempotency_key="client_retry_key",
    )
    events_path = (
        tmp_path
        / "resume_runtime_idempotent"
        / "confirmations"
        / "events.jsonl"
    )
    before = events_path.read_text(encoding="utf-8").splitlines()

    repeated = loop.resume_turn(
        suspended.confirmation_id,
        "revenue",
        expected_version=suspended.version,
        idempotency_key="client_retry_key",
    )
    after = events_path.read_text(encoding="utf-8").splitlines()

    assert repeated == FinalResponse(content="done")
    assert after == before


def test_resume_turn_streaming_answers_runtime_confirmation(tmp_path, monkeypatch):
    from data_agent.agent.confirmation.models import ConfirmationStatus
    from data_agent.llm.client import Response

    _patch_direct_question_tool(monkeypatch, tmp_path)
    loop = AgentLoop(client=None, session_id="resume_runtime_streaming")
    suspended = loop._execute_single_tool(_ToolCall(), [_ToolCall()], 0)

    def _stream_done(_round_num):
        yield {
            "type": "_response",
            "response": Response(text="done"),
            "streamed_text": "done",
        }

    loop._stream_llm_round = _stream_done

    events = list(
        loop.resume_turn_streaming(
            suspended.confirmation_id,
            "revenue",
            expected_version=suspended.version,
            idempotency_key="stream_answer_key",
        )
    )
    record = loop._confirmation_runtime().get(
        "resume_runtime_streaming",
        suspended.confirmation_id,
    )

    assert [event for event in events if event["type"] == "error"] == []
    assert record.status == ConfirmationStatus.RESOLVED
    assert record.response == "revenue"


def test_resume_turn_uses_client_idempotency_key(tmp_path, monkeypatch):
    _patch_direct_question_tool(monkeypatch, tmp_path)
    loop = AgentLoop(client=None, session_id="resume_runtime_client_key")
    suspended = loop._execute_single_tool(_ToolCall(), [_ToolCall()], 0)
    loop._loop = lambda _user_input: FinalResponse(content="done")

    loop.resume_turn(
        suspended.confirmation_id,
        "revenue",
        expected_version=suspended.version,
        idempotency_key="client_retry_key",
    )
    record = loop._confirmation_runtime().get(
        "resume_runtime_client_key",
        suspended.confirmation_id,
    )

    assert record.response_id == "client_retry_key"


def test_resume_turn_rejects_legacy_suspension_file(tmp_path, monkeypatch):
    from data_agent.agent.loop import SuspendedForConfirmation, SuspensionManager

    _patch_direct_question_tool(monkeypatch, tmp_path)
    SuspensionManager(tmp_path).save(
        SuspendedForConfirmation(
            suspension_id="legacy_only",
            question="Legacy question?",
            options=[],
            context="",
            snapshot={"messages": []},
        )
    )
    loop = AgentLoop(client=None, session_id="resume_rejects_legacy")
    loop._loop = lambda _user_input: FinalResponse(content="done")

    result = loop.resume_turn("legacy_only", "answer")

    assert isinstance(result, FinalResponse)
    assert "runtime confirmation legacy_only not found" in result.content


def test_resume_turn_requires_runtime_idempotency_key(tmp_path, monkeypatch):
    _patch_direct_question_tool(monkeypatch, tmp_path)
    loop = AgentLoop(client=None, session_id="resume_requires_key")
    suspended = loop._execute_single_tool(_ToolCall(), [_ToolCall()], 0)
    loop._loop = lambda _user_input: FinalResponse(content="done")

    result = loop.resume_turn(
        suspended.confirmation_id,
        "revenue",
        expected_version=suspended.version,
        idempotency_key="",
    )

    assert isinstance(result, FinalResponse)
    assert "idempotency_key is required" in result.content


def test_sync_loop_blocks_final_response_when_runtime_confirmation_pending(tmp_path, monkeypatch):
    from data_agent.llm.client import Response

    _patch_direct_question_tool(monkeypatch, tmp_path)
    loop = AgentLoop(client=None, session_id="final_guard_pending")
    loop._get_system_prompt = lambda: ""
    candidate = __import__(
        "data_agent.agent.confirmation.runtime",
        fromlist=["build_required_question_candidate"],
    ).build_required_question_candidate(
        session_id="final_guard_pending",
        turn_id="turn_guard",
        message_version=1,
        request={
            "question": "Confirm route?",
            "options": [{"label": "Trend", "value": "trend"}],
            "confirmation_type": "route_selection",
            "blocking_reason": "Route affects the final answer.",
        },
        source="question_need_detector",
        operation="route_selection",
    )
    loop._confirmation_runtime().request(candidate)

    class FinalOnlyClient:
        def chat(self, *args, **kwargs):
            return Response(text="final answer should not bypass confirmation")

    loop.client = FinalOnlyClient()

    result = loop._loop("analyze data")

    assert result.confirmation_id == result.suspension_id
    assert result.question == "Confirm route?"


def test_stream_loop_blocks_final_response_when_runtime_confirmation_pending(tmp_path, monkeypatch):
    from data_agent.llm.client import Response

    _patch_direct_question_tool(monkeypatch, tmp_path)
    loop = AgentLoop(client=None, session_id="final_guard_stream_pending")
    loop._get_system_prompt = lambda: ""
    loop._prepare_analysis_turn = lambda _user_input: []
    loop._turn_question_need = None
    candidate = __import__(
        "data_agent.agent.confirmation.runtime",
        fromlist=["build_required_question_candidate"],
    ).build_required_question_candidate(
        session_id="final_guard_stream_pending",
        turn_id="turn_guard",
        message_version=1,
        request={
            "question": "Confirm stream route?",
            "options": [{"label": "Trend", "value": "trend"}],
            "confirmation_type": "route_selection",
            "blocking_reason": "Route affects the final answer.",
        },
        source="question_need_detector",
        operation="route_selection",
    )
    loop._confirmation_runtime().request(candidate)

    loop._stream_llm_round = lambda _round_num: iter([{
        "type": "_response",
        "response": Response(text="stream final should not bypass"),
        "streamed_text": "stream final should not bypass",
    }])

    events = list(loop.stream_turn("analyze data"))
    suspended = [event for event in events if event["type"] == "suspended"][0]

    assert suspended["confirmation_id"] == suspended["suspension_id"]
    assert suspended["question"] == "Confirm stream route?"
