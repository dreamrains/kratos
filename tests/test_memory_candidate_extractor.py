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


def test_extractor_creates_metric_definition_candidate(tmp_path, monkeypatch):
    sessions_dir = tmp_path / "sessions"
    _write_session(sessions_dir, "s1", "请记住：GMV 口径 = 支付金额 - 取消订单 - 退款订单。")
    root = tmp_path / "knowledge"
    monkeypatch.setattr(EvidenceStore, "_try_extract_memory_candidates", lambda self, session_id: None)
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


def test_extractor_is_idempotent_after_auto_extraction(tmp_path):
    sessions_dir = tmp_path / "sessions"
    _write_session(sessions_dir, "s3", "以后默认先做缺失值检查，再做趋势分析。")
    root = tmp_path / "knowledge"
    EvidenceStore(root, sessions_dir=sessions_dir).index_session("s3")
    extractor = MemoryCandidateExtractor(root=root, sessions_dir=sessions_dir)

    first = extractor.extract_for_session("s3")
    second = extractor.extract_for_session("s3")

    assert first.created == 0
    assert first.skipped == 1
    assert second.created == 0
    assert second.skipped == 1
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

    assert result.created == 0
    assert result.skipped == 1
    item = MemoryStore(root).list()[0]
    assert item.type.value == "correction"
    assert item.needs_review is True


# Atomic extraction uses real storage, public registry and existing management API.
import json,sqlite3,io,shutil
from pathlib import Path
import pytest
from tests.test_trusted_publication_semantics import engine
from data_agent.knowledge.candidates import MemoryCandidateExtractor
from data_agent.knowledge.evidence import EvidenceStore
from data_agent.knowledge.memory import MemoryStore
_EXTRACTION_OUT=Path('tmp/s3-memory-extraction-20261012-r1')
_EXTRACTION_TEXTS=['请记住：EXTRACT_FIRST 使用原值。','请记住：EXTRACT_SECOND 保留未知。']
def _extraction_rows(root):
    with sqlite3.connect(root/'knowledge.sqlite3') as conn:
        conn.row_factory=sqlite3.Row
        return [dict(r) for r in conn.execute('SELECT * FROM memory_items ORDER BY id')]
def _extraction_setup(cfg,monkeypatch,mode):
    from data_agent.tools import knowledge_tools
    sid='extraction_source';store=MemoryStore(cfg.knowledge_dir)
    monkeypatch.setattr(knowledge_tools,'_memory_store',store)
    p=cfg.sessions_resolved/sid;p.mkdir(parents=True,exist_ok=True)
    (p/'meta.json').write_text(json.dumps({'project_name':'ecommerce'}),encoding='utf-8')
    def seed(messages):
        (p/'conversation.json').write_text(json.dumps(messages,ensure_ascii=False),encoding='utf-8')
        with monkeypatch.context() as m:
            m.setattr(EvidenceStore,'_try_extract_memory_candidates',lambda *a:None)
            EvidenceStore(cfg.knowledge_dir,cfg.sessions_resolved).index_session(sid)
    if mode=='refresh':
        seed([{'role':'user','content':_EXTRACTION_TEXTS[0]}]);MemoryCandidateExtractor().extract_for_session(sid)
    seed([{'role':'assistant','content':'已有上下文'},*[{'role':'user','content':t} for t in _EXTRACTION_TEXTS]])
    before=_extraction_rows(store.root)
    if mode!='success':
        with store.db.connect() as conn:
            conn.execute("CREATE TRIGGER fail_second BEFORE INSERT ON memory_items WHEN NEW.text LIKE '%EXTRACT_SECOND%' BEGIN SELECT RAISE(ABORT,'extraction_second_failure'); END")
    return sid,store,before
def _extraction_capture(name,value):
    p=_EXTRACTION_OUT/'focused-evidence'/Path(value['storage_root']).parents[2].name/name
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2)
    return p
