"""Default-off M02 replay using the current binding and finalization path.

The values and receipt identity are from the archived 2026-09-24 E4 M02
curve_fitting result. This is a content-equivalent local replay, not a new
natural-model result or a claim that the old rejected answer was valid.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.loop import AgentLoop
from data_agent.agent import publication_synthesis as ps


_RECEIPT_ID = "tr_d593c760494c"
_POINTS = [0.55, 0.42, 0.31, 0.24, 0.18, 0.13, 0.10]
_FITS = [
    {"family": "exponential", "parameters": {"a": 0.73892193, "b": -0.28583215}, "r_squared": 0.99946726},
    {"family": "logarithmic", "parameters": {"a": 0.56522015, "b": -0.23771293}, "r_squared": 0.99519237},
    {"family": "power", "parameters": {"a": 0.67600697, "b": -0.86571711}, "r_squared": 0.85626503},
]


def _packet() -> dict:
    result = {
        "points": [{"x": index, "y": value, "n_observed": 1} for index, value in enumerate(_POINTS, 1)],
        "fits": deepcopy(_FITS),
        "effective_n": 7,
        "unit_status": "not_confirmed",
        "claim_ceiling": "descriptive",
        "zero_value_semantics": "unknown",
    }
    state = AnalysisSessionState("ffb95bc5a766")
    fixture_digest = "sha256:" + hashlib.sha256(
        json.dumps(result, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    state.add_tool_receipt({
        "id": _RECEIPT_ID,
        "tool_name": "curve_fitting",
        "result_sha256": fixture_digest,
        "structured_result_sha256": fixture_digest,
        "result_preview": "three fitted families",
        "dataset_refs": ["M02-retention"],
        "data_identities": {"M02-retention": {
            "version_id": "dv_local_m02",
            "fingerprint": fixture_digest,
        }},
        "publication_facts": ps.extract_publication_facts(result, max_facts=500),
        "publication_fact_groups": ps.extract_publication_fact_groups(result, receipt_id=_RECEIPT_ID)["groups"],
        "publication_contract": ps.publication_contract("curve_fitting", result, {"dataset": "M02-retention"}),
    })
    return ps.build_publication_packet(
        state,
        user_input="解释 D1 至 D7 留存；D30 只能给未验证的情景，不能称为预测。",
        substantive_tools={"curve_fitting"},
        receipt_ids=[_RECEIPT_ID],
    )


def _finalize(packet: dict, candidate: str) -> tuple[str | None, str | None]:
    fake_loop = SimpleNamespace(
        _turn_publication_packet=packet,
        _turn_origin_revision_issued=False,
        context=SimpleNamespace(turn_state=None),
    )
    return AgentLoop._render_finalized_publication(fake_loop, candidate)


def test_host_produces_m02_claims_and_existing_finalizer_renders_raw_d7():
    packet = _packet()
    candidate = ps.produce_m02_receipt_claim_candidate(packet, _RECEIPT_ID, scenario_time_point=30)
    assert candidate is not None
    visible, bindings, issues = ps.parse_answer_bindings(candidate, packet)
    assert issues == []
    assert [block["claim_type"] for block in bindings["blocks"]] == ["descriptive_fit", "scenario_extrapolation"]
    assert all(block["requirement_refs"] == [] for block in bindings["blocks"])
    assert "[[claim:" in visible

    rendered, error = _finalize(packet, candidate)
    assert error is None and rendered is not None
    # The receipt proves x=7, not the user's D7 semantic alias.
    assert "观测端点 x=7：原始数值 0.1" in rendered
    assert "10%" not in rendered and "55%" not in rendered
    assert "单位未确认" in rendered and "未做留出验证" in rendered
    assert "D30" in rendered and "不是已验证预测" in rendered
    assert "[[claim:" not in rendered and "answer-bindings" not in rendered
    assert len(packet["answer_bindings"]["blocks"]) == 2
    assert len(packet["answer_render_trace"]["entries"]) == 2
    assert all(item.get("answer_coverage") == "unassessed" for item in packet["requirements"])


def test_host_candidate_excludes_independent_unbound_prose_and_rejects_stale_packet():
    packet = _packet()
    candidate = ps.produce_m02_receipt_claim_candidate(packet, _RECEIPT_ID)
    assert candidate is not None and "99%" not in candidate
    rendered, error = _finalize(packet, candidate)
    assert error is None and rendered and "99%" not in rendered
    assert "D30" not in rendered

    stale = deepcopy(packet)
    stale["snapshot_digest"] = "sha256:other-snapshot"
    stale["binding_digest"] = "sha256:other-binding"
    rejected, error = _finalize(stale, candidate)
    assert rejected is None and "stale_answer_bindings" in error


def test_host_production_fails_closed_on_missing_or_foreign_receipt_facts():
    packet = _packet()
    assert ps.produce_m02_receipt_claim_candidate(packet, "tr_foreign") is None
    packet["sources"][0]["facts"] = [
        fact for fact in packet["sources"][0]["facts"] if fact["path"] != "points[6].y"
    ]
    assert ps.produce_m02_receipt_claim_candidate(packet, _RECEIPT_ID) is None


def test_host_production_rejects_unit_or_time_point_escalation():
    packet = _packet()
    assert ps.produce_m02_receipt_claim_candidate(packet, _RECEIPT_ID, scenario_time_point=7) is None
    assert ps.produce_m02_receipt_claim_candidate(packet, _RECEIPT_ID, scenario_time_point=True) is None
    packet["publication_scope"][0]["unit_status"] = "confirmed"
    assert ps.produce_m02_receipt_claim_candidate(packet, _RECEIPT_ID) is None


def test_host_production_needs_same_dataset_version_identity():
    packet = _packet()
    packet["sources"][0]["data_identities"] = {}
    assert ps.produce_m02_receipt_claim_candidate(packet, _RECEIPT_ID) is None


def test_malformed_endpoint_refs_fail_validation_without_raising():
    packet = _packet()
    candidate = ps.produce_m02_receipt_claim_candidate(packet, _RECEIPT_ID)
    assert candidate is not None
    _, bindings, issues = ps.parse_answer_bindings(candidate, packet)
    assert not issues
    block = dict(bindings["blocks"][0], fact_refs=[{}, {}])
    assert ps._descriptive_fit_binding_issue(block, packet) is not None


def test_archived_e4_curve_receipt_replays_through_current_finalizer_when_present():
    archived = (
        Path(__file__).resolve().parents[1]
        / "tmp/trust-reset-p08-real-20260924-r1/sessions/ffb95bc5a766/analysis_state.json"
    )
    if not archived.is_file():
        pytest.skip("archived E4 session is not part of a clean checkout")
    state = AnalysisSessionState.from_dict(json.loads(archived.read_text(encoding="utf-8")), "ffb95bc5a766")
    packet = ps.build_publication_packet(
        state,
        user_input="解释 D1 至 D7 留存；D30 仅作未验证情景。",
        substantive_tools={"curve_fitting"},
        receipt_ids=[_RECEIPT_ID],
    )
    candidate = ps.produce_m02_receipt_claim_candidate(packet, _RECEIPT_ID, scenario_time_point=30)
    assert candidate is not None
    rendered, error = _finalize(packet, candidate)
    assert error is None and rendered is not None
    assert "观测端点 x=7：原始数值 0.1" in rendered
    assert "10%" not in rendered and "单位未确认" in rendered
    assert len(packet["answer_bindings"]["blocks"]) == 2
    assert len(packet["answer_render_trace"]["entries"]) == 2
