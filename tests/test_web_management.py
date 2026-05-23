from pathlib import Path

import data_agent.config as config_module
from data_agent.config import AgentConfig
from data_agent.web.app import create_app


def test_management_knowledge_and_memory_api(tmp_path: Path, monkeypatch):
    cfg = AgentConfig(WORKSPACE_DIR=tmp_path / "workspace", SESSIONS_DIR=tmp_path / "sessions")
    monkeypatch.setattr(config_module, "_config", cfg)
    app = create_app()
    client = app.test_client()

    response = client.post(
        "/api/management/knowledge",
        json={
            "title": "GMV definition",
            "domain": "ecommerce",
            "content": "GMV excludes canceled orders.",
            "summary": "GMV rule",
            "tags": ["metric"],
        },
    )
    assert response.status_code == 200
    item_id = response.get_json()["id"]

    response = client.get("/api/management/knowledge/search?q=canceled&domain=ecommerce")
    assert response.status_code == 200
    assert response.get_json()[0]["id"] == item_id

    response = client.post(
        "/api/management/memory",
        json={
            "text": "Use net revenue.",
            "summary": "Net revenue preference.",
            "memory_type": "domain_fact",
            "confidence": 0.7,
            "domain": "ecommerce",
        },
    )
    assert response.status_code == 200
    memory_id = response.get_json()["id"]

    response = client.post(f"/api/management/memory/{memory_id}/confirm")
    assert response.status_code == 200
    assert response.get_json()["status"] == "confirmed"


def test_management_api_validates_required_fields(tmp_path: Path, monkeypatch):
    cfg = AgentConfig(WORKSPACE_DIR=tmp_path / "workspace", SESSIONS_DIR=tmp_path / "sessions")
    monkeypatch.setattr(config_module, "_config", cfg)
    app = create_app()
    client = app.test_client()

    response = client.post("/api/management/knowledge", json={"title": "Missing content"})
    assert response.status_code == 400
    assert "error" in response.get_json()

    response = client.post("/api/management/memory", json={"summary": "Missing text"})
    assert response.status_code == 400
    assert "error" in response.get_json()

    response = client.get("/api/management/memory?status=unknown")
    assert response.status_code == 400
    assert "error" in response.get_json()
