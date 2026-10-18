from pathlib import Path

from data_agent.knowledge.library import KnowledgeLibrary
from data_agent.knowledge.models import KnowledgeStatus


def test_create_search_and_read_knowledge_item(tmp_path: Path):
    library = KnowledgeLibrary(tmp_path / "knowledge")

    item = library.create(
        title="GMV definition",
        domain="ecommerce",
        content="GMV = paid order amount excluding canceled orders.",
        summary="Defines GMV.",
        tags=["metric", "revenue"],
    )

    assert item.status == KnowledgeStatus.ACTIVE
    assert item.domain == "ecommerce"
    assert (tmp_path / "knowledge" / "library" / "ecommerce").exists()

    loaded = library.get(item.id)
    assert loaded is not None
    assert loaded.content == "GMV = paid order amount excluding canceled orders."

    results = library.search("paid canceled", domain="ecommerce")
    assert [result.id for result in results] == [item.id]


def test_deprecated_knowledge_is_hidden_from_default_search(tmp_path: Path):
    library = KnowledgeLibrary(tmp_path / "knowledge")
    item = library.create(
        title="Old rule",
        domain="general",
        content="Use the old rule.",
        summary="Old rule.",
    )

    library.deprecate(item.id, superseded_by="")

    assert library.get(item.id).status == KnowledgeStatus.DEPRECATED
    assert library.search("old rule") == []
    assert library.search("old rule", include_deprecated=True)[0].id == item.id


def test_domain_path_traversal_is_sanitized_inside_library(tmp_path: Path):
    root = tmp_path / "knowledge"
    library = KnowledgeLibrary(root)

    item = library.create(
        title="Unsafe domain",
        domain="../../escaped:bad\\domain",
        content="safe content",
    )

    item_path = (root / item.path).resolve()
    library_dir = (root / "library").resolve()
    path_parts = Path(item.path).parts

    assert item_path.is_relative_to(library_dir)
    assert path_parts[0] == "library"
    assert path_parts[1] == "escaped-bad-domain"
    assert ".." not in path_parts
    assert ":" not in Path(item.path).as_posix()
    assert "domain" not in path_parts[2:-1]
    assert not (tmp_path / "escaped:bad").exists()


def test_restore_clears_superseded_by(tmp_path: Path):
    library = KnowledgeLibrary(tmp_path / "knowledge")
    item = library.create("Old metric", "general", "Old content")

    deprecated = library.deprecate(item.id, superseded_by="kn_new")
    assert deprecated.superseded_by == "kn_new"

    restored = library.restore(item.id)

    assert restored.status == KnowledgeStatus.ACTIVE
    assert restored.superseded_by == ""


def test_update_increments_version_and_updates_content(tmp_path: Path):
    library = KnowledgeLibrary(tmp_path / "knowledge")
    item = library.create("Metric", "general", "Old content")

    updated = library.update(item.id, content="New content", summary="New summary")

    assert updated.version == item.version + 1
    assert updated.content == "New content"
    assert updated.summary == "New summary"
    assert library.get(item.id).content == "New content"


def test_delete_removes_file_and_database_record(tmp_path: Path):
    root = tmp_path / "knowledge"
    library = KnowledgeLibrary(root)
    item = library.create("Metric", "general", "Content")
    item_path = root / item.path
    assert item_path.exists()

    assert library.delete(item.id) is True

    assert not item_path.exists()
    assert library.get(item.id) is None


# S3: independent disk/SQLite oracles across the existing public interfaces.
import json
import ast
import pytest


def _knowledge_storage_fixture(engine, monkeypatch):
    from data_agent.tools import knowledge_tools
    from data_agent.web.app import create_app
    loop, cfg = engine
    library = KnowledgeLibrary(cfg.knowledge_dir)
    monkeypatch.setattr(knowledge_tools, "_knowledge_library", library)
    app = create_app()
    app.config["PROPAGATE_EXCEPTIONS"] = False
    return library, app.test_client()


def _knowledge_call(library, http, route, action, item=None, content="NEW\r\nLINE\nEND\r"):
    from data_agent.tools.registry import registry
    if route == "library":
        try:
            if action == "create": return library.create("Metric", "general", content)
            if action == "update": return library.update(item.id, content=content, summary="NEW SUMMARY")
            return library.delete(item.id)
        except Exception as exc: return {"error": type(exc).__name__}
    if route == "registry":
        result = registry.execute("create_knowledge_item", {"title":"Metric", "domain":"general", "content":content})
        return ast.literal_eval(result.summary)
    if action == "create": response = http.post("/api/management/knowledge", json={"title":"Metric", "domain":"general", "content":content})
    elif action == "update": response = http.patch("/api/management/knowledge/"+item.id, json={"content":content,"summary":"NEW SUMMARY"})
    else: response = http.delete("/api/management/knowledge/"+item.id)
    return response.get_json() if response.status_code < 400 else {"error":response.status_code}


