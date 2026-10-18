from pathlib import Path

import pytest

from data_agent.knowledge.memory import MemoryStore
from data_agent.knowledge.models import MemoryStatus, MemoryType


def test_create_confirm_reject_and_deprecate_memory(tmp_path: Path):
    store = MemoryStore(tmp_path / "knowledge")

    candidate = store.create_candidate(
        text="Use net revenue for ecommerce revenue analysis.",
        summary="Prefer net revenue.",
        memory_type=MemoryType.DOMAIN_FACT,
        confidence=0.72,
        source_session_id="s1",
        domain="ecommerce",
        tags=["metric"],
    )

    assert candidate.status == MemoryStatus.CANDIDATE
    assert candidate.type == MemoryType.DOMAIN_FACT
    assert candidate.source_session_id == "s1"
    assert candidate.domain == "ecommerce"
    assert candidate.tags == ["metric"]
    assert store.list(status=MemoryStatus.CANDIDATE.value)[0].id == candidate.id

    confirmed = store.confirm(candidate.id)
    assert confirmed is not None
    assert confirmed.status == MemoryStatus.CONFIRMED
    assert confirmed.confidence > candidate.confidence

    reject_candidate = store.create_candidate(text="Reject this memory.")
    rejected = store.reject(reject_candidate.id)
    assert rejected is not None
    assert rejected.status == MemoryStatus.REJECTED

    deprecated = store.deprecate(confirmed.id)
    assert deprecated is not None
    assert deprecated.status == MemoryStatus.DEPRECATED

    promote_candidate = store.create_candidate(text="Promote this memory.")
    promoted_base = store.confirm(promote_candidate.id)
    promoted = store.mark_promoted(promoted_base.id)
    assert promoted is not None
    assert promoted.status == MemoryStatus.PROMOTED


def test_confirmed_memory_search_excludes_candidates(tmp_path: Path):
    store = MemoryStore(tmp_path / "knowledge")
    store.create_candidate(
        text="Always inspect MCP config for tool startup failures.",
        summary="MCP startup troubleshooting.",
        memory_type=MemoryType.WORKFLOW_PATTERN,
        confidence=0.6,
    )

    assert store.search("MCP startup") == []
    candidate = store.list(status=MemoryStatus.CANDIDATE.value)[0]
    store.confirm(candidate.id)

    assert store.search("MCP startup")[0].id == candidate.id


def test_touch_used_updates_usage_metadata(tmp_path: Path):
    store = MemoryStore(tmp_path / "knowledge")
    item = store.create_candidate(
        text="Check workbook headers before analysis.",
        summary="Workbook header check.",
    )

    touched = store.touch_used(item.id)

    assert touched is not None
    assert touched.hit_count == 1
    assert touched.last_used_at


def test_invalid_memory_type_status_and_confidence_are_rejected(tmp_path: Path):
    store = MemoryStore(tmp_path / "knowledge")

    with pytest.raises(ValueError, match="memory_type"):
        store.create_candidate(text="Bad type.", memory_type="not-a-type")

    with pytest.raises(ValueError, match="confidence"):
        store.create_candidate(text="Bad confidence.", confidence=1.5)

    with pytest.raises(ValueError, match="confidence"):
        store.create_candidate(text="Bad confidence.", confidence="nan")

    with pytest.raises(ValueError, match="status"):
        store.list(status="not-a-status")


def test_json_list_fields_reject_strings_and_round_trip_lists(tmp_path: Path):
    store = MemoryStore(tmp_path / "knowledge")

    with pytest.raises(ValueError, match="tags"):
        store.create_candidate(text="Bad tags.", tags="metric")

    item = store.create_candidate(
        text="Keep source references.",
        source_message_ids=["m1", "m2"],
        source_tool_call_ids=["t1"],
        tags=["metric", "source"],
    )

    loaded = store.get(item.id)
    assert loaded is not None
    assert loaded.source_message_ids == ["m1", "m2"]
    assert loaded.source_tool_call_ids == ["t1"]
    assert loaded.tags == ["metric", "source"]


