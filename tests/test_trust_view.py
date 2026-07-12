import json

from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.trust_view import build_trust_view


def test_empty_trust_view_is_only_an_empty_workbench_contract() -> None:
    view = build_trust_view(None, session_id="missing")

    assert set(view) == {"status", "session_id", "updated_at", "workbench"}
    assert view["status"] == "empty"
    assert view["session_id"] == "missing"
    assert set(view["workbench"]) == {"action_board", "multifile_analysis", "details", "full_answer"}
    assert set(view["workbench"]["action_board"]) == {"confirmed", "uncertain", "next_steps", "trust_basis"}
    assert set(view["workbench"]["multifile_analysis"]) == {
        "data_understanding",
        "relationships",
    }


def test_workbench_projects_scope_confirmation_and_verification_without_internal_ids() -> None:
    state = AnalysisSessionState(session_id="bounded_details", data_state="data_loaded")
    state.goal = "Evaluate savings-card performance"
    state.data_pool = [{
        "file_id": "orders_file",
        "filename": "orders.xlsx",
        "dataset": "orders",
        "status": "loaded",
    }]
    state.dataset_contracts = [{
        "id": "duc_orders",
        "dataset": "orders",
        "quality_status": "ready",
    }]
    state.analysis_plan = {
        "method_plan": [{"step_id": "step_orders", "dataset_inputs": ["orders"]}]
    }
    state.pending_confirmations = [{
        "id": "confirm_method",
        "status": "pending",
        "confirmation_type": "method_confirmation",
        "question": "Use a 30-day comparison window?",
        "blocking_reason": "The window changes the interpretation.",
    }]
    state.verification_reports = [{
        "overall_status": "pass_with_downgrades",
        "claim_count": 3,
        "failed_count": 0,
        "downgraded_count": 1,
        "evidence_signature": "private-signature",
        "artifact_path": "sessions/private/verification.json",
    }]

    before = state.to_dict()
    view = build_trust_view(state)

    assert state.to_dict() == before
    details = view["workbench"]["details"]
    assert details["scope"]["goal"] == "Evaluate savings-card performance"
    assert details["scope"]["files"][0]["assignment"] == "used"
    assert details["scope"]["files"][0]["task_count"] == 1
    assert details["confirmation"]["status"] == "needs_confirmation"
    rendered = json.dumps(view, ensure_ascii=False)
    assert "task_refs" not in rendered
    assert "evidence_signature" not in rendered
    assert "artifact_path" not in rendered


def test_relationships_remain_diagnostic_and_keep_bounded_supporting_detail() -> None:
    state = AnalysisSessionState(session_id="relationship_details", data_state="data_loaded")
    state.file_relationships = [{
        "relationship_id": "rel_orders_flow",
        "status": "rejected",
        "file_ids": ["orders", "flow"],
        "value": "Can compare user coverage.",
        "risk": "Many-to-many row multiplication.",
        "evidence": ["shared user_id", "high key coverage", "extra evidence", "fourth", "fifth"],
        "uncertainties": ["different time windows"],
        "requires_confirmation": True,
    }]

    relationship = build_trust_view(state)["workbench"]["multifile_analysis"]["relationships"][0]

    assert relationship["diagnostic_only"] is True
    assert relationship["status"] == "rejected"
    assert relationship["evidence"] == [
        "shared user_id",
        "high key coverage",
        "extra evidence",
        "fourth",
    ]
    assert relationship["uncertainties"] == ["different time windows"]


def test_action_board_next_steps_are_suggestions_and_never_auto_submit() -> None:
    state = AnalysisSessionState(session_id="directions", data_state="data_loaded")
    state.active_scope.update({"active_dataset": "orders", "active_mode": "data_loaded"})
    state.dataset_contracts = [{
        "id": "duc_orders",
        "dataset": "orders",
        "field_roles": {"date": ["date"], "metrics": ["gmv"]},
        "quality_status": "ready",
    }]
    state.route_proposals = [{
        "id": "route_trend",
        "dataset": "orders",
        "direction": "trend",
        "label": "GMV trend",
        "reason": "Date and GMV are available.",
        "evidence_requirements": ["daily GMV"],
    }]

    next_steps = build_trust_view(state)["workbench"]["action_board"]["next_steps"]

    assert next_steps
    route_steps = [n for n in next_steps if n.get("kind") == "route"]
    assert route_steps
    assert all(n.get("auto_submit") is False for n in route_steps)


def test_loaded_state_is_ready_even_before_evidence_exists() -> None:
    state = AnalysisSessionState(session_id="loaded", data_state="data_loaded")

    view = build_trust_view(state)

    assert view["status"] == "ready"
    # Loaded, so "ready" — but no evidence exists yet, so the trust basis
    # reflects an unverified state (the canonical home for these values now).
    trust_basis = view["workbench"]["action_board"]["trust_basis"]
    assert trust_basis["evidence_count"] == 0
    assert trust_basis["verification_status"] == "not_run"


from pathlib import Path
from types import SimpleNamespace


def _write_session(tmp_path, session_id, messages):
    sdir = tmp_path / "sessions" / session_id
    sdir.mkdir(parents=True, exist_ok=True)
    (sdir / "meta.json").write_text(json.dumps({"project_name": "p"}, ensure_ascii=False), encoding="utf-8")
    (sdir / "conversation.jsonl").write_text(
        "".join(json.dumps(m, ensure_ascii=False) + "\n" for m in messages),
        encoding="utf-8",
    )


def test_full_answer_is_last_assistant_message(tmp_path, monkeypatch):
    from data_agent import config
    from data_agent.config import AgentConfig
    from data_agent.agent.trust_view import build_trust_view

    seeded_answer = "## 最新结论\n收入下降"
    monkeypatch.setattr(config, "_config", AgentConfig(SESSIONS_DIR=tmp_path / "sessions"))
    _write_session(tmp_path, "s1", [
        {"role": "user", "content": "问"},
        {"role": "assistant", "content": "旧答案"},
        {"role": "user", "content": "再问"},
        {"role": "assistant", "content": seeded_answer},
    ])
    state = SimpleNamespace(evidence_records=[], verification_reports=[],
                            data_understanding_bundles=[], route_proposals=[],
                            file_relationships=[], goal="", data_state="data_loaded")
    view = build_trust_view(state, session_id="s1")
    # Exact equality guards the regression: a previous version routed the
    # content through _text() which collapses all newlines to single spaces,
    # breaking the frontend's markdown rendering. The raw multi-line string
    # must round-trip byte-for-byte.
    assert view["workbench"]["full_answer"] == seeded_answer
    assert "\n" in view["workbench"]["full_answer"]
    assert view["workbench"]["full_answer"].startswith("## 最新结论")
    assert "收入下降" in view["workbench"]["full_answer"]


def test_full_answer_none_when_no_session_or_empty(tmp_path, monkeypatch):
    from data_agent import config
    from data_agent.config import AgentConfig
    from data_agent.agent.trust_view import build_trust_view

    monkeypatch.setattr(config, "_config", AgentConfig(SESSIONS_DIR=tmp_path / "sessions"))
    state = SimpleNamespace(evidence_records=[], verification_reports=[],
                            data_understanding_bundles=[], route_proposals=[],
                            file_relationships=[], goal="", data_state="data_loaded")
    assert build_trust_view(state, session_id="missing")["workbench"]["full_answer"] is None
    assert build_trust_view(state, session_id="")["workbench"]["full_answer"] is None
