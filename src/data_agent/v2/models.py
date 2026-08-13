from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class CommitmentPriority(StrEnum):
    CORE = "core"
    OPTIONAL = "optional"
    CONDITIONAL = "conditional"


class FindingKind(StrEnum):
    ESTIMATE = "estimate"
    NULL_RESULT = "null_result"
    DATA_QUALITY = "data_quality"
    METHOD_DIAGNOSTIC = "method_diagnostic"
    LIMITATION = "limitation"
    ASSOCIATION = "association"
    TRANSFORMATION = "transformation"
    GROUP_COMPARISON = "group_comparison"
    TIME_TREND = "time_trend"
    FORECAST = "forecast"


class ClaimClass(StrEnum):
    DESCRIPTIVE = "descriptive"
    ASSOCIATIONAL = "associational"
    INFERENTIAL = "inferential"
    PREDICTIVE = "predictive"
    CAUSAL = "causal"


CLAIM_CLASS_RANK: dict[ClaimClass, int] = {
    ClaimClass.DESCRIPTIVE: 0,
    ClaimClass.ASSOCIATIONAL: 1,
    ClaimClass.INFERENTIAL: 2,
    ClaimClass.PREDICTIVE: 3,
    ClaimClass.CAUSAL: 4,
}


class EventType(StrEnum):
    TOOL_STARTED = "tool_started"
    TOOL_SUCCEEDED = "tool_succeeded"
    TOOL_FAILED = "tool_failed"
    ARTIFACT_CREATED = "artifact_created"
    ARTIFACT_FAILED = "artifact_failed"
    FALLBACK_STARTED = "fallback_started"
    USER_INPUT_REQUIRED = "user_input_required"
    USER_INTERRUPTED = "user_interrupted"
    BUDGET_EXHAUSTED = "budget_exhausted"
    SYSTEM_FAILED = "system_failed"


class OutcomeStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUPPORTED = "supported"
    NULL_RESULT = "null_result"
    LIMITED = "limited"
    UNAVAILABLE = "unavailable"
    NEEDS_INPUT = "needs_input"
    INTERRUPTED = "interrupted"
    SYSTEM_FAILED = "system_failed"


PUBLISHABLE_OUTCOMES = frozenset(
    {
        OutcomeStatus.SUPPORTED,
        OutcomeStatus.NULL_RESULT,
        OutcomeStatus.LIMITED,
        OutcomeStatus.UNAVAILABLE,
    }
)


class AnswerBlockType(StrEnum):
    EXECUTIVE_ANSWER = "executive_answer"
    KEY_FINDING = "key_finding"
    COMPARISON = "comparison"
    CHART = "chart"
    METHOD = "method"
    UNCERTAINTY = "uncertainty"
    LIMITATION = "limitation"
    RECOMMENDATION = "recommendation"
    NEXT_INVESTIGATION = "next_investigation"
    SUPPLEMENTAL = "supplemental"


class CalibrationAction(StrEnum):
    SUPPORTED = "supported"
    EXPLORATORY = "exploratory"
    REVISE = "revise"
    REPLACE_WITH_DIAGNOSTIC = "replace_with_diagnostic"
    OMIT_OPTIONAL = "omit_optional"


def _required(value: str, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{field_name} is required")
    return normalized


def _tuple(values: tuple[str, ...] | list[str] | None) -> tuple[str, ...]:
    return tuple(str(value).strip() for value in (values or ()) if str(value).strip())


@dataclass(frozen=True, slots=True)
class Commitment:
    commitment_id: str
    priority: CommitmentPriority
    question: str
    dataset_version_ids: tuple[str, ...]
    accepted_result_kinds: tuple[FindingKind, ...]
    accepted_method_capabilities: tuple[str, ...]
    target_semantics: str = ""
    activation_condition: str = ""
    visualization_intent: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "commitment_id", _required(self.commitment_id, "commitment_id"))
        object.__setattr__(self, "question", _required(self.question, "question"))
        object.__setattr__(self, "dataset_version_ids", _tuple(self.dataset_version_ids))
        object.__setattr__(
            self,
            "accepted_method_capabilities",
            _tuple(self.accepted_method_capabilities),
        )
        if not self.accepted_result_kinds:
            raise ValueError("accepted_result_kinds is required")
        if not self.accepted_method_capabilities:
            raise ValueError("accepted_method_capabilities is required")


@dataclass(frozen=True, slots=True)
class ExecutionEvent:
    event_id: str
    run_id: str
    commitment_id: str
    event_type: EventType
    tool_call_id: str = ""
    tool_name: str = ""
    capability: str = ""
    dataset_version_ids: tuple[str, ...] = ()
    input_digest: str = ""
    result_ref: str = ""
    error_code: str = ""
    message: str = ""
    timestamp: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_id", _required(self.event_id, "event_id"))
        object.__setattr__(self, "run_id", _required(self.run_id, "run_id"))
        object.__setattr__(self, "commitment_id", _required(self.commitment_id, "commitment_id"))
        object.__setattr__(self, "dataset_version_ids", _tuple(self.dataset_version_ids))


