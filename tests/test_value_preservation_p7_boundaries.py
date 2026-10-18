"""P7 independent safety oracles; failures block dependent browser acceptance.

These exercise real host gates with structured fixtures, not a browser or a
Provider. Keep the expected safety behavior when repairing the implementation.
"""
from tests.support.rendered_text import visible_text, table_rows, has_pair, has_number, has_record
import hashlib
import json

import pytest

from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.hypotheses import (
    build_hypothesis_set,
    update_hypotheses_from_evidence,
)
from tests.test_trusted_publication_semantics import engine,execute
from tests.test_trusted_publication_runtime import request
from data_agent.agent.publication.runtime import snapshot_for_turn
from data_agent.agent.publication.service import PublicationService
from data_agent.agent.publication.contracts import encode
import pandas as pd


def _p7_actual(loop,include_b):
    loop.context.workspace.add("channel_A",pd.DataFrame({"day":range(1,8),"retention":[.08]*7}))
    request(loop,"解释渠道 A 的留存边界",{'kind': 'series', 'scope': {'datasets': ['channel_A'], 'metrics': ['retention']}},kind="result",purposes=["interpretation"])
    execute(loop,"curve_fitting",{"name":"channel_A","x_col":"day","y_col":"retention"})
    if include_b:
        loop.context.workspace.add("channel_B",pd.DataFrame({"day":range(1,31),"retention":[.08]*30}))
        request(loop,"解释渠道 B 的留存",{'kind': 'series', 'scope': {'datasets': ['channel_B'], 'metrics': ['retention']}},kind="result",purposes=["interpretation"])
        from data_agent.agent.confirmation.runtime import build_action_registry,build_measurement_mapping_candidate
        from data_agent.agent.confirmation.service import ConfirmationService
        from data_agent.session.history import load_canonical_history
        from data_agent.config import get_config
        h=load_canonical_history(loop.session_id)
        candidate=build_measurement_mapping_candidate(session_id=loop.session_id,turn_id="runtime_turn",workspace=loop.context.workspace,canonical_history=h,
            source_message_ref=h.messages[-1]["request_id"],exact_span="渠道 B 的留存",dataset="channel_B",column="retention",x_column="day",x_start=1,x_end=30)
        service=ConfirmationService(get_config().sessions_resolved,action_registry=build_action_registry());service.request(candidate)
        service.respond(loop.session_id,candidate.confirmation_id,"fraction",service.checkpoint(loop.session_id).version,"b-scale")
        execute(loop,"curve_fitting",{"name":"channel_B","x_col":"day","y_col":"retention"})
    return snapshot_for_turn(loop)


def _p7_source_answer(snapshot,text,reject):
    host=snapshot.as_dict();requirements=host["requirements"]
    section=[]
    for r in requirements:
        section.append({"requirement_ids":[r["id"]],"parts":[{"kind":"claim","ref":cid} for cid in r["claim_ids"]]})
    a=next(r for r in requirements if any(c["scope"]["dataset"]=="channel_A" and c["id"] in r["claim_ids"] for c in host["claims"]))
    bpoint=next((c for c in host["claims"] if c["scope"]["dataset"]=="channel_B" and c["basis_refs"][0]["result_path"]==["points",29,"y"]),None)
    if reject:
        # Even a legitimate B observation cannot be assigned to A's obligation.
        section.append({"requirement_ids":[a["id"]],"parts":[{"kind":"claim","ref":bpoint["id"] if bpoint else "absent-A-D30"}]})
    calls=[]
    # Preserve the original natural phrasing as the open-span oracle input;
    # these fixed review decisions test localization, not classifier quality.
    owner=next(i for i,r in enumerate(requirements) if bpoint and bpoint["id"] in r["claim_ids"]) if bpoint and not reject else 0
    section[owner]["parts"].append({"kind":"text","purpose":"interpretation","text":text,"claim_refs":[bpoint["id"]] if bpoint and not reject else []})
    def audit(q):
        calls.append(q)
        return {"schema":"publication_audit.v2","snapshot_digest":q["snapshot_digest"],"draft_digest":q["draft_digest"],
            "decisions":[{"part_id":part["part_id"],"disposition":"reject" if reject else "accept","reason":"frozen original source/window oracle","evidence_refs":part["requirement_ids"]+part["claim_refs"]} for part in q["parts"]]}
    answer=PublicationService(snapshot,auditor=audit).publish(encode({"schema":"answer_bindings.v2","snapshot_digest":snapshot.digest,"sections":section})).as_dict()
    assert len(calls)==1 and answer["source_snapshot"]["claims"]==host["claims"]
    if reject:
        assert text not in answer["body"]
        assert any(i["code"] in {"unknown_claim_ref","unbound_deliverable_ref"} for i in answer["issues"])
    else:
        assert text in answer["body"] and not answer["issues"]
    if bpoint:
        assert bpoint["value"]==.08 and bpoint["unit"]=="proportion"
        trace=next(t for t in answer["render_trace"] if t["ref"]==bpoint["id"] and t["disposition"]=="accepted")
        assert "8%" in visible_text(trace["rendered_text"]) and "channel_B" in visible_text(trace["rendered_text"])
    assert not any(c["scope"]["dataset"]=="channel_A" and c["basis_refs"][0]["result_path"]==["points",29,"y"] for c in host["claims"])
    return answer




