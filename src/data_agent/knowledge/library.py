from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from pathlib import Path

from data_agent.config import get_config
from data_agent.knowledge.models import KnowledgeItem, KnowledgeSource, KnowledgeStatus
from data_agent.knowledge.sqlite_store import KnowledgeDatabase, row_to_dict, rows_to_dicts


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _slug(text: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", text.strip()).strip("-").lower()
    return value or "knowledge"


class KnowledgeLibrary:
    def __init__(self, root: Path | None = None):
        self.root = root or get_config().knowledge_dir
        self.library_dir = self.root / "library"
        self.db = KnowledgeDatabase(self.root / "knowledge.sqlite3")

    def create(
        self,
        title: str,
        domain: str,
        content: str,
        summary: str = "",
        tags: list[str] | None = None,
        source: KnowledgeSource = KnowledgeSource.USER,
    ) -> KnowledgeItem:
        item_id = f"kn_{uuid.uuid4().hex[:10]}"
        domain_value = domain.strip() or "general"
        path = self.library_dir / domain_value / f"{_slug(title)}-{item_id}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        now = _now()

        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO knowledge_items
                (id, title, domain, path, summary, status, tags, source, version,
                 created_at, updated_at, deprecated_at, supersedes, superseded_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item_id,
                    title,
                    domain_value,
                    str(path.relative_to(self.root)),
                    summary,
                    KnowledgeStatus.ACTIVE.value,
                    json.dumps(tags or [], ensure_ascii=False),
                    source.value,
                    1,
                    now,
                    now,
                    "",
                    "",
                    "",
                ),
            )
        item = self.get(item_id)
        if item is None:
            raise RuntimeError(f"Created knowledge item {item_id} could not be loaded")
        return item

    def get(self, item_id: str) -> KnowledgeItem | None:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM knowledge_items WHERE id = ?",
                (item_id,),
            ).fetchone()
        if row is None:
            return None
        return self._item_from_row(row_to_dict(row))

    def list(self, domain: str = "", status: str = "") -> list[KnowledgeItem]:
        clauses = []
        params = []
        if domain:
            clauses.append("domain = ?")
            params.append(domain)
        if status:
            clauses.append("status = ?")
            params.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.db.connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM knowledge_items {where} ORDER BY updated_at DESC",
                params,
            ).fetchall()
        return [self._item_from_row(row) for row in rows_to_dicts(rows)]

    def update(
        self,
        item_id: str,
        content: str | None = None,
        title: str | None = None,
        summary: str | None = None,
        tags: list[str] | None = None,
    ) -> KnowledgeItem | None:
        item = self.get(item_id)
        if item is None:
            return None
        if content is not None:
            (self.root / item.path).write_text(content, encoding="utf-8")
        next_title = title if title is not None else item.title
        next_summary = summary if summary is not None else item.summary
        next_tags = tags if tags is not None else item.tags
        with self.db.connect() as conn:
            conn.execute(
                """
                UPDATE knowledge_items
                SET title = ?, summary = ?, tags = ?, version = version + 1, updated_at = ?
                WHERE id = ?
                """,
                (
                    next_title,
                    next_summary,
                    json.dumps(next_tags, ensure_ascii=False),
                    _now(),
                    item_id,
                ),
            )
        return self.get(item_id)

    def deprecate(self, item_id: str, superseded_by: str = "") -> KnowledgeItem | None:
        with self.db.connect() as conn:
            conn.execute(
                """
                UPDATE knowledge_items
                SET status = ?, deprecated_at = ?, updated_at = ?, superseded_by = ?
                WHERE id = ?
                """,
                (KnowledgeStatus.DEPRECATED.value, _now(), _now(), superseded_by, item_id),
            )
        return self.get(item_id)

    def restore(self, item_id: str) -> KnowledgeItem | None:
        with self.db.connect() as conn:
            conn.execute(
                """
                UPDATE knowledge_items
                SET status = ?, deprecated_at = '', updated_at = ?
                WHERE id = ?
                """,
                (KnowledgeStatus.ACTIVE.value, _now(), item_id),
            )
        return self.get(item_id)

    def delete(self, item_id: str) -> bool:
        item = self.get(item_id)
        if item is None:
            return False
        (self.root / item.path).unlink(missing_ok=True)
        with self.db.connect() as conn:
            conn.execute("DELETE FROM knowledge_items WHERE id = ?", (item_id,))
        return True

    def search(
        self,
        query: str,
        domain: str = "",
        include_deprecated: bool = False,
        limit: int = 5,
    ) -> list[KnowledgeItem]:
        terms = [term.lower() for term in query.split() if term.strip()]
        candidates = self.list(domain=domain)
        scored: list[tuple[int, KnowledgeItem]] = []
        for item in candidates:
            if item.status == KnowledgeStatus.DEPRECATED and not include_deprecated:
                continue
            haystack = " ".join([item.title, item.summary, item.content, " ".join(item.tags)]).lower()
            score = sum(haystack.count(term) for term in terms)
            if score > 0:
                scored.append((score, item))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [item for _, item in scored[:limit]]

    def _item_from_row(self, row: dict) -> KnowledgeItem:
        path = self.root / row["path"]
        content = path.read_text(encoding="utf-8") if path.exists() else ""
        return KnowledgeItem(
            id=row["id"],
            title=row["title"],
            domain=row["domain"],
            path=row["path"],
            summary=row["summary"],
            status=KnowledgeStatus(row["status"]),
            tags=json.loads(row["tags"] or "[]"),
            source=KnowledgeSource(row["source"]),
            version=int(row["version"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            deprecated_at=row["deprecated_at"],
            supersedes=row["supersedes"],
            superseded_by=row["superseded_by"],
            content=content,
        )
