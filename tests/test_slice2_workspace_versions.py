"""Slice 2: raw datasets and derived analysis datasets have distinct identities."""

from __future__ import annotations

import pandas as pd

from data_agent.session.workspace import Workspace
from data_agent.agent.context import AgentContext, use_agent_context
from data_agent.tools.data_clean import apply_type_conversion, auto_clean, clean_data
from data_agent.tools.data_io import load_data, reload_data
from data_agent.tools.eda import top_n
from data_agent.tools.statistics import ab_test
from data_agent.tools.chart_contract import validate_chart_request


def test_raw_identity_survives_a_copy_on_write_derived_dataset():
    workspace = Workspace()
    raw = pd.DataFrame({"revenue": ["12.5", "-", "8"], "campaign": ["a", "b", "a"]})

    workspace.add("cross_promotion", raw)
    raw_identity = workspace.get_data_identity("cross_promotion")
    parsed = raw.assign(revenue=pd.to_numeric(raw["revenue"], errors="coerce"))
    workspace.derive(
        "cross_promotion",
        "cross_promotion__analysis",
        parsed,
        expression="revenue: object -> numeric; '-' -> missing",
    )

    analysis_identity = workspace.get_data_identity("cross_promotion__analysis")

    assert raw_identity["role"] == "raw"
    assert raw_identity["fingerprint"].startswith("sha256:")
    assert workspace.get("cross_promotion").equals(raw)
    assert workspace.get("cross_promotion__analysis")["revenue"].isna().sum() == 1
    assert analysis_identity["role"] == "analysis"
    assert analysis_identity["parent_version_ids"] == [raw_identity["version_id"]]
    assert analysis_identity["source_fingerprint"] == raw_identity["fingerprint"]
    assert analysis_identity["fingerprint"] != raw_identity["fingerprint"]


def test_list_datasets_exposes_version_identity_without_leaking_values():
    workspace = Workspace()
    workspace.add("orders", pd.DataFrame({"user_id": [101, 102], "amount": [10, 20]}))

    listed = workspace.list_datasets()["orders"]

    assert listed["data_identity"]["role"] == "raw"
    assert listed["data_identity"]["version_id"]
    assert "101" not in str(listed["data_identity"])


def test_safe_type_conversion_creates_an_analysis_version_without_replacing_raw():
    workspace = Workspace()
    context = AgentContext(session_id="slice2-cow", workspace=workspace)
    raw = pd.DataFrame({"revenue": ["12.5", "-", "8"]})

    with use_agent_context(context):
        workspace.add("cross_promotion", raw)
        result = apply_type_conversion("cross_promotion", column="revenue", target_type="numeric")

    payload = __import__("json").loads(result)
    assert "dataset" in payload, payload
    analysis_name = payload["dataset"]
    assert payload["source_dataset"] == "cross_promotion"
    assert workspace.get("cross_promotion").equals(raw)
    assert workspace.get(analysis_name)["revenue"].isna().sum() == 1
    assert workspace.get_data_identity(analysis_name)["role"] == "analysis"


def test_d04_before_after_orders_use_the_paired_user_level_path():
    data_path = __import__("pathlib").Path("reference/test_doc/省钱卡购卡前后订单.xlsx")
    workspace = Workspace()
    context = AgentContext(session_id="slice2-r02", workspace=workspace)
    group_col = "用户类型（1是购卡前30天内，2是购卡后30天内）"

    with use_agent_context(context):
        workspace.add("d04_orders", pd.read_excel(data_path))
        result = __import__("json").loads(ab_test("d04_orders", group_col, "实收金额"))

    assert result["design"] == "paired"
    assert result["analysis_unit"] == "user_id"
    assert result["unit_aggregation"] == "sum"
    assert result["paired_sample_size"] == 61
    assert result["excluded_unpaired_units"] == 1
    assert result["difference"]["absolute"] == -1220.1311
    assert result["test"]["p_value"] == 0.0186
    assert result["wilcoxon_signed_rank"]["p_value"] == 0.027699


