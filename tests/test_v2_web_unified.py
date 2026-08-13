from __future__ import annotations

import json

import numpy as np
import pandas as pd

import data_agent.config as config_module
from data_agent.config import AgentConfig
from data_agent.web.app import create_app
from data_agent.v2.execution_control import StopReceipt, StopRequestConflict
from data_agent.v2.models import EventType, ExecutionEvent
from data_agent.v2.store import V2FactStore
from data_agent.v2.steer import SteerStatus, SteerStore


def _events(raw: str):
    parsed = []
    name = ""
    data = ""
    for line in raw.splitlines():
        if line.startswith("event: "):
            name = line.removeprefix("event: ")
        elif line.startswith("data: "):
            data = line.removeprefix("data: ")
        elif not line and name and data:
            parsed.append((name, json.loads(data)))
            name = ""
            data = ""
    return parsed


def _client(monkeypatch, tmp_path):
    workspace = tmp_path / "workspace"
    inbox = workspace / "inbox"
    inbox.mkdir(parents=True)
    pd.DataFrame({"sales": [10, 20, 30]}).to_csv(inbox / "sales.csv", index=False)
    index = np.arange(70, dtype=float)
    channel = np.where(index % 2 == 0, "online", "store")
    pd.DataFrame(
        {
            "date": pd.date_range("2026-01-01", periods=70, freq="D"),
            "sales": 100 + 1.2 * index + np.where(channel == "store", 12, 0),
            "channel": channel,
            "unit_id": [f"u{i}" for i in range(70)],
        }
    ).to_csv(inbox / "combined.csv", index=False)
    pd.DataFrame({"order_date": ["01/02/2026", "03/04/2026"]}).to_csv(
        inbox / "ambiguous.csv", index=False
    )
    monkeypatch.setattr(
        config_module,
        "_config",
        AgentConfig(WORKSPACE_DIR=workspace, SESSIONS_DIR=tmp_path / "sessions"),
    )
    return create_app().test_client()


