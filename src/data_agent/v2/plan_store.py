from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import asdict, dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import Any

from data_agent.v2.identity import require_storage_id
from data_agent.v2.planner import (
    AnalysisPlan,
    PlannerFailureReason,
    PlannerFailureStage,
    PlanStatus,
    normalize_planner_failure_diagnostic,
)
from data_agent.v2.planning_input import planning_question_blocks


class DurablePlanStatus(StrEnum):
    REQUESTED = "requested"
    READY = "ready"
    NEEDS_INPUT = "needs_input"
    UNSUPPORTED = "unsupported"
    FAILED = "failed"
    CONSUMED = "consumed"


class PlanConflict(RuntimeError):
    """A planning transition conflicts with append-only history."""


@dataclass(frozen=True, slots=True)
class DurablePlanRecord:
    plan_id: str
    client_request_id: str
    question: str
    dataset_context: dict[str, Any]
    provider_authorization_ref: str
    provider_calls_authorized: int
    status: DurablePlanStatus
    analysis_kind: str = ""
    parameters: dict[str, Any] | None = None
    rationale: str = ""
    questions: tuple[str, ...] = ()
    maximum_claim_class: str = ""
    planner_invocations: int = 0
    model_id: str = ""
    provider_calls: int = 0
    target_turn_id: str = ""
    error_code: str = ""
    message: str = ""
    error_reason_code: str = ""
    failure_stage: str = ""
    diagnostic: dict[str, Any] | None = None
    parent_plan_id: str = ""
    planning_input_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["status"] = self.status.value
        value["parameters"] = dict(self.parameters or {})
        value["questions"] = list(self.questions)
        value.pop("diagnostic", None)
        if not self.error_reason_code:
            value.pop("error_reason_code", None)
        if not self.failure_stage:
            value.pop("failure_stage", None)
        value["message_blocks"] = (
            list(planning_question_blocks(self.plan_id, self.questions))
            if self.status is DurablePlanStatus.NEEDS_INPUT
            else []
        )
        return value


_PLAN_LOCK = threading.RLock()


def _line(value: dict[str, Any]) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


