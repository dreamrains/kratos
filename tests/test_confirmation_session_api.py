import json
from dataclasses import replace

from data_agent.config import AgentConfig


def _use_tmp_config(monkeypatch, tmp_path):
    import data_agent.config as config_module

    cfg = AgentConfig(
        PROJECT_DIR=tmp_path / "project",
        SESSIONS_DIR=tmp_path / "sessions",
        SKILL_AUTO_DISCOVER=False,
    )
    monkeypatch.setattr(config_module, "_config", cfg)
    return cfg


def _write_session(cfg, session_id):
    from data_agent.session.history import save_session

    save_session(
        [
            {"role": "user", "content": "analyze revenue"},
            {"role": "assistant", "content": "I need one answer first."},
        ],
        session_id,
    )


def _request_runtime_confirmation(
    cfg,
    session_id,
    *,
    confirmation_id="cf_session_1",
    decision_key="metric-choice",
    resolution_action="record_confirmation_answer",
    registry=None,
):
    from data_agent.agent.confirmation import AnswerMode, ConfirmationOption, QuestionCandidate
    from data_agent.agent.confirmation.runtime import build_action_registry
    from data_agent.agent.confirmation.service import ConfirmationService

    service = ConfirmationService(
        cfg.sessions_resolved,
        action_registry=registry or build_action_registry(),
    )
    service.request(
        QuestionCandidate(
            confirmation_id=confirmation_id,
            session_id=session_id,
            turn_id="turn_1",
            decision_key=f"{session_id}:{decision_key}",
            source="test",
            operation="direct_user_question",
            question="Which metric?",
            decision_impact="Metric choice changes the calculation.",
            answer_mode=AnswerMode.SINGLE_SELECT,
            options=(ConfirmationOption(label="Revenue", value="revenue"),),
            blocking_surfaces=("agent_turn",),
            skippable=True,
            resolution_action=resolution_action,
            resolution_params={
                "context": "Choose the metric.",
                "confirmation_type": "metric_scope",
                "related_task_id": 12,
                "related_spec_id": "spec_1",
            },
            data_version="messages:2",
            spec_version="spec_1",
        )
    )
    return service.checkpoint(session_id)


def test_session_detail_returns_active_runtime_confirmation(tmp_path, monkeypatch):
    cfg = _use_tmp_config(monkeypatch, tmp_path)
    session_id = "session_active_runtime"
    _write_session(cfg, session_id)
    active = _request_runtime_confirmation(cfg, session_id)

    from data_agent.web.app import create_app

    client = create_app().test_client()
    resp = client.get(f"/api/sessions/{session_id}")

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["active_confirmation"]["confirmation_id"] == active.confirmation_id
    assert body["active_confirmation"]["suspension_id"] == active.confirmation_id
    assert body["active_confirmation"]["version"] == active.version
    assert body["active_confirmation"]["status"] == "suspended"
    assert body["active_confirmation"]["question"] == "Which metric?"
    assert body["active_confirmation"]["options"] == [
        {"label": "Revenue", "value": "revenue", "description": ""}
    ]
    assert body["active_confirmation"]["context"] == "Choose the metric."
    assert body["active_confirmation"]["multi_select"] is False
    assert body["active_confirmation"]["confirmation_type"] == "metric_scope"
    assert body["active_confirmation"]["blocking_reason"] == "Metric choice changes the calculation."
    assert body["active_confirmation"]["related_task_id"] == 12
    assert body["active_confirmation"]["related_spec_id"] == "spec_1"
    assert body["active_confirmation"]["skippable"] is True
    assert body["queued_confirmation_count"] == 0
    assert body["failed_confirmation_count"] == 0


