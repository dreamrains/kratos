"""Observation-only curve fits use receipt-owned claims, never prose R² matching."""

import json
import importlib
from types import SimpleNamespace

import pandas as pd
import pytest

from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.loop import AgentLoop
from data_agent.agent.publication_synthesis import (
    build_publication_packet,
    extract_publication_fact_groups,
    extract_publication_facts,
    parse_answer_bindings,
    publication_contract,
    render_bound_claims,
    render_verified_partial_answer,
)


def _packet():
    receipt_id = "tr_r4_curve"
    return {
        "status": "ready",
        "snapshot_digest": "sha256:current-r4-fit-snapshot",
        "question": "解释 D1 至 D7 的观测留存曲线；不要求 D30 外推。",
        "requirements": [],
        "evidence": [],
        "sources": [{"receipt_id": receipt_id, "tool_name": "curve_fitting", "facts": []}],
        "publication_scope": [{
            "receipt_id": receipt_id,
            "tool": "curve_fitting",
            "observed_x_range": [1.0, 7.0],
            "claim_ceiling": "descriptive",
            "unit_status": "not_confirmed",
            "zero_value_semantics": "unknown",
            "scenario_extrapolation": {
                "status": "descriptive_fit_only",
                "effective_n": 7,
                "validation": "none",
                "models": [
                    {"family": "exponential", "parameters": {"a": 0.73892193, "b": -0.28583215}, "r_squared": 0.99946726},
                    {"family": "logarithmic", "parameters": {"a": 0.56522015, "b": -0.23771293}, "r_squared": 0.99519237},
                    {"family": "power", "parameters": {"a": 0.67600697, "b": -0.86571711}, "r_squared": 0.85626503},
                ],
            },
        }],
    }


