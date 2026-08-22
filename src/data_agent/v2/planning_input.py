from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from data_agent.v2.identity import require_storage_id


class PlanningInputConflict(RuntimeError):
    """A planning input conflicts with immutable reply history."""


@dataclass(frozen=True, slots=True)
class PlanningInputRecord:
    planning_input_id: str
    source_plan_id: str
    client_reply_id: str
    questions: tuple[dict[str, str], ...]
    answers: tuple[dict[str, str], ...]
    clarifications: tuple[dict[str, str], ...]
    semantic_resolutions: tuple[dict[str, str], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        for key in (
            "questions",
            "answers",
            "clarifications",
            "semantic_resolutions",
        ):
            value[key] = [dict(item) for item in getattr(self, key)]
        return value


_PLANNING_INPUT_LOCK = threading.RLock()


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


def planning_question_id(plan_id: str, position: int) -> str:
    safe_plan_id = require_storage_id(plan_id, "plan_id")
    if isinstance(position, bool) or not isinstance(position, int) or position < 1:
        raise ValueError("question position must be a positive integer")
    return require_storage_id(
        f"{safe_plan_id}_question_{position}", "question_id"
    )


def planning_question_blocks(
    plan_id: str, questions: Iterable[str]
) -> tuple[dict[str, str], ...]:
    normalized = tuple(str(item or "").strip() for item in questions)
    if not normalized or any(not item for item in normalized):
        raise ValueError("planning questions must be nonempty")
    return tuple(
        {
            "type": "planning_question",
            "plan_id": require_storage_id(plan_id, "plan_id"),
            "question_id": planning_question_id(plan_id, index),
            "text": text,
        }
        for index, text in enumerate(normalized, start=1)
    )


def _normalize_questions(
    questions: Iterable[dict[str, Any]],
) -> tuple[dict[str, str], ...]:
    normalized: list[dict[str, str]] = []
    for raw in questions:
        if not isinstance(raw, dict):
            raise ValueError("questions must contain objects")
        question_id = require_storage_id(raw.get("question_id", ""), "question_id")
        text = str(raw.get("text") or "").strip()
        if not text:
            raise ValueError("question text is required")
        normalized.append({"question_id": question_id, "text": text})
    if not normalized:
        raise ValueError("questions are required")
    ids = [item["question_id"] for item in normalized]
    if len(ids) != len(set(ids)):
        raise ValueError("question_id must be unique")
    return tuple(normalized)


def _normalize_answers(
    answers: Iterable[dict[str, Any]],
    questions: tuple[dict[str, str], ...],
) -> tuple[dict[str, str], ...]:
    normalized: list[dict[str, str]] = []
    for raw in answers:
        if not isinstance(raw, dict):
            raise ValueError("answers must contain objects")
        question_id = require_storage_id(raw.get("question_id", ""), "question_id")
        answer = str(raw.get("answer") or "").strip()
        if not answer:
            raise ValueError("answer is required")
        normalized.append({"question_id": question_id, "answer": answer})
    expected = [item["question_id"] for item in questions]
    received = [item["question_id"] for item in normalized]
    if sorted(received) != sorted(expected) or len(received) != len(set(received)):
        raise ValueError("each planning question must be answered exactly once")
    by_id = {item["question_id"]: item["answer"] for item in normalized}
    return tuple(
        {"question_id": question_id, "answer": by_id[question_id]}
        for question_id in expected
    )


def normalize_semantic_resolutions(
    resolutions: Iterable[dict[str, Any]],
) -> tuple[dict[str, str], ...]:
    normalized: list[dict[str, str]] = []
    for raw in resolutions:
        if not isinstance(raw, dict):
            raise ValueError("semantic_resolutions must contain objects")
        if set(raw) != {"prerequisite_code", "column"}:
            raise ValueError("semantic resolution fields are invalid")
        prerequisite_code = str(raw.get("prerequisite_code") or "").strip()
        column = str(raw.get("column") or "").strip()
        if prerequisite_code != "analysis_unit_semantics":
            raise ValueError("semantic prerequisite code is invalid")
        if not column:
            raise ValueError("semantic resolution column is required")
        normalized.append(
            {"prerequisite_code": prerequisite_code, "column": column}
        )
    codes = [item["prerequisite_code"] for item in normalized]
    if len(codes) != len(set(codes)):
        raise ValueError("semantic prerequisite code must be unique")
    return tuple(normalized)


class PlanningInputStore:
    """Append-only ledger of user answers to one terminal needs_input plan."""

    def __init__(self, sessions_root: Path | str, session_id: str) -> None:
        safe_session_id = require_storage_id(session_id, "session_id")
        self.path = (
            Path(sessions_root) / safe_session_id / "v2" / "planning_inputs.jsonl"
        )

    def _events(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        events: list[dict[str, Any]] = []
        for line_number, line in enumerate(
            self.path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"invalid planning input JSONL at {self.path}:{line_number}"
                ) from exc
            if not isinstance(value, dict) or value.get("event_type") != "recorded":
                raise ValueError("invalid planning input event")
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
            raise PlanningInputConflict(f"planning input event conflict: {event_id}")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(canonical + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def list_all(self) -> list[PlanningInputRecord]:
        result: list[PlanningInputRecord] = []
        seen: set[str] = set()
        for event in self._events():
            input_id = require_storage_id(
                event.get("planning_input_id", ""), "planning_input_id"
            )
            if input_id in seen:
                raise PlanningInputConflict(f"duplicate planning input: {input_id}")
            seen.add(input_id)
            questions = _normalize_questions(event.get("questions") or ())
            answers = _normalize_answers(event.get("answers") or (), questions)
            semantic_resolutions = normalize_semantic_resolutions(
                event.get("semantic_resolutions") or ()
            )
            by_id = {item["question_id"]: item["answer"] for item in answers}
            result.append(
                PlanningInputRecord(
                    planning_input_id=input_id,
                    source_plan_id=require_storage_id(
                        event.get("source_plan_id", ""), "source_plan_id"
                    ),
                    client_reply_id=require_storage_id(
                        event.get("client_reply_id", ""), "client_reply_id"
                    ),
                    questions=questions,
                    answers=answers,
                    clarifications=tuple(
                        {
                            "question": item["text"],
                            "answer": by_id[item["question_id"]],
                        }
                        for item in questions
                    ),
                    semantic_resolutions=semantic_resolutions,
                )
            )
        return result

    def get(self, planning_input_id: str) -> PlanningInputRecord:
        safe_id = require_storage_id(planning_input_id, "planning_input_id")
        for record in self.list_all():
            if record.planning_input_id == safe_id:
                return record
        raise KeyError(f"unknown planning input {safe_id}")

    def record(
        self,
        *,
        source_plan_id: str,
        client_reply_id: str,
        questions: Iterable[dict[str, Any]],
        answers: Iterable[dict[str, Any]],
        semantic_resolutions: Iterable[dict[str, Any]] = (),
    ) -> PlanningInputRecord:
        source_id = require_storage_id(source_plan_id, "source_plan_id")
        reply_id = require_storage_id(client_reply_id, "client_reply_id")
        normalized_questions = _normalize_questions(tuple(questions))
        normalized_answers = _normalize_answers(tuple(answers), normalized_questions)
        normalized_semantic_resolutions = normalize_semantic_resolutions(
            tuple(semantic_resolutions)
        )
        planning_input_id = f"planning_input_{_digest(reply_id)}"
        with _PLANNING_INPUT_LOCK:
            existing = next(
                (
                    item
                    for item in self.list_all()
                    if item.client_reply_id == reply_id
                ),
                None,
            )
            if existing is not None:
                same = (
                    existing.source_plan_id == source_id
                    and existing.questions == normalized_questions
                    and existing.answers == normalized_answers
                    and existing.semantic_resolutions
                    == normalized_semantic_resolutions
                )
                if not same:
                    raise PlanningInputConflict(
                        f"client_reply_id has different reply content: {reply_id}"
                    )
                return existing
            self._append(
                {
                    "event_id": f"planning_input_event_{_digest(planning_input_id)}",
                    "event_type": "recorded",
                    "planning_input_id": planning_input_id,
                    "source_plan_id": source_id,
                    "client_reply_id": reply_id,
                    "questions": list(normalized_questions),
                    "answers": list(normalized_answers),
                    "semantic_resolutions": list(
                        normalized_semantic_resolutions
                    ),
                }
            )
            return self.get(planning_input_id)
