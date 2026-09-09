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

    # Contract update (P1 / D08 / H04): text overlap alone is a candidate
    # association, never a support relation. Original requirement marked the
    # hypothesis "supported" from token overlap; the confirmed product
    # principle keeps it undetermined until a structured relation exists.
    assert updated["hypotheses"][0]["status"] == "inconclusive"
    assert updated["hypotheses"][0]["related_evidence_ids"] == ["ev_1"]
    assert updated["hypotheses"][0]["supporting_evidence_ids"] == []
    assert updated["hypotheses"][1]["status"] == "inconclusive"
    assert updated["status_summary"].get("supported") is None
    assert updated["status_summary"]["inconclusive"] >= 1


# ── P1 (D08): prevent false hypothesis upgrades (H01–H05) ──


def _evidence(evidence_id: str, claim: str, **overrides) -> dict:
    record = {"id": evidence_id, "claim": claim, "result_summary": claim, "dataset": "sales"}
    record.update(overrides)
    return record


def test_h01_negated_claim_text_does_not_mark_supported():
    hypothesis_set = build_hypothesis_set("compare revenue by period", _entry_decision(), _state())
    first = hypothesis_set["hypotheses"][0]
    negated = f"It is false that {first['claim']}"

    updated = update_hypotheses_from_evidence(
        hypothesis_set,
        [_evidence("ev_negated", negated)],
    )

    hypothesis = updated["hypotheses"][0]
    assert hypothesis["status"] != "supported"
    assert hypothesis["supporting_evidence_ids"] == []


def test_h02_identical_text_from_other_dataset_is_not_related():
    hypothesis_set = build_hypothesis_set("compare revenue by period", _entry_decision(), _state())
    first = hypothesis_set["hypotheses"][0]

    updated = update_hypotheses_from_evidence(
        hypothesis_set,
        [_evidence("ev_other_dataset", first["claim"], dataset="orders")],
    )

    hypothesis = updated["hypotheses"][0]
    assert hypothesis["status"] != "supported"
    assert hypothesis["supporting_evidence_ids"] == []
    assert hypothesis["related_evidence_ids"] == []


def test_h03_same_dataset_evidence_from_other_plan_is_not_related():
    state = _state()
    state.analysis_plan = {"id": "plan_current", "goal": "Compare periods"}
    hypothesis_set = build_hypothesis_set("compare revenue by period", _entry_decision(), state)
    first = hypothesis_set["hypotheses"][0]

    updated = update_hypotheses_from_evidence(
        hypothesis_set,
        [_evidence("ev_other_plan", first["claim"], plan_id="plan_other")],
    )

    hypothesis = updated["hypotheses"][0]
    assert hypothesis["status"] != "supported"
    assert hypothesis["supporting_evidence_ids"] == []
    assert hypothesis["related_evidence_ids"] == []


def test_h04_pure_text_overlap_stays_candidate_relation():
    hypothesis_set = build_hypothesis_set("compare revenue by period", _entry_decision(), _state())
    first = hypothesis_set["hypotheses"][0]

    updated = update_hypotheses_from_evidence(
        hypothesis_set,
        [_evidence("ev_text_only", first["claim"])],
    )

    hypothesis = updated["hypotheses"][0]
    assert hypothesis["status"] == "inconclusive"
    assert hypothesis["related_evidence_ids"] == ["ev_text_only"]
    assert hypothesis["supporting_evidence_ids"] == []
    assert hypothesis["conflicting_evidence_ids"] == []


def test_h05_stale_supporting_ids_do_not_survive_recompute():
    hypothesis_set = build_hypothesis_set("compare revenue by period", _entry_decision(), _state())
    stale = dict(hypothesis_set["hypotheses"][0])
    stale["status"] = "supported"
    stale["supporting_evidence_ids"] = ["ev_gone"]
    hypothesis_set["hypotheses"][0] = stale

    updated = update_hypotheses_from_evidence(hypothesis_set, [])

    hypothesis = updated["hypotheses"][0]
    assert hypothesis["status"] != "supported"
    assert hypothesis["supporting_evidence_ids"] == []


def test_supported_hypothesis_demotes_when_evidence_becomes_unrelated():
    hypothesis_set = build_hypothesis_set("compare revenue by period", _entry_decision(), _state())
    stale = dict(hypothesis_set["hypotheses"][0])
    stale["status"] = "supported"
    stale["supporting_evidence_ids"] = ["ev_gone"]
    hypothesis_set["hypotheses"][0] = stale

    updated = update_hypotheses_from_evidence(
        hypothesis_set,
        [_evidence("ev_unrelated", "Conversion funnel improved markedly")],
    )

    hypothesis = updated["hypotheses"][0]
    assert hypothesis["status"] != "supported"
    assert hypothesis["supporting_evidence_ids"] == []
    assert "ev_gone" not in hypothesis.get("related_evidence_ids", [])


# ── P5 (D08/D09): structured hypothesis evidence relations (H06–H09, H12) ──


def _relation_evidence(
    evidence_id: str,
    hypothesis_id: str,
    relation: str,
    metric: str,
    observed: str,
    *,
    delta: float,
    claim: str = "structured measurement",
    dataset: str = "sales",
    method: str = "period compare",
):
    return {
        "id": evidence_id,
        "claim": claim,
        "result_summary": claim,
        "dataset": dataset,
        "method": method,
        "measurements": [{
            "metric": metric,
            "definition": f"{metric} aggregated per period",
            "value": max(abs(delta), 1),
            "unit": "currency",
            "grain": "period",
            "population_scope": "all records",
            "time_scope": "2026-08",
            "method": method,
            "denominator": "period days",
            "limitations": [],
            "delta": delta,
        }],
        "competing_hypotheses": [{
            "hypothesis_id": hypothesis_id,
            "relation": relation,
            "metric": metric,
            "observed": observed,
        }],
    }


