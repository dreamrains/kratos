from data_agent.knowledge.library import KnowledgeLibrary
from data_agent.knowledge.memory import MemoryStore
from data_agent.knowledge.models import KnowledgeSource, MemoryStatus


def test_memory_promotes_to_knowledge_with_traceable_source(tmp_path):
    root = tmp_path / "knowledge"
    memory = MemoryStore(root)
    library = KnowledgeLibrary(root)
    item = memory.create_candidate(
        text="GMV must exclude canceled and refunded orders.",
        summary="GMV口径",
        domain="ecommerce",
        tags=["gmv"],
        source_session_id="s1",
    )
    memory.confirm(item.id)

    knowledge = memory.promote_to_knowledge(
        item.id,
        library=library,
        title="GMV 口径",
        summary="GMV 排除取消与退款订单",
    )
    promoted = memory.get(item.id)

    assert knowledge is not None
    assert knowledge.source == KnowledgeSource.MEMORY_PROMOTION
    assert knowledge.domain == "ecommerce"
    assert "GMV" in knowledge.content
    assert promoted.status == MemoryStatus.PROMOTED
    assert promoted.promotion_target == knowledge.id


def test_memory_edit_and_candidate_delete(tmp_path):
    store = MemoryStore(tmp_path / "knowledge")
    item = store.create_candidate("Use gross revenue.", domain="ecommerce", confidence=0.6)

    updated = store.update(
        item.id,
        text="Use net revenue.",
        summary="Revenue preference",
        confidence=0.8,
        tags=["revenue"],
    )

    assert updated.text == "Use net revenue."
    assert updated.summary == "Revenue preference"
    assert updated.confidence == 0.8
    assert updated.tags == ["revenue"]
    assert store.delete_candidate(item.id) is True
    assert store.get(item.id) is None


import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from tests.test_trusted_publication_semantics import engine
from data_agent.knowledge.library import KnowledgeLibrary
from data_agent.knowledge.memory import MemoryStore
from data_agent.knowledge.models import MemoryStatus


def _promotion_snapshot(store,library):
    with store.db.connect() as conn:
        memory=[dict(r) for r in conn.execute("SELECT * FROM memory_items ORDER BY id")]
    with library.db.connect() as conn:
        knowledge=[dict(r) for r in conn.execute("SELECT * FROM knowledge_items ORDER BY id")]
    files={str(p.relative_to(library.root)):p.read_bytes() for p in library.library_dir.rglob("*.md")}
    return memory,knowledge,files


def _promotion_fixture(engine,monkeypatch):
    from data_agent.web.app import create_app
    from data_agent.web.blueprints import management
    _,cfg=engine;store=MemoryStore(cfg.knowledge_dir);library=KnowledgeLibrary(cfg.knowledge_dir)
    old=library.create("Old policy","general","OLD_REFERENCE")
    item=store.create_candidate("NEW_PROMOTION\r\n中文\nend\r",summary="Memory policy",tags=["metric"]);item=store.confirm(item.id)
    monkeypatch.setattr(management,"MemoryStore",lambda:store);monkeypatch.setattr(management,"KnowledgeLibrary",lambda:library)
    app=create_app();app.config["PROPAGATE_EXCEPTIONS"]=False
    return store,library,old,item,app.test_client()


def _promotion_call(store,library,http,route,item,**args):
    if route=="http":
        response=http.post("/api/management/memory/"+item.id+"/promote",json=args)
        return {"error":response.status_code} if response.status_code>=400 else response.get_json()
    try:return store.promote_to_knowledge(item.id,library,**args)
    except Exception as exc:return {"error":type(exc).__name__}


