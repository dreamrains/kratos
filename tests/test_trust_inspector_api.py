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


def _clear_confirmation_gate():
    return {
        "status": "clear",
        "confirmation_type": "",
        "question": "",
        "blocking_reason": "",
        "risk_fields": [],
        "affected_routes": [],
        "blocked_surfaces": [],
    }


def test_trust_view_endpoint_returns_exact_empty_view_for_missing_session(tmp_path):
    cfg, old_sessions, old_tasks_dir, old_next_id = _use_tmp_state(tmp_path)
    try:
        from data_agent.web.app import create_app

        client = create_app().test_client()
        resp = client.get("/api/sessions/missing_session/trust")

        assert resp.status_code == 200
        assert resp.get_json() == {
            "status": "empty",
            "session_id": "missing_session",
            "updated_at": "",
            "datasets": [],
            "routes": [],
            "risks": [],
            "verification": None,
            "hypotheses": [],
            "active_scope": {
                "active_dataset": "",
                "active_route": "",
                "active_goal": "",
                "active_mode": "consulting",
            },
            "scope_counts": {
                "datasets": 0,
                "routes": 0,
                "risks": 0,
                "hypothesis_sets": 0,
                "artifacts": 0,
            },
            "recommendations": {
                "active_dataset": "",
                "active_route": "",
                "active_mode": "consulting",
                "executable": [],
                "exploratory": [],
                "counts": {"executable": 0, "exploratory": 0},
                "confirmation_gate": _clear_confirmation_gate(),
            },
            "active_bundle": None,
            "file_relationships": [],
            "history": {"datasets": [], "routes": [], "risks": [], "hypotheses": []},
        }
    finally:
        _restore_state(cfg, old_sessions, old_tasks_dir, old_next_id)


