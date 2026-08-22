from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Iterable


class ValidationLayer(StrEnum):
    OWNER_CONTRACT = "owner_contract"
    INCIDENT_REPLAY = "incident_replay"
    SSE_TRANSPORT_CONTRACT = "sse_transport_contract"
    BROWSER_INTERACTION_JOURNEY = "browser_interaction_journey"
    REFRESH_PERSISTENCE_JOURNEY = "refresh_persistence_journey"
    SCENARIO_SEMANTIC_ORACLE = "scenario_semantic_oracle"
    REAL_PROVIDER_ANALYSIS_JOURNEY = "real_provider_analysis_journey"
    HUMAN_SEMANTIC_REVIEW = "human_semantic_review"


class LayerStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    BLOCKED = "blocked"
    NOT_RUN = "not_run"


class ReadinessStatus(StrEnum):
    NOT_READY = "not_ready"
    READY_FOR_HUMAN_DECISION = "ready_for_human_decision"


HUMAN_REVIEW_DIMENSIONS = (
    "question_understanding",
    "data_scope",
    "method_fit",
    "statistical_rigor",
    "claim_calibration",
    "alternative_explanations",
    "pyramid_structure",
    "chart_value",
    "recommendation_quality",
    "journey_integrity",
)


def _required(value: str, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{field_name} is required")
    return normalized


def _digest(value: str) -> str:
    normalized = _required(value, "source_digest")
    if len(normalized) != 71 or not normalized.startswith("sha256:"):
        raise ValueError("source_digest must be a sha256 value")
    try:
        int(normalized.removeprefix("sha256:"), 16)
    except ValueError as exc:
        raise ValueError("source_digest must be a sha256 value") from exc
    return normalized


@dataclass(frozen=True, slots=True)
class ReleaseSourceSnapshot:
    version: str
    source_digest: str
    files: tuple[str, ...]
    git_head: str
    dirty: bool

    def to_dict(self, *, include_files: bool = False) -> dict[str, Any]:
        payload = {
            "version": self.version,
            "source_digest": self.source_digest,
            "file_count": len(self.files),
            "git_head": self.git_head,
            "dirty": self.dirty,
        }
        if include_files:
            payload["files"] = list(self.files)
        return payload


@dataclass(frozen=True, slots=True)
class ScenarioRequirement:
    scenario_id: str
    user_value: str
    entry: str
    fixture: str
    required_layers: tuple[ValidationLayer, ...]
    required_semantic_events: tuple[str, ...]
    required_block_types: tuple[str, ...]
    required_interactions: tuple[str, ...]
    chart_policy: str
    forbidden_behaviors: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "scenario_id", _required(self.scenario_id, "scenario_id"))
        object.__setattr__(self, "user_value", _required(self.user_value, "user_value"))
        object.__setattr__(self, "entry", _required(self.entry, "entry"))
        object.__setattr__(self, "fixture", _required(self.fixture, "fixture"))
        if not self.required_layers:
            raise ValueError("required_layers is required")
        if len(self.required_layers) != len(set(self.required_layers)):
            raise ValueError(f"duplicate required layer in {self.scenario_id}")
        for field_name in (
            "required_semantic_events", "required_block_types", "required_interactions",
            "forbidden_behaviors"
        ):
            values = tuple(
                str(item).strip() for item in getattr(self, field_name) if str(item).strip()
            )
            object.__setattr__(self, field_name, values)
            if not values:
                raise ValueError(f"{field_name} is required for {self.scenario_id}")
            if len(values) != len(set(values)):
                raise ValueError(f"duplicate {field_name} in {self.scenario_id}")
        if self.chart_policy not in {"required", "conditional", "forbidden"}:
            raise ValueError(f"invalid chart_policy for {self.scenario_id}")


@dataclass(frozen=True, slots=True)
class RepresentativeValidationTarget:
    scenario_id: str
    fixture: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "scenario_id", _required(self.scenario_id, "scenario_id"))
        object.__setattr__(self, "fixture", _required(self.fixture, "fixture"))