@pytest.mark.parametrize("route",["store","http"])
@pytest.mark.parametrize("fault",["deny","partial","before_replace","after_replace","sql_statement","sql_commit","memory_readback","knowledge_readback","state_mismatch"])
def test_memory_promotion_caught_failure_restores_both_resources(engine,monkeypatch,route,fault):
    from tests.test_global_capabilities import _rule_write_fault
    from data_agent.knowledge import library as library_module
    store,library,old,item,http=_promotion_fixture(engine,monkeypatch);before=_promotion_snapshot(store,library)
    with monkeypatch.context() as m:
        m.setattr(library_module.uuid,"uuid4",lambda:SimpleNamespace(hex="b"*32))
        if fault in {"deny","partial","before_replace","after_replace"}:
            path=library.root/"library/general/memory-policy-kn_bbbbbbbbbb.md"
            fired=_rule_write_fault(m,path,item.text,fault)
        elif fault in {"sql_statement","sql_commit","state_mismatch"}:
            with store.db.connect() as conn:
                if fault=="sql_statement":conn.execute("CREATE TRIGGER deny_promotion BEFORE UPDATE ON memory_items WHEN NEW.status='promoted' BEGIN SELECT RAISE(ABORT, 'promotion denied'); END")
                elif fault=="sql_commit":
                    conn.execute("CREATE TABLE allowed_guard (id INTEGER PRIMARY KEY)")
                    conn.execute("CREATE TABLE deferred_guard (id INTEGER REFERENCES allowed_guard(id) DEFERRABLE INITIALLY DEFERRED)")
                    conn.execute("CREATE TRIGGER fail_commit AFTER UPDATE ON memory_items WHEN NEW.status='promoted' BEGIN INSERT INTO deferred_guard VALUES(1); END")
                else:conn.execute("CREATE TRIGGER mismatch AFTER UPDATE ON memory_items WHEN NEW.status='promoted' BEGIN UPDATE memory_items SET promotion_target='wrong' WHERE id=NEW.id; END")
        elif fault=="memory_readback":
            original=MemoryStore._item_from_row
            def reject(self,row):
                if row["status"]=="promoted":raise OSError("promotion memory readback failed")
                return original(self,row)
            m.setattr(MemoryStore,"_item_from_row",reject)
        else:
            original=KnowledgeLibrary._item_from_row
            def reject(self,row):
                if row["id"]!=old.id:raise OSError("promotion knowledge readback failed")
                return original(self,row)
            m.setattr(KnowledgeLibrary,"_item_from_row",reject)
        result=_promotion_call(store,library,http,route,item)
        assert isinstance(result,dict) and "error" in result,result
        if fault in {"deny","partial","before_replace","after_replace"}:assert fired["fired"]
    assert _promotion_snapshot(store,library)==before
    assert not list(library.root.rglob(".atomic-*.tmp"))


@pytest.mark.parametrize("route",["store","http"])
@pytest.mark.parametrize("scope",["other_root","other_database"])
def test_memory_promotion_different_database_rejected_before_write(engine,monkeypatch,route,scope):
    from data_agent.knowledge.sqlite_store import KnowledgeDatabase
    store,library,old,item,http=_promotion_fixture(engine,monkeypatch)
    if scope=="other_root":
        other=KnowledgeLibrary(library.root.parent/"other-knowledge")
        library.root=other.root;library.library_dir=other.library_dir;library.db=other.db
    else:library.db=KnowledgeDatabase(library.root/"other.sqlite3")
    before=_promotion_snapshot(store,library)
    result=_promotion_call(store,library,http,route,item)
    assert isinstance(result,dict) and "error" in result,result
    assert _promotion_snapshot(store,library)==before


@pytest.mark.parametrize("route",["store","http"])
@pytest.mark.parametrize("text",["","中文内容","line\r\nline\nend\r"])
def test_memory_promotion_success_preserves_exact_content_and_source(engine,monkeypatch,route,text):
    store,library,old,_,http=_promotion_fixture(engine,monkeypatch)
    item=store.create_candidate(text,summary="Summary",domain="ecommerce",tags=["exact"]);store.confirm(item.id)
    result=_promotion_call(store,library,http,route,item,title="Explicit title",summary="Explicit summary")
    assert not (isinstance(result,dict) and "error" in result)
    current=store.get(item.id);knowledge=library.get(current.promotion_target)
    assert current.status==MemoryStatus.PROMOTED and current.text==text
    assert knowledge.content==text and knowledge.title=="Explicit title" and knowledge.summary=="Explicit summary" and knowledge.domain=="ecommerce" and knowledge.tags==["exact"]
    assert knowledge.source.value=="memory_promotion" and knowledge.version==1
    assert (library.root/knowledge.path).read_bytes()==text.encode("utf-8")
    assert library.get(old.id).content=="OLD_REFERENCE"


@pytest.mark.parametrize("route",["store","http"])
@pytest.mark.parametrize("state",["missing","candidate","rejected","deprecated","promoted"])
def test_memory_promotion_only_confirmed_state_can_write(engine,monkeypatch,route,state):
    store,library,old,_,http=_promotion_fixture(engine,monkeypatch)
    item=store.create_candidate("Other memory")
    if state=="missing":item=SimpleNamespace(id="missing")
    elif state=="rejected":item=store.reject(item.id)
    elif state in {"deprecated","promoted"}:
        store.confirm(item.id);item=store.deprecate(item.id) if state=="deprecated" else store.mark_promoted(item.id)
    before=_promotion_snapshot(store,library);result=_promotion_call(store,library,http,route,item)
    assert result is None if route=="store" and state=="missing" else isinstance(result,dict) and "error" in result
    assert _promotion_snapshot(store,library)==before
