"""P2-1：修订候选落盘 + 证据抽取跳过被拒内容。

RED 素材为 r2 批次 M02 真实轨迹（08c2ac223941）：
- 第二次被拒的修订候选全文只在失败通知的引文里，conversation/analyses
  均无——审计不可达；
- 被拒候选全文却作为 evidence 记录泄漏进 knowledge.sqlite3（且因散文
  含"不是"被误分类为 user_correction），可被检索注入未来上下文。
"""

from data_agent.agent.loop import AgentLoop
from data_agent.config import get_config
from data_agent.session.history import save_session


def _make_loop(tmp_path, monkeypatch, sid):
    cfg = get_config()
    monkeypatch.setattr(cfg, "sessions_dir", tmp_path / "sessions")
    monkeypatch.setattr(cfg, "skill_auto_discover", False)
    return AgentLoop(client=None, session_id=sid)


def _rejected_dir(tmp_path, sid):
    return tmp_path / "sessions" / sid / "publication_rejected"


def test_second_rejected_candidate_is_persisted_for_audit(tmp_path, monkeypatch):
    """恢复额度用尽后的拒绝同样必须落盘（此前第二次起全文丢失）。"""
    loop = _make_loop(tmp_path, monkeypatch, "rej_second")
    loop._turn_publication_recovery_used = True

    recovered = loop._recover_publication_narrative(
        {"role": "assistant", "content": "候选全文：D30 外推 3.6%。"},
        "[unbound_time_point_claim] 时间点数值主张未绑定到具体来源。",
    )

    assert recovered is False
    files = sorted(_rejected_dir(tmp_path, "rej_second").glob("candidate_*.md"))
    assert files, "被拒候选全文必须落盘供审计"
    body = files[0].read_text(encoding="utf-8")
    assert "候选全文：D30 外推 3.6%。" in body
    assert "[unbound_time_point_claim]" in body


def test_first_rejected_candidate_is_persisted_alongside_recovery(tmp_path, monkeypatch):
    loop = _make_loop(tmp_path, monkeypatch, "rej_first")

    recovered = loop._recover_publication_narrative(
        {"role": "assistant", "content": "第一稿候选全文。"},
        "[code] 校验错误",
    )

    assert recovered is True
    files = sorted(_rejected_dir(tmp_path, "rej_first").glob("candidate_*.md"))
    assert files
    assert "第一稿候选全文。" in files[0].read_text(encoding="utf-8")


def test_index_session_skips_rejected_messages(tmp_path, monkeypatch):
    """被拒发布候选不得进入证据库（此前以 user_correction 泄漏并可检索）。"""
    from data_agent.knowledge.evidence import EvidenceStore

    cfg = get_config()
    monkeypatch.setattr(cfg, "sessions_dir", tmp_path / "sessions")
    sid = "rej_evidence"
    rejected_text = "被拒候选：这不是结论，D30 外推 3.6% 应为情景值。"
    save_session([
        {"role": "user", "content": "请分析留存"},
        {"role": "assistant", "content": rejected_text, "publication_rejected": True},
        {"role": "assistant", "content": "合规终稿：D7 留存 10%。"},
    ], sid)

    store = EvidenceStore(
        root=tmp_path / "knowledge", sessions_dir=tmp_path / "sessions",
    )
    store.index_session(sid)

    with store.db.connect() as conn:
        rows = conn.execute(
            "SELECT id, kind FROM evidence_records WHERE session_id = ?", (sid,),
        ).fetchall()
    by_index = {row[0].split("_")[-1]: row[1] for row in rows}
    assert "1" not in by_index, "被拒候选不得进入证据库"
    assert by_index.get("0") == "message"
    assert by_index.get("2") == "message"
    hits = store.search("D30 外推")
    assert all(rejected_text[:20] not in (hit.content or "") for hit in hits)
