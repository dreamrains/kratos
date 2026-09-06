"""P7 independent safety oracles; failures block dependent browser acceptance.

These exercise real host gates with structured fixtures, not a browser or a
Provider. Keep the expected safety behavior when repairing the implementation.
"""
import hashlib
import json

import pytest

from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.hypotheses import (
    build_hypothesis_set,
    update_hypotheses_from_evidence,
)
from data_agent.agent.publication_synthesis import (
    build_publication_packet,
    extract_publication_facts,
    publication_contract,
    validate_final_narrative,
)


def _curve_receipt(dataset, last_day):
    result = {
        "method": "curve_family_comparison",
        "status": "supported",
        "points": [{"x": day, "y": 0.08} for day in range(1, last_day + 1)],
        "fits": [{"family": "power", "parameters": {"a": 0.08, "b": 0}, "r_squared": 1}],
        "limitations": ["拟合只描述观测区间。"],
    }
    args = {"name": dataset, "x_col": "day", "y_col": "retention"}
    return {
        "id": "receipt_" + dataset,
        "tool_name": "curve_fitting",
        "arguments": args,
        "result_sha256": hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest(),
        "result_preview": f"curve_fitting {dataset} observed D1-D{last_day}",
        "publication_facts": extract_publication_facts(result),
        "publication_contract": publication_contract("curve_fitting", result, args=args),
    }


@pytest.mark.parametrize("include_b,text,should_reject", [
    pytest.param(False, "渠道 A 不能预测 D30，建议继续收集至第30天。", False, id="P7-N-control-boundary"),
    pytest.param(False, "渠道 A 的 D30 留存预计为 5%。", True, id="P7-N-control-unobserved"),
    pytest.param(True, "渠道 B 的 D30 留存为 8%。", False, id="P7-N-control-observed-b"),
    pytest.param(True, "渠道 A 的 D30 留存预计为 5%。", True, id="P7-N-cross-source-bypass"),
])
def test_p7_prediction_is_bound_to_its_source(include_b, text, should_reject, record_property):
    state = AnalysisSessionState(session_id="p7_scope_oracle")
    state.add_tool_receipt(_curve_receipt("渠道 A", 7))
    if include_b:
        state.add_tool_receipt(_curve_receipt("渠道 B", 30))
    packet = build_publication_packet(
        state, user_input="分别分析渠道 A 和渠道 B 的留存",
        substantive_tools={"curve_fitting"},
        receipt_ids=[item["id"] for item in state.tool_receipts],
    )
    error = validate_final_narrative(text, packet)
    record_property("packet", json.dumps(packet, ensure_ascii=False))
    record_property("input", text)
    record_property("actual_error", str(error))
    assert (error is not None) == should_reject, (
        "A only has D1-D7. B's D30 observation cannot authorize A's D30 prediction. "
        f"text={text!r}; error={error!r}"
    )


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
    updated = update_hypotheses_from_evidence(hypothesis_set, [evidence])
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