@dataclass(frozen=True, slots=True)
class Finding:
    finding_id: str
    commitment_id: str
    finding_kind: FindingKind
    dataset_version_ids: tuple[str, ...]
    metric_identity: str
    method_capability: str
    maximum_claim_class: ClaimClass
    computation_ref: str
    feature_identity: str = ""
    population_scope: str = ""
    time_scope: str = ""
    estimate: float | int | str | None = None
    unit: str = ""
    direction: str = ""
    effective_sample: int | None = None
    uncertainty: dict[str, Any] = field(default_factory=dict)
    assumption_results: dict[str, Any] = field(default_factory=dict)
    limitations: tuple[str, ...] = ()
    verification_level: str = "structured_checked"

    def __post_init__(self) -> None:
        object.__setattr__(self, "finding_id", _required(self.finding_id, "finding_id"))
        object.__setattr__(self, "commitment_id", _required(self.commitment_id, "commitment_id"))
        object.__setattr__(self, "metric_identity", _required(self.metric_identity, "metric_identity"))
        object.__setattr__(
            self,
            "method_capability",
            _required(self.method_capability, "method_capability"),
        )
        object.__setattr__(self, "computation_ref", _required(self.computation_ref, "computation_ref"))
        object.__setattr__(self, "dataset_version_ids", _tuple(self.dataset_version_ids))
        object.__setattr__(self, "limitations", _tuple(self.limitations))
        if not self.dataset_version_ids:
            raise ValueError("dataset_version_ids is required")


@dataclass(frozen=True, slots=True)
class CommitmentOutcome:
    commitment_id: str
    status: OutcomeStatus
    finding_ids: tuple[str, ...] = ()
    reason_code: str = ""
    event_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RunProjection:
    outcomes: dict[str, CommitmentOutcome]
    publishable: bool
    blocking_commitment_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AnswerBlockDraft:
    block_id: str
    block_type: AnswerBlockType
    headline: str
    narrative: str
    support_refs: tuple[str, ...] = ()
    claim_class: ClaimClass | None = None
    canonical_values: tuple[float | int | str, ...] = ()
    limitations: tuple[str, ...] = ()
    chart_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "block_id", _required(self.block_id, "block_id"))
        object.__setattr__(self, "headline", _required(self.headline, "headline"))
        object.__setattr__(self, "narrative", _required(self.narrative, "narrative"))
        object.__setattr__(self, "support_refs", _tuple(self.support_refs))
        object.__setattr__(self, "limitations", _tuple(self.limitations))
        object.__setattr__(self, "chart_refs", _tuple(self.chart_refs))


@dataclass(frozen=True, slots=True)
class AnswerBlock:
    block_id: str
    block_type: AnswerBlockType
    headline: str
    narrative: str
    support_refs: tuple[str, ...]
    claim_class: ClaimClass | None = None
    canonical_values: tuple[float | int | str, ...] = ()
    limitations: tuple[str, ...] = ()
    chart_refs: tuple[str, ...] = ()
    calibration: CalibrationAction = CalibrationAction.SUPPORTED


@dataclass(frozen=True, slots=True)
class BlockCalibration:
    block_id: str
    action: CalibrationAction
    reason_code: str = ""
    message: str = ""


@dataclass(frozen=True, slots=True)
class ChartArtifact:
    chart_id: str
    title: str
    chart_type: str
    dataset_version_ids: tuple[str, ...]
    finding_refs: tuple[str, ...]
    x_field: str
    y_fields: tuple[str, ...]
    purpose: str
    relative_path: str
    content_fingerprint: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "chart_id", _required(self.chart_id, "chart_id"))
        object.__setattr__(self, "title", _required(self.title, "title"))
        object.__setattr__(self, "chart_type", _required(self.chart_type, "chart_type"))
        object.__setattr__(self, "x_field", _required(self.x_field, "x_field"))
        object.__setattr__(self, "purpose", _required(self.purpose, "purpose"))
        object.__setattr__(
            self,
            "content_fingerprint",
            _required(self.content_fingerprint, "content_fingerprint"),
        )
        object.__setattr__(self, "dataset_version_ids", _tuple(self.dataset_version_ids))
        object.__setattr__(self, "finding_refs", _tuple(self.finding_refs))
        object.__setattr__(self, "y_fields", _tuple(self.y_fields))
        expected_path = f"charts/{self.chart_id}.html"
        if self.relative_path != expected_path:
            raise ValueError(f"relative_path must equal {expected_path}")
        if not self.dataset_version_ids or not self.y_fields:
            raise ValueError("chart dataset_version_ids and y_fields are required")
        if self.purpose in {"evidence", "insight"} and not self.finding_refs:
            raise ValueError("evidence-backed charts require finding_refs")
        if not self.content_fingerprint.startswith("sha256:"):
            raise ValueError("chart content_fingerprint must use sha256")


@dataclass(frozen=True, slots=True)
class ExploratoryArtifact:
    artifact_id: str
    dataset_version_ids: tuple[str, ...]
    purpose: str
    code_fingerprint: str
    status: str
    output: str
    result: str
    error_code: str
    risk_level: str
    limitations: tuple[str, ...]
    verification_level: str
    content_fingerprint: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifact_id", _required(self.artifact_id, "artifact_id"))
        object.__setattr__(self, "dataset_version_ids", _tuple(self.dataset_version_ids))
        object.__setattr__(self, "purpose", _required(self.purpose, "purpose"))
        object.__setattr__(self, "limitations", _tuple(self.limitations))
        if not self.dataset_version_ids:
            raise ValueError("exploratory artifact dataset_version_ids is required")
        if self.status not in {"succeeded", "rejected", "failed", "timed_out"}:
            raise ValueError("invalid exploratory artifact status")
        if self.verification_level != "exploratory_only":
            raise ValueError("exploratory artifacts must remain exploratory_only")
        if not self.code_fingerprint.startswith("sha256:"):
            raise ValueError("code_fingerprint must use sha256")
        if not self.content_fingerprint.startswith("sha256:"):
            raise ValueError("content_fingerprint must use sha256")


@dataclass(frozen=True, slots=True)
class CompiledAnswer:
    blocks: tuple[AnswerBlock, ...]
    markdown: str
    calibrations: tuple[BlockCalibration, ...] = ()
