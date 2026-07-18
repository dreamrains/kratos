"""Runtime adapters that connect direct questions to the confirmation kernel."""

from __future__ import annotations

from typing import Any
import hashlib
import json

from data_agent.agent.confirmation.models import (
    AnswerMode,
    ConfirmationContractError,
    ConfirmationOption,
    ConfirmationRecord,
    FREE_TEXT_ANSWER_ACTIONS,
    QuestionCandidate,
)
from data_agent.agent.confirmation_policy import (
    OBSOLETE_CONFIRMATION_TYPES,
    is_obsolete_confirmation_record,
)
from data_agent.agent.confirmation.actions import (
    ResolutionActionRegistry,
    ResolutionContext,
)


def build_direct_question_candidate(
    *,
    session_id: str,
    turn_id: str,
    message_version: int,
    request: Any,
) -> QuestionCandidate:
    """Convert a direct ask_user_question signal into a policy candidate."""

    return _build_question_candidate(
        session_id=session_id,
        turn_id=turn_id,
        message_version=message_version,
        request=request,
        source="ask_user_question",
        operation="direct_user_question",
        id_prefix="direct",
    )


def build_required_question_candidate(
    *,
    session_id: str,
    turn_id: str,
    message_version: int,
    request: Any,
    source: str,
    operation: str,
) -> QuestionCandidate:
    """Convert an automatic hard-question signal into a policy candidate."""

    return _build_question_candidate(
        session_id=session_id,
        turn_id=turn_id,
        message_version=message_version,
        request=request,
        source=source,
        operation=operation,
        id_prefix="auto",
    )


