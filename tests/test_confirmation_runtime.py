import pytest
from dataclasses import replace
from types import SimpleNamespace

from data_agent.agent.confirmation import (
    AnswerMode,
    ConfirmationContractError,
)
from data_agent.agent.loop import AgentLoop, FinalResponse, UserConfirmationRequired


def _append_ledger_record(
    sessions_root,
    session_id,
    *,
    confirmation_id,
    status,
    confirmation_type,
    resolution_action,
):
    from data_agent.agent.confirmation import (
        AnswerMode,
        ConfirmationEvent,
        ConfirmationOption,
        ConfirmationRecord,
        ConfirmationRequest,
        QuestionCandidate,
    )
    from data_agent.agent.confirmation.store import ConfirmationStore

    candidate = QuestionCandidate(
        confirmation_id=confirmation_id,
        session_id=session_id,
        turn_id="legacy_turn",
        decision_key=f"{session_id}:{confirmation_id}",
        source="legacy",
        operation=confirmation_type,
        question="Legacy relationship question?",
        decision_impact="Legacy relationship gate",
        answer_mode=AnswerMode.SINGLE_SELECT,
        options=(ConfirmationOption("Include", "include"),),
        blocking_surfaces=("agent_turn",),
        skippable=True,
        resolution_action=resolution_action,
        resolution_params={"confirmation_type": confirmation_type, "decision_kind": "metric_definition", "missing_value": "对比指标口径", "affected_operations": ["period_compare"]},
    )
    request = ConfirmationRequest.from_candidate(candidate)
    record = ConfirmationRecord.from_request(request, now="2026-06-27T00:00:00Z")
    record = replace(
        record,
        status=status,
        suspension_id=(f"susp_{confirmation_id}" if status.value == "suspended" else ""),
        failure_reason=("legacy action missing" if status.value == "failed" else ""),
    )
    ConfirmationStore(sessions_root, session_id).append(ConfirmationEvent(
        event_id=f"event_{confirmation_id}",
        confirmation_id=confirmation_id,
        session_id=session_id,
        event_type="legacy_fixture",
        version=record.version,
        occurred_at=record.updated_at,
        record=record,
    ))
    return record


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


def _suspended_event_for(request, *, source, operation):
    from data_agent.agent.confirmation.models import (
        ConfirmationRecord,
        ConfirmationRequest,
    )
    from data_agent.agent.confirmation.runtime import (
        build_required_question_candidate,
        confirmation_record_to_suspended_event,
    )

    candidate = build_required_question_candidate(
        session_id="session_1",
        turn_id="turn_1",
        message_version=1,
        request=request,
        source=source,
        operation=operation,
    )
    record = ConfirmationRecord.from_request(
        ConfirmationRequest.from_candidate(candidate),
        now="2026-07-08T00:00:00Z",
    )
    return confirmation_record_to_suspended_event(record)


def test_suspended_event_reports_free_text_availability():
    """allow_free_text must mirror service._validate_answer: True for
    ask_user_question (record-only) and FREE_TEXT questions, False for
    state-driving single selects so the web UI hides the free-text box there."""
    from data_agent.agent.confirmation.models import (
        ConfirmationRecord,
        ConfirmationRequest,
    )
    from data_agent.agent.confirmation.runtime import (
        build_direct_question_candidate,
        confirmation_record_to_suspended_event,
    )

    def event_for_direct(request):
        candidate = build_direct_question_candidate(
            session_id="session_1",
            turn_id="turn_1",
            message_version=1,
            request=request,
        )
        record = ConfirmationRecord.from_request(
            ConfirmationRequest.from_candidate(candidate),
            now="2026-07-08T00:00:00Z",
        )
        return confirmation_record_to_suspended_event(record)

    # ask_user_question with options → record-only → free text allowed
    direct_event = event_for_direct(
        UserConfirmationRequired(
            question="你手头的数据是什么格式？",
            options=[{"label": "CSV", "value": "csv"}, {"label": "聊聊", "value": "chat"}],
        )
    )
    assert direct_event["allow_free_text"] is True
    assert direct_event["multi_select"] is False

    # ask_user_question multi_select → record-only → free text allowed
    multi_event = event_for_direct(
        UserConfirmationRequired(
            question="想关注哪些维度？",
            options=[{"label": "收入", "value": "revenue"}, {"label": "留存", "value": "retention"}],
            multi_select=True,
        )
    )
    assert multi_event["allow_free_text"] is True
    assert multi_event["multi_select"] is True

    # FREE_TEXT question (no options) → free text allowed
    free_text_event = event_for_direct(
        UserConfirmationRequired(question="描述业务规则", options=[])
    )
    assert free_text_event["allow_free_text"] is True

    # state-driving single select (stage) → free text NOT allowed
    stage_event = _suspended_event_for(
        UserConfirmationRequired(
            question="确认分析阶段？",
            options=[{"label": "范围", "value": "scope"}],
            state_updates='{"stage": "scope"}',
        ),
        source="analysis_plan",
        operation="scope_confirmation",
    )
    assert stage_event["allow_free_text"] is False

    # state-driving single select (method) → free text NOT allowed
    method_event = _suspended_event_for(
        UserConfirmationRequired(
            question="确认方法？",
            options=[{"label": "确认方法", "value": "confirm_method"}],
            state_updates='{"method_confirmation": {"analysis_spec_id": "spec_1"}}',
        ),
        source="method_playbook",
        operation="method_confirmation",
    )
    assert method_event["allow_free_text"] is False


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
            "risk_fields": ["分析路线"],
            "affected_routes": ["trend"],
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


def test_runtime_does_not_register_resolve_file_relationship_action():
    from data_agent.agent.confirmation.actions import (
        ResolutionContext,
        UnknownResolutionAction,
    )
    from data_agent.agent.confirmation.runtime import build_action_registry

    registry = build_action_registry()

    with pytest.raises(UnknownResolutionAction):
        registry.apply(
            "resolve_file_relationship",
            ResolutionContext("session_1", "cf_legacy", {}),
            "include_in_active_bundle",
            "cf_legacy:answer_1",
        )


def test_checkpoint_restore_and_new_turn_ignore_obsolete_ledger_records(tmp_path, monkeypatch):
    from data_agent.agent.confirmation import ConfirmationStatus
    from data_agent.agent.confirmation.runtime import build_action_registry
    from data_agent.agent.confirmation.service import ConfirmationService
    from data_agent.config import get_config

    session_id = "obsolete_ledger_checkpoint"
    for confirmation_id, status, confirmation_type in (
        ("legacy_pending", ConfirmationStatus.PENDING, "file_relationship_confirmation"),
        ("legacy_suspended", ConfirmationStatus.SUSPENDED, "file_exclusion_confirmation"),
        ("legacy_failed", ConfirmationStatus.FAILED, "join_logic_confirmation"),
    ):
        _append_ledger_record(
            tmp_path,
            session_id,
            confirmation_id=confirmation_id,
            status=status,
            confirmation_type=confirmation_type,
            resolution_action="resolve_file_relationship",
        )

    service = ConfirmationService(tmp_path, action_registry=build_action_registry())
    assert service.checkpoint(session_id) is None
    assert service.restore(session_id) is None

    cfg = get_config()
    monkeypatch.setattr(cfg, "sessions_dir", tmp_path)
    loop = AgentLoop(client=None, session_id=session_id)
    assert loop._runtime_confirmation_checkpoint() is None

    assert service.get(session_id, "legacy_pending").status == ConfirmationStatus.PENDING
    assert service.get(session_id, "legacy_suspended").status == ConfirmationStatus.SUSPENDED
    assert service.get(session_id, "legacy_failed").status == ConfirmationStatus.FAILED


def test_cached_obsolete_confirmation_id_is_not_projected_for_resume(tmp_path, monkeypatch):
    from data_agent.agent.confirmation import ConfirmationStatus
    from data_agent.config import get_config

    session_id = "obsolete_cached_resume"
    old = _append_ledger_record(
        tmp_path,
        session_id,
        confirmation_id="legacy_cached",
        status=ConfirmationStatus.SUSPENDED,
        confirmation_type="file_relationship_confirmation",
        resolution_action="resolve_file_relationship",
    )
    cfg = get_config()
    monkeypatch.setattr(cfg, "sessions_dir", tmp_path)
    loop = AgentLoop(client=None, session_id=session_id)

    assert loop._runtime_suspension_for_resume(old.confirmation_id) is None
    result = loop.resume_turn(old.confirmation_id, "include")
    assert isinstance(result, FinalResponse)
    assert "not found" in result.content


def test_method_ledger_record_remains_actionable(tmp_path):
    from data_agent.agent.confirmation import ConfirmationStatus
    from data_agent.agent.confirmation.runtime import build_action_registry
    from data_agent.agent.confirmation.service import ConfirmationService

    session_id = "method_ledger_checkpoint"
    _append_ledger_record(
        tmp_path,
        session_id,
        confirmation_id="method_pending",
        status=ConfirmationStatus.PENDING,
        confirmation_type="method_confirmation",
        resolution_action="record_confirmation_answer",
    )

    service = ConfirmationService(tmp_path, action_registry=build_action_registry())
    checkpoint = service.checkpoint(session_id)

    assert checkpoint is not None
    assert checkpoint.confirmation_id == "method_pending"
    assert checkpoint.status == ConfirmationStatus.SUSPENDED
    assert service.restore(session_id).confirmation_id == "method_pending"


