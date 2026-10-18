from __future__ import annotations

import sqlite3
import threading
from collections import OrderedDict
from contextlib import closing
from pathlib import Path
from typing import Iterable


class KnowledgeDatabase:
    # Process-local, bounded proof cache; connections and transactions are never cached.
    _initialization_lock = threading.RLock()
    _initialized = OrderedDict()
    _initialization_cache_limit = 256

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize(force=False)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _database_identity(self):
        try:
            path = self.path.resolve(strict=True)
            info = path.stat()
            birth = getattr(info, "st_birthtime_ns", None)
            if not info.st_ino or birth is None:
                return None
            return (str(path), info.st_dev, info.st_ino, birth)
        except OSError:
            return None

    @staticmethod
    def _schema_version(conn):
        try:
            version = conn.execute("PRAGMA schema_version").fetchone()[0]
            return version if isinstance(version, int) else None
        except sqlite3.Error:
            return None

    def _forget_initialization(self):
        path = str(self.path.resolve())
        for key in list(self._initialized):
            if key[1][0] == path:
                del self._initialized[key]

    def _initialize(self, *, force):
        with self._initialization_lock:
            try:
                before = self._database_identity()
                with closing(self.connect()) as conn:
                    identity = self._database_identity()
                    version = self._schema_version(conn)
                    key = (type(self), identity)
                    proven = (identity is not None and identity == before and version is not None
                              and self._initialized.get(key) == (version, SCHEMA))
                    if force or not proven:
                        with conn:
                            conn.executescript(SCHEMA)
                            self._migrate(conn)
                        version = self._schema_version(conn)
                    after = self._database_identity()
                    self._forget_initialization()
                    if identity is not None and identity == after and version is not None:
                        self._initialized[key] = (version, SCHEMA)
                        while len(self._initialized) > self._initialization_cache_limit:
                            self._initialized.popitem(last=False)
            except Exception:
                self._forget_initialization()
                raise

    def initialize(self) -> None:
        """Explicit initialization always checks and applies the existing migrations."""
        self._initialize(force=True)

    def _migrate(self, conn: sqlite3.Connection) -> None:
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(memory_items)").fetchall()}
        columns = {
            "reason": "TEXT NOT NULL DEFAULT ''",
            "source_evidence_ids": "TEXT NOT NULL DEFAULT '[]'",
            "needs_review": "INTEGER NOT NULL DEFAULT 0",
            "review_note": "TEXT NOT NULL DEFAULT ''",
            "dedup_key": "TEXT NOT NULL DEFAULT ''",
        }
        for name, ddl in columns.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE memory_items ADD COLUMN {name} {ddl}")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_domain_status ON knowledge_items(domain, status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_status_domain ON memory_items(status, domain)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_dedup_key ON memory_items(dedup_key)")
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_memory_dedup_key_unique "
            "ON memory_items(dedup_key) WHERE dedup_key <> ''"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_needs_review ON memory_items(needs_review)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_evidence_session ON evidence_records(session_id)")


def search_limit(value: int) -> int:
    """Normalize an integer count; nonpositive counts disable the search."""
    from numbers import Integral
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise ValueError("search limit must be an integer, not bool, float or string")
    return max(0, int(value))


def row_to_dict(row: sqlite3.Row) -> dict:
    return {key: row[key] for key in row.keys()}


def rows_to_dicts(rows: Iterable[sqlite3.Row]) -> list[dict]:
    return [row_to_dict(row) for row in rows]


SCHEMA = """
CREATE TABLE IF NOT EXISTS knowledge_items (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    domain TEXT NOT NULL,
    path TEXT NOT NULL,
    summary TEXT NOT NULL,
    status TEXT NOT NULL,
    tags TEXT NOT NULL,
    source TEXT NOT NULL,
    version INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deprecated_at TEXT NOT NULL,
    supersedes TEXT NOT NULL,
    superseded_by TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS memory_items (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    text TEXT NOT NULL,
    summary TEXT NOT NULL,
    status TEXT NOT NULL,
    confidence REAL NOT NULL,
    source_session_id TEXT NOT NULL,
    source_message_ids TEXT NOT NULL,
    source_tool_call_ids TEXT NOT NULL,
    project_id TEXT NOT NULL,
    domain TEXT NOT NULL,
    tags TEXT NOT NULL,
    last_used_at TEXT NOT NULL,
    hit_count INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    promotion_target TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    source_evidence_ids TEXT NOT NULL DEFAULT '[]',
    needs_review INTEGER NOT NULL DEFAULT 0,
    review_note TEXT NOT NULL DEFAULT '',
    dedup_key TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS evidence_records (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    content_ref TEXT NOT NULL,
    summary TEXT NOT NULL,
    embedding_ref TEXT NOT NULL,
    created_at TEXT NOT NULL,
    tags TEXT NOT NULL
);

"""
