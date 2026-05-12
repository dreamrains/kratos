import json

from data_agent.config import get_config
from data_agent.session.task_manager import task_manager


def _use_tmp_state(tmp_path):
    cfg = get_config()
    old_sessions = cfg.sessions_dir
    old_tasks_dir = task_manager._dir
    cfg.sessions_dir = tmp_path / "sessions"
    task_manager._dir = tmp_path / "tasks"
    task_manager.reset_for_testing()
    return cfg, old_sessions, old_tasks_dir


def _restore_state(cfg, old_sessions, old_tasks_dir):
    cfg.sessions_dir = old_sessions
    task_manager._dir = old_tasks_dir
    task_manager._next_id_val = 0


def test_web_capabilities_describe_cli_parity_and_local_mode():
    from data_agent.web.app import create_app

    client = create_app().test_client()
    resp = client.get("/api/capabilities")

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["terminology"]["primary_entity"] == "project"
    assert body["mode"]["profile"] == "local_personal_client"
    assert body["mode"]["local_execution"] is True
    assert body["privacy"]["default_host"] == "127.0.0.1"

    command_names = {item["name"] for item in body["commands"]}
    assert {"project", "analysis", "tasks", "report", "export"} <= command_names

    report = next(item for item in body["commands"] if item["name"] == "report")
    assert "brief" in report["variants"]
    assert "formal" in report["variants"]
    assert {"markdown", "html", "pdf"} <= set(report["formats"])

    capability_ids = {item["id"] for item in body["capabilities"]}
    assert "fallback.python" in capability_ids
    assert "artifact.formal_report" in capability_ids
    assert "artifact.conversation_export" in capability_ids


def test_web_analysis_state_endpoint_and_reset(tmp_path):
    cfg, old_sessions, old_tasks_dir = _use_tmp_state(tmp_path)
    session_id = "web_analysis_state"
    state_dir = tmp_path / "sessions" / session_id
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "analysis_state.json").write_text(
        json.dumps(
            {
                "session_id": session_id,
                "project_name": "Revenue",
                "goal": "分析收入下降原因",
                "stage": "execute",
                "data_state": "data_loaded",
                "data_requirements": [{"id": "req_1", "goal": "收入分析"}],
                "analysis_spec": {"id": "spec_1", "goal": "收入下降归因"},
                "evidence_records": [{"id": "ev_1", "claim": "收入下降主要来自渠道 A"}],
                "pending_confirmations": [{"id": "cf_1", "status": "pending"}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    try:
        from data_agent.web.app import create_app

        client = create_app().test_client()
        resp = client.get(f"/api/sessions/{session_id}/analysis")

        assert resp.status_code == 200
        body = resp.get_json()
        assert body["state"]["goal"] == "分析收入下降原因"
        assert body["summary"]["requirements"] == 1
        assert body["summary"]["has_spec"] is True
        assert body["summary"]["evidence_records"] == 1
        assert body["summary"]["pending_confirmations"] == 1

        reset_resp = client.post(f"/api/sessions/{session_id}/analysis/reset")
        assert reset_resp.status_code == 200
        reset_body = reset_resp.get_json()
        assert reset_body["state"]["goal"] == ""
        assert reset_body["state"]["stage"] == "discover"
        assert reset_body["summary"]["evidence_records"] == 0
    finally:
        _restore_state(cfg, old_sessions, old_tasks_dir)


def test_web_tasks_preserve_workflow_fields_and_scope_order(tmp_path):
    cfg, old_sessions, old_tasks_dir = _use_tmp_state(tmp_path)
    try:
        from data_agent.web.app import create_app

        client = create_app().test_client()
        other = client.post("/api/tasks", json={"subject": "Other", "session_id": "s_other"})
        assert other.status_code == 201
        scoped = client.post(
            "/api/tasks",
            json={
                "subject": "Compare periods",
                "session_id": "s_current",
                "project_name": "Revenue",
                "stage": "execute",
                "node_type": "analysis",
                "analysis_spec_id": "spec_1",
                "required_capability": "analysis.period_compare",
                "evidence_requirements": ["metric_delta"],
                "confirmation_policy": {"requires_confirmation": False},
            },
        )

        assert scoped.status_code == 201
        task = scoped.get_json()
        assert task["required_capability"] == "analysis.period_compare"
        assert task["evidence_requirements"] == ["metric_delta"]

        updated = client.patch(
            f"/api/tasks/{task['id']}",
            json={
                "result_summary": "收入下降 12%",
                "evidence_ids": ["ev_1"],
                "confidence": "medium",
                "required_capability": "analysis.dimension_decomposition",
            },
        )
        assert updated.status_code == 200
        assert updated.get_json()["required_capability"] == "analysis.dimension_decomposition"
        assert updated.get_json()["evidence_ids"] == ["ev_1"]

        listed = client.get("/api/tasks?session_id=s_current")
        assert listed.status_code == 200
        tasks = listed.get_json()
        assert tasks[0]["session_id"] == "s_current"
        assert {t["session_id"] for t in tasks} == {"s_current", "s_other"}
    finally:
        _restore_state(cfg, old_sessions, old_tasks_dir)
