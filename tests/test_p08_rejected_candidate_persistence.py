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




from tests.test_trusted_publication_semantics import engine,execute
from tests.test_trusted_publication_runtime import request


def test_second_rejected_candidate_is_persisted_for_audit(engine):
    from data_agent.agent.publication.runtime import publish,commit,read_answer
    from data_agent.session.history import load_session
    from data_agent.agent.publication.contracts import digest
    import json
    loop,cfg=engine
    request(loop,"计算当前记录数",{'kind': 'measurement', 'scope': {'datasets': ['orders'], 'quantity': 'rows'}})
    execute(loop,"describe_dataset",{"name":"orders"})
    first="第一稿候选：D30 外推 3.6%。"
    second="第二稿候选：D30 外推 5%。"
    assert publish(loop,first)[1]
    body,error=publish(loop,second)
    assert error is None and "D30 外推" not in body and "12" in body
    assert commit(loop,{"role":"assistant"},body) is None
    records=[json.loads(p.read_text(encoding="utf-8")) for p in (cfg.sessions_resolved/loop.session_id/"publication_rejected").glob("candidate_*.json")]
    assert {r["raw_draft"] for r in records}=={first,second}
    assert all(r["draft_digest"]==digest(r["raw_draft"]) and r["reasons"] for r in records)
    message=load_session(loop.session_id)["messages"][-1]
    answer=read_answer(loop.session_id,message["answer_ref"])
    assert answer["draft_digest"]==digest(second) and message["content"]==answer["body"]==body


def test_first_rejected_candidate_is_persisted_alongside_recovery(engine):
    from data_agent.agent.publication.runtime import publish,snapshot_for_turn
    from tests.test_trusted_publication_runtime import draft
    import json
    loop,cfg=engine
    request(loop,"计算当前记录数",{'kind': 'measurement', 'scope': {'datasets': ['orders'], 'quantity': 'rows'}})
    execute(loop,"describe_dataset",{"name":"orders"})
    candidate="第一稿候选全文。"
    assert publish(loop,candidate)[1]
    files=list((cfg.sessions_resolved/loop.session_id/"publication_rejected").glob("candidate_*.json"))
    assert len(files)==1 and json.loads(files[0].read_text(encoding="utf-8"))["raw_draft"]==candidate
    body,error=publish(loop,draft(snapshot_for_turn(loop)))
    assert error is None and "12" in body and candidate not in body


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