@pytest.mark.parametrize("include_b,text,should_reject", [
    pytest.param(False, "渠道 A 不能预测 D30，建议继续收集至第30天。", False, id="P7-N-control-boundary"),
    pytest.param(False, "渠道 A 的 D30 留存预计为 5%。", True, id="P7-N-control-unobserved"),
    pytest.param(True, "渠道 B 的 D30 留存为 8%。", False, id="P7-N-control-observed-b"),
    pytest.param(True, "渠道 A 的 D30 留存预计为 5%。", True, id="P7-N-cross-source-bypass"),
])
def test_p7_prediction_is_bound_to_its_source(engine,include_b,text,should_reject,record_property):
    loop,_=engine
    snapshot=_p7_actual(loop,include_b)
    answer=_p7_source_answer(snapshot,text,should_reject)
    record_property("current_snapshot",json.dumps(snapshot.as_dict(),ensure_ascii=False))
    record_property("original_input",text)
    record_property("actual_trace",json.dumps(answer["render_trace"],ensure_ascii=False))


@pytest.mark.parametrize("metric,delta,relation,expected", [
    pytest.param("revenue", 10, "supports", "supported", id="P7-H-control-support"),
    pytest.param("revenue", 0, "refutes", "refuted", id="P7-H-control-refute"),
    pytest.param("revenue", 0, "supports", "not_supported", id="P7-H-flat-cannot-support-change"),
    pytest.param("revenue", 10, "refutes", "not_refuted", id="P7-H-change-cannot-refute-change"),
    pytest.param("orders", 10, "supports", "not_supported", id="P7-H-wrong-metric"),
])
def test_p7_relation_must_satisfy_target_predicate(metric, delta, relation, expected, record_property):
    state = AnalysisSessionState(session_id="p7_hypothesis_oracle", data_state="data_loaded")
    state.analysis_plan = {"id": "plan_p7"}
    state.dataset_contracts = [{
        "dataset": "sales",
        "field_roles": {"date": ["date"], "metrics": ["revenue", "orders"]},
    }]
    hypothesis_set = build_hypothesis_set(
        "compare revenue by period",
        {"decision": "direct_analysis", "dataset": "sales", "route": "period_compare"},
        state,
    )
    target = hypothesis_set["hypotheses"][0]
    assert target["claim"] == "revenue changed between the compared periods in sales."
    observed = "increased" if delta > 0 else "flat"
    evidence = {
        "id": "ev_p7", "dataset": "sales", "plan_id": "plan_p7",
        "claim": f"{metric} delta is {delta} in the compared periods.",
        "result_summary": f"{metric}: before=100, after={100 + delta}",
        "method": "compare_periods",
        "measurements": [{"metric": metric, "delta": delta, "value": 100 + delta}],
        "competing_hypotheses": [{
            "hypothesis_id": target["id"], "relation": relation,
            "metric": metric, "observed": observed,
        }],
    }
    # This is the pure predicate oracle. Receipt identity/value verification
    # is exercised separately; model measurements alone no longer authorize a
    # supported/refuted status.
    verified = {"ev_p7": {metric: {
        "value": delta, "direction": observed, "receipt_id": "tr_host_verified_for_predicate_test",
    }}}
    updated = update_hypotheses_from_evidence(
        hypothesis_set, [evidence], verified_measurements=verified,
    )
    actual = updated["hypotheses"][0]
    record_property("hypothesis", json.dumps(target, ensure_ascii=False))
    record_property("evidence", json.dumps(evidence, ensure_ascii=False))
    record_property("actual", json.dumps(actual, ensure_ascii=False))
    if expected.startswith("not_"):
        assert actual["status"] != expected[4:], (
            "The relation label is a model proposal; the host must check the "
            f"target metric and predicate, not just direction. Actual: {actual}"
        )
    else:
        assert actual["status"] == expected


