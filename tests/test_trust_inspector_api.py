"""Current HTTP contract for the minimal Workbench projection."""

import json

from data_agent.config import get_config
from data_agent.session.task_manager import task_manager


def _use_tmp_state(tmp_path):
    cfg = get_config()
    old_sessions, old_tasks_dir, old_next_id = cfg.sessions_dir, task_manager._dir, task_manager._next_id_val
    cfg.sessions_dir, task_manager._dir = tmp_path / "sessions", tmp_path / "tasks"
    task_manager.reset_for_testing()
    return cfg, old_sessions, old_tasks_dir, old_next_id


def _restore_state(cfg, old_sessions, old_tasks_dir, old_next_id):
    cfg.sessions_dir, task_manager._dir, task_manager._next_id_val = old_sessions, old_tasks_dir, old_next_id


def _write_state(tmp_path, session_id, payload):
    directory = tmp_path / "sessions" / session_id
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "analysis_state.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_workbench_endpoint_returns_bounded_empty_contract(tmp_path):
    cfg, *previous = _use_tmp_state(tmp_path)
    try:
        from data_agent.web.app import create_app
        payload = create_app().test_client().get("/api/sessions/missing_session/trust").get_json()
        assert payload["status"] == "empty"
        assert payload["session_id"] == "missing_session"
        assert payload["workbench"]["verified_conclusions"] == []
        assert payload["workbench"]["verified_total"] == 0
        assert payload["workbench"]["pending_findings"] == []
    finally:
        _restore_state(cfg, *previous)


def test_workbench_endpoint_does_not_promote_annotation_reports(tmp_path):
    cfg, *previous = _use_tmp_state(tmp_path)
    session_id = "workbench_session"
    state_path = _write_state(tmp_path, session_id, {
        "session_id": session_id,
        "updated_at": "2026-07-07 10:00:00",
        "data_state": "data_loaded",
        "evidence_records": [{"id": "ev_sales", "claim": "Revenue declined.", "confidence": "high", "result_summary": "-10%", "dataset": "sales"}],
        "verification_reports": [],
        "route_proposals": [{"artifact_path": "sessions/private/route.json"}],
    })
    before = state_path.read_text(encoding="utf-8")
    try:
        from data_agent.agent.analysis_state import load_analysis_state
        from data_agent.web.app import create_app

        state = load_analysis_state(session_id)
        state.verification_reports = [{"passed_evidence_ids": ["ev_sales"], "evidence_fingerprint": 'd5bff43303205a55'}]
        state_path.write_text(json.dumps(state.to_dict(), ensure_ascii=False), encoding="utf-8")
        payload = create_app().test_client().get(f"/api/sessions/{session_id}/trust").get_json()

        assert payload["status"] == "ready"
        assert payload["workbench"]["verified_conclusions"] == []
        assert payload["workbench"]["verified_total"] == 0
        assert "artifact_path" not in json.dumps(payload)
        assert state_path.read_text(encoding="utf-8") != before
    finally:
        _restore_state(cfg, *previous)


def test_workbench_endpoint_does_not_project_scope_or_relationship_diagnostics(tmp_path):
    cfg, *previous = _use_tmp_state(tmp_path)
    try:
        from data_agent.web.app import create_app
        _write_state(tmp_path, "scope_contract", {"session_id": "scope_contract", "data_state": "data_loaded", "file_relationships": [{"relationship_id": "rel_orders_flow"}], "data_pool": [{"dataset": "orders"}]})
        payload = create_app().test_client().get("/api/sessions/scope_contract/trust").get_json()
        assert payload["workbench"]["verified_conclusions"] == []
        assert payload["workbench"]["verified_total"] == 0
        assert payload["workbench"]["pending_findings"] == []
        assert set(payload["workbench"]) == {"verified_conclusions", "verified_total", "pending_findings"}
    finally:
        _restore_state(cfg, *previous)


def test_analysis_state_endpoint_emits_strict_json_without_changing_raw_measurements(tmp_path):
    cfg, *previous = _use_tmp_state(tmp_path)
    sid = "state_nonfinite"
    try:
        path = _write_state(tmp_path, sid, {"session_id":sid, "evidence_records":[
            {"id":"ev_actual", "dataset":"orders", "measurements":[
                {"metric":"amount", "value":120},
                {"metric":"undefined_statistic", "value":float("nan")},
                {"metric":"unbounded_statistic", "value":float("inf")},
                {"metric":"negative_unbounded", "value":-float("inf")}
            ]}]})
        before = path.read_bytes()
        from data_agent.web.app import create_app
        response = create_app().test_client().get(f"/api/sessions/{sid}/analysis")
        def invalid_constant(value): raise AssertionError("nonstandard JSON constant: "+value)
        payload = json.loads(response.get_data(as_text=True), parse_constant=invalid_constant)
        assert response.status_code == 200
        assert [m["value"] for m in payload["state"]["evidence_records"][0]["measurements"]] == [120,None,None,None]
        assert payload["summary"]["evidence_records"] == 1
        assert path.read_bytes() == before
        projection = create_app().test_client().get(f"/api/sessions/{sid}/trust").get_json()
        assert projection["workbench"]["verified_conclusions"] == []
    finally:
        _restore_state(cfg, *previous)