def test_trust_view_endpoint_returns_populated_view_and_does_not_mutate_state(tmp_path):
    cfg, old_sessions, old_tasks_dir, old_next_id = _use_tmp_state(tmp_path)
    session_id = "trust_session"
    state_dir = tmp_path / "sessions" / session_id
    state_dir.mkdir(parents=True, exist_ok=True)
    state_path = state_dir / "analysis_state.json"
    state_path.write_text(
        json.dumps(
            {
                "session_id": session_id,
                "updated_at": "2026-06-07 12:30:00",
                "data_state": "data_loaded",
                "dataset_contracts": [
                    {
                        "dataset": "sales",
                        "row_count": 120,
                        "column_count": 4,
                        "quality": {"status": "warning", "score": 0.91},
                        "field_roles": {
                            "date": ["order_date"],
                            "metrics": ["revenue", "orders"],
                            "dimensions": ["region"],
                        },
                        "supported_analyses": ["trend", "segment"],
                    }
                ],
                "route_proposals": [
                    {
                        "id": "route_trend",
                        "dataset": "sales",
                        "direction": "trend",
                        "label": "Revenue trend",
                        "reason": "order_date and revenue are available",
                        "budget_level": "low",
                    }
                ],
                "verification_reports": [
                    {
                        "id": "verify_1",
                        "overall_status": "pass",
                        "claim_count": 3,
                        "failed_count": 0,
                        "downgraded_count": 1,
                        "evidence_signature": "sig-123",
                        "created_at": "2026-06-07 12:35:00",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    before = state_path.read_text(encoding="utf-8")

    try:
        from data_agent.web.app import create_app

        client = create_app().test_client()
        resp = client.get(f"/api/sessions/{session_id}/trust")

        assert resp.status_code == 200
        assert resp.get_json() == {
            "status": "ready",
            "session_id": session_id,
            "updated_at": "2026-06-07 12:30:00",
            "datasets": [
                {
                    "dataset": "sales",
                    "rows": 120,
                    "columns": 4,
                    "quality_status": "warning",
                    "quality_score": 0.91,
                    "key_fields": ["order_date", "revenue", "orders", "region"],
                    "supported_analyses": ["trend", "segment"],
                    "preview_notes": [],
                }
            ],
            "routes": [],
            "risks": [],
            "verification": {
                "id": "verify_1",
                "status": "pass",
                "claim_count": 3,
                "failed_count": 0,
                "downgraded_count": 1,
                "evidence_signature": "sig-123",
                "created_at": "2026-06-07 12:35:00",
            },
            "hypotheses": [],
            "active_scope": {
                "active_dataset": "",
                "active_route": "",
                "active_goal": "",
                "active_mode": "consulting",
            },
            "scope_counts": {
                "datasets": 1,
                "routes": 1,
                "risks": 0,
                "hypothesis_sets": 0,
                "artifacts": 0,
            },
            "recommendations": {
                "active_dataset": "",
                "active_route": "",
                "active_mode": "consulting",
                "executable": [],
                "exploratory": [],
                "counts": {"executable": 0, "exploratory": 0},
                "confirmation_gate": _clear_confirmation_gate(),
            },
            "active_bundle": None,
            "file_relationships": [],
            "history": {
                "datasets": [
                    {
                        "dataset": "sales",
                        "rows": 120,
                        "columns": 4,
                        "quality_status": "warning",
                        "quality_score": 0.91,
                        "key_fields": ["order_date", "revenue", "orders", "region"],
                        "supported_analyses": ["trend", "segment"],
                        "preview_notes": [],
                    }
                ],
                "routes": [
                    {
                        "id": "route_trend",
                        "dataset": "sales",
                        "direction": "trend",
                        "label": "Revenue trend",
                        "reason": "order_date and revenue are available",
                        "limitations": [],
                        "budget_level": "low",
                        "prompt": (
                            "Please analyze the current dataset using the trend direction. "
                            "Focus: Revenue trend. "
                            "Rationale: order_date and revenue are available."
                        ),
                        "auto_submit": False,
                    }
                ],
                "risks": [],
                "hypotheses": [],
            },
        }
        assert state_path.read_text(encoding="utf-8") == before
    finally:
        _restore_state(cfg, old_sessions, old_tasks_dir, old_next_id)


def test_trust_view_endpoint_returns_active_bundle_summary_without_mutating_state(tmp_path):
    cfg, old_sessions, old_tasks_dir, old_next_id = _use_tmp_state(tmp_path)
    session_id = "trust_bundle_session"
    state_dir = tmp_path / "sessions" / session_id
    state_dir.mkdir(parents=True, exist_ok=True)
    state_path = state_dir / "analysis_state.json"
    state_path.write_text(
        json.dumps(
            {
                "session_id": session_id,
                "updated_at": "2026-06-07 12:40:00",
                "data_state": "data_loaded",
                "data_pool": [
                    {
                        "file_id": "file_old",
                        "filename": "orders_old.csv",
                        "dataset": "orders_old",
                        "row_count": 120,
                        "column_count": 6,
                        "columns": ["large", "columns", "should", "not", "leak"],
                        "status": "available",
                    },
                    {
                        "file_id": "file_new",
                        "filename": "orders_new.csv",
                        "dataset": "orders_new",
                        "rows": 98,
                        "columns": ["order_id", "revenue"],
                        "status": "available",
                    },
                ],
                "dataset_bundles": [
                    {
                        "bundle_id": "bundle_orders",
                        "label": "Orders scope",
                        "file_ids": ["file_old", "file_new"],
                        "dataset_names": ["orders_old", "orders_new"],
                        "relationship_status": "confirmed",
                        "relationship_mode": "include_in_active_bundle",
                    }
                ],
                "active_bundle_id": "bundle_orders",
                "file_relationships": [
                    {
                        "relationship_id": "rel_orders",
                        "status": "confirmed",
                        "requires_confirmation": False,
                        "relationship_mode": "include_in_active_bundle",
                        "file_ids": ["file_old", "file_new", "file_extra"],
                        "evidence": ["same order_id", "overlapping dates", "not returned"],
                        "uncertainties": ["row counts differ", "missing region keys", "not returned"],
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    before = state_path.read_text(encoding="utf-8")

    try:
        from data_agent.web.app import create_app

        client = create_app().test_client()
        resp = client.get(f"/api/sessions/{session_id}/trust")

        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["active_bundle"] == {
            "bundle_id": "bundle_orders",
            "label": "Orders scope",
            "file_count": 2,
            "dataset_names": ["orders_old", "orders_new"],
            "relationship_status": "confirmed",
            "relationship_mode": "include_in_active_bundle",
            "files": [
                {
                    "file_id": "file_old",
                    "filename": "orders_old.csv",
                    "dataset": "orders_old",
                    "rows": 120,
                    "columns": 6,
                    "status": "available",
                },
                {
                    "file_id": "file_new",
                    "filename": "orders_new.csv",
                    "dataset": "orders_new",
                    "rows": 98,
                    "columns": 2,
                    "status": "available",
                },
            ],
            "remaining_file_count": 0,
        }
        assert payload["file_relationships"] == [
            {
                "relationship_id": "rel_orders",
                "status": "confirmed",
                "requires_confirmation": False,
                "relationship_mode": "include_in_active_bundle",
                "confirmation_type": "",
                "file_count": 3,
                "file_ids": ["file_old", "file_new", "file_extra"],
                "evidence": ["same order_id", "overlapping dates"],
                "uncertainties": ["row counts differ", "missing region keys"],
            }
        ]
        assert "large" not in json.dumps(payload["active_bundle"], ensure_ascii=False)
        assert state_path.read_text(encoding="utf-8") == before
    finally:
        _restore_state(cfg, old_sessions, old_tasks_dir, old_next_id)


def test_trust_view_endpoint_hydrates_artifact_refs_without_mutating_state(tmp_path):
    cfg, old_sessions, old_tasks_dir, old_next_id = _use_tmp_state(tmp_path)
    session_id = "trust_hydration_session"
    state_dir = tmp_path / "sessions" / session_id
    artifact_dir = state_dir / "tool_outputs"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    contract_path = artifact_dir / "contract.json"
    contract_path.write_text(
        json.dumps(
            {
                "dataset": "retention",
                "row_count": 62,
                "column_count": 13,
                "quality": {"status": "ready", "score": 100},
                "field_roles": {
                    "date": ["date"],
                    "metrics": ["daily_active", "day_1_retention"],
                },
                "unsupported_analyses": [
                    {"type": "user_level_retention", "reason": "aggregate grain"}
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    route_path = artifact_dir / "route.json"
    route_path.write_text(
        json.dumps(
            {
                "id": "route_retention_trend",
                "dataset": "retention",
                "direction": "trend",
                "limitations": ["Descriptive trend only"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    state_path = state_dir / "analysis_state.json"
    state_path.write_text(
        json.dumps(
            {
                "session_id": session_id,
                "data_state": "data_loaded",
                "active_scope": {
                    "active_dataset": "retention",
                    "active_mode": "data_loaded",
                },
                "dataset_contracts": [
                    {
                        "dataset": "retention",
                        "artifact_path": str(contract_path),
                        "quality_status": "ready",
                    }
                ],
                "route_proposals": [
                    {
                        "id": "route_retention_trend",
                        "dataset": "retention",
                        "artifact_path": str(route_path),
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    before = state_path.read_text(encoding="utf-8")

    try:
        from data_agent.web.app import create_app

        client = create_app().test_client()
        resp = client.get(f"/api/sessions/{session_id}/trust")

        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["datasets"][0]["rows"] == 62
        assert payload["datasets"][0]["columns"] == 13
        assert payload["datasets"][0]["key_fields"] == ["date", "daily_active", "day_1_retention"]
        assert payload["routes"][0]["direction"] == "trend"
        assert payload["routes"][0]["limitations"] == ["Descriptive trend only"]
        assert payload["scope_counts"] == {
            "datasets": 1,
            "routes": 1,
            "risks": 1,
            "hypothesis_sets": 0,
            "artifacts": 2,
        }
        assert payload["risks"] == [
            {
                "severity": "warning",
                "source": "unsupported_analysis",
                "dataset": "retention",
                "field": "user_level_retention",
                "message": "aggregate grain",
            }
        ]
        assert state_path.read_text(encoding="utf-8") == before
    finally:
        _restore_state(cfg, old_sessions, old_tasks_dir, old_next_id)