@dataclass(frozen=True, slots=True)
class ReleaseMatrix:
    version: str
    scenarios: tuple[ScenarioRequirement, ...]
    shared_runtime_scenario_id: str
    shared_runtime_layers: tuple[ValidationLayer, ...]
    shared_runtime_required_semantic_events: tuple[str, ...]
    shared_runtime_required_interactions: tuple[str, ...]
    shared_runtime_chart_policy: str
    representative_provider_targets: tuple[RepresentativeValidationTarget, ...]
    representative_human_targets: tuple[RepresentativeValidationTarget, ...]
    provider_call_budget: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "version", _required(self.version, "version"))
        if not self.scenarios:
            raise ValueError("release matrix requires scenarios")
        ids = [item.scenario_id for item in self.scenarios]
        if len(ids) != len(set(ids)):
            raise ValueError("release matrix scenario ids must be unique")
        object.__setattr__(
            self,
            "shared_runtime_scenario_id",
            _required(self.shared_runtime_scenario_id, "shared_runtime_scenario_id"),
        )
        if self.shared_runtime_scenario_id not in ids:
            raise ValueError("shared runtime scenario must exist in release matrix")
        shared_layers = tuple(ValidationLayer(layer) for layer in self.shared_runtime_layers)
        object.__setattr__(self, "shared_runtime_layers", shared_layers)
        if not shared_layers:
            raise ValueError("shared_runtime_layers is required")
        if len(shared_layers) != len(set(shared_layers)):
            raise ValueError("duplicate shared runtime layer")
        for field_name in (
            "shared_runtime_required_semantic_events",
            "shared_runtime_required_interactions",
        ):
            values = tuple(
                str(item).strip()
                for item in getattr(self, field_name)
                if str(item).strip()
            )
            object.__setattr__(self, field_name, values)
            if not values or len(values) != len(set(values)):
                raise ValueError(f"{field_name} must contain unique values")
        if self.shared_runtime_chart_policy not in {"required", "conditional", "forbidden"}:
            raise ValueError("invalid shared_runtime_chart_policy")
        shared = set(shared_layers)
        if any(shared.intersection(item.required_layers) for item in self.scenarios):
            raise ValueError("shared runtime layers cannot be scenario-specific layers")
        if any(
            item.required_layers != (ValidationLayer.SCENARIO_SEMANTIC_ORACLE,)
            for item in self.scenarios
        ):
            raise ValueError("every scenario requires exactly one semantic oracle")
        if any(item.entry != "/" for item in self.scenarios):
            raise ValueError("release scenarios must use the root V2 entry")
        for field_name in (
            "representative_provider_targets",
            "representative_human_targets",
        ):
            targets = tuple(getattr(self, field_name))
            object.__setattr__(self, field_name, targets)
            target_ids = [target.scenario_id for target in targets]
            if not targets or len(target_ids) != len(set(target_ids)):
                raise ValueError(f"{field_name} must contain unique targets")
            if not set(target_ids).issubset(ids):
                raise ValueError(f"{field_name} contains an unknown scenario")
        if type(self.provider_call_budget) is not int or not 2 <= self.provider_call_budget <= 3:
            raise ValueError("provider_call_budget must be between 2 and 3")
        if self.provider_call_budget != len(self.representative_provider_targets):
            raise ValueError("provider call budget must equal representative provider targets")
        scenarios = {item.scenario_id: item for item in self.scenarios}
        if any(
            target.fixture != scenarios[target.scenario_id].fixture
            for target in self.representative_provider_targets
        ):
            raise ValueError("representative Provider targets must use their scenario fixture")


@dataclass(frozen=True, slots=True)
class ReleaseRequirement:
    """One bounded release obligation and the receipt identity that can satisfy it."""

    requirement_id: str
    scenario_id: str
    layer: ValidationLayer
    scenario: ScenarioRequirement
    expected_fixture: str
    required_semantic_events: tuple[str, ...]
    required_block_types: tuple[str, ...]
    required_interactions: tuple[str, ...]
    chart_policy: str


