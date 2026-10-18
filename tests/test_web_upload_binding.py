"""Regression coverage for deterministic Web upload-to-session binding."""

from __future__ import annotations

import io
from pathlib import Path

import pytest


@pytest.fixture
def isolated_storage(tmp_path, monkeypatch):
    from data_agent.config import get_config

    cfg = get_config()
    monkeypatch.setattr(cfg, "workspace_dir", tmp_path / "workspace")
    monkeypatch.setattr(cfg, "sessions_dir", tmp_path / "sessions")
    return cfg


def _upload(
    client,
    filename: str = "retention.csv",
    content: bytes = b"day,retention\n1,0.4\n7,0.2\n",
) -> dict:
    response = client.post(
        "/api/upload",
        data={"file": (io.BytesIO(content), filename)},
        content_type="multipart/form-data",
    )
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()


def test_upload_returns_an_opaque_ticket_without_publishing_a_shared_inbox_file(
    isolated_storage,
):
    from data_agent.web.app import create_app

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        payload = _upload(client)

    assert payload["filename"] == "retention.csv"
    assert len(payload["upload_id"]) == 32
    assert "path" not in payload
    assert not (isolated_storage.inbox_dir / "retention.csv").exists()
    ticket_dir = isolated_storage.sessions_resolved / ".pending_uploads" / payload["upload_id"]
    assert (ticket_dir / "upload.json").is_file()
    assert (ticket_dir / "retention.csv").is_file()


def test_pending_upload_can_be_cancelled_without_deleting_claimed_data(isolated_storage):
    from data_agent.web.app import create_app
    from data_agent.web.blueprints.uploads import bind_uploads_to_session

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        pending = _upload(client, content=b"x\n1\n")
        cancelled = client.delete(f"/api/upload/{pending['upload_id']}")
        assert cancelled.status_code == 200
        assert not (
            isolated_storage.sessions_resolved
            / ".pending_uploads"
            / pending["upload_id"]
        ).exists()

        claimed = _upload(client, content=b"x\n2\n")
        bound = bind_uploads_to_session(
            "session-one",
            [{"upload_id": claimed["upload_id"], "filename": claimed["filename"]}],
        )[0]
        repeated = client.delete(f"/api/upload/{claimed['upload_id']}")

    assert repeated.status_code == 200
    assert bound.path.is_file()


def test_chat_binds_and_loads_upload_before_the_model_turn(isolated_storage):
    from data_agent.agent.context import use_agent_context
    from data_agent.agent.loop import AgentLoop
    from data_agent.session.workspace import workspace
    from data_agent.web.app import create_app

    loop = AgentLoop(client=object(), session_id="upload-session")
    observed: dict = {}

    def fake_stream(message: str, turn_context: str = ""):
        with use_agent_context(loop.context):
            observed["datasets"] = workspace.list_datasets()
        observed["message"] = message
        observed["turn_context"] = turn_context
        yield {"type": "text_delta", "text": "analysis started"}

    loop.stream_turn = fake_stream

    class Manager:
        @staticmethod
        def get_or_create(session_id=None, model_id=None):
            assert session_id == "upload-session"
            return loop

    app = create_app()
    app.config.update(TESTING=True, agent_manager=Manager())
    with app.test_client() as client:
        uploaded = _upload(client)
        response = client.post(
            "/api/chat",
            json={
                "session_id": "upload-session",
                "message": "请拟合留存率公式\n分析文件: retention.csv",
                "uploads": [
                    {"upload_id": uploaded["upload_id"], "filename": uploaded["filename"]}
                ],
            },
            buffered=True,
        )

    assert response.status_code == 200
    assert "analysis started" in response.get_data(as_text=True)
    assert "retention" in observed["datasets"]
    assert "retention__raw" in observed["datasets"]
    assert "retention.csv" in observed["turn_context"]
    assert "already loaded" in observed["turn_context"]
    assert "Do not ask the user for file paths" in observed["turn_context"]
    bound_file = (
        isolated_storage.sessions_resolved
        / "upload-session"
        / "uploads"
        / uploaded["upload_id"]
        / "retention.csv"
    )
    assert bound_file.is_file()
    assert not (
        isolated_storage.sessions_resolved
        / ".pending_uploads"
        / uploaded["upload_id"]
    ).exists()