class TestHypothesisRelations:

    def test_h06_valid_structured_relation_marks_supported(self):
        state = _state()
        hypothesis_set = build_hypothesis_set("compare revenue by period", _entry_decision(), state)
        primary = hypothesis_set["hypotheses"][0]

        updated = update_hypotheses_from_evidence(hypothesis_set, [
            _relation_evidence(
                "ev_h06", primary["id"], "supports", "revenue", "increased",
                delta=112, claim="Revenue increased between the compared periods.",
            ),
        ])

        hypothesis = updated["hypotheses"][0]
        assert hypothesis["status"] == "supported"
        assert hypothesis["supporting_evidence_ids"] == ["ev_h06"]
        assert hypothesis["evidence_relations"]
        relation = hypothesis["evidence_relations"][0]
        assert relation["evidence_id"] == "ev_h06"
        assert relation["relation"] == "supports"
        assert relation["basis"]

    def test_h07_valid_refuting_relation_marks_refuted_and_no_relation_stays_open(self):
        hypothesis_set = build_hypothesis_set("compare revenue by period", _entry_decision(), _state())
        primary = hypothesis_set["hypotheses"][0]

        refuted = update_hypotheses_from_evidence(hypothesis_set, [
            _relation_evidence(
                "ev_flat", primary["id"], "refutes", "revenue", "flat",
                delta=0, claim="Revenue was flat between the compared periods.",
            ),
        ])
        assert refuted["hypotheses"][0]["status"] == "refuted"
        assert refuted["hypotheses"][0]["conflicting_evidence_ids"] == ["ev_flat"]

        # “无支持”不能充当反证：没有任何结构化关系时假设保持未决
        open_set = build_hypothesis_set("compare revenue by period", _entry_decision(), _state())
        untouched = update_hypotheses_from_evidence(open_set, [
            _evidence("ev_none", "unrelated descriptive text"),
        ])
        assert untouched["hypotheses"][0]["status"] != "refuted"

    def test_h08_simultaneous_support_and_refutation_is_contested(self):
        hypothesis_set = build_hypothesis_set("compare revenue by period", _entry_decision(), _state())
        primary = hypothesis_set["hypotheses"][0]

        updated = update_hypotheses_from_evidence(hypothesis_set, [
            _relation_evidence(
                "ev_up", primary["id"], "supports", "revenue", "increased",
                delta=112, claim="Revenue increased.",
            ),
            _relation_evidence(
                "ev_flat", primary["id"], "refutes", "revenue", "flat",
                delta=0, claim="Revenue was flat in the matched window.",
            ),
        ])

        hypothesis = updated["hypotheses"][0]
        assert hypothesis["status"] == "contested"
        assert hypothesis["supporting_evidence_ids"] == ["ev_up"]
        assert hypothesis["conflicting_evidence_ids"] == ["ev_flat"]

    def test_h09_chinese_and_english_evidence_agree_via_structure(self):
        set_en = build_hypothesis_set("compare revenue by period", _entry_decision(), _state())
        set_zh = build_hypothesis_set("对比两个周期的收入", _entry_decision(), _state())
        primary_en = set_en["hypotheses"][0]
        primary_zh = set_zh["hypotheses"][0]

        updated_en = update_hypotheses_from_evidence(set_en, [
            _relation_evidence(
                "ev_en", primary_en["id"], "supports", "revenue", "increased",
                delta=112, claim="Revenue increased between the compared periods.",
            ),
        ])
        updated_zh = update_hypotheses_from_evidence(set_zh, [
            _relation_evidence(
                "ev_zh", primary_zh["id"], "supports", "revenue", "increased",
                delta=112, claim="对比周期内收入上升。",
            ),
        ])

        assert updated_en["hypotheses"][0]["status"] == updated_zh["hypotheses"][0]["status"] == "supported"

    def test_descriptive_relation_cannot_support_causal_alternative(self):
        hypothesis_set = build_hypothesis_set("compare revenue by period", _entry_decision(), _state())
        causal = hypothesis_set["hypotheses"][1]  # “因为订单量变化导致收入变化”

        updated = update_hypotheses_from_evidence(hypothesis_set, [
            _relation_evidence(
                "ev_orders", causal["id"], "supports", "orders", "increased",
                delta=40, claim="Orders increased between periods.",
            ),
        ])

        hypothesis = updated["hypotheses"][1]
        assert hypothesis["status"] != "supported"
        assert hypothesis["supporting_evidence_ids"] == []

    def test_h12_prompt_brief_marks_open_alternatives_without_fabricated_exclusion(self):
        from data_agent.agent.hypotheses import hypotheses_prompt_brief

        state = _state()
        hypothesis_set = build_hypothesis_set("compare revenue by period", _entry_decision(), state)
        primary = hypothesis_set["hypotheses"][0]
        updated = update_hypotheses_from_evidence(hypothesis_set, [
            _relation_evidence(
                "ev_h12", primary["id"], "supports", "revenue", "increased",
                delta=112, claim="Revenue increased between the compared periods.",
            ),
        ])
        state.hypothesis_sets = [{
            "id": updated["id"],
            "dataset": updated["dataset"],
            "route": updated["route"],
            "count": len(updated["hypotheses"]),
            "artifact_path": "",
            "_hydrated_for_test": updated,
        }]

        brief = hypotheses_prompt_brief(state, hydrated=[updated])

        assert "supported" in brief
        assert "未决" in brief or "inconclusive" in brief
        assert "区分" in brief
        assert "已排除" not in brief
