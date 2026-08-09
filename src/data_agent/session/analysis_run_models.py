"""Immutable domain models for transactional analysis runs."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class RunStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    RECOVERY = "recovery"
    COMPLETED = "completed"
    FAILED = "failed"
    TERMINATED = "terminated"


class StepStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class StepSpec:
    subject: str
    capability: str = ""
    payload: dict[str, Any] | None = None
    idempotency_key: str = ""


@dataclass(frozen=True, slots=True)
class AnalysisStep:
    step_id: str
    run_id: str
    ordinal: int
    subject: str
    capability: str
    status: StepStatus
    payload: dict[str, Any]
    version: int


@dataclass(frozen=True, slots=True)
class AnalysisRun:
    run_id: str
    session_id: str
    status: RunStatus
    version: int
    steps: tuple[AnalysisStep, ...]

    @property
    def current_step(self) -> AnalysisStep | None:
        current = [step for step in self.steps if step.status == StepStatus.IN_PROGRESS]
        return current[0] if len(current) == 1 else None

