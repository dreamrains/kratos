from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

import pandas as pd


def _canonical_container(value: Any) -> str:
    """Return a stable representation for container values in object columns."""

    def normalize(item: Any) -> Any:
        if isinstance(item, dict):
            pairs = [(normalize(key), normalize(val)) for key, val in item.items()]
            pairs.sort(key=lambda pair: json.dumps(pair[0], ensure_ascii=False, sort_keys=True, default=str))
            return {"type": "dict", "items": pairs}
        if isinstance(item, list):
            return {"type": "list", "items": [normalize(value) for value in item]}
        if isinstance(item, tuple):
            return {"type": "tuple", "items": [normalize(value) for value in item]}
        if isinstance(item, set):
            values = [normalize(value) for value in item]
            values.sort(key=lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True, default=str))
            return {"type": "set", "items": values}
        return item

    return json.dumps(normalize(value), ensure_ascii=False, sort_keys=True, default=str)


def frame_fingerprint(frame: pd.DataFrame) -> str:
    """Create a deterministic fingerprint from a frame's schema, index, and values."""
    schema = [(str(column), str(dtype)) for column, dtype in frame.dtypes.items()]
    hashable = frame.copy(deep=True)
    for position, dtype in enumerate(hashable.dtypes):
        if pd.api.types.is_object_dtype(dtype):
            hashable.iloc[:, position] = hashable.iloc[:, position].map(
                lambda value: _canonical_container(value)
                if isinstance(value, (dict, list, tuple, set))
                else value
            )
    values = pd.util.hash_pandas_object(hashable, index=True, categorize=True).values.tobytes()
    schema_bytes = json.dumps(schema, ensure_ascii=False).encode("utf-8")
    digest = hashlib.sha256(schema_bytes + values).hexdigest()
    return f"sha256:{digest}"


@dataclass(frozen=True)
class TransformationRecord:
    parent_dataset_id: str
    raw_dataset_id: str
    source_fingerprint: str
    logical_name: str
    operations: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    affected_columns: tuple[str, ...] = field(default_factory=tuple)
    affected_row_count: int = 0
    before_after_metrics: dict[str, Any] = field(default_factory=dict)
    information_loss: bool = False
    decision_policy: str = "auto_safe"
    confirmation_status: str = "not_required"
    derived_dataset_id: str = ""
    version: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["operations"] = [dict(item) for item in self.operations]
        payload["affected_columns"] = list(self.affected_columns)
        identity = {key: value for key, value in payload.items() if key not in {"created_at", "id"}}
        payload["id"] = "transform_" + hashlib.sha256(
            json.dumps(identity, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()[:16]
        return payload


def finalize_transformation_record(
    record: dict[str, Any],
    *,
    derived_dataset_id: str,
    version: int,
) -> dict[str, Any]:
    payload = dict(record)
    payload["derived_dataset_id"] = derived_dataset_id
    payload["version"] = version
    identity = {key: value for key, value in payload.items() if key not in {"created_at", "id"}}
    payload["id"] = "transform_" + hashlib.sha256(
        json.dumps(identity, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:16]
    return payload