def test_search_domain_filter_limit_and_stable_order(tmp_path: Path):
    store = MemoryStore(tmp_path / "knowledge")
    older = store.confirm(
        store.create_candidate(
            text="Use net revenue in ecommerce reporting.",
            summary="net revenue",
            domain="ecommerce",
            confidence=0.8,
        ).id
    )
    newer = store.confirm(
        store.create_candidate(
            text="Use net revenue in ecommerce dashboards.",
            summary="net revenue",
            domain="ecommerce",
            confidence=0.8,
        ).id
    )
    store.confirm(
        store.create_candidate(
            text="Use net revenue in finance reporting.",
            summary="net revenue",
            domain="finance",
            confidence=0.95,
        ).id
    )

    assert store.search("net revenue", limit=0) == []
    expected = sorted([older, newer], key=lambda item: (item.updated_at, item.id), reverse=True)
    assert store.search("net revenue", domain="ecommerce", limit=10) == expected


def test_touch_used_missing_id_returns_none(tmp_path: Path):
    store = MemoryStore(tmp_path / "knowledge")

    assert store.touch_used("missing") is None


def test_terminal_statuses_cannot_be_confirmed(tmp_path: Path):
    store = MemoryStore(tmp_path / "knowledge")
    rejected = store.reject(store.create_candidate(text="Reject.").id)
    deprecated = store.deprecate(store.confirm(store.create_candidate(text="Deprecate.").id).id)
    promoted = store.mark_promoted(store.confirm(store.create_candidate(text="Promote.").id).id)

    assert store.confirm(rejected.id).status == MemoryStatus.REJECTED
    assert store.confirm(deprecated.id).status == MemoryStatus.DEPRECATED
    assert store.confirm(promoted.id).status == MemoryStatus.PROMOTED


# S3: rollback of mutations whose public result cannot be read before commit.
import json
import sqlite3
from tests.test_trusted_publication_semantics import engine


def _memory_storage_rows(root):
    with sqlite3.connect(root / "knowledge.sqlite3") as conn:
        conn.row_factory=sqlite3.Row
        return [dict(r) for r in conn.execute("SELECT * FROM memory_items ORDER BY id")]


def _memory_storage_fixture(engine,monkeypatch):
    from data_agent.tools import knowledge_tools
    from data_agent.web.app import create_app
    _,cfg=engine;store=MemoryStore(cfg.knowledge_dir)
    monkeypatch.setattr(knowledge_tools,"_memory_store",store)
    app=create_app();app.config["PROPAGATE_EXCEPTIONS"]=False
    return store,app.test_client()


def _memory_storage_call(store,http,route,action,item):
    from data_agent.tools.registry import registry
    if route=="registry":
        name="create_memory_candidate" if action=="create" else "confirm_memory"
        args={"text":"NEW MEMORY","summary":"NEW SUMMARY"} if action=="create" else {"memory_id":item.id}
        result=registry.execute(name,args)
        return {"error":True} if "error" in json.loads(result.summary) else result.data
    if route=="http":
        base="/api/management/memory"
        if action=="create":response=http.post(base,json={"text":"NEW MEMORY","summary":"NEW SUMMARY"})
        elif action=="update":response=http.patch(base+"/"+item.id,json={"text":"NEW MEMORY","summary":"NEW SUMMARY"})
        else:response=http.post(base+"/"+item.id+"/"+action)
        return {"error":True} if response.status_code>=400 else response.get_json()
    try:
        if action=="create":return store.create_candidate("NEW MEMORY",summary="NEW SUMMARY")
        if action=="update":return store.update(item.id,text="NEW MEMORY",summary="NEW SUMMARY")
        return getattr(store,action)(item.id)
    except Exception as exc:return {"error":type(exc).__name__}


_MEMORY_STORAGE_ROUTES=[(action,route) for action,routes in [
    ("create",["store","registry","http"]),("confirm",["store","registry","http"]),
    ("update",["store","http"]),("reject",["store","http"]),("deprecate",["store","http"]),
    ("mark_promoted",["store"]),("touch_used",["store"])] for route in routes]


