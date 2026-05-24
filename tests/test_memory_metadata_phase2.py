import sqlite3

import pytest

from data_agent.knowledge.memory import MemoryStore


def _create_old_schema_database(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE knowledge_items (
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

            CREATE TABLE memory_items (
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

            CREATE TABLE evidence_records (
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
        )


def test_existing_old_schema_database_migrates_before_metadata_indexes(tmp_path):
    root = tmp_path / "knowledge"
    db_path = root / "knowledge.sqlite3"
    _create_old_schema_database(db_path)

    store = MemoryStore(root)
    item = store.create_candidate(
        text="Review migrated memory.",
        needs_review=True,
        dedup_key="migration:test",
    )

    with sqlite3.connect(db_path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(memory_items)").fetchall()}
        indexes = {row[1] for row in conn.execute("PRAGMA index_list(memory_items)").fetchall()}

    assert {"reason", "source_evidence_ids", "needs_review", "review_note", "dedup_key"} <= columns
    assert {"idx_memory_dedup_key", "idx_memory_needs_review"} <= indexes
    assert store.list(needs_review=True)[0].id == item.id


def test_memory_candidate_persists_review_metadata(tmp_path):
    store = MemoryStore(tmp_path / "knowledge")

    item = store.create_candidate(
        text="GMV should exclude canceled orders.",
        summary="GMV rule",
        memory_type="domain_fact",
        domain="ecommerce",
        reason="User stated an explicit metric rule.",
        source_evidence_ids=["ev_s1_0"],
        needs_review=True,
        review_note="Possible conflict with older GMV rule.",
        dedup_key="domain_fact:ecommerce:gmv:exclude:canceled",
    )

    loaded = store.get(item.id)

    assert loaded.reason == "User stated an explicit metric rule."
    assert loaded.source_evidence_ids == ["ev_s1_0"]
    assert loaded.needs_review is True
    assert loaded.review_note == "Possible conflict with older GMV rule."
    assert loaded.dedup_key == "domain_fact:ecommerce:gmv:exclude:canceled"


def test_memory_list_filters_needs_review(tmp_path):
    store = MemoryStore(tmp_path / "knowledge")
    store.create_candidate("A", needs_review=True, dedup_key="a")
    store.create_candidate("B", needs_review=False, dedup_key="b")

    items = store.list(needs_review=True)

    assert [item.text for item in items] == ["A"]


def test_create_candidate_reuses_duplicate_dedup_key(tmp_path):
    store = MemoryStore(tmp_path / "knowledge")
    first = store.create_candidate("Use net revenue.", dedup_key="preference:revenue")
    second = store.create_candidate("Use net revenue.", dedup_key="preference:revenue")

    assert second.id == first.id
    assert len(store.list()) == 1


def test_database_rejects_duplicate_non_empty_dedup_key(tmp_path):
    root = tmp_path / "knowledge"
    store = MemoryStore(root)
    first = store.create_candidate("Use net revenue.", dedup_key="preference:revenue")

    with sqlite3.connect(root / "knowledge.sqlite3") as conn:
        indexes = {
            row[1]: row
            for row in conn.execute("PRAGMA index_list(memory_items)").fetchall()
        }
        unique_index = indexes["idx_memory_dedup_key_unique"]

        with pytest.raises(sqlite3.IntegrityError):
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
                    "mem_duplicate",
                    first.type.value,
                    "Use net revenue again.",
                    "",
                    first.status.value,
                    first.confidence,
                    "",
                    "[]",
                    "[]",
                    "",
                    "general",
                    "[]",
                    "",
                    0,
                    first.created_at,
                    first.updated_at,
                    "none",
                    "",
                    "[]",
                    0,
                    "",
                    first.dedup_key,
                ),
            )

        duplicate_count = conn.execute(
            "SELECT COUNT(*) FROM memory_items WHERE dedup_key = ?",
            (first.dedup_key,),
        ).fetchone()[0]

    assert unique_index[2] == 1
    assert duplicate_count == 1


def test_empty_dedup_keys_allow_multiple_records(tmp_path):
    store = MemoryStore(tmp_path / "knowledge")
    first = store.create_candidate("Use net revenue.")
    second = store.create_candidate("Use gross revenue.")

    assert first.id != second.id
    assert [item.dedup_key for item in store.list()] == ["", ""]


def test_update_rejects_duplicate_non_empty_dedup_key(tmp_path):
    store = MemoryStore(tmp_path / "knowledge")
    first = store.create_candidate("Use net revenue.", dedup_key="preference:revenue")
    second = store.create_candidate("Use gross revenue.", dedup_key="preference:gross-revenue")

    with pytest.raises(ValueError, match="dedup_key"):
        store.update(second.id, dedup_key=first.dedup_key)

    assert store.get(second.id).dedup_key == "preference:gross-revenue"
