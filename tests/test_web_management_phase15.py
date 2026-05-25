from pathlib import Path

import data_agent.config as config_module
from data_agent.config import AgentConfig
from data_agent.web.app import create_app


def test_management_memory_edit_delete_promote(tmp_path: Path, monkeypatch):
    cfg = AgentConfig(WORKSPACE_DIR=tmp_path / "workspace", SESSIONS_DIR=tmp_path / "sessions")
    monkeypatch.setattr(config_module, "_config", cfg)
    app = create_app()
    client = app.test_client()

    create = client.post(
        "/api/management/memory",
        json={
            "text": "GMV excludes canceled orders.",
            "summary": "GMV rule",
            "domain": "ecommerce",
            "tags": ["gmv"],
        },
    )
    assert create.status_code == 200
    memory_id = create.get_json()["id"]

    edit = client.patch(
        f"/api/management/memory/{memory_id}",
        json={"text": "GMV excludes canceled and refunded orders.", "summary": "GMV updated"},
    )
    assert edit.status_code == 200
    assert "refunded" in edit.get_json()["text"]

    client.post(f"/api/management/memory/{memory_id}/confirm")
    promote = client.post(
        f"/api/management/memory/{memory_id}/promote",
        json={"title": "GMV 口径", "summary": "GMV excludes canceled and refunded orders."},
    )
    assert promote.status_code == 201
    payload = promote.get_json()
    assert payload["memory"]["status"] == "promoted"
    assert payload["knowledge"]["source"] == "memory_promotion"

    delete = client.delete(f"/api/management/memory/{memory_id}")
    assert delete.status_code == 409