def test_d04_exact_duplicates_are_retained_until_deduplication_is_explicit():
    data_path = __import__("pathlib").Path("reference/test_doc/省钱卡购卡前后订单.xlsx")
    workspace = Workspace()
    context = AgentContext(session_id="slice2-r02-dedup", workspace=workspace)
    raw = pd.read_excel(data_path)

    with use_agent_context(context):
        workspace.add("d04_orders", raw)
        retained = __import__("json").loads(clean_data("d04_orders"))
        deduplicated = __import__("json").loads(clean_data("d04_orders", deduplicate=True))

    assert raw.duplicated().sum() == 468
    assert retained["final_rows"] == 7206
    assert not any(action["action"] == "deduplicate" for action in retained["actions"])
    assert deduplicated["final_rows"] == 6738
    assert any(action["action"] == "deduplicate" and action["removed"] == 468 for action in deduplicated["actions"])


def test_d05_mixed_revenue_is_parsed_in_a_derived_analysis_version_with_failures_visible():
    data_path = __import__("pathlib").Path("reference/test_doc/游戏互推.xlsx")
    raw = pd.read_excel(data_path)
    cleaned, applied, _ = auto_clean(raw)
    revenue_conversion = next(item for item in applied if item["column"] == "卖量收入")

    assert raw["卖量收入"].eq("-").sum() == 59
    assert cleaned["卖量收入"].notna().sum() == 1926
    assert cleaned["卖量收入"].isna().sum() == 59
    assert revenue_conversion["conversion_failures"] == 59
    assert revenue_conversion["conversion_failure_rate"] == 0.029723


def test_load_data_keeps_d05_upload_as_raw_and_uses_named_analysis_dataset():
    from data_agent.session.workspace import workspace

    raw_name = "slice2_d05_upload"
    raw_snapshot_name = f"{raw_name}__raw"
    analysis_name = raw_name
    workspace.remove(raw_name)
    workspace.remove(raw_snapshot_name)
    try:
        data_path = __import__("pathlib").Path("reference/test_doc/游戏互推.xlsx").resolve()
        output = load_data(str(data_path), name=raw_name)
        assert analysis_name in output
        assert raw_snapshot_name in output
        assert workspace.get(raw_snapshot_name)["卖量收入"].eq("-").sum() == 59
        assert workspace.get(analysis_name)["卖量收入"].isna().sum() == 59
        raw_identity = workspace.get_data_identity(raw_snapshot_name)
        analysis_identity = workspace.get_data_identity(analysis_name)
        assert raw_identity["role"] == "raw"
        assert analysis_identity["role"] == "analysis"
        assert analysis_identity["parent_version_ids"] == [raw_identity["version_id"]]
    finally:
        workspace.remove(analysis_name)
        workspace.remove(raw_snapshot_name)


def test_reload_data_archives_the_previous_active_version_without_rewriting_it(tmp_path):
    """A same-name reload must preserve the old evidence-addressable version."""
    from data_agent.config import get_config

    first_path = tmp_path / "orders_v1.csv"
    second_path = tmp_path / "orders_v2.csv"
    first_path.write_text("date,amount\n2026-09-01,10\n2026-09-02,20\n", encoding="utf-8")
    second_path.write_text("date,amount\n2026-09-01,10\n2026-09-02,10\n", encoding="utf-8")
    cfg = get_config()
    old_sessions = cfg.sessions_dir
    cfg.sessions_dir = tmp_path / "sessions"
    local_workspace = Workspace()
    context = AgentContext(session_id="reload_data_audit", workspace=local_workspace)
    try:
        with use_agent_context(context):
            first_output = load_data(str(first_path), name="orders")
            first_identity = local_workspace.get_data_identity("orders")
            reload_output = reload_data(str(second_path), name="orders")

        archived = "orders__history"
        current_identity = local_workspace.get_data_identity("orders")
        archived_identity = local_workspace.get_data_identity(archived)
        assert "orders__raw" in first_output
        assert "旧活动版本已归档为 'orders__history'" in reload_output
        assert local_workspace.get(archived)["amount"].tolist() == [10, 20]
        assert local_workspace.get("orders")["amount"].tolist() == [10, 10]
        assert archived_identity == first_identity
        assert current_identity["fingerprint"] != first_identity["fingerprint"]
        assert local_workspace.get_metadata(archived, "archived_from") == "orders"
        assert any(
            item["op"] == "archive_version" and item["to"] == archived
            for item in local_workspace.get_transform_log()
        )
        assert (cfg.sessions_dir / context.session_id / "data" / "orders__history.pkl").is_file()
    finally:
        cfg.sessions_dir = old_sessions


