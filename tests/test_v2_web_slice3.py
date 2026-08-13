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


def _client(monkeypatch, tmp_path):
    workspace = tmp_path / "workspace"
    inbox = workspace / "inbox"
    inbox.mkdir(parents=True)
    monkeypatch.setattr(
        config_module,
        "_config",
        AgentConfig(WORKSPACE_DIR=workspace, SESSIONS_DIR=tmp_path / "sessions"),
    )
    return create_app().test_client(), inbox


def test_v2_iso_date_transform_completes_without_confirmation(monkeypatch, tmp_path):
    client, inbox = _client(monkeypatch, tmp_path)
    pd.DataFrame({"order_date": ["2026-01-02", "2026-02-03"]}).to_csv(
        inbox / "iso.csv", index=False
    )

    response = client.post(
        "/api/v2/transform-dates",
        json={
            "session_id": "session_iso_web",
            "turn_id": "turn_iso_web",
            "filename": "iso.csv",
            "date_column": "order_date",
            "question": "转换订单日期。",
        },
    )
    events = _events(response.get_data(as_text=True))
    names = [name for name, _ in events]

    assert response.status_code == 200
    assert "user_input_required" not in names
    assert names[-1] == "turn_completed"
    refreshed = client.get("/api/v2/sessions/session_iso_web/turns/turn_iso_web")
    assert refreshed.get_json()["status"] == "finalized"


def test_v2_ambiguous_date_persists_choice_then_resolves(monkeypatch, tmp_path):
    client, inbox = _client(monkeypatch, tmp_path)
    pd.DataFrame({"order_date": ["01/02/2026", "03/04/2026"]}).to_csv(
        inbox / "ambiguous.csv", index=False
    )

    first = client.post(
        "/api/v2/transform-dates",
        json={
            "session_id": "session_ambiguous_web",
            "turn_id": "turn_ambiguous_web",
            "filename": "ambiguous.csv",
            "date_column": "order_date",
            "question": "转换订单日期。",
        },
    )
    first_events = _events(first.get_data(as_text=True))
    required = next(data for name, data in first_events if name == "user_input_required")
    pending = client.get(
        "/api/v2/sessions/session_ambiguous_web/turns/turn_ambiguous_web"
    ).get_json()

    assert first_events[-1][0] == "user_input_required"
    assert pending["status"] == "draft"
    assert pending["transformation"]["status"] == "pending"
    assert pending["transformation"]["proposal"]["proposal_id"] == required["proposal_id"]

    resolved = client.post(
        "/api/v2/transform-dates/resolve",
        json={
            "session_id": "session_ambiguous_web",
            "turn_id": "turn_ambiguous_web",
            "proposal_id": required["proposal_id"],
            "option_key": "dmy",
            "expected_parent_version_id": required["parent_version_id"],
            "expected_parent_content_fingerprint": required[
                "parent_content_fingerprint"
            ],
        },
    )
    resolved_events = _events(resolved.get_data(as_text=True))
    refreshed = client.get(
        "/api/v2/sessions/session_ambiguous_web/turns/turn_ambiguous_web"
    ).get_json()

    assert resolved_events[-1][0] == "turn_completed"
    assert refreshed["status"] == "finalized"
    assert refreshed["transformation"]["status"] == "resolved"
    assert "日/月/年" in json.dumps(refreshed, ensure_ascii=False)


def test_v2_stale_transform_resolution_streams_failure(monkeypatch, tmp_path):
    client, inbox = _client(monkeypatch, tmp_path)
    pd.DataFrame({"order_date": ["01/02/2026", "03/04/2026"]}).to_csv(
        inbox / "ambiguous.csv", index=False
    )
    first = _events(
        client.post(
            "/api/v2/transform-dates",
            json={
                "session_id": "session_stale_web",
                "turn_id": "turn_stale_web",
                "filename": "ambiguous.csv",
                "date_column": "order_date",
                "question": "转换订单日期。",
            },
        ).get_data(as_text=True)
    )
    required = next(data for name, data in first if name == "user_input_required")

    response = client.post(
        "/api/v2/transform-dates/resolve",
        json={
            "session_id": "session_stale_web",
            "turn_id": "turn_stale_web",
            "proposal_id": required["proposal_id"],
            "option_key": "dmy",
            "expected_parent_version_id": "dv_stale",
            "expected_parent_content_fingerprint": "sha256:stale",
        },
    )
    events = _events(response.get_data(as_text=True))

    assert events[-1][0] == "turn_failed"
    assert events[-1][1]["error_code"] == "StaleTransformationProposal"