@pytest.mark.parametrize('route',['store','registry','http'])
@pytest.mark.parametrize('mode',['create','refresh'])
def test_extraction_caught_failure_rolls_back_whole_batch(engine,monkeypatch,route,mode):
    from data_agent.tools.registry import registry
    from data_agent.web.app import create_app
    _,cfg=engine;sid,store,before=_extraction_setup(cfg,monkeypatch,mode)
    if route=='store':
        with pytest.raises(sqlite3.IntegrityError):MemoryCandidateExtractor().extract_for_session(sid)
        result='IntegrityError'
    elif route=='registry':
        r=registry.execute('extract_memory_candidates',{'session_id':sid});result=r.to_web();assert (r.data or json.loads(r.summary)).get("error")
    else:
        app=create_app();app.config['PROPAGATE_EXCEPTIONS']=False
        with app.test_client() as http:r=http.post('/api/management/memory/extract',json={'session_id':sid});result={'status':r.status_code,'body':r.get_data(as_text=True)}
        assert r.status_code==500
    after=_extraction_rows(store.root);_extraction_capture(route+'_'+mode+'.json',{'before':before,'after':after,'result':result,'storage_root':str(store.root)})
    assert after==before
@pytest.mark.parametrize('mode',['create','refresh'])
def test_extraction_auto_index_failure_preserves_evidence_and_old_candidates(engine,monkeypatch,mode):
    _,cfg=engine;sid,store,before=_extraction_setup(cfg,monkeypatch,mode)
    indexed=EvidenceStore(cfg.knowledge_dir,cfg.sessions_resolved).index_session(sid)
    after=_extraction_rows(store.root)
    with store.db.connect() as conn:evidence=[dict(r) for r in conn.execute('SELECT * FROM evidence_records ORDER BY id')]
    _extraction_capture('auto_'+mode+'.json',{'before':before,'after':after,'indexed':indexed,'evidence':evidence,'storage_root':str(store.root)})
    assert indexed==3 and len(evidence)==3
    assert after==before

@pytest.mark.parametrize('route',['store','registry','http'])
@pytest.mark.parametrize('fault',['second_readback','refresh_readback','second_commit','refresh_ignored'])
def test_extraction_commit_and_readback_restore_entire_batch(engine,monkeypatch,route,fault):
    from data_agent.tools.registry import registry
    from data_agent.web.app import create_app
    _,cfg=engine;sid,store,before=_extraction_setup(cfg,monkeypatch,'refresh' if fault.startswith('refresh') else 'create')
    with store.db.connect() as conn:
        conn.execute('DROP TRIGGER fail_second')
        if fault=='second_commit':
            conn.execute('CREATE TABLE allowed_guard(id INTEGER PRIMARY KEY)')
            conn.execute('CREATE TABLE deferred_guard(id INTEGER REFERENCES allowed_guard(id) DEFERRABLE INITIALLY DEFERRED)')
            conn.execute("CREATE TRIGGER reject_commit AFTER INSERT ON memory_items WHEN NEW.text LIKE '%EXTRACT_SECOND%' BEGIN INSERT INTO deferred_guard VALUES(1); END")
        if fault=='refresh_ignored':conn.execute("CREATE TRIGGER ignore_refresh BEFORE UPDATE ON memory_items BEGIN SELECT RAISE(IGNORE); END")
    fired=[];original=MemoryStore._item_from_row
    if fault in {'second_readback','refresh_readback'}:
        def reject(self,row):
            changed=('EXTRACT_SECOND' in row['text'] if fault=='second_readback' else 'EXTRACT_FIRST' in row['text'] and json.loads(row['source_evidence_ids'])==['ev_extraction_source_1'])
            if changed:fired.append(True);raise OSError('extraction result readback failure')
            return original(self,row)
        monkeypatch.setattr(MemoryStore,'_item_from_row',reject)
    error=None
    try:
        if route=='store':MemoryCandidateExtractor().extract_for_session(sid)
        elif route=='registry':
            r=registry.execute('extract_memory_candidates',{'session_id':sid});error=(r.data or json.loads(r.summary)).get("error")
        else:
            app=create_app();app.config['PROPAGATE_EXCEPTIONS']=False
            with app.test_client() as http:r=http.post('/api/management/memory/extract',json={'session_id':sid});error=r.status_code==500
    except (RuntimeError,OSError,sqlite3.IntegrityError) as exc:error=str(exc)
    after=_extraction_rows(store.root);_extraction_capture('fault_'+route+'_'+fault+'.json',{'before':before,'after':after,'error':error,'fired':fired,'storage_root':str(store.root)})
    assert error
    if fault.endswith('readback'):assert fired
    assert after==before
    if fault=='second_commit':
        with store.db.connect() as conn:assert conn.execute('SELECT COUNT(*) FROM deferred_guard').fetchone()[0]==0