def test_top_n_can_create_a_copy_on_write_dataset_for_a_following_chart():
    workspace = Workspace()
    context = AgentContext(session_id="slice2-top-n", workspace=workspace)
    raw = pd.DataFrame({"game": ["a", "b", "c"], "revenue": [10, 30, 20]})

    with use_agent_context(context):
        workspace.add("cross", raw)
        result = __import__("json").loads(top_n("cross", sort_by="revenue", n=2, save_as="cross_top2"))

    assert result["dataset"] == "cross_top2"
    assert result["source_dataset"] == "cross"
    assert workspace.get("cross").equals(raw)
    assert workspace.get("cross_top2")["revenue"].tolist() == [30, 20]
    assert workspace.get_data_identity("cross_top2")["parent_version_ids"] == [
        workspace.get_data_identity("cross")["version_id"]
    ]


def test_low_cardinality_numeric_group_is_explicitly_safe_for_a_bar_chart_axis():
    contract = validate_chart_request(
        pd.DataFrame({"window_code": [1, 1, 2, 2], "revenue": [10, 20, 15, 25]}),
        chart_type="bar",
        x_col="window_code",
        y_cols=["revenue"],
        aggregation="sum",
    )

    assert contract.valid
    assert contract.semantic_roles["window_code"] == "category"
    assert contract.dataframe["window_code"].tolist() == ["1", "1", "2", "2"]
    assert "low_cardinality_numeric_to_category" in contract.transformations


def test_source_identity_and_transitive_roots_survive_real_derivation():
    workspace=Workspace()
    frame=pd.DataFrame({'value':[1,2]})
    origins=[{'kind':'uploaded_file','source_id':'upload-a','file_sha256':'sha256:a'},
             {'kind':'uploaded_file','source_id':'upload-b','file_sha256':'sha256:b'}]
    for name,origin in zip(('a','b'),origins): workspace.add(name,frame,source_origin=origin)
    a=workspace.get_data_identity('a');b=workspace.get_data_identity('b')
    assert a['fingerprint']==b['fingerprint'] and a['version_id']!=b['version_id']
    workspace.derive('a','a_copy',frame,expression='copy original')
    workspace.derive_multi(['a_copy','b'],'joined',pd.concat([frame,frame]),expression='concat all rows')
    joined=workspace.get_data_identity('joined')
    assert set(joined['ancestor_version_ids'])=={a['version_id'],b['version_id'],workspace.get_data_identity('a_copy')['version_id']}
    assert joined['source_origins']==origins
    joined['source_origins'][0]['kind']='forged'
    joined['ancestor_version_ids'].clear()
    assert workspace.get_data_identity('joined')['source_origins']==origins
    assert len(workspace.get_data_identity('joined')['ancestor_version_ids'])==3


# S3: file ingestion is one namespace commit, including explicit replacement.
import pytest
from copy import deepcopy