def _release_requirements(matrix: ReleaseMatrix) -> tuple[ReleaseRequirement, ...]:
    scenarios = {item.scenario_id: item for item in matrix.scenarios}
    shared_scenario = scenarios[matrix.shared_runtime_scenario_id]
    requirements = [
        ReleaseRequirement(
            requirement_id=f"shared_runtime:{layer.value}",
            scenario_id=shared_scenario.scenario_id,
            layer=layer,
            scenario=shared_scenario,
            expected_fixture=shared_scenario.fixture,
            required_semantic_events=matrix.shared_runtime_required_semantic_events,
            required_block_types=shared_scenario.required_block_types,
            required_interactions=matrix.shared_runtime_required_interactions,
            chart_policy=matrix.shared_runtime_chart_policy,
        )
        for layer in matrix.shared_runtime_layers
    ]
    requirements.extend(
        ReleaseRequirement(
            requirement_id=f"{scenario.scenario_id}:{layer.value}",
            scenario_id=scenario.scenario_id,
            layer=layer,
            scenario=scenario,
            expected_fixture=scenario.fixture,
            required_semantic_events=scenario.required_semantic_events,
            required_block_types=scenario.required_block_types,
            required_interactions=scenario.required_interactions,
            chart_policy=scenario.chart_policy,
        )
        for scenario in matrix.scenarios
        for layer in scenario.required_layers
    )
    requirements.extend(
        ReleaseRequirement(
            requirement_id=(
                f"{target.scenario_id}:"
                f"{ValidationLayer.REAL_PROVIDER_ANALYSIS_JOURNEY.value}"
            ),
            scenario_id=target.scenario_id,
            layer=ValidationLayer.REAL_PROVIDER_ANALYSIS_JOURNEY,
            scenario=scenarios[target.scenario_id],
            expected_fixture=target.fixture,
            required_semantic_events=scenarios[target.scenario_id].required_semantic_events,
            required_block_types=scenarios[target.scenario_id].required_block_types,
            required_interactions=scenarios[target.scenario_id].required_interactions,
            chart_policy=scenarios[target.scenario_id].chart_policy,
        )
        for target in matrix.representative_provider_targets
    )
    requirements.extend(
        ReleaseRequirement(
            requirement_id=(
                f"{target.scenario_id}:"
                f"{ValidationLayer.HUMAN_SEMANTIC_REVIEW.value}"
            ),
            scenario_id=target.scenario_id,
            layer=ValidationLayer.HUMAN_SEMANTIC_REVIEW,
            scenario=scenarios[target.scenario_id],
            expected_fixture=target.fixture,
            required_semantic_events=scenarios[target.scenario_id].required_semantic_events,
            required_block_types=scenarios[target.scenario_id].required_block_types,
            required_interactions=scenarios[target.scenario_id].required_interactions,
            chart_policy=scenarios[target.scenario_id].chart_policy,
        )
        for target in matrix.representative_human_targets
    )
    targets = [(item.scenario_id, item.layer) for item in requirements]
    if len(targets) != len(set(targets)):
        raise ValueError("release matrix has duplicate receipt targets")
    return tuple(requirements)


