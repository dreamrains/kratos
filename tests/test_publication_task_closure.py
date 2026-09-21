"""P1-3: publication is not held hostage by the task ledger.

Both R21 M04 failures died on analysis_audit_incomplete because projected
tasks were unfinished, even though the model had produced honest structured
artifacts and boundary-respecting answers.  Per the 2026-09-21 goal
realignment the ledger is host bookkeeping: the publication guard keeps
requiring plan + hypothesis set + structured relations, unfinished tasks
stop blocking the turn, and the host closes open tasks at successful
publication with an explicit closure reason so the audit trail stays honest.
"""

from __future__ import annotations

import pytest

from data_agent.session.task_manager import task_manager


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(task_manager, "_dir", tmp_path / "tasks")
    monkeypatch.setattr(task_manager, "_next_id_val", 0)
    return task_manager


def _state_with(plan_id: str):
    class _State:
        analysis_plan = {"id": plan_id, "method_plan": [{"step_id": "S1"}]}
        hypothesis_sets = [{"id": "hypotheses_1"}]
        evidence_records = [{
            "id": "ev_1",
            "competing_hypotheses": [{"hypothesis_id": "h1", "relation": "supports"}],
        }]
    return _State()


def _loop_with_state(monkeypatch, state):
    from tests.test_analysis_quality_guard_scope import _loop_with

    loop = _loop_with(["record_analysis_plan", "record_evidence_record"])
    monkeypatch.setattr(type(loop.context), "analysis_state", state, raising=False)
    return loop


def test_unfinished_tasks_no_longer_block_publication_guard(ledger, monkeypatch):
    plan = ledger.create_plan(session_id="s1", goal="hypotheses", source="analysis_plan")
    ledger.create("S1", session_id="s1", plan_id=plan["id"],
                  analysis_plan_id="ap1", step_id="S1")
    ledger.start_next_ready_stage3c0b_task(session_id="s1", project_name="")

    loop = _loop_with_state(monkeypatch, _state_with(plan["id"]))
    monkeypatch.setattr(loop, "session_id", "s1", raising=False)

    gaps = loop._competing_hypothesis_quality_gaps("请提出并检验至少两种竞争性假设")
    assert gaps == [], gaps


def test_missing_structured_relations_still_block(ledger, monkeypatch):
    plan = ledger.create_plan(session_id="s2", goal="hypotheses", source="analysis_plan")

    class _Empty:
        analysis_plan = {"id": plan["id"], "method_plan": [{"step_id": "S1"}]}
        hypothesis_sets = []
        evidence_records = []

    loop = _loop_with_state(monkeypatch, _Empty())
    monkeypatch.setattr(loop, "session_id", "s2", raising=False)
    gaps = loop._competing_hypothesis_quality_gaps("请提出并检验至少两种竞争性假设")
    assert any("hypothesis" in gap for gap in gaps), gaps


def test_host_closes_open_tasks_at_publication_with_reason(ledger):
    plan = ledger.create_plan(session_id="s3", goal="g", source="analysis_plan")
    t1 = ledger.create("S1", session_id="s3", plan_id=plan["id"],
                       analysis_plan_id="ap1", step_id="S1")
    ledger.start_next_ready_stage3c0b_task(session_id="s3", project_name="")
    t2 = ledger.create("S2", session_id="s3", plan_id=plan["id"],
                       analysis_plan_id="ap1", step_id="S2")

    closed = ledger.close_open_tasks_for_publication(
        session_id="s3", project_name="", reason="superseded_by_publication"
    )

    assert sorted(closed) == sorted([t1["id"], t2["id"]])
    for tid in (t1["id"], t2["id"]):
        task = ledger.get(tid)
        assert task["status"] == "closed_by_publication"
        assert task.get("closure_reason") == "superseded_by_publication"
    assert ledger.get_active_plan_id("s3", "") == ""


def test_closure_never_touches_other_sessions(ledger):
    plan = ledger.create_plan(session_id="s4", goal="g", source="analysis_plan")
    mine = ledger.create("mine", session_id="s4", plan_id=plan["id"], step_id="S1")
    other = ledger.create("other", session_id="s5", plan_id=plan["id"], step_id="S2")

    closed = ledger.close_open_tasks_for_publication(
        session_id="s4", project_name="", reason="superseded_by_publication"
    )
    assert closed == [mine["id"]]
    assert ledger.get(other["id"])["status"] == "pending"