def test_service_rejects_new_obsolete_candidate_and_cannot_revive_old_action(tmp_path):
    from data_agent.agent.confirmation import (
        AnswerMode,
        ConfirmationOption,
        ConfirmationStatus,
        QuestionCandidate,
        RequestDisposition,
    )
    from data_agent.agent.confirmation.runtime import build_action_registry
    from data_agent.agent.confirmation.service import (
        ConfirmationService,
        InvalidConfirmationTransition,
    )

    session_id = "obsolete_ledger_response"
    service = ConfirmationService(tmp_path, action_registry=build_action_registry())
    candidate = QuestionCandidate(
        confirmation_id="legacy_new",
        session_id=session_id,
        turn_id="turn_1",
        decision_key="legacy:new",
        source="legacy",
        operation="join_logic_confirmation",
        question="Legacy join question?",
        decision_impact="Legacy join gate",
        answer_mode=AnswerMode.SINGLE_SELECT,
        options=(ConfirmationOption("Include", "include"),),
        blocking_surfaces=("agent_turn",),
        skippable=True,
        resolution_action="resolve_file_relationship",
        resolution_params={"confirmation_type": "join_logic_confirmation"},
    )

    result = service.request(candidate)

    assert result.disposition == RequestDisposition.REJECTED
    assert result.record is None

    old = _append_ledger_record(
        tmp_path,
        session_id,
        confirmation_id="legacy_old",
        status=ConfirmationStatus.SUSPENDED,
        confirmation_type="file_relationship_confirmation",
        resolution_action="resolve_file_relationship",
    )
    with pytest.raises(InvalidConfirmationTransition, match="obsolete"):
        service.respond(session_id, old.confirmation_id, "include", old.version, "old_answer")
    assert service.get(session_id, old.confirmation_id).status == ConfirmationStatus.SUSPENDED


def test_legacy_relationship_confirmation_type_is_rejected_not_fallback():
    from data_agent.agent.confirmation.runtime import build_direct_question_candidate

    with pytest.raises(ConfirmationContractError, match="obsolete confirmation type"):
        build_direct_question_candidate(
            session_id="session_1",
            turn_id="turn_1",
            message_version=1,
            request=UserConfirmationRequired(
                question="Legacy relationship question",
                options=[{"label": "Include", "value": "include_in_active_bundle"}],
                confirmation_type="file_relationship_confirmation",
                state_updates={
                    "file_relationship_confirmation": {"relationship_id": "rel_1"},
                },
            ),
        )


@pytest.mark.parametrize(
    "state_updates",
    [
        {"file_relationship_confirmation": {"relationship_id": "rel_1"}},
        '{"file_relationship_confirmation": {"relationship_id": "rel_1"}}',
    ],
)
def test_legacy_relationship_state_update_is_rejected_before_safe_fallback(
    state_updates,
):
    from data_agent.agent.confirmation.runtime import build_direct_question_candidate

    with pytest.raises(ConfirmationContractError, match="obsolete confirmation"):
        build_direct_question_candidate(
            session_id="session_1",
            turn_id="turn_1",
            message_version=1,
            request=UserConfirmationRequired(
                question="Legacy relationship question",
                options=[{"label": "Include", "value": "include_in_active_bundle"}],
                state_updates=state_updates,
            ),
        )


def test_auto_suspend_ignores_only_obsolete_pending_confirmations():
    from data_agent.agent.analysis_state import AnalysisSessionState

    loop = AgentLoop(client=None, session_id="obsolete_pending")
    state = AnalysisSessionState(session_id="obsolete_pending")
    state.pending_confirmations = [{
        "id": "legacy_relationship",
        "status": "pending",
        "confirmation_type": "file_relationship_confirmation",
        "question": "Legacy relationship question",
        "options": [{"label": "Include", "value": "include"}],
        "state_updates": {"stage": "scope"},
    }]

    assert loop._pending_confirmation_for_auto_suspend(state) is None


def test_auto_suspend_keeps_new_confirmation_types_actionable():
    from data_agent.agent.analysis_state import AnalysisSessionState

    loop = AgentLoop(client=None, session_id="new_pending")
    state = AnalysisSessionState(session_id="new_pending")
    pending = {
        "id": "method_gate",
        "status": "pending",
        "confirmation_type": "method_confirmation",
        "question": "Confirm the method?",
        "options": [{"label": "Confirm", "value": "confirm_method"}],
        "state_updates": {"stage": "plan"},
    }
    state.pending_confirmations = [pending]

    assert loop._pending_confirmation_for_auto_suspend(state) is pending


def _scope_selection_state():
    from data_agent.agent.analysis_state import AnalysisSessionState

    state = AnalysisSessionState(session_id="runtime_scope", data_state="data_loaded")
    state.data_pool = [
        {
            "file_id": "sales_a",
            "filename": "sales.csv",
            "dataset": "sales_a",
            "status": "loaded",
        },
        {
            "file_id": "sales_b",
            "filename": "sales.csv",
            "dataset": "sales_b",
            "status": "loaded",
        },
    ]
    state.dataset_contracts = [
        {"id": "duc_sales_a", "dataset": "sales_a", "quality_status": "ready"},
        {"id": "duc_sales_b", "dataset": "sales_b", "quality_status": "ready"},
    ]
    return state


def _multiple_scope_selection_state():
    state = _scope_selection_state()
    state.data_pool.extend([
        {
            "file_id": "cost_a",
            "filename": "cost.csv",
            "dataset": "cost_a",
            "status": "loaded",
        },
        {
            "file_id": "cost_b",
            "filename": "cost.csv",
            "dataset": "cost_b",
            "status": "loaded",
        },
    ])
    state.dataset_contracts.extend([
        {"id": "duc_cost_a", "dataset": "cost_a", "quality_status": "ready"},
        {"id": "duc_cost_b", "dataset": "cost_b", "quality_status": "ready"},
    ])
    return state


def _scope_selection_question(state):
    from data_agent.agent.question_need_detector import detect_question_need

    intent = SimpleNamespace(intent_type="directed_analysis", clarity="clear")
    return detect_question_need("analyze sales.csv", intent, state)


def _question_for_goal(state, goal):
    from data_agent.agent.question_need_detector import detect_question_need

    intent = SimpleNamespace(intent_type="directed_analysis", clarity="clear")
    return detect_question_need(goal, intent, state)


def test_auto_suspend_routes_scope_selection_through_unified_runtime(tmp_path, monkeypatch):
    import data_agent.agent.loop as loop_module

    cfg = loop_module.get_config()
    monkeypatch.setattr(cfg, "sessions_dir", tmp_path)
    monkeypatch.setattr(cfg, "skill_auto_discover", False)
    monkeypatch.setattr(loop_module, "get_config", lambda: cfg)
    loop = AgentLoop(client=None, session_id="runtime_scope")
    state = _scope_selection_state()
    state.pending_confirmations = [{
        "id": "legacy_relationship",
        "status": "pending",
        "confirmation_type": "file_relationship_confirmation",
        "question": "Legacy relationship question",
        "options": [{"label": "Include", "value": "include"}],
        "state_updates": {"stage": "scope"},
    }]
    loop.context.analysis_state = state
    loop._turn_existing_pending_ids = set()
    loop._turn_question_need = _scope_selection_question(state)

    result = loop._maybe_auto_suspend_for_required_question()

    assert result is not None
    assert result.confirmation_type == "file_scope_selection"
    assert "file" in result.question.lower()
    assert [option["value"] for option in result.options] == ["sales_a", "sales_b"]
    assert result.confirmation_id == result.suspension_id


def test_existing_actionable_confirmation_precedes_new_scope_question(tmp_path, monkeypatch):
    import data_agent.agent.loop as loop_module

    cfg = loop_module.get_config()
    monkeypatch.setattr(cfg, "sessions_dir", tmp_path)
    monkeypatch.setattr(cfg, "skill_auto_discover", False)
    monkeypatch.setattr(loop_module, "get_config", lambda: cfg)
    loop = AgentLoop(client=None, session_id="runtime_scope_priority")
    state = _scope_selection_state()
    state.pending_confirmations = [{
        "id": "method_gate",
        "status": "pending",
        "confirmation_type": "method_confirmation",
        "question": "Confirm the method?",
        "options": [{"label": "Confirm", "value": "confirm_method"}],
        "state_updates": {"stage": "plan"},
    }]
    loop.context.analysis_state = state
    loop._turn_existing_pending_ids = set()
    loop._turn_question_need = _scope_selection_question(state)

    result = loop._maybe_auto_suspend_for_required_question()

    # IC2 契约更新：原断言通用方法 pending 优先悬挂；新原则下方法审批被
    # 策略降级，让位给本轮新检测到的真实文件范围问题。
    assert result is not None
    assert result.confirmation_type == "file_scope_selection"
    assert "file" in result.question.lower() or "sales" in result.question.lower()


def test_runtime_confirms_independent_scope_groups_in_successive_rounds(tmp_path, monkeypatch):
    import data_agent.agent.loop as loop_module

    cfg = loop_module.get_config()
    monkeypatch.setattr(cfg, "sessions_dir", tmp_path)
    monkeypatch.setattr(cfg, "skill_auto_discover", False)
    monkeypatch.setattr(loop_module, "get_config", lambda: cfg)
    loop = AgentLoop(client=None, session_id="runtime_scope_groups")
    state = _multiple_scope_selection_state()
    loop.context.analysis_state = state
    loop._turn_existing_pending_ids = set()
    loop._turn_question_need = _question_for_goal(
        state,
        "compare sales.csv with cost.csv",
    )

    first = loop._maybe_auto_suspend_for_required_question()

    assert [option["value"] for option in first.options] == ["sales_a", "sales_b"]
    loop._confirmation_runtime().respond(
        loop.session_id,
        first.confirmation_id,
        "sales_b",
        first.version,
        "select_sales_b",
    )
    loop._turn_question_need = _question_for_goal(
        state,
        "compare sales.csv using sales_b with cost.csv",
    )

    second = loop._maybe_auto_suspend_for_required_question()

    assert [option["value"] for option in second.options] == ["cost_a", "cost_b"]
    assert second.confirmation_id == second.suspension_id
    assert second.confirmation_id != first.confirmation_id


