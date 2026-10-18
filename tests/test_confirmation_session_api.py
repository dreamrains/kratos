import json
import pytest
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
        extra_meta={"publication_schema": "answer_bindings.v2"},
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
                "decision_kind": "metric_definition",
                "missing_value": "对比指标口径",
                "affected_operations": ["period_compare"],
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
            resolution_params={"confirmation_type": confirmation_type, "decision_kind": "metric_definition", "missing_value": "对比指标口径", "affected_operations": ["period_compare"]},
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


@pytest.mark.parametrize("legacy_kind", ["template", "window", "unknown_source", "future_empty"])
def test_s3_p7_old_protocol_is_readonly_across_refresh_restart_and_resume(tmp_path, monkeypatch, legacy_kind):
    """Original F5 shapes, produced here; not a recovered historical run."""
    from data_agent.agent.confirmation import AnswerMode, ConfirmationOption, ConfirmationRequest, ConfirmationRecord, ConfirmationEvent
    from data_agent.agent.confirmation.store import ConfirmationStore
    from data_agent.agent.loop import AgentLoop, SuspensionManager, SuspendedForConfirmation
    from data_agent.agent.publication.runtime import require_writable, ReadOnlySessionError
    from data_agent.session.history import save_session, load_session
    from data_agent.web.agent_manager import AgentManager
    from data_agent.web.app import create_app
    from hashlib import sha256

    cfg = _use_tmp_config(monkeypatch, tmp_path)
    sid = "s3_p7_" + legacy_kind
    messages = [] if legacy_kind == "future_empty" else [{"role": "user", "content": "original request"}, {"role": "assistant", "content": "original result 10%"}]
    schema = "answer_bindings.v99" if legacy_kind == "future_empty" else "answer_bindings.v1"
    save_session(messages, sid, extra_meta={"publication_schema": schema}, merge_protect=False)
    from data_agent.session.task_manager import task_manager
    monkeypatch.setattr(task_manager, "_dir", cfg.project_resolved / "tasks")
    monkeypatch.setattr(task_manager, "_next_id_val", 0)
    task = task_manager.create("Original confirmation", session_id=sid, node_type="confirmation", confirmation_ids=["cf_original"])
    params = {"confirmation_type": "method_confirmation", "decision_kind": "time_window", "missing_value": "original window", "affected_operations": ["period_compare"]}
    request = ConfirmationRequest(confirmation_id="cf_original", session_id=sid, turn_id="original_turn", decision_key="original_decision", source="unknown_source" if legacy_kind == "unknown_source" else "method_playbook", operation="period_compare", question="Confirm method?" if legacy_kind == "template" else "Which original window?", decision_impact="Original scope", answer_mode=AnswerMode.SINGLE_SELECT, options=(ConfirmationOption("7 days", "7 days"), ConfirmationOption("30 days", "30 days")) if legacy_kind == "window" else (ConfirmationOption("Original", "original"),), blocking_surfaces=("agent_turn",), skippable=True, resolution_action="record_confirmation_answer", resolution_params=params, continuation_context={"messages": messages, "task_id": task["id"], "checkpoint": "original"})
    record = replace(ConfirmationRecord.from_request(request, now="2026-06-27T00:00:00Z"), status="suspended", suspension_id="cf_original")
    store = ConfirmationStore(cfg.sessions_resolved, sid)
    store.append(ConfirmationEvent(event_id="original_event", confirmation_id=record.confirmation_id, session_id=sid, event_type="suspended", version=record.version, occurred_at=record.updated_at, record=record))
    own = cfg.sessions_resolved / sid
    (own / "analysis_state.json").write_text(json.dumps({"session_id": sid, "pending_confirmations": [record.to_dict()], "original_unknown_field": {"retain": True}}), encoding="utf-8")
    SuspensionManager(own).save(SuspendedForConfirmation(suspension_id=record.confirmation_id, confirmation_id=record.confirmation_id, question=request.question, options=[o.to_dict() for o in request.options], context="original window/field", snapshot={"messages": messages}, confirmation_type="method_confirmation", related_task_id=task["id"]))
    original_tasks = {p.name: p.read_bytes() for p in task_manager.dir.glob("*.json")}
    if legacy_kind == "future_empty":
        with store.events_path.open("ab") as handle:
            handle.write(b'{"schema":"confirmation.v99","event_type":"unknown_future_event","opaque":{"keep":7}}\n')
    original = {p.relative_to(own).as_posix(): p.read_bytes() for p in own.rglob("*") if p.is_file()}
    calls = []
    def no_client(**kw):
        calls.append(kw)
        raise AssertionError("Old protocol cannot construct a model client")
    loop = AgentLoop(client=object(), session_id=sid)
    app = create_app()
    for warm in (False, True, False):
        manager = AgentManager(client_factory=no_client)
        if warm: manager._loops[sid] = loop
        app.config["agent_manager"] = manager
        with app.test_client() as http:
            response = http.get("/api/sessions/" + sid)
            assert response.status_code == 200, response.get_data(as_text=True)
            body = response.get_json()
            assert body["read_only"] is True and body["active_confirmation"] is None
            assert body["messages"] == messages
            for endpoint, payload in (("/api/chat", {"message": "continue"}), ("/api/chat/resume", {"confirmation_id": record.confirmation_id, "expected_version": 1, "idempotency_key": "original_answer", "user_response": "original"})):
                response = http.post(endpoint, json=dict(session_id=sid, **payload))
                assert response.status_code == 409, (warm, endpoint, response.get_data(as_text=True))
        with pytest.raises(ReadOnlySessionError): manager.get_or_create(sid)
    with pytest.raises(ReadOnlySessionError): require_writable(sid)
    with pytest.raises(ReadOnlySessionError): loop.run_turn_structured("continue")
    with pytest.raises(ReadOnlySessionError): list(loop.stream_turn("continue"))
    with pytest.raises(ReadOnlySessionError): loop.resume_turn("cf_original", "original", expected_version=1, idempotency_key="a")
    with pytest.raises(ReadOnlySessionError): list(loop.resume_turn_streaming("cf_original", "original", expected_version=1, idempotency_key="b"))
    assert calls == []
    assert {p.name: p.read_bytes() for p in task_manager.dir.glob("*.json")} == original_tasks
    assert load_session(sid)["messages"] == messages
    assert {p.relative_to(own).as_posix(): p.read_bytes() for p in own.rglob("*") if p.is_file()} == original
    proof = {"fixture_identity": "new explicit original F5 shapes, not historical receipt", "legacy_kind": legacy_kind, "schema": schema, "original_sha256": {p: sha256(b).hexdigest() for p, b in original.items()}, "Provider": 0}
    capture = __import__("os").environ.get("DATA_AGENT_S3_CONFIRMATION_CAPTURE_DIR")
    if capture:
        d = __import__("pathlib").Path(capture); d.mkdir(parents=True, exist_ok=True)
        (d / (legacy_kind + ".json")).write_text(json.dumps(proof, indent=2), encoding="utf-8")