def test_session_detail_counts_runtime_queue_and_failed_records(tmp_path, monkeypatch):
    cfg = _use_tmp_config(monkeypatch, tmp_path)
    session_id = "session_runtime_counts"
    _write_session(cfg, session_id)

    from data_agent.agent.confirmation.runtime import build_action_registry
    from data_agent.agent.confirmation.service import (
        ConfirmationResolutionFailed,
        ConfirmationService,
    )

    registry = build_action_registry()

    def _fail_for_test(_context, _answer):
        raise RuntimeError("boom")

    registry.register("fail_for_test", _fail_for_test)
    failed_active = _request_runtime_confirmation(
        cfg,
        session_id,
        confirmation_id="cf_failed_1",
        decision_key="failed",
        resolution_action="fail_for_test",
        registry=registry,
    )
    service = ConfirmationService(cfg.sessions_resolved, action_registry=registry)
    try:
        service.respond(session_id, failed_active.confirmation_id, "revenue", failed_active.version, "fail_key")
    except ConfirmationResolutionFailed:
        pass
    _request_runtime_confirmation(cfg, session_id, confirmation_id="cf_count_1", decision_key="count-1")

    from data_agent.web.app import create_app

    client = create_app().test_client()
    body = client.get(f"/api/sessions/{session_id}").get_json()

    assert body["active_confirmation"]["confirmation_id"] == "cf_failed_1"
    assert body["queued_confirmation_count"] == 1
    assert body["failed_confirmation_count"] == 1


def test_session_detail_ignores_legacy_pending_confirmations(tmp_path, monkeypatch):
    cfg = _use_tmp_config(monkeypatch, tmp_path)
    session_id = "session_legacy_pending"
    _write_session(cfg, session_id)
    session_dir = cfg.sessions_resolved / session_id
    (session_dir / "analysis_state.json").write_text(
        json.dumps(
            {
                "session_id": session_id,
                "pending_confirmations": [
                    {"id": "legacy_cf", "status": "pending", "question": "Legacy question?"}
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    from data_agent.web.app import create_app

    client = create_app().test_client()
    body = client.get(f"/api/sessions/{session_id}").get_json()

    assert body["active_confirmation"] is None
    assert body["queued_confirmation_count"] == 0
    assert body["failed_confirmation_count"] == 0


def test_session_detail_ignores_obsolete_runtime_ledger_states(tmp_path, monkeypatch):
    from data_agent.agent.confirmation import (
        AnswerMode,
        ConfirmationEvent,
        ConfirmationOption,
        ConfirmationRecord,
        ConfirmationRequest,
        ConfirmationStatus,
        QuestionCandidate,
    )
    from data_agent.agent.confirmation.store import ConfirmationStore

    cfg = _use_tmp_config(monkeypatch, tmp_path)
    session_id = "session_obsolete_runtime"
    _write_session(cfg, session_id)
    store = ConfirmationStore(cfg.sessions_resolved, session_id)
    for confirmation_id, status, confirmation_type in (
        ("legacy_pending", ConfirmationStatus.PENDING, "file_relationship_confirmation"),
        ("legacy_suspended", ConfirmationStatus.SUSPENDED, "file_exclusion_confirmation"),
        ("legacy_failed", ConfirmationStatus.FAILED, "join_logic_confirmation"),
    ):
        candidate = QuestionCandidate(
            confirmation_id=confirmation_id,
            session_id=session_id,
            turn_id="legacy_turn",
            decision_key=f"legacy:{confirmation_id}",
            source="legacy",
            operation=confirmation_type,
            question="Legacy relationship question?",
            decision_impact="Legacy relationship gate",
            answer_mode=AnswerMode.SINGLE_SELECT,
            options=(ConfirmationOption("Include", "include"),),
            blocking_surfaces=("agent_turn",),
            skippable=True,
            resolution_action="resolve_file_relationship",
            resolution_params={"confirmation_type": confirmation_type},
        )
        record = ConfirmationRecord.from_request(
            ConfirmationRequest.from_candidate(candidate),
            now="2026-06-27T00:00:00Z",
        )
        record = replace(
            record,
            status=status,
            suspension_id=(f"susp_{confirmation_id}" if status == ConfirmationStatus.SUSPENDED else ""),
            failure_reason=("legacy action missing" if status == ConfirmationStatus.FAILED else ""),
        )
        store.append(ConfirmationEvent(
            event_id=f"event_{confirmation_id}",
            confirmation_id=confirmation_id,
            session_id=session_id,
            event_type="legacy_fixture",
            version=record.version,
            occurred_at=record.updated_at,
            record=record,
        ))

    from data_agent.web.app import create_app

    body = create_app().test_client().get(f"/api/sessions/{session_id}").get_json()

    assert body["active_confirmation"] is None
    assert body["queued_confirmation_count"] == 0
    assert body["failed_confirmation_count"] == 0
