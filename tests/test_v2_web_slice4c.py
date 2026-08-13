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
    index = np.arange(70, dtype=float)
    pd.DataFrame(
        {
            "date": pd.date_range("2026-01-01", periods=70, freq="D"),
            "sales": 100 + 2 * index + np.sin(index),
        }
    ).to_csv(inbox / "forecast.csv", index=False)
    monkeypatch.setattr(
        config_module,
        "_config",
        AgentConfig(WORKSPACE_DIR=workspace, SESSIONS_DIR=tmp_path / "sessions"),
    )
    return create_app().test_client()


def test_v2_forecast_sse_chart_recommendation_and_refresh(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    response = client.post(
        "/api/v2/forecast",
        json={
            "session_id": "session_forecast_web",
            "turn_id": "turn_forecast_web",
            "filename": "forecast.csv",
            "time_field": "date",
            "metric": "sales",
            "frequency": "daily",
            "aggregation": "sum",
            "horizon": 7,
            "question": "未来七天销售基线是多少，如何使用？",
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
        "/api/v2/sessions/session_forecast_web/turns/turn_forecast_web"
    ).get_json()
    chart_id = refreshed["artifacts"][0]["chart_id"]
    chart = client.get(f"/api/v2/sessions/session_forecast_web/artifacts/{chart_id}")
    rendered = json.dumps(refreshed["blocks"], ensure_ascii=False)

    assert refreshed["request_context"]["analysis_kind"] == "forecast"
    assert refreshed["request_context"]["horizon"] == "7"
    assert refreshed["request_context"]["recommendation_mode"] == "investigative_next_step"
    assert refreshed["blocks"][0]["chart_refs"] == [chart_id]
    assert "时间外" in rendered
    assert "经验预测区间" in rendered
    assert any(item["block_type"] == "next_investigation" for item in refreshed["blocks"])
    assert chart.status_code == 200
    assert "/static/js/plotly-3.5.0.min.js" in chart.get_data(as_text=True)


def test_v2_forecast_endpoint_rejects_non_integer_horizon(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    response = client.post(
        "/api/v2/forecast",
        json={
            "filename": "forecast.csv",
            "time_field": "date",
            "metric": "sales",
            "frequency": "daily",
            "aggregation": "sum",
            "horizon": "7",
            "question": "预测未来。",
        },
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "horizon must be an integer"

    out_of_range = client.post(
        "/api/v2/forecast",
        json={
            "filename": "forecast.csv",
            "time_field": "date",
            "metric": "sales",
            "frequency": "daily",
            "aggregation": "sum",
            "horizon": 31,
            "question": "预测未来。",
        },
    )

    assert out_of_range.status_code == 400
    assert out_of_range.get_json()["error"] == "horizon must be between 1 and 30"
