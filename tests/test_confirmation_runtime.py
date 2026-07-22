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
        resolution_params={"confirmation_type": confirmation_type},
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


def test_dataset_transformation_candidate_binds_the_proposal_versions():
    from data_agent.agent.confirmation.runtime import build_dataset_transformation_candidate

    candidate = build_dataset_transformation_candidate(
        session_id="session_1",
        turn_id="turn_1",
        proposal_ref={
            "proposal_id": "proposal_123",
            "artifact_path": "sessions/session_1/tool_outputs/proposal_123_detail.json",
            "data_version": "dataset:dataset_orders_v2:sha256:source",
            "spec_version": "transformation:proposal_fingerprint",
            "candidate_fingerprint": "sha256:candidate",
        },
    )

    assert candidate.resolution_action == "approve_dataset_transformation"
    assert candidate.data_version == "dataset:dataset_orders_v2:sha256:source"
    assert candidate.spec_version == "transformation:proposal_fingerprint"
    assert candidate.resolution_params["proposal_id"] == "proposal_123"
    assert candidate.resolution_params["candidate_fingerprint"] == "sha256:candidate"


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

    assert result is not None
    assert result.confirmation_type == "method_confirmation"
    assert result.question == "Confirm the method?"


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


def test_resume_turn_marks_confirmation_resume_for_publish_audit(tmp_path, monkeypatch):
    _patch_direct_question_tool(monkeypatch, tmp_path)
    loop = AgentLoop(client=None, session_id="resume_publish_audit")
    suspended = loop._execute_single_tool(_ToolCall(), [_ToolCall()], 0)
    observed = {}

    def _loop_after_resume(_user_input):
        observed["resumed"] = loop._turn_resumed_from_confirmation
        return FinalResponse(content="done")

    loop._loop = _loop_after_resume

    result = loop.resume_turn(
        suspended.confirmation_id,
        "revenue",
        expected_version=suspended.version,
        idempotency_key="resume_publish_audit_key",
    )

    assert result == FinalResponse(content="done")
    assert observed == {"resumed": True}


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
    loop._gate_final_analysis_answer = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        AssertionError("confirmation guard must run before final-answer audit")
    )

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
    loop._gate_final_analysis_answer = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        AssertionError("confirmation guard must run before final-answer audit")
    )

    events = list(loop.stream_turn("analyze data"))
    suspended = [event for event in events if event["type"] == "suspended"][0]

    assert suspended["confirmation_id"] == suspended["suspension_id"]
    assert suspended["question"] == "Confirm stream route?"