@dataclass(frozen=True, slots=True)
class ReleaseReceipt:
    receipt_id: str
    source_digest: str
    scenario_id: str
    layer: ValidationLayer
    status: LayerStatus
    evidence_refs: tuple[str, ...]
    oracle_identity: str
    fixture_path: str = ""
    first_failure_stage: str = ""
    provider_calls: int = 0
    provider_authorization_ref: str = ""
    semantic_dimensions: tuple[tuple[str, LayerStatus], ...] = ()
    historical_technical_stability: LayerStatus | None = None
    observed_semantic_events: tuple[str, ...] = ()
    observed_block_types: tuple[str, ...] = ()
    observed_interactions: tuple[str, ...] = ()
    chart_observation: str = ""
    forbidden_behavior_hits: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "receipt_id", _required(self.receipt_id, "receipt_id"))
        object.__setattr__(self, "source_digest", _digest(self.source_digest))
        object.__setattr__(self, "scenario_id", _required(self.scenario_id, "scenario_id"))
        object.__setattr__(self, "oracle_identity", _required(self.oracle_identity, "oracle_identity"))
        object.__setattr__(self, "fixture_path", str(self.fixture_path or "").strip().replace("\\", "/"))
        refs = tuple(str(item).strip() for item in self.evidence_refs if str(item).strip())
        object.__setattr__(self, "evidence_refs", refs)
        if not refs:
            raise ValueError("evidence_refs is required")
        if self.status is not LayerStatus.PASS and not str(self.first_failure_stage).strip():
            raise ValueError("non-pass receipt requires first_failure_stage")
        if isinstance(self.provider_calls, bool) or self.provider_calls < 0:
            raise ValueError("provider_calls must be a non-negative integer")
        if self.layer is not ValidationLayer.REAL_PROVIDER_ANALYSIS_JOURNEY and self.provider_calls:
            raise ValueError("provider_calls are valid only for real-provider receipts")
        if self.provider_calls and not str(self.provider_authorization_ref).strip():
            raise ValueError("provider calls require provider_authorization_ref")
        if (
            self.layer is ValidationLayer.REAL_PROVIDER_ANALYSIS_JOURNEY
            and self.status is LayerStatus.PASS
            and self.provider_calls < 1
        ):
            raise ValueError("passing real-provider receipt requires provider_calls")
        dimensions = tuple((str(key).strip(), LayerStatus(status)) for key, status in self.semantic_dimensions)
        object.__setattr__(self, "semantic_dimensions", dimensions)
        dimension_keys = [key for key, _ in dimensions]
        if len(dimension_keys) != len(set(dimension_keys)):
            raise ValueError("semantic dimension keys must be unique")
        if self.layer is ValidationLayer.HUMAN_SEMANTIC_REVIEW:
            if set(dimension_keys) != set(HUMAN_REVIEW_DIMENSIONS):
                raise ValueError("human semantic receipt requires every review dimension")
            if self.status is LayerStatus.PASS and any(
                status is not LayerStatus.PASS for _, status in dimensions
            ):
                raise ValueError("passing human semantic receipt requires every dimension to pass")
            if (
                self.historical_technical_stability is not None
                and self.status is LayerStatus.PASS
            ):
                raise ValueError("historical technical stability cannot accompany a passing human receipt")
        elif dimensions:
            raise ValueError("semantic_dimensions are valid only for human review receipts")
        elif self.historical_technical_stability is not None:
            raise ValueError("historical technical stability is valid only for human review receipts")
        for field_name in (
            "observed_semantic_events", "observed_block_types", "observed_interactions",
            "forbidden_behavior_hits"
        ):
            values = tuple(
                str(item).strip() for item in getattr(self, field_name) if str(item).strip()
            )
            object.__setattr__(self, field_name, values)
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} must be unique")
        if self.chart_observation not in {
            "", "rendered", "not_warranted", "forbidden_absent", "failed"
        }:
            raise ValueError("invalid chart_observation")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ReleaseReceipt":
        raw_dimensions = dict(value.get("semantic_dimensions") or {})
        historical_stability = raw_dimensions.pop("stability", None)
        return cls(
            receipt_id=value.get("receipt_id", ""),
            source_digest=value.get("source_digest", ""),
            scenario_id=value.get("scenario_id", ""),
            layer=ValidationLayer(value.get("layer", "")),
            status=LayerStatus(value.get("status", "")),
            evidence_refs=tuple(value.get("evidence_refs") or ()),
            oracle_identity=value.get("oracle_identity", ""),
            fixture_path=value.get("fixture_path", ""),
            first_failure_stage=value.get("first_failure_stage", ""),
            provider_calls=value.get("provider_calls", 0),
            provider_authorization_ref=value.get("provider_authorization_ref", ""),
            semantic_dimensions=tuple(
                (key, LayerStatus(status)) for key, status in raw_dimensions.items()
            ),
            historical_technical_stability=(
                LayerStatus(historical_stability)
                if historical_stability is not None
                else None
            ),
            observed_semantic_events=tuple(value.get("observed_semantic_events") or ()),
            observed_block_types=tuple(value.get("observed_block_types") or ()),
            observed_interactions=tuple(value.get("observed_interactions") or ()),
            chart_observation=value.get("chart_observation", ""),
            forbidden_behavior_hits=tuple(value.get("forbidden_behavior_hits") or ()),
        )


