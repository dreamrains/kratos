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
class ReleaseMatrix:
    version: str
    scenarios: tuple[ScenarioRequirement, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "version", _required(self.version, "version"))
        if not self.scenarios:
            raise ValueError("release matrix requires scenarios")
        ids = [item.scenario_id for item in self.scenarios]
        if len(ids) != len(set(ids)):
            raise ValueError("release matrix scenario ids must be unique")


@dataclass(frozen=True, slots=True)
class ReleaseReceipt:
    receipt_id: str
    source_digest: str
    scenario_id: str
    layer: ValidationLayer
    status: LayerStatus
    evidence_refs: tuple[str, ...]
    oracle_identity: str
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
    return ReleaseMatrix(version=value.get("version", ""), scenarios=tuple(scenarios))


def evaluate_release_readiness(
    matrix: ReleaseMatrix,
    receipts: Iterable[ReleaseReceipt],
    *,
    current_source_digest: str,
) -> ReleaseReadinessDecision:
    digest = _digest(current_source_digest)
    requirements = {
        (scenario.scenario_id, layer)
        for scenario in matrix.scenarios
        for layer in scenario.required_layers
    }
    current: dict[tuple[str, ValidationLayer], list[ReleaseReceipt]] = {}
    stale_ids: list[str] = []
    unknown_ids: list[str] = []
    provider_calls = 0
    for receipt in receipts:
        if receipt.source_digest != digest:
            stale_ids.append(receipt.receipt_id)
            continue
        key = (receipt.scenario_id, receipt.layer)
        if key not in requirements:
            unknown_ids.append(receipt.receipt_id)
            continue
        current.setdefault(key, []).append(receipt)
        if receipt.layer is ValidationLayer.REAL_PROVIDER_ANALYSIS_JOURNEY:
            provider_calls += receipt.provider_calls

    missing: list[str] = []
    non_pass: list[str] = []
    conflicts: list[str] = []
    incomplete_ids: list[str] = []
    scenario_by_id = {item.scenario_id: item for item in matrix.scenarios}
    for scenario_id, layer in sorted(requirements, key=lambda item: (item[0], item[1].value)):
        key_text = f"{scenario_id}:{layer.value}"
        matches = current.get((scenario_id, layer), [])
        if not matches:
            missing.append(key_text)
        elif len(matches) > 1:
            conflicts.append(key_text)
        elif matches[0].status is not LayerStatus.PASS:
            non_pass.append(key_text)
        elif not _receipt_covers_requirement(matches[0], scenario_by_id[scenario_id]):
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
    receipt: ReleaseReceipt, scenario: ScenarioRequirement
) -> bool:
    if receipt.forbidden_behavior_hits:
        return False
    if receipt.layer is ValidationLayer.SSE_TRANSPORT_CONTRACT:
        return set(receipt.observed_semantic_events) >= set(scenario.required_semantic_events)
    if receipt.layer is ValidationLayer.BROWSER_INTERACTION_JOURNEY:
        if not set(receipt.observed_interactions) >= set(scenario.required_interactions):
            return False
        if scenario.chart_policy == "required":
            return receipt.chart_observation == "rendered"
        if scenario.chart_policy == "conditional":
            return receipt.chart_observation in {"rendered", "not_warranted"}
        return receipt.chart_observation == "forbidden_absent"
    if receipt.layer is ValidationLayer.REFRESH_PERSISTENCE_JOURNEY:
        return "refresh_restore" in receipt.observed_interactions
    if receipt.layer is ValidationLayer.REAL_PROVIDER_ANALYSIS_JOURNEY:
        return set(receipt.observed_block_types) >= set(scenario.required_block_types)
    return True


def load_receipts(path: Path | str | None) -> tuple[ReleaseReceipt, ...]:
    if path is None:
        return ()
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError("receipt file must contain a JSON array")
    return tuple(ReleaseReceipt.from_dict(item) for item in value)
