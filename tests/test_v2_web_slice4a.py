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


def _client(monkeypatch, tmp_path):
    workspace = tmp_path / "workspace"
    inbox = workspace / "inbox"
    inbox.mkdir(parents=True)
    index = np.arange(24, dtype=float)
    pd.DataFrame(
        {
            "unit_id": [f"u{i}" for i in range(48)],
            "channel": ["A"] * 24 + ["B"] * 24,
            "revenue": np.concatenate(
                [100 + np.sin(index), 110 + np.sin(index)]
            ),
        }
    ).to_csv(inbox / "groups.csv", index=False)
    monkeypatch.setattr(
        config_module,
        "_config",
        AgentConfig(WORKSPACE_DIR=workspace, SESSIONS_DIR=tmp_path / "sessions"),
    )
    return create_app().test_client()


def test_v2_group_comparison_sse_chart_recommendation_and_refresh(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    response = client.post(
        "/api/v2/group-comparison",
        json={
            "session_id": "session_group_web",
            "turn_id": "turn_group_web",
            "filename": "groups.csv",
            "metric": "revenue",
            "group": "channel",
            "analysis_unit": "unit_id",
            "question": "两组收入有何差异，应该采取什么行动？",
            "recommendation_intent": "act",
            "action_risk": "low",
            "reversible": True,
        },
    )
    events = _events(response.get_data(as_text=True))
    names = [name for name, _ in events]

    assert response.status_code == 200
    assert names[0] == "turn_started"
    assert "artifact_created" in names
    assert names[-1] == "turn_completed"
    refreshed = client.get(
        "/api/v2/sessions/session_group_web/turns/turn_group_web"
    ).get_json()
    chart_id = refreshed["artifacts"][0]["chart_id"]
    chart = client.get(
        f"/api/v2/sessions/session_group_web/artifacts/{chart_id}"
    )

    assert refreshed["request_context"]["analysis_kind"] == "group_comparison"
    assert refreshed["request_context"]["recommendation_mode"] == "investigative_next_step"
    assert refreshed["blocks"][0]["chart_refs"] == [chart_id]
    assert any(item["block_type"] == "next_investigation" for item in refreshed["blocks"])
    assert chart.status_code == 200
    assert "/static/js/plotly-3.5.0.min.js" in chart.get_data(as_text=True)


def test_v2_group_endpoint_rejects_non_boolean_reversibility(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    response = client.post(
        "/api/v2/group-comparison",
        json={
            "filename": "groups.csv",
            "metric": "revenue",
            "group": "channel",
            "analysis_unit": "unit_id",
            "question": "比较两组。",
            "recommendation_intent": "none",
            "action_risk": "low",
            "reversible": "true",
        },
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "reversible must be a boolean"