@pytest.mark.parametrize("route,action", [("library","create"),("registry","create"),("http","create"),("library","update"),("http","update"),("library","delete"),("http","delete")])
@pytest.mark.parametrize("sql_fault",["statement","commit"])
def test_knowledge_storage_sql_failure_restores_original_file_and_row(engine,monkeypatch,route,action,sql_fault):
    library,http = _knowledge_storage_fixture(engine,monkeypatch)
    item = library.create("Original", "general", "OLD CONTENT")
    before_files = {p.relative_to(library.root).as_posix():p.read_bytes() for p in library.library_dir.rglob("*.md")}
    with library.db.connect() as conn:
        before_rows = [tuple(r) for r in conn.execute("SELECT * FROM knowledge_items ORDER BY id")]
        conn.execute("CREATE TABLE s3_parent (id INTEGER PRIMARY KEY)")
        conn.execute("CREATE TABLE s3_child (id INTEGER REFERENCES s3_parent(id) DEFERRABLE INITIALLY DEFERRED)")
        body = "SELECT RAISE(ABORT, 's3_write_refused');" if sql_fault=="statement" else "INSERT INTO s3_child VALUES (999);"
        conn.execute("CREATE TRIGGER fail_write BEFORE "+{"create":"INSERT","update":"UPDATE","delete":"DELETE"}[action]+" ON knowledge_items BEGIN "+body+" END")
    result = _knowledge_call(library,http,route,action,item)
    assert isinstance(result,dict) and "error" in result,result
    after_files = {p.relative_to(library.root).as_posix():p.read_bytes() for p in library.library_dir.rglob("*.md")}
    with library.db.connect() as conn: after_rows = [tuple(r) for r in conn.execute("SELECT * FROM knowledge_items ORDER BY id")]
    assert after_rows == before_rows
    assert after_files == before_files
    assert KnowledgeLibrary(library.root).get(item.id).content == "OLD CONTENT"
    assert not list(library.root.rglob(".atomic-*.tmp"))


@pytest.mark.parametrize("route",["library","registry","http"])
def test_knowledge_storage_exact_content_across_create_search_restart(engine,monkeypatch,route):
    library,http = _knowledge_storage_fixture(engine,monkeypatch)
    content = "EXACT\r\nLINE\nEND\r"
    result = _knowledge_call(library,http,route,"create",content=content)
    item_id = result["id"] if isinstance(result,dict) else result.id
    item = KnowledgeLibrary(library.root).get(item_id)
    assert item.content == content
    assert (library.root/item.path).read_bytes() == content.encode("utf-8")
    from data_agent.tools.registry import registry
    found = ast.literal_eval(registry.execute("search_knowledge",{"query":"EXACT"}).summary)
    assert found[0]["content"] == content
    found = http.get("/api/management/knowledge/search?q=EXACT").get_json()
    assert found[0]["content"] == content


@pytest.mark.parametrize("route",["library","http"])
@pytest.mark.parametrize("fault",["deny","partial","before_replace","after_replace"])
def test_knowledge_storage_failed_content_write_preserves_version(engine,monkeypatch,route,fault):
    from tests.test_global_capabilities import _rule_write_fault
    library,http = _knowledge_storage_fixture(engine,monkeypatch)
    item = library.create("Original", "general", "OLD CONTENT")
    path = library.root/item.path
    with monkeypatch.context() as m:
        fired = _rule_write_fault(m,path,"NEW CONTENT",fault)
        result = _knowledge_call(library,http,route,"update",item,content="NEW CONTENT")
        assert fired["fired"] and isinstance(result,dict) and "error" in result,result
    current = KnowledgeLibrary(library.root).get(item.id)
    assert path.read_bytes() == b"OLD CONTENT"
    assert current.content == "OLD CONTENT" and current.version == 1 and current.summary == ""
    assert not list(library.root.rglob(".atomic-*.tmp"))


@pytest.mark.parametrize("action",["create","update"])
def test_knowledge_storage_readback_failure_rolls_back_sql_and_disk(engine,monkeypatch,action):
    library,http = _knowledge_storage_fixture(engine,monkeypatch)
    item = library.create("Original", "general", "OLD CONTENT")
    before = {p.name:p.read_bytes() for p in library.library_dir.rglob("*.md")}
    original = library._item_from_row
    def reject_new(row):
        if (action=="create" and row["id"]!=item.id) or (action=="update" and row["version"]>1): raise OSError("readback failure")
        return original(row)
    monkeypatch.setattr(library,"_item_from_row",reject_new)
    result = _knowledge_call(library,http,"library",action,item)
    assert "error" in result
    loaded = KnowledgeLibrary(library.root)
    assert [(x.id,x.version,x.content) for x in loaded.list()] == [(item.id,1,"OLD CONTENT")]
    assert {p.name:p.read_bytes() for p in library.library_dir.rglob("*.md")} == before