@dataclass(frozen=True, slots=True)
class ReleaseEvidenceRecord:
    """An append-only validation observation that can deterministically mint one receipt."""

    evidence_id: str
    source_digest: str
    scenario_id: str
    layer: ValidationLayer
    status: LayerStatus
    evidence_refs: tuple[str, ...]
    oracle_identity: str
    fixture_path: str = ""
    first_failure_stage: str = ""
    provider_calls: int = 0
    provider_authorization_ref: str = ""
    semantic_dimensions: tuple[tuple[str, LayerStatus], ...] = ()
    observed_semantic_events: tuple[str, ...] = ()
    observed_block_types: tuple[str, ...] = ()
    observed_interactions: tuple[str, ...] = ()
    chart_observation: str = ""
    forbidden_behavior_hits: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_id", _required(self.evidence_id, "evidence_id"))
        object.__setattr__(self, "source_digest", _digest(self.source_digest))
        object.__setattr__(self, "scenario_id", _required(self.scenario_id, "scenario_id"))
        object.__setattr__(self, "layer", ValidationLayer(self.layer))
        object.__setattr__(self, "status", LayerStatus(self.status))
        # Reuse the receipt validator so evidence cannot mint a weaker receipt.
        self.to_receipt()

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ReleaseEvidenceRecord":
        return cls(
            evidence_id=value.get("evidence_id", ""),
            source_digest=value.get("source_digest", ""),
            scenario_id=value.get("scenario_id", ""),
            layer=ValidationLayer(value.get("layer", "")),
            status=LayerStatus(value.get("status", "")),
            evidence_refs=tuple(value.get("evidence_refs") or ()),
            oracle_identity=value.get("oracle_identity", ""),
            fixture_path=value.get("fixture_path", ""),
            first_failure_stage=value.get("first_failure_stage", ""),
            provider_calls=value.get("provider_calls", 0),
            provider_authorization_ref=value.get("provider_authorization_ref", ""),
            semantic_dimensions=tuple(
                (key, LayerStatus(status))
                for key, status in dict(value.get("semantic_dimensions") or {}).items()
            ),
            observed_semantic_events=tuple(value.get("observed_semantic_events") or ()),
            observed_block_types=tuple(value.get("observed_block_types") or ()),
            observed_interactions=tuple(value.get("observed_interactions") or ()),
            chart_observation=value.get("chart_observation", ""),
            forbidden_behavior_hits=tuple(value.get("forbidden_behavior_hits") or ()),
        )

    def to_receipt(self) -> ReleaseReceipt:
        return ReleaseReceipt(
            receipt_id=f"receipt_{self.evidence_id}",
            source_digest=self.source_digest,
            scenario_id=self.scenario_id,
            layer=self.layer,
            status=self.status,
            evidence_refs=self.evidence_refs,
            oracle_identity=self.oracle_identity,
            fixture_path=self.fixture_path,
            first_failure_stage=self.first_failure_stage,
            provider_calls=self.provider_calls,
            provider_authorization_ref=self.provider_authorization_ref,
            semantic_dimensions=self.semantic_dimensions,
            observed_semantic_events=self.observed_semantic_events,
            observed_block_types=self.observed_block_types,
            observed_interactions=self.observed_interactions,
            chart_observation=self.chart_observation,
            forbidden_behavior_hits=self.forbidden_behavior_hits,
        )


def _receipt_payload(receipt: ReleaseReceipt) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "receipt_id": receipt.receipt_id,
        "source_digest": receipt.source_digest,
        "scenario_id": receipt.scenario_id,
        "layer": receipt.layer.value,
        "status": receipt.status.value,
        "evidence_refs": list(receipt.evidence_refs),
        "oracle_identity": receipt.oracle_identity,
    }
    optional_fields = {
        "first_failure_stage": receipt.first_failure_stage,
        "fixture_path": receipt.fixture_path,
        "provider_calls": receipt.provider_calls,
        "provider_authorization_ref": receipt.provider_authorization_ref,
        "semantic_dimensions": {
            key: status.value for key, status in receipt.semantic_dimensions
        },
        "observed_semantic_events": list(receipt.observed_semantic_events),
        "observed_block_types": list(receipt.observed_block_types),
        "observed_interactions": list(receipt.observed_interactions),
        "chart_observation": receipt.chart_observation,
        "forbidden_behavior_hits": list(receipt.forbidden_behavior_hits),
    }
    payload.update(
        {key: value for key, value in optional_fields.items() if value not in ("", 0, {}, [])}
    )
    return payload


