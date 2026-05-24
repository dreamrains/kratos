import json

from data_agent.knowledge.candidates import MemoryCandidateExtractor
from data_agent.knowledge.evidence import EvidenceStore
from data_agent.knowledge.memory import MemoryStore


def _write_session(sessions_dir, session_id, content, project_name="ecommerce", role="user"):
    session_dir = sessions_dir / session_id
    session_dir.mkdir(parents=True)
    (session_dir / "meta.json").write_text(
        json.dumps({"project_name": project_name, "saved_at": "2026-05-24T10:00:00"}, ensure_ascii=False),
        encoding="utf-8",
    )
    (session_dir / "conversation.json").write_text(
        json.dumps([{"role": role, "content": content}], ensure_ascii=False),
        encoding="utf-8",
    )


def test_extractor_creates_metric_definition_candidate(tmp_path):
    sessions_dir = tmp_path / "sessions"
    _write_session(sessions_dir, "s1", "请记住：GMV 口径 = 支付金额 - 取消订单 - 退款订单。")
    root = tmp_path / "knowledge"
    EvidenceStore(root, sessions_dir=sessions_dir).index_session("s1")

    result = MemoryCandidateExtractor(root=root, sessions_dir=sessions_dir).extract_for_session("s1")

    assert result.created == 1
    item = MemoryStore(root).list()[0]
    assert item.status.value == "candidate"
    assert item.type.value == "domain_fact"
    assert item.reason
    assert item.source_evidence_ids
    assert item.dedup_key


def test_extractor_ignores_ordinary_conversation(tmp_path):
    sessions_dir = tmp_path / "sessions"
    _write_session(sessions_dir, "s2", "你好，帮我看一下这个文件。")
    root = tmp_path / "knowledge"
    EvidenceStore(root, sessions_dir=sessions_dir).index_session("s2")

    result = MemoryCandidateExtractor(root=root, sessions_dir=sessions_dir).extract_for_session("s2")

    assert result.created == 0
    assert MemoryStore(root).list() == []


def test_extractor_deduplicates_repeated_runs(tmp_path):
    sessions_dir = tmp_path / "sessions"
    _write_session(sessions_dir, "s3", "以后默认先做缺失值检查，再做趋势分析。")
    root = tmp_path / "knowledge"
    EvidenceStore(root, sessions_dir=sessions_dir).index_session("s3")
    extractor = MemoryCandidateExtractor(root=root, sessions_dir=sessions_dir)

    first = extractor.extract_for_session("s3")
    second = extractor.extract_for_session("s3")

    assert first.created == 1
    assert second.created == 0
    assert len(MemoryStore(root).list()) == 1


def test_extractor_ignores_non_user_metric_like_content(tmp_path):
    sessions_dir = tmp_path / "sessions"
    session_dir = sessions_dir / "s4"
    session_dir.mkdir(parents=True)
    (session_dir / "meta.json").write_text(
        json.dumps({"project_name": "ecommerce", "saved_at": "2026-05-24T10:00:00"}, ensure_ascii=False),
        encoding="utf-8",
    )
    (session_dir / "conversation.json").write_text(
        json.dumps(
            [
                {"role": "assistant", "content": '{"metric": "GMV", "value": "paid_amount = total"}'},
                {"role": "tool", "content": '{"formula": "metric = value"}'},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    root = tmp_path / "knowledge"
    EvidenceStore(root, sessions_dir=sessions_dir).index_session("s4")

    result = MemoryCandidateExtractor(root=root, sessions_dir=sessions_dir).extract_for_session("s4")

    assert result.created == 0
    assert MemoryStore(root).list() == []


def test_extractor_keeps_project_id_but_uses_general_domain_for_client_project(tmp_path):
    sessions_dir = tmp_path / "sessions"
    _write_session(sessions_dir, "s5", "请记住：GMV 口径 = 支付金额。", project_name="client-a-q2")
    root = tmp_path / "knowledge"
    EvidenceStore(root, sessions_dir=sessions_dir).index_session("s5")

    MemoryCandidateExtractor(root=root, sessions_dir=sessions_dir).extract_for_session("s5")

    item = MemoryStore(root).list()[0]
    assert item.project_id == "client-a-q2"
    assert item.domain == "general"


def test_extractor_classifies_corrections_as_reviewable_correction_memory(tmp_path):
    sessions_dir = tmp_path / "sessions"
    _write_session(sessions_dir, "s6", "纠正一下：GMV 应该排除退款订单。")
    root = tmp_path / "knowledge"
    EvidenceStore(root, sessions_dir=sessions_dir).index_session("s6")

    result = MemoryCandidateExtractor(root=root, sessions_dir=sessions_dir).extract_for_session("s6")

    assert result.created == 1
    item = MemoryStore(root).list()[0]
    assert item.type.value == "correction"
    assert item.needs_review is True