@pytest.mark.parametrize("action,route",_MEMORY_STORAGE_ROUTES)
@pytest.mark.parametrize("fault",["raise","missing"])
def test_memory_storage_readback_failure_keeps_original_database(engine,monkeypatch,action,route,fault):
    store,http=_memory_storage_fixture(engine,monkeypatch)
    item=store.create_candidate("OLD MEMORY",summary="OLD SUMMARY",source_session_id="owned")
    if action in {"deprecate","mark_promoted"}:item=store.confirm(item.id)
    before=_memory_storage_rows(store.root);original=MemoryStore._item_from_row;fired=[]
    old_status=item.status.value
    def reject_changed(self,row):
        changed=(row["id"]!=item.id if action=="create" else row["text"]!="OLD MEMORY" if action=="update" else row["hit_count"]>0 if action=="touch_used" else row["status"]!=old_status)
        if changed:
            fired.append(True)
            if fault=="missing":return None
            raise OSError("memory result readback failed")
        return original(self,row)
    with monkeypatch.context() as m:
        m.setattr(MemoryStore,"_item_from_row",reject_changed)
        result=_memory_storage_call(store,http,route,action,item)
        assert fired and isinstance(result,dict) and "error" in result,result
    assert _memory_storage_rows(store.root)==before
    assert MemoryStore(store.root).get(item.id).text=="OLD MEMORY"


@pytest.mark.parametrize("route",["store","registry","http"])
@pytest.mark.parametrize("action",["create","confirm"])
def test_memory_storage_sql_rejection_is_not_reported_as_success(engine,monkeypatch,route,action):
    store,http=_memory_storage_fixture(engine,monkeypatch);item=store.create_candidate("OLD MEMORY")
    before=_memory_storage_rows(store.root)
    event="INSERT" if action=="create" else "UPDATE"
    with store.db.connect() as conn:conn.execute(f"CREATE TRIGGER deny_write BEFORE {event} ON memory_items BEGIN SELECT RAISE(ABORT, 'memory denied'); END")
    result=_memory_storage_call(store,http,route,action,item)
    assert isinstance(result,dict) and "error" in result,result
    assert _memory_storage_rows(store.root)==before


@pytest.mark.parametrize("action",["create","confirm","update","reject","deprecate","mark_promoted","touch_used"])
def test_memory_storage_commit_failure_keeps_original_database(tmp_path,action):
    store=MemoryStore(tmp_path/"knowledge");item=store.create_candidate("OLD MEMORY")
    if action in {"deprecate","mark_promoted"}:item=store.confirm(item.id)
    before=_memory_storage_rows(store.root)
    event="INSERT" if action=="create" else "UPDATE"
    with store.db.connect() as conn:
        conn.execute("CREATE TABLE allowed_guard (id INTEGER PRIMARY KEY)")
        conn.execute("CREATE TABLE deferred_guard (id INTEGER REFERENCES allowed_guard(id) DEFERRABLE INITIALLY DEFERRED)")
        conn.execute(f"CREATE TRIGGER fail_commit AFTER {event} ON memory_items BEGIN INSERT INTO deferred_guard VALUES(1); END")
    result=_memory_storage_call(store,None,"store",action,item)
    assert isinstance(result,dict) and "error" in result,result
    assert _memory_storage_rows(store.root)==before
    with store.db.connect() as conn:assert conn.execute("SELECT COUNT(*) FROM deferred_guard").fetchone()[0]==0


@pytest.mark.parametrize("text",["","中文记忆","line\r\nline\nend\r"])
def test_memory_storage_exact_text_roundtrip_and_status_contract(tmp_path,text):
    store=MemoryStore(tmp_path/"knowledge");item=store.create_candidate(text,source_session_id="s1",tags=["exact"])
    assert MemoryStore(store.root).get(item.id).text==text
    confirmed=store.confirm(item.id);assert confirmed.status==MemoryStatus.CONFIRMED and confirmed.confidence==pytest.approx(.75)
    assert store.confirm(item.id)==confirmed
    updated=store.update(item.id,text=text,summary="updated");assert updated.text==text and updated.summary=="updated"
    assert store.deprecate(item.id).status==MemoryStatus.DEPRECATED
    with pytest.raises(ValueError):store.update(item.id,text="no")
    assert store.reject(item.id).status==MemoryStatus.DEPRECATED


def test_memory_storage_missing_touch_keeps_original_none_semantics(tmp_path):
    store=MemoryStore(tmp_path/"knowledge")
    assert store.touch_used("missing") is None and store.confirm("missing") is None
    assert store.update("missing",text="no") is None and store.reject("missing") is None
    assert _memory_storage_rows(store.root)==[]
