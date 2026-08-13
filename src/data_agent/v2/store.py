from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

from data_agent.v2.identity import require_storage_id
from data_agent.v2.models import (
    AnswerBlock,
    AnswerBlockDraft,
    AnswerBlockType,
    ClaimClass,
    Commitment,
    CommitmentPriority,
    EventType,
    ExecutionEvent,
    Finding,
    FindingKind,
)


class FactConflictError(RuntimeError):
    """Raised when an existing immutable fact ID is reused with new content."""


def _json_line(value: dict[str, Any]) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSONL record at {path}:{line_number}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"non-object JSONL record at {path}:{line_number}")
        records.append(value)
    return records


def _atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temp_path.replace(path)
    finally:
        temp_path.unlink(missing_ok=True)


class V2FactStore:
    """Session-local persistence for V2 immutable facts and answer blocks."""

    def __init__(self, sessions_root: Path | str, session_id: str) -> None:
        safe_session_id = require_storage_id(session_id, "session_id")
        self.root = Path(sessions_root) / safe_session_id / "v2"
        self.root.mkdir(parents=True, exist_ok=True)

    @property
    def _commitments_path(self) -> Path:
        return self.root / "commitments.json"

    @property
    def _events_path(self) -> Path:
        return self.root / "execution_events.jsonl"

    @property
    def _findings_path(self) -> Path:
        return self.root / "findings.jsonl"

    def write_commitments(self, commitments: list[Commitment]) -> None:
        ids = [item.commitment_id for item in commitments]
        if len(ids) != len(set(ids)):
            raise ValueError("commitment ids must be unique")
        _atomic_write_json(self._commitments_path, [asdict(item) for item in commitments])

    def read_commitments(self) -> list[Commitment]:
        if not self._commitments_path.exists():
            return []
        values = json.loads(self._commitments_path.read_text(encoding="utf-8"))
        return [
            Commitment(
                commitment_id=value["commitment_id"],
                priority=CommitmentPriority(value["priority"]),
                question=value["question"],
                dataset_version_ids=tuple(value.get("dataset_version_ids") or ()),
                accepted_result_kinds=tuple(
                    FindingKind(item) for item in value.get("accepted_result_kinds") or ()
                ),
                accepted_method_capabilities=tuple(
                    value.get("accepted_method_capabilities") or ()
                ),
                target_semantics=value.get("target_semantics", ""),
                activation_condition=value.get("activation_condition", ""),
                visualization_intent=value.get("visualization_intent", ""),
            )
            for value in values
        ]

    def _append_immutable(self, path: Path, id_field: str, record: dict[str, Any]) -> bool:
        fact_id = str(record.get(id_field) or "")
        canonical = _json_line(record)
        for existing in _read_jsonl(path):
            if existing.get(id_field) != fact_id:
                continue
            if _json_line(existing) == canonical:
                return False
            raise FactConflictError(f"immutable fact conflict for {fact_id}")
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(canonical + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return True

    def append_event(self, event: ExecutionEvent) -> bool:
        return self._append_immutable(
            self._events_path,
            "event_id",
            asdict(event),
        )

    def read_events(self) -> list[ExecutionEvent]:
        return [
            ExecutionEvent(
                event_id=value["event_id"],
                run_id=value["run_id"],
                commitment_id=value["commitment_id"],
                event_type=EventType(value["event_type"]),
                tool_call_id=value.get("tool_call_id", ""),
                tool_name=value.get("tool_name", ""),
                capability=value.get("capability", ""),
                dataset_version_ids=tuple(value.get("dataset_version_ids") or ()),
                input_digest=value.get("input_digest", ""),
                result_ref=value.get("result_ref", ""),
                error_code=value.get("error_code", ""),
                message=value.get("message", ""),
                timestamp=value.get("timestamp", ""),
            )
            for value in _read_jsonl(self._events_path)
        ]

    def append_finding(self, finding: Finding) -> bool:
        return self._append_immutable(
            self._findings_path,
            "finding_id",
            asdict(finding),
        )

    def read_findings(self) -> list[Finding]:
        return [
            Finding(
                finding_id=value["finding_id"],
                commitment_id=value["commitment_id"],
                finding_kind=FindingKind(value["finding_kind"]),
                dataset_version_ids=tuple(value.get("dataset_version_ids") or ()),
                metric_identity=value["metric_identity"],
                method_capability=value["method_capability"],
                maximum_claim_class=ClaimClass(value["maximum_claim_class"]),
                computation_ref=value["computation_ref"],
                feature_identity=value.get("feature_identity", ""),
                population_scope=value.get("population_scope", ""),
                time_scope=value.get("time_scope", ""),
                estimate=value.get("estimate"),
                unit=value.get("unit", ""),
                direction=value.get("direction", ""),
                effective_sample=value.get("effective_sample"),
                uncertainty=dict(value.get("uncertainty") or {}),
                assumption_results=dict(value.get("assumption_results") or {}),
                limitations=tuple(value.get("limitations") or ()),
                verification_level=value.get("verification_level", "structured_checked"),
            )
            for value in _read_jsonl(self._findings_path)
        ]

    def write_turn_blocks(
        self,
        turn_id: str,
        blocks: list[AnswerBlockDraft | AnswerBlock],
        *,
        status: str,
    ) -> None:
        safe_turn_id = require_storage_id(turn_id, "turn_id")
        if status not in {"draft", "finalized", "failed"}:
            raise ValueError("invalid turn status")
        _atomic_write_json(
            self.root / "turns" / f"{safe_turn_id}.json",
            {
                "turn_id": safe_turn_id,
                "status": status,
                "blocks": [asdict(item) for item in blocks],
            },
        )

    def read_turn_blocks(self, turn_id: str) -> dict[str, Any]:
        safe_turn_id = require_storage_id(turn_id, "turn_id")
        path = self.root / "turns" / f"{safe_turn_id}.json"
        if not path.exists():
            raise KeyError(f"unknown V2 turn {safe_turn_id}")
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("invalid V2 turn payload")
        return value