def test_same_session_upload_retires_old_execution_scope_before_loading(isolated_storage, monkeypatch):
    from data_agent.agent.context import use_agent_context
    from data_agent.agent.loop import AgentLoop
    from data_agent.session.task_manager import task_manager
    from data_agent.session.workspace import workspace
    from data_agent.web.app import create_app
    import pandas as pd

    monkeypatch.setattr(task_manager, "_dir", isolated_storage.workspace_resolved / "tasks")
    monkeypatch.setattr(task_manager, "_next_id_val", 0)
    loop = AgentLoop(client=object(), session_id="upload-replan")
    from data_agent.agent.analysis_state import load_analysis_state
    from tests.test_stage3c0b_workflow_projection import _validated_plan
    state=load_analysis_state(loop.session_id)
    original_projection=state.set_analysis_plan(_validated_plan());state.save()
    loop.context.analysis_state=state
    with use_agent_context(loop.context):
        workspace.add("old_data", pd.DataFrame({"x": [1]}))
    old_plan = task_manager.create_plan(session_id=loop.session_id, goal="Old data plan")
    old_task = task_manager.create(
        "Old execution step",
        session_id=loop.session_id,
        plan_id=old_plan["id"],
        status="in_progress",
        dataset_inputs=["old_data"],
    )
    loop.context.refresh_workspace_scope()
    observed = {}

    def fake_stream(message, turn_context=""):
        with use_agent_context(loop.context):
            observed["datasets"] = workspace.list_datasets()
        yield {"type": "text_delta", "text": "ready"}

    loop.stream_turn = fake_stream

    class Manager:
        @staticmethod
        def get_or_create(session_id=None, model_id=None):
            return loop

    app = create_app()
    app.config.update(TESTING=True, agent_manager=Manager())
    with app.test_client() as client:
        uploaded = _upload(client, filename="next.csv", content=b"x\n2\n")
        response = client.post(
            "/api/chat",
            json={"session_id": loop.session_id, "message": "continue", "uploads": [uploaded]},
            buffered=True,
        )

    assert response.status_code == 200
    assert {"next", "next__raw"} <= set(observed["datasets"])
    assert task_manager.get_active_plan_id(loop.session_id) == ""
    assert task_manager.get(old_task["id"])["status"] == "superseded"
    assert state.analysis_plan is None and state.analysis_spec is None
    assert state.regression_history[-1]["analysis_plan"]==original_projection
    from data_agent.agent.analysis_flow_controller import AnalysisFlowController
    assert AnalysisFlowController(loop.session_id).ensure_workflow_tasks(state)["created"]==0
    assert task_manager.get_active_plan_id(loop.session_id)==""
    assert load_analysis_state(loop.session_id).regression_history[-1]["analysis_plan"]==original_projection


def test_failed_upload_ingestion_restores_plan_scope_and_removes_partial_datasets(
    isolated_storage,
    monkeypatch,
):
    import json
    import pandas as pd
    from data_agent.agent.context import use_agent_context
    from data_agent.agent.loop import AgentLoop
    from data_agent.session.task_manager import task_manager
    from data_agent.session.workspace import workspace
    from data_agent.tools import data_io
    from data_agent.web.app import create_app

    monkeypatch.setattr(task_manager, "_dir", isolated_storage.workspace_resolved / "tasks")
    monkeypatch.setattr(task_manager, "_next_id_val", 0)
    loop = AgentLoop(client=object(), session_id="upload-rollback")
    from data_agent.agent.analysis_state import load_analysis_state
    from tests.test_stage3c0b_workflow_projection import _validated_plan
    state=load_analysis_state(loop.session_id)
    original_projection=state.set_analysis_plan(_validated_plan());state.save()
    loop.context.analysis_state=state
    with use_agent_context(loop.context):
        workspace.add("old_data", pd.DataFrame({"x": [1]}))
    old_plan = task_manager.create_plan(session_id=loop.session_id, goal="Old data plan")
    old_task = task_manager.create(
        "Old execution step",
        session_id=loop.session_id,
        plan_id=old_plan["id"],
        plan_status="active",
        analysis_plan_id=old_plan["id"],
        step_id="step_old",
        combination_mode="independent",
        dataset_inputs=["old_data"],
    )
    task_manager.update(old_task["id"], status="in_progress")
    loop.context.refresh_workspace_scope()

    def fail_after_partial_load(_path, name):
        workspace.add(f"{name}__raw", pd.DataFrame({"x": [2]}))
        workspace.add(name, pd.DataFrame({"x": [2]}))
        return "Error: derived analysis copy failed"

    monkeypatch.setattr(data_io, "load_data", fail_after_partial_load)

    class Manager:
        @staticmethod
        def get_or_create(session_id=None, model_id=None):
            return loop

    app = create_app()
    app.config.update(TESTING=True, agent_manager=Manager())
    with app.test_client() as client:
        uploaded = _upload(client, filename="broken.csv", content=b"x\n2\n")
        response = client.post(
            "/api/chat",
            json={"session_id": loop.session_id, "message": "continue", "uploads": [uploaded]},
        )

    assert response.status_code == 422
    assert task_manager.get_active_plan_id(loop.session_id) == old_plan["id"]
    restored_task = task_manager.get(old_task["id"])
    assert restored_task["status"] == "in_progress"
    assert restored_task["plan_status"] == "active"
    assert loop.context.workspace_scope.plan_id == old_plan["id"]
    assert state.analysis_plan==original_projection and state.analysis_spec is None
    assert state.regression_history==[]
    assert load_analysis_state(loop.session_id).analysis_plan==original_projection
    with use_agent_context(loop.context):
        assert set(workspace.list_datasets()) == {"old_data"}
    record_path = (
        isolated_storage.sessions_resolved
        / loop.session_id
        / "uploads"
        / uploaded["upload_id"]
        / "upload.json"
    )
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["status"] == "failed"
    assert "derived analysis copy failed" in record["error"]


