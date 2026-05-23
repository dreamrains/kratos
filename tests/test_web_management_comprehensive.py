"""Comprehensive tests for Web Management API - all endpoints."""

import json
from pathlib import Path

import data_agent.config as config_module
from data_agent.config import AgentConfig
from data_agent.web.app import create_app


def _make_client(tmp_path: Path, monkeypatch):
    cfg = AgentConfig(WORKSPACE_DIR=tmp_path / "workspace", SESSIONS_DIR=tmp_path / "sessions")
    monkeypatch.setattr(config_module, "_config", cfg)
    app = create_app()
    return app.test_client()


# ── Knowledge API ─────────────────────────────────────────────────────


class TestKnowledgeListAPI:
    def test_list_empty(self, tmp_path: Path, monkeypatch):
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/management/knowledge")
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_list_with_domain_filter(self, tmp_path: Path, monkeypatch):
        client = _make_client(tmp_path, monkeypatch)
        client.post("/api/management/knowledge", json={
            "title": "Ecom rule", "domain": "ecommerce", "content": "Rule",
        })
        client.post("/api/management/knowledge", json={
            "title": "General rule", "domain": "general", "content": "Rule",
        })

        resp = client.get("/api/management/knowledge?domain=ecommerce")
        items = resp.get_json()
        assert len(items) == 1
        assert items[0]["domain"] == "ecommerce"

    def test_list_with_status_filter(self, tmp_path: Path, monkeypatch):
        client = _make_client(tmp_path, monkeypatch)
        r = client.post("/api/management/knowledge", json={
            "title": "To deprecate", "domain": "general", "content": "Content",
        })
        item_id = r.get_json()["id"]
        client.post(f"/api/management/knowledge/{item_id}/deprecate")

        active = client.get("/api/management/knowledge?status=active")
        assert len(active.get_json()) == 0

        deprecated = client.get("/api/management/knowledge?status=deprecated")
        assert len(deprecated.get_json()) == 1