def _block(**changes):
    block = {
        "claim_id": "claim_observed_fit",
        "exact_text": "[[claim:claim_observed_fit]]",
        "claim_type": "descriptive_fit",
        "status": "descriptive",
        "unit_status": "not_confirmed",
        "validation_status": "none",
        "receipt_ref": "tr_r4_curve",
        "families": ["exponential", "logarithmic", "power"],
        "requirement_refs": [],
        "fact_refs": [],
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


def test_r4_fit_without_extrapolation_is_rendered_from_receipt():
    packet = _packet()
    visible, bindings, issues = parse_answer_bindings(_candidate(packet, _block()), packet)
    assert not issues
    rendered = render_bound_claims(visible, packet, bindings)
    assert "0.99946726" in rendered and "0.85626503" in rendered
    assert "exponential" in rendered and "logarithmic" in rendered and "power" in rendered
    assert "x=1—7" in rendered
    assert "单位未确认" in rendered and "未做留出" in rendered
    assert "D30" not in rendered and "预测值" not in rendered


def test_fit_rejects_omitted_family_and_model_supplied_value():
    packet = _packet()
    for block in (
        _block(families=["exponential", "power"]),
        _block(display_r_squared=1.0),
    ):
        _, bindings, issues = parse_answer_bindings(_candidate(packet, block), packet)
        assert any(issue["code"] == "invalid_descriptive_fit_binding" for issue in issues)
        assert bindings["blocks"] == []


def test_fit_rejects_foreign_receipt_and_forged_prediction_status():
    packet = _packet()
    for block in (
        _block(receipt_ref="tr_unrelated"),
        _block(status="validated_prediction"),
        _block(validation_status="holdout_passed"),
    ):
        assert any(
            issue["code"] == "invalid_descriptive_fit_binding"
            for issue in parse_answer_bindings(_candidate(packet, block), packet)[2]
        )


def test_fit_partial_publication_keeps_only_host_rendered_claim():
    packet = _packet()
    _, bindings, issues = parse_answer_bindings(_candidate(packet, _block()), packet)
    assert not issues
    partial, accepted = render_verified_partial_answer(packet, bindings)
    assert "0.99946726" in partial and "未做留出" in partial
    assert accepted["blocks"][0]["claim_type"] == "descriptive_fit"


def test_fit_uses_actual_curve_fitting_tool_contract(monkeypatch):
    curve_module = importlib.import_module("data_agent.tools.curve_fitting")
    frame = pd.DataFrame({"day": range(1, 8), "retention": [0.8, 0.61, 0.49, 0.42, 0.36, 0.31, 0.27]})
    monkeypatch.setattr(curve_module, "get_df", lambda _name: (frame, None))
    result = curve_module.curve_fitting("fixture", x_col="day", y_col="retention").data
    assert result and result["fits"]
    state = AnalysisSessionState("fit-claim")
    state.add_tool_receipt({
        "id": "tr_r4_curve",
        "tool_name": "curve_fitting",
        "result_sha256": "sha256:actual-fit-result",
        "structured_result_sha256": "sha256:actual-fit-structured",
        "result_preview": "fits computed",
        "publication_facts": extract_publication_facts(result, max_facts=500),
        "publication_fact_groups": extract_publication_fact_groups(result, receipt_id="tr_r4_curve")["groups"],
        "publication_contract": publication_contract("curve_fitting", result),
    })
    packet = build_publication_packet(
        state, user_input="解释已观察曲线", substantive_tools={"curve_fitting"}, receipt_ids=["tr_r4_curve"],
    )
    families = [model["family"] for model in packet["publication_scope"][0]["scenario_extrapolation"]["models"]]
    visible, bindings, issues = parse_answer_bindings(
        _candidate(packet, _block(families=families)), packet,
    )
    assert not issues
    rendered = render_bound_claims(visible, packet, bindings)
    assert all(family in rendered for family in families)
    assert "x=1—7" in rendered and "有效拟合点 7" in rendered


def test_fit_rechecks_scope_at_render_time_and_rejects_nonfinite_quality():
    packet = _packet()
    visible, bindings, issues = parse_answer_bindings(_candidate(packet, _block()), packet)
    assert not issues
    packet["publication_scope"][0]["scenario_extrapolation"]["models"][0]["r_squared"] = float("nan")
    with pytest.raises(ValueError, match="渲染前失效"):
        render_bound_claims(visible, packet, bindings)
    packet = _packet()
    packet["publication_scope"][0]["scenario_extrapolation"]["models"][0]["parameters"]["a"] = True
    assert any(issue["code"] == "invalid_descriptive_fit_binding" for issue in parse_answer_bindings(_candidate(packet, _block()), packet)[2])


def test_fit_rejects_insufficient_points_or_confirmed_unit_without_label():
    packet = _packet()
    packet["publication_scope"][0]["scenario_extrapolation"]["effective_n"] = 4
    assert any(issue["code"] == "invalid_descriptive_fit_binding" for issue in parse_answer_bindings(_candidate(packet, _block()), packet)[2])
    packet = _packet()
    packet["publication_scope"][0]["unit_status"] = "confirmed"
    assert any(issue["code"] == "invalid_descriptive_fit_binding" for issue in parse_answer_bindings(_candidate(packet, _block()), packet)[2])


def test_terminal_publication_keeps_observed_fit_and_rejects_forged_fit():
    packet = _packet()
    fake_loop = SimpleNamespace(
        _turn_publication_packet=packet,
        _turn_origin_revision_issued=False,
        context=SimpleNamespace(turn_state=None),
    )
    published, error = AgentLoop._render_finalized_publication(fake_loop, _candidate(packet, _block()))
    assert error is None and published and "0.99946726" in published
    assert "[[claim:" not in published and "answer-bindings" not in published
    rejected, error = AgentLoop._render_finalized_publication(
        fake_loop, _candidate(packet, _block(validation_status="holdout_passed")),
    )
    assert rejected is None and "invalid_descriptive_fit_binding" in error
