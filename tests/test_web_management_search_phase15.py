import json
from pathlib import Path

import data_agent.config as config_module
from data_agent.config import AgentConfig
from data_agent.web.app import create_app


def test_management_can_reindex_session_and_global_search(tmp_path: Path, monkeypatch):
    cfg = AgentConfig(WORKSPACE_DIR=tmp_path / "workspace", SESSIONS_DIR=tmp_path / "sessions")
    monkeypatch.setattr(config_module, "_config", cfg)
    app = create_app()
    client = app.test_client()

    session_dir = cfg.sessions_resolved / "s_global"
    session_dir.mkdir(parents=True)
    (session_dir / "meta.json").write_text(
        json.dumps({"project_name": "ecommerce", "saved_at": "2026-05-23T10:00:00"}, ensure_ascii=False),
        encoding="utf-8",
    )
    (session_dir / "conversation.json").write_text(
        json.dumps([{"role": "user", "content": "GMV 排除取消订单"}], ensure_ascii=False),
        encoding="utf-8",
    )

    index_resp = client.post("/api/management/evidence/index", json={"session_id": "s_global"})
    assert index_resp.status_code == 200
    assert index_resp.get_json()["indexed"] >= 1

    knowledge_resp = client.post(
        "/api/management/knowledge",
        json={"title": "GMV 口径", "domain": "ecommerce", "content": "GMV excludes canceled orders."},
    )
    assert knowledge_resp.status_code == 200

    memory_resp = client.post(
        "/api/management/memory",
        json={"text": "GMV excludes canceled orders.", "domain": "ecommerce"},
    )
    memory_id = memory_resp.get_json()["id"]
    client.post(f"/api/management/memory/{memory_id}/confirm")

    search = client.get("/api/management/search?q=GMV&project_id=ecommerce")
    assert search.status_code == 200
    payload = search.get_json()
    assert payload["knowledge"]
    assert payload["memory"]
    assert payload["evidence"]


def test_management_domains_lists_known_domains(tmp_path: Path, monkeypatch):
    cfg = AgentConfig(WORKSPACE_DIR=tmp_path / "workspace", SESSIONS_DIR=tmp_path / "sessions")
    monkeypatch.setattr(config_module, "_config", cfg)
    app = create_app()
    client = app.test_client()

    client.post(
        "/api/management/knowledge",
        json={"title": "留存率", "domain": "game", "content": "留存率定义"},
    )

    resp = client.get("/api/management/domains")

    assert resp.status_code == 200
    assert "game" in resp.get_json()["domains"]