@pytest.mark.parametrize("replace", [False, True])
@pytest.mark.parametrize("fault", ["clean", "raw_add", "derive", "derive_error"])
def test_file_ingestion_failure_preserves_namespace_identity_metadata_and_log(engine, monkeypatch, replace, fault):
    from data_agent.tools.registry import registry
    import data_agent.tools.data_clean as clean
    loop, cfg = engine
    source = cfg.workspace_resolved / "inbox" / "replacement.csv"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("amount,label\n91,new\n92,new\n", encoding="utf-8")
    ws = loop.context.workspace
    ws.set_metadata("orders", "sentinel", {"old": "keep"})
    before = deepcopy(ws.list_datasets())
    frames = {name: ws.get(name) for name in before}
    log = deepcopy(ws.get_transform_log())
    owner = Workspace
    method = {"clean": "auto_clean", "raw_add": "add", "derive": "derive", "derive_error": "derive"}[fault]
    original = getattr(clean if fault == "clean" else owner, method)
    def fail(*args, **kwargs):
        if fault != "clean": original(*args, **kwargs)
        if fault == "derive_error": return "Error: injected producer return"
        raise RuntimeError("injected ingestion " + fault)
    monkeypatch.setattr(clean if fault == "clean" else owner, method, fail)
    args = {"source": str(source), "name": "orders" if replace else "new_table"}
    result = registry.execute("reload_data" if replace else "load_data", args)
    assert "error" in result.summary.lower(), result.summary
    assert ws.list_datasets() == before
    assert ws.get_transform_log() == log
    for name, frame in frames.items(): pd.testing.assert_frame_equal(ws.get(name), frame)


def test_reload_requires_existing_target_and_creates_no_objects(engine):
    from data_agent.tools.registry import registry
    loop, cfg = engine
    source = cfg.workspace_resolved / "inbox" / "new.csv"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("amount\n99\n", encoding="utf-8")
    before = deepcopy(loop.context.workspace.list_datasets())
    result = registry.execute("reload_data", {"source": str(source), "name": "missing"})
    assert "error" in result.summary.lower(), result.summary
    assert loop.context.workspace.list_datasets() == before


@pytest.mark.parametrize("alias", ["../escape", "a/b", "a\\b", ".", "..", "", "bad\nname", "a" * 129])
def test_file_ingestion_rejects_unsafe_alias_before_namespace_or_persistence(engine, alias):
    from data_agent.tools.registry import registry
    loop, cfg = engine
    source = cfg.workspace_resolved / "inbox" / "new.csv"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("amount\n99\n", encoding="utf-8")
    before = deepcopy(loop.context.workspace.list_datasets())
    result = registry.execute("load_data", {"source": str(source), "name": alias})
    assert "error" in result.summary.lower(), result.summary
    assert loop.context.workspace.list_datasets() == before


@pytest.mark.parametrize("fmt", ["csv", "tsv", "excel", "json", "jsonl"])
def test_file_formats_bind_exact_source_bytes_raw_parent_and_history(engine, fmt):
    import hashlib
    from data_agent.tools.registry import registry
    loop, cfg = engine
    root = cfg.workspace_resolved / "inbox"; root.mkdir(parents=True, exist_ok=True)
    suffix = {"excel": "xlsx"}.get(fmt, fmt)
    def write(path, values):
        frame = pd.DataFrame({"amount": values, "label": ["甲", "乙"]})
        if fmt in {"csv", "tsv"}: frame.to_csv(path, index=False, sep="\t" if fmt == "tsv" else ",")
        elif fmt == "excel": frame.to_excel(path, index=False)
        else: frame.to_json(path, orient="records", lines=fmt == "jsonl", force_ascii=False)
        return frame
    first = root / ("v1." + suffix); second = root / ("v2." + suffix)
    expected = write(first, [11, 29]); write(second, [7, 13])
    result = registry.execute("load_data", {"source": str(first), "name": "loaded"})
    assert "error" not in result.summary.lower(), result.summary
    ws = loop.context.workspace; old = ws.get_data_identity("loaded")
    pd.testing.assert_frame_equal(ws.get("loaded__raw"), expected)
    assert old["parent_version_ids"] == [ws.get_data_identity("loaded__raw")["version_id"]]
    assert old["source_origins"][0]["file_sha256"] == "sha256:" + hashlib.sha256(first.read_bytes()).hexdigest()
    conflict = registry.execute("load_data", {"source": str(second), "name": "loaded"})
    assert "error" in conflict.summary.lower() and ws.get_data_identity("loaded") == old
    result = registry.execute("reload_data", {"source": str(second), "name": "loaded"})
    assert "error" not in result.summary.lower(), result.summary
    assert ws.get_data_identity("loaded__history") == old
    assert ws.get("loaded")["amount"].tolist() == [7, 13]
    assert ws.get_data_identity("loaded")["source_origins"][0]["file_sha256"] == "sha256:" + hashlib.sha256(second.read_bytes()).hexdigest()

