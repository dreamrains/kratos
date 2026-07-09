import json

from data_agent.config import get_config
from data_agent.session.task_manager import task_manager


def _use_tmp_state(tmp_path):
    cfg = get_config()
    old_sessions = cfg.sessions_dir
    old_tasks_dir = task_manager._dir
    old_next_id = task_manager._next_id_val
    cfg.sessions_dir = tmp_path / "sessions"
    task_manager._dir = tmp_path / "tasks"
    task_manager.reset_for_testing()
    return cfg, old_sessions, old_tasks_dir, old_next_id


def _restore_state(cfg, old_sessions, old_tasks_dir, old_next_id):
    cfg.sessions_dir = old_sessions
    task_manager._dir = old_tasks_dir
    task_manager._next_id_val = old_next_id


def _write_state(tmp_path, session_id, payload):
    state_dir = tmp_path / "sessions" / session_id
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / "analysis_state.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def test_workbench_endpoint_returns_bounded_empty_contract(tmp_path):
    cfg, old_sessions, old_tasks_dir, old_next_id = _use_tmp_state(tmp_path)
    try:
        from data_agent.web.app import create_app

        payload = create_app().test_client().get(
            "/api/sessions/missing_session/trust"
        ).get_json()

        assert set(payload) == {"status", "session_id", "updated_at", "workbench"}
        assert payload["status"] == "empty"
        assert payload["session_id"] == "missing_session"
        assert set(payload["workbench"]) == {"action_board", "multifile_analysis", "details", "full_answer"}
    finally:
        _restore_state(cfg, old_sessions, old_tasks_dir, old_next_id)


def test_workbench_endpoint_returns_current_analysis_without_mutating_state(tmp_path):
    cfg, old_sessions, old_tasks_dir, old_next_id = _use_tmp_state(tmp_path)
    session_id = "workbench_session"
    state_path = _write_state(tmp_path, session_id, {
        "session_id": session_id,
        "updated_at": "2026-07-07 10:00:00",
        "data_state": "data_loaded",
        "active_scope": {"active_dataset": "sales", "active_mode": "data_loaded"},
        "dataset_contracts": [{
            "id": "duc_sales",
            "dataset": "sales",
            "quality_status": "ready",
            "field_roles": {"date": ["date"], "metrics": ["revenue"]},
        }],
        "route_proposals": [{
            "id": "route_trend",
            "dataset": "sales",
            "direction": "trend",
            "label": "Revenue trend",
            "evidence_requirements": ["daily revenue"],
            "artifact_path": "sessions/private/route.json",
        }],
        "verification_reports": [{
            "overall_status": "pass",
            "claim_count": 2,
            "failed_count": 0,
            "evidence_signature": "private-signature",
        }],
    })
    before = state_path.read_text(encoding="utf-8")
    try:
        from data_agent.web.app import create_app

        response = create_app().test_client().get(f"/api/sessions/{session_id}/trust")
        payload = response.get_json()

        assert response.status_code == 200
        assert set(payload) == {"status", "session_id", "updated_at", "workbench"}
        assert payload["status"] == "ready"
        assert payload["workbench"]["multifile_analysis"]["analysis_directions"][0]["auto_submit"] is False
        assert payload["workbench"]["details"]["verification"]["claim_count"] == 2
        rendered = json.dumps(payload, ensure_ascii=False)
        assert "artifact_path" not in rendered
        assert "evidence_signature" not in rendered
        assert state_path.read_text(encoding="utf-8") == before
    finally:
        _restore_state(cfg, old_sessions, old_tasks_dir, old_next_id)


def test_workbench_endpoint_projects_bounded_scope_decisions(tmp_path):
    cfg, old_sessions, old_tasks_dir, old_next_id = _use_tmp_state(tmp_path)
    session_id = "scope_contract"
    _write_state(tmp_path, session_id, {
        "session_id": session_id,
        "data_state": "data_loaded",
        "goal": "analyze orders",
        "data_pool": [{
            "file_id": "orders_file",
            "filename": "orders.csv",
            "dataset": "orders",
            "status": "loaded",
        }],
        "dataset_contracts": [{
            "id": "duc_orders",
            "dataset": "orders",
            "quality_status": "ready",
        }],
        "analysis_plan": {
            "method_plan": [{
                "step_id": "step_orders",
                "dataset_inputs": ["orders"],
            }],
        },
    })
    try:
        from data_agent.web.app import create_app

        payload = create_app().test_client().get(
            f"/api/sessions/{session_id}/trust"
        ).get_json()

        decision = payload["workbench"]["details"]["scope"]["files"][0]
        assert decision["assignment"] == "used"
        assert decision["task_count"] == 1
        assert "task_refs" not in json.dumps(payload)
    finally:
        _restore_state(cfg, old_sessions, old_tasks_dir, old_next_id)


def test_workbench_endpoint_keeps_relationship_evidence_diagnostic(tmp_path):
    cfg, old_sessions, old_tasks_dir, old_next_id = _use_tmp_state(tmp_path)
    session_id = "relationship_contract"
    _write_state(tmp_path, session_id, {
        "session_id": session_id,
        "data_state": "data_loaded",
        "file_relationships": [{
            "relationship_id": "rel_orders_flow",
            "status": "rejected",
            "file_ids": ["orders", "flow"],
            "evidence": ["shared user_id"],
            "uncertainties": ["many-to-many"],
        }],
    })
    try:
        from data_agent.web.app import create_app

        payload = create_app().test_client().get(
            f"/api/sessions/{session_id}/trust"
        ).get_json()
        relationship = payload["workbench"]["multifile_analysis"]["relationships"][0]

        assert relationship["diagnostic_only"] is True
        assert relationship["evidence"] == ["shared user_id"]
        assert relationship["uncertainties"] == ["many-to-many"]
    finally:
        _restore_state(cfg, old_sessions, old_tasks_dir, old_next_id)