def project_release_status(
    matrix: ReleaseMatrix,
    evidence: Iterable[ReleaseEvidenceRecord],
    *,
    current_source_digest: str,
) -> dict[str, Any]:
    """Project current readiness from append-only observations without mutating them."""

    receipts = tuple(record.to_receipt() for record in evidence)
    decision = evaluate_release_readiness(
        matrix, receipts, current_source_digest=current_source_digest
    )
    requirements = _release_requirements(matrix)
    by_requirement: dict[tuple[str, ValidationLayer], list[ReleaseReceipt]] = {}
    for receipt in receipts:
        if receipt.source_digest == decision.source_digest:
            by_requirement.setdefault((receipt.scenario_id, receipt.layer), []).append(receipt)

    summary = {"total": len(requirements), "pass": 0, "fail": 0, "blocked": 0, "not_run": 0, "conflict": 0, "incomplete": 0}
    gaps: list[str] = []
    first_failure: dict[str, str] | None = None
    for requirement in requirements:
        matches = by_requirement.get((requirement.scenario_id, requirement.layer), [])
        stage = ""
        if not matches:
            category = "not_run"
            stage = "not_run"
        elif len(matches) > 1:
            category = "conflict"
            stage = "conflicting_receipts"
        else:
            receipt = matches[0]
            if receipt.status is LayerStatus.PASS and _receipt_covers_requirement(receipt, requirement):
                category = "pass"
            elif receipt.status is LayerStatus.PASS:
                category = "incomplete"
                stage = "receipt_coverage_incomplete"
            else:
                category = receipt.status.value
                stage = receipt.first_failure_stage
        summary[category] += 1
        if category != "pass":
            gaps.append(requirement.requirement_id)
            if first_failure is None:
                first_failure = {"requirement": requirement.requirement_id, "stage": stage}
    return {
        "version": "v2_release_status_projection.v1",
        "source_digest": decision.source_digest,
        "matrix_version": matrix.version,
        "status": decision.status.value,
        "summary": summary,
        "first_failure": first_failure,
        "root_cutover_gaps": gaps,
        "decision": decision.to_dict(),
        "receipts": [_receipt_payload(receipt) for receipt in receipts],
    }


@dataclass(frozen=True, slots=True)
class ReleaseReadinessDecision:
    status: ReadinessStatus
    source_digest: str
    missing_requirements: tuple[str, ...]
    non_pass_requirements: tuple[str, ...]
    conflicting_requirements: tuple[str, ...]
    stale_receipt_ids: tuple[str, ...]
    unknown_receipt_ids: tuple[str, ...]
    incomplete_receipt_ids: tuple[str, ...]
    provider_calls: int
    root_switch_authorized: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "source_digest": self.source_digest,
            "missing_requirements": list(self.missing_requirements),
            "non_pass_requirements": list(self.non_pass_requirements),
            "conflicting_requirements": list(self.conflicting_requirements),
            "stale_receipt_ids": list(self.stale_receipt_ids),
            "unknown_receipt_ids": list(self.unknown_receipt_ids),
            "incomplete_receipt_ids": list(self.incomplete_receipt_ids),
            "provider_calls": self.provider_calls,
            "root_switch_authorized": self.root_switch_authorized,
        }