from tests.test_trusted_publication_semantics import engine


@pytest.mark.parametrize("replace", [False, True])
@pytest.mark.parametrize("fault", ["missing", "empty", "malformed", "unsupported"])
def test_file_parse_failure_preserves_active_and_all_existing_objects(engine, replace, fault):
    from data_agent.tools.registry import registry
    loop, cfg = engine; ws = loop.context.workspace
    source = cfg.workspace_resolved / "inbox" / ("invalid.txt" if fault == "unsupported" else "invalid.csv")
    source.parent.mkdir(parents=True, exist_ok=True)
    if fault != "missing": source.write_text('amount\n"unterminated' if fault == "malformed" else "" if fault == "empty" else "amount\n9\n", encoding="utf-8")
    before, log = deepcopy(ws.list_datasets()), deepcopy(ws.get_transform_log())
    result = registry.execute("reload_data" if replace else "load_data", {"name": "orders" if replace else "fresh", "source": str(source)})
    assert "error" in result.summary.lower(), result.summary
    assert ws.list_datasets() == before and ws.get_transform_log() == log


@pytest.mark.parametrize("fmt", ["csv", "tsv"])
@pytest.mark.parametrize("explicit_format", [False, True])
def test_file_gbk_fallback_and_explicit_format_use_exact_input(engine, fmt, explicit_format):
    import hashlib
    from data_agent.tools.registry import registry
    loop, cfg = engine; ws = loop.context.workspace
    source = cfg.workspace_resolved / "inbox" / ("encoded." + ("dat" if explicit_format else fmt))
    source.parent.mkdir(parents=True, exist_ok=True)
    raw = ("amount,label\n17,中文\n" if fmt == "csv" else "amount\tlabel\n17\t中文\n").encode("gbk")
    source.write_bytes(raw)
    args = {"name": "encoded", "source": str(source)}
    if explicit_format: args["fmt"] = fmt.upper()
    result = registry.execute("load_data", args)
    assert "error" not in result.summary.lower(), result.summary
    assert ws.get("encoded")["label"].tolist() == ["中文"]
    assert ws.get_data_identity("encoded")["source_origins"][0]["file_sha256"] == "sha256:" + hashlib.sha256(raw).hexdigest()


