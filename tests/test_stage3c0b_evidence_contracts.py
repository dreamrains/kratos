from __future__ import annotations

import json

from data_agent.session.task_manager import TaskManager


def _measurement(metric: str = "click_rate", value: float = 0.125, unit: str = "ratio") -> dict:
    return {
        "metric": metric,
        "definition": "Clicks divided by impressions.",
        "value": value,
        "unit": unit,
        "grain": "banner_day",
        "population_scope": "all banner impressions",
        "time_scope": "2026-06-01 to 2026-06-07",
        "method": "aggregate ratio",
        "denominator": "impressions",
        "limitations": ["descriptive only"],
    }


def _canonical_evidence(
    *,
    evidence_requirement: str = "click_rate",
    claim_key: str | None = None,
    evidence_id: str | None = None,
) -> dict:
    record = {
        "plan_id": "plan_abc",
        "step_id": "step_banner",
        "claim_key": claim_key or evidence_requirement,
        "claim": f"Banner {evidence_requirement} is supported by current data.",
        "dataset": "banner",
        "dataset_contract_id": "contract_banner",
        "method": "grouped aggregation",
        "tool_calls": [{"name": "run_python", "args": {"metric": evidence_requirement}}],
        "result_summary": f"{evidence_requirement}=0.125",
        "sample_size": 4000,
        "limitations": ["descriptive only"],
        "confidence": "high",
        "evidence_requirement": evidence_requirement,
        "measurements": [_measurement(metric=evidence_requirement)],
    }
    if evidence_id is not None:
        record["id"] = evidence_id
    return record


def test_evidence_id_for_slugs_stable_id():
    from data_agent.agent.evidence_contracts import evidence_id_for

    assert (
        evidence_id_for("plan_abc", "step_banner", "banner_click_rate")
        == "ev_plan_abc_step_banner_banner_click_rate"
    )


def test_valid_evidence_passes_has_id_and_preserves_measurement_unit():
    from data_agent.agent.evidence_contracts import validate_stage3c0b_evidence

    result = validate_stage3c0b_evidence(_canonical_evidence(), current_plan_id="plan_abc")

    assert result.ok is True
    assert result.record["id"] == "ev_plan_abc_step_banner_click_rate"
    assert result.record["measurements"][0]["unit"] == "ratio"


def test_old_metrics_without_measurements_rejected_as_missing_measurements():
    from data_agent.agent.evidence_contracts import validate_stage3c0b_evidence

    record = _canonical_evidence()
    record.pop("measurements")
    record["metrics"] = {"click_rate": 0.125}

    result = validate_stage3c0b_evidence(record, current_plan_id="plan_abc")

    assert result.ok is False
    assert result.error_type == "missing_measurements"


def test_evidence_from_other_plan_rejected_as_outside_current_plan():
    from data_agent.agent.evidence_contracts import validate_stage3c0b_evidence

    result = validate_stage3c0b_evidence(_canonical_evidence(), current_plan_id="plan_other")

    assert result.ok is False
    assert result.error_type == "evidence_outside_current_plan"
    assert result.details["current_plan_id"] == "plan_other"


def test_evidence_without_current_plan_rejected_as_outside_current_plan():
    from data_agent.agent.evidence_contracts import validate_stage3c0b_evidence

    result = validate_stage3c0b_evidence(_canonical_evidence(), current_plan_id="")

    assert result.ok is False
    assert result.error_type == "evidence_outside_current_plan"
    assert result.details["current_plan_id"] == ""


def test_empty_canonical_evidence_field_rejected():
    from data_agent.agent.evidence_contracts import validate_stage3c0b_evidence

    record = _canonical_evidence()
    record["claim"] = "   "

    result = validate_stage3c0b_evidence(record, current_plan_id="plan_abc")

    assert result.ok is False
    assert result.error_type == "missing_canonical_fields"
    assert "claim" in result.details["missing"]


def test_empty_measurement_compatibility_field_rejected():
    from data_agent.agent.evidence_contracts import validate_stage3c0b_evidence

    record = _canonical_evidence()
    record["measurements"][0]["denominator"] = ""

    result = validate_stage3c0b_evidence(record, current_plan_id="plan_abc")

    assert result.ok is False
    assert result.error_type == "missing_measurement_fields"
    assert "denominator" in result.details["missing"]


def test_record_evidence_record_rejects_stage3c0b_evidence_without_current_plan(monkeypatch):
    from data_agent.tools.analysis_flow import record_evidence_record

    monkeypatch.setattr("data_agent.tools.analysis_flow._current_state", lambda: None)

    result = json.loads(record_evidence_record(json.dumps(_canonical_evidence())))

    assert result["error_type"] == "evidence_outside_current_plan"


