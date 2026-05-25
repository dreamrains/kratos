import json
from pathlib import Path

import data_agent.config as config_module
from data_agent.config import AgentConfig
from data_agent.web.app import create_app


def _client(tmp_path: Path, monkeypatch):
    cfg = AgentConfig(WORKSPACE_DIR=tmp_path / "workspace", SESSIONS_DIR=tmp_path / "sessions")
    monkeypatch.setattr(config_module, "_config", cfg)
    return create_app().test_client(), cfg


def _write_session(cfg: AgentConfig, session_id: str, content: str, project_name: str = "ecommerce") -> None:
    session_dir = cfg.sessions_resolved / session_id
    session_dir.mkdir(parents=True)
    (session_dir / "meta.json").write_text(
        json.dumps({"project_name": project_name, "saved_at": "2026-05-24T10:00:00"}, ensure_ascii=False),
        encoding="utf-8",
    )
    (session_dir / "conversation.json").write_text(
        json.dumps([{"role": "user", "content": content}], ensure_ascii=False),
        encoding="utf-8",
    )


def test_management_extract_memory_candidates_returns_review_metadata(tmp_path: Path, monkeypatch):
    client, cfg = _client(tmp_path, monkeypatch)
    _write_session(cfg, "s1", "Remember: GMV should exclude canceled orders.")
    indexed = client.post("/api/management/evidence/index", json={"session_id": "s1"})
    assert indexed.status_code == 200

    resp = client.post("/api/management/memory/extract", json={"session_id": "s1"})

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["scanned"] == 1
    assert payload["created"] >= 0
    assert payload["candidates"]
    assert payload["candidates"][0]["reason"]
    assert payload["candidates"][0]["source_evidence_ids"]


def test_management_extract_memory_candidates_validates_session_id(tmp_path: Path, monkeypatch):
    client, _cfg = _client(tmp_path, monkeypatch)

    resp = client.post("/api/management/memory/extract", json={})

    assert resp.status_code == 400
    assert resp.get_json()["error"] == "session_id is required"


def test_management_memory_needs_review_filter(tmp_path: Path, monkeypatch):
    client, _cfg = _client(tmp_path, monkeypatch)
    review = client.post(
        "/api/management/memory",
        json={"text": "GMV includes all orders.", "needs_review": True},
    ).get_json()
    client.post(
        "/api/management/memory",
        json={"text": "Use net revenue.", "needs_review": False},
    )

    filtered = client.get("/api/management/memory?needs_review=true")

    assert filtered.status_code == 200
    payload = filtered.get_json()
    assert [item["id"] for item in payload] == [review["id"]]
    assert payload[0]["needs_review"] is True


def test_management_memory_sources_returns_records_and_404(tmp_path: Path, monkeypatch):
    client, cfg = _client(tmp_path, monkeypatch)
    _write_session(cfg, "s2", "Remember: default to net revenue.")
    client.post("/api/management/evidence/index", json={"session_id": "s2"})
    created = client.post(
        "/api/management/memory",
        json={"text": "Use net revenue.", "source_evidence_ids": ["ev_s2_0"]},
    )
    memory_id = created.get_json()["id"]

    sources = client.get(f"/api/management/memory/{memory_id}/sources")
    missing = client.get("/api/management/memory/mem_missing/sources")

    assert sources.status_code == 200
    assert sources.get_json()["memory_id"] == memory_id
    assert sources.get_json()["sources"][0]["id"] == "ev_s2_0"
    assert missing.status_code == 404


def test_management_memory_serializes_review_metadata_on_create_update_and_list(tmp_path: Path, monkeypatch):
    client, _cfg = _client(tmp_path, monkeypatch)
    created = client.post(
        "/api/management/memory",
        json={
            "text": "GMV excludes canceled orders.",
            "reason": "User stated a metric rule.",
            "source_evidence_ids": ["ev_manual_0"],
            "needs_review": True,
            "review_note": "Check against old GMV rule.",
            "dedup_key": "domain_fact:ecommerce:gmv",
        },
    )
    memory_id = created.get_json()["id"]

    updated = client.patch(
        f"/api/management/memory/{memory_id}",
        json={
            "reason": "Updated reason.",
            "source_evidence_ids": ["ev_manual_1"],
            "needs_review": False,
            "review_note": "Reviewed.",
            "dedup_key": "domain_fact:ecommerce:gmv-reviewed",
        },
    )
    listed = client.get("/api/management/memory")

    assert created.status_code == 200
    assert created.get_json()["reason"] == "User stated a metric rule."
    assert created.get_json()["source_evidence_ids"] == ["ev_manual_0"]
    assert created.get_json()["needs_review"] is True
    assert created.get_json()["review_note"] == "Check against old GMV rule."
    assert created.get_json()["dedup_key"] == "domain_fact:ecommerce:gmv"
    assert updated.status_code == 200
    assert updated.get_json()["reason"] == "Updated reason."
    assert updated.get_json()["source_evidence_ids"] == ["ev_manual_1"]
    assert updated.get_json()["needs_review"] is False
    assert updated.get_json()["review_note"] == "Reviewed."
    assert updated.get_json()["dedup_key"] == "domain_fact:ecommerce:gmv-reviewed"
    assert listed.status_code == 200
    assert listed.get_json()[0]["dedup_key"] == "domain_fact:ecommerce:gmv-reviewed"


def test_management_memory_create_parses_string_false_review_values(tmp_path: Path, monkeypatch):
    client, _cfg = _client(tmp_path, monkeypatch)

    false_text = client.post(
        "/api/management/memory",
        json={"text": "Use net revenue.", "needs_review": "false"},
    )
    zero_text = client.post(
        "/api/management/memory",
        json={"text": "Use gross revenue.", "needs_review": "0"},
    )

    assert false_text.status_code == 200
    assert false_text.get_json()["needs_review"] is False
    assert zero_text.status_code == 200
    assert zero_text.get_json()["needs_review"] is False


def test_management_memory_update_parses_string_false_review_value(tmp_path: Path, monkeypatch):
    client, _cfg = _client(tmp_path, monkeypatch)
    created = client.post(
        "/api/management/memory",
        json={"text": "Review this rule.", "needs_review": True},
    )
    memory_id = created.get_json()["id"]

    updated = client.patch(
        f"/api/management/memory/{memory_id}",
        json={"needs_review": "false"},
    )

    assert updated.status_code == 200
    assert updated.get_json()["needs_review"] is False


def test_management_memory_rejects_invalid_review_boolean_values(tmp_path: Path, monkeypatch):
    client, _cfg = _client(tmp_path, monkeypatch)
    created = client.post("/api/management/memory", json={"text": "Review this rule."})
    memory_id = created.get_json()["id"]

    create = client.post(
        "/api/management/memory",
        json={"text": "Invalid create value.", "needs_review": "sometimes"},
    )
    update = client.patch(
        f"/api/management/memory/{memory_id}",
        json={"needs_review": "sometimes"},
    )
    query = client.get("/api/management/memory?needs_review=sometimes")

    assert create.status_code == 400
    assert "needs_review" in create.get_json()["error"]
    assert update.status_code == 400
    assert "needs_review" in update.get_json()["error"]
    assert query.status_code == 400
    assert "needs_review" in query.get_json()["error"]