def build_dataset_transformation_candidate(
    *,
    session_id: str,
    turn_id: str,
    proposal_ref: dict[str, Any],
) -> QuestionCandidate:
    """Create the canonical confirmation request for one persisted data proposal."""
    proposal_id = str(proposal_ref.get("proposal_id") or "").strip()
    data_version = str(proposal_ref.get("data_version") or "").strip()
    spec_version = str(proposal_ref.get("spec_version") or "").strip()
    candidate_fingerprint = str(proposal_ref.get("candidate_fingerprint") or "").strip()
    if not proposal_id or not data_version or not spec_version or not candidate_fingerprint:
        raise ConfirmationContractError("dataset transformation proposal reference is incomplete")
    identity = hashlib.sha256(
        json.dumps(
            {"session_id": session_id, "turn_id": turn_id, "proposal_id": proposal_id, "data_version": data_version, "spec_version": spec_version, "candidate_fingerprint": candidate_fingerprint},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return QuestionCandidate(
        confirmation_id=f"transform_{identity[:24]}",
        session_id=session_id,
        turn_id=turn_id,
        decision_key=f"{session_id}:dataset_transformation:{proposal_id}",
        source="data_cleaning",
        operation="dataset_transformation",
        question="Apply the proposed data transformation?",
        decision_impact="This change creates a new analysis dataset version.",
        answer_mode=AnswerMode.SINGLE_SELECT,
        options=(ConfirmationOption("Approve", "approve"), ConfirmationOption("Reject", "reject")),
        blocking_surfaces=("analysis_execution",),
        skippable=True,
        resolution_action="approve_dataset_transformation",
        resolution_params={
            "proposal_id": proposal_id,
            "artifact_path": str(proposal_ref.get("artifact_path") or ""),
            "data_version": data_version,
            "spec_version": spec_version,
            "candidate_fingerprint": candidate_fingerprint,
        },
        data_version=data_version,
        spec_version=spec_version,
    )


def _build_question_candidate(
    *,
    session_id: str,
    turn_id: str,
    message_version: int,
    request: Any,
    source: str,
    operation: str,
    id_prefix: str,
) -> QuestionCandidate:
    confirmation_type = str(_request_value(request, "confirmation_type", "") or "").strip()
    raw_state_updates = _state_updates(_request_value(request, "state_updates", ""))
    obsolete_request = {
        "operation": operation,
        "resolution_params": {
            "confirmation_type": confirmation_type,
            "state_updates": raw_state_updates,
        },
    }
    if is_obsolete_confirmation_record(obsolete_request):
        if confirmation_type in OBSOLETE_CONFIRMATION_TYPES:
            detail = f"type is not actionable: {confirmation_type}"
        else:
            detail = "request is not actionable"
        raise ConfirmationContractError(
            f"obsolete confirmation {detail}"
        )
    identity = _question_identity(
        session_id,
        turn_id,
        message_version,
        request,
        source=source,
        operation=operation,
    )
    options = _normalise_options(_request_value(request, "options", ()))
    answer_mode = _answer_mode(options, bool(_request_value(request, "multi_select", False)))
    resolution_params = _resolution_params_for(request)
    return QuestionCandidate(
        confirmation_id=f"{id_prefix}_{identity[:24]}",
        session_id=session_id,
        turn_id=turn_id,
        decision_key=f"{session_id}:{operation}:{identity}",
        source=source,
        operation=operation,
        question=str(_request_value(request, "question", "") or "").strip(),
        decision_impact=(
            str(_request_value(request, "blocking_reason", "") or "").strip()
            or "The current agent turn cannot continue without this answer."
        ),
        answer_mode=answer_mode,
        options=options,
        blocking_surfaces=("agent_turn",),
        skippable=True,
        resolution_action=_resolution_action_for(request),
        resolution_params=resolution_params,
        data_version=f"messages:{int(message_version)}",
        spec_version=str(_request_value(request, "related_spec_id", "") or "").strip(),
    )


def confirmation_record_to_suspended_event(record: ConfirmationRecord) -> dict[str, Any]:
    params = dict(record.resolution_params)
    return {
        "type": "suspended",
        "confirmation_id": record.confirmation_id,
        "suspension_id": record.confirmation_id,
        "version": record.version,
        "question": record.question,
        "options": [option.to_dict() for option in record.options],
        "context": str(params.get("context") or ""),
        "multi_select": record.answer_mode == AnswerMode.MULTI_SELECT,
        "allow_free_text": _allows_free_text(record),
        "confirmation_type": str(params.get("confirmation_type") or ""),
        "blocking_reason": record.decision_impact,
        "related_task_id": int(params.get("related_task_id") or 0),
        "related_spec_id": str(params.get("related_spec_id") or ""),
    }


def _allows_free_text(record: ConfirmationRecord) -> bool:
    """Whether the UI may offer a free-text answer for this confirmation.

    True for FREE_TEXT questions and for SINGLE_SELECT / MULTI_SELECT questions
    whose answer is only recorded (e.g. ask_user_question). False for
    state-driving selects (set_analysis_stage / confirm_method / ...), whose
    action needs specific option values. Kept consistent with
    service._validate_answer via the shared FREE_TEXT_ANSWER_ACTIONS set.
    """
    if record.answer_mode == AnswerMode.FREE_TEXT:
        return True
    if record.resolution_action in FREE_TEXT_ANSWER_ACTIONS:
        return record.answer_mode in (AnswerMode.SINGLE_SELECT, AnswerMode.MULTI_SELECT)
    return False


def confirmation_record_to_session_payload(record: ConfirmationRecord) -> dict[str, Any]:
    payload = confirmation_record_to_suspended_event(record)
    payload["status"] = record.status.value
    payload["skippable"] = bool(record.skippable)
    return payload


def confirmation_session_state(service: Any, session_id: str) -> dict[str, Any]:
    from data_agent.agent.confirmation.models import ConfirmationStatus

    records = service._store(session_id).load_records()
    active = None
    queued = 0
    failed = 0
    for record in records.values():
        if is_obsolete_confirmation_record(record):
            continue
        if record.status == ConfirmationStatus.SUSPENDED and active is None:
            active = confirmation_record_to_session_payload(record)
        elif record.status == ConfirmationStatus.PENDING:
            queued += 1
        elif record.status == ConfirmationStatus.FAILED:
            failed += 1
            if active is None:
                active = confirmation_record_to_session_payload(record)
    return {
        "active_confirmation": active,
        "queued_confirmation_count": queued,
        "failed_confirmation_count": failed,
    }


def confirmation_record_to_loop_result(
    record: ConfirmationRecord,
    snapshot: dict[str, Any],
) -> Any:
    from data_agent.agent.loop import SuspendedForConfirmation

    event = confirmation_record_to_suspended_event(record)
    return SuspendedForConfirmation(
        suspension_id=record.confirmation_id,
        confirmation_id=record.confirmation_id,
        version=record.version,
        question=record.question,
        options=event["options"],
        context=event["context"],
        snapshot=snapshot,
        state_updates=json.dumps(
            dict(record.resolution_params.get("state_updates") or {}),
            ensure_ascii=False,
        ),
        multi_select=event["multi_select"],
        allow_free_text=event["allow_free_text"],
        confirmation_type=event["confirmation_type"],
        blocking_reason=event["blocking_reason"],
        related_task_id=event["related_task_id"],
        related_spec_id=event["related_spec_id"],
    )


def build_action_registry() -> ResolutionActionRegistry:
    registry = ResolutionActionRegistry()
    registry.register("record_confirmation_answer", _record_confirmation_answer)
    registry.register(
        "approve_dataset_transformation",
        _record_dataset_transformation_approval,
        validator=lambda _context, answer: answer in {"approve", "reject"},
    )
    registry.register(
        "set_analysis_stage",
        _apply_state_update_action,
        validator=_validate_stage_action,
    )
    registry.register(
        "confirm_method",
        _apply_state_update_action,
        validator=_validate_method_action,
    )
    return registry


def _record_dataset_transformation_approval(
    context: ResolutionContext,
    answer: Any,
) -> dict[str, Any]:
    """Record the exact approval subject; candidate computation stays in data_clean."""
    return {
        "confirmation_id": context.confirmation_id,
        "proposal_id": str(context.parameters.get("proposal_id") or ""),
        "data_version": str(context.parameters.get("data_version") or ""),
        "spec_version": str(context.parameters.get("spec_version") or ""),
        "candidate_fingerprint": str(context.parameters.get("candidate_fingerprint") or ""),
        "approved": answer == "approve",
    }


def _answer_mode(
    options: tuple[ConfirmationOption, ...],
    multi_select: bool,
) -> AnswerMode:
    if not options:
        return AnswerMode.FREE_TEXT
    if multi_select:
        return AnswerMode.MULTI_SELECT
    return AnswerMode.SINGLE_SELECT


def _record_confirmation_answer(
    context: ResolutionContext,
    answer: Any,
) -> dict[str, Any]:
    return {
        "confirmation_id": context.confirmation_id,
        "question": str(context.parameters.get("question") or ""),
        "answer": answer,
    }


def _apply_state_update_action(
    context: ResolutionContext,
    answer: Any,
) -> dict[str, Any]:
    updates = context.parameters.get("state_updates")
    if not isinstance(updates, dict):
        updates = {}
    from data_agent.agent.analysis_state import load_analysis_state

    state = load_analysis_state(context.session_id)
    state.apply_state_updates(updates, answer=answer)
    state.save()
    return {
        "confirmation_id": context.confirmation_id,
        "applied": sorted(updates),
        "answer": answer,
    }


def _validate_stage_action(context: ResolutionContext, answer: Any) -> bool:
    updates = context.parameters.get("state_updates")
    if not isinstance(updates, dict) or not updates:
        return False
    allowed_keys = {"stage", "data_state"}
    if any(key not in allowed_keys for key in updates):
        return False
    from data_agent.agent.analysis_state import DATA_STATES, STAGES

    stage = updates.get("stage")
    data_state = updates.get("data_state")
    if stage is not None and stage not in STAGES:
        return False
    if data_state is not None and data_state not in DATA_STATES:
        return False
    return True


def _validate_method_action(context: ResolutionContext, answer: Any) -> bool:
    updates = context.parameters.get("state_updates")
    confirmation = updates.get("method_confirmation") if isinstance(updates, dict) else None
    if not isinstance(confirmation, dict):
        return False
    from data_agent.agent.analysis_plan_contracts import analysis_plan_id_from_mapping

    return bool(analysis_plan_id_from_mapping(confirmation))


def _question_identity(
    session_id: str,
    turn_id: str,
    message_version: int,
    request: Any,
    *,
    source: str,
    operation: str,
) -> str:
    payload = {
        "session_id": session_id,
        "turn_id": turn_id,
        "message_version": int(message_version),
        "source": str(source or "").strip(),
        "operation": str(operation or "").strip(),
        "question": str(_request_value(request, "question", "") or "").strip(),
        "options": [option.to_dict() for option in _normalise_options(_request_value(request, "options", ()))],
        "multi_select": bool(_request_value(request, "multi_select", False)),
        "confirmation_type": str(_request_value(request, "confirmation_type", "") or "").strip(),
        "related_task_id": int(_request_value(request, "related_task_id", 0) or 0),
        "related_spec_id": str(_request_value(request, "related_spec_id", "") or "").strip(),
        "state_update_shape": _state_update_shape(_request_value(request, "state_updates", "")),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _normalise_options(raw_options: Any) -> tuple[ConfirmationOption, ...]:
    if isinstance(raw_options, str):
        raw_options = json.loads(raw_options) if raw_options.strip().startswith("[") else []
    options: list[ConfirmationOption] = []
    for index, raw in enumerate(raw_options or (), start=1):
        if isinstance(raw, dict):
            label = str(raw.get("label") or raw.get("value") or "").strip()
            value = str(raw.get("value") or raw.get("label") or "").strip()
            description = str(raw.get("description") or "").strip()
        else:
            label = str(raw or "").strip()
            value = label
            description = ""
        if not label:
            label = f"Option {index}"
        if not value:
            value = label
        options.append(ConfirmationOption(label=label, value=value, description=description))
    return tuple(options)


def _resolution_action_for(request: Any) -> str:
    updates = _state_updates(_request_value(request, "state_updates", ""))
    if set(updates).issubset({"stage", "data_state"}) and updates:
        return "set_analysis_stage"
    if isinstance(updates.get("method_confirmation"), dict):
        return "confirm_method"
    return "record_confirmation_answer"


def _resolution_params_for(request: Any) -> dict[str, Any]:
    return {
        "confirmation_type": str(_request_value(request, "confirmation_type", "") or "").strip(),
        "blocking_reason": str(_request_value(request, "blocking_reason", "") or "").strip(),
        "context": str(_request_value(request, "context", "") or ""),
        "related_task_id": int(_request_value(request, "related_task_id", 0) or 0),
        "related_spec_id": str(_request_value(request, "related_spec_id", "") or "").strip(),
        "question": str(_request_value(request, "question", "") or "").strip(),
        "state_updates": _safe_state_updates(_request_value(request, "state_updates", "")),
    }


def _request_value(request: Any, key: str, default: Any = None) -> Any:
    if isinstance(request, dict):
        return request.get(key, default)
    return getattr(request, key, default)


def _safe_state_updates(value: Any) -> dict[str, Any]:
    updates = _state_updates(value)
    allowed: dict[str, Any] = {}
    for key in ("stage", "data_state"):
        if isinstance(updates.get(key), str):
            allowed[key] = updates[key]
    for key in ("method_confirmation",):
        if isinstance(updates.get(key), dict):
            allowed[key] = dict(updates[key])
    return allowed


def _state_update_shape(value: Any) -> list[str]:
    return sorted(_safe_state_updates(value))


def _state_updates(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, dict):
            return parsed
    return {}