def test_metadata_publication_failure_restores_prior_workspace_metadata(
    isolated_storage,
    monkeypatch,
):
    import pandas as pd
    from data_agent.agent.context import use_agent_context
    from data_agent.agent.loop import AgentLoop
    from data_agent.session.task_manager import task_manager
    from data_agent.session.workspace import workspace
    from data_agent.web.app import create_app
    from data_agent.web.blueprints import uploads as uploads_module

    monkeypatch.setattr(task_manager, "_dir", isolated_storage.workspace_resolved / "tasks")
    monkeypatch.setattr(task_manager, "_next_id_val", 0)
    loop = AgentLoop(client=object(), session_id="upload-metadata-rollback")
    with use_agent_context(loop.context):
        workspace.add("old_data", pd.DataFrame({"x": [1]}))
        workspace.save_meta(loop.session_id)
    meta_path = isolated_storage.sessions_resolved / loop.session_id / "workspace_meta.json"
    meta_before = meta_path.read_bytes()
    old_plan = task_manager.create_plan(session_id=loop.session_id, goal="Old plan")
    old_task = task_manager.create(
        "Old step", session_id=loop.session_id, plan_id=old_plan["id"],
    )
    loop.context.refresh_workspace_scope()

    monkeypatch.setattr(
        uploads_module,
        "_update_ingestion_record",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("metadata record write failed")),
    )

    class Manager:
        @staticmethod
        def get_or_create(session_id=None, model_id=None):
            return loop

    app = create_app()
    app.config.update(TESTING=True, agent_manager=Manager())
    with app.test_client() as client:
        uploaded = _upload(client, filename="next.csv", content=b"x\n2\n")
        response = client.post(
            "/api/chat",
            json={"session_id": loop.session_id, "message": "continue", "uploads": [uploaded]},
        )

    assert response.status_code == 422
    assert meta_path.read_bytes() == meta_before
    assert task_manager.get_active_plan_id(loop.session_id) == old_plan["id"]
    assert task_manager.get(old_task["id"])["status"] == "pending"
    with use_agent_context(loop.context):
        assert set(workspace.list_datasets()) == {"old_data"}


def test_claimed_upload_cannot_be_rebound_to_another_session(isolated_storage):
    from data_agent.web.app import create_app
    from data_agent.web.blueprints.uploads import bind_uploads_to_session

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        uploaded = _upload(client)

    refs = [{"upload_id": uploaded["upload_id"], "filename": uploaded["filename"]}]
    first = bind_uploads_to_session("session-one", refs)
    assert first[0].session_id == "session-one"
    assert bind_uploads_to_session("session-one", refs)[0].path == first[0].path
    with pytest.raises(ValueError, match="not available"):
        bind_uploads_to_session("session-two", refs)


def test_upload_context_does_not_promote_repeated_ids_or_reclassify_prices(isolated_storage):
    from data_agent.agent.loop import AgentLoop
    from data_agent.web.app import create_app

    loop = AgentLoop(client=object(), session_id="semantic-upload")
    observed = {}

    def fake_stream(message, turn_context=""):
        observed["context"] = turn_context
        yield {"type": "text_delta", "text": "ready"}

    loop.stream_turn = fake_stream

    class Manager:
        @staticmethod
        def get_or_create(session_id=None, model_id=None):
            return loop

    rows = ["user_id,支付时间,商品名称,售价"]
    for i in range(20):
        rows.append(f"{700000000000000000 + i % 2},2026-04-{i+7:02d},周卡,{[12,45][i%2]}")
    app = create_app()
    app.config.update(TESTING=True, agent_manager=Manager())
    with app.test_client() as client:
        uploaded = _upload(client, filename="orders.csv", content=("\n".join(rows)).encode("utf8"))
        response = client.post("/api/chat", json={"session_id":"semantic-upload", "message":"比较订单金额", "uploads":[uploaded]}, buffered=True)
    assert response.status_code == 200
    context = observed["context"]
    assert "1 ID" in context
    assert "user_id 整体呈" not in context and "的 user_id" not in context
    assert "列 '售价'" not in context


def test_same_filename_uploads_are_isolated_by_ticket_and_session(isolated_storage):
    from data_agent.web.app import create_app
    from data_agent.web.blueprints.uploads import bind_uploads_to_session

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        first = _upload(client, content=b"x\n1\n")
        second = _upload(client, content=b"x\n2\n")

    assert first["upload_id"] != second["upload_id"]
    assert first["sha256"] != second["sha256"]
    first_bound = bind_uploads_to_session(
        "session-one",
        [{"upload_id": first["upload_id"], "filename": first["filename"]}],
    )[0]
    second_bound = bind_uploads_to_session(
        "session-two",
        [{"upload_id": second["upload_id"], "filename": second["filename"]}],
    )[0]
    assert first_bound.path != second_bound.path
    assert first_bound.path.read_bytes() == b"x\n1\n"
    assert second_bound.path.read_bytes() == b"x\n2\n"


def test_ticket_binding_rejects_bytes_changed_after_upload(isolated_storage):
    from data_agent.web.app import create_app
    from data_agent.web.blueprints.uploads import bind_uploads_to_session

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        uploaded = _upload(client)

    staged = (
        isolated_storage.sessions_resolved
        / ".pending_uploads"
        / uploaded["upload_id"]
        / uploaded["filename"]
    )
    staged.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="integrity verification"):
        bind_uploads_to_session(
            "session-one",
            [{"upload_id": uploaded["upload_id"], "filename": uploaded["filename"]}],
        )