class TestKnowledgeCreateAPI:
    def test_create_returns_full_item(self, tmp_path: Path, monkeypatch):
        client = _make_client(tmp_path, monkeypatch)
        resp = client.post("/api/management/knowledge", json={
            "title": "Test knowledge",
            "domain": "ecommerce",
            "content": "Test content",
            "summary": "A test",
            "tags": ["test"],
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["title"] == "Test knowledge"
        assert data["domain"] == "ecommerce"
        assert data["content"] == "Test content"
        assert data["status"] == "active"
        assert data["tags"] == ["test"]
        assert data["version"] == 1

    def test_create_empty_title_rejected(self, tmp_path: Path, monkeypatch):
        client = _make_client(tmp_path, monkeypatch)
        resp = client.post("/api/management/knowledge", json={
            "title": "", "content": "Content",
        })
        assert resp.status_code == 400

    def test_create_empty_content_rejected(self, tmp_path: Path, monkeypatch):
        client = _make_client(tmp_path, monkeypatch)
        resp = client.post("/api/management/knowledge", json={
            "title": "Title", "content": "",
        })
        assert resp.status_code == 400

    def test_create_defaults_to_general_domain(self, tmp_path: Path, monkeypatch):
        client = _make_client(tmp_path, monkeypatch)
        resp = client.post("/api/management/knowledge", json={
            "title": "No domain", "content": "Content",
        })
        assert resp.get_json()["domain"] == "general"


class TestKnowledgeUpdateAPI:
    def test_update_content(self, tmp_path: Path, monkeypatch):
        client = _make_client(tmp_path, monkeypatch)
        r = client.post("/api/management/knowledge", json={
            "title": "Original", "domain": "general", "content": "Old",
        })
        item_id = r.get_json()["id"]

        resp = client.patch(f"/api/management/knowledge/{item_id}", json={
            "content": "Updated content",
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["content"] == "Updated content"
        assert data["version"] == 2

    def test_update_title_and_summary(self, tmp_path: Path, monkeypatch):
        client = _make_client(tmp_path, monkeypatch)
        r = client.post("/api/management/knowledge", json={
            "title": "Old title", "domain": "general", "content": "Content", "summary": "Old",
        })
        item_id = r.get_json()["id"]

        resp = client.patch(f"/api/management/knowledge/{item_id}", json={
            "title": "New title", "summary": "New summary",
        })
        data = resp.get_json()
        assert data["title"] == "New title"
        assert data["summary"] == "New summary"

    def test_update_nonexistent_returns_404(self, tmp_path: Path, monkeypatch):
        client = _make_client(tmp_path, monkeypatch)
        resp = client.patch("/api/management/knowledge/kn_nonexistent", json={"content": "x"})
        assert resp.status_code == 404


class TestKnowledgeDeprecateRestoreAPI:
    def test_deprecate_then_restore(self, tmp_path: Path, monkeypatch):
        client = _make_client(tmp_path, monkeypatch)
        r = client.post("/api/management/knowledge", json={
            "title": "Item", "domain": "general", "content": "Content",
        })
        item_id = r.get_json()["id"]

        dep_resp = client.post(f"/api/management/knowledge/{item_id}/deprecate")
        assert dep_resp.status_code == 200
        assert dep_resp.get_json()["status"] == "deprecated"

        restore_resp = client.post(f"/api/management/knowledge/{item_id}/restore")
        assert restore_resp.status_code == 200
        assert restore_resp.get_json()["status"] == "active"

    def test_deprecate_nonexistent_returns_404(self, tmp_path: Path, monkeypatch):
        client = _make_client(tmp_path, monkeypatch)
        resp = client.post("/api/management/knowledge/kn_nonexistent/deprecate")
        assert resp.status_code == 404

    def test_restore_nonexistent_returns_404(self, tmp_path: Path, monkeypatch):
        client = _make_client(tmp_path, monkeypatch)
        resp = client.post("/api/management/knowledge/kn_nonexistent/restore")
        assert resp.status_code == 404


class TestKnowledgeDeleteAPI:
    def test_delete_existing_item(self, tmp_path: Path, monkeypatch):
        client = _make_client(tmp_path, monkeypatch)
        r = client.post("/api/management/knowledge", json={
            "title": "Delete me", "domain": "general", "content": "Content",
        })
        item_id = r.get_json()["id"]

        resp = client.delete(f"/api/management/knowledge/{item_id}")
        assert resp.status_code == 200
        assert resp.get_json()["deleted"] is True

        list_resp = client.get("/api/management/knowledge")
        assert len(list_resp.get_json()) == 0

    def test_delete_nonexistent_returns_404(self, tmp_path: Path, monkeypatch):
        client = _make_client(tmp_path, monkeypatch)
        resp = client.delete("/api/management/knowledge/kn_nonexistent")
        assert resp.status_code == 404


class TestKnowledgeSearchAPI:
    def test_search_returns_matching_items(self, tmp_path: Path, monkeypatch):
        client = _make_client(tmp_path, monkeypatch)
        client.post("/api/management/knowledge", json={
            "title": "GMV", "domain": "ecommerce", "content": "GMV excludes canceled orders",
        })
        client.post("/api/management/knowledge", json={
            "title": "Revenue", "domain": "general", "content": "Revenue definition",
        })

        resp = client.get("/api/management/knowledge/search?q=GMV+canceled")
        assert resp.status_code == 200
        results = resp.get_json()
        assert len(results) == 1
        assert results[0]["title"] == "GMV"

    def test_search_no_match_returns_empty(self, tmp_path: Path, monkeypatch):
        client = _make_client(tmp_path, monkeypatch)
        client.post("/api/management/knowledge", json={
            "title": "Item", "domain": "general", "content": "Content",
        })
        resp = client.get("/api/management/knowledge/search?q=nonexistent")
        assert resp.get_json() == []


# ── Memory API ────────────────────────────────────────────────────────


class TestMemoryListAPI:
    def test_list_empty(self, tmp_path: Path, monkeypatch):
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/management/memory")
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_list_with_status_filter(self, tmp_path: Path, monkeypatch):
        client = _make_client(tmp_path, monkeypatch)
        r = client.post("/api/management/memory", json={
            "text": "Test memory", "confidence": 0.7,
        })
        memory_id = r.get_json()["id"]
        client.post(f"/api/management/memory/{memory_id}/confirm")

        candidates = client.get("/api/management/memory?status=candidate")
        confirmed = client.get("/api/management/memory?status=confirmed")
        assert len(candidates.get_json()) == 0
        assert len(confirmed.get_json()) == 1


class TestMemoryCreateAPI:
    def test_create_returns_full_item(self, tmp_path: Path, monkeypatch):
        client = _make_client(tmp_path, monkeypatch)
        resp = client.post("/api/management/memory", json={
            "text": "Prefer net revenue",
            "summary": "Net revenue preference",
            "memory_type": "domain_fact",
            "confidence": 0.75,
            "domain": "ecommerce",
            "tags": ["revenue"],
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["text"] == "Prefer net revenue"
        assert data["status"] == "candidate"
        assert data["confidence"] == 0.75
        assert data["domain"] == "ecommerce"

    def test_create_with_source_fields(self, tmp_path: Path, monkeypatch):
        client = _make_client(tmp_path, monkeypatch)
        resp = client.post("/api/management/memory", json={
            "text": "Test",
            "source_session_id": "s1",
            "source_message_ids": ["m1"],
            "project_id": "p1",
        })
        data = resp.get_json()
        assert data["source_session_id"] == "s1"
        assert data["project_id"] == "p1"

    def test_create_invalid_confidence_rejected(self, tmp_path: Path, monkeypatch):
        client = _make_client(tmp_path, monkeypatch)
        resp = client.post("/api/management/memory", json={
            "text": "Bad confidence", "confidence": 2.0,
        })
        assert resp.status_code == 400

    def test_create_invalid_memory_type_rejected(self, tmp_path: Path, monkeypatch):
        client = _make_client(tmp_path, monkeypatch)
        resp = client.post("/api/management/memory", json={
            "text": "Bad type", "memory_type": "invalid_type",
        })
        assert resp.status_code == 400


class TestMemoryConfirmRejectDeprecateAPI:
    def test_confirm_candidate(self, tmp_path: Path, monkeypatch):
        client = _make_client(tmp_path, monkeypatch)
        r = client.post("/api/management/memory", json={"text": "To confirm", "confidence": 0.7})
        memory_id = r.get_json()["id"]

        resp = client.post(f"/api/management/memory/{memory_id}/confirm")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "confirmed"

    def test_reject_candidate(self, tmp_path: Path, monkeypatch):
        client = _make_client(tmp_path, monkeypatch)
        r = client.post("/api/management/memory", json={"text": "To reject"})
        memory_id = r.get_json()["id"]

        resp = client.post(f"/api/management/memory/{memory_id}/reject")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "rejected"

    def test_deprecate_confirmed(self, tmp_path: Path, monkeypatch):
        client = _make_client(tmp_path, monkeypatch)
        r = client.post("/api/management/memory", json={"text": "To deprecate", "confidence": 0.7})
        memory_id = r.get_json()["id"]
        client.post(f"/api/management/memory/{memory_id}/confirm")

        resp = client.post(f"/api/management/memory/{memory_id}/deprecate")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "deprecated"

    def test_confirm_nonexistent_returns_404(self, tmp_path: Path, monkeypatch):
        client = _make_client(tmp_path, monkeypatch)
        resp = client.post("/api/management/memory/mem_nonexistent/confirm")
        assert resp.status_code == 404

    def test_reject_nonexistent_returns_404(self, tmp_path: Path, monkeypatch):
        client = _make_client(tmp_path, monkeypatch)
        resp = client.post("/api/management/memory/mem_nonexistent/reject")
        assert resp.status_code == 404


# ── Evidence API ──────────────────────────────────────────────────────


class TestEvidenceSearchAPI:
    def test_search_empty_returns_empty(self, tmp_path: Path, monkeypatch):
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/management/evidence/search?q=test")
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_search_after_indexing(self, tmp_path: Path, monkeypatch):
        cfg = AgentConfig(WORKSPACE_DIR=tmp_path / "workspace", SESSIONS_DIR=tmp_path / "sessions")
        monkeypatch.setattr(config_module, "_config", cfg)

        sessions_dir = tmp_path / "sessions"
        session_dir = sessions_dir / "s1"
        session_dir.mkdir(parents=True)
        (session_dir / "meta.json").write_text(
            json.dumps({"session_id": "s1", "project_name": "test"}),
        )
        (session_dir / "conversation.json").write_text(
            json.dumps([{"role": "user", "content": "Revenue analysis for Q1"}]),
        )

        from data_agent.knowledge.evidence import EvidenceStore
        EvidenceStore(cfg.knowledge_dir, sessions_dir=sessions_dir).index_session("s1")

        app = create_app()
        client = app.test_client()
        resp = client.get("/api/management/evidence/search?q=Revenue")
        assert resp.status_code == 200
        results = resp.get_json()
        assert len(results) == 1
        assert "Revenue" in results[0]["summary"]

    def test_search_with_project_filter(self, tmp_path: Path, monkeypatch):
        cfg = AgentConfig(WORKSPACE_DIR=tmp_path / "workspace", SESSIONS_DIR=tmp_path / "sessions")
        monkeypatch.setattr(config_module, "_config", cfg)

        sessions_dir = tmp_path / "sessions"
        session_dir = sessions_dir / "s1"
        session_dir.mkdir(parents=True)
        (session_dir / "meta.json").write_text(
            json.dumps({"session_id": "s1", "project_name": "alpha"}),
        )
        (session_dir / "conversation.json").write_text(
            json.dumps([{"role": "user", "content": "Revenue analysis"}]),
        )

        from data_agent.knowledge.evidence import EvidenceStore
        EvidenceStore(cfg.knowledge_dir, sessions_dir=sessions_dir).index_session("s1")

        app = create_app()
        client = app.test_client()

        right = client.get("/api/management/evidence/search?q=Revenue&project_id=alpha")
        assert len(right.get_json()) == 1

        wrong = client.get("/api/management/evidence/search?q=Revenue&project_id=wrong")
        assert wrong.get_json() == []
