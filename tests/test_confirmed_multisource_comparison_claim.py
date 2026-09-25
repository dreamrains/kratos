"""Executed six-source comparisons can render per-source typed values offline."""

import json
from copy import deepcopy
from types import SimpleNamespace

import pandas as pd

from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.loop import AgentLoop
from data_agent.agent.publication_synthesis import (
    build_publication_packet, extract_publication_fact_groups,
    parse_answer_bindings, produce_offline_comparison_claim_candidate,
    publication_contract,
)
from data_agent.session.workspace import Workspace


def _case():
    workspace = Workspace()
    state = AnalysisSessionState("six_compare_typed")
    dates = pd.to_datetime(["2026-09-01", "2026-09-02"])
    ids = []
    for index in range(1, 7):
        name, receipt_id = f"source_{index}", f"tr_cmp_{index}"
        workspace.add(name, pd.DataFrame({"date": dates,
                                          "amount": [10 * index, 11 * index]}))
        result = {
            "period_a": {"range": ["2026-09-01", "2026-09-01"], "rows": 1,
                         "day_count": 1},
            "period_b": {"range": ["2026-09-02", "2026-09-02"], "rows": 1,
                         "day_count": 1},
            "metrics": {"amount": {"period_a": 10 * index,
                                    "period_b": 11 * index, "diff": index}},
        }
        state.tool_receipts.append({
            "id": receipt_id, "tool_name": "compare_periods",
            "result_sha256": f"sha256:compare-{index}",
            "arguments": {"name": name, "date_col": "date", "metrics": "amount"},
            "dataset_refs": [name],
            "data_identities": {name: workspace.get_data_identity(name)},
            "publication_fact_groups": extract_publication_fact_groups(
                result, receipt_id=receipt_id)["groups"],
            "publication_contract": publication_contract(
                "compare_periods", result, args={"name": name}),
        })
        ids.append(receipt_id)
    return state, workspace, ids


def _packet(state, workspace, ids):
    return build_publication_packet(
        state, user_input="逐来源列出两日金额与变化", substantive_tools={"compare_periods"},
        receipt_ids=ids, offline_trust_projection=True, offline_workspace=workspace,
    )


def test_six_executed_comparisons_render_six_source_bound_claims():
    state, workspace, ids = _case()
    packet = _packet(state, workspace, ids)
    candidate = produce_offline_comparison_claim_candidate(packet, ids)
    visible, bindings, issues = parse_answer_bindings(candidate, packet)
    assert not issues and visible and len(bindings["blocks"]) == 6
    loop = SimpleNamespace(_turn_publication_packet=packet,
                           _turn_origin_revision_issued=False,
                           context=SimpleNamespace(turn_state=None))
    rendered, error = AgentLoop._render_finalized_publication(loop, candidate)
    assert error is None and rendered
    assert "source_1" in rendered and "source_6" in rendered
    assert "10" in rendered and "11" in rendered and "60" in rendered and "66" in rendered
    assert "七天" not in rendered and "相互独立" not in rendered and "210" not in rendered
    assert len(packet["answer_render_trace"]["entries"]) == 6
    assert packet["requirements"] == []


def test_stale_unselected_or_forged_comparison_fails_closed():
    state, workspace, ids = _case()
    packet = _packet(state, workspace, ids[:-1])
    assert produce_offline_comparison_claim_candidate(packet, ids) is None
    workspace.add("source_2", pd.DataFrame({
        "date": pd.to_datetime(["2026-09-01", "2026-09-02"]),
        "amount": [200, 220],
    }))
    packet = _packet(state, workspace, ids)
    assert produce_offline_comparison_claim_candidate(packet, ids) is None

    state, workspace, ids = _case()
    packet = _packet(state, workspace, ids)
    candidate = produce_offline_comparison_claim_candidate(packet, ids)
    payload = json.loads(candidate.split("```answer-bindings\n", 1)[1].split("\n```", 1)[0])
    payload["blocks"][0]["fact_refs"] = deepcopy(payload["blocks"][1]["fact_refs"])
    forged = "\n\n".join(block["exact_text"] for block in payload["blocks"])
    forged += "\n\n```answer-bindings\n" + json.dumps(payload) + "\n```"
    _, bindings, issues = parse_answer_bindings(forged, packet)
    assert issues and len(bindings["blocks"]) == 5
