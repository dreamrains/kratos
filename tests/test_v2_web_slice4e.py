from __future__ import annotations

import json

import pandas as pd

import data_agent.config as config_module
from data_agent.config import AgentConfig
from data_agent.web.app import create_app


def _events(raw: str):
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


def _client(monkeypatch, tmp_path):
    workspace = tmp_path / "workspace"
    inbox = workspace / "inbox"
    inbox.mkdir(parents=True)
    pd.DataFrame({"sales": [10, 20, 30, 40]}).to_csv(inbox / "sales.csv", index=False)
    monkeypatch.setattr(
        config_module,
        "_config",
        AgentConfig(WORKSPACE_DIR=workspace, SESSIONS_DIR=tmp_path / "sessions"),
    )
    return create_app().test_client()


def test_v2_exploratory_python_sse_and_refresh(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    response = client.post(
        "/api/v2/exploratory-python",
        json={
            "session_id": "session_py_web",
            "turn_id": "turn_py_web",
            "filename": "sales.csv",
            "metric": "sales",
            "question": "销售额的总体水平如何？",
            "purpose": "检查中位数",
            "code": 'result = data["sales"].median()',
        },
    )
    events = _events(response.get_data(as_text=True))
    names = [name for name, _ in events]

    assert response.status_code == 200
    assert names.count("tool_started") == 2
    assert "supplemental_artifact_created" in names
    assert names[-1] == "turn_completed"
    refreshed = client.get(
        "/api/v2/sessions/session_py_web/turns/turn_py_web"
    ).get_json()
    assert refreshed["request_context"]["analysis_kind"] == "exploratory_python"
    assert len(refreshed["supplemental_artifacts"]) == 1
    assert refreshed["blocks"][-1]["calibration"] == "exploratory"


def test_v2_exploratory_endpoint_requires_explicit_purpose(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    response = client.post(
        "/api/v2/exploratory-python",
        json={
            "filename": "sales.csv",
            "metric": "sales",
            "question": "总体水平？",
            "purpose": "",
            "code": "result = len(data)",
        },
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "purpose and code are required"
