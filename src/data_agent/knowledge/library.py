from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from pathlib import Path

from data_agent.config import get_config
from data_agent.utils.atomic_files import rollback_atomic_writes, write_bytes_atomic, unlink_with_rollback
from data_agent.knowledge.models import KnowledgeItem, KnowledgeSource, KnowledgeStatus
from data_agent.knowledge.sqlite_store import KnowledgeDatabase, row_to_dict, rows_to_dicts, search_limit


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _slug(text: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", text.strip()).strip("-").lower()
    return value or "knowledge"


def _safe_domain(domain: str) -> str:
    return _slug(domain.replace("..", " "))


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
        with rollback_atomic_writes():
            with self.db.connect() as conn:
                conn.execute("BEGIN")
                item = self._create_with_connection(conn, title, domain, content, summary, tags, source)
        return item

    def _create_with_connection(
        self,
        conn,
        title: str,
        domain: str,
        content: str,
        summary: str = "",
        tags: list[str] | None = None,
        source: KnowledgeSource = KnowledgeSource.USER,
    ) -> KnowledgeItem:
        # The caller owns the SQLite transaction and atomic file rollback.
        item_id = f"kn_{uuid.uuid4().hex[:10]}"
        domain_value = _safe_domain(domain) if domain.strip() else "general"
        path = self._resolve_library_path(Path("library") / domain_value / f"{_slug(title)}-{item_id}.md")
        path.parent.mkdir(parents=True, exist_ok=True)
        now = _now()
        relative_path = path.relative_to(self.root.resolve())

        write_bytes_atomic(path, content.encode("utf-8"))
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
                str(relative_path),
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
        item = self._get_with_connection(conn, item_id)
        if item is None:
            raise RuntimeError(f"Created knowledge item {item_id} could not be loaded")
        return item

    def _get_with_connection(self, conn, item_id: str) -> KnowledgeItem | None:
        row = conn.execute("SELECT * FROM knowledge_items WHERE id = ?", (item_id,)).fetchone()
        return self._item_from_row(row_to_dict(row)) if row is not None else None

    def get(self, item_id: str) -> KnowledgeItem | None:
        with self.db.connect() as conn:
            return self._get_with_connection(conn, item_id)

    def list(self, domain: str = "", status: str = "") -> list[KnowledgeItem]:
        clauses = []
        params = []
        if domain:
            clauses.append("domain = ?")
            params.append(_safe_domain(domain))
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
        with rollback_atomic_writes():
            with self.db.connect() as conn:
                conn.execute("BEGIN")
                item = self._get_with_connection(conn, item_id)
                if item is None:
                    return None
                if content is not None:
                    write_bytes_atomic(self._resolve_library_path(item.path), content.encode("utf-8"))
                next_title = title if title is not None else item.title
                next_summary = summary if summary is not None else item.summary
                next_tags = tags if tags is not None else item.tags
                conn.execute(
                    """
                    UPDATE knowledge_items
                    SET title = ?, summary = ?, tags = ?, version = version + 1, updated_at = ?
                    WHERE id = ?
                    """,
                    (next_title, next_summary, json.dumps(next_tags, ensure_ascii=False), _now(), item_id),
                )
                updated = self._get_with_connection(conn, item_id)
                if updated is None:
                    raise RuntimeError(f"Updated knowledge item {item_id} could not be loaded")
        return updated

    def _set_visibility(self, item_id: str, status: KnowledgeStatus, superseded_by: str = "") -> KnowledgeItem | None:
        with self.db.connect() as conn:
            conn.execute("BEGIN")
            now = _now()
            conn.execute(
                """
                UPDATE knowledge_items
                SET status = ?, deprecated_at = ?, updated_at = ?, superseded_by = ?
                WHERE id = ?
                """,
                (status.value, now if status == KnowledgeStatus.DEPRECATED else "", now, superseded_by, item_id),
            )
            item = self._get_with_connection(conn, item_id)
        return item

    def deprecate(self, item_id: str, superseded_by: str = "") -> KnowledgeItem | None:
        return self._set_visibility(item_id, KnowledgeStatus.DEPRECATED, superseded_by)

    def restore(self, item_id: str) -> KnowledgeItem | None:
        return self._set_visibility(item_id, KnowledgeStatus.ACTIVE)

    def delete(self, item_id: str) -> bool:
        with rollback_atomic_writes():
            with self.db.connect() as conn:
                conn.execute("BEGIN")
                item = self._get_with_connection(conn, item_id)
                if item is None:
                    return False
                unlink_with_rollback(self._resolve_library_path(item.path))
                conn.execute("DELETE FROM knowledge_items WHERE id = ?", (item_id,))
        return True

    def search(
        self,
        query: str,
        domain: str = "",
        include_deprecated: bool = False,
        limit: int = 5,
    ) -> list[KnowledgeItem]:
        limit = search_limit(limit)
        if not limit:
            return []
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
        path = self._resolve_library_path(row["path"])
        content = path.read_bytes().decode("utf-8")
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

    def _resolve_library_path(self, path: str | Path) -> Path:
        candidate = (self.root / path).resolve()
        root = self.root.resolve()
        library_dir = self.library_dir.resolve()
        if not candidate.is_relative_to(root) or not candidate.is_relative_to(library_dir):
            raise ValueError(f"Knowledge path escapes library directory: {path}")
        return candidate
