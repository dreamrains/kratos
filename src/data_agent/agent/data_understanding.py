"""Canonical, deterministic data-understanding bundle contracts."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping


DATA_UNDERSTANDING_VERSION = "data_understanding.v1"

RELATIONSHIP_STATUSES = {
    "proposed",
    "validating",
    "validated",
    "rejected",
    "needs_confirmation",
}

_FINGERPRINT_EXCLUDED_PATHS = {
    ("id",),
    ("data_fingerprint",),
    ("created_at",),
    ("updated_at",),
    ("generated_at",),
}
_LIST_FIELDS = (
    "entities",
    "metrics",
    "dimensions",
    "time_ranges",
    "quality_findings",
    "relationship_candidates",
    "supported_questions",
    "unsupported_questions",
    "analysis_constraints",
)
_UNORDERED_LIST_PATHS = {
    ("datasets",),
    ("entities",),
    ("metrics",),
    ("dimensions",),
    ("quality_findings",),
    ("relationship_candidates",),
}
_IDENTIFIER_FIELDS = {
    "column",
    "contract_version",
    "dataset",
    "dataset_contract_id",
    "current_contract_id",
    "field",
    "grain",
    "id",
    "left_dataset",
    "left_key",
    "normalized_left_key",
    "right_dataset",
    "right_key",
    "normalized_right_key",
    "name",
    "status",
}
_SCALAR_IDENTIFIER_COLLECTIONS = {"entities", "metrics", "dimensions"}
_IDENTIFIER_ITEM_FIELDS = {
    "entities": {"entity", "identifier", "name", "id", "column", "field"},
    "metrics": {"metric", "identifier", "name", "id", "column", "field"},
    "dimensions": {"dimension", "identifier", "name", "id", "column", "field"},
}
_IDENTIFIER_LIST_FIELDS = {"columns", "shared_columns"}


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


@dataclass(frozen=True)
class BundleValidationResult:
    ok: bool
    bundle: Mapping[str, Any] = field(default_factory=dict)
    error_type: str = ""
    message: str = ""
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "bundle", _freeze(self.bundle))
        object.__setattr__(self, "details", _freeze(self.details))

    def thaw_bundle(self) -> dict[str, Any]:
        """Return an explicit mutable copy for callers that need ownership."""
        return _thaw(self.bundle)

    def thaw_details(self) -> dict[str, Any]:
        """Return an explicit mutable copy of validation details."""
        return _thaw(self.details)


def _error(error_type: str, message: str, **details: Any) -> BundleValidationResult:
    return BundleValidationResult(
        False,
        error_type=error_type,
        message=message,
        details=details,
    )


def _normalize_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    return " ".join(value.split())


def _normalize_identifier(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    return value.strip()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _is_identifier_path(path: tuple[str | int, ...]) -> bool:
    string_parts = [part for part in path if isinstance(part, str)]
    if not string_parts:
        return False
    field_name = string_parts[-1]
    return (
        field_name in _IDENTIFIER_FIELDS
        or field_name.endswith("_id")
        or "key_mapping" in string_parts
        or (
            len(path) == 2
            and path[0] in _SCALAR_IDENTIFIER_COLLECTIONS
            and isinstance(path[1], int)
        )
        or (
            len(path) >= 3
            and path[0] in _IDENTIFIER_ITEM_FIELDS
            and field_name in _IDENTIFIER_ITEM_FIELDS[path[0]]
        )
        or (
            len(path) >= 2
            and path[-2] in _IDENTIFIER_LIST_FIELDS
            and isinstance(path[-1], int)
        )
        or (len(path) == 2 and path[0] == "grain")
    )


def _normalize_semantic(value: Any, *, path: tuple[str | int, ...] = ()) -> Any:
    if isinstance(value, str):
        return value.strip() if _is_identifier_path(path) else " ".join(value.split())
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Non-finite numbers are not valid bundle content.")
        return value
    if isinstance(value, list):
        normalized = [
            _normalize_semantic(item, path=(*path, index))
            for index, item in enumerate(value)
        ]
        if path in _UNORDERED_LIST_PATHS:
            return sorted(normalized, key=_canonical_json)
        return normalized
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("Bundle object keys must be strings.")
        normalize_keys = bool(path and path[-1] == "key_mapping")
        normalized: dict[str, Any] = {}
        for key, item in sorted(value.items()):
            normalized_key = key.strip() if normalize_keys else key
            if not normalized_key or normalized_key in normalized:
                raise ValueError("Bundle object keys must be unique non-empty strings.")
            normalized[normalized_key] = _normalize_semantic(
                item,
                path=(*path, normalized_key),
            )
        return normalized
    raise ValueError(f"Unsupported bundle value type: {type(value).__name__}")


def _without_fingerprint_excluded_paths(
    value: Any,
    *,
    path: tuple[str | int, ...] = (),
) -> Any:
    if isinstance(value, list):
        return [
            _without_fingerprint_excluded_paths(item, path=(*path, index))
            for index, item in enumerate(value)
        ]
    if isinstance(value, dict):
        return {
            key: _without_fingerprint_excluded_paths(item, path=(*path, key))
            for key, item in value.items()
            if (*path, key) not in _FINGERPRINT_EXCLUDED_PATHS
        }
    return value


def _identity_for(bundle: dict[str, Any]) -> tuple[str, str]:
    semantic = _without_fingerprint_excluded_paths(bundle)
    digest = hashlib.sha256(_canonical_json(semantic).encode("utf-8")).hexdigest()
    return f"sha256:{digest}", f"dub_{digest[:16]}"


def _normalize_columns(value: Any, *, path: tuple[str | int, ...]) -> Any | None:
    if isinstance(value, list) and value:
        normalized: list[Any] = []
        for column in value:
            if isinstance(column, str):
                text = column.strip()
                if not text:
                    return None
                normalized.append(text)
                continue
            if isinstance(column, dict):
                name = _normalize_identifier(column.get("name"))
                if not name:
                    return None
                try:
                    item = _normalize_semantic(column, path=(*path, len(normalized)))
                except ValueError:
                    return None
                item["name"] = name
                normalized.append(item)
                continue
            return None
        return normalized
    if isinstance(value, dict) and value:
        if not all(isinstance(key, str) and key.strip() for key in value):
            return None
        try:
            normalized = {
                key.strip(): _normalize_semantic(item, path=(*path, key.strip()))
                for key, item in value.items()
            }
        except ValueError:
            return None
        if len(normalized) != len(value):
            return None
        return dict(sorted(normalized.items()))
    return None


def _normalize_dataset(dataset: Any, index: int) -> BundleValidationResult:
    if not isinstance(dataset, dict):
        return _error(
            "invalid_dataset_understanding",
            "Each dataset understanding must be an object.",
            index=index,
            fields=["dataset"],
        )

    dataset_name = _normalize_identifier(dataset.get("dataset"))
    contract_id = _normalize_identifier(
        dataset.get("dataset_contract_id", dataset.get("current_contract_id"))
    )
    grain = _normalize_identifier(dataset.get("grain"))
    rows = dataset.get("rows")
    columns_field = "columns" if "columns" in dataset else "schema"
    columns = _normalize_columns(
        dataset.get(columns_field),
        path=("datasets", index, columns_field),
    )

    invalid_fields: list[str] = []
    if not dataset_name:
        invalid_fields.append("dataset")
    if not contract_id:
        invalid_fields.append("dataset_contract_id")
    if not grain:
        invalid_fields.append("grain")
    if isinstance(rows, bool) or not isinstance(rows, int) or rows < 0:
        invalid_fields.append("rows")
    if columns is None:
        invalid_fields.append(columns_field)
    if invalid_fields:
        return _error(
            "invalid_dataset_understanding",
            "Dataset understanding is missing or has invalid required fields.",
            index=index,
            fields=invalid_fields,
        )

    try:
        normalized = _normalize_semantic(dataset, path=("datasets", index))
    except ValueError as exc:
        return _error(
            "invalid_dataset_understanding",
            str(exc),
            index=index,
            fields=["dataset"],
        )
    normalized["dataset"] = dataset_name
    normalized["dataset_contract_id"] = contract_id
    normalized.pop("current_contract_id", None)
    normalized["grain"] = grain
    normalized["rows"] = rows
    normalized[columns_field] = columns
    return BundleValidationResult(True, bundle=normalized)


def validate_data_understanding_bundle(bundle: Any) -> BundleValidationResult:
    if not isinstance(bundle, dict):
        return _error("invalid_bundle", "DataUnderstandingBundle must be an object.")
    if bundle.get("contract_version") != DATA_UNDERSTANDING_VERSION:
        return _error(
            "unsupported_contract_version",
            "DataUnderstandingBundle contract_version is not supported.",
            expected=DATA_UNDERSTANDING_VERSION,
            actual=bundle.get("contract_version"),
        )

    datasets = bundle.get("datasets")
    if not isinstance(datasets, list) or not datasets:
        return _error("invalid_datasets", "DataUnderstandingBundle requires a non-empty datasets list.")

    normalized_datasets: list[dict[str, Any]] = []
    for index, dataset in enumerate(datasets):
        result = _normalize_dataset(dataset, index)
        if not result.ok:
            return result
        normalized_datasets.append(result.thaw_bundle())

    relationships = bundle.get("relationship_candidates", [])
    if not isinstance(relationships, list):
        return _error(
            "invalid_relationship_candidate",
            "relationship_candidates must be a list of hypothesis objects.",
        )
    normalized_relationships: list[dict[str, Any]] = []
    for index, relationship in enumerate(relationships):
        status = _normalize_text(relationship.get("status")) if isinstance(relationship, dict) else None
        if not isinstance(relationship, dict) or status not in RELATIONSHIP_STATUSES:
            return _error(
                "invalid_relationship_candidate",
                "Relationship candidate has an invalid hypothesis status.",
                index=index,
                allowed_statuses=sorted(RELATIONSHIP_STATUSES),
            )
        normalized_relationship = dict(relationship)
        normalized_relationship["status"] = status
        normalized_relationships.append(normalized_relationship)

    for field_name in _LIST_FIELDS:
        value = bundle.get(field_name, [])
        if not isinstance(value, list):
            return _error(
                "invalid_bundle_field",
                f"{field_name} must be a list.",
                field=field_name,
            )

    version = bundle.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version != 1:
        return _error(
            "invalid_bundle_version",
            "DataUnderstandingBundle version must be the integer 1.",
            actual=version,
        )
    grain = bundle.get("grain")
    if not isinstance(grain, dict) or not all(isinstance(key, str) for key in grain):
        return _error(
            "invalid_bundle_grain",
            "DataUnderstandingBundle grain must be an object with string keys.",
        )

    normalized_source = dict(bundle)
    normalized_source["contract_version"] = DATA_UNDERSTANDING_VERSION
    normalized_source["datasets"] = normalized_datasets
    normalized_source["relationship_candidates"] = normalized_relationships
    for field_name in _LIST_FIELDS:
        normalized_source.setdefault(field_name, [])

    try:
        normalized = _normalize_semantic(normalized_source)
    except ValueError as exc:
        return _error("invalid_bundle_content", str(exc))
    fingerprint, bundle_id = _identity_for(normalized)
    existing_fingerprint = bundle.get("data_fingerprint")
    existing_id = bundle.get("id")
    if (
        existing_fingerprint is not None and existing_fingerprint != fingerprint
    ) or (
        existing_id is not None and existing_id != bundle_id
    ):
        return _error(
            "bundle_identity_mismatch",
            "DataUnderstandingBundle identity does not match its normalized semantic content.",
            expected_id=bundle_id,
            expected_data_fingerprint=fingerprint,
        )
    normalized["data_fingerprint"] = fingerprint
    normalized["id"] = bundle_id
    return BundleValidationResult(True, bundle=normalized)


def build_data_understanding_bundle(
    *,
    datasets: list[dict[str, Any]],
    quality_findings: list[Any],
    relationship_candidates: list[dict[str, Any]],
    entities: list[Any] | None = None,
    metrics: list[Any] | None = None,
    dimensions: list[Any] | None = None,
    time_ranges: list[Any] | None = None,
    grain: dict[str, Any] | None = None,
    supported_questions: list[Any] | None = None,
    unsupported_questions: list[Any] | None = None,
    analysis_constraints: list[Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "contract_version": DATA_UNDERSTANDING_VERSION,
        "version": 1,
        "datasets": datasets,
        "entities": [] if entities is None else entities,
        "metrics": [] if metrics is None else metrics,
        "dimensions": [] if dimensions is None else dimensions,
        "time_ranges": [] if time_ranges is None else time_ranges,
        "grain": {} if grain is None else grain,
        "quality_findings": quality_findings,
        "relationship_candidates": relationship_candidates,
        "supported_questions": [] if supported_questions is None else supported_questions,
        "unsupported_questions": [] if unsupported_questions is None else unsupported_questions,
        "analysis_constraints": [] if analysis_constraints is None else analysis_constraints,
    }
    result = validate_data_understanding_bundle(payload)
    if not result.ok:
        raise ValueError(f"{result.error_type}: {result.message}")
    return result.thaw_bundle()
