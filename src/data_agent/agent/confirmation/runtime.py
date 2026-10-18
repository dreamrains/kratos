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
    ConfirmationRequest,
    FREE_TEXT_ANSWER_ACTIONS,
    QuestionCandidate,
)
from data_agent.agent.confirmation.decision import (
    METHOD_DECISION_KINDS,
    decision_context_from_payload,
    stable_decision_key,
)
from dataclasses import fields as dataclass_fields
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

    candidate = _build_question_candidate(
        session_id=session_id, turn_id=turn_id, message_version=message_version,
        request=request, source="ask_user_question", operation="direct_user_question", id_prefix="direct",
    )
    context = str(_request_value(request, "context", "") or "")
    if not context.lstrip().startswith("["):
        return candidate
    try:
        questions = json.loads(context)
    except ValueError as exc:
        raise ConfirmationContractError("multi-question context must be a JSON array") from exc
    if (not isinstance(questions, list) or not 1 <= len(questions) <= 4
            or any(not isinstance(q, dict) or not isinstance(q.get("question"), str) or not q["question"].strip() for q in questions)):
        raise ConfirmationContractError("multi-question context must contain 1 to 4 complete questions")
    bindings = []
    for index, question in enumerate(questions):
        payload = {key: candidate.resolution_params[key] for key in (
            "confirmation_type", "blocking_reason", "state_updates", "related_task_id", "related_spec_id", "scope_data_version"
        ) if key in candidate.resolution_params}
        # Display metadata is preserved in input, but a model cannot mint host
        # provenance, data versions, defaults, or state actions in a child.
        payload.update({key: question[key] for key in
                        ("question", "options", "multi_select", "confirmation_type", "reuse_decision_id") if key in question})
        payload["context"] = ""
        member = _build_question_candidate(
            session_id=session_id, turn_id=turn_id + ":question:" + str(index),
            message_version=message_version, request=payload, source="ask_user_question",
            operation="direct_user_question", id_prefix="question",
        )
        bindings.append({"question_id": member.confirmation_id, "request": ConfirmationRequest.from_candidate(member).to_dict(), "input": dict(question)})
    from dataclasses import replace
    params = dict(candidate.resolution_params, question_bindings=bindings)
    identity = json.dumps([[b["request"][key] for key in ("decision_key", "data_version", "spec_version")] for b in bindings], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return replace(candidate, resolution_params=params, decision_key=session_id + ":questions:" + hashlib.sha256(identity.encode("utf-8")).hexdigest())


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


def build_measurement_mapping_candidate(
    *, session_id: str, turn_id: str, workspace: Any,
    canonical_history: Any, source_message_ref: str,
    exact_span: str, dataset: str, column: str, x_column: str = "",
    x_start: int | None = None, x_end: int | None = None, cost_scopes: list[list[str]] | None = None,
) -> QuestionCandidate | None:
    """Offer one version-scoped business mapping decision from a real user span.

    The caller proposes the source span and column. This host check proves
    their identity, not their semantic equivalence; only the user's selected
    answer can confirm the mapping. No question is automatically scheduled.
    """
    from data_agent.session.history import CanonicalHistorySnapshot, _history_sha256
    from data_agent.session.workspace import Workspace, WorkspaceProxy
    from pandas.api.types import is_numeric_dtype

    if (not isinstance(canonical_history, CanonicalHistorySnapshot)
            or not isinstance(canonical_history.messages, list)
            or canonical_history.message_count != len(canonical_history.messages)
            or canonical_history.sha256 != _history_sha256(canonical_history.messages)
            or not isinstance(canonical_history.revision, int)
            or canonical_history.revision < 0
            or not all(isinstance(value, str) and value and len(value) <= 120
                       and not any(ord(char) < 32 for char in value)
                       for value in (session_id, turn_id, source_message_ref,
                                     exact_span, dataset, column))
            or not isinstance(x_column, str)
            or len(x_column) > 120
            or any(ord(char) < 32 for char in x_column)
            or (bool(x_column) != (x_start is not None and x_end is not None))
            or (x_column and (isinstance(x_start, bool) or not isinstance(x_start, int)
                              or isinstance(x_end, bool) or not isinstance(x_end, int)
                              or x_start > x_end or x_end - x_start >= 128))
            or not source_message_ref.startswith("msg_")
            or not isinstance(workspace, (Workspace, WorkspaceProxy))):
        return None
    # The same byte-bound canonical source resolver is used before and after compaction.
    from data_agent.agent.publication.requirements import _source
    try:
        content = _source(canonical_history, source_message_ref)
    except (ValueError, OSError, KeyError, TypeError):
        return None
    if content.count(exact_span) != 1:
        return None
    try:
        frame = workspace.get(dataset)
        identity = workspace.get_data_identity(dataset)
    except (AttributeError, KeyError, TypeError, ValueError):
        return None
    if (frame is None or not isinstance(identity, dict)
            or list(frame.columns).count(column) != 1
            or not is_numeric_dtype(frame[column])
            or (x_column and (x_column == column
                              or list(frame.columns).count(x_column) != 1
                              or not is_numeric_dtype(frame[x_column])))
            or not isinstance(identity.get("version_id"), str)
            or not identity["version_id"]
            or not identity.get("source_fingerprint")
            or identity.get("fingerprint") != Workspace._frame_fingerprint(frame)):
        return None
    if cost_scopes is not None:
        if (x_column or not isinstance(cost_scopes,list) or not 1<=len(cost_scopes)<=4
                or any(not isinstance(costs,list) or not 1<=len(costs)<=2
                    or any(not isinstance(c,str) or not c or len(c)>96 or any(ord(ch)<32 for ch in c)
                        or c==column or list(frame.columns).count(c)!=1 or not is_numeric_dtype(frame[c]) for c in costs)
                    or len(set(costs))!=len(costs) for costs in cost_scopes)
                or len({tuple(costs) for costs in cost_scopes})!=len(cost_scopes)):
            return None
    if x_column:
        try:
            in_range = frame[frame[x_column].between(x_start, x_end, inclusive="both")]
            values = list(in_range[x_column])
            integer_values = [int(value) for value in values]
        except (TypeError, ValueError):
            return None
        if (len(values) != x_end - x_start + 1
                or set(integer_values) != set(range(x_start, x_end + 1))
                or any(value != integer for value, integer in zip(values, integer_values))):
            return None
    version_id = identity["version_id"]
    seed = json.dumps([session_id, source_message_ref, exact_span, dataset,
                       column, x_column, x_start, x_end, version_id] + ([cost_scopes] if cost_scopes is not None else []),
                      ensure_ascii=False, separators=(",", ":"))
    decision_id = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]
    occurrence_id = hashlib.sha256(f"{decision_id}|{turn_id}".encode("utf-8")).hexdigest()[:24]
    options = (
        ConfirmationOption("对应，小数比例（例如 0.10 表示 10%）", "fraction"),
        ConfirmationOption("对应，百分数原值（例如 0.10 表示 0.10%）", "percentage_points"),
        ConfirmationOption("对应，但单位或尺度尚未确认", "raw"),
        ConfirmationOption("不对应或无法确认", "unconfirmed"),
    )
    if cost_scopes is not None:
        formulas=[{"schema_version":"metric_scope_formula.v1","dataset":dataset,"effect_column":column,"cost_columns":costs} for costs in cost_scopes]
        options=tuple(ConfirmationOption("口径 "+str(i+1)+"（成本："+"、".join(formula["cost_columns"])+"）",json.dumps(formula,ensure_ascii=False,sort_keys=True,separators=(",",":")),metric_scope_formula_description(formula)) for i,formula in enumerate(formulas))+(ConfirmationOption("不对应或无法确认","unconfirmed"),)
    candidate = QuestionCandidate(
        confirmation_id=f"measurement_{occurrence_id}",
        session_id=session_id, turn_id=turn_id,
        decision_key=f"measurement:{decision_id}",
        source="host_measurement_mapping.v1", operation="confirm_measurement",
        question=(f"请确认「{exact_span}」在当前数据「{dataset}」中的账面计算公式；每项公式与成本列见选项。" if cost_scopes is not None else (f"你提到的「{exact_span}」是否对应数据「{dataset}」中的"
                  + (f"「{x_column}」列从 {x_start} 到 {x_end} 的每个整数点，"
                     f"及「{column}」数值列？"
                     if x_column else f"「{column}」列？")
                  + "如果对应，请选择数值列的尺度。")),
        decision_impact="该映射会改变回答的指标身份和数值呈现。",
        answer_mode=AnswerMode.SINGLE_SELECT, options=options,
        blocking_surfaces=("measurement_mapping",), skippable=True,
        resolution_action="record_confirmation_answer",
        resolution_params={
            "confirmation_type": "metric_definition",
            "decision_kind": "metric_definition",
            "missing_value": exact_span,
            "affected_operations": ["answer_claim"],
            "business_scope": f"{source_message_ref}|{exact_span}|{dataset}|{column}",
            "measurement_mapping": {
                "dataset": dataset, "column": column,
                "source_message_ref": source_message_ref,
                "exact_span": exact_span,
                **({"cost_scopes":cost_scopes} if cost_scopes is not None else {}),
                **({"x_column": x_column, "x_start": x_start, "x_end": x_end}
                   if x_column else {}),
            },
        },
        data_version=version_id,
        spec_version="measurement_spec:" + hashlib.sha256(seed.encode("utf-8")).hexdigest(),
    )
    return _apply_stable_decision_key(candidate)


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
    resolution_params = _with_decision_context(resolution_params, request, source=source)
    if source == "pending_confirmation" and _request_value(request, "pending_state_id", ""):
        resolution_params["pending_state_id"] = str(_request_value(request, "pending_state_id"))
    candidate = QuestionCandidate(
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
        # IC1/R02/R05: data_version carries the *relevant* data identity (or
        # empty = unversioned), never the message count - unrelated file
        # changes and continued conversation must not invalidate a decision.
        data_version=str(resolution_params.get("scope_data_version") or "").strip(),
        spec_version=str(_request_value(request, "related_spec_id", "") or "").strip(),
        safe_default=str(_request_value(request, "safe_default", "") or "").strip(),
    )
    return _apply_stable_decision_key(candidate)