def test_s3_p7_new_empty_and_current_protocol_remain_writable(tmp_path, monkeypatch):
    from data_agent.agent.publication.runtime import require_writable
    from data_agent.session.history import save_session
    cfg = _use_tmp_config(monkeypatch, tmp_path)
    require_writable("new_empty")
    save_session([], "current_empty", extra_meta={"publication_schema": "answer_bindings.v2"})
    require_writable("current_empty")


@pytest.mark.parametrize("route", ["guard", "manager", "loop"])
@pytest.mark.parametrize("schema", ["answer_bindings.v99", 0])
def test_s3_p7_explicit_future_schema_blocks_even_empty_history(tmp_path, monkeypatch, route, schema):
    from data_agent.session.history import save_session
    from data_agent.agent.publication.runtime import require_writable, ReadOnlySessionError
    from data_agent.web.agent_manager import AgentManager
    from data_agent.agent.loop import AgentLoop
    _use_tmp_config(monkeypatch, tmp_path)
    save_session([], "future_empty", extra_meta={"publication_schema": schema})
    with pytest.raises(ReadOnlySessionError):
        if route == "guard": require_writable("future_empty")
        elif route == "manager": AgentManager(client_factory=lambda **kw: (_ for _ in ()).throw(AssertionError("no client"))).get_or_create("future_empty")
        else: AgentLoop(client=object(), session_id="future_empty").run_turn_structured("continue")