class PlanStore:
    """Append-only ledger for one-call model planning and plan consumption."""

    def __init__(self, sessions_root: Path | str, session_id: str) -> None:
        safe_session_id = require_storage_id(session_id, "session_id")
        self.path = Path(sessions_root) / safe_session_id / "v2" / "plans.jsonl"

    def _events(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        events = []
        for line_number, line in enumerate(
            self.path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"invalid plan JSONL at {self.path}:{line_number}"
                ) from exc
            if not isinstance(value, dict):
                raise ValueError("invalid plan event")
            events.append(value)
        return events

    def _append(self, event: dict[str, Any]) -> None:
        event_id = require_storage_id(event.get("event_id", ""), "event_id")
        canonical = _line(event)
        for existing in self._events():
            if existing.get("event_id") != event_id:
                continue
            if _line(existing) == canonical:
                return
            raise PlanConflict(f"plan event conflict: {event_id}")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(canonical + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def list_all(self) -> list[DurablePlanRecord]:
        projected: dict[str, DurablePlanRecord] = {}
        order: list[str] = []
        for event in self._events():
            plan_id = require_storage_id(event.get("plan_id", ""), "plan_id")
            event_type = str(event.get("event_type") or "")
            if event_type == "requested":
                if plan_id in projected:
                    raise PlanConflict(f"duplicate requested event for {plan_id}")
                context = event.get("dataset_context")
                if not isinstance(context, dict):
                    raise ValueError("plan dataset_context must be an object")
                projected[plan_id] = DurablePlanRecord(
                    plan_id=plan_id,
                    client_request_id=event["client_request_id"],
                    question=event["question"],
                    dataset_context=dict(context),
                    provider_authorization_ref=event["provider_authorization_ref"],
                    provider_calls_authorized=int(event["provider_calls_authorized"]),
                    status=DurablePlanStatus.REQUESTED,
                    parent_plan_id=str(event.get("parent_plan_id") or ""),
                    planning_input_id=str(event.get("planning_input_id") or ""),
                )
                order.append(plan_id)
                continue
            current = projected.get(plan_id)
            if current is None:
                raise PlanConflict(f"plan transition without request: {plan_id}")
            if event_type == "consumed":
                if current.status is not DurablePlanStatus.READY:
                    raise PlanConflict(
                        f"plan transition after {current.status.value}: {plan_id}"
                    )
                projected[plan_id] = replace(
                    current,
                    status=DurablePlanStatus.CONSUMED,
                    target_turn_id=event["target_turn_id"],
                )
                continue
            if current.status is not DurablePlanStatus.REQUESTED:
                raise PlanConflict(
                    f"plan transition after {current.status.value}: {plan_id}"
                )
            if event_type in {"ready", "needs_input", "unsupported"}:
                projected[plan_id] = replace(
                    current,
                    status=DurablePlanStatus(event_type),
                    analysis_kind=str(event.get("analysis_kind") or ""),
                    parameters=dict(event.get("parameters") or {}),
                    rationale=str(event.get("rationale") or ""),
                    questions=tuple(event.get("questions") or ()),
                    maximum_claim_class=str(
                        event.get("maximum_claim_class") or ""
                    ),
                    planner_invocations=int(event.get("planner_invocations") or 0),
                    model_id=str(event.get("model_id") or ""),
                    provider_calls=int(event.get("provider_calls") or 0),
                )
            elif event_type == "failed":
                diagnostic = event.get("diagnostic")
                if not isinstance(diagnostic, dict):
                    diagnostic = {}
                elif diagnostic:
                    diagnostic = normalize_planner_failure_diagnostic(diagnostic)
                    if diagnostic["failure_stage"] != str(
                        event.get("failure_stage") or ""
                    ):
                        raise ValueError(
                            "persisted diagnostic failure_stage differs from event"
                        )
                projected[plan_id] = replace(
                    current,
                    status=DurablePlanStatus.FAILED,
                    provider_calls=int(event.get("provider_calls") or 0),
                    error_code=str(event.get("error_code") or "planning_failed"),
                    message=str(event.get("message") or "planning failed"),
                    error_reason_code=str(event.get("error_reason_code") or ""),
                    failure_stage=str(event.get("failure_stage") or ""),
                    diagnostic=dict(diagnostic),
                )
            else:
                raise ValueError(f"unknown plan event_type: {event_type}")
        return [projected[plan_id] for plan_id in order]

    def get(self, plan_id: str) -> DurablePlanRecord:
        safe_id = require_storage_id(plan_id, "plan_id")
        for item in self.list_all():
            if item.plan_id == safe_id:
                return item
        raise KeyError(f"unknown plan {safe_id}")

    def find_by_client_request(
        self, client_request_id: str
    ) -> DurablePlanRecord | None:
        safe_id = require_storage_id(client_request_id, "client_request_id")
        return next(
            (item for item in self.list_all() if item.client_request_id == safe_id),
            None,
        )

    def request(
        self,
        *,
        client_request_id: str,
        question: str,
        dataset_context: dict[str, Any],
        provider_authorization_ref: str,
        provider_calls_authorized: int,
        parent_plan_id: str = "",
        planning_input_id: str = "",
    ) -> DurablePlanRecord:
        client_id = require_storage_id(client_request_id, "client_request_id")
        normalized_question = str(question or "").strip()
        authorization_ref = str(provider_authorization_ref or "").strip()
        if not normalized_question:
            raise ValueError("question is required")
        if not isinstance(dataset_context, dict) or not dataset_context.get("filename"):
            raise ValueError("dataset_context with filename is required")
        source_fingerprint = str(
            dataset_context.get("source_fingerprint") or ""
        ).strip()
        if not source_fingerprint.startswith("sha256:"):
            raise ValueError("dataset_context source_fingerprint is required")
        normalized_context = json.loads(
            json.dumps(dataset_context, ensure_ascii=False, sort_keys=True, allow_nan=False)
        )
        if (
            isinstance(provider_calls_authorized, bool)
            or provider_calls_authorized != 1
        ):
            raise ValueError("provider_calls_authorized must equal 1")
        if not authorization_ref:
            raise ValueError("provider_authorization_ref is required")
        normalized_parent = str(parent_plan_id or "").strip()
        normalized_input = str(planning_input_id or "").strip()
        if bool(normalized_parent) != bool(normalized_input):
            raise ValueError(
                "parent_plan_id and planning_input_id must be provided together"
            )
        if normalized_parent:
            normalized_parent = require_storage_id(
                normalized_parent, "parent_plan_id"
            )
            normalized_input = require_storage_id(
                normalized_input, "planning_input_id"
            )
        plan_id = f"plan_{_digest(client_id)}"
        with _PLAN_LOCK:
            all_records = self.list_all()
            existing = next(
                (item for item in all_records if item.client_request_id == client_id),
                None,
            )
            if existing is not None:
                same = (
                    existing.question == normalized_question
                    and existing.dataset_context == normalized_context
                    and existing.provider_authorization_ref == authorization_ref
                    and existing.provider_calls_authorized
                    == provider_calls_authorized
                    and existing.parent_plan_id == normalized_parent
                    and existing.planning_input_id == normalized_input
                )
                if not same:
                    raise PlanConflict(
                        f"client_request_id has different planning content: {client_id}"
                    )
                return existing
            authorization_owner = next(
                (
                    item
                    for item in all_records
                    if item.provider_authorization_ref == authorization_ref
                ),
                None,
            )
            if authorization_owner is not None:
                raise PlanConflict(
                    "provider_authorization_ref was already used by another planning request"
                )
            if normalized_input:
                input_owners = tuple(
                    item
                    for item in all_records
                    if item.planning_input_id == normalized_input
                )
                retry_differs = any(
                    item.parent_plan_id != normalized_parent
                    or item.question != normalized_question
                    or item.dataset_context != normalized_context
                    for item in input_owners
                )
                if retry_differs:
                    raise PlanConflict(
                        "planning_input_id retry has different planning content"
                    )
                if any(
                    item.status is not DurablePlanStatus.FAILED
                    for item in input_owners
                ):
                    raise PlanConflict(
                        "planning_input_id already derived another planning request"
                    )
            self._append(
                {
                    "event_id": f"plan_event_{_digest(plan_id + ':requested')}",
                    "plan_id": plan_id,
                    "event_type": "requested",
                    "client_request_id": client_id,
                    "question": normalized_question,
                    "dataset_context": normalized_context,
                    "provider_authorization_ref": authorization_ref,
                    "provider_calls_authorized": provider_calls_authorized,
                    "parent_plan_id": normalized_parent,
                    "planning_input_id": normalized_input,
                }
            )
            return self.get(plan_id)

    def require_replayable(self, plan_id: str) -> DurablePlanRecord:
        current = self.get(plan_id)
        if current.status is DurablePlanStatus.REQUESTED:
            raise PlanConflict(
                "incomplete planning request requires a new request identity and authorization"
            )
        return current

    def complete(self, plan_id: str, result: AnalysisPlan) -> DurablePlanRecord:
        safe_id = require_storage_id(plan_id, "plan_id")
        with _PLAN_LOCK:
            current = self.get(safe_id)
            if current.status is not DurablePlanStatus.REQUESTED:
                raise PlanConflict(f"cannot complete {current.status.value} plan")
            if result.user_question != current.question:
                raise PlanConflict("planner result question differs from request")
            if result.planner_invocations != 1:
                raise PlanConflict("planner result must report one invocation")
            event_type = result.status.value
            if event_type not in {"ready", "needs_input", "unsupported"}:
                raise PlanConflict(f"cannot persist planner status {event_type}")
            if result.status is PlanStatus.READY:
                if result.analysis_kind is None or not result.parameters:
                    raise PlanConflict("ready planner result requires an executable route")
                if not result.maximum_claim_class:
                    raise PlanConflict("ready planner result requires a claim ceiling")
            elif result.analysis_kind is not None or result.parameters:
                raise PlanConflict(
                    f"{event_type} planner result cannot contain an executable route"
                )
            self._append(
                {
                    "event_id": f"plan_event_{_digest(safe_id + ':' + event_type)}",
                    "plan_id": safe_id,
                    "event_type": event_type,
                    "analysis_kind": (
                        result.analysis_kind.value if result.analysis_kind else ""
                    ),
                    "parameters": result.parameters,
                    "rationale": result.rationale,
                    "questions": list(result.questions),
                    "maximum_claim_class": result.maximum_claim_class,
                    "planner_invocations": result.planner_invocations,
                    "model_id": result.model_id,
                    "provider_calls": 1,
                }
            )
            return self.get(safe_id)

    def fail(
        self,
        plan_id: str,
        *,
        error_code: str,
        message: str,
        error_reason_code: str = "",
        failure_stage: str = "",
        diagnostic: dict[str, Any] | None = None,
    ) -> DurablePlanRecord:
        safe_id = require_storage_id(plan_id, "plan_id")
        normalized_error = str(error_code or "").strip() or "planning_failed"
        normalized_message = str(message or "").strip() or "planning failed"
        normalized_reason = (
            PlannerFailureReason(error_reason_code).value if error_reason_code else ""
        )
        normalized_stage = (
            PlannerFailureStage(failure_stage).value if failure_stage else ""
        )
        if diagnostic is None:
            normalized_diagnostic: dict[str, Any] = {}
        elif not isinstance(diagnostic, dict):
            raise ValueError("diagnostic must be an object")
        else:
            normalized_diagnostic = normalize_planner_failure_diagnostic(diagnostic)
            if normalized_diagnostic["failure_stage"] != normalized_stage:
                raise ValueError("diagnostic failure_stage differs from failure_stage")
        with _PLAN_LOCK:
            current = self.get(safe_id)
            if current.status is not DurablePlanStatus.REQUESTED:
                raise PlanConflict(f"cannot fail {current.status.value} plan")
            self._append(
                {
                    "event_id": f"plan_event_{_digest(safe_id + ':failed')}",
                    "plan_id": safe_id,
                    "event_type": "failed",
                    "provider_calls": 1,
                    "error_code": normalized_error,
                    "message": normalized_message,
                    "error_reason_code": normalized_reason,
                    "failure_stage": normalized_stage,
                    "diagnostic": normalized_diagnostic,
                }
            )
            return self.get(safe_id)

    def consume(self, plan_id: str, *, target_turn_id: str) -> DurablePlanRecord:
        safe_id = require_storage_id(plan_id, "plan_id")
        safe_target = require_storage_id(target_turn_id, "target_turn_id")
        with _PLAN_LOCK:
            current = self.get(safe_id)
            if current.status is DurablePlanStatus.CONSUMED:
                if current.target_turn_id != safe_target:
                    raise PlanConflict("plan was consumed by a different target turn")
                return current
            if current.status is not DurablePlanStatus.READY:
                raise PlanConflict(f"cannot consume {current.status.value} plan")
            self._append(
                {
                    "event_id": f"plan_event_{_digest(safe_id + ':consumed:' + safe_target)}",
                    "plan_id": safe_id,
                    "event_type": "consumed",
                    "target_turn_id": safe_target,
                }
            )
            return self.get(safe_id)
