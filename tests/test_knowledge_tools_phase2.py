from pathlib import Path

import data_agent.config as config_module
from data_agent.config import AgentConfig
from data_agent.knowledge.memory import MemoryStore
from data_agent.tools import knowledge_tools
from data_agent.tools.registry import registry


def _configure(tmp_path: Path, monkeypatch):
    cfg = AgentConfig(WORKSPACE_DIR=tmp_path / "workspace", SESSIONS_DIR=tmp_path / "sessions")
    monkeypatch.setattr(config_module, "_config", cfg)
    knowledge_tools.reset_knowledge_services_for_tests()
    knowledge_tools.set_active_session(None)
    return cfg


def test_memory_candidate_tools_are_registered():
    names = set(registry.tool_names)

    assert "extract_memory_candidates" in names
    assert "list_memory_candidates" in names


def test_list_memory_candidates_returns_only_candidates_with_review_metadata(tmp_path, monkeypatch):
    cfg = _configure(tmp_path, monkeypatch)
    store = MemoryStore(cfg.knowledge_dir)
    candidate = store.create_candidate(
        text="candidate memory",
        reason="User stated a reusable rule.",
        source_evidence_ids=["ev_s1_0"],
        needs_review=True,
        review_note="Review before use.",
        dedup_key="workflow:general:candidate",
    )
    confirmed = store.create_candidate(
        text="confirmed memory",
        dedup_key="workflow:general:confirmed",
    )
    store.confirm(confirmed.id)

    result = knowledge_tools.list_memory_candidates()

    assert [item["id"] for item in result] == [candidate.id]
    assert result[0]["status"] == "candidate"
    assert result[0]["reason"] == "User stated a reusable rule."
    assert result[0]["source_evidence_ids"] == ["ev_s1_0"]
    assert result[0]["needs_review"] is True
    assert result[0]["review_note"] == "Review before use."
    assert result[0]["dedup_key"] == "workflow:general:candidate"


def test_list_memory_candidates_can_filter_review_needed(tmp_path, monkeypatch):
    cfg = _configure(tmp_path, monkeypatch)
    store = MemoryStore(cfg.knowledge_dir)
    review = store.create_candidate(
        text="review memory",
        needs_review=True,
        dedup_key="workflow:general:review",
    )
    store.create_candidate(
        text="no review memory",
        needs_review=False,
        dedup_key="workflow:general:no-review",
    )

    result = knowledge_tools.list_memory_candidates(needs_review=True)

    assert [item["id"] for item in result] == [review.id]
    assert result[0]["needs_review"] is True


def test_extract_memory_candidates_returns_summary_payload(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    session_dir = tmp_path / "sessions" / "s1"
    session_dir.mkdir(parents=True)
    (session_dir / "meta.json").write_text('{"project_name": "ecommerce"}', encoding="utf-8")
    (session_dir / "conversation.json").write_text(
        '[{"role": "user", "content": "Remember GMV definition equals paid orders."}]',
        encoding="utf-8",
    )

    from data_agent.knowledge.evidence import EvidenceStore

    monkeypatch.setattr(EvidenceStore, "_try_extract_memory_candidates", lambda self, session_id: None)
    EvidenceStore().index_session("s1")
    knowledge_tools.reset_knowledge_services_for_tests()

    result = knowledge_tools.extract_memory_candidates("s1")

    assert result["scanned"] == 1
    assert result["created"] == 1
    assert result["skipped"] == 0
    assert result["candidates"]


def test_extract_memory_candidates_requires_session_id(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)

    result = knowledge_tools.extract_memory_candidates()

    assert result == {"error": "session_id is required"}
