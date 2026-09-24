"""A confirmed axis and scale may bind the whole observed series, never a forecast."""

from copy import deepcopy
import hashlib
import json
from types import SimpleNamespace

import pandas as pd

from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.confirmation.runtime import build_action_registry, build_measurement_mapping_candidate
from data_agent.agent.confirmation.service import ConfirmationService
from data_agent.agent.loop import AgentLoop
from data_agent.agent import publication_synthesis as ps
from data_agent.session.history import CanonicalHistorySnapshot, _history_sha256
from data_agent.session.workspace import Workspace


_PROMPT = "请计算并解释 D1 至 D7 留存；判断当前数据是否可以预测 D30。"
_SPAN = "D1 至 D7 留存"
_RECEIPT = "tr_confirmed_curve"
_Y = [0.55, 0.42, 0.31, 0.24, 0.18, 0.13, 0.10]


def _setup(tmp_path, *, answer="fraction"):
    workspace = Workspace()
    workspace.add("retention", pd.DataFrame({"day": list(range(1, 8)), "retention": _Y}))
    messages = [{"role": "user", "content": _PROMPT}]
    history = CanonicalHistorySnapshot(messages, 1, _history_sha256(messages), 1)
    candidate = build_measurement_mapping_candidate(
        session_id="session_1", turn_id="turn_1", workspace=workspace,
        canonical_history=history,
        source_message_ref="msg_" + hashlib.sha256(_PROMPT.encode()).hexdigest()[:12],
        exact_span=_SPAN, dataset="retention", column="retention",
        x_column="day", x_start=1, x_end=7,
    )
    assert candidate is not None
    service = ConfirmationService(tmp_path, action_registry=build_action_registry())
    service.request(candidate)
    if answer == "skipped":
        service.skip("session_1", candidate.confirmation_id,
                     service.checkpoint("session_1").version, "skip_axis")
    else:
        service.respond("session_1", candidate.confirmation_id, answer,
                        service.checkpoint("session_1").version, "answer_axis")
    result = {
        "points": [{"x": i, "y": y, "n_observed": 1} for i, y in enumerate(_Y, 1)],
        "fits": [{"family": "exponential", "parameters": {"a": 0.7, "b": -0.2},
                  "r_squared": 0.9}],
        "effective_n": 7, "unit_status": "not_confirmed",
        "claim_ceiling": "descriptive", "zero_value_semantics": "unknown",
    }
    digest = "sha256:" + hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
    state = AnalysisSessionState("session_1")
    state.add_tool_receipt({
        "id": _RECEIPT, "tool_name": "curve_fitting", "result_sha256": digest,
        "structured_result_sha256": digest, "result_preview": "curve",
        "arguments": {"name": "retention", "x_col": "day", "y_col": "retention"},
        "dataset_refs": ["retention"],
        "data_identities": {"retention": workspace.get_data_identity("retention")},
        "publication_facts": ps.extract_publication_facts(result, max_facts=500),
        "publication_fact_groups": ps.extract_publication_fact_groups(
            result, receipt_id=_RECEIPT)["groups"],
        "publication_contract": ps.publication_contract(
            "curve_fitting", result, {"dataset": "retention"}),
    })
    return state, workspace, history


def _packet(state, workspace, history, tmp_path):
    return ps.build_publication_packet(
        state, user_input=_PROMPT, substantive_tools={"curve_fitting"},
        receipt_ids=[_RECEIPT], offline_confirmed_m02=True,
        offline_workspace=workspace, canonical_history=history,
        confirmation_sessions_root=tmp_path,
    )


def _finalize(packet, candidate):
    loop = SimpleNamespace(_turn_publication_packet=packet,
                           _turn_origin_revision_issued=False,
                           context=SimpleNamespace(turn_state=None))
    return AgentLoop._render_finalized_publication(loop, candidate)