def test_task_manager_requires_all_evidence_requirements_before_completion(tmp_path):
    mgr = TaskManager(tasks_dir=tmp_path / "tasks")
    plan = mgr.create_plan(session_id="s1", goal="Analyze banner", source="analysis_plan")
    task = mgr.create(
        "Analyze banner metrics",
        session_id="s1",
        plan_id=plan["id"],
        plan_version=plan["version"],
        analysis_plan_id="plan_abc",
        step_id="step_banner",
        dataset_contract_ids=["contract_banner"],
        evidence_requirements=["click_rate", "conversion_rate"],
    )

    completed = mgr.complete_matching_tasks_from_evidence(
        session_id="s1",
        evidence=_canonical_evidence(evidence_requirement="click_rate"),
    )

    assert completed == []
    updated = mgr.get(task["id"])
    assert updated["status"] == "pending"
    assert updated["evidence_ids"] == ["ev_plan_abc_step_banner_click_rate"]
    assert updated["satisfied_evidence_requirements"] == ["click_rate"]


def test_task_manager_completes_when_all_requirements_have_evidence_and_stores_ids(tmp_path):
    mgr = TaskManager(tasks_dir=tmp_path / "tasks")
    plan = mgr.create_plan(session_id="s1", goal="Analyze banner", source="analysis_plan")
    task = mgr.create(
        "Analyze banner metrics",
        session_id="s1",
        plan_id=plan["id"],
        plan_version=plan["version"],
        analysis_plan_id="plan_abc",
        step_id="step_banner",
        dataset_contract_ids=["contract_banner"],
        evidence_requirements=["click_rate", "conversion_rate"],
    )

    first_completed = mgr.complete_matching_tasks_from_evidence(
        session_id="s1",
        evidence=_canonical_evidence(evidence_requirement="click_rate"),
    )
    second_completed = mgr.complete_matching_tasks_from_evidence(
        session_id="s1",
        evidence=_canonical_evidence(evidence_requirement="conversion_rate"),
    )

    assert first_completed == []
    assert second_completed == [task["id"]]
    updated = mgr.get(task["id"])
    assert updated["status"] == "completed"
    assert updated["evidence_ids"] == [
        "ev_plan_abc_step_banner_click_rate",
        "ev_plan_abc_step_banner_conversion_rate",
    ]
    assert updated["satisfied_evidence_requirements"] == ["click_rate", "conversion_rate"]
    assert updated["completed_by"] == "evidence"


def test_scoped_task_ignores_claim_key_without_evidence_requirement(tmp_path):
    mgr = TaskManager(tasks_dir=tmp_path / "tasks")
    plan = mgr.create_plan(session_id="s1", goal="Analyze banner", source="analysis_plan")
    task = mgr.create(
        "Analyze banner metrics",
        session_id="s1",
        plan_id=plan["id"],
        plan_version=plan["version"],
        analysis_plan_id="plan_abc",
        step_id="step_banner",
        dataset_contract_ids=["contract_banner"],
        evidence_requirements=["click_rate"],
    )
    evidence = _canonical_evidence(evidence_requirement="click_rate")
    evidence.pop("evidence_requirement")

    completed = mgr.complete_matching_tasks_from_evidence(session_id="s1", evidence=evidence)

    assert completed == []
    updated = mgr.get(task["id"])
    assert updated["status"] == "pending"
    assert updated["evidence_ids"] == []
    assert updated["satisfied_evidence_requirements"] == []


def test_legacy_text_task_not_completed_while_scoped_stage3c0b_task_active(tmp_path):
    mgr = TaskManager(tasks_dir=tmp_path / "tasks")
    plan = mgr.create_plan(session_id="s1", goal="Analyze banner", source="analysis_plan")
    scoped = mgr.create(
        "Scoped banner metric",
        session_id="s1",
        plan_id=plan["id"],
        plan_version=plan["version"],
        analysis_plan_id="plan_abc",
        step_id="step_banner",
        dataset_contract_ids=["contract_banner"],
        evidence_requirements=["conversion_rate"],
    )
    legacy = mgr.create(
        "Legacy click-rate task",
        session_id="s1",
        plan_id=plan["id"],
        plan_version=plan["version"],
        expected_output="click_rate summary",
        evidence_requirements=["click_rate"],
    )

    completed = mgr.complete_matching_tasks_from_evidence(
        session_id="s1",
        evidence=_canonical_evidence(evidence_requirement="click_rate"),
    )

    assert completed == []
    assert mgr.get(scoped["id"])["status"] == "pending"
    assert mgr.get(legacy["id"])["status"] == "pending"