# ── P7/R1+R2 补充反例（修复后新增；保持与上方 oracle 同一判定链） ──


@pytest.mark.parametrize("text,should_reject", [
    # 交换顺序：B 在前，A 的外推仍拒绝，B 的事实仍放行
    pytest.param("渠道 B 的 D30 留存为 8%。", False, id="P7R1-swapped-b-fact"),
    pytest.param("渠道 A 的 D30 留存预计为 5%。", True, id="P7R1-swapped-a-extrapolation"),
    # 未指明来源：不是所有来源都观测到 D30 → 缺少绑定，进入修订
    pytest.param("D30 留存为 8%。", True, id="P7R1-unspecified-source"),
    # 混合句：边界句 + 同段预测断言
    pytest.param("渠道 A 不能预测 D30，但预计 D30 大约是 5%。", True, id="P7R1-mixed-boundary-prediction"),
])
def test_p7r1_supplementary_source_binding(engine,text,should_reject):
    loop,_=engine
    snapshot=_p7_actual(loop,True)
    # Source order does not authorize a new dataset/window pair.
    host=snapshot.as_dict();host["claims"].reverse()
    from data_agent.agent.publication.contracts import HostSnapshot
    _p7_source_answer(HostSnapshot.freeze(**host),text,should_reject)


def test_p7r1_same_name_different_ranges_treated_ambiguous(engine):
    from data_agent.agent.publication.native import resolve_native_claims
    loop,_=engine
    loop.context.workspace.add("retention_v2",pd.DataFrame({"day":range(1,31),"retention":[.08]*30}))
    request(loop,"当前 retention_v2 的留存边界",{'kind': 'series', 'scope': {'datasets': ['retention_v2'], 'metrics': ['retention']}})
    old_rid,_=execute(loop,"curve_fitting",{"name":"retention_v2","x_col":"day","y_col":"retention"})
    loop.context.workspace.add("retention_v2",pd.DataFrame({"day":range(1,8),"retention":[.08]*7}))
    execute(loop,"curve_fitting",{"name":"retention_v2","x_col":"day","y_col":"retention"})
    with pytest.raises(ValueError):resolve_native_claims(session_id=loop.session_id,receipt_id=old_rid)
    snapshot=snapshot_for_turn(loop)
    assert not any(c["basis_refs"][0]["receipt_id"]==old_rid for c in snapshot.as_dict()["claims"])
    assert not any(c["basis_refs"][0]["result_path"]==["points",29,"y"] for c in snapshot.as_dict()["claims"])
    row=snapshot.as_dict()["requirements"][0]
    answer=PublicationService(snapshot).publish(encode({"schema":"answer_bindings.v2","snapshot_digest":snapshot.digest,
        "sections":[{"requirement_ids":[row["id"]],"parts":[{"kind":"claim","ref":"old-same-name-D30"}]}]})).as_dict()
    assert any(i["code"]=="unknown_claim_ref" for i in answer["issues"])