def _git(root: Path, *args: str) -> bytes:
    try:
        result = subprocess.run(
            ["git", *args], cwd=root, check=True, capture_output=True
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ValueError(f"unable to compute Git-bound source identity: {args}") from exc
    return result.stdout


def compute_release_source_digest(root: Path | str) -> ReleaseSourceSnapshot:
    repository = Path(root).resolve()
    if not (repository / ".git").exists():
        raise ValueError("release source root must be a Git worktree")
    pathspecs = ("src", "scripts", "tests", "pyproject.toml")
    raw_paths = _git(
        repository,
        "-c", "core.quotepath=false",
        "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--",
        *pathspecs,
    )
    paths = sorted(
        {
            item.decode("utf-8", errors="surrogateescape").replace("\\", "/")
            for item in raw_paths.split(b"\0")
            if item
        }
    )
    identities: list[tuple[str, str]] = []
    for relative in paths:
        absolute = repository / Path(relative)
        if not absolute.is_file():
            continue
        blob = _git(
            repository,
            "hash-object", f"--path={relative}", "--", relative,
        ).decode("ascii").strip()
        identities.append((relative, blob))
    manifest = "\n".join(f"{path}\0{blob}" for path, blob in identities)
    source_digest = f"sha256:{hashlib.sha256(manifest.encode('utf-8')).hexdigest()}"
    try:
        git_head = _git(repository, "rev-parse", "HEAD").decode("ascii").strip()
    except ValueError:
        git_head = ""
    dirty_output = _git(
        repository, "status", "--porcelain=v1", "--untracked-files=all", "--", *pathspecs
    )
    return ReleaseSourceSnapshot(
        version="v2_release_source.v1",
        source_digest=source_digest,
        files=tuple(path for path, _ in identities),
        git_head=git_head,
        dirty=bool(dirty_output.strip()),
    )


def load_release_matrix(path: Path | str) -> ReleaseMatrix:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("scenarios"), list):
        raise ValueError("invalid release matrix")
    shared_runtime = value.get("shared_runtime")
    if not isinstance(shared_runtime, dict):
        raise ValueError("release matrix shared_runtime is required")
    representative = value.get("representative_validation")
    if not isinstance(representative, dict):
        raise ValueError("release matrix representative_validation is required")

    def targets(field_name: str) -> tuple[RepresentativeValidationTarget, ...]:
        raw_targets = representative.get(field_name)
        if not isinstance(raw_targets, list) or not all(
            isinstance(item, dict) for item in raw_targets
        ):
            raise ValueError(f"representative_validation {field_name} is required")
        return tuple(
            RepresentativeValidationTarget(
                scenario_id=item.get("scenario_id", ""),
                fixture=item.get("fixture", ""),
            )
            for item in raw_targets
        )
    scenarios = []
    for item in value["scenarios"]:
        if not isinstance(item, dict):
            raise ValueError("invalid release matrix scenario")
        scenarios.append(
            ScenarioRequirement(
                scenario_id=item.get("scenario_id", ""),
                user_value=item.get("user_value", ""),
                entry=item.get("entry", ""),
                fixture=item.get("fixture", ""),
                required_layers=tuple(
                    ValidationLayer(layer) for layer in item.get("required_layers") or ()
                ),
                required_semantic_events=tuple(item.get("required_semantic_events") or ()),
                required_block_types=tuple(item.get("required_block_types") or ()),
                required_interactions=tuple(item.get("required_interactions") or ()),
                chart_policy=item.get("chart_policy", ""),
                forbidden_behaviors=tuple(item.get("forbidden_behaviors") or ()),
            )
        )
    return ReleaseMatrix(
        version=value.get("version", ""),
        scenarios=tuple(scenarios),
        shared_runtime_scenario_id=shared_runtime.get("scenario_id", ""),
        shared_runtime_layers=tuple(
            ValidationLayer(layer) for layer in shared_runtime.get("layers") or ()
        ),
        shared_runtime_required_semantic_events=tuple(
            shared_runtime.get("required_semantic_events") or ()
        ),
        shared_runtime_required_interactions=tuple(
            shared_runtime.get("required_interactions") or ()
        ),
        shared_runtime_chart_policy=shared_runtime.get("chart_policy", ""),
        representative_provider_targets=targets("real_provider"),
        representative_human_targets=targets("human_semantic"),
        provider_call_budget=representative.get("provider_call_budget", 0),
    )


