import json

import pandas as pd

import data_agent.config as config_module
from data_agent.config import AgentConfig
from data_agent.web.app import create_app


def _events(raw: str) -> list[tuple[str, dict]]:
    parsed = []
    event_name = ""
    data = ""
    for line in raw.splitlines():
        if line.startswith("event: "):
            event_name = line.removeprefix("event: ")
        elif line.startswith("data: "):
            data = line.removeprefix("data: ")
        elif not line and event_name and data:
            parsed.append((event_name, json.loads(data)))
            event_name = ""
            data = ""
    return parsed


def test_v2_slice1_semantic_sse_and_refresh(monkeypatch, tmp_path):
    workspace = tmp_path / "workspace"
    sessions = tmp_path / "sessions"
    inbox = workspace / "inbox"
    inbox.mkdir(parents=True)
    pd.DataFrame({"sales": [100, 200]}).to_csv(inbox / "sales.csv", index=False)
    monkeypatch.setattr(
        config_module,
        "_config",
        AgentConfig(WORKSPACE_DIR=workspace, SESSIONS_DIR=sessions),
    )
    app = create_app()
    client = app.test_client()

    response = client.post(
        "/api/v2/describe",
        json={
            "session_id": "session_web",
            "turn_id": "turn_web",
            "filename": "sales.csv",
            "metric": "sales",
            "question": "平均销售额是多少？",
        },
    )

    assert response.status_code == 200
    events = _events(response.get_data(as_text=True))
    names = [name for name, _ in events]
    assert names[0] == "turn_started"
    assert "tool_started" in names
    assert "outcome_snapshot" in names
    assert names[-1] == "turn_completed"
    assert names.index("tool_started") < names.index("final_block_delta")
    assert not any(name == "turn_failed" for name in names)

    refreshed = client.get("/api/v2/sessions/session_web/turns/turn_web")
    assert refreshed.status_code == 200
    payload = refreshed.get_json()
    assert payload["status"] == "finalized"
    assert payload["blocks"][0]["block_type"] == "executive_answer"
    assert "150" in payload["blocks"][0]["narrative"]


def test_v2_failure_has_explicit_terminal_event(monkeypatch, tmp_path):
    monkeypatch.setattr(
        config_module,
        "_config",
        AgentConfig(WORKSPACE_DIR=tmp_path / "workspace", SESSIONS_DIR=tmp_path / "sessions"),
    )
    client = create_app().test_client()

    response = client.post(
        "/api/v2/describe",
        json={
            "session_id": "session_bad",
            "turn_id": "turn_bad",
            "filename": "missing.csv",
            "metric": "sales",
            "question": "平均销售额是多少？",
        },
    )
    events = _events(response.get_data(as_text=True))

    assert [name for name, _ in events] == ["turn_failed"]
    assert events[0][1]["status"] == "failed"
    assert events[0][1]["error_code"] == "FileNotFoundError"
