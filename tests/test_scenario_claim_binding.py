"""Phase 2 RED contracts: the existing answer-bindings channel owns M02 scenarios.

The receipt values mirror the persisted R4 M02 curve_fitting contract. Historical
prose failures are evidence, not an invitation to expand a phrase lexicon.
"""

from __future__ import annotations

import json
import hashlib
from types import SimpleNamespace

from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent import publication_synthesis as ps
from data_agent.agent.loop import AgentLoop


def _packet() -> dict:
    receipt_id = "tr_3b550d8e6a32"
    return {
        "status": "ready",
        "snapshot_digest": "sha256:r4-m02-current-packet",
        "question": "解释 D1 至 D7 留存；如使用曲线拟合，D30 仅展示未验证情景。",
        "requirements": [],
        "evidence": [],
        "sources": [{"receipt_id": receipt_id, "tool_name": "curve_fitting", "facts": []}],
        "publication_scope": [{
            "receipt_id": receipt_id,
            "tool": "curve_fitting",
            "source_dataset": "M02-retention",
            "observed_x_range": [1.0, 7.0],
            "extrapolation_allowed": False,
            "unit_status": "not_confirmed",
            "claim_ceiling": "descriptive",
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


def _candidate(packet: dict, **changes) -> str:
    block = {
        "claim_id": "claim_m02_d30",
        "exact_text": "[[claim:claim_m02_d30]]",
        "claim_type": "scenario_extrapolation",
        "status": "unvalidated",
        "unit_status": "not_confirmed",
        "validation_status": "none",
        "receipt_ref": "tr_3b550d8e6a32",
        "time_point": 30,
        "families": ["exponential", "logarithmic", "power"],
        "requirement_refs": [],
        "fact_refs": [],
        "derived_refs": [],
    }
    block.update(changes)
    payload = {
        "schema_version": "answer_bindings.v1",
        "packet_digest": packet.get("binding_digest", packet["snapshot_digest"]),
        "blocks": [block],
    }
    return (
        "D1—D7 是已观察区间；下表仅比较 D30 的未验证拟合情景，"
        "D30 本身仍未知。\n\n[[claim:claim_m02_d30]]\n\n"
        "```answer-bindings\n" + json.dumps(payload, ensure_ascii=False) + "\n```"
    )


def test_r4_equivalent_scenario_uses_existing_binding_and_host_renderer():
    packet = _packet()
    visible, bindings, issues = ps.parse_answer_bindings(_candidate(packet), packet)
    assert issues == []
    assert bindings["blocks"][0]["claim_type"] == "scenario_extrapolation"
    rendered = ps.render_bound_claims(visible, packet, bindings)
    assert "[[claim:" not in rendered
    assert "exponential" in rendered and "logarithmic" in rendered and "power" in rendered
    assert "0.99946726" in rendered and "0.85626503" in rendered
    assert "0.00013949" in rendered and "-0.243" in rendered and "0.035" in rendered
    assert "未做留出验证" in rendered and "回测" in rendered and "外部验证" in rendered
    assert "单位未确认" in rendered and "%" not in rendered
    assert "D30 本身仍未知" in rendered


def test_r4_rejected_prose_remains_a_red_control_not_a_phrase_patch():
    scope = _packet()["publication_scope"][0]
    # Excerpt from the second persisted R4 M02 rejected candidate. The new
    # path never attempts to repair this clause by extending its word list.
    old_clause = (
        "D30 的三个数值只能读作三种机制假设下的拟合情景："
        "指数族的 0.014% 对应相对衰减率近似恒定，"
        "幂律族的 3.56% 对应长尾缓慢衰减，"
        "对数族因自身给出负值而不适用于外推。"
    )
    assert any(
        issue["code"] == "unbound_time_point_claim"
        for issue in ps._extrapolation_issues(old_clause, [scope])
    )


def test_scenario_binding_rejects_foreign_receipt_and_model_supplied_values():
    packet = _packet()
    for changed in (
        {"receipt_ref": "tr_foreign"},
        {"reported_values": {"exponential": 0.5}},
        {"status": "validated_prediction"},
        {"unit_status": "confirmed_ratio"},
        {"validation_status": "holdout_passed"},
        {"families": ["exponential", "power"]},
        {"time_point": 6},
    ):
        _, bindings, issues = ps.parse_answer_bindings(_candidate(packet, **changed), packet)
        assert bindings is not None
        assert issues, changed


def test_unbound_fabricated_d30_value_still_fails_deterministically():
    packet = _packet()
    candidate = "D30 的留存率为 50%。\n\n" + _candidate(packet)
    visible, bindings, issues = ps.parse_answer_bindings(candidate, packet)
    assert bindings is not None and not issues
    assert any(
        issue["code"] in {"unbound_time_point_claim", "extrapolated_time_point"}
        for issue in ps.validate_final_narrative_issues(visible, packet)
    )


def test_finalization_returns_host_rendered_body_not_appendix_only():
    packet = _packet()
    fake_loop = SimpleNamespace(
        _turn_publication_packet=packet,
        _turn_origin_revision_issued=False,
        context=SimpleNamespace(turn_state=None),
    )
    rendered, error = AgentLoop._render_finalized_publication(fake_loop, _candidate(packet))
    assert error is None
    assert rendered is not None and "[[claim:" not in rendered
    assert "D30" in rendered and "exponential" in rendered
    assert "answer-bindings" not in rendered


def test_explicit_receipt_ratio_unit_allows_percent_conversion():
    packet = _packet()
    scope = packet["publication_scope"][0]
    scope["analysis_unit"] = "ratio"
    scope["unit_status"] = "confirmed"
    visible, bindings, issues = ps.parse_answer_bindings(
        _candidate(packet, unit_status="confirmed"), packet
    )
    assert issues == []
    rendered = ps.render_bound_claims(visible, packet, bindings)
    assert "比率（%）" in rendered
    assert "0.0139%" in rendered
    assert "单位未确认" not in rendered


def test_malformed_receipt_fails_closed_without_publishing_placeholder():
    packet = _packet()
    packet["publication_scope"][0]["scenario_extrapolation"]["models"][0]["parameters"] = {"a": "not-a-number"}
    visible, bindings, issues = ps.parse_answer_bindings(_candidate(packet), packet)
    assert visible
    assert bindings is not None and issues
    fake_loop = SimpleNamespace(
        _turn_publication_packet=packet,
        _turn_origin_revision_issued=False,
        context=SimpleNamespace(turn_state=None),
    )
    published, error = AgentLoop._render_finalized_publication(fake_loop, _candidate(packet))
    assert published is None and "invalid_scenario_binding" in error


def test_placeholder_without_valid_binding_is_never_published():
    packet = _packet()
    bare = "D30 仍未知。[[claim:claim_m02_d30]]"
    _, bindings, issues = ps.parse_answer_bindings(bare, packet)
    assert bindings is None
    assert any(issue["code"] == "unbound_claim_placeholder" for issue in issues)
    fake_loop = SimpleNamespace(
        _turn_publication_packet=packet,
        _turn_origin_revision_issued=False,
        context=SimpleNamespace(turn_state=None),
    )
    published, error = AgentLoop._render_finalized_publication(fake_loop, bare)
    assert published is None and "unbound_claim_placeholder" in error


def test_persisted_reply_and_publication_hash_bind_the_host_rendered_body():
    packet = _packet()
    state = SimpleNamespace(publication_packets=[])
    state.add_publication_packet = lambda item: state.publication_packets.append(item)
    fake_loop = SimpleNamespace(
        session_id="m02-local",
        _turn_publication_packet=packet,
        _turn_origin_revision_issued=False,
        context=SimpleNamespace(turn_state=None, analysis_state=state),
        messages=[],
        _auto_save=lambda: None,
        _register_publication_receipt_artifact=lambda packet, state: None,
    )
    fake_loop._commit_publication_packet = lambda packet, text: AgentLoop._commit_publication_packet(
        fake_loop, packet, text
    )
    rendered, error = AgentLoop._render_finalized_publication(fake_loop, _candidate(packet))
    assert error is None and rendered is not None
    assistant_msg = {"role": "assistant", "content": ""}
    assert AgentLoop._persist_accepted_answer(fake_loop, assistant_msg, rendered) is None
    expected_hash = "sha256:" + hashlib.sha256(rendered.encode("utf-8")).hexdigest()
    assert assistant_msg["content"] == rendered
    assert assistant_msg["answer_sha256"] == expected_hash
    assert state.publication_packets[-1]["answer_sha256"] == expected_hash


def test_real_packet_builder_exposes_receipt_scope_to_existing_binding_prompt():
    state = AnalysisSessionState("m02-built")
    model_rows = _packet()["publication_scope"][0]["scenario_extrapolation"]["models"]
    result = {
        "points": [{"x": x, "y": y} for x, y in enumerate((0.55, 0.42, 0.31, 0.24, 0.18, 0.13, 0.10), 1)],
        "fits": model_rows,
        "effective_n": 7,
        "unit_status": "not_confirmed",
        "claim_ceiling": "descriptive",
    }
    state.add_tool_receipt({
        "id": "tr_curve_built",
        "tool_name": "curve_fitting",
        "result_sha256": "sha256:curve-result",
        "structured_result_sha256": "sha256:curve-structured",
        "result_preview": "three fitted families",
        "publication_facts": ps.extract_publication_facts(result),
        "publication_fact_groups": ps.extract_publication_fact_groups(
            result, receipt_id="tr_curve_built"
        )["groups"],
        "publication_contract": ps.publication_contract(
            "curve_fitting", result, {"dataset": "M02-retention"}
        ),
    })
    packet = ps.build_publication_packet(
        state,
        user_input="请解释 D1 至 D7 留存，并展示未验证的 D30 拟合情景。",
        substantive_tools={"curve_fitting"},
        phase="preview",
    )
    assert packet["status"] == "ready"
    assert packet["publication_scope"][0]["scenario_extrapolation"]["validation"] == "none"
    prompt = ps.publication_packet_prompt(packet)
    assert "answer_bindings.v1" in prompt and "[[claim:claim_ID]]" in prompt
    assert "unit_status/validation_status" in prompt
    final_packet = ps.build_publication_packet(
        state,
        user_input="请解释 D1 至 D7 留存，并展示未验证的 D30 拟合情景。",
        substantive_tools={"curve_fitting"},
        phase="final",
    )
    assert packet["snapshot_digest"] != final_packet["snapshot_digest"]
    assert packet["binding_digest"] == final_packet["binding_digest"]
    visible, bindings, issues = ps.parse_answer_bindings(
        _candidate(packet, receipt_ref="tr_curve_built"), final_packet
    )
    assert visible and bindings and issues == []
    state.requirement_revision += 1
    changed_packet = ps.build_publication_packet(
        state,
        user_input="请解释 D1 至 D7 留存，并展示未验证的 D30 拟合情景。",
        substantive_tools={"curve_fitting"},
        phase="final",
    )
    assert changed_packet["binding_digest"] != packet["binding_digest"]
    assert any(
        issue["code"] == "stale_answer_bindings"
        for issue in ps.parse_answer_bindings(
            _candidate(packet, receipt_ref="tr_curve_built"), changed_packet
        )[2]
    )