_FALLBACK_OPERATIONS = ("agent_turn",)


def _with_decision_context(params: dict[str, Any], request: Any, *, source: str) -> dict[str, Any]:
    """Attach the IC1 decision context from the request payload.

    Internal deterministic gates already carry concrete gaps (question type,
    risk fields, affected routes); the context makes that explicit so the
    policy contract can verify it without trusting free-form question text.
    For internal sources the gate's blocked surfaces - at minimum the agent
    turn the suspension blocks - count as the affected operations. Direct
    model asks must name their affected operations explicitly.
    """
    decision_context = _request_value(request, "decision_context", {}) or {}
    if not isinstance(decision_context, dict):
        decision_context = {}
    payload = {
        **params,
        **decision_context,
        "risk_fields": _request_value(request, "risk_fields", ()),
        "affected_routes": _request_value(request, "affected_routes", ()),
        "affected_operations": decision_context.get("affected_operations")
        or _request_value(request, "affected_operations", ()),
        "missing_value": decision_context.get("missing_value")
        or _request_value(request, "missing_value", ""),
    }
    context = decision_context_from_payload(payload)
    if source == "question_need_detector":
        # Only this deterministic producer derives field risk from cleaning
        # receipts and route dependencies. Model-supplied risk_fields in a
        # direct ask must never certify its own blocking impact.
        risk_fields = _text_items(_request_value(request, "risk_fields", ()))
        affected_routes = _text_items(_request_value(request, "affected_routes", ()))
        if risk_fields and affected_routes:
            params["host_risk_fields"] = risk_fields
            params["host_affected_routes"] = affected_routes
    if (
        str(params.get("confirmation_type") or "").strip() in METHOD_DECISION_KINDS
        and context["decision_kind"]
    ):
        # Persist the host-recovered business type, not the model's retired
        # method tag.  This keeps the UI, ledger and reuse identity aligned
        # with the operation that genuinely blocks.
        params["confirmation_type"] = context["decision_kind"]
    if not context["affected_operations"]:
        blocked = _request_value(request, "blocked_surfaces", ())
        surfaces = [str(item).strip() for item in (blocked or ()) if str(item).strip()]
        if surfaces:
            context["affected_operations"] = surfaces
        else:
            # 挂起确认在结构上就阻塞当前 agent 轮；能力级封锁
            # （is_capability_blocked_by_confirmation）仍要求显式命名能力，
            # 因此这里不构成 Q12 担心的"默认所有工作都受影响"。
            context["affected_operations"] = list(_FALLBACK_OPERATIONS)
    for key in ("decision_kind", "missing_value", "affected_operations", "business_scope"):
        if context.get(key):
            params.setdefault(key, context[key])
    return params


