import json

import data_agent.config as config_module
from data_agent.config import AgentConfig
from data_agent.knowledge.evidence import EvidenceStore
from data_agent.knowledge.memory import MemoryStore
from data_agent.session.history import save_session


def _test_config(tmp_path):
    return AgentConfig(WORKSPACE_DIR=tmp_path / "workspace", SESSIONS_DIR=tmp_path / "sessions")


def test_save_session_auto_extracts_high_signal_candidate(tmp_path, monkeypatch):
    cfg = _test_config(tmp_path)
    monkeypatch.setattr(config_module, "_config", cfg)

    save_session(
        [{"role": "user", "content": "请记住：GMV 需要排除取消订单和退款订单。"}],
        "auto_candidate",
        extra_meta={"project_name": "ecommerce"},
    )

    candidates = MemoryStore(cfg.knowledge_dir).list(status="candidate")

    assert len(candidates) == 1
    assert candidates[0].source_evidence_ids
    assert candidates[0].source_session_id == "auto_candidate"
    assert candidates[0].project_id == "ecommerce"


def test_save_session_does_not_extract_ordinary_user_content(tmp_path, monkeypatch):
    cfg = _test_config(tmp_path)
    monkeypatch.setattr(config_module, "_config", cfg)

    save_session([{"role": "user", "content": "帮我分析这个 CSV 文件。"}], "ordinary")

    assert MemoryStore(cfg.knowledge_dir).list(status="candidate") == []


def test_index_session_auto_extracts_manual_session_without_session_id_meta(tmp_path):
    sessions_dir = tmp_path / "sessions"
    session_dir = sessions_dir / "manual"
    session_dir.mkdir(parents=True)
    (session_dir / "meta.json").write_text(
        json.dumps({"project_name": "ecommerce", "saved_at": "2026-05-24T10:00:00"}, ensure_ascii=False),
        encoding="utf-8",
    )
    (session_dir / "conversation.json").write_text(
        json.dumps([{"role": "user", "content": "请记住：GMV 需要排除取消订单。"}], ensure_ascii=False),
        encoding="utf-8",
    )
    root = tmp_path / "knowledge"

    indexed = EvidenceStore(root, sessions_dir=sessions_dir).index_session("manual")

    candidates = MemoryStore(root).list(status="candidate")
    assert indexed == 1
    assert len(candidates) == 1
    assert candidates[0].source_session_id == "manual"
    assert candidates[0].source_evidence_ids == ["ev_manual_0"]


def test_reindex_refreshes_existing_candidate_source_evidence_ids(tmp_path, monkeypatch):
    cfg = _test_config(tmp_path)
    monkeypatch.setattr(config_module, "_config", cfg)
    memory_text = "请记住：GMV 需要排除取消订单。"

    save_session(
        [{"role": "user", "content": memory_text}],
        "shifted_candidate",
        extra_meta={"project_name": "ecommerce"},
    )
    store = MemoryStore(cfg.knowledge_dir)
    first = store.list(status="candidate")[0]
    assert first.source_evidence_ids == ["ev_shifted_candidate_0"]

    save_session(
        [
            {"role": "assistant", "content": "已准备好分析。"},
            {"role": "user", "content": memory_text},
        ],
        "shifted_candidate",
        extra_meta={"project_name": "ecommerce"},
    )

    candidates = store.list(status="candidate")
    refreshed = store.get(first.id)
    current_evidence = EvidenceStore(cfg.knowledge_dir, sessions_dir=cfg.sessions_resolved).get("ev_shifted_candidate_1")
    assert len(candidates) == 1
    assert refreshed.source_evidence_ids == ["ev_shifted_candidate_1"]
    assert current_evidence is not None
    assert current_evidence.content == memory_text


def test_candidate_extraction_failure_does_not_break_index_session(tmp_path, monkeypatch):
    from data_agent.knowledge.candidates import MemoryCandidateExtractor

    cfg = _test_config(tmp_path)
    monkeypatch.setattr(config_module, "_config", cfg)
    save_session(
        [{"role": "user", "content": "请记住：GMV 需要排除取消订单和退款订单。"}],
        "extract_failure_index",
        extra_meta={"project_name": "ecommerce"},
    )

    def raise_extraction_error(self, session_id):
        raise RuntimeError("boom")

    monkeypatch.setattr(MemoryCandidateExtractor, "extract_for_session", raise_extraction_error)

    indexed = EvidenceStore(cfg.knowledge_dir, sessions_dir=cfg.sessions_resolved).index_session("extract_failure_index")

    assert indexed == 1


def test_candidate_extraction_failure_does_not_break_save_session(tmp_path, monkeypatch):
    from data_agent.knowledge.candidates import MemoryCandidateExtractor

    cfg = _test_config(tmp_path)
    monkeypatch.setattr(config_module, "_config", cfg)
    calls = []

    def raise_extraction_error(self, session_id):
        calls.append(session_id)
        raise RuntimeError("boom")

    monkeypatch.setattr(MemoryCandidateExtractor, "extract_for_session", raise_extraction_error)

    session_id = save_session(
        [{"role": "user", "content": "请记住：GMV 需要排除取消订单和退款订单。"}],
        "extract_failure_save",
        extra_meta={"project_name": "ecommerce"},
    )

    records = EvidenceStore(cfg.knowledge_dir, sessions_dir=cfg.sessions_resolved).search(
        "GMV",
        project_id="ecommerce",
    )
    assert session_id == "extract_failure_save"
    assert calls == ["extract_failure_save"]
    assert [record.session_id for record in records] == ["extract_failure_save"]