# S3 SQL ingestion: real SQLite and independent source/namespace oracles.
@pytest.mark.parametrize("case", ["collision", "unsafe", "query_failure", "install_failure", "source", "empty"])
def test_sql_ingestion_preserves_sources_types_and_failure_boundaries(engine, monkeypatch, tmp_path, case):
    import hashlib
    import sqlalchemy
    from data_agent.tools.registry import registry
    loop, cfg = engine
    ws = loop.context.workspace
    database = tmp_path / "source.sqlite"
    connection = "sqlite:///" + str(database)
    engine_db = sqlalchemy.create_engine(connection)
    with engine_db.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE incoming (amount INTEGER, code TEXT)")
        conn.exec_driver_sql("INSERT INTO incoming VALUES (7, '12%'), (13, '2026-10-11'), (22, 'raw')")
    engine_db.dispose()
    before = deepcopy(ws.list_datasets())
    old_frames = {n: ws.get(n) for n in before}
    log = deepcopy(ws.get_transform_log())
    disposed = []
    original_create = sqlalchemy.create_engine
    def create(*args, **kwargs):
        actual = original_create(*args, **kwargs)
        original_dispose = actual.dispose
        def dispose(*a, **kw):
            disposed.append(True)
            return original_dispose(*a, **kw)
        monkeypatch.setattr(actual, "dispose", dispose)
        return actual
    monkeypatch.setattr(sqlalchemy, "create_engine", create)
    name = "orders" if case == "collision" else "../escape" if case == "unsafe" else "sql_orders"
    query = "SELECT amount, code FROM incoming" + (" WHERE 1=0" if case == "empty" else "")
    if case == "query_failure": query = "SELECT * FROM missing_table"
    if case == "install_failure":
        original_derive = Workspace.derive
        def fail(*a, **kw):
            original_derive(*a, **kw)
            raise RuntimeError("injected SQL derive failure")
        monkeypatch.setattr(Workspace, "derive", fail)
    result = registry.execute("load_sql", {"connection_string": connection, "query": query, "name": name})
    if case in {"collision", "unsafe", "query_failure", "install_failure"}:
        assert "error" in result.summary.lower(), result.summary
        assert ws.list_datasets() == before
        assert ws.get_transform_log() == log
        for n, frame in old_frames.items(): pd.testing.assert_frame_equal(ws.get(n), frame)
        assert disposed == ([] if case in {"collision", "unsafe"} else [True])
        return
    assert "error" not in result.summary.lower(), result.summary
    identity = ws.get_data_identity(name)
    assert identity["role"] == "analysis"
    raw = next(n for n, info in ws.list_datasets().items() if info["data_identity"]["version_id"] in identity["parent_version_ids"])
    pd.testing.assert_frame_equal(ws.get(raw), ws.get(name))
    assert ws.get(name)["code"].tolist() == ([] if case == "empty" else ["12%", "2026-10-11", "raw"])
    origin = identity["source_origins"][0]
    assert origin["kind"] == "sql_query"
    assert origin["query_sha256"] == "sha256:" + hashlib.sha256(query.encode()).hexdigest()
    assert origin["source_id"] == "sha256:" + hashlib.sha256(connection.encode()).hexdigest()
    assert connection not in str(origin) and query not in str(origin)
    assert disposed == [True]
    assert any(c["dataset"] == name for c in loop.context.analysis_state.dataset_contracts)


@pytest.mark.parametrize("phase", ["blocked_query", "connect", "dispose", "backup", "metadata", "trust"])
def test_sql_ingestion_does_not_report_success_when_read_or_durability_fails(engine, monkeypatch, phase):
    import sqlalchemy
    import data_agent.tools.data_io as module
    from data_agent.tools.registry import registry
    loop, _ = engine
    ws = loop.context.workspace
    before = deepcopy(ws.list_datasets())
    disposed = []
    class FakeConnection:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def exec_driver_sql(self, sql):
            from types import SimpleNamespace
            return SimpleNamespace(scalar_one=lambda: 1)
    class FakeEngine:
        def connect(self): return FakeConnection()
        def dispose(self):
            disposed.append(True)
            if phase == "dispose": raise RuntimeError("secret-password")
    def connect(*args, **kwargs):
        if phase in {"blocked_query", "connect"}: raise RuntimeError("secret-password")
        return FakeEngine()
    monkeypatch.setattr(sqlalchemy, "create_engine", connect)
    monkeypatch.setattr(module.pd, "read_sql", lambda *a, **kw: pd.DataFrame({"amount": [7, 13, 22]}))
    def fail(*a, **kw): raise RuntimeError("secret-password")
    if phase == "backup": monkeypatch.setattr(Workspace, "persist_dataset", fail)
    if phase == "metadata": monkeypatch.setattr(Workspace, "save_meta", fail)
    if phase == "trust": monkeypatch.setattr(module, "_record_trust_workflow", fail)
    result = registry.execute("load_sql", {"connection_string": "sqlite://", "query": "DELETE FROM incoming" if phase == "blocked_query" else "SELECT * FROM incoming", "name": "new_sql"})
    assert "error" in result.summary.lower(), result.summary
    assert "secret-password" not in result.summary
    assert disposed == ([] if phase in {"blocked_query", "connect"} else [True])
    # Failed ingestion now restores the whole namespace, including durable failures.
    assert ws.list_datasets() == before
    assert not ws.exists("new_sql") and not ws.exists("new_sql__raw")


