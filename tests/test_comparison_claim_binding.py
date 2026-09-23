"""Closed comparison claim: current compare_periods receipt, not prose arithmetic."""

import json

import pandas as pd
import pytest

from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.publication_synthesis import (
    build_publication_packet,
    extract_publication_fact_groups,
    extract_publication_facts,
    parse_answer_bindings,
    publication_contract,
    render_bound_claims,
    render_verified_partial_answer,
    validate_final_narrative_issues,
)


def _result(*, difference=-1134):
    return {
        "period_a": {"range": ["2026-04-07", "2026-04-21"], "rows": 47, "day_count": 15},
        "period_b": {"range": ["2026-04-22", "2026-05-06"], "rows": 24, "day_count": 15},
        "combined": {"row_count": 71, "day_count": 30},
        "metrics": {"revenue": {
            "period_a": 1818, "period_b": 684, "diff": difference,
            "change_pct": -62.38,
        }},
    }


def _packet(*, receipts=None):
    state = AnalysisSessionState("comparison-claim")
    for receipt_id, result in (receipts or [("tr_current", _result())]):
        state.add_tool_receipt({
            "id": receipt_id,
            "tool_name": "compare_periods",
            "result_sha256": f"sha256:{receipt_id}",
            "structured_result_sha256": f"sha256:structured-{receipt_id}",
            "result_preview": "comparison computed",
            "publication_facts": extract_publication_facts(result, max_facts=500),
            "publication_fact_groups": extract_publication_fact_groups(result, receipt_id=receipt_id)["groups"],
            "publication_contract": publication_contract("compare_periods", result),
        })
    return build_publication_packet(
        state, user_input="比较前后两个周期", substantive_tools={"compare_periods"},
        receipt_ids=[receipt_id for receipt_id, _ in (receipts or [("tr_current", _result())])],
    )


def _block(packet, *, receipt_ref="tr_current", **changes):
    source = next(source for source in packet["sources"] if source["receipt_id"] == receipt_ref)
    by_path = {fact["path"]: fact["fact_id"] for fact in source["facts"]}
    block = {
        "claim_id": "claim_period_revenue",
        "exact_text": "[[claim:claim_period_revenue]]",
        "claim_type": "comparison",
        "status": "computed",
        "unit_status": "not_confirmed",
        "receipt_ref": receipt_ref,
        "requirement_refs": [],
        "fact_refs": [by_path[f"metrics.revenue.{field}"] for field in ("period_a", "period_b", "diff")],
        "derived_refs": [],
    }
    block.update(changes)
    return block


def _candidate(packet, block):
    return block["exact_text"] + "\n\n```answer-bindings\n" + json.dumps({
        "schema_version": "answer_bindings.v1",
        "packet_digest": packet["snapshot_digest"],
        "blocks": [block],
    }, ensure_ascii=False) + "\n```"


def test_comparison_from_real_tool_shape_is_host_rendered_in_place():
    packet = _packet()
    visible, bindings, issues = parse_answer_bindings(_candidate(packet, _block(packet)), packet)
    assert not issues
    packet["answer_bindings"] = bindings
    assert not validate_final_narrative_issues(visible, packet)
    rendered = render_bound_claims(visible, packet, bindings)
    for value in ("revenue", "2026-04-07", "2026-04-21", "2026-04-22", "2026-05-06", "1818", "684", "-1134"):
        assert value in rendered
    assert "单位未确认" in rendered
    assert "%" not in rendered and "同比" not in rendered


def test_comparison_accepts_actual_compare_periods_tool_result(monkeypatch):
    from data_agent.tools import eda

    frame = pd.DataFrame({
        "日期": ["2026-04-07", "2026-04-08", "2026-04-22", "2026-04-23"],
        "revenue": [100, 200, 50, 75],
    })
    monkeypatch.setattr(eda, "get_df", lambda _name: (frame, None))
    result = json.loads(eda.compare_periods(
        "fixture", date_col="日期", metrics="revenue",
        period_a="2026-04-07~2026-04-08", period_b="2026-04-22~2026-04-23",
    ))
    packet = _packet(receipts=[("tr_current", result)])
    visible, bindings, issues = parse_answer_bindings(_candidate(packet, _block(packet)), packet)
    assert not issues
    rendered = render_bound_claims(visible, packet, bindings)
    assert "| 基准期 | 2026-04-07—2026-04-08 | 2 | 300 |" in rendered
    assert "| 对比期 | 2026-04-22—2026-04-23 | 2 | 125 |" in rendered
    assert "-175" in rendered