def test_filename_recovery_treats_session_upload_name_as_a_literal(isolated_storage):
    from data_agent.agent.context import AgentContext, use_agent_context
    from data_agent.session.workspace import Workspace
    from data_agent.tools.data_io import _resolve_source

    uploaded = (
        isolated_storage.sessions_resolved
        / "session-one"
        / "uploads"
        / ("a" * 32)
        / "[retention].csv"
    )
    uploaded.parent.mkdir(parents=True, exist_ok=True)
    uploaded.write_text("day,retention\n1,0.4\n", encoding="utf-8")
    context = AgentContext(session_id="session-one", workspace=Workspace())

    with use_agent_context(context):
        resolved = _resolve_source("[retention].csv")

    assert resolved == uploaded


def test_chat_rejects_a_forged_ticket_without_starting_the_model_turn(isolated_storage):
    from data_agent.agent.loop import AgentLoop
    from data_agent.web.app import create_app

    loop = AgentLoop(client=object(), session_id="forged-session")
    started = False

    def fake_stream(message: str):
        nonlocal started
        started = True
        yield {"type": "text_delta", "text": "must not run"}

    loop.stream_turn = fake_stream

    class Manager:
        @staticmethod
        def get_or_create(session_id=None, model_id=None):
            return loop

    app = create_app()
    app.config.update(TESTING=True, agent_manager=Manager())
    with app.test_client() as client:
        response = client.post(
            "/api/chat",
            json={
                "session_id": "forged-session",
                "message": "analyze",
                "uploads": [{"upload_id": "0" * 32, "filename": "retention.csv"}],
            },
        )

    assert response.status_code == 422
    assert response.headers["X-Data-Agent-Session-Id"] == "forged-session"
    assert "not available" in response.get_json()["error"]
    assert started is False


def test_list_files_skips_a_transient_entry_instead_of_failing_the_whole_listing(
    isolated_storage,
    monkeypatch,
):
    from data_agent.tools.file_ops import list_files
    import json

    root = isolated_storage.workspace_resolved
    stable = root / "inbox" / "stable.csv"
    transient = root / "knowledge" / "knowledge.sqlite3-shm"
    stable.parent.mkdir(parents=True, exist_ok=True)
    transient.parent.mkdir(parents=True, exist_ok=True)
    stable.write_text("a\n1\n", encoding="utf-8")
    transient.write_bytes(b"temporary")

    original_stat = Path.stat

    def flaky_stat(path, *args, **kwargs):
        if path == transient:
            raise FileNotFoundError(2, "transient file disappeared", str(path))
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", flaky_stat)
    result = list_files("**/*")

    assert "inbox\\stable.csv" in result or "inbox/stable.csv" in result
    catalogue = json.loads(result)
    assert catalogue["skipped_entries"] == 1 and catalogue["status"] == "partial"
    assert any(entry["path"] == "inbox/stable.csv" for entry in catalogue["entries"])
    assert "Error" not in result


def test_frontend_sends_structured_uploads_and_blocks_send_while_uploading():
    js = Path("src/data_agent/web/static/js/app.js").read_text(encoding="utf-8")
    html = Path("src/data_agent/web/templates/index.html").read_text(encoding="utf-8")

    assert "body.uploads" in js
    assert "upload_id" in js
    assert "this.isUploading" in js[js.index("async sendMessage"):js.index("async uploadFile")]
    assert "removeUploadedFile(fi)" in html
    remove_upload = js[js.index("async removeUploadedFile"):]
    assert "method: 'DELETE'" in remove_upload
    assert "if (!response.ok)" in remove_upload
    assert "this.uploadedFiles = this.uploadedFiles.filter" in remove_upload
    assert ':disabled="sessionReadOnly || isUploading || (!inputText.trim() && !uploadedFiles.length)"' in html


def test_first_party_web_assets_are_content_versioned(isolated_storage):
    from data_agent.web.app import create_app

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        html = client.get("/").get_data(as_text=True)

    assert "/static/js/app.js?v=" in html
    assert "/static/css/app.css?v=" in html


@pytest.mark.parametrize("relation",["new","replace"])
def test_structured_upload_mapping_uses_exact_user_alias_and_retains_old_version(isolated_storage,monkeypatch,relation):
    from data_agent.agent.loop import AgentLoop
    from data_agent.agent.context import use_agent_context
    from data_agent.web.app import create_app
    from data_agent.web.blueprints.uploads import bind_uploads_to_session, ingest_bound_uploads
    from data_agent.session.task_manager import task_manager
    from data_agent.session.workspace import workspace
    monkeypatch.setattr(task_manager,"_dir",isolated_storage.workspace_resolved/"tasks")
    loop=AgentLoop(client=object(),session_id="object_binding")
    app=create_app();app.config["TESTING"]=True
    with app.test_client() as client:
        if relation=="replace":
            old=_upload(client,"original.csv",b"amount\n10\n")
            bound=bind_uploads_to_session(loop.session_id,[old]);ingest_bound_uploads(loop,bound)
            with use_agent_context(loop.context):
                loop._bind_current_uploads("加载为 business",[{"upload_id":old["upload_id"],"dataset":"business","relation":"new","exact_span":"加载为 business"}])
                old_identity=workspace.get_data_identity("business")
        ticket=_upload(client,"not-a-version-heuristic.csv",b"amount\n20\n")
        bound=bind_uploads_to_session(loop.session_id,[ticket]);ingest_bound_uploads(loop,bound)
    text="这是同一业务对象新版" if relation=="replace" else "请加载为 business"
    with use_agent_context(loop.context):
        source=loop._current_uploads["uploads"][0]["dataset"]
        new_identity=workspace.get_data_identity(source)
        loop._bind_current_uploads(text,[{"upload_id":ticket["upload_id"],"dataset":"business","relation":relation,"exact_span":text}])
        assert workspace.get_data_identity("business")==new_identity
        assert workspace.get("business")["amount"].tolist()==[20]
        if relation=="replace":
            archived=[n for n,info in workspace.list_datasets().items() if info.get("metadata",{}).get("archived_from")=="business"]
            assert len(archived)==1 and workspace.get_data_identity(archived[0])==old_identity
            assert workspace.get(archived[0])["amount"].tolist()==[10]
    import json
    record=json.loads(bound[0].record_path.read_text(encoding="utf-8"))
    assert record["dataset_name"]=="business" and record["sha256"]==ticket["sha256"]


