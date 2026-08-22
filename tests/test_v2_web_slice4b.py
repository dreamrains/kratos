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
    dates = pd.date_range("2026-01-01", periods=42, freq="D")
    weekday = np.array([0, 2, 3, 4, 5, -3, -5], dtype=float)
    pd.DataFrame(
        {
            "date": dates,
            "sales": 100 + 1.8 * np.arange(42) + weekday[dates.dayofweek],
        }
    ).to_csv(inbox / "daily.csv", index=False)
    monkeypatch.setattr(
        config_module,
        "_config",
        AgentConfig(WORKSPACE_DIR=workspace, SESSIONS_DIR=tmp_path / "sessions"),
    )
    return create_app().test_client()


def test_v2_time_trend_sse_chart_recommendation_and_refresh(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    response = client.post(
        "/api/v2/time-trend",
        json={
            "session_id": "session_time_web",
            "turn_id": "turn_time_web",
            "filename": "daily.csv",
            "time_field": "date",
            "metric": "sales",
            "frequency": "daily",
            "aggregation": "sum",
            "question": "历史销售是否有趋势，接下来应该怎么做？",
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
        "/api/v2/sessions/session_time_web/turns/turn_time_web"
    ).get_json()
    chart_id = refreshed["artifacts"][0]["chart_id"]
    chart = client.get(f"/api/v2/sessions/session_time_web/artifacts/{chart_id}")
    answer_text = json.dumps(refreshed["blocks"], ensure_ascii=False)

    assert refreshed["request_context"]["analysis_kind"] == "time_trend"
    assert refreshed["request_context"]["frequency"] == "daily"
    assert refreshed["request_context"]["aggregation"] == "sum"
    assert refreshed["request_context"]["recommendation_mode"] == "investigative_next_step"
    assert refreshed["blocks"][0]["chart_refs"] == [chart_id]
    assert "不是未来预测" in answer_text
    assert "HAC" in answer_text
    assert any(item["block_type"] == "next_investigation" for item in refreshed["blocks"])
    assert chart.status_code == 200
    assert "/static/js/plotly-3.5.0.min.js" in chart.get_data(as_text=True)


def test_v2_time_endpoint_rejects_invalid_controls(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    base = {
        "filename": "daily.csv",
        "time_field": "date",
        "metric": "sales",
        "frequency": "daily",
        "aggregation": "sum",
        "question": "是否有趋势？",
        "recommendation_intent": "none",
        "action_risk": "low",
        "reversible": True,
    }

    invalid_frequency = client.post(
        "/api/v2/time-trend", json={**base, "frequency": "quarterly"}
    )
    invalid_reversible = client.post(
        "/api/v2/time-trend", json={**base, "reversible": "true"}
    )

    assert invalid_frequency.status_code == 400
    assert invalid_reversible.status_code == 400
    assert invalid_reversible.get_json()["error"] == "reversible must be a boolean"