def test_comparison_rejects_bad_delta_and_does_not_keep_wrong_claim():
    packet = _packet(receipts=[("tr_current", _result(difference=-999))])
    visible, bindings, issues = parse_answer_bindings(_candidate(packet, _block(packet)), packet)
    assert any(issue["code"] == "invalid_comparison_binding" for issue in issues)
    assert bindings["blocks"] == []
    assert "[[claim:" in visible


def test_comparison_cannot_join_two_current_receipts_or_swap_periods():
    packet = _packet(receipts=[("tr_old", _result()), ("tr_current", _result())])
    source_old = next(source for source in packet["sources"] if source["receipt_id"] == "tr_old")
    old_a = next(fact["fact_id"] for fact in source_old["facts"] if fact["path"] == "metrics.revenue.period_a")
    block = _block(packet, fact_refs=[old_a, *_block(packet)["fact_refs"][1:]])
    assert any(issue["code"] == "invalid_comparison_binding" for issue in parse_answer_bindings(_candidate(packet, block), packet)[2])
    swapped = _block(packet, fact_refs=list(reversed(_block(packet)["fact_refs"])))
    assert any(issue["code"] == "invalid_comparison_binding" for issue in parse_answer_bindings(_candidate(packet, swapped), packet)[2])


def test_comparison_requires_receipt_window_and_matching_unit_status():
    packet = _packet()
    wrong_unit = _block(packet, unit_status="confirmed_ratio")
    assert any(issue["code"] == "invalid_comparison_binding" for issue in parse_answer_bindings(_candidate(packet, wrong_unit), packet)[2])
    packet["publication_scope"][0]["observation_window"]["period_a"] = None
    assert any(issue["code"] == "invalid_comparison_binding" for issue in parse_answer_bindings(_candidate(packet, _block(packet)), packet)[2])


def test_comparison_accepts_bounded_tool_rounding_and_true_zero():
    result = _result()
    result["metrics"]["revenue"].update({"period_a": 0, "period_b": 0.1000, "diff": 0.1001})
    packet = _packet(receipts=[("tr_current", result)])
    visible, bindings, issues = parse_answer_bindings(_candidate(packet, _block(packet)), packet)
    assert not issues
    rendered = render_bound_claims(visible, packet, bindings)
    assert "| 0 |" in rendered
    assert "0.1" in rendered
    assert "0.1001" not in rendered
    assert "%" not in rendered


def test_comparison_different_window_lengths_are_disclosed_from_scope():
    result = _result()
    result["period_b"]["range"][1] = "2026-05-07"
    result["period_b"]["day_count"] = 16
    packet = _packet(receipts=[("tr_current", result)])
    visible, bindings, issues = parse_answer_bindings(_candidate(packet, _block(packet)), packet)
    assert not issues
    rendered = render_bound_claims(visible, packet, bindings)
    assert "2026-05-07" in rendered
    assert "区间天数不同" in rendered


def test_comparison_rechecks_current_scope_at_render_time():
    packet = _packet()
    visible, bindings, issues = parse_answer_bindings(_candidate(packet, _block(packet)), packet)
    assert not issues
    packet["publication_scope"][0]["observation_window"]["period_b"] = None
    with pytest.raises(ValueError, match="渲染前失效"):
        render_bound_claims(visible, packet, bindings)


def test_verified_comparison_survives_partial_publication_without_raw_prose():
    packet = _packet()
    visible, bindings, issues = parse_answer_bindings(_candidate(packet, _block(packet)), packet)
    assert not issues
    partial, accepted = render_verified_partial_answer(packet, bindings)
    assert partial and "1818" in partial and "-1134" in partial
    assert accepted["blocks"][0]["claim_type"] == "comparison"
    assert "[[claim:" not in partial