def _text_items(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _apply_stable_decision_key(candidate: QuestionCandidate) -> QuestionCandidate:
    """Swap the per-occurrence key for the semantic reuse key when available.

    Same decision + same business scope across turns then maps to one key, so
    a resolved answer is reused (R01) and message counts never re-ask (R02).
    Candidates without a semantic scope keep the per-occurrence key - nothing
    unverifiable gets reused (design §6).
    """
    logical_key = stable_decision_key(candidate, session_id=candidate.session_id)
    if not logical_key:
        return candidate
    values = {
        field.name: getattr(candidate, field.name)
        for field in dataclass_fields(QuestionCandidate)
    }
    values["decision_key"] = logical_key
    return QuestionCandidate(**values)


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
    if context.parameters.get("question_bindings"):
        resolved = {item["question_id"]: item for item in json.loads(answer)}
        if any(resolved[b["question_id"]]["status"] != "resolved"
               for b in context.parameters["question_bindings"] if b["disposition"] == "confirmation"):
            return {"confirmation_id": context.confirmation_id, "applied": [], "answer": answer}
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
    return isinstance(confirmation, dict) and bool(confirmation.get("analysis_spec_id"))


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
    params = {
        "confirmation_type": str(_request_value(request, "confirmation_type", "") or "").strip(),
        "blocking_reason": str(_request_value(request, "blocking_reason", "") or "").strip(),
        "context": str(_request_value(request, "context") or ""),
        "related_task_id": int(_request_value(request, "related_task_id", 0) or 0),
        "related_spec_id": str(_request_value(request, "related_spec_id", "") or "").strip(),
        "question": str(_request_value(request, "question", "") or "").strip(),
        "state_updates": _safe_state_updates(_request_value(request, "state_updates", "")),
    }
    reference = _request_value(request, "reuse_decision_id", "")
    if isinstance(reference, str) and reference.strip():
        params["reuse_decision_id"] = reference.strip()
    # IC1 决策上下文与版本绑定字段从请求透传（宿主生产者显式提供时优先）。
    decision_context = _request_value(request, "decision_context", {}) or {}
    if not isinstance(decision_context, dict):
        decision_context = {}
    for key in (
        "decision_kind",
        "missing_value",
        "affected_operations",
        "business_scope",
        "default_origin",
        "scope_data_version",
    ):
        value = _request_value(request, key, None)
        if value in (None, "", [], ()) and isinstance(decision_context, dict):
            value = decision_context.get(key)
        if value not in (None, "", [], ()):
            params[key] = value
    return params


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


def metric_scope_formula_description(formula: dict[str, Any]) -> str:
    """One user-visible arithmetic choice; it claims no causal attribution."""
    quoted = lambda value: json.dumps(value, ensure_ascii=False)
    expression = " - ".join(
        f"SUM({quoted(column)})" for column in
        [formula["effect_column"], *formula["cost_columns"]]
    )
    return (f"按数据集 {quoted(formula['dataset'])}：账面净收益 = {expression}。"
            "所选列的业务对应关系由本次选择确认；文件列名不证明促销因果。")



def _host_confirmation_binding(context, scope, requirement_ids=None):
    """Bind only uniquely declared current needs and existing read permissions."""
    from data_agent.agent.publication.requirements import ORIGIN, _source, target_datasets
    from data_agent.session.history import load_canonical_history
    state = context.analysis_state
    if state is None or scope is None or scope.phase == "error":
        return None
    records = getattr(state, "answer_requirements", None)
    if not isinstance(records, list) or any(not isinstance(r, dict) for r in records):
        return None
    current = set(context.turn_requirement_ids if requirement_ids is None else requirement_ids)
    requirements = [r for r in records
                    if r.get("id") in current and r.get("lifecycle_status") == "active"]
    if not requirements or len(requirements) != len(current) or {r["id"] for r in requirements} != current:
        return None
    try:
        history = load_canonical_history(context.session_id)
        groups = {}
        for requirement in requirements:
            if requirement.get("origin") != ORIGIN or requirement.get("scope_issue"):
                return None
            source = _source(history, requirement["source_message_ref"])
            start, end = requirement["source_start"], requirement["source_end"]
            if (type(start) is not int or type(end) is not int or not 0 <= start < end <= len(source)
                    or source[start:end] != requirement["original_text"]):
                return None
            for ref in requirement.get("continuation_refs", []):
                original = _source(history, ref["source_message_ref"])
                start, end = ref["source_start"], ref["source_end"]
                if (type(start) is not int or type(end) is not int or not 0 <= start < end <= len(original)
                        or original[start:end] != ref["original_text"]):
                    return None
            names = tuple(target_datasets(requirement))
            if names:
                groups.setdefault(names, []).append(requirement)
            elif requirement.get("semantic_kind") in {"result", "gap"}:
                return None
        if len(groups) != 1:
            return None
        names, selected = next(iter(groups.items()))
        if scope.phase != "legacy" and not set(names).issubset(scope.allowed_datasets):
            return None
        objects = {name: context.workspace._publication_data_identity(name) for name in names}
        if any(not value.get("version_id") or not value.get("fingerprint") for value in objects.values()):
            return None
        if any(not context.workspace._receipt_identity_matches(name, expected)
               for r in selected for name, expected in r.get("source_data_identities", {}).items()):
            return None
        return {"status": "host_bound", "session_id": context.session_id,
                "project_name": context.project_name or "", "objects": objects,
                "requirements": [{"id": r["id"], "business_scope": r.get("business_scope", {})}
                                 for r in sorted(selected, key=lambda r:r["id"])],
                "requirement_sources": [{key:r[key] for key in
                    ("id", "source_message_ref", "source_start", "source_end", "original_text")}
                    for r in sorted(selected, key=lambda r:r["id"])],
                "permission_scope": {"phase": scope.phase, "plan_id": scope.plan_id,
                    "task_id": scope.task_id, "step_id": scope.step_id,
                    "allowed_datasets": sorted(scope.allowed_datasets)}}
    except (ValueError, OSError, KeyError, TypeError, PermissionError):
        return None


def host_curve_sensitivity_without_window(context=None, scope=None):
    """Prove the current bound native deliveries, not a model dependency label."""
    from data_agent.agent.context import get_current_context
    from data_agent.tools.registry import registry
    from data_agent.agent.publication.native import MINIMAL_PRODUCT_CONTRACTS
    from pandas.api.types import is_numeric_dtype
    context=context or get_current_context()
    if context is None:return False
    scope=scope or context.workspace_scope
    binding=_host_confirmation_binding(context,scope)
    if binding is None:return False
    if (registry.capability_for("curve_fitting") or {}).get("output_contract")!=MINIMAL_PRODUCT_CONTRACTS["curve_fitting"]:return False
    ids={r["id"] for r in binding["requirements"]}
    required=[r for r in context.analysis_state.answer_requirements if r.get("id") in ids]
    if not required:return False
    allowed={"zero_values","curve_weight_col","curve_mature_through_col","curve_compare_weights","curve_output","curve_value_scale"}
    try:
        for req in required:
            if req.get("semantic_kind")!="result":return False
            declarations=req.get("necessary_deliveries") or [{"scope":req.get("business_scope",{})}]
            for declaration in declarations:
                business=declaration.get("scope",{});params=business.get("parameters",{})
                if (params.get("curve_compare_weights") is not True
                        or params.get("curve_output") not in {"sensitivity","max_absolute_difference"}
                        or set(params)-allowed or not params.get("curve_weight_col")
                        or not business.get("datasets") or not business.get("metrics")):return False
                for name in business["datasets"]:
                    if name not in binding["objects"]:return False
                    frame=context.workspace.get(name)
                    columns=set(business["metrics"])|{params["curve_weight_col"]}
                    if params.get("curve_mature_through_col"):columns.add(params["curve_mature_through_col"])
                    if frame is None or any(list(frame.columns).count(c)!=1 or not is_numeric_dtype(frame[c]) for c in columns):return False
        return True
    except (ValueError,KeyError,TypeError,PermissionError,AttributeError):return False


def bind_confirmation_candidate(candidate, *, context, scope, request_id):
    """One host adapter for direct, automatic, and grouped business questions."""
    from dataclasses import replace
    if candidate.source == "host_measurement_mapping.v1":
        return candidate  # This producer already validates exact source/version/permission.
    binding = _host_confirmation_binding(context, scope)
    params = dict(candidate.resolution_params)
    related_task = params.get("related_task_id")
    related_spec = params.get("related_spec_id")
    actual_spec = (getattr(context.analysis_state, "analysis_plan", None) or {}).get("id")
    if (candidate.session_id != context.session_id
            or (related_task and int(related_task) != scope.task_id)
            or (related_spec and related_spec != actual_spec)):
        binding = None
    if binding is None:
        binding = {"status": "request_only", "session_id": context.session_id,
                   "request_id": request_id}
    version = _confirmation_binding_version(binding)
    params["host_binding"] = binding
    params.pop("host_nonblocking_reason", None)
    # Decision 94: the original source/permission proof must establish a
    # full-table count. A model's field or dependency label is not evidence.
    from data_agent.agent.confirmation.decision import decision_context_from_candidate
    if (binding["status"] == "host_bound" and candidate.source == "ask_user_question"
            and candidate.resolution_action == "record_confirmation_answer"
            and not params.get("question_bindings")
            and decision_context_from_candidate(candidate)["decision_kind"] == "time_window"):
        ids = {r["id"] for r in binding["requirements"]}
        required = [r for r in context.analysis_state.answer_requirements if r.get("id") in ids]
        if _full_table_count_requirements(required):
            params["host_nonblocking_reason"] = (
                "当前原需求与交付只计算已核定数据的全表记录数，不依赖时间窗口；"
                "请继续原任务，不据模型自报依赖暂停。")
    if (binding["status"]=="host_bound" and candidate.resolution_action=="record_confirmation_answer"
            and not params.get("question_bindings")
            and decision_context_from_candidate(candidate)["decision_kind"]=="time_window"
            and host_curve_sensitivity_without_window(context,scope)):
        params["host_nonblocking_reason"]="当前已核原需求的全部原生曲线敏感性交付不依赖日期窗口；保留真实混合时段缺口。"
    if params.get("question_bindings"):
        members = []
        for original in params["question_bindings"]:
            request = ConfirmationRequest.from_dict(original["request"])
            member = QuestionCandidate(**{field.name:getattr(request,field.name) for field in dataclass_fields(QuestionCandidate)})
            bound = bind_confirmation_candidate(member, context=context, scope=scope, request_id=request_id)
            members.append(dict(original, question_id=bound.confirmation_id,
                request=ConfirmationRequest.from_candidate(bound).to_dict()))
        params["question_bindings"] = members
        group = [[b["request"][key] for key in ("decision_key", "data_version", "spec_version")] for b in members]
        candidate = replace(candidate, decision_key=context.session_id+":questions:"+hashlib.sha256(
            json.dumps(group,ensure_ascii=False,sort_keys=True,separators=(",", ":")).encode()).hexdigest())
    confirmation_id = candidate.confirmation_id.rsplit("_",1)[0]+"_"+hashlib.sha256(
        json.dumps([candidate.confirmation_id,version],separators=(",", ":")).encode()).hexdigest()[:24]
    return replace(candidate, confirmation_id=confirmation_id, data_version=version, resolution_params=params)




def bind_referenced_decision(candidate, *, service, context, scope, request_id):
    """Resolve an explicit ID to its original business decision, never to new prose."""
    from dataclasses import replace
    from data_agent.agent.confirmation.models import ConfirmationStatus
    from data_agent.agent.confirmation.decision import decision_context_from_candidate, resolved_question_records
    params = dict(candidate.resolution_params)
    params.pop("host_reuse_decision_id", None)
    if params.get("question_bindings"):
        members = []
        for original in params["question_bindings"]:
            request = ConfirmationRequest.from_dict(original["request"])
            member = QuestionCandidate(**{field.name: getattr(request, field.name) for field in dataclass_fields(QuestionCandidate)})
            bound = bind_referenced_decision(member, service=service, context=context, scope=scope, request_id=request_id)
            members.append(dict(original, request=ConfirmationRequest.from_candidate(bound).to_dict()))
        return replace(candidate, resolution_params=dict(params, question_bindings=members))
    reference = params.get("reuse_decision_id")
    if not reference:
        return replace(candidate, resolution_params=params)
    matches = [item for record in service._store(context.session_id).load_records().values()
               for item in resolved_question_records(record)
               if (item.resolution_params.get("_question_id") or item.confirmation_id) == reference]
    if len(matches) != 1:
        return replace(candidate, resolution_params=params)
    original = matches[0]
    if (original.status != ConfirmationStatus.RESOLVED or original.session_id != candidate.session_id
            or original.resolution_params.get("host_binding", {}).get("status") != "host_bound"
            or params.get("host_binding", {}).get("status") != "host_bound"
            or original.data_version != candidate.data_version or original.spec_version != candidate.spec_version
            or not confirmation_binding_is_current(original, context=context, scope=scope, request_id=request_id)
            or original.resolution_action != "record_confirmation_answer" or candidate.resolution_action != original.resolution_action
            or original.answer_mode != candidate.answer_mode
            or sorted(o.value for o in original.options) != sorted(o.value for o in candidate.options)
            or decision_context_from_candidate(original)["decision_kind"] != decision_context_from_candidate(candidate)["decision_kind"]):
        return replace(candidate, resolution_params=params)
    for key in ("decision_kind", "missing_value", "affected_operations", "business_scope", "confirmation_type", "question"):
        if key in original.resolution_params:
            params[key] = original.resolution_params[key]
        else:
            params.pop(key, None)
    params["host_reuse_decision_id"] = reference
    return replace(candidate, decision_key=original.decision_key, question=original.question,
                   options=original.options, resolution_params=params)


def _confirmation_binding_version(binding):
    # Original requirement bytes, objects, and versions define applicability.
    # A task cursor or an unrelated visible object does not add authority.
    identity = ({key:binding[key] for key in
                ("session_id", "project_name", "objects", "requirements", "requirement_sources")}
                if binding["status"] == "host_bound" else binding)
    return "sha256:" + hashlib.sha256(json.dumps(identity, ensure_ascii=False,
                       sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def confirmation_binding_is_current(record, *, context, scope, request_id=None):
    binding = record.resolution_params.get("host_binding")
    if binding and binding.get("status") == "request_only":
        # A low-level checkpoint without a new external request keeps its
        # occurrence. Production turns supply their original request identity.
        if request_id is None:
            return True
        return (binding.get("session_id") == context.session_id
                and binding.get("request_id") == request_id
                and _confirmation_binding_version(binding) == record.data_version)
    if not binding or binding.get("status") != "host_bound":
        return True  # Existing explicitly versioned producers retain their own checks.
    current = _host_confirmation_binding(context, scope,
        requirement_ids=[r["id"] for r in binding["requirements"]])
    return current is not None and _confirmation_binding_version(current) == record.data_version


def _full_table_count_requirements(required):
    return bool(required) and all(
        r.get("semantic_kind") == "result"
        and set(r.get("business_scope", {})) == {"datasets", "quantity"}
        and r["business_scope"]["quantity"] == "rows" and r.get("necessary_deliveries")
        and all(d.get("kind") == "measurement" and d.get("scope") == r["business_scope"]
                for d in r["necessary_deliveries"]) for r in required)