@pytest.mark.parametrize("fault",["foreign_ticket","ambiguous_replace","invented_alias","invalid_path","repeat_ticket","changed_bytes"])
def test_upload_mapping_failure_cannot_replace_data_or_ticket(isolated_storage,monkeypatch,fault):
    from copy import deepcopy
    from data_agent.agent.loop import AgentLoop
    from data_agent.agent.context import use_agent_context
    from data_agent.web.app import create_app
    from data_agent.web.blueprints.uploads import bind_uploads_to_session, ingest_bound_uploads
    from data_agent.session.task_manager import task_manager
    from data_agent.session.workspace import workspace
    monkeypatch.setattr(task_manager,"_dir",isolated_storage.workspace_resolved/"tasks")
    loop=AgentLoop(client=object(),session_id="reject_object_binding");app=create_app();app.config["TESTING"]=True
    with app.test_client() as client:
        ticket=_upload(client,"source.csv",b"amount\n20\n")
        bound=bind_uploads_to_session(loop.session_id,[ticket]);ingest_bound_uploads(loop,bound)
    text="加载为 business";row={"upload_id":ticket["upload_id"],"dataset":"business","relation":"new","exact_span":text};rows=[row]
    if fault=="foreign_ticket":row["upload_id"]="0"*32
    if fault=="ambiguous_replace":row["relation"]="replace"
    if fault=="invented_alias":row["dataset"]="not_user_named"
    if fault=="invalid_path":row["dataset"]="../business"
    if fault=="repeat_ticket":rows.append(deepcopy(row))
    if fault=="changed_bytes":bound[0].path.write_bytes(b"amount\n999\n")
    record=bound[0].record_path.read_bytes()
    with use_agent_context(loop.context):
        identities={n:workspace.get_data_identity(n) for n in workspace.list_datasets()}
        with pytest.raises(ValueError):loop._bind_current_uploads(text,rows)
        assert identities=={n:workspace.get_data_identity(n) for n in workspace.list_datasets()}
    assert record==bound[0].record_path.read_bytes()


@pytest.mark.parametrize("fault",["ticket","workspace_meta","analysis_state"])
def test_object_mapping_persistence_failure_restores_exact_namespace_metadata_and_tickets(isolated_storage,monkeypatch,fault):
    import pandas as pd
    from copy import deepcopy
    from data_agent.agent.loop import AgentLoop
    from data_agent.agent.context import use_agent_context
    from data_agent.web.app import create_app
    from data_agent.web.blueprints import uploads as adapter
    from data_agent.session.task_manager import task_manager
    from data_agent.session.history import _session_dir
    from data_agent.session.workspace import workspace,Workspace
    monkeypatch.setattr(task_manager,"_dir",isolated_storage.workspace_resolved/"tasks")
    loop=AgentLoop(client=object(),session_id="object_atomic_failure")
    with use_agent_context(loop.context):
        workspace.add("original__raw",pd.DataFrame({"amount":[10]}))
        workspace.derive("original__raw","business",workspace.get("original__raw"),"analysis copy")
        workspace.set_metadata("business","_source_path","original.csv")
    app=create_app()
    with app.test_client() as client:
        ticket=_upload(client,"replacement.csv",b"amount\n20\n")
        bound=adapter.bind_uploads_to_session(loop.session_id,[ticket]);adapter.ingest_bound_uploads(loop,bound)
    meta=_session_dir(loop.session_id)/"workspace_meta.json"
    meta.write_bytes(meta.read_bytes().replace(b"\r\n",b"\n"))
    before_meta=meta.read_bytes();before_ticket=bound[0].record_path.read_bytes()
    state_path=_session_dir(loop.session_id)/"analysis_state.json"
    before_state=state_path.read_bytes();before_contracts=deepcopy(loop.context.analysis_state.dataset_contracts)
    with use_agent_context(loop.context):
        before=deepcopy(workspace.list_datasets());log=deepcopy(workspace.get_transform_log())
        if fault=="ticket":
            original=adapter._update_ingestion_record
            def failing(*args,**kw):original(*args,**kw);raise OSError("after ticket write")
            monkeypatch.setattr(adapter,"_update_ingestion_record",failing)
        elif fault=="workspace_meta":
            original=Workspace.save_meta
            def failing(*args,**kw):original(*args,**kw);raise OSError("after metadata write")
            monkeypatch.setattr(Workspace,"save_meta",failing)
        else:
            original=loop.context.analysis_state.save
            def failing(*args,**kw):original(*args,**kw);raise OSError("after analysis state write")
            monkeypatch.setattr(loop.context.analysis_state,"save",failing)
        with pytest.raises(OSError):
            loop._bind_current_uploads("这是同一对象新版",[{"upload_id":ticket["upload_id"],"dataset":"business","relation":"replace","exact_span":"这是同一对象新版"}])
        assert workspace.list_datasets()==before
        assert workspace.get_transform_log()==log
    assert meta.read_bytes()==before_meta and bound[0].record_path.read_bytes()==before_ticket

    assert state_path.read_bytes()==before_state
    assert loop.context.analysis_state.dataset_contracts==before_contracts


