from __future__ import annotations

import json
import math
import uuid
from datetime import datetime
from pathlib import Path

from data_agent.config import get_config
from data_agent.knowledge.models import MemoryItem, MemoryStatus, MemoryType
from data_agent.knowledge.sqlite_store import KnowledgeDatabase, row_to_dict, rows_to_dicts


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _memory_type(value: MemoryType | str) -> MemoryType:
    try:
        return value if isinstance(value, MemoryType) else MemoryType(value)
    except ValueError as exc:
        raise ValueError(f"Invalid memory_type: {value}") from exc


def _memory_status(value: MemoryStatus | str) -> MemoryStatus:
    try:
        return value if isinstance(value, MemoryStatus) else MemoryStatus(value)
    except ValueError as exc:
        raise ValueError(f"Invalid status: {value}") from exc


def _json_list(values: list[str] | tuple[str, ...] | None, field_name: str) -> str:
    if values is None:
        return "[]"
    if not isinstance(values, (list, tuple)) or isinstance(values, str):
        raise ValueError(f"Invalid {field_name}: expected list[str]")
    if not all(isinstance(value, str) for value in values):
        raise ValueError(f"Invalid {field_name}: expected list[str]")
    return json.dumps(list(values), ensure_ascii=False)


class MemoryStore:
    def __init__(self, root: Path | None = None):
        self.root = root or get_config().knowledge_dir
        self.db = KnowledgeDatabase(self.root / "knowledge.sqlite3")

    def create_candidate(
        self,
        text: str,
        summary: str = "",
        memory_type: MemoryType | str = MemoryType.WORKFLOW_PATTERN,
        confidence: float = 0.6,
        source_session_id: str = "",
        source_message_ids: list[str] | None = None,
        source_tool_call_ids: list[str] | None = None,
        project_id: str = "",
        domain: str = "general",
        tags: list[str] | None = None,
        promotion_target: str = "none",
        reason: str = "",
        source_evidence_ids: list[str] | None = None,
        needs_review: bool = False,
        review_note: str = "",
        dedup_key: str = "",
    ) -> MemoryItem:
        type_value = _memory_type(memory_type)
        confidence_value = float(confidence)
        if not math.isfinite(confidence_value) or confidence_value < 0 or confidence_value > 1:
            raise ValueError(f"Invalid confidence: {confidence}")
        dedup_key = dedup_key.strip()
        existing = self.get_by_dedup_key(dedup_key)
        if existing is not None:
            return existing

        item_id = f"mem_{uuid.uuid4().hex[:10]}"
        now = _now()
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO memory_items
                (id, type, text, summary, status, confidence, source_session_id,
                 source_message_ids, source_tool_call_ids, project_id, domain,
                 tags, last_used_at, hit_count, created_at, updated_at, promotion_target,
                 reason, source_evidence_ids, needs_review, review_note, dedup_key)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item_id,
                    type_value.value,
                    text,
                    summary,
                    MemoryStatus.CANDIDATE.value,
                    confidence_value,
                    source_session_id,
                    _json_list(source_message_ids, "source_message_ids"),
                    _json_list(source_tool_call_ids, "source_tool_call_ids"),
                    project_id,
                    domain.strip() or "general",
                    _json_list(tags, "tags"),
                    "",
                    0,
                    now,
                    now,
                    promotion_target,
                    reason,
                    _json_list(source_evidence_ids, "source_evidence_ids"),
                    1 if needs_review else 0,
                    review_note,
                    dedup_key,
                ),
            )
        item = self.get(item_id)
        if item is None:
            raise RuntimeError(f"Created memory item {item_id} could not be loaded")
        return item

    def get_by_dedup_key(self, dedup_key: str) -> MemoryItem | None:
        dedup_key = dedup_key.strip()
        if not dedup_key:
            return None
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM memory_items WHERE dedup_key = ? ORDER BY updated_at DESC LIMIT 1",
                (dedup_key,),
            ).fetchone()
        if row is None:
            return None
        return self._item_from_row(row_to_dict(row))

    def get(self, item_id: str) -> MemoryItem | None:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM memory_items WHERE id = ?",
                (item_id,),
            ).fetchone()
        if row is None:
            return None
        return self._item_from_row(row_to_dict(row))

    def list(
        self,
        status: MemoryStatus | str = "",
        domain: str = "",
        needs_review: bool | None = None,
    ) -> list[MemoryItem]:
        clauses = []
        params = []
        if status:
            clauses.append("status = ?")
            params.append(_memory_status(status).value)
        if domain:
            clauses.append("domain = ?")
            params.append(domain)
        if needs_review is not None:
            clauses.append("needs_review = ?")
            params.append(1 if needs_review else 0)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.db.connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM memory_items {where} ORDER BY updated_at DESC",
                params,
            ).fetchall()
        return [self._item_from_row(row) for row in rows_to_dicts(rows)]

    def confirm(self, item_id: str) -> MemoryItem | None:
        item = self.get(item_id)
        if item is None:
            return None
        if item.status != MemoryStatus.CANDIDATE:
            return item
        with self.db.connect() as conn:
            conn.execute(
                """
                UPDATE memory_items
                SET status = ?, confidence = ?, updated_at = ?
                WHERE id = ?
                """,
                (MemoryStatus.CONFIRMED.value, min(0.95, item.confidence + 0.15), _now(), item_id),
            )
        return self.get(item_id)

    def reject(self, item_id: str) -> MemoryItem | None:
        return self._set_status(item_id, MemoryStatus.REJECTED, allowed={MemoryStatus.CANDIDATE})

    def deprecate(self, item_id: str) -> MemoryItem | None:
        return self._set_status(item_id, MemoryStatus.DEPRECATED, allowed={MemoryStatus.CONFIRMED})

    def mark_promoted(self, item_id: str) -> MemoryItem | None:
        return self._set_status(item_id, MemoryStatus.PROMOTED, allowed={MemoryStatus.CONFIRMED})

    def update(
        self,
        item_id: str,
        text: str | None = None,
        summary: str | None = None,
        memory_type: MemoryType | str | None = None,
        confidence: float | None = None,
        domain: str | None = None,
        tags: list[str] | None = None,
        reason: str | None = None,
        source_evidence_ids: list[str] | None = None,
        needs_review: bool | None = None,
        review_note: str | None = None,
        dedup_key: str | None = None,
    ) -> MemoryItem | None:
        item = self.get(item_id)
        if item is None:
            return None
        if item.status in {MemoryStatus.PROMOTED, MemoryStatus.DEPRECATED}:
            raise ValueError("Promoted or deprecated memories cannot be edited")
        next_type = _memory_type(memory_type) if memory_type is not None else item.type
        next_confidence = item.confidence if confidence is None else float(confidence)
        if not math.isfinite(next_confidence) or next_confidence < 0 or next_confidence > 1:
            raise ValueError(f"Invalid confidence: {confidence}")
        with self.db.connect() as conn:
            conn.execute(
                """
                UPDATE memory_items
                SET text = ?, summary = ?, type = ?, confidence = ?, domain = ?, tags = ?,
                    reason = ?, source_evidence_ids = ?, needs_review = ?, review_note = ?,
                    dedup_key = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    text if text is not None else item.text,
                    summary if summary is not None else item.summary,
                    next_type.value,
                    next_confidence,
                    domain.strip() if domain is not None and domain.strip() else item.domain,
                    _json_list(tags if tags is not None else item.tags, "tags"),
                    reason if reason is not None else item.reason,
                    _json_list(
                        source_evidence_ids if source_evidence_ids is not None else item.source_evidence_ids,
                        "source_evidence_ids",
                    ),
                    1 if (needs_review if needs_review is not None else item.needs_review) else 0,
                    review_note if review_note is not None else item.review_note,
                    dedup_key.strip() if dedup_key is not None else item.dedup_key,
                    _now(),
                    item_id,
                ),
            )
        return self.get(item_id)

    def delete_candidate(self, item_id: str) -> bool:
        item = self.get(item_id)
        if item is None:
            return False
        if item.status not in {MemoryStatus.CANDIDATE, MemoryStatus.REJECTED}:
            raise ValueError("Only candidate or rejected memories can be deleted")
        with self.db.connect() as conn:
            conn.execute("DELETE FROM memory_items WHERE id = ?", (item_id,))
        return True

    def promote_to_knowledge(
        self,
        item_id: str,
        library,
        title: str = "",
        summary: str = "",
    ):
        from data_agent.knowledge.models import KnowledgeSource

        item = self.get(item_id)
        if item is None:
            return None
        if item.status != MemoryStatus.CONFIRMED:
            raise ValueError("Only confirmed memories can be promoted")
        knowledge = library.create(
            title=title or item.summary or item.text[:60],
            domain=item.domain or "general",
            content=item.text,
            summary=summary or item.summary,
            tags=item.tags,
            source=KnowledgeSource.MEMORY_PROMOTION,
        )
        with self.db.connect() as conn:
            conn.execute(
                """
                UPDATE memory_items
                SET status = ?, promotion_target = ?, updated_at = ?
                WHERE id = ?
                """,
                (MemoryStatus.PROMOTED.value, knowledge.id, _now(), item_id),
            )
        return knowledge

    def search(self, query: str, domain: str = "", limit: int = 5) -> list[MemoryItem]:
        if limit <= 0:
            return []
        terms = [term.lower() for term in query.split() if term.strip()]
        if not terms:
            return []
        candidates = self.list(status=MemoryStatus.CONFIRMED, domain=domain)
        scored: list[tuple[int, float, str, str, MemoryItem]] = []
        for item in candidates:
            haystack = " ".join([item.text, item.summary, " ".join(item.tags)]).lower()
            score = sum(haystack.count(term) for term in terms)
            if score > 0:
                scored.append((score, item.confidence, item.updated_at, item.id, item))
        scored.sort(key=lambda pair: (pair[0], pair[1], pair[2], pair[3]), reverse=True)
        return [item for _, _, _, _, item in scored[:limit]]

    def touch_used(self, item_id: str) -> MemoryItem | None:
        now = _now()
        with self.db.connect() as conn:
            conn.execute(
                """
                UPDATE memory_items
                SET last_used_at = ?, hit_count = hit_count + 1, updated_at = ?
                WHERE id = ?
                """,
                (now, now, item_id),
            )
        return self.get(item_id)

    def _set_status(
        self,
        item_id: str,
        status: MemoryStatus,
        allowed: set[MemoryStatus] | None = None,
    ) -> MemoryItem | None:
        item = self.get(item_id)
        if item is None:
            return None
        if allowed is not None and item.status not in allowed:
            return item
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE memory_items SET status = ?, updated_at = ? WHERE id = ?",
                (status.value, _now(), item_id),
            )
        return self.get(item_id)

    def _item_from_row(self, row: dict) -> MemoryItem:
        return MemoryItem(
            id=row["id"],
            type=MemoryType(row["type"]),
            text=row["text"],
            summary=row["summary"],
            status=MemoryStatus(row["status"]),
            confidence=float(row["confidence"]),
            source_session_id=row["source_session_id"],
            source_message_ids=json.loads(row["source_message_ids"] or "[]"),
            source_tool_call_ids=json.loads(row["source_tool_call_ids"] or "[]"),
            project_id=row["project_id"],
            domain=row["domain"],
            tags=json.loads(row["tags"] or "[]"),
            last_used_at=row["last_used_at"],
            hit_count=int(row["hit_count"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            promotion_target=row["promotion_target"],
            reason=row["reason"],
            source_evidence_ids=json.loads(row["source_evidence_ids"] or "[]"),
            needs_review=bool(row["needs_review"]),
            review_note=row["review_note"],
            dedup_key=row["dedup_key"],
        )