@pytest.mark.parametrize("route",["library","registry","http"])
def test_knowledge_storage_missing_source_is_not_fabricated_as_empty(engine,monkeypatch,route):
    library,http = _knowledge_storage_fixture(engine,monkeypatch)
    item = library.create("Original", "general", "OLD CONTENT")
    (library.root/item.path).unlink()
    if route=="library":
        with pytest.raises(FileNotFoundError): library.get(item.id)
    elif route=="registry":
        from data_agent.tools.registry import registry
        assert "error" in json.loads(registry.execute("search_knowledge",{"query":"Original"}).summary)
    else:
        assert http.get("/api/management/knowledge/search?q=Original").status_code == 500

from tests.test_trusted_publication_semantics import engine


@pytest.mark.parametrize("route",["library","http"])
@pytest.mark.parametrize("fault",["before_unlink","after_unlink"])
def test_knowledge_storage_failed_delete_restores_file_and_row(engine,monkeypatch,route,fault):
    library,http = _knowledge_storage_fixture(engine,monkeypatch)
    item = library.create("Original", "general", "OLD CONTENT")
    path = library.root/item.path
    unlink = Path.unlink
    fired = []
    def reject(p,*args,**kwargs):
        if p==path and not fired:
            fired.append(True)
            if fault=="after_unlink": unlink(p,*args,**kwargs)
            raise OSError("delete failed")
        return unlink(p,*args,**kwargs)
    with monkeypatch.context() as m:
        m.setattr(Path,"unlink",reject)
        result = _knowledge_call(library,http,route,"delete",item)
        assert fired and "error" in result
    loaded = KnowledgeLibrary(library.root).get(item.id)
    assert loaded.content=="OLD CONTENT" and loaded.version==1
    assert path.read_bytes()==b"OLD CONTENT"


@pytest.mark.parametrize("route",["library","registry","http"])
@pytest.mark.parametrize("fault",["deny","partial","before_replace","after_replace"])
def test_knowledge_storage_failed_creation_leaves_no_file_or_row(engine,monkeypatch,route,fault):
    from types import SimpleNamespace
    from data_agent.knowledge import library as library_module
    from tests.test_global_capabilities import _rule_write_fault
    library,http = _knowledge_storage_fixture(engine,monkeypatch)
    path=library.root/"library/general/metric-kn_aaaaaaaaaa.md";path.parent.mkdir(parents=True)
    with monkeypatch.context() as m:
        m.setattr(library_module.uuid,"uuid4",lambda:SimpleNamespace(hex="a"*32))
        fired=_rule_write_fault(m,path,"NEW CONTENT",fault)
        result=_knowledge_call(library,http,route,"create",content="NEW CONTENT")
        assert fired["fired"] and "error" in result
    assert not path.exists() and KnowledgeLibrary(library.root).list()==[]
    assert not list(library.root.rglob(".atomic-*.tmp"))


@pytest.mark.parametrize("route",["library","http"])
@pytest.mark.parametrize("action",["deprecate","restore"])
def test_knowledge_storage_visibility_readback_failure_preserves_original_status(engine,monkeypatch,route,action):
    library,http=_knowledge_storage_fixture(engine,monkeypatch)
    item=library.create("Original","general","OLD CONTENT")
    if action=="restore":item=library.deprecate(item.id)
    before=item.status.value;original=KnowledgeLibrary._item_from_row
    def reject_changed(self,row):
        if row["status"]!=before:raise OSError("visibility readback failed")
        return original(self,row)
    with monkeypatch.context() as m:
        m.setattr(KnowledgeLibrary,"_item_from_row",reject_changed)
        if route=="library":
            with pytest.raises(OSError):getattr(library,action)(item.id)
        else:assert http.post("/api/management/knowledge/"+item.id+"/"+action).status_code==500
    assert KnowledgeLibrary(library.root).get(item.id).status.value==before
    assert (library.root/item.path).read_bytes()==b"OLD CONTENT"


@pytest.mark.parametrize("content",["","中文正文", "line\r\nline\nend\r"])
def test_knowledge_storage_successful_update_and_delete_keep_original_semantics(tmp_path,content):
    library=KnowledgeLibrary(tmp_path/"knowledge");item=library.create("Original","general","OLD")
    updated=library.update(item.id,content=content,title="New title",summary="New summary",tags=["metric"])
    assert updated.content==content and updated.version==2 and updated.title=="New title" and updated.tags==["metric"] and updated.summary=="New summary"
    assert (library.root/item.path).read_bytes()==content.encode("utf-8")
    assert library.delete(item.id) and not (library.root/item.path).exists() and library.get(item.id) is None
    assert library.update(item.id,content="Missing") is None and library.delete(item.id) is False
