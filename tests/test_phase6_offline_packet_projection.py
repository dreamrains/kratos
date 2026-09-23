"""Offline-only projection of existing artifacts into the same packet digest."""

import json

import pytest

from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.publication_synthesis import (
    build_publication_packet, extract_publication_fact_groups, publication_contract, publication_packet_prompt,
    render_trusted_core_preview,
)
from data_agent.config import get_config
from data_agent.session.history import register_artifact


def _state(session_id="offline_projection"):
    state = AnalysisSessionState(session_id)
    state.tool_receipts = [{
        "id": "tr_data", "tool_name": "run_python", "result_sha256": "sha256:data",
        "result_preview": "computed", "publication_facts": [{"path": "revenue.value", "value": "100"}],
        "publication_contract": publication_contract("run_python", {"source_rows": 12}),
        "data_identities": {},
    }]
    return state


def _packet(state, **options):
    return build_publication_packet(
        state, user_input="分析收入", substantive_tools={"run_python", "compare_periods"},
        receipt_ids=["tr_data", "tr_chart"], **options,
    )


def test_projection_is_default_off_and_offline_packet_cannot_be_model_prompt(tmp_path):
    state = _state()
    normal = _packet(state)
    assert "offline_trust_projection" not in normal
    assert "<publication_synthesis_packet>" in publication_packet_prompt(normal)
    projected = _packet(state, offline_trust_projection=True)
    assert projected["offline_trust_projection"] == {"charts": [], "hypotheses": []}
    assert projected["snapshot_digest"] != normal["snapshot_digest"]
    with pytest.raises(ValueError, match="offline"):
        publication_packet_prompt(projected)


def test_current_six_source_synthesis_facts_enter_only_explicit_offline_packet():
    state = _state("six_source_projection")
    state.tool_receipts.append({
        "id": "tr_six", "tool_name": "synthesize_time_series",
        "result_sha256": "sha256:six", "result_preview": "six aligned sources",
        "data_identities": {"combined": {"version_id": "v_current"}},
        "publication_facts": [
            {"path": f"sources.source_{index}.amount.day_2", "value": str(index * 11)}
            for index in range(1, 7)
        ],
        "publication_contract": publication_contract(
            "synthesize_time_series", {"aligned_rows": 2},
        ),
    })
    normal = build_publication_packet(
        state, user_input="保留全部六个来源", substantive_tools={"run_python"},
        receipt_ids=["tr_data", "tr_six"],
    )
    assert [source["receipt_id"] for source in normal["sources"]] == ["tr_data"]
    projected = build_publication_packet(
        state, user_input="保留全部六个来源", substantive_tools={"run_python"},
        receipt_ids=["tr_data", "tr_six"], offline_trust_projection=True,
    )
    assert projected["snapshot_digest"] != normal["snapshot_digest"]
    synthesis = next(source for source in projected["sources"] if source["receipt_id"] == "tr_six")
    assert len(synthesis["facts"]) == 6
    preview = render_trusted_core_preview(projected, None)
    assert "sources.source_1.amount.day_2" in preview["text"]
    assert "sources.source_6.amount.day_2" in preview["text"]
    assert preview["accepted_claim_ids"] == []
    without_explicit_turn = build_publication_packet(
        state, user_input="保留全部六个来源", substantive_tools={"run_python"},
        offline_trust_projection=True,
    )
    assert all(source["receipt_id"] != "tr_six" for source in without_explicit_turn["sources"])
    without_selected_receipt = build_publication_packet(
        state, user_input="保留全部六个来源", substantive_tools={"run_python"},
        receipt_ids=["tr_data"], offline_trust_projection=True,
    )
    assert all(source["receipt_id"] != "tr_six" for source in without_selected_receipt["sources"])


def test_current_registered_chart_is_previewed_as_artifact_not_business_fact(tmp_path):
    cfg = get_config()
    old = cfg.sessions_dir
    cfg.sessions_dir = tmp_path / "sessions"
    try:
        state = _state("chart_projection")
        chart_path = "sessions/chart_projection/charts/current.html"
        chart_file = cfg.sessions_resolved / "chart_projection" / "charts" / "current.html"
        chart_file.parent.mkdir(parents=True)
        chart_file.write_text("<html>chart</html>", encoding="utf-8")
        register_artifact(state.session_id, chart_path, "chart", "current chart")
        state.tool_receipts.append({
            "id": "tr_chart", "tool_name": "create_chart",
            "result_preview": f"Chart saved: {chart_path}", "result_sha256": "sha256:chart",
            "data_identities": {},
        })
        packet = _packet(state, offline_trust_projection=True)
        charts = packet["offline_trust_projection"]["charts"]
        assert len(charts) == 1
        assert {key: charts[0][key] for key in ("path", "receipt_id", "status")} == {
            "path": chart_path, "receipt_id": "tr_chart", "status": "artifact_only",
        }
        assert charts[0]["sha256"].startswith("sha256:")
        preview = render_trusted_core_preview(packet, None)
        assert f"[[chart:{chart_path}]]" in preview["text"]
        assert "不证明图中分析结论" in preview["text"]
        assert preview["accepted_claim_ids"] == []
        unselected = build_publication_packet(
            state, user_input="分析收入", substantive_tools={"run_python"},
            receipt_ids=["tr_data"], offline_trust_projection=True,
        )
        assert unselected["offline_trust_projection"]["charts"] == []
        no_turn_scope = build_publication_packet(
            state, user_input="分析收入", substantive_tools={"run_python"},
            offline_trust_projection=True,
        )
        assert no_turn_scope["offline_trust_projection"] == {"charts": [], "hypotheses": []}
    finally:
        cfg.sessions_dir = old