@pytest.mark.parametrize("operation", ["DELETE FROM incoming RETURNING amount", "UPDATE incoming SET amount=999 RETURNING amount", "INSERT INTO incoming VALUES (999) RETURNING amount"])
def test_sql_enforced_read_only_prevents_cte_database_mutation(engine, tmp_path, operation):
    import sqlite3
    from data_agent.tools.registry import registry
    loop, _ = engine
    database = tmp_path / "readonly.sqlite"
    with sqlite3.connect(database) as conn:
        conn.execute("CREATE TABLE incoming(amount INTEGER)")
        conn.executemany("INSERT INTO incoming VALUES (?)", [(7,), (13,), (22,)])
    before = deepcopy(loop.context.workspace.list_datasets())
    result = registry.execute("load_sql", {"connection_string": "sqlite:///" + str(database), "query": "WITH observed AS (SELECT 1) " + operation, "name": "readonly_attempt"})
    assert "error" in result.summary.lower() and "只读" in result.summary, result.summary
    with sqlite3.connect(database) as conn:
        assert conn.execute("SELECT amount FROM incoming ORDER BY amount").fetchall() == [(7,), (13,), (22,)]
    assert loop.context.workspace.list_datasets() == before


@pytest.mark.parametrize("backend", ["postgresql", "mysql", "mssql", "oracle"])
def test_sql_unverified_backend_is_rejected_before_driver_or_connection(engine, monkeypatch, backend):
    import sqlalchemy
    from data_agent.tools.registry import registry
    calls = []
    def connect(*a, **kw):
        calls.append(a)
        raise RuntimeError("must not connect")
    monkeypatch.setattr(sqlalchemy, "create_engine", connect)
    result = registry.execute("load_sql", {"connection_string": backend + "://user:secret@example.test/db", "query": "SELECT 1", "name": "unsupported"})
    assert "error" in result.summary.lower() and "只读" in result.summary and "未支持" in result.summary
    assert not calls and "secret" not in result.summary


@pytest.mark.parametrize("guard", [0, None])
def test_sql_unverified_read_only_setting_does_not_execute_query(engine, monkeypatch, guard):
    import sqlalchemy
    from types import SimpleNamespace
    import data_agent.tools.data_io as module
    from data_agent.tools.registry import registry
    calls = []; disposed = []
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def exec_driver_sql(self, sql): return SimpleNamespace(scalar_one=lambda: guard)
    class Engine:
        def connect(self): return Connection()
        def dispose(self): disposed.append(True)
    monkeypatch.setattr(sqlalchemy, "create_engine", lambda *a, **kw: Engine())
    def read(*a, **kw):
        calls.append(True)
        return pd.DataFrame({"amount": [1]})
    monkeypatch.setattr(module.pd, "read_sql", read)
    before = deepcopy(engine[0].context.workspace.list_datasets())
    result = registry.execute("load_sql", {"connection_string": "sqlite://", "query": "SELECT 1", "name": "unverified"})
    assert "error" in result.summary.lower() and "只读" in result.summary
    assert not calls and disposed == [True]
    assert engine[0].context.workspace.list_datasets() == before
