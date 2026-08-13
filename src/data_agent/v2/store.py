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
    ChartArtifact,
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


def _atomic_write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(value)
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

    @property
    def _charts_path(self) -> Path:
        return self.root / "charts"

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

    def write_chart_artifact(self, artifact: ChartArtifact, html: str) -> bool:
        import hashlib

        chart_id = require_storage_id(artifact.chart_id, "chart_id")
        actual_fingerprint = f"sha256:{hashlib.sha256(html.encode('utf-8')).hexdigest()}"
        if actual_fingerprint != artifact.content_fingerprint:
            raise FactConflictError(f"chart content fingerprint mismatch for {chart_id}")
        expected_relative_path = f"charts/{chart_id}.html"
        if artifact.relative_path != expected_relative_path:
            raise ValueError("chart relative_path does not match chart_id")
        if artifact.purpose in {"evidence", "insight"}:
            known_findings = {item.finding_id for item in self.read_findings()}
            missing_findings = set(artifact.finding_refs) - known_findings
            if missing_findings:
                raise ValueError(
                    "chart finding_refs must exist in the session Evidence Ledger"
                )
        metadata_path = self._charts_path / f"{chart_id}.json"
        html_path = self._charts_path / f"{chart_id}.html"
        metadata = asdict(artifact)
        if metadata_path.exists() or html_path.exists():
            if not metadata_path.exists() or not html_path.exists():
                raise FactConflictError(f"incomplete chart artifact for {chart_id}")
            existing_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if (
                _json_line(existing_metadata) == _json_line(metadata)
                and html_path.read_text(encoding="utf-8") == html
            ):
                return False
            raise FactConflictError(f"immutable chart artifact conflict for {chart_id}")

        _atomic_write_text(html_path, html)
        try:
            _atomic_write_json(metadata_path, metadata)
        except Exception:
            html_path.unlink(missing_ok=True)
            raise
        return True

    def read_chart_artifact(self, chart_id: str) -> ChartArtifact:
        safe_chart_id = require_storage_id(chart_id, "chart_id")
        path = self._charts_path / f"{safe_chart_id}.json"
        if not path.exists():
            raise KeyError(f"unknown V2 chart {safe_chart_id}")
        value = json.loads(path.read_text(encoding="utf-8"))
        return ChartArtifact(
            chart_id=value["chart_id"],
            title=value["title"],
            chart_type=value["chart_type"],
            dataset_version_ids=tuple(value.get("dataset_version_ids") or ()),
            finding_refs=tuple(value.get("finding_refs") or ()),
            x_field=value["x_field"],
            y_fields=tuple(value.get("y_fields") or ()),
            purpose=value["purpose"],
            relative_path=value["relative_path"],
            content_fingerprint=value["content_fingerprint"],
        )

    def read_chart_html(self, chart_id: str) -> str:
        artifact = self.read_chart_artifact(chart_id)
        path = self.root / artifact.relative_path
        if not path.exists():
            raise KeyError(f"missing V2 chart content {artifact.chart_id}")
        return path.read_text(encoding="utf-8")

    def write_turn_blocks(
        self,
        turn_id: str,
        blocks: list[AnswerBlockDraft | AnswerBlock],
        *,
        status: str,
        artifact_ids: tuple[str, ...] = (),
        request_context: dict[str, str] | None = None,
    ) -> None:
        safe_turn_id = require_storage_id(turn_id, "turn_id")
        if status not in {"draft", "finalized", "failed"}:
            raise ValueError("invalid turn status")
        safe_artifact_ids = tuple(
            require_storage_id(item, "chart_id") for item in artifact_ids
        )
        if len(safe_artifact_ids) != len(set(safe_artifact_ids)):
            raise ValueError("artifact_ids must be unique")
        for chart_id in safe_artifact_ids:
            self.read_chart_artifact(chart_id)
        referenced_chart_ids = {
            chart_id for block in blocks for chart_id in block.chart_refs
        }
        missing_chart_ids = referenced_chart_ids - set(safe_artifact_ids)
        if missing_chart_ids:
            raise ValueError("answer block chart_refs must exist in artifact_ids")
        raw_context = dict(request_context or {})
        allowed_context_keys = {
            "filename",
            "metric",
            "target",
            "features",
            "analysis_unit",
            "time_field",
            "question",
            "analysis_kind",
            "date_column",
            "proposal_id",
            "group",
            "recommendation_intent",
            "action_risk",
            "reversible",
            "recommendation_mode",
            "frequency",
            "aggregation",
            "horizon",
        }
        if set(raw_context) - allowed_context_keys:
            raise ValueError("request_context contains unsupported fields")
        normalized_context = {
            key: str(value or "").strip()
            for key, value in raw_context.items()
            if str(value or "").strip()
        }
        _atomic_write_json(
            self.root / "turns" / f"{safe_turn_id}.json",
            {
                "turn_id": safe_turn_id,
                "status": status,
                "blocks": [asdict(item) for item in blocks],
                "artifact_ids": list(safe_artifact_ids),
                "request_context": normalized_context,
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
        artifact_ids = tuple(value.get("artifact_ids") or ())
        value["artifact_ids"] = list(artifact_ids)
        value["request_context"] = dict(value.get("request_context") or {})
        value["artifacts"] = [
            asdict(self.read_chart_artifact(chart_id)) for chart_id in artifact_ids
        ]
        return value