def evaluate_release_readiness(
    matrix: ReleaseMatrix,
    receipts: Iterable[ReleaseReceipt],
    *,
    current_source_digest: str,
) -> ReleaseReadinessDecision:
    digest = _digest(current_source_digest)
    requirements = _release_requirements(matrix)
    required_targets = {(item.scenario_id, item.layer) for item in requirements}
    current: dict[tuple[str, ValidationLayer], list[ReleaseReceipt]] = {}
    stale_ids: list[str] = []
    unknown_ids: list[str] = []
    provider_calls = 0
    for receipt in receipts:
        if receipt.source_digest != digest:
            stale_ids.append(receipt.receipt_id)
            continue
        key = (receipt.scenario_id, receipt.layer)
        if key not in required_targets:
            unknown_ids.append(receipt.receipt_id)
            continue
        current.setdefault(key, []).append(receipt)
        if receipt.layer is ValidationLayer.REAL_PROVIDER_ANALYSIS_JOURNEY:
            provider_calls += receipt.provider_calls

    missing: list[str] = []
    non_pass: list[str] = []
    conflicts: list[str] = []
    incomplete_ids: list[str] = []
    for requirement in requirements:
        matches = current.get((requirement.scenario_id, requirement.layer), [])
        if not matches:
            missing.append(requirement.requirement_id)
        elif len(matches) > 1:
            conflicts.append(requirement.requirement_id)
        elif matches[0].status is not LayerStatus.PASS:
            non_pass.append(requirement.requirement_id)
        elif not _receipt_covers_requirement(matches[0], requirement):
            incomplete_ids.append(matches[0].receipt_id)

    ready = not (missing or non_pass or conflicts or unknown_ids or incomplete_ids)
    return ReleaseReadinessDecision(
        status=(
            ReadinessStatus.READY_FOR_HUMAN_DECISION
            if ready
            else ReadinessStatus.NOT_READY
        ),
        source_digest=digest,
        missing_requirements=tuple(missing),
        non_pass_requirements=tuple(non_pass),
        conflicting_requirements=tuple(conflicts),
        stale_receipt_ids=tuple(sorted(stale_ids)),
        unknown_receipt_ids=tuple(sorted(unknown_ids)),
        incomplete_receipt_ids=tuple(sorted(incomplete_ids)),
        provider_calls=provider_calls,
        root_switch_authorized=False,
    )


def _receipt_covers_requirement(
    receipt: ReleaseReceipt, requirement: ReleaseRequirement
) -> bool:
    if receipt.forbidden_behavior_hits:
        return False
    if receipt.layer in {
        ValidationLayer.SCENARIO_SEMANTIC_ORACLE,
        ValidationLayer.REAL_PROVIDER_ANALYSIS_JOURNEY,
        ValidationLayer.HUMAN_SEMANTIC_REVIEW,
    } and receipt.fixture_path != requirement.expected_fixture.replace("\\", "/"):
        return False

    def chart_policy_covered() -> bool:
        if requirement.chart_policy == "required":
            return receipt.chart_observation == "rendered"
        if requirement.chart_policy == "conditional":
            return receipt.chart_observation in {"rendered", "not_warranted"}
        return receipt.chart_observation == "forbidden_absent"

    if receipt.layer is ValidationLayer.SSE_TRANSPORT_CONTRACT:
        return set(receipt.observed_semantic_events) >= set(requirement.required_semantic_events)
    if receipt.layer is ValidationLayer.BROWSER_INTERACTION_JOURNEY:
        if not set(receipt.observed_interactions) >= set(requirement.required_interactions):
            return False
        return chart_policy_covered()
    if receipt.layer is ValidationLayer.REFRESH_PERSISTENCE_JOURNEY:
        return "refresh_restore" in receipt.observed_interactions
    if receipt.layer is ValidationLayer.SCENARIO_SEMANTIC_ORACLE:
        return (
            set(receipt.observed_semantic_events) >= set(requirement.required_semantic_events)
            and set(receipt.observed_block_types) >= set(requirement.required_block_types)
            and chart_policy_covered()
        )
    if receipt.layer is ValidationLayer.REAL_PROVIDER_ANALYSIS_JOURNEY:
        return (
            receipt.provider_calls == 1
            and set(receipt.observed_semantic_events) >= set(requirement.required_semantic_events)
            and set(receipt.observed_block_types) >= set(requirement.required_block_types)
            and chart_policy_covered()
        )
    return True


def load_receipts(path: Path | str | None) -> tuple[ReleaseReceipt, ...]:
    if path is None:
        return ()
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError("receipt file must contain a JSON array")
    return tuple(ReleaseReceipt.from_dict(item) for item in value)


def load_release_evidence(path: Path | str) -> tuple[ReleaseEvidenceRecord, ...]:
    """Load only the append-only evidence-bundle shape used by the projector."""

    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if (
        not isinstance(value, dict)
        or value.get("version") != "v2_release_evidence.v1"
        or not isinstance(value.get("records"), list)
        or set(value) != {"version", "records"}
    ):
        raise ValueError("invalid release evidence bundle")
    records = tuple(ReleaseEvidenceRecord.from_dict(item) for item in value["records"] if isinstance(item, dict))
    if len(records) != len(value["records"]):
        raise ValueError("release evidence records must be objects")
    ids = [record.evidence_id for record in records]
    if len(ids) != len(set(ids)):
        raise ValueError("release evidence ids must be unique")
    return records