def test_excessive_scope_candidates_suspend_as_free_text(tmp_path, monkeypatch):
    import data_agent.agent.loop as loop_module
    from data_agent.agent.analysis_state import AnalysisSessionState

    cfg = loop_module.get_config()
    monkeypatch.setattr(cfg, "sessions_dir", tmp_path)
    monkeypatch.setattr(cfg, "skill_auto_discover", False)
    monkeypatch.setattr(loop_module, "get_config", lambda: cfg)
    loop = AgentLoop(client=None, session_id="runtime_many_scope_candidates")
    state = AnalysisSessionState(session_id="runtime_many_scope_candidates", data_state="data_loaded")
    state.data_pool = [{
        "file_id": "other_first",
        "filename": "other.csv",
        "dataset": "other",
        "status": "loaded",
    }] + [
        {
            "file_id": f"sales_{index}",
            "filename": "sales.csv",
            "dataset": f"sales_{index}",
            "status": "loaded",
        }
        for index in range(21)
    ]
    state.dataset_contracts = [
        {"id": "duc_other", "dataset": "other", "quality_status": "ready"},
    ] + [
        {"id": f"duc_sales_{index}", "dataset": f"sales_{index}", "quality_status": "ready"}
        for index in range(21)
    ]
    loop.context.analysis_state = state
    loop._turn_existing_pending_ids = set()
    loop._turn_question_need = _question_for_goal(state, "analyze sales.csv")

    suspended = loop._maybe_auto_suspend_for_required_question()
    record = loop._confirmation_runtime().get(loop.session_id, suspended.confirmation_id)

    assert suspended.options == []
    assert record.answer_mode == AnswerMode.FREE_TEXT
    assert "第 N 个文件" in suspended.question
    assert "2-22" in suspended.question

    loop._confirmation_runtime().respond(
        loop.session_id,
        suspended.confirmation_id,
        "第 22 个文件",
        suspended.version,
        "select_upload_21",
    )
    next_question = _question_for_goal(
        state,
        "analyze sales.csv using 第 22 个文件",
    )

    assert next_question["status"] == "clear"


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
    from data_agent.agent.context import use_agent_context
    from tests.test_trusted_publication_runtime import request
    with use_agent_context(loop.context): request(loop,"Which metric should be used?",kind="knowledge")
    # This fixture tests a genuine goal-selection continuation, not pure knowledge consultation.
    loop.context.turn_intent.intent_type="intent_negotiation"
    suspended = loop._execute_single_tool(_ToolCall(), [_ToolCall()], 0)

    def _stream_done(_round_num):
        import json
        from data_agent.agent.publication.runtime import snapshot_for_turn
        snap=snapshot_for_turn(loop)
        raw=json.dumps({"schema":"answer_bindings.v2","snapshot_digest":snap.digest,"sections":[{"requirement_ids":[r["id"] for r in snap.as_dict()["requirements"]],"parts":[{"kind":"text","purpose":"knowledge","text":"done","claim_refs":[]}]}]})
        yield {
            "type": "_response",
            "response": Response(text=raw),
            "streamed_text": "unaccepted draft",
        }

    loop._stream_llm_round = _stream_done
    requirements_before = list(loop.context.analysis_state.answer_requirements)
    revision_before = loop.context.analysis_state.requirement_revision

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
    assert loop.context.analysis_state.answer_requirements == requirements_before
    assert loop.context.analysis_state.requirement_revision == revision_before


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
            "risk_fields": ["分析路线"],
            "affected_routes": ["trend"],
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
            "risk_fields": ["分析路线"],
            "affected_routes": ["trend"],
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


