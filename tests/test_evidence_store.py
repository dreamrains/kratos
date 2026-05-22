import json
from pathlib import Path

from data_agent.knowledge.evidence import EvidenceStore
from data_agent.knowledge.models import EvidenceKind


def _write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def test_index_session_messages_and_search(tmp_path: Path):
    sessions_dir = tmp_path / "sessions"
    session_dir = sessions_dir / "s1"
    session_dir.mkdir(parents=True)
    _write_json(
        session_dir / "meta.json",
        {"session_id": "s1", "project_name": "sales", "saved_at": "2026-05-23 10:00:00"},
    )
    _write_json(
        session_dir / "conversation.json",
        [
            {"role": "user", "content": "Please analyze net revenue by channel."},
            {"role": "assistant", "content": "I will compare channels using net revenue."},
        ],
    )

    store = EvidenceStore(tmp_path / "knowledge", sessions_dir=sessions_dir)
    indexed = store.index_session("s1")

    assert indexed == 2
    results = store.search("net revenue", project_id="sales")
    assert len(results) == 2
    assert results[0].kind == EvidenceKind.MESSAGE
    assert "net revenue" in results[0].content.lower()


def test_index_session_reads_jsonl_and_ignores_other_sessions(tmp_path: Path):
    sessions_dir = tmp_path / "sessions"
    session_dir = sessions_dir / "s1"
    other_dir = sessions_dir / "s2"
    session_dir.mkdir(parents=True)
    other_dir.mkdir(parents=True)
    _write_json(session_dir / "meta.json", {"project_name": "sales"})
    _write_json(other_dir / "meta.json", {"project_name": "ops"})
    (session_dir / "conversation.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"role": "user", "content": "conversion funnel dipped"}, ensure_ascii=False),
                "not-json",
                json.dumps({"role": "assistant", "content": {"metric": "conversion"}}, ensure_ascii=False),
            ]
        ),
        encoding="utf-8",
    )
    (other_dir / "conversation.json").write_text(
        json.dumps([{"role": "user", "content": "conversion should not be indexed"}]),
        encoding="utf-8",
    )

    store = EvidenceStore(tmp_path / "knowledge", sessions_dir=sessions_dir)

    assert store.index_session("s1") == 2
    assert store.search("conversion", project_id="ops") == []
    assert len(store.search("conversion", project_id="sales")) == 2


def test_content_ref_cannot_escape_sessions_dir(tmp_path: Path):
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "conversation.json").write_text(
        json.dumps([{"role": "user", "content": "secret outside content"}]),
        encoding="utf-8",
    )

    store = EvidenceStore(tmp_path / "knowledge", sessions_dir=sessions_dir)
    with store.db.connect() as conn:
        conn.execute(
            """
            INSERT INTO evidence_records
            (id, session_id, project_id, kind, content_ref, summary, embedding_ref, created_at, tags)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ev_escape",
                "..",
                "",
                EvidenceKind.MESSAGE.value,
                "../outside:message:0",
                "malicious",
                "",
                "2026-05-23T10:00:00",
                "[]",
            ),
        )

    record = store.get("ev_escape")

    assert record is not None
    assert record.content == ""


def test_search_limit_and_missing_or_invalid_refs(tmp_path: Path):
    sessions_dir = tmp_path / "sessions"
    session_dir = sessions_dir / "s1"
    session_dir.mkdir(parents=True)
    _write_json(
        session_dir / "conversation.json",
        [
            {"role": "user", "content": "alpha alpha beta"},
            {"role": "assistant", "content": "alpha beta"},
        ],
    )
    store = EvidenceStore(tmp_path / "knowledge", sessions_dir=sessions_dir)
    store.index_session("s1")

    assert store.search("alpha", limit=0) == []
    assert [item.content for item in store.search("alpha", limit=1)] == ["alpha alpha beta"]
    assert store._content_for_ref("s1:message:not-int") == ""
    assert store._content_for_ref("s1:message:99") == ""


def test_reindex_session_removes_stale_evidence(tmp_path: Path):
    sessions_dir = tmp_path / "sessions"
    session_dir = sessions_dir / "s1"
    session_dir.mkdir(parents=True)
    _write_json(session_dir / "meta.json", {"project_name": "sales"})
    _write_json(
        session_dir / "conversation.json",
        [
            {"role": "user", "content": "fresh metric"},
            {"role": "assistant", "content": "stale metric"},
        ],
    )
    store = EvidenceStore(tmp_path / "knowledge", sessions_dir=sessions_dir)

    assert store.index_session("s1") == 2
    _write_json(
        session_dir / "conversation.json",
        [
            {"role": "user", "content": "fresh metric"},
            {"role": "assistant", "content": ""},
        ],
    )

    assert store.index_session("s1") == 1
    assert [item.content for item in store.search("fresh", project_id="sales")] == ["fresh metric"]
    assert store.search("stale", project_id="sales") == []
    assert store.get("ev_s1_1") is None


def test_content_ref_must_match_row_session_id(tmp_path: Path):
    sessions_dir = tmp_path / "sessions"
    s1_dir = sessions_dir / "s1"
    s2_dir = sessions_dir / "s2"
    s1_dir.mkdir(parents=True)
    s2_dir.mkdir(parents=True)
    _write_json(s1_dir / "conversation.json", [{"role": "user", "content": "session one content"}])
    _write_json(s2_dir / "conversation.json", [{"role": "user", "content": "session two secret"}])

    store = EvidenceStore(tmp_path / "knowledge", sessions_dir=sessions_dir)
    with store.db.connect() as conn:
        conn.execute(
            """
            INSERT INTO evidence_records
            (id, session_id, project_id, kind, content_ref, summary, embedding_ref, created_at, tags)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ev_mismatch",
                "s1",
                "",
                EvidenceKind.MESSAGE.value,
                "s2:message:0",
                "mismatch",
                "",
                "2026-05-23T10:00:00",
                "[]",
            ),
        )

    record = store.get("ev_mismatch")

    assert record is not None
    assert record.content == ""
