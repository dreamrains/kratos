import json

import numpy as np
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


def test_v2_factor_semantic_sse_and_refresh(monkeypatch, tmp_path):
    workspace = tmp_path / "workspace"
    sessions = tmp_path / "sessions"
    inbox = workspace / "inbox"
    inbox.mkdir(parents=True)
    index = np.arange(48, dtype=float)
    marketing = ((index * 7) % 31) + 10
    service = ((index * 11) % 23) + 60
    pd.DataFrame(
        {
            "unit_id": [f"u{i:03d}" for i in range(48)],
            "target": 0.8 * marketing + 0.35 * service + np.sin(index * 1.7) * 3,
            "marketing": marketing,
            "service": service,
            "noise": np.cos(index * 0.9),
        }
    ).to_csv(inbox / "factors.csv", index=False)
    monkeypatch.setattr(
        config_module,
        "_config",
        AgentConfig(WORKSPACE_DIR=workspace, SESSIONS_DIR=sessions),
    )
    client = create_app().test_client()

    response = client.post(
        "/api/v2/factors",
        json={
            "session_id": "session_factor_web",
            "turn_id": "turn_factor_web",
            "filename": "factors.csv",
            "target": "target",
            "features": ["marketing", "service", "noise"],
            "analysis_unit": "unit_id",
            "time_field": "",
            "question": "哪些因素与 target 存在可靠关系？",
        },
    )
    events = _events(response.get_data(as_text=True))
    names = [name for name, _ in events]

    assert response.status_code == 200
    assert names[0] == "turn_started"
    assert "tool_started" in names
    assert "artifact_created" in names
    assert names[-1] == "turn_completed"
    assert names.index("tool_started") < names.index("final_block_delta")

    refreshed = client.get(
        "/api/v2/sessions/session_factor_web/turns/turn_factor_web"
    )
    payload = refreshed.get_json()
    chart_id = payload["artifacts"][0]["chart_id"]
    chart = client.get(
        f"/api/v2/sessions/session_factor_web/artifacts/{chart_id}"
    )

    assert refreshed.status_code == 200
    assert payload["request_context"]["analysis_kind"] == "factor_relationship"
    assert payload["request_context"]["target"] == "target"
    assert payload["blocks"][0]["chart_refs"] == [chart_id]
    assert chart.status_code == 200
    assert "/static/js/plotly-3.5.0.min.js" in chart.get_data(as_text=True)


def test_v2_factor_endpoint_rejects_string_features(monkeypatch, tmp_path):
    monkeypatch.setattr(
        config_module,
        "_config",
        AgentConfig(WORKSPACE_DIR=tmp_path / "workspace", SESSIONS_DIR=tmp_path / "sessions"),
    )
    response = create_app().test_client().post(
        "/api/v2/factors",
        json={
            "filename": "factors.csv",
            "target": "target",
            "features": "marketing,service",
            "analysis_unit": "unit_id",
            "question": "哪些因素有关？",
        },
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "features must be a JSON array"