def _p7_relation_state():
    state = AnalysisSessionState(session_id="p7r2_predicates", data_state="data_loaded")
    state.analysis_plan = {"id": "plan_p7"}
    state.dataset_contracts = [{
        "dataset": "sales",
        "field_roles": {"date": ["date"], "metrics": ["revenue", "orders"]},
    }]
    hypothesis_set = build_hypothesis_set(
        "compare revenue by period",
        {"decision": "direct_analysis", "dataset": "sales", "route": "period_compare"},
        state,
    )
    return hypothesis_set


def _p7_relation_evidence(target_id, metric, delta, relation, observed, *, method="compare_periods"):
    return {
        "id": "ev_p7r2", "dataset": "sales", "plan_id": "plan_p7",
        "claim": f"{metric} delta is {delta}.",
        "result_summary": f"{metric}: {delta}",
        "method": method,
        "measurements": [{"metric": metric, "delta": delta, "value": abs(delta)}],
        "competing_hypotheses": [{
            "hypothesis_id": target_id, "relation": relation,
            "metric": metric, "observed": observed,
        }],
    }


class TestP7R2SupplementaryPredicates:

    def test_nan_delta_cannot_decide(self):
        hypothesis_set = _p7_relation_state()
        target = hypothesis_set["hypotheses"][0]
        evidence = _p7_relation_evidence(
            target["id"], "revenue", float("nan"), "supports", "increased",
        )
        updated = update_hypotheses_from_evidence(hypothesis_set, [evidence])
        hypothesis = updated["hypotheses"][0]
        assert hypothesis["status"] not in {"supported", "refuted", "contested"}
        assert hypothesis["relation_candidates"][0]["reason"] == "direction_unknown"

    def test_infinite_delta_cannot_decide(self):
        hypothesis_set = _p7_relation_state()
        target = hypothesis_set["hypotheses"][0]
        evidence = _p7_relation_evidence(
            target["id"], "revenue", float("inf"), "supports", "increased",
        )
        updated = update_hypotheses_from_evidence(hypothesis_set, [evidence])
        assert updated["hypotheses"][0]["status"] not in {"supported", "refuted", "contested"}

    def test_rejected_proposal_retained_with_reason(self):
        hypothesis_set = _p7_relation_state()
        target = hypothesis_set["hypotheses"][0]
        evidence = _p7_relation_evidence(
            target["id"], "orders", 10, "supports", "increased",
        )
        updated = update_hypotheses_from_evidence(hypothesis_set, [evidence])
        hypothesis = updated["hypotheses"][0]
        assert hypothesis["status"] not in {"supported", "refuted"}
        assert hypothesis["relation_candidates"]
        assert hypothesis["relation_candidates"][0]["reason"] == "metric_not_target"

    def test_predicate_mismatch_reason_is_stable(self):
        hypothesis_set = _p7_relation_state()
        target = hypothesis_set["hypotheses"][0]
        evidence = _p7_relation_evidence(
            target["id"], "revenue", 0, "supports", "flat",
        )
        updated = update_hypotheses_from_evidence(hypothesis_set, [evidence])
        hypothesis = updated["hypotheses"][0]
        assert hypothesis["status"] not in {"supported", "refuted"}
        reasons = {item["reason"] for item in hypothesis["relation_candidates"]}
        assert any(reason.startswith("relation_predicate_mismatch") for reason in reasons)

    def test_causal_insufficiency_reason(self):
        hypothesis_set = _p7_relation_state()
        causal = hypothesis_set["hypotheses"][1]
        evidence = _p7_relation_evidence(
            causal["id"], "orders", 10, "supports", "increased",
            method="compare_periods",
        )
        updated = update_hypotheses_from_evidence(hypothesis_set, [evidence])
        hypothesis = updated["hypotheses"][1]
        assert hypothesis["status"] not in {"supported", "refuted"}
        assert hypothesis["relation_candidates"]