def test_chart_from_other_session_or_unselected_receipt_is_not_projected(tmp_path):
    cfg = get_config()
    old = cfg.sessions_dir
    cfg.sessions_dir = tmp_path / "sessions"
    try:
        state = _state("chart_isolation")
        foreign = "sessions/other/charts/old.html"
        state.tool_receipts.append({
            "id": "tr_chart", "tool_name": "create_chart",
            "result_preview": f"Chart saved: {foreign}", "result_sha256": "sha256:old",
        })
        assert _packet(state, offline_trust_projection=True)["offline_trust_projection"]["charts"] == []
        state.tool_receipts[-1]["result_preview"] = "Chart saved: sessions/chart_isolation/charts/missing.html"
        assert _packet(state, offline_trust_projection=True)["offline_trust_projection"]["charts"] == []
    finally:
        cfg.sessions_dir = old


def test_current_plan_relation_is_recomputed_from_bound_evidence(tmp_path):
    cfg = get_config()
    old = cfg.sessions_dir
    cfg.sessions_dir = tmp_path / "sessions"
    try:
        state = _state("hyp_projection")
        comparison = {
            "period_a": {"range": ["2026-01-01", "2026-01-02"], "day_count": 2},
            "period_b": {"range": ["2026-01-03", "2026-01-04"], "day_count": 2},
            "metrics": {"revenue": {"period_a": 10, "period_b": 20, "diff": 10}},
        }
        state.tool_receipts[0].update({
            "tool_name": "compare_periods",
            "publication_fact_groups": extract_publication_fact_groups(comparison, receipt_id="tr_data")["groups"],
            "publication_contract": publication_contract("compare_periods", comparison),
        })
        state.analysis_plan = {"id": "plan_current"}
        hypothesis = {
            "id": "hyp_set", "dataset": "sales", "route": "period_compare", "plan_id": "plan_current",
            "hypotheses": [
                {"id": "hyp_1", "claim": "revenue changed between periods", "status": "proposed",
                 "claim_type": "descriptive", "decision_rule": {"metrics": ["revenue"], "predicate": "changed"},
                 "verification_level": "verifiable", "evidence_requirements": []},
                {"id": "hyp_causal", "claim": "revenue changed because of intervention", "status": "proposed",
                 "claim_type": "causal", "decision_rule": {"metrics": ["revenue"], "predicate": ""},
                 "verification_level": "verifiable", "evidence_requirements": []},
                {"id": "hyp_stat", "claim": "revenue difference is significant", "status": "proposed",
                 "claim_type": "statistical", "decision_rule": {"metrics": ["revenue"], "predicate": ""},
                 "verification_level": "verifiable", "evidence_requirements": []},
            ],
        }
        path = cfg.sessions_resolved / state.session_id / "tool_outputs" / "hyp_set.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(hypothesis), encoding="utf-8")
        state.hypothesis_sets = [{"id": "hyp_set", "plan_id": "plan_current",
                                  "dataset": "sales", "route": "period_compare", "artifact_path": str(path)}]
        state.evidence_records = [{
            "id": "ev_current", "plan_id": "plan_current", "dataset": "sales",
            "tool_receipt_ids": ["tr_data"],
            "result_bindings": [{"receipt_id": "tr_data", "result_sha256": "sha256:data", "data_identities": {}}],
            "measurements": [{"metric": "revenue", "delta": 10, "p_value": 0.01}],
            "competing_hypotheses": [
                {"hypothesis_id": hypothesis_id, "relation": "supports",
                 "metric": "revenue", "observed": "increased"}
                for hypothesis_id in ("hyp_1", "hyp_causal", "hyp_stat")
            ],
            "method": "causal", "claim": "revenue changed between periods",
        }]
        packet = _packet(state, offline_trust_projection=True)
        rows = packet["offline_trust_projection"]["hypotheses"]
        assert len(rows) == 3
        assert {key: rows[0][key] for key in (
            "hypothesis_id", "set_id", "status", "supporting_evidence_ids", "conflicting_evidence_ids",
        )} == {"hypothesis_id": "hyp_1", "set_id": "hyp_set", "status": "supported",
              "supporting_evidence_ids": ["ev_current"], "conflicting_evidence_ids": []}
        assert rows[0]["artifact_sha256"].startswith("sha256:")
        assert all(row["status"] != "supported" for row in rows[1:])
        assert all(row["supporting_evidence_ids"] == [] for row in rows[1:])
        assert "hyp_1" in render_trusted_core_preview(packet, None)["text"]
        state.evidence_records[0]["measurements"][0]["delta"] = 99
        mismatched = _packet(state, offline_trust_projection=True)["offline_trust_projection"]["hypotheses"]
        assert mismatched[0]["status"] != "supported"
        assert mismatched[0]["supporting_evidence_ids"] == []
        state.evidence_records[0]["measurements"][0]["delta"] = 10
        state.evidence_records[0]["result_bindings"][0]["result_sha256"] = "sha256:stale"
        stale = _packet(state, offline_trust_projection=True)["offline_trust_projection"]["hypotheses"]
        assert stale[0]["status"] != "supported"
        assert stale[0]["supporting_evidence_ids"] == []
        state.analysis_plan = {"id": "plan_other"}
        assert _packet(state, offline_trust_projection=True)["offline_trust_projection"]["hypotheses"] == []
    finally:
        cfg.sessions_dir = old
