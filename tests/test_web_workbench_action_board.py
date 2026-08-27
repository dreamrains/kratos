"""HTTP contract: the trust endpoint serves verified conclusions only."""

import json

from data_agent.web.app import create_app


def _seed_session(tmp_path, session_id, messages):
    sdir = tmp_path / "sessions" / session_id
    sdir.mkdir(parents=True, exist_ok=True)
    (sdir / "meta.json").write_text(json.dumps({"project_name": "p"}, ensure_ascii=False), encoding="utf-8")
    (sdir / "conversation.jsonl").write_text(
        "".join(json.dumps(m, ensure_ascii=False) + "\n" for m in messages),
        encoding="utf-8",
    )
    # minimal analysis_state.json so the endpoint loads a non-None state
    state = {
        "session_id": session_id,
        "evidence_records": [
            {"id": "ev_income_down", "claim": "收入下降", "confidence": "high", "dataset": "d", "result_summary": "-10%", "limitations": []},
        ],
        "verification_reports": [{"overall_status": "pass", "passed_evidence_ids": ["ev_income_down"]}],
        "data_understanding_bundles": [],
        "route_proposals": [],
        "file_relationships": [],
        "data_state": "data_loaded",
    }
    (sdir / "analysis_state.json").write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


def test_trust_endpoint_returns_only_verified_conclusions(tmp_path, monkeypatch):
    from data_agent import config
    from data_agent.config import AgentConfig

    monkeypatch.setattr(config, "_config", AgentConfig(SESSIONS_DIR=tmp_path / "sessions"))
    seeded_answer = "## 结论\n\n收入下降\n- 复购减弱"
    _seed_session(tmp_path, "s1", [
        {"role": "user", "content": "问"},
        {"role": "assistant", "content": seeded_answer},
    ])

    client = create_app().test_client()
    resp = client.get("/api/sessions/s1/trust")
    assert resp.status_code == 200
    data = resp.get_json()
    workbench = data["workbench"]
    assert set(workbench) == {"verified_conclusions"}
    assert workbench["verified_conclusions"] == []
    assert seeded_answer not in json.dumps(workbench, ensure_ascii=False)