@pytest.mark.parametrize("fault", [None, "foreign_span", "missing_span", "unmentioned_object"])
def test_recorded_m06_explicit_replacement_with_other_loaded_object(isolated_storage, monkeypatch, fault):
    """Original M06 input, actual HTTP tickets/ingestion and atomic object binding."""
    import json
    import pandas as pd
    from types import SimpleNamespace
    from data_agent.agent.loop import AgentLoop
    from data_agent.agent.context import use_agent_context
    from data_agent.web.app import create_app
    from data_agent.web.blueprints.uploads import bind_uploads_to_session, ingest_bound_uploads
    from data_agent.session.task_manager import task_manager
    from data_agent.session.workspace import workspace

    material = json.loads(Path("tests/fixtures/p5-contract-reset-20261009.json").read_text(encoding="utf-8"))["m06_explicit_replacement"]
    monkeypatch.setattr(task_manager, "_dir", isolated_storage.workspace_resolved / "tasks")
    loop = AgentLoop(client=object(), session_id="recorded_m06_object")
    loop._publication_turn_id = "offline_m06_replacement"
    app = create_app(); app.config["TESTING"] = True
    with app.test_client() as client:
        for name, content in [(material["other_object"], b"sales\n120\n"), (material["object"], b"incremental_revenue,coupon_cost,channel_cost\n110,14,10\n")]:
            initial = _upload(client, name + ".csv", content)
            ingest_bound_uploads(loop, bind_uploads_to_session(loop.session_id, [initial]))
            with use_agent_context(loop.context):
                loop._bind_current_uploads("加载为 " + name, [{"upload_id": initial["upload_id"], "dataset": name, "relation": "new", "exact_span": "加载为 " + name}])
        with use_agent_context(loop.context):
            original_id = workspace.get_data_identity(material["object"])
            other_id = workspace.get_data_identity(material["other_object"])
        ticket = _upload(client, material["filename"], material["csv"].encode("utf-8"))
        assert ticket["sha256"] == material["csv_sha256"]
        bound = bind_uploads_to_session(loop.session_id, [ticket])
        ingest_bound_uploads(loop, bound)
    user = material["user_input"]
    row = {"upload_id": ticket["upload_id"], "dataset": material["object"], "relation": "replace", "exact_span": user, "object_span": material["object"]}
    if fault == "foreign_span": row["object_span"] = material["filename"]
    if fault == "missing_span": row.pop("object_span")
    if fault == "unmentioned_object": row.update(dataset=material["other_object"], object_span=material["other_object"])
    ticket_before = bound[0].record_path.read_bytes()
    with use_agent_context(loop.context):
        source = loop._current_uploads["uploads"][0]["dataset"]
        replacement_id = workspace.get_data_identity(source)
        if fault in {"foreign_span", "unmentioned_object"}:
            with pytest.raises(ValueError): loop._bind_current_uploads(user, [row], SimpleNamespace())
        elif fault == "missing_span":
            candidate = loop._bind_current_uploads(user, [row], SimpleNamespace())
            assert candidate.resolution_params["confirmation_type"] == "file_scope"
            options = [json.loads(option.value)[0]["dataset"] for option in candidate.options]
            assert set(options) == {material["object"], material["other_object"]}
        else:
            assert loop._bind_current_uploads(user, [row], SimpleNamespace()) is None
            assert workspace.get_data_identity(material["object"]) == replacement_id != original_id
            assert workspace.get(material["object"])["incremental_revenue"].sum() == 120
            archives = [n for n, info in workspace.list_datasets().items() if info.get("metadata", {}).get("archived_from") == material["object"]]
            assert len(archives) == 1 and workspace.get_data_identity(archives[0]) == original_id
            assert workspace.get_data_identity(material["other_object"]) == other_id
            assert json.loads(bound[0].record_path.read_text(encoding="utf-8"))["dataset_name"] == material["object"]
        if fault:
            assert workspace.get_data_identity(material["object"]) == original_id
            assert workspace.get_data_identity(material["other_object"]) == other_id
            assert bound[0].record_path.read_bytes() == ticket_before