@pytest.mark.parametrize("entry", ["direct", "automatic"])
@pytest.mark.parametrize("mode", ["resolved", "open", "skipped", "cancelled", "expired", "changed"])
def test_s3_business_reuse_has_one_disposition_across_adapters(tmp_path, monkeypatch, entry, mode):
    import os, json
    from pathlib import Path
    import data_agent.agent.loop as module
    from data_agent.agent.loop import SuspendedForConfirmation
    cfg = module.get_config()
    monkeypatch.setattr(cfg, "sessions_dir", tmp_path / "sessions")
    monkeypatch.setattr(cfg, "mcp_enabled", False)
    monkeypatch.setattr(cfg, "skill_auto_discover", False)
    loop, _ = _s3_bound_question_fixture(tmp_path, monkeypatch, session_id="reuse_" + entry + "_" + mode)
    payload = {
        "question": "净收益的成本是否包含券成本？",
        "options": [{"label": "包含", "value": "include"}, {"label": "不包含", "value": "exclude"}],
        "confirmation_type": "metric_scope",
        "blocking_reason": "成本边界会改变净收益，用户尚未定义。",
    }
    def invoke(value, turn):
        if entry == "automatic":
            return loop._suspend_for_required_question_payload(value, source="question_need_detector", operation="metric_scope")
        return loop._suspend_for_confirmation_request(UserConfirmationRequired(**value), turn_id=turn)
    first = invoke(payload, "first")
    assert isinstance(first, SuspendedForConfirmation)
    service = loop._confirmation_runtime()
    active = service.checkpoint(loop.session_id)
    if mode in {"resolved", "changed"}:
        service.respond(loop.session_id, active.confirmation_id, "include", active.version, "answer_once")
    elif mode == "skipped":
        service.skip(loop.session_id, active.confirmation_id, active.version, "skip_once")
    elif mode == "cancelled":
        service.cancel(loop.session_id, active.confirmation_id, active.version, "cancel_once")
    elif mode == "expired":
        service.expire(loop.session_id, active.confirmation_id, active.version, "explicit_expiry")
    before = service._store(loop.session_id).load_records()
    loop.messages.extend([{"role": "user", "content": "沿用同一业务范围继续。"}, {"role": "assistant", "content": "继续核对。"}])
    next_payload = dict(payload)
    if mode == "changed":
        next_payload["question"] = "改为不包含券成本的净收益口径，是否另扣渠道成本？"
    result = invoke(next_payload, "second")
    after = service._store(loop.session_id).load_records()
    out = Path(os.environ.get("DATA_AGENT_S3_ASK_EVIDENCE", str(tmp_path / "evidence")))
    out.mkdir(parents=True, exist_ok=True)
    (out / ("reuse_" + entry + "_" + mode + ".json")).write_text(json.dumps({
        "entry": entry, "mode": mode, "payload": next_payload,
        "result_type": type(result).__name__, "result": vars(result) if hasattr(result, "__dict__") else result,
        "before": {k:v.to_dict() for k,v in before.items()}, "after": {k:v.to_dict() for k,v in after.items()},
        "provider_calls": 0,
    }, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    if mode == "resolved":
        assert after == before
        assert service.checkpoint(loop.session_id) is None
        if entry == "automatic":
            assert result is None, "An already resolved automatic decision must not become a suspension again."
        else:
            assert isinstance(result, str) and "include" in result
    else:
        assert isinstance(result, SuspendedForConfirmation)
        assert result.confirmation_id == active.confirmation_id if mode == "open" else result.confirmation_id != active.confirmation_id


def _s3_mixed_question_loop(tmp_path, monkeypatch, route):
    import json
    import data_agent.agent.loop as module
    from data_agent.tools.interaction import ask_user_question
    from data_agent.tools.registry import registry
    from data_agent.tools import discover_tools
    discover_tools();cfg=module.get_config()
    monkeypatch.setattr(cfg,"sessions_dir",tmp_path/"sessions");monkeypatch.setattr(cfg,"mcp_enabled",False);monkeypatch.setattr(cfg,"skill_auto_discover",False)
    loop,_=_s3_bound_question_fixture(tmp_path,monkeypatch,session_id="batch_"+route)
    cost={"question":"净收益的成本是否包含券成本？","options":[{"label":"包含","value":"include"},{"label":"不包含","value":"exclude"}]}
    window={"question":"比较窗口采用近7天还是近30天？","options":[{"label":"近7天","value":"window7"},{"label":"近30天","value":"window30"}],"confirmation_type":"time_window"}
    method={"question":"是否使用留存方法继续分析？","options":[{"label":"按此方法继续","value":"yes"}],"confirmation_type":"method_confirmation"}
    first=loop._suspend_for_confirmation_request(UserConfirmationRequired(**cost,confirmation_type="metric_scope",blocking_reason="成本边界需用户决定。"),turn_id="cost")
    service=loop._confirmation_runtime();active=service.checkpoint(loop.session_id);service.respond(loop.session_id,active.confirmation_id,"include",active.version,"cost_once")
    def invoke(questions):
        args={"questions":json.dumps(questions,ensure_ascii=False),"confirmation_type":"metric_scope","blocking_reason":"只有比较窗口仍未定义。"}
        try:
            ask_user_question(**args) if route=="direct" else registry.execute("ask_user_question",args)
        except UserConfirmationRequired as request:
            return loop._suspend_for_confirmation_request(request,turn_id="batch")
        raise AssertionError("Expected original interaction signal")
    return loop,service,cost,method,window,invoke


@pytest.mark.parametrize("route",["direct","registry"])
@pytest.mark.parametrize("include_method",[False,True])
def test_s3_multi_question_only_unresolved_item_is_displayed_and_answer_reuses(tmp_path,monkeypatch,route,include_method):
    import json,os
    from pathlib import Path
    from data_agent.agent.loop import SuspendedForConfirmation
    loop,service,cost,method,window,invoke=_s3_mixed_question_loop(tmp_path,monkeypatch,route)
    result=invoke([cost,method,window] if include_method else [cost,window])
    assert isinstance(result,SuspendedForConfirmation)
    visible=json.loads(result.context)
    assert len(visible)==1 and visible[0]["question"]==window["question"]
    active=service.checkpoint(loop.session_id)
    bindings=active.resolution_params["question_bindings"]
    assert [b["disposition"] for b in bindings]==(["reused","advisory","confirmation"] if include_method else ["reused","confirmation"])
    submitted=json.dumps([{"question_id":visible[0]["question_id"],"question":window["question"],"answer":"window7","is_free_input":False}],ensure_ascii=False)
    resolved=service.respond(loop.session_id,active.confirmation_id,submitted,active.version,"window_once")
    saved=json.loads(resolved.response)
    assert saved[0]["answer"]=="include" and saved[-1]["answer"]=="window7"
    assert len(saved)==len(bindings) and len({r["question_id"] for r in saved})==len(saved)
    replay=service.respond(loop.session_id,active.confirmation_id,submitted,active.version,"window_once")
    assert replay==resolved
    request=dict(window);kind=request.pop("confirmation_type")
    reused=loop._suspend_for_confirmation_request(UserConfirmationRequired(**request,confirmation_type=kind),turn_id="same_window")
    assert isinstance(reused,str) and "window7" in reused and service.checkpoint(loop.session_id) is None
    out=Path(os.environ.get("DATA_AGENT_S3_ASK_EVIDENCE",str(tmp_path/"evidence")));out.mkdir(parents=True,exist_ok=True)
    (out/("batch_"+route+"_"+str(include_method)+".json")).write_text(json.dumps({"visible":visible,"bindings":bindings,"resolved":resolved.to_dict(),"reused":reused,"provider_calls":0},ensure_ascii=False,indent=2,default=str),encoding="utf-8")


@pytest.mark.parametrize("fault",["missing","wrong_id","wrong_question","bad_option","duplicate","not_json","not_array"])
def test_s3_multi_question_rejects_unbound_answers_without_transition(tmp_path,monkeypatch,fault):
    import json
    from data_agent.agent.confirmation.service import ConfirmationAnswerError
    loop,service,cost,method,window,invoke=_s3_mixed_question_loop(tmp_path,monkeypatch,"direct")
    result=invoke([cost,method,window]);visible=json.loads(result.context);active=service.checkpoint(loop.session_id)
    row={"question_id":visible[0]["question_id"],"question":window["question"],"answer":"window7","is_free_input":False};answer=[row]
    if fault=="missing":answer=[]
    if fault=="wrong_id":row["question_id"]="unknown_question"
    if fault=="wrong_question":row["question"]="另一题"
    if fault=="bad_option":row["answer"]="not_an_option"
    if fault=="duplicate":answer=[row,row]
    if fault=="not_array":answer={"answer":"window7"}
    raw="[broken" if fault=="not_json" else json.dumps(answer,ensure_ascii=False)
    before=service._store(loop.session_id).load_records()
    with pytest.raises(ConfirmationAnswerError):service.respond(loop.session_id,active.confirmation_id,raw,active.version,"invalid")
    assert service._store(loop.session_id).load_records()==before


def test_s3_confirmed_state_action_has_one_owner_on_resume(tmp_path,monkeypatch):
    import data_agent.agent.loop as module
    from data_agent.agent.analysis_state import AnalysisSessionState
    cfg=module.get_config();monkeypatch.setattr(cfg,"sessions_dir",tmp_path/"sessions");monkeypatch.setattr(cfg,"mcp_enabled",False);monkeypatch.setattr(cfg,"skill_auto_discover",False)
    loop=AgentLoop(client=None,session_id="single_action")
    calls=[];original=AnalysisSessionState.apply_state_updates
    def observed(self,*args,**kwargs):calls.append((self.session_id,args));return original(self,*args,**kwargs)
    monkeypatch.setattr(AnalysisSessionState,"apply_state_updates",observed)
    suspended=loop._suspend_for_confirmation_request(UserConfirmationRequired(question="选择业务范围？",options=[{"label":"全表","value":"all"}],confirmation_type="scope_confirmation",state_updates='{"stage":"scope"}'),turn_id="single")
    loop._loop=lambda _text:FinalResponse(content="independent completion control")
    loop.resume_turn(suspended.confirmation_id,"all",expected_version=suspended.version,idempotency_key="once")
    assert len(calls)==1,"The service action is authoritative; the legacy post-resume adapter must not apply it again."


def test_s3_skipped_batch_item_cannot_apply_global_state_action(tmp_path,monkeypatch):
    import json
    from data_agent.agent.analysis_state import load_analysis_state
    from data_agent.agent.loop import UserConfirmationRequired
    loop,service,cost,method,window,invoke=_s3_mixed_question_loop(tmp_path,monkeypatch,"direct")
    before=load_analysis_state(loop.session_id).stage
    suspended=loop._suspend_for_confirmation_request(UserConfirmationRequired(question=window["question"],options=[],context=json.dumps([window],ensure_ascii=False),confirmation_type="metric_scope",state_updates='{"stage":"plan"}'),turn_id="skip_batch")
    visible=json.loads(suspended.context);row=visible[0]
    submitted=json.dumps([{"question_id":row["question_id"],"question":row["question"],"answer":"skipped","is_free_input":False}],ensure_ascii=False)
    resolved=service.respond(loop.session_id,suspended.confirmation_id,submitted,suspended.version,"skip_item")
    assert json.loads(resolved.response)[0]["status"]=="skipped"
    assert load_analysis_state(loop.session_id).stage==before



def _s3_bound_question_fixture(tmp_path, monkeypatch, session_id="bound_question"):
    from data_agent.tools import discover_tools
    discover_tools()  # Keep tool module imports outside a temporary manager replacement.
    import pandas as pd
    import data_agent.agent.loop as module
    import data_agent.session.task_manager as task_module
    from data_agent.agent.context import use_agent_context
    from tests.test_trusted_publication_runtime import request
    cfg=module.get_config()
    monkeypatch.setattr(cfg,"sessions_dir",tmp_path/"sessions")
    monkeypatch.setattr(cfg,"workspace_dir",tmp_path/"workspace")
    monkeypatch.setattr(cfg,"mcp_enabled",False);monkeypatch.setattr(cfg,"skill_auto_discover",False)
    manager=task_module.TaskManager(tasks_dir=tmp_path/"tasks")
    monkeypatch.setattr(task_module,"task_manager",manager)
    loop=AgentLoop(client=None,session_id=session_id)
    with use_agent_context(loop.context):
        loop.context.workspace.add("orders",pd.DataFrame({"day":pd.date_range("2026-10-01",periods=7),"amount":[10]*7}))
        request(loop,"计算orders的金额合计，窗口由我选择。",{"kind":"measurement","scope":{"datasets":["orders"],"metrics":["amount"],"quantity":"sum"}})
    loop.context.analysis_state.save()
    loop._publication_turn_id="request_one"
    return loop,manager


@pytest.mark.parametrize("route",["direct","registry","automatic"])
@pytest.mark.parametrize("mode",["same","unrelated","changed_source","wrong_permission","tampered_requirement","ambiguous_requirements","different_goal","unbound_next_request","unbound_same_request"])
def test_s3_host_bound_reuse_checks_real_request_objects_versions_and_permissions(tmp_path,monkeypatch,route,mode):
    import os,json,pandas as pd
    from pathlib import Path
    from data_agent.agent.context import use_agent_context
    from data_agent.agent.loop import SuspendedForConfirmation
    from data_agent.tools.interaction import ask_user_question
    from data_agent.tools.registry import registry
    from data_agent.tools import discover_tools
    from tests.test_trusted_publication_runtime import request
    from tests.test_stage3c0b_execution_scope import _scoped_task
    discover_tools();loop,manager=_s3_bound_question_fixture(tmp_path,monkeypatch)
    payload={"question":"当前orders表按哪个观测窗口计算合计？","options":[{"label":"10月1日至7日","value":"2026-10-01~2026-10-07"},{"label":"10月1日至14日","value":"2026-10-01~2026-10-14"}],"confirmation_type":"time_window","blocking_reason":"当前数据的统计窗口尚未确定。"}
    def invoke():
        with use_agent_context(loop.context):
            if route=="automatic":return loop._suspend_for_required_question_payload(payload,source="question_need_detector",operation="time_window")
            try:
                ask_user_question(**payload) if route=="direct" else registry.execute("ask_user_question",payload)
            except UserConfirmationRequired as question:
                return loop._suspend_for_confirmation_request(question,turn_id=loop._publication_turn_id)
            raise AssertionError("original question signal missing")
    if mode.startswith("unbound"):
        loop.context.turn_requirement_ids=[]
    first=invoke();assert isinstance(first,SuspendedForConfirmation)
    service=loop._confirmation_runtime();active=service.checkpoint(loop.session_id)
    resolved=service.respond(loop.session_id,active.confirmation_id,"2026-10-01~2026-10-07",active.version,"bound_once")
    v1=loop.context.workspace.get_data_identity("orders")
    with use_agent_context(loop.context):
        if mode=="unrelated":loop.context.workspace.add("unrelated",pd.DataFrame({"id":[99]}))
        elif mode=="changed_source":loop.context.workspace.add("orders",pd.DataFrame({"day":pd.date_range("2026-10-08",periods=7),"amount":[20]*7}))
        elif mode=="wrong_permission":
            loop.context.workspace.add("unrelated",pd.DataFrame({"id":[99]}))
            _scoped_task(manager,session_id=loop.session_id,datasets=["unrelated"],contracts=[])
        elif mode=="tampered_requirement":loop.context.analysis_state.answer_requirements[0]["source_end"]+=1
        elif mode=="ambiguous_requirements":
            old=list(loop.context.turn_requirement_ids);loop.context.workspace.add("other",pd.DataFrame({"amount":[999]}))
            request(loop,"另算other的合计。",{"kind":"measurement","scope":{"datasets":["other"],"metrics":["amount"],"quantity":"sum"}})
            loop.context.turn_requirement_ids=old+loop.context.turn_requirement_ids
        elif mode=="different_goal":
            request(loop,"改为orders的均值目标，另行选择窗口。",{"kind":"measurement","scope":{"datasets":["orders"],"metrics":["amount"],"quantity":"mean"}})
    if mode!="unbound_same_request":loop._publication_turn_id="request_two"
    result=invoke();records=service._store(loop.session_id).load_records()
    out=Path(os.environ.get("DATA_AGENT_S3_ASK_EVIDENCE",str(tmp_path/"evidence")));out.mkdir(parents=True,exist_ok=True)
    (out/("host_bound_"+route+"_"+mode+".json")).write_text(json.dumps({"route":route,"mode":mode,"source_v1":v1,"record":resolved.to_dict(),"result":vars(result) if hasattr(result,"__dict__") else result,"records":{k:v.to_dict() for k,v in records.items()},"provider_calls":0},ensure_ascii=False,indent=2,default=str),encoding="utf-8")
    if mode in {"same","unrelated","unbound_same_request"}:
        assert result is None if route=="automatic" else isinstance(result,str)
        assert len(records)==1 and service.checkpoint(loop.session_id) is None
    else:
        assert isinstance(result,SuspendedForConfirmation),"A scope key alone must not reuse an answer without current host applicability."
        assert result.confirmation_id!=active.confirmation_id
    if mode in {"same","unrelated"}:
        assert resolved.data_version and resolved.data_version!="messages:0"
        assert resolved.resolution_params["host_binding"]["objects"]["orders"]==v1


@pytest.mark.parametrize("route",["direct","registry"])
@pytest.mark.parametrize("origin",["","user_request","schema","confirmed_data","exploration_scope"])
def test_s3_model_origin_tags_cannot_supply_a_multi_question_safe_default(tmp_path,monkeypatch,route,origin):
    import json
    from data_agent.agent.context import use_agent_context
    from data_agent.agent.loop import SuspendedForConfirmation
    from data_agent.tools import discover_tools
    from data_agent.tools.interaction import ask_user_question
    from data_agent.tools.registry import registry
    discover_tools();loop,_=_s3_bound_question_fixture(tmp_path,monkeypatch)
    item={"question":"比较窗口采用近7天还是近30天？","options":[{"label":"近7天","value":"window7"},{"label":"近30天","value":"window30"}],"confirmation_type":"time_window"}
    if origin:item.update(safe_default="window7",default_origin=origin)
    args={"questions":json.dumps([item],ensure_ascii=False),"confirmation_type":"metric_scope","blocking_reason":"窗口尚未由用户选择。"}
    with use_agent_context(loop.context):
        try:ask_user_question(**args) if route=="direct" else registry.execute("ask_user_question",args)
        except UserConfirmationRequired as question:result=loop._suspend_for_confirmation_request(question,turn_id="origin")
        else:raise AssertionError("original question signal missing")
    assert isinstance(result,SuspendedForConfirmation),"A model-supplied host-origin label is not actual host evidence."
    assert json.loads(result.context)[0]["question"]==item["question"]



@pytest.mark.parametrize("route",["direct","registry","automatic"])
@pytest.mark.parametrize("mode",["same","changed_source","wrong_permission"])
def test_s3_pending_bound_answer_revalidates_before_state_action(tmp_path,monkeypatch,route,mode):
    import json,pandas as pd
    from data_agent.agent.context import use_agent_context
    from data_agent.agent.analysis_state import AnalysisSessionState
    from data_agent.agent.confirmation.models import ConfirmationStatus
    from data_agent.agent.confirmation.service import ConfirmationVersionConflict
    from data_agent.tools.interaction import ask_user_question
    from data_agent.tools.registry import registry
    from data_agent.tools import discover_tools
    from tests.test_stage3c0b_execution_scope import _scoped_task
    discover_tools();loop,manager=_s3_bound_question_fixture(tmp_path,monkeypatch)
    payload={"question":"当前orders的计算窗口是什么？","options":[{"label":"10月1日至7日","value":"window7"}],"confirmation_type":"time_window","state_updates":'{"stage":"plan"}'}
    def invoke():
        with use_agent_context(loop.context):
            if route=="automatic":return loop._suspend_for_required_question_payload(payload,source="question_need_detector",operation="time_window")
            try:ask_user_question(**payload) if route=="direct" else registry.execute("ask_user_question",payload)
            except UserConfirmationRequired as question:return loop._suspend_for_confirmation_request(question,turn_id="pending")
            raise AssertionError("original question signal missing")
    first=invoke();service=loop._confirmation_runtime();record=service.get(loop.session_id,first.confirmation_id)
    calls=[];original=AnalysisSessionState.apply_state_updates
    def observe(self,*args,**kw):calls.append(args);return original(self,*args,**kw)
    monkeypatch.setattr(AnalysisSessionState,"apply_state_updates",observe)
    with use_agent_context(loop.context):
        if mode=="changed_source":loop.context.workspace.add("orders",pd.DataFrame({"day":pd.date_range("2026-10-08",periods=7),"amount":[20]*7}))
        elif mode=="wrong_permission":
            loop.context.workspace.add("unrelated",pd.DataFrame({"id":[99]}))
            _scoped_task(manager,session_id=loop.session_id,datasets=["unrelated"],contracts=[])
        if mode=="same":
            resolved=loop._resolve_runtime_confirmation(first,"window7",expected_version=record.version,idempotency_key="pending_once")
            loop._resolve_confirmation(resolved,"window7")
            loop._resolve_runtime_confirmation(first,"window7",expected_version=record.version,idempotency_key="pending_once")
            assert len(calls)==1 and loop.context.analysis_state.stage=="plan"
        else:
            with pytest.raises(ConfirmationVersionConflict):
                loop._resolve_runtime_confirmation(first,"window7",expected_version=record.version,idempotency_key="stale_answer")
            assert calls==[]
            expired=service.get(loop.session_id,first.confirmation_id)
            assert expired.status==ConfirmationStatus.EXPIRED and expired.response is None
            events=(service._store(loop.session_id).load().events_by_id or {}).values()
            assert not any(e.event_type in {"response_received","applying","resolved"} for e in events)
            if mode=="changed_source":
                fresh=invoke();assert fresh.confirmation_id!=first.confirmation_id


@pytest.mark.parametrize("route",["cli","kernel_control"])
@pytest.mark.parametrize("multi",[False,True])
@pytest.mark.parametrize("state_action",[False,True])
@pytest.mark.parametrize("comma_values",[False,True])
def test_s3_cli_numeric_selection_keeps_original_values_before_service_action(tmp_path,monkeypatch,route,multi,state_action,comma_values):
    from data_agent.agent.context import use_agent_context
    from data_agent.agent.loop import UserConfirmationRequired,FinalResponse
    import data_agent.tools.interaction as ui
    loop,_=_s3_bound_question_fixture(tmp_path,monkeypatch)
    values=["window,7","window,30"] if comma_values else ["window7","window30"]
    payload=UserConfirmationRequired(question="orders采用哪个窗口？",options=[{"label":"近7天","value":values[0]},{"label":"近30天","value":values[1]}],multi_select=multi,confirmation_type="time_window",state_updates='{"stage":"plan"}' if state_action else '')
    expected=values if multi else values[0]
    with use_agent_context(loop.context):
        susp=loop._suspend_for_confirmation_request(payload,turn_id="cli_values")
        monkeypatch.setattr(ui,"_robust_input",lambda *a,**kw:"1,2" if multi else "1")
        # This test assesses the real collector/service boundary, not publication.
        monkeypatch.setattr(loop,"_loop",lambda *a,**kw:FinalResponse(content="focused lifecycle complete"))
        if route=="cli":assert loop._handle_cli_suspension(susp)=="focused lifecycle complete"
        else:loop._resolve_runtime_confirmation(susp,expected,expected_version=susp.version,idempotency_key="kernel_values")
        record=loop._confirmation_runtime().get(loop.session_id,susp.confirmation_id)
        assert record.response==expected
        assert record.status.value=="resolved"
        if state_action:
            from data_agent.agent.analysis_state import load_analysis_state
            assert load_analysis_state(loop.session_id).stage=="plan"


@pytest.mark.parametrize("grouped",[False,True])
@pytest.mark.parametrize("state_action",[False,True])
def test_s3_cli_mixed_selected_and_free_answer_is_preserved_and_state_gate_remains_strict(tmp_path,monkeypatch,grouped,state_action):
    import json
    from data_agent.agent.context import use_agent_context
    from data_agent.agent.loop import UserConfirmationRequired,FinalResponse
    from data_agent.agent.confirmation.service import ConfirmationAnswerError
    import data_agent.tools.interaction as ui
    loop,_=_s3_bound_question_fixture(tmp_path,monkeypatch)
    options=[{"label":"近7天","value":"window7"},{"label":"近30天","value":"window30"}]
    question={"question":"orders采用哪些范围和补充口径？","options":options,"multi_select":True,"confirmation_type":"time_window"}
    if grouped:
        from data_agent.tools.interaction import ask_user_question
        try:ask_user_question(questions=json.dumps([question],ensure_ascii=False),confirmation_type="time_window",state_updates='{"stage":"plan"}' if state_action else '')
        except UserConfirmationRequired as signal:payload=signal
        else:raise AssertionError("original multi-question signal missing")
    else:payload=UserConfirmationRequired(**question,state_updates='{"stage":"plan"}' if state_action else '')
    with use_agent_context(loop.context):
        susp=loop._suspend_for_confirmation_request(payload,turn_id="cli_mixed")
        before=loop._confirmation_runtime().get(loop.session_id,susp.confirmation_id)
        monkeypatch.setattr(ui,"_robust_input",lambda *a,**kw:"1,补充口径")
        monkeypatch.setattr(loop,"_loop",lambda *a,**kw:FinalResponse(content="focused lifecycle complete"))
        if state_action:
            with pytest.raises(ConfirmationAnswerError):loop._handle_cli_suspension(susp)
            after=loop._confirmation_runtime().get(loop.session_id,susp.confirmation_id)
            assert after.to_dict()==before.to_dict()
        else:
            loop._handle_cli_suspension(susp)
            record=loop._confirmation_runtime().get(loop.session_id,susp.confirmation_id)
            if grouped:
                rows=json.loads(record.response);assert len(rows)==1 and rows[0]["answer"]==["window7","补充口径"] and rows[0]["is_free_input"] is True
            else:assert record.response==["window7","补充口径"]


def test_s3_cli_mixed_collector_keeps_typed_values_and_explicit_free_text():
    from data_agent.tools.interaction import _process_answer
    options=[{"label":"近7天","value":"window7"},{"label":"近30天","value":"window30"}]
    result=_process_answer("1,补充口径",options,True)
    assert result["answer_values"]==["window7","补充口径"]
    assert result["answer"]=="近7天, 补充口径" and result["is_free_input"] is True


@pytest.mark.parametrize("route",["direct","registry","automatic"])
@pytest.mark.parametrize("bound",[False,True])
@pytest.mark.parametrize("new_request",[False,True])
def test_s3_pending_question_request_domain_preserves_bound_open_and_expires_only_prior_unbound(tmp_path,monkeypatch,route,bound,new_request):
    from copy import deepcopy
    from data_agent.agent.context import use_agent_context
    from data_agent.agent.loop import UserConfirmationRequired,SuspendedForConfirmation
    from data_agent.agent.confirmation.service import ConfirmationVersionConflict
    from data_agent.session.history import save_session
    from data_agent.tools.interaction import ask_user_question
    from data_agent.tools.registry import registry
    loop,_=_s3_bound_question_fixture(tmp_path,monkeypatch)
    if not bound:loop.context.turn_requirement_ids=[]
    payload={"question":"orders当前统计窗口如何定义？","options":[{"label":"近7天","value":"window7"},{"label":"近30天","value":"window30"}],"confirmation_type":"time_window","blocking_reason":"缺少当前业务窗口。"}
    def invoke():
        if route=="automatic":return loop._suspend_for_required_question_payload(payload,source="question_need_detector",operation="time_window")
        try:ask_user_question(**payload) if route=="direct" else registry.execute("ask_user_question",payload)
        except UserConfirmationRequired as signal:return loop._suspend_for_confirmation_request(signal,turn_id=loop._publication_turn_id)
        raise AssertionError("original question signal missing")
    with use_agent_context(loop.context):
        first=invoke();assert isinstance(first,SuspendedForConfirmation)
        service=loop._confirmation_runtime();original=service.get(loop.session_id,first.confirmation_id)
        requirements=deepcopy(loop.context.analysis_state.answer_requirements)
        if new_request:
            loop.messages.append({"role":"user","content":"本轮继续确认当前统计窗口。","request_id":"msg_open_new_request"})
            save_session(loop.messages,loop.session_id,merge_protect=False,extra_meta={"publication_schema":"answer_bindings.v2"})
            loop._publication_turn_id="request_two"
        second=invoke();assert isinstance(second,SuspendedForConfirmation)
        assert loop.context.analysis_state.answer_requirements==requirements
        if new_request and not bound:
            expired=service.get(loop.session_id,first.confirmation_id)
            assert expired.status.value=="expired" and expired.response is None and expired.continuation_context==original.continuation_context
            assert second.confirmation_id!=first.confirmation_id
            current=service.get(loop.session_id,second.confirmation_id)
            assert current.status.value=="suspended" and current.resolution_params["host_binding"]["request_id"]=="request_two"
            with pytest.raises(ConfirmationVersionConflict):loop._resolve_runtime_confirmation(first,"window7",expected_version=original.version,idempotency_key="stale_unbound")
            assert service.get(loop.session_id,first.confirmation_id).response is None
            loop._resolve_runtime_confirmation(second,"window7",expected_version=current.version,idempotency_key="current_unbound")
            assert service.get(loop.session_id,second.confirmation_id).response=="window7"
        else:
            assert second.confirmation_id==first.confirmation_id
            assert len(service._store(loop.session_id).load_records())==1


@pytest.mark.parametrize("route",["direct","registry"])
def test_s3_unbound_group_occurrence_expires_without_resolving_any_original_child(tmp_path,monkeypatch,route):
    import json
    from data_agent.agent.context import use_agent_context
    from data_agent.agent.loop import UserConfirmationRequired
    from data_agent.agent.confirmation.decision import resolved_question_records
    from data_agent.session.history import save_session
    from data_agent.tools.interaction import ask_user_question
    from data_agent.tools.registry import registry
    loop,_=_s3_bound_question_fixture(tmp_path,monkeypatch);loop.context.turn_requirement_ids=[]
    questions=[{"question":"成本是否包含券成本？","options":[{"label":"包含","value":"include"},{"label":"不包含","value":"exclude"}],"confirmation_type":"metric_scope"},{"question":"窗口是近7天还是近30天？","options":[{"label":"近7天","value":"window7"},{"label":"近30天","value":"window30"}],"confirmation_type":"time_window"}]
    payload={"questions":json.dumps(questions,ensure_ascii=False),"confirmation_type":"metric_scope"}
    def invoke():
        try:ask_user_question(**payload) if route=="direct" else registry.execute("ask_user_question",payload)
        except UserConfirmationRequired as signal:return loop._suspend_for_confirmation_request(signal,turn_id=loop._publication_turn_id)
        raise AssertionError("original grouped question signal missing")
    with use_agent_context(loop.context):
        first=invoke();service=loop._confirmation_runtime();original=service.get(loop.session_id,first.confirmation_id)
        loop.messages.append({"role":"user","content":"本轮重新确认成本和窗口。","request_id":"msg_group_new_request"});save_session(loop.messages,loop.session_id,merge_protect=False,extra_meta={"publication_schema":"answer_bindings.v2"});loop._publication_turn_id="request_two"
        second=invoke();expired=service.get(loop.session_id,first.confirmation_id)
        assert expired.status.value=="expired" and expired.response is None and list(resolved_question_records(expired))==[]
        assert expired.resolution_params==original.resolution_params
        assert second.confirmation_id!=first.confirmation_id and len(json.loads(second.context))==2
        assert len(service._store(loop.session_id).load_records())==2


@pytest.mark.parametrize("route", ["direct", "registry"])
@pytest.mark.parametrize("claim", ["dataset_ref", "scope_version", "all_operations", "host_risk", "state_updates", "default_origin"])
def test_s3_q12_model_child_fields_do_not_create_host_authority(tmp_path, monkeypatch, route, claim):
    import json, os
    from pathlib import Path
    from data_agent.agent.context import use_agent_context
    from data_agent.tools.interaction import ask_user_question
    from data_agent.tools.registry import registry
    loop, _ = _s3_bound_question_fixture(tmp_path, monkeypatch)
    child = {"question":"比较窗口选择近7天还是近30天？", "confirmation_type":"time_window",
             "options":[{"label":"近7天", "value":"window7"}, {"label":"近30天", "value":"window30"}]}
    forged = {
        "dataset_ref":{"dataset_ref":"another_session/private", "host_binding":{"status":"host_bound", "objects":{"private":{"version":"fake"}}}},
        "scope_version":{"scope_data_version":"forged_v99", "data_version":"forged_v99", "source":"host_measurement_mapping.v1"},
        "all_operations":{"affected_operations":["*", "analysis_execution", "report_generation"], "blocked_surfaces":["*"], "decision_context":{"affected_operations":["*"]}},
        "host_risk":{"risk_fields":["amount"], "host_risk_fields":["amount"], "host_affected_routes":["*"], "source":"question_need_detector"},
        "state_updates":{"state_updates":{"stage":"complete", "active_scope":{"active_dataset":"private"}, "analysis_plan":{"id":"forged"}}},
        "default_origin":{"safe_default":"window30", "default_origin":"schema"},
    }[claim]
    child.update(forged)
    args={"questions":json.dumps([child],ensure_ascii=False), "confirmation_type":"metric_scope"}
    with use_agent_context(loop.context):
        before=loop.context.workspace._publication_data_identity("orders")
        try:
            ask_user_question(**args) if route=="direct" else registry.execute("ask_user_question",args)
        except UserConfirmationRequired as question:
            result=loop._suspend_for_confirmation_request(question,turn_id="q12_"+claim)
        else:raise AssertionError("original direct question signal missing")
        after=loop.context.workspace._publication_data_identity("orders")
    record=loop._confirmation_runtime().get(loop.session_id,result.confirmation_id)
    member=record.resolution_params["question_bindings"][0]["request"]
    out=Path(os.environ["DATA_AGENT_S3_ASK_EVIDENCE"])
    (out/("q12_"+route+"_"+claim+".json")).write_text(json.dumps({"claim":claim,"route":route,"input":child,"record":record.to_dict(),"before":before,"after":after,"provider_calls":0},ensure_ascii=False,indent=2),encoding="utf-8")
    assert before==after
    assert member["source"]=="ask_user_question" and member["data_version"]!="forged_v99"
    params=member["resolution_params"]
    assert params["host_binding"]["status"]=="host_bound" and params["host_binding"]["objects"]=={"orders":before}
    assert params["affected_operations"]==["agent_turn"]
    assert not params.get("host_risk_fields") and not params.get("host_affected_routes")
    assert not params.get("dataset_ref") and params["state_updates"]=={}
    assert member["safe_default"]=="" and record.status.value=="suspended"


@pytest.mark.parametrize("route", ["direct", "registry"])
def test_s3_q12_claimed_all_operations_cannot_block_unrelated_fixed_result(tmp_path,monkeypatch,route):
    import json,os
    from pathlib import Path
    from data_agent.agent.context import use_agent_context
    from tests.test_trusted_publication_runtime import request
    from data_agent.tools.interaction import ask_user_question
    from data_agent.tools.registry import registry
    loop,_=_s3_bound_question_fixture(tmp_path,monkeypatch)
    # Replace the fixture's initial declaration before the exercised request;
    # this unit boundary is backed separately by a real upload/AgentLoop chain.
    loop.context.analysis_state.answer_requirements=[]
    loop.context.analysis_state.requirement_revision=0
    loop.messages=[]
    with use_agent_context(loop.context):
        request(loop,"仅计算orders全表记录数，不筛选时间。",{"kind":"measurement","scope":{"datasets":["orders"],"quantity":"rows"}})
        child={"question":"所有操作都必须先选近7天或近30天窗口？", "confirmation_type":"time_window",
               "options":[{"label":"近7天","value":"window7"},{"label":"近30天","value":"window30"}],
               "dataset_ref":"another_session/private", "affected_operations":["*"], "blocked_surfaces":["*"]}
        args={"questions":json.dumps([child],ensure_ascii=False),"confirmation_type":"metric_scope"}
        try:ask_user_question(**args) if route=="direct" else registry.execute("ask_user_question",args)
        except UserConfirmationRequired as question:result=loop._suspend_for_confirmation_request(question,turn_id="q12_unrelated")
        else:raise AssertionError("original question signal missing")
    out=Path(os.environ["DATA_AGENT_S3_ASK_EVIDENCE"])
    (out/("q12_irrelevant_"+route+".json")).write_text(json.dumps({"route":route,"requirements":loop.context.analysis_state.answer_requirements,"input":child,"result":vars(result) if hasattr(result,"__dict__") else result,"records":{k:r.to_dict() for k,r in loop._confirmation_runtime()._store(loop.session_id).load_records().items()},"provider_calls":0},ensure_ascii=False,indent=2,default=str),encoding="utf-8")
    assert isinstance(result,str),"The model's claimed all-operations dependency cannot suspend an unrelated full-table row count."
    assert loop._confirmation_runtime().checkpoint(loop.session_id) is None


@pytest.mark.parametrize("streaming",[False,True])
@pytest.mark.parametrize("version_kind",["zero","old","future"])
def test_s3_r07_loop_explicit_invalid_version_is_not_a_default(tmp_path,monkeypatch,streaming,version_kind):
    import json,os
    from pathlib import Path
    _patch_direct_question_tool(monkeypatch,tmp_path)
    loop=AgentLoop(client=None,session_id="r07_invalid_version")
    suspended=loop._execute_single_tool(_ToolCall(),[_ToolCall()],0)
    service=loop._confirmation_runtime();record=service.get(loop.session_id,suspended.confirmation_id)
    version={"zero":0,"old":record.version-1,"future":record.version+1}[version_kind]
    calls=[]
    loop._loop=lambda value:calls.append(value) or FinalResponse(content="should not continue")
    def stream(value):calls.append(value);yield {"type":"text_delta","text":"should not continue"}
    monkeypatch.setattr(loop,"_stream_analysis_loop",stream)
    if streaming:result=list(loop.resume_turn_streaming(record.confirmation_id,"revenue",expected_version=version,idempotency_key="invalid_once"))
    else:result=loop.resume_turn(record.confirmation_id,"revenue",expected_version=version,idempotency_key="invalid_once")
    after=service.get(loop.session_id,record.confirmation_id)
    out=Path(os.environ["DATA_AGENT_S3_ASK_EVIDENCE"])
    (out/(f"r07_adapter_{streaming}_{version_kind}.json")).write_text(json.dumps({"before":record.to_dict(),"after":after.to_dict(),"version":version,"streaming":streaming,"result":vars(result) if hasattr(result,"__dict__") else result,"calls":calls,"provider_calls":0},indent=2),encoding="utf-8")
    assert after==record and calls==[],"An explicit invalid version must not be replaced with the current version."
    assert any(e["type"]=="error" for e in result) if streaming else result.content.startswith("Error:")


@pytest.mark.parametrize("route",["direct","registry"])
@pytest.mark.parametrize("mode",["filtered_rows","missing_delivery","mixed_deliveries","changed_source","state_action"])
def test_s3_q12_host_irrelevance_requires_exact_original_count_scope(tmp_path,monkeypatch,route,mode):
    import json,os
    from pathlib import Path
    from data_agent.agent.context import use_agent_context
    from tests.test_trusted_publication_runtime import request
    from data_agent.tools.interaction import ask_user_question
    from data_agent.tools.registry import registry
    loop,_=_s3_bound_question_fixture(tmp_path,monkeypatch)
    loop.context.analysis_state.answer_requirements=[];loop.context.analysis_state.requirement_revision=0;loop.messages=[]
    scope={"datasets":["orders"],"quantity":"rows"}
    if mode=="filtered_rows":scope["parameters"]={"period_a":"2026-10-01~2026-10-07"}
    with use_agent_context(loop.context):
        request(loop,"计算orders指定业务范围的记录数，范围仍需确定。",{"kind":"measurement","scope":scope})
        required=loop.context.analysis_state.answer_requirements[0]
        if mode=="missing_delivery":required["necessary_deliveries"]=[]
        if mode=="mixed_deliveries":required["necessary_deliveries"].append({"kind":"measurement","scope":{"datasets":["orders"],"metrics":["amount"],"quantity":"sum"}})
        if mode=="changed_source":required["source_data_identities"]["orders"]["fingerprint"]="forged_current_source"
        args={"question":"比较窗口选择近7天还是近30天？","confirmation_type":"time_window","options":[{"label":"近7天","value":"window7"},{"label":"近30天","value":"window30"}]}
        if mode=="state_action":args["state_updates"]='{"stage":"scope"}'
        try:ask_user_question(**args) if route=="direct" else registry.execute("ask_user_question",args)
        except UserConfirmationRequired as question:result=loop._suspend_for_confirmation_request(question,turn_id="q12_proof_control")
        else:raise AssertionError("original question signal missing")
    record=loop._confirmation_runtime().get(loop.session_id,result.confirmation_id)
    out=Path(os.environ["DATA_AGENT_S3_ASK_EVIDENCE"])
    (out/(f"q12_proof_{route}_{mode}.json")).write_text(json.dumps({"route":route,"mode":mode,"requirement":required,"record":record.to_dict(),"provider_calls":0},ensure_ascii=False,indent=2),encoding="utf-8")
    assert record.status.value=="suspended" and not record.resolution_params.get("host_nonblocking_reason")


@pytest.mark.parametrize("route", ["direct", "registry", "automatic"])
def test_s3_r09_concurrent_bound_adapters_have_one_pending_card(tmp_path, monkeypatch, route):
    from concurrent.futures import ThreadPoolExecutor
    from contextvars import copy_context
    from threading import Barrier
    import json, os
    from pathlib import Path
    from data_agent.agent.context import use_agent_context
    from data_agent.agent.loop import SuspendedForConfirmation
    from data_agent.tools.interaction import ask_user_question
    from data_agent.tools.registry import registry
    loop,_=_s3_bound_question_fixture(tmp_path,monkeypatch,session_id="r09_"+route)
    payload={"question":"金额合计使用近7天还是近30天？","confirmation_type":"time_window",
             "options":[{"label":"近7天","value":"window7"},{"label":"近30天","value":"window30"}]}
    service=loop._confirmation_runtime();barrier=Barrier(2)
    def arrive(index):
        with use_agent_context(loop.context):
            barrier.wait(timeout=10)
            if route == "automatic":
                return loop._suspend_for_required_question_payload(payload,source="question_need_detector",operation="time_window")
            try:
                ask_user_question(**payload) if route=="direct" else registry.execute("ask_user_question",payload)
            except UserConfirmationRequired as question:
                return loop._suspend_for_confirmation_request(question,turn_id="arrival_"+str(index))
            raise AssertionError("Original question producer did not signal")
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(copy_context().run,arrive,index) for index in range(2)]
        results=[f.result(timeout=20) for f in futures]
    loaded=service._store(loop.session_id).load();active=service.checkpoint(loop.session_id)
    out=Path(os.environ["DATA_AGENT_S3_ASK_EVIDENCE"])
    (out/("r09_adapters_"+route+".json")).write_text(json.dumps({"route":route,"results":[vars(r) if hasattr(r,"__dict__") else str(r) for r in results],"records":{k:v.to_dict() for k,v in loaded.records.items()},"events":[e.to_dict() for e in loaded.events_by_id.values()],"provider_calls":0},ensure_ascii=False,indent=2,default=str),encoding="utf-8")
    assert all(isinstance(r,SuspendedForConfirmation) for r in results)
    assert {r.confirmation_id for r in results}=={active.confirmation_id} and len(loaded.records)==1
    assert [e.event_type for e in loaded.events_by_id.values()]==["requested","suspended"]
    assert active.resolution_params["host_binding"]["status"]=="host_bound" and active.response is None


@pytest.mark.parametrize("route", ["signal", "direct", "registry"])
def test_s3_q12_top_mapping_does_not_discard_material_batch_question(tmp_path, monkeypatch, route):
    import json, os
    from pathlib import Path
    from data_agent.agent.context import use_agent_context
    from data_agent.agent.loop import SuspendedForConfirmation
    from data_agent.tools.interaction import ask_user_question
    from data_agent.tools.registry import registry
    loop,_=_s3_bound_question_fixture(tmp_path,monkeypatch,session_id="q12_mixed_"+route)
    child={"question":"金额合计使用近7天还是近30天？","confirmation_type":"time_window",
           "options":[{"label":"近7天","value":"window7"},{"label":"近30天","value":"window30"}]}
    mapping={"exact_span":"金额合计","dataset":"orders","column":"amount"}
    args={"questions":json.dumps([child],ensure_ascii=False),"measurement_mapping":json.dumps(mapping,ensure_ascii=False)}
    with use_agent_context(loop.context):
        if route=="signal":
            result=loop._suspend_for_confirmation_request(UserConfirmationRequired(question=child["question"],options=[],context=args["questions"],measurement_mapping=args["measurement_mapping"]),turn_id="mixed_mapping")
        else:
            try:
                ask_user_question(**args) if route=="direct" else registry.execute("ask_user_question",args)
            except UserConfirmationRequired as question:
                result=loop._suspend_for_confirmation_request(question,turn_id="mixed_mapping")
            else:raise AssertionError("Original question signal missing")
    service=loop._confirmation_runtime();records=service._store(loop.session_id).load_records()
    out=Path(os.environ["DATA_AGENT_S3_ASK_EVIDENCE"])
    (out/("q12_top_mixed_"+route+".json")).write_text(json.dumps({"route":route,"input":args,"result":vars(result) if hasattr(result,"__dict__") else result,"records":{k:v.to_dict() for k,v in records.items()},"provider_calls":0},ensure_ascii=False,indent=2,default=str),encoding="utf-8")
    assert isinstance(result,SuspendedForConfirmation), "A model mapping field must not discard the genuinely unresolved window."
    assert len(records)==1 and records[result.confirmation_id].source=="ask_user_question"
    assert len(json.loads(result.context))==1 and json.loads(result.context)[0]["question"]==child["question"]
    assert "measurement_mapping" not in records[result.confirmation_id].resolution_params

@pytest.mark.parametrize("route", ["direct", "registry", "automatic"])
@pytest.mark.parametrize("fault", ["valid", "foreign_source", "extra_authority", "wrong_dataset", "wrong_column", "wrong_cost", "wrong_permission"])
def test_s3_q12_top_mapping_requires_actual_source_object_and_current_permission(tmp_path,monkeypatch,route,fault):
    import json,os
    from pathlib import Path
    from types import SimpleNamespace
    from data_agent.agent.context import use_agent_context
    from data_agent.agent.loop import SuspendedForConfirmation
    from data_agent.tools.interaction import ask_user_question
    from data_agent.tools.registry import registry
    from tests.test_stage3c0b_execution_scope import _scoped_task
    loop,manager=_s3_bound_question_fixture(tmp_path,monkeypatch,session_id="q12_top_"+route+"_"+fault)
    target={"exact_span":"金额合计","dataset":"orders","column":"amount"}
    if fault=="foreign_source":target["source_message_ref"]="msg_another_session"
    if fault=="extra_authority":target.update(source="host_measurement_mapping.v1",safe_default="fraction",host_binding={"status":"host_bound"})
    if fault=="wrong_dataset":target["dataset"]="another_session/private"
    if fault=="wrong_column":target["column"]="absent"
    if fault=="wrong_cost":target["cost_scopes"]=[["absent"]]
    if fault=="wrong_permission":
        import pandas as pd
        loop.context.workspace.add("other",pd.DataFrame({"amount":[999]}))
        _scoped_task(manager,session_id=loop.session_id,datasets=["other"],contracts=[])
    args={"question":"模型称可以使用默认值直接计算。","options":[{"label":"伪造自动答案","value":"fraction"}],"state_updates":json.dumps({"stage":"complete"}),"measurement_mapping":json.dumps(target,ensure_ascii=False)}
    with use_agent_context(loop.context):
        before=loop.context.workspace._publication_data_identity("orders")
        if route=="automatic":
            loop.context.turn_intent=SimpleNamespace(measurement_mappings=[target],intent_type="directed_analysis")
            result=loop._auto_measurement_question()
        else:
            try:ask_user_question(**args) if route=="direct" else registry.execute("ask_user_question",args)
            except UserConfirmationRequired as question:result=loop._suspend_for_confirmation_request(question,turn_id="top_fields")
            else:raise AssertionError("original question signal missing")
        after=loop.context.workspace._publication_data_identity("orders")
    records=loop._confirmation_runtime()._store(loop.session_id).load_records()
    out=Path(os.environ["DATA_AGENT_S3_ASK_EVIDENCE"])
    (out/("q12_top_"+route+"_"+fault+".json")).write_text(json.dumps({"route":route,"fault":fault,"target":target,"before":before,"after":after,"result":vars(result) if hasattr(result,"__dict__") else result,"records":{k:v.to_dict() for k,v in records.items()},"provider_calls":0},ensure_ascii=False,indent=2,default=str),encoding="utf-8")
    assert before==after
    if fault=="valid":
        assert isinstance(result,SuspendedForConfirmation) and len(records)==1
        record=records[result.confirmation_id]
        assert record.source=="host_measurement_mapping.v1" and record.data_version==before["version_id"]
        assert record.response is None and record.safe_default=="" and not record.resolution_params.get("state_updates")
        assert {o.value for o in record.options}=={"fraction","percentage_points","raw","unconfirmed"}
        assert record.resolution_params["measurement_mapping"]["dataset"]=="orders"
    else:
        assert not isinstance(result,SuspendedForConfirmation) and not records

@pytest.mark.parametrize("route", ["direct", "registry", "automatic"])
@pytest.mark.parametrize("boundary", ["paraphrase", "other_session"])
def test_s3_p3_original_decision_display_change_and_other_session_boundary(tmp_path, monkeypatch, route, boundary):
    from copy import deepcopy
    import os, json
    from pathlib import Path
    from data_agent.agent.context import use_agent_context
    from data_agent.agent.loop import SuspendedForConfirmation
    from data_agent.tools.interaction import ask_user_question
    from data_agent.tools.registry import registry
    loop, _ = _s3_bound_question_fixture(tmp_path, monkeypatch, session_id="original_scope")
    payload = {"question": "当前orders表按哪个观测窗口计算合计？", "confirmation_type": "time_window", "blocking_reason": "统计窗口尚未确定。", "options": [{"label": "10月1日至7日", "value": "2026-10-01~2026-10-07"}, {"label": "10月1日至14日", "value": "2026-10-01~2026-10-14"}]}
    def invoke(target, args):
        with use_agent_context(target.context):
            if route == "automatic": return target._suspend_for_required_question_payload(args, source="question_need_detector", operation="time_window")
            try:
                ask_user_question(**args) if route == "direct" else registry.execute("ask_user_question", args)
            except UserConfirmationRequired as signal:
                return target._suspend_for_confirmation_request(signal, turn_id=target._publication_turn_id)
            raise AssertionError("original signal missing")
    first = invoke(loop, payload); assert isinstance(first, SuspendedForConfirmation)
    service = loop._confirmation_runtime(); active = service.checkpoint(loop.session_id)
    resolved = service.respond(loop.session_id, active.confirmation_id, payload["options"][0]["value"], active.version, "original_answer")
    assert resolved.resolution_params["host_binding"]["status"] == "host_bound"
    target = loop
    changed = deepcopy(payload)
    if boundary == "other_session":
        target, _ = _s3_bound_question_fixture(tmp_path, monkeypatch, session_id="other_scope")
    else:
        changed["question"] = "这次金额合计采用哪段统计时间范围？"
        changed["options"][0]["label"] = "第一周"
        changed["options"][1]["label"] = "前两周"
    changed["reuse_decision_id"] = resolved.confirmation_id
    target._publication_turn_id = "new_occurrence"
    result = invoke(target, changed)
    records = target._confirmation_runtime()._store(target.session_id).load_records()
    proof = {"route": route, "boundary": boundary, "original": resolved.to_dict(), "question": changed, "records": {k: v.to_dict() for k, v in records.items()}, "result": vars(result) if hasattr(result, "__dict__") else result, "Provider": 0}
    out = Path(os.environ["DATA_AGENT_S3_ASK_EVIDENCE"])
    (out / ("original_decision_" + boundary + "_" + route + ".json")).write_text(json.dumps(proof, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    if boundary == "other_session":
        assert isinstance(result, SuspendedForConfirmation) and len(records) == 1
        assert target.session_id != loop.session_id and next(iter(records.values())).response is None
        assert service.get(loop.session_id, active.confirmation_id) == resolved
    else:
        assert result is None if route == "automatic" else isinstance(result, str)
        assert len(records) == 1 and target._confirmation_runtime().checkpoint(target.session_id) is None


@pytest.mark.parametrize("fault", ["missing_ref", "unknown_ref", "changed_options", "changed_kind", "changed_data", "new_state_action", "unbound", "skipped"])
def test_s3_p3_explicit_decision_reference_cannot_create_authority(tmp_path, monkeypatch, fault):
    from copy import deepcopy
    import pandas as pd
    from data_agent.agent.context import use_agent_context
    from data_agent.agent.loop import SuspendedForConfirmation
    loop, _ = _s3_bound_question_fixture(tmp_path, monkeypatch)
    if fault == "unbound": loop.context.turn_requirement_ids = []
    options = [{"label": "first week", "value": "7"}, {"label": "two weeks", "value": "14"}]
    original = UserConfirmationRequired(question="Choose original window", options=options, confirmation_type="time_window")
    first = loop._suspend_for_confirmation_request(original, turn_id="first")
    service = loop._confirmation_runtime(); active = service.checkpoint(loop.session_id)
    if fault == "skipped": service.skip(loop.session_id, active.confirmation_id, active.version, "skip")
    else: service.respond(loop.session_id, active.confirmation_id, "7", active.version, "answered")
    payload = {"question": "Rephrased original time scope", "options": deepcopy(options), "confirmation_type": "time_window", "reuse_decision_id": active.confirmation_id}
    if fault == "missing_ref": payload.pop("reuse_decision_id")
    elif fault == "unknown_ref": payload["reuse_decision_id"] = "unknown"
    elif fault == "changed_options": payload["options"][1]["value"] = "30"
    elif fault == "changed_kind": payload["confirmation_type"] = "metric_scope"
    elif fault == "changed_data":
        with use_agent_context(loop.context): loop.context.workspace.add("orders", pd.DataFrame({"amount": [999]}))
    elif fault == "new_state_action": payload["state_updates"] = '{"stage":"plan"}'
    loop._publication_turn_id = "second_request"
    before = loop.context.analysis_state.to_dict()
    result = loop._suspend_for_confirmation_request(UserConfirmationRequired(**payload), turn_id="second")
    assert isinstance(result, SuspendedForConfirmation) and result.confirmation_id != first.confirmation_id
    assert loop.context.analysis_state.stage == before["stage"]
    assert service.get(loop.session_id, active.confirmation_id).response == ("skipped" if fault == "skipped" else "7")


@pytest.mark.parametrize("reference_kind", ["child", "parent", "group"])
def test_s3_p3_group_reuse_keeps_original_question_identity(tmp_path, monkeypatch, reference_kind):
    import json
    from data_agent.agent.loop import SuspendedForConfirmation
    loop, _ = _s3_bound_question_fixture(tmp_path, monkeypatch)
    options = [{"label": "7 days", "value": "7"}, {"label": "14 days", "value": "14"}]
    questions = [{"question": label, "options": options, "confirmation_type": "time_window"} for label in ("Original prior window?", "Original later window?")]
    first = loop._suspend_for_confirmation_request(UserConfirmationRequired(question="Original windows", options=[], context=json.dumps(questions)), turn_id="first")
    visible = json.loads(first.context)
    answer = json.dumps([{"question_id": q["question_id"], "question": q["question"], "answer": str(7*(i+1)), "is_free_input": False} for i,q in enumerate(visible)])
    service = loop._confirmation_runtime(); active = service.checkpoint(loop.session_id)
    service.respond(loop.session_id, active.confirmation_id, answer, active.version, "original_both")
    original_events = service._store(loop.session_id).events_path.read_bytes()
    loop._publication_turn_id = "second_request"
    if reference_kind == "group":
        changed = [dict(q, question="Display change "+str(i), reuse_decision_id=visible[i]["question_id"]) for i,q in enumerate(questions)]
        request = UserConfirmationRequired(question="Changed display", options=[], context=json.dumps(changed))
    else:
        request = UserConfirmationRequired(question="Display change", options=options, confirmation_type="time_window", reuse_decision_id=active.confirmation_id if reference_kind == "parent" else visible[0]["question_id"])
    result = loop._suspend_for_confirmation_request(request, turn_id="second")
    if reference_kind == "parent":
        assert isinstance(result, SuspendedForConfirmation)
    else:
        assert isinstance(result, str) and "Original prior window?" in result
        if reference_kind == "child": assert "Original later window?" not in result and '"7"' in result
        assert service._store(loop.session_id).events_path.read_bytes() == original_events
        assert len(service._store(loop.session_id).load_records()) == 1
