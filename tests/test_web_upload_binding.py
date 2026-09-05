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
    assert "Skipped 1 transient or inaccessible entry" in result
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
    assert ':disabled="isUploading || (!inputText.trim() && !uploadedFiles.length)"' in html


def test_first_party_web_assets_are_content_versioned(isolated_storage):
    from data_agent.web.app import create_app

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        html = client.get("/").get_data(as_text=True)

    assert "/static/js/app.js?v=" in html
    assert "/static/css/app.css?v=" in html