def test_confirmed_whole_series_uses_existing_fit_claim_and_host_renderer(tmp_path):
    state, workspace, history = _setup(tmp_path)
    packet = _packet(state, workspace, history, tmp_path)
    assert packet["confirmed_observation"]["scale"] == "fraction"
    candidate = ps.produce_m02_receipt_claim_candidate(packet, _RECEIPT, scenario_time_point=30)
    visible, bindings, issues = ps.parse_answer_bindings(candidate, packet)
    assert not issues and len(bindings["blocks"]) == 2 and visible
    assert len(bindings["blocks"][0]["fact_refs"]) == 14
    assert bindings["blocks"][0]["requirement_refs"] == [packet["requirements"][0]["id"]]
    assert bindings["blocks"][1]["requirement_refs"] == []
    rendered, error = _finalize(packet, candidate)
    assert error is None and rendered
    assert "55%" in rendered and "10%" in rendered
    assert "未做留出验证" in rendered and "不是已验证预测" in rendered
    assert packet["requirements"][0]["answer_coverage"] == "answered"
    assert len(packet["answer_render_trace"]["entries"]) == 2


def test_missing_confirmation_or_tool_column_identity_keeps_unassessed(tmp_path):
    state, workspace, history = _setup(tmp_path, answer="skipped")
    packet = _packet(state, workspace, history, tmp_path)
    assert "confirmed_observation" not in packet
    candidate = ps.produce_m02_receipt_claim_candidate(packet, _RECEIPT)
    _rendered, error = _finalize(packet, candidate)
    assert error is None
    assert all(item["answer_coverage"] != "answered" for item in packet["requirements"])

    state, workspace, history = _setup(tmp_path / "other")
    state.tool_receipts[0]["arguments"]["y_col"] = "different"
    packet = _packet(state, workspace, history, tmp_path / "other")
    assert "confirmed_observation" not in packet


def test_stale_series_or_forged_fact_refs_cannot_gain_answered(tmp_path):
    state, workspace, history = _setup(tmp_path)
    workspace.add("retention", pd.DataFrame({"day": list(range(1, 8)),
                                               "retention": [*(_Y[:-1]), 0.20]}))
    assert "confirmed_observation" not in _packet(state, workspace, history, tmp_path)

    state, workspace, history = _setup(tmp_path / "fresh")
    packet = _packet(state, workspace, history, tmp_path / "fresh")
    candidate = ps.produce_m02_receipt_claim_candidate(packet, _RECEIPT)
    _visible, bindings, issues = ps.parse_answer_bindings(candidate, packet)
    assert not issues
    forged = deepcopy(bindings["blocks"][0])
    forged["fact_refs"] = forged["fact_refs"][:-2]
    assert ps._descriptive_fit_binding_issue(forged, packet) is not None


def test_percentage_points_are_not_silently_multiplied(tmp_path):
    state, workspace, history = _setup(tmp_path, answer="percentage_points")
    packet = _packet(state, workspace, history, tmp_path)
    candidate = ps.produce_m02_receipt_claim_candidate(packet, _RECEIPT)
    rendered, error = _finalize(packet, candidate)
    assert error is None and rendered
    assert "0.1%" in rendered and "10%" not in rendered
    assert packet["requirements"][0]["answer_coverage"] == "answered"


def test_missing_middle_observation_fails_closed(tmp_path):
    state, workspace, history = _setup(tmp_path)
    state.tool_receipts[0]["publication_facts"] = [
        fact for fact in state.tool_receipts[0]["publication_facts"]
        if fact["path"] != "points[3].y"
    ]
    state.tool_receipts[0]["publication_fact_groups"] = [
        group for group in state.tool_receipts[0]["publication_fact_groups"]
        if group["source_path"] != "points[3]"
    ]
    packet = _packet(state, workspace, history, tmp_path)
    assert "confirmed_observation" not in packet
    candidate = ps.produce_m02_receipt_claim_candidate(packet, _RECEIPT)
    assert candidate is not None
    rendered, error = _finalize(packet, candidate)
    assert error is None and rendered
    assert all(item["answer_coverage"] != "answered" for item in packet["requirements"])