def test_unified_api_runs_descriptive_sse_and_restores_kind(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    response = client.post(
        "/api/v2/analyze",
        json={
            "analysis_kind": "descriptive",
            "session_id": "session_unified",
            "turn_id": "turn_unified",
            "filename": "sales.csv",
            "metric": "sales",
            "question": "平均销售额是多少？",
        },
    )
    events = _events(response.get_data(as_text=True))

    assert response.status_code == 200
    assert events[0][0] == "turn_started"
    assert events[-1][0] == "turn_completed"
    restored = client.get(
        "/api/v2/sessions/session_unified/turns/turn_unified"
    ).get_json()
    assert restored["request_context"]["analysis_kind"] == "descriptive"


def test_unified_api_rejects_invalid_kind_and_enums_before_sse(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    unknown = client.post("/api/v2/analyze", json={"analysis_kind": "magic"})
    invalid_frequency = client.post(
        "/api/v2/analyze",
        json={
            "analysis_kind": "time_trend",
            "filename": "sales.csv",
            "time_field": "date",
            "metric": "sales",
            "frequency": "yearly",
            "aggregation": "sum",
            "question": "趋势？",
        },
    )

    assert unknown.status_code == 400
    assert "unknown analysis_kind" in unknown.get_json()["error"]
    assert invalid_frequency.status_code == 400


def test_unified_api_requires_explicit_kind(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    response = client.post(
        "/api/v2/analyze",
        json={"filename": "sales.csv", "question": "帮我分析趋势。"},
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "analysis_kind is required"


def test_unified_api_supports_two_sequential_turns_in_one_session(
    monkeypatch, tmp_path
):
    client = _client(monkeypatch, tmp_path)
    common = {
        "analysis_kind": "descriptive",
        "session_id": "session_two_turns",
        "filename": "sales.csv",
        "metric": "sales",
    }

    first = client.post(
        "/api/v2/analyze",
        json={**common, "turn_id": "turn_one", "question": "第一轮平均值？"},
    )
    first_events = _events(first.get_data(as_text=True))
    second = client.post(
        "/api/v2/analyze",
        json={**common, "turn_id": "turn_two", "question": "第二轮平均值？"},
    )
    second_events = _events(second.get_data(as_text=True))

    assert first_events[-1][0] == "turn_completed"
    assert second_events[-1][0] == "turn_completed"
    assert client.get(
        "/api/v2/sessions/session_two_turns/turns/turn_one"
    ).get_json()["status"] == "finalized"
    assert client.get(
        "/api/v2/sessions/session_two_turns/turns/turn_two"
    ).get_json()["status"] == "finalized"
    store = V2FactStore(tmp_path / "sessions", "session_two_turns")
    assert len(store.read_commitments()) == 2


def test_unified_api_assembles_multiple_findings_and_charts(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    response = client.post(
        "/api/v2/analyze",
        json={
            "analysis_kind": "multi_finding_synthesis",
            "session_id": "session_multi_unified",
            "turn_id": "turn_multi_unified",
            "filename": "combined.csv",
            "time_field": "date",
            "metric": "sales",
            "frequency": "daily",
            "aggregation": "mean",
            "group": "channel",
            "analysis_unit": "unit_id",
            "question": "销售如何变化，不同渠道是否有差异？",
        },
    )
    events = _events(response.get_data(as_text=True))
    restored = client.get(
        "/api/v2/sessions/session_multi_unified/turns/turn_multi_unified"
    ).get_json()

    assert response.status_code == 200
    assert events[-1][0] == "turn_completed"
    assert len(restored["blocks"]) >= 4
    assert len(restored["artifacts"]) == 2
    assert restored["request_context"]["analysis_kind"] == "multi_finding_synthesis"


def test_unified_api_preserves_date_confirmation_and_resolution(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    first = client.post(
        "/api/v2/analyze",
        json={
            "analysis_kind": "date_transformation",
            "session_id": "session_date_unified",
            "turn_id": "turn_date_unified",
            "filename": "ambiguous.csv",
            "date_column": "order_date",
            "question": "转换订单日期。",
        },
    )
    first_events = _events(first.get_data(as_text=True))
    required = next(data for name, data in first_events if name == "user_input_required")

    resolved = client.post(
        "/api/v2/transform-dates/resolve",
        json={
            "session_id": "session_date_unified",
            "turn_id": "turn_date_unified",
            "proposal_id": required["proposal_id"],
            "option_key": "dmy",
            "expected_parent_version_id": required["parent_version_id"],
            "expected_parent_content_fingerprint": required[
                "parent_content_fingerprint"
            ],
        },
    )
    resolved_events = _events(resolved.get_data(as_text=True))
    restored = client.get(
        "/api/v2/sessions/session_date_unified/turns/turn_date_unified"
    ).get_json()

    assert first_events[-1][0] == "user_input_required"
    assert resolved_events[-1][0] == "turn_completed"
    assert restored["status"] == "finalized"
    assert restored["transformation"]["status"] == "resolved"
    assert restored["request_context"]["analysis_kind"] == "date_transformation"


def test_unified_stop_endpoint_returns_only_after_durable_receipt(
    monkeypatch, tmp_path
):
    client = _client(monkeypatch, tmp_path)

    class StubRegistry:
        def request_stop(self, session_id, turn_id):
            assert session_id == "session_stop_api"
            assert turn_id == "turn_stop_api"
            return StopReceipt(
                status="interrupted",
                session_id=session_id,
                turn_id=turn_id,
                run_id="run_stop_api",
                commitment_ids=("commitment_stop_api",),
            )

    import data_agent.web.blueprints.v2 as v2_module

    monkeypatch.setattr(v2_module, "ACTIVE_V2_RUNS", StubRegistry())
    response = client.post(
        "/api/v2/runs/stop",
        json={"session_id": "session_stop_api", "turn_id": "turn_stop_api"},
    )

    assert response.status_code == 202
    assert response.get_json()["status"] == "interrupted"


def test_unified_stop_is_idempotent_after_worker_unregisters(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    store = V2FactStore(tmp_path / "sessions", "session_stopped")
    store.request_turn_interrupt("turn_stopped", "run_stopped")
    store.append_event(
        ExecutionEvent(
            event_id="event_stopped",
            run_id="run_stopped",
            commitment_id="commitment_stopped",
            event_type=EventType.USER_INTERRUPTED,
        )
    )
    store.write_turn_blocks("turn_stopped", [], status="interrupted")

    class InactiveRegistry:
        def request_stop(self, session_id, turn_id):
            raise StopRequestConflict("run is not active")

    import data_agent.web.blueprints.v2 as v2_module

    monkeypatch.setattr(v2_module, "ACTIVE_V2_RUNS", InactiveRegistry())
    response = client.post(
        "/api/v2/runs/stop",
        json={"session_id": "session_stopped", "turn_id": "turn_stopped"},
    )

    assert response.status_code == 202
    assert response.get_json() == {
        "status": "interrupted",
        "session_id": "session_stopped",
        "turn_id": "turn_stopped",
        "run_id": "run_stopped",
        "commitment_ids": ["commitment_stopped"],
    }


def test_unified_steer_api_persists_through_active_registry(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    steers = SteerStore(tmp_path / "sessions", "session_steer_api")

    class StubRegistry:
        def request_steer(
            self,
            session_id,
            turn_id,
            *,
            expected_run_id,
            client_request_id,
            message,
        ):
            assert session_id == "session_steer_api"
            assert turn_id == "turn_steer_api"
            assert expected_run_id == "run_steer_api"
            return steers.enqueue(
                source_turn_id=turn_id,
                source_run_id=expected_run_id,
                client_request_id=client_request_id,
                message=message,
                resume_payload={
                    "analysis_kind": "descriptive",
                    "filename": "sales.csv",
                    "metric": "sales",
                    "question": "原问题",
                },
            )

    import data_agent.web.blueprints.v2 as v2_module

    monkeypatch.setattr(v2_module, "ACTIVE_V2_RUNS", StubRegistry())
    response = client.post(
        "/api/v2/runs/steer",
        json={
            "session_id": "session_steer_api",
            "turn_id": "turn_steer_api",
            "expected_run_id": "run_steer_api",
            "client_request_id": "client_steer_api",
            "message": "下一轮看中位数",
        },
    )

    assert response.status_code == 202
    assert response.get_json()["status"] == "queued"
    assert steers.queued_for_run("run_steer_api") is not None


def test_unified_steer_consumption_uses_frozen_server_payload_and_projects_history(
    monkeypatch, tmp_path
):
    client = _client(monkeypatch, tmp_path)
    sessions_root = tmp_path / "sessions"
    session_id = "session_steer_consume"
    source_turn_id = "turn_steer_source"
    target_turn_id = "turn_steer_target"
    V2FactStore(sessions_root, session_id).write_turn_blocks(
        source_turn_id,
        [],
        status="finalized",
        request_context={
            "analysis_kind": "descriptive",
            "filename": "sales.csv",
            "metric": "sales",
            "question": "原问题",
        },
    )
    steers = SteerStore(sessions_root, session_id)
    queued = steers.enqueue(
        source_turn_id=source_turn_id,
        source_run_id="run_steer_source",
        client_request_id="client_steer_consume",
        message="下一轮回答新的问题",
        resume_payload={
            "analysis_kind": "descriptive",
            "filename": "sales.csv",
            "metric": "sales",
            "question": "原问题",
        },
    )

    response = client.post(
        "/api/v2/analyze",
        json={
            "session_id": session_id,
            "turn_id": target_turn_id,
            "steer_id": queued.steer_id,
            "analysis_kind": "magic",
            "metric": "missing_metric",
            "question": "不得信任消费时 DOM",
        },
    )
    events = _events(response.get_data(as_text=True))
    target = client.get(
        f"/api/v2/sessions/{session_id}/turns/{target_turn_id}"
    ).get_json()
    source = client.get(
        f"/api/v2/sessions/{session_id}/turns/{source_turn_id}"
    ).get_json()

    assert response.status_code == 200
    assert events[-1][0] == "turn_completed"
    assert target["request_context"]["analysis_kind"] == "descriptive"
    assert target["request_context"]["metric"] == "sales"
    assert target["request_context"]["question"] == "下一轮回答新的问题"
    assert source["steers"][0]["status"] == "consumed"
    assert source["steers"][0]["target_turn_id"] == target_turn_id
    assert steers.get(queued.steer_id).status is SteerStatus.CONSUMED


def test_unified_steer_retry_is_idempotent_after_active_worker_unregisters(
    monkeypatch, tmp_path
):
    client = _client(monkeypatch, tmp_path)
    steers = SteerStore(tmp_path / "sessions", "session_steer_retry")
    queued = steers.enqueue(
        source_turn_id="turn_steer_retry",
        source_run_id="run_steer_retry",
        client_request_id="client_steer_retry",
        message="持久化后的重试",
        resume_payload={"analysis_kind": "descriptive"},
    )

    class InactiveRegistry:
        def request_steer(self, *args, **kwargs):
            raise StopRequestConflict("run is not active")

    import data_agent.web.blueprints.v2 as v2_module

    monkeypatch.setattr(v2_module, "ACTIVE_V2_RUNS", InactiveRegistry())
    response = client.post(
        "/api/v2/runs/steer",
        json={
            "session_id": "session_steer_retry",
            "turn_id": "turn_steer_retry",
            "expected_run_id": "run_steer_retry",
            "client_request_id": "client_steer_retry",
            "message": "持久化后的重试",
        },
    )

    assert response.status_code == 202
    assert response.get_json()["steer_id"] == queued.steer_id
