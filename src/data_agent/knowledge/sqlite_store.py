from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable


class KnowledgeDatabase:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)


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
    promotion_target TEXT NOT NULL
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

CREATE INDEX IF NOT EXISTS idx_knowledge_domain_status
    ON knowledge_items(domain, status);
CREATE INDEX IF NOT EXISTS idx_memory_status_domain
    ON memory_items(status, domain);
CREATE INDEX IF NOT EXISTS idx_evidence_session
    ON evidence_records(session_id);
"""