def test_s1_upload_alias_contract_requires_exact_current_identity(isolated_storage,monkeypatch):
    import json
    import pandas as pd
    from copy import deepcopy
    from data_agent.agent.loop import AgentLoop
    from data_agent.agent.context import use_agent_context
    from data_agent.web.app import create_app
    from data_agent.web.blueprints import uploads as adapter
    from data_agent.session.task_manager import task_manager
    from data_agent.tools import discover_tools
    discover_tools()
    from data_agent.tools.registry import registry
    from tests.test_trusted_publication_runtime import request
    monkeypatch.setattr(task_manager,"_dir",isolated_storage.workspace_resolved/"tasks")
    loop=AgentLoop(client=object(),session_id="s1_alias_contract")
    with create_app().test_client() as client:
        ticket=_upload(client,"original.csv",b"amount\n10\n20\n")
        bound=adapter.bind_uploads_to_session(loop.session_id,[ticket]);adapter.ingest_bound_uploads(loop,bound)
    with use_agent_context(loop.context):
        assert loop._bind_current_uploads("加载为business",[{"upload_id":ticket["upload_id"],"dataset":"business","relation":"new","exact_span":"加载为business"}]) is None
        request(loop,"统计business记录数",{"kind":"measurement","scope":{"datasets":["business"],"quantity":"rows"}})
        plan=deepcopy(loop.context.analysis_state.analysis_plan)
        response=registry.execute("record_analysis_plan",{"plan_json":plan})
        valid=response.data or json.loads(response.summary)
        assert "error" not in valid,valid
        loop.context.workspace.add("business",pd.DataFrame({"amount":[99]}))
        plan=deepcopy(loop.context.analysis_state.analysis_plan)
        plan["requirement_revision"]=loop.context.analysis_state.requirement_revision
        response=registry.execute("record_analysis_plan",{"plan_json":plan})
        invalid=response.data or json.loads(response.summary)
        assert invalid["error_type"]=="missing_dataset_contract",invalid


@pytest.mark.parametrize("fault",[None,"load_failure"])
def test_s2_new_upload_discovers_prior_objects_after_factual_task_finishes(isolated_storage,monkeypatch,fault):
    from data_agent.agent.loop import AgentLoop
    from data_agent.agent.context import use_agent_context
    from data_agent.web.app import create_app
    from data_agent.web.blueprints import uploads as adapter
    from data_agent.session.task_manager import task_manager
    from data_agent.session.workspace import workspace
    from tests.test_scoped_workspace import _stage3c0b_task
    monkeypatch.setattr(task_manager,"_dir",isolated_storage.workspace_resolved/"tasks")
    loop=AgentLoop(client=object(),session_id="s2_upload_after_compute")
    with create_app().test_client() as client:
        initial=_upload(client,"business.csv",b"date,amount\n2026-09-01,10\n2026-09-02,20\n2026-09-03,20\n")
        adapter.ingest_bound_uploads(loop,adapter.bind_uploads_to_session(loop.session_id,[initial]))
        with use_agent_context(loop.context):
            original=workspace.get_data_identity("business")
            before=set(workspace.list_datasets())
            _stage3c0b_task(task_manager,session_id=loop.session_id,datasets=["business"],mode="synthesis")
            assert loop.context.refresh_workspace_scope().phase=="synthesis"
            assert workspace.list_datasets()=={} and workspace.get("business") is None
        ticket=_upload(client,"business-v2.csv",b"date,amount\n2026-09-01,99\n2026-09-02,99\n2026-09-03,99\n")
        if fault:
            monkeypatch.setattr("data_agent.tools.data_io.load_data",lambda *a,**kw:"Error: injected actual ingestion failure")
        bound=adapter.bind_uploads_to_session(loop.session_id,[ticket])
        if fault:
            with pytest.raises(adapter.UploadIngestionError):adapter.ingest_bound_uploads(loop,bound)
            with use_agent_context(loop.context):
                assert workspace._publication_data_identity("business")==original
                assert all(workspace._publication_dataset_exists(n) for n in before)
                assert loop.context.refresh_workspace_scope().phase=="synthesis"
        else:
            adapter.ingest_bound_uploads(loop,bound)
            assert loop._current_uploads["prior_objects"]==["business"]
            with use_agent_context(loop.context):
                loop._bind_current_uploads("这是同一对象的新版本",[{"upload_id":ticket["upload_id"],"dataset":"business","relation":"replace","exact_span":"这是同一对象的新版本"}])
                assert workspace.get_data_identity("business")!=original
                assert workspace.get("business")["amount"].tolist()==[99,99,99]
                from data_agent.agent.artifact_refs import hydrate_refs
                state=loop.context.analysis_state
                assert state.active_scope["active_dataset"]=="business"
                source=next(r for r in state.dataset_contracts if r.get("host_aliases"))
                assert hydrate_refs([source])[0]["dataset"]=="business"
                route=next(r for r in state.route_proposals if r.get("host_aliases"))
                assert hydrate_refs([route])[0]["dataset"]=="business"


