from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

import pandas as pd

from data_agent.v2.identity import require_storage_id


class DatasetRole(StrEnum):
    RAW = "raw"
    ANALYSIS = "analysis"
    CANDIDATE = "candidate"


@dataclass(frozen=True, slots=True)
class DatasetVersion:
    dataset_version_id: str
    logical_dataset_id: str
    role: DatasetRole
    parent_version_id: str
    source_identity: str
    content_fingerprint: str
    schema_fingerprint: str
    row_count: int
    column_schema: tuple[tuple[str, str], ...]
    transform: dict[str, Any] = field(default_factory=dict)


def frame_fingerprint(frame: pd.DataFrame) -> str:
    digest = hashlib.sha256()
    schema = [(str(column), str(dtype)) for column, dtype in frame.dtypes.items()]
    digest.update(json.dumps(schema, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    digest.update(str(len(frame)).encode("ascii"))
    digest.update(pd.util.hash_pandas_object(frame, index=True).values.tobytes())
    return f"sha256:{digest.hexdigest()}"


def _schema_fingerprint(frame: pd.DataFrame) -> str:
    schema = [(str(column), str(dtype)) for column, dtype in frame.dtypes.items()]
    payload = json.dumps(schema, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp_path = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(
                value,
                handle,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temp_path.replace(path)
    finally:
        temp_path.unlink(missing_ok=True)


class DatasetRegistry:
    """Session-owned immutable dataset versions for the V2 runtime."""

    def __init__(self, sessions_root: Path | str, session_id: str) -> None:
        safe_session_id = require_storage_id(session_id, "session_id")
        self.root = Path(sessions_root) / safe_session_id / "v2" / "datasets"
        self.root.mkdir(parents=True, exist_ok=True)
        self._manifest_path = self.root / "manifest.json"
        self._versions = self._load_manifest()

    def _load_manifest(self) -> list[DatasetVersion]:
        if not self._manifest_path.exists():
            return []
        values = json.loads(self._manifest_path.read_text(encoding="utf-8"))
        return [
            DatasetVersion(
                dataset_version_id=value["dataset_version_id"],
                logical_dataset_id=value["logical_dataset_id"],
                role=DatasetRole(value["role"]),
                parent_version_id=value.get("parent_version_id", ""),
                source_identity=value.get("source_identity", ""),
                content_fingerprint=value["content_fingerprint"],
                schema_fingerprint=value["schema_fingerprint"],
                row_count=int(value["row_count"]),
                column_schema=tuple(tuple(item) for item in value.get("column_schema") or ()),
                transform=dict(value.get("transform") or {}),
            )
            for value in values
        ]

    def _save_manifest(self) -> None:
        _atomic_json(self._manifest_path, [asdict(item) for item in self._versions])

    def _frame_path(self, version_id: str) -> Path:
        return self.root / f"{version_id}.pkl"

    def _version_id(
        self,
        *,
        logical_dataset_id: str,
        role: DatasetRole,
        parent_version_id: str,
        content_fingerprint: str,
        transform: dict[str, Any],
    ) -> str:
        payload = json.dumps(
            {
                "logical_dataset_id": logical_dataset_id,
                "role": role,
                "parent_version_id": parent_version_id,
                "content_fingerprint": content_fingerprint,
                "transform": transform,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return f"dv_{hashlib.sha256(payload).hexdigest()[:24]}"

    def _persist_version(self, version: DatasetVersion, frame: pd.DataFrame) -> DatasetVersion:
        existing = next(
            (item for item in self._versions if item.dataset_version_id == version.dataset_version_id),
            None,
        )
        if existing is not None:
            if existing != version:
                raise ValueError(f"dataset version conflict: {version.dataset_version_id}")
            return existing
        frame_path = self._frame_path(version.dataset_version_id)
        if frame_path.exists():
            raise ValueError(f"orphan dataset frame exists: {version.dataset_version_id}")
        fd, name = tempfile.mkstemp(
            prefix=f".{version.dataset_version_id}.", suffix=".pkl.tmp", dir=self.root
        )
        os.close(fd)
        temp_frame_path = Path(name)
        try:
            frame.copy(deep=True).to_pickle(temp_frame_path)
            temp_frame_path.replace(frame_path)
        finally:
            temp_frame_path.unlink(missing_ok=True)
        self._versions.append(version)
        try:
            self._save_manifest()
        except Exception:
            self._versions.pop()
            frame_path.unlink(missing_ok=True)
            raise
        return version

    def register_raw(
        self,
        logical_dataset_id: str,
        frame: pd.DataFrame,
        *,
        source_identity: str,
    ) -> DatasetVersion:
        logical_id = str(logical_dataset_id or "").strip()
        source_id = str(source_identity or "").strip()
        if not logical_id or not source_id:
            raise ValueError("logical_dataset_id and source_identity are required")
        prior_raw = next(
            (
                item
                for item in self._versions
                if item.logical_dataset_id == logical_id and item.role is DatasetRole.RAW
            ),
            None,
        )
        if prior_raw is not None and prior_raw.source_identity != source_id:
            raise ValueError("raw source identity differs for existing logical dataset")
        content = frame_fingerprint(frame)
        transform: dict[str, Any] = {}
        version = DatasetVersion(
            dataset_version_id=self._version_id(
                logical_dataset_id=logical_id,
                role=DatasetRole.RAW,
                parent_version_id="",
                content_fingerprint=content,
                transform=transform,
            ),
            logical_dataset_id=logical_id,
            role=DatasetRole.RAW,
            parent_version_id="",
            source_identity=source_id,
            content_fingerprint=content,
            schema_fingerprint=_schema_fingerprint(frame),
            row_count=len(frame),
            column_schema=tuple((str(column), str(dtype)) for column, dtype in frame.dtypes.items()),
            transform=transform,
        )
        if prior_raw is not None and prior_raw.dataset_version_id != version.dataset_version_id:
            raise ValueError("raw content differs for existing logical dataset")
        return self._persist_version(version, frame)

    def derive(
        self,
        *,
        parent_version_id: str,
        frame: pd.DataFrame,
        role: DatasetRole,
        transform: dict[str, Any],
    ) -> DatasetVersion:
        if role is DatasetRole.RAW:
            raise ValueError("derive cannot create a raw version")
        parent = self.get_version(parent_version_id)
        normalized_transform = json.loads(
            json.dumps(transform, ensure_ascii=False, sort_keys=True, default=str)
        )
        if not normalized_transform:
            raise ValueError("transform is required for a derived version")
        content = frame_fingerprint(frame)
        version = DatasetVersion(
            dataset_version_id=self._version_id(
                logical_dataset_id=parent.logical_dataset_id,
                role=role,
                parent_version_id=parent.dataset_version_id,
                content_fingerprint=content,
                transform=normalized_transform,
            ),
            logical_dataset_id=parent.logical_dataset_id,
            role=role,
            parent_version_id=parent.dataset_version_id,
            source_identity=parent.source_identity,
            content_fingerprint=content,
            schema_fingerprint=_schema_fingerprint(frame),
            row_count=len(frame),
            column_schema=tuple((str(column), str(dtype)) for column, dtype in frame.dtypes.items()),
            transform=normalized_transform,
        )
        return self._persist_version(version, frame)

    def get_version(self, dataset_version_id: str) -> DatasetVersion:
        for item in self._versions:
            if item.dataset_version_id == dataset_version_id:
                return item
        raise KeyError(f"unknown dataset version {dataset_version_id}")

    def get_frame(self, dataset_version_id: str) -> pd.DataFrame:
        self.get_version(dataset_version_id)
        return pd.read_pickle(self._frame_path(dataset_version_id)).copy(deep=True)

    def list_versions(self, logical_dataset_id: str | None = None) -> list[DatasetVersion]:
        if logical_dataset_id is None:
            return list(self._versions)
        return [item for item in self._versions if item.logical_dataset_id == logical_dataset_id]
