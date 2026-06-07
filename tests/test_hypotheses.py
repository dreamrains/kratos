from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.hypotheses import (
    build_hypothesis_set,
    hydrate_hypothesis_refs,
    persist_hypothesis_set,
    update_hypotheses_from_evidence,
)


def _state() -> AnalysisSessionState:
    state = AnalysisSessionState(session_id="hypothesis_tests", data_state="data_loaded")
    state.dataset_contracts = [{
        "id": "contract_sales",
        "dataset": "sales",
        "quality": {"status": "ready", "score": 96},
        "field_roles": {
            "date": ["date"],
            "metrics": ["revenue", "orders"],
            "rate_metrics": ["conversion_rate"],
            "dimensions": ["channel"],
        },
        "supported_analyses": ["period_compare", "trend"],
    }]
    return state


def _entry_decision(route: str = "period_compare") -> dict:
    return {
        "decision": "direct_analysis",
        "dataset": "sales",
        "route": route,
        "limitations": ["Requires comparable periods"],
    }


def test_period_compare_generates_competing_hypotheses_with_requirements():
    hypothesis_set = build_hypothesis_set("compare revenue by period", _entry_decision(), _state())

    assert hypothesis_set["dataset"] == "sales"
    assert hypothesis_set["route"] == "period_compare"
    assert len(hypothesis_set["hypotheses"]) == 4
    assert {hypothesis["status"] for hypothesis in hypothesis_set["hypotheses"]} == {"proposed"}
    assert hypothesis_set["hypotheses"][0]["verification_level"] == "verifiable"
    assert hypothesis_set["hypotheses"][0]["evidence_requirements"][0] == {
        "kind": "metric",
        "field": "revenue",
        "required": True,
    }
    assert "alternative" in hypothesis_set["hypotheses"][1]["tags"]
    assert "baseline" in hypothesis_set["hypotheses"][-1]["tags"]


def test_retention_hypothesis_is_not_verifiable_without_user_grain():
    entry_decision = {
        "decision": "request_data",
        "dataset": "sales",
        "route": "user_level_retention",
        "limitations": ["aggregate grain"],
    }

    hypothesis_set = build_hypothesis_set("analyze user retention", entry_decision, _state())

    assert len(hypothesis_set["hypotheses"]) == 1
    hypothesis = hypothesis_set["hypotheses"][0]
    assert hypothesis["status"] == "unsupported_by_data"
    assert hypothesis["verification_level"] == "not_verifiable"
    assert "aggregate grain" in hypothesis["limitations"]
    assert hypothesis_set["status_summary"] == {"unsupported_by_data": 1}


def test_hypothesis_set_persists_as_artifact_and_hydrates(tmp_path, monkeypatch):
    from data_agent.config import get_config

    cfg = get_config()
    monkeypatch.setattr(cfg, "sessions_dir", tmp_path / "sessions")
    hypothesis_set = build_hypothesis_set("compare revenue by period", _entry_decision(), _state())

    ref = persist_hypothesis_set("hyp_persist", hypothesis_set)
    hydrated = hydrate_hypothesis_refs([ref])

    assert ref["count"] == 4
    assert hydrated[0]["hypotheses"][0]["claim"] == hypothesis_set["hypotheses"][0]["claim"]


def test_update_hypotheses_from_evidence_marks_supported_and_inconclusive():
    hypothesis_set = build_hypothesis_set("compare revenue by period", _entry_decision(), _state())
    first = hypothesis_set["hypotheses"][0]
    evidence = [{
        "id": "ev_1",
        "claim": first["claim"],
        "result_summary": "The observed evidence matches the first hypothesis.",
    }]

    updated = update_hypotheses_from_evidence(hypothesis_set, evidence)

    assert updated["hypotheses"][0]["status"] == "supported"
    assert updated["hypotheses"][0]["supporting_evidence_ids"] == ["ev_1"]
    assert updated["hypotheses"][1]["status"] == "inconclusive"
    assert updated["status_summary"]["supported"] == 1
    assert updated["status_summary"]["inconclusive"] >= 1