# S3 approved parameter contract and original atomic writer ownership.
from pathlib import Path
import json,io,pytest,pandas as pd
from tests.test_trusted_publication_semantics import engine
from tests.test_trusted_publication_runtime import _NativeProductModel
import os
UPLOAD_ATOMIC_E=Path(os.environ.get('DATA_AGENT_S3_UPLOAD_ATOMIC_EVIDENCE','tmp/s3-upload-atomic-20261014-r2/evidence-promoted'));UPLOAD_ATOMIC_E.mkdir(exist_ok=True)
def _save_upload_atomic_probe(n,d):(UPLOAD_ATOMIC_E/n).write_text(json.dumps(d,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
def _upload_atomic_root_at(tmp_path,length):
 base=tmp_path/'sessions';n=length-len(str(base.resolve()))-1;assert n>0;root=base/('x'*n);root.mkdir(parents=True);assert len(str(root.resolve()))==length;return root
@pytest.mark.parametrize('length',[140,156])
@pytest.mark.parametrize('route',['direct','binding','normal'])
def test_existing_destination_does_not_need_longer_atomic_path_s3_upload_atomic(engine,tmp_path,monkeypatch,length,route):
 from data_agent.web.blueprints import uploads
 from data_agent.web.app import create_app
 from data_agent.web.agent_manager import AgentManager
 from data_agent.session.history import load_session
 from data_agent.agent.publication.runtime import read_answer
 _,cfg=engine;root=_upload_atomic_root_at(tmp_path,length);monkeypatch.setattr(cfg,'sessions_dir',root);sid='long_bind_case';raw=b'amount\n10\n20\n30\n';record={'value':'preserve'}
 if route=='direct':
  parent=root/sid/'uploads'/('a'*32);parent.mkdir(parents=True);dest=parent/'upload.json';dest.write_text(json.dumps(record),encoding='utf-8');error=None
  try:uploads._write_json_atomic(dest,{'value':'new exact'})
  except OSError as exc:error={'type':type(exc).__name__,'message':str(exc)}
  actual=json.loads(dest.read_text(encoding='utf-8'));_save_upload_atomic_probe(route+str(length)+'.json',{'route':route,'root_length':length,'destination_length':len(str(dest.resolve())),'original_temp_length':len(str(dest.with_name('.upload.json.'+'b'*32+'.tmp').resolve())),'result':actual,'error':error,'provider_calls':0});assert error is None and actual=={'value':'new exact'};return
 content='加载上传数据并将其命名为experiment；报告当前真实记录数。';model=_NativeProductModel(content,'experiment','describe_dataset',{'name':'experiment'},[{'kind':'measurement','scope':{'datasets':['experiment'],'quantity':'rows'}}]);manager=AgentManager(client_factory=lambda **kw:model,auxiliary_client_factory=lambda:model);app=create_app();app.config['agent_manager']=manager
 with app.test_client() as h:
  response=h.post('/api/upload',data={'file':(io.BytesIO(raw),'experiment.csv')},content_type='multipart/form-data');ticket=response.get_json();assert response.status_code==200,ticket;model.ticket=ticket
  if route=='binding':
   error=None;bound=None
   try:bound=uploads.bind_uploads_to_session(sid,[ticket])
   except OSError as exc:error={'type':type(exc).__name__,'message':str(exc)}
   _save_upload_atomic_probe(route+str(length)+'.json',{'route':route,'root_length':length,'ticket':ticket,'error':error,'bound':[str(x.path) for x in bound] if bound else [],'provider_calls':0});assert error is None and len(bound)==1 and bound[0].path.read_bytes()==raw;return
  response=h.post('/api/chat',json={'session_id':sid,'message':content,'uploads':[ticket]});text=response.get_data(as_text=True);events=[(b.split('\n',1)[0][7:],json.loads(b.split('\ndata: ',1)[1])) for b in text.split('\n\n') if b.startswith('event:')];refresh=h.get('/api/sessions/'+sid).get_json()
 saved=load_session(sid);a=read_answer(sid,saved['messages'][-1]['answer_ref']) if saved and saved['messages'][-1].get('answer_ref') else None;_save_upload_atomic_probe(route+str(length)+'.json',{'route':route,'root_length':length,'ticket':ticket,'raw_hex':raw.hex(),'response_status':response.status_code,'response_text':text,'events':events,'saved':saved,'answer':a,'refresh':refresh,'session_dir':str(root/sid),'provider_calls':0});assert response.status_code==200 and a and a['requirement_outcomes'][0]['status']=='answered';ids={t['ref'] for t in a['render_trace'] if t['kind']=='claim' and t['disposition']=='accepted'};assert any(c['id'] in ids and c['value']==3 and c['target'].get('statistic')=='rows' for c in a['source_snapshot']['claims'])

@pytest.mark.parametrize('phase',['temporary','replace'])
def test_upload_atomic_failure_keeps_old_snapshot_and_no_residue_s3_upload_atomic(engine,tmp_path,monkeypatch,phase):
 from data_agent.web.blueprints import uploads
 dest=tmp_path/'upload.json';dest.write_bytes(b'{"old":true}');before=dest.read_bytes();original_write=Path.write_text;original_replace=Path.replace;fired=[]
 def write(p,*a,**kw):
  if p.parent==dest.parent and p!=dest and not fired and phase=='temporary':fired.append(phase);p.write_bytes(b'PARTIAL');raise OSError('INJECT_UPLOAD_ATOMIC')
  return original_write(p,*a,**kw)
 def replace(p,target):
  if Path(target)==dest and not fired and phase=='replace':fired.append(phase);raise OSError('INJECT_UPLOAD_ATOMIC')
  return original_replace(p,target)
 monkeypatch.setattr(Path,'write_text',write);monkeypatch.setattr(Path,'replace',replace)
 with pytest.raises(OSError,match='INJECT_UPLOAD_ATOMIC'):uploads._write_json_atomic(dest,{'new':True})
 residue=[p.name for p in dest.parent.glob('*.tmp')];_save_upload_atomic_probe('fault_'+phase+'.json',{'phase':phase,'fired':fired,'before_hex':before.hex(),'after_hex':dest.read_bytes().hex(),'residue':residue,'provider_calls':0});assert dest.read_bytes()==before and not residue
