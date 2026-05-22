from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from data_agent.config import get_config
from data_agent.knowledge.models import EvidenceKind, EvidenceRecord
from data_agent.knowledge.sqlite_store import KnowledgeDatabase, row_to_dict, rows_to_dicts


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class EvidenceStore:
    def __init__(self, root: Path | None = None, sessions_dir: Path | None = None):
        self.root = root or get_config().knowledge_dir
        self.sessions_dir = sessions_dir or get_config().sessions_resolved
        self.db = KnowledgeDatabase(self.root / "knowledge.sqlite3")

    def index_session(self, session_id: str) -> int:
        session_dir = self._session_dir_for(session_id)
        if session_dir is None:
            return 0
        meta = self._read_json(session_dir / "meta.json", default={})
        if not isinstance(meta, dict):
            meta = {}
        messages = self._read_messages(session_dir)
        project_id = str(meta.get("project_name") or meta.get("project_id") or "")
        created_at = str(meta.get("saved_at") or _now())
        inserted = 0
        with self.db.connect() as conn:
            for idx, message in enumerate(messages):
                content = self._message_content(message)
                if not content:
                    continue
                evidence_id = f"ev_{session_id}_{idx}"
                conn.execute(
                    """
                    INSERT OR REPLACE INTO evidence_records
                    (id, session_id, project_id, kind, content_ref, summary,
                     embedding_ref, created_at, tags)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        evidence_id,
                        session_id,
                        project_id,
                        EvidenceKind.MESSAGE.value,
                        f"{session_id}:message:{idx}",
                        content[:300],
                        "",
                        created_at,
                        json.dumps([str(message.get("role", ""))], ensure_ascii=False),
                    ),
                )
                inserted += 1
        return inserted

    def search(self, query: str, project_id: str = "", limit: int = 10) -> list[EvidenceRecord]:
        if limit <= 0:
            return []
        terms = [term.lower() for term in query.split() if term.strip()]
        if not terms:
            return []
        clauses = []
        params = []
        if project_id:
            clauses.append("project_id = ?")
            params.append(project_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.db.connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM evidence_records {where} ORDER BY created_at DESC, id ASC",
                params,
            ).fetchall()
        scored: list[tuple[int, str, EvidenceRecord]] = []
        for row in rows_to_dicts(rows):
            record = self._record_from_row(row)
            haystack = f"{record.summary}\n{record.content}".lower()
            score = sum(haystack.count(term) for term in terms)
            if score > 0:
                scored.append((score, record.created_at, record))
        scored.sort(key=lambda item: (item[0], item[1], item[2].id), reverse=True)
        return [record for _, _, record in scored[:limit]]

    def get(self, evidence_id: str) -> EvidenceRecord | None:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM evidence_records WHERE id = ?",
                (evidence_id,),
            ).fetchone()
        if row is None:
            return None
        return self._record_from_row(row_to_dict(row))

    def _record_from_row(self, row: dict[str, Any]) -> EvidenceRecord:
        return EvidenceRecord(
            id=row["id"],
            session_id=row["session_id"],
            project_id=row["project_id"],
            kind=EvidenceKind(row["kind"]),
            content_ref=row["content_ref"],
            summary=row["summary"],
            embedding_ref=row["embedding_ref"],
            created_at=row["created_at"],
            tags=self._json_list(row["tags"]),
            content=self._content_for_ref(row["content_ref"]),
        )

    def _content_for_ref(self, content_ref: str) -> str:
        prefix = ":message:"
        if prefix not in content_ref:
            return ""
        session_id, index_text = content_ref.split(prefix, 1)
        if not index_text.isdigit():
            return ""
        session_dir = self._session_dir_for(session_id)
        if session_dir is None:
            return ""
        messages = self._read_messages(session_dir)
        index = int(index_text)
        if index >= len(messages):
            return ""
        return self._message_content(messages[index])

    def _session_dir_for(self, session_id: str) -> Path | None:
        session_path = Path(session_id)
        if not session_id or session_path.is_absolute() or len(session_path.parts) != 1:
            return None
        if session_path.parts[0] in {".", ".."}:
            return None
        base = self.sessions_dir.resolve()
        candidate = (base / session_path).resolve()
        try:
            candidate.relative_to(base)
        except ValueError:
            return None
        return candidate

    def _read_messages(self, session_dir: Path) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        conversation_path = session_dir / "conversation.json"
        if conversation_path.exists():
            loaded = self._read_json(conversation_path, default=[])
            if isinstance(loaded, list):
                messages.extend(item for item in loaded if isinstance(item, dict))

        jsonl_path = session_dir / "conversation.jsonl"
        if jsonl_path.exists():
            try:
                lines = jsonl_path.read_text(encoding="utf-8").splitlines()
            except OSError:
                lines = []
            for line in lines:
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(item, dict):
                    messages.append(item)
        return messages

    def _read_json(self, path: Path, default):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return default

    def _message_content(self, message: dict[str, Any]) -> str:
        content = message.get("content", "")
        if isinstance(content, str):
            return content
        return json.dumps(content, ensure_ascii=False)

    def _json_list(self, value: str) -> list[str]:
        try:
            decoded = json.loads(value or "[]")
        except json.JSONDecodeError:
            return []
        if not isinstance(decoded, list):
            return []
        return [item for item in decoded if isinstance(item, str)]
