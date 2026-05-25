import json
from pathlib import Path

import data_agent.config as config_module
from data_agent.config import AgentConfig
from data_agent.web.app import create_app


ROOT = Path(__file__).resolve().parents[1]


def _client(tmp_path: Path, monkeypatch):
    cfg = AgentConfig(WORKSPACE_DIR=tmp_path / "workspace", SESSIONS_DIR=tmp_path / "sessions")
    monkeypatch.setattr(config_module, "_config", cfg)
    return create_app().test_client(), cfg


def test_management_center_review_flow_api_contract(tmp_path, monkeypatch):
    client, cfg = _client(tmp_path, monkeypatch)
    session_dir = cfg.sessions_resolved / "review_flow"
    session_dir.mkdir(parents=True)
    (session_dir / "meta.json").write_text(
        json.dumps({"project_name": "game", "saved_at": "2026-05-25T10:00:00"}, ensure_ascii=False),
        encoding="utf-8",
    )
    (session_dir / "conversation.json").write_text(
        json.dumps(
            [{"role": "user", "content": "请记住：游戏留存分析默认先看次日留存，再看7日留存。"}],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    indexed = client.post("/api/management/evidence/index", json={"session_id": "review_flow"})
    assert indexed.status_code == 200

    extract = client.post("/api/management/memory/extract", json={"session_id": "review_flow"})
    assert extract.status_code == 200
    candidate = client.get("/api/management/memory?status=candidate").get_json()[0]

    assert candidate["reason"]
    assert candidate["source_evidence_ids"]
    assert candidate["dedup_key"]

    sources = client.get(f"/api/management/memory/{candidate['id']}/sources").get_json()
    assert sources["memory_id"] == candidate["id"]
    assert sources["sources"]

    edit = client.patch(
        f"/api/management/memory/{candidate['id']}",
        json={"review_note": "Reviewed from MVP quality flow", "needs_review": "false"},
    )
    assert edit.status_code == 200
    assert edit.get_json()["review_note"] == "Reviewed from MVP quality flow"
    assert edit.get_json()["needs_review"] is False


def test_management_center_static_contract_for_review_workflow():
    html = (ROOT / "src/data_agent/web/templates/index.html").read_text(encoding="utf-8")
    js = (ROOT / "src/data_agent/web/static/js/app.js").read_text(encoding="utf-8")

    assert "提取当前会话记忆" in html
    assert "查看来源" in html
    assert "需要审核" in html
    assert "review_note" in js
    assert "source_evidence_ids" in js
    assert "currentSessionId === '_pending_'" in js
