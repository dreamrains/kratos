from data_agent.knowledge.sqlite_store import KnowledgeDatabase


def test_knowledge_database_sets_wal_and_busy_timeout(tmp_path):
    db = KnowledgeDatabase(tmp_path / "knowledge.sqlite3")

    with db.connect() as conn:
        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        busy_timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]

    assert journal_mode.lower() == "wal"
    assert busy_timeout >= 5000