@pytest.mark.parametrize("status", ["candidate", "rejected", "confirmed", "observed", "promoted", "deprecated"])
def test_extraction_refresh_preserves_original_state_boundary(engine, monkeypatch, status):
    _, cfg = engine
    sid, store, _ = _extraction_setup(cfg, monkeypatch, "success")
    MemoryCandidateExtractor().extract_for_session(sid)
    item = next(i for i in store.list() if "EXTRACT_FIRST" in i.text)
    with store.db.connect() as conn:
        conn.execute("UPDATE memory_items SET status=? WHERE id=?", (status, item.id))
    source = cfg.sessions_resolved / sid / "conversation.json"
    messages = json.loads(source.read_text(encoding="utf-8"))
    source.write_text(json.dumps([{"role": "assistant", "content": "shift"}, *messages], ensure_ascii=False), encoding="utf-8")
    with monkeypatch.context() as m:
        m.setattr(EvidenceStore, "_try_extract_memory_candidates", lambda *a: None)
        EvidenceStore().index_session(sid)
    before = _extraction_rows(store.root)
    result = MemoryCandidateExtractor().extract_for_session(sid)
    after = _extraction_rows(store.root)
    old = next(r for r in before if r["id"] == item.id)
    current = next(r for r in after if r["id"] == item.id)
    assert result.created == 0 and result.skipped == 2
    assert current["status"] == status and current["text"] == old["text"]
    if status in {"candidate", "rejected"}:
        assert json.loads(current["source_evidence_ids"]) == ["ev_extraction_source_2"]
    else:
        assert current == old
    _extraction_capture("status_" + status + ".json", {"before": before, "after": after, "status": status, "storage_root": str(store.root)})


@pytest.mark.parametrize("limit,created,skipped", [(0, 0, 2), (1, 1, 1), (10, 2, 0)])
def test_extraction_retains_original_new_candidate_limit(engine, monkeypatch, limit, created, skipped):
    _, cfg = engine
    sid, store, _ = _extraction_setup(cfg, monkeypatch, "success")
    result = MemoryCandidateExtractor().extract_for_session(sid, max_candidates=limit)
    assert result.scanned == 3 and result.created == created and result.skipped == skipped
    assert len(result.candidates) == len(_extraction_rows(store.root)) == created


def test_extraction_same_batch_normalized_dedup_keeps_original_first_text(engine, monkeypatch):
    _, cfg = engine
    sid, store, _ = _extraction_setup(cfg, monkeypatch, "success")
    texts = ["Please remember: EXACT VALUE", "please remember:  exact value"]
    path = cfg.sessions_resolved / sid / "conversation.json"
    path.write_text(json.dumps([{"role": "user", "content": t} for t in texts]), encoding="utf-8")
    with monkeypatch.context() as m:
        m.setattr(EvidenceStore, "_try_extract_memory_candidates", lambda *a: None)
        EvidenceStore().index_session(sid)
    result = MemoryCandidateExtractor().extract_for_session(sid)
    items = store.list()
    assert result.created == 1 and result.skipped == 1 and len(items) == 1
    assert items[0].text == texts[0] and items[0].source_evidence_ids == ["ev_extraction_source_1"]
    repeated = MemoryCandidateExtractor().extract_for_session(sid)
    assert repeated.created == 0 and repeated.skipped == 2 and store.list()[0].id == items[0].id


def test_extraction_empty_evidence_is_a_true_noop(engine):
    _, cfg = engine
    store = MemoryStore(cfg.knowledge_dir)
    before = _extraction_rows(store.root)
    result = MemoryCandidateExtractor().extract_for_session("missing")
    assert (result.scanned, result.created, result.skipped, result.candidates) == (0, 0, 0, [])
    assert _extraction_rows(store.root) == before
