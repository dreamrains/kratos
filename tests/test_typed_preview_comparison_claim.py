"""A complete current preview may supply the existing comparison binding."""

import hashlib
from copy import deepcopy

import pandas as pd

from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.context import use_agent_context
from data_agent.agent.loop import AgentLoop
from data_agent.agent.publication_synthesis import (
    build_publication_packet, parse_answer_bindings,
    produce_offline_comparison_claim_candidate, publication_contract,
    render_bound_claims,
)
from data_agent.session.workspace import Workspace


def _case():
    state = AnalysisSessionState("preview_comparison_trial")
    workspace = Workspace()
    ids = []
    for index in range(1, 7):
        name, receipt_id = f"src_{index}", f"preview_{index}"
        frame = pd.DataFrame({
            "source": [f"source_{index}"] * 2,
            "date": ["2026-09-01", "2026-09-02"],
            "amount": [10 * index, 11 * index],
        })
        workspace.add(name, frame)
        result = frame.to_string()
        state.tool_receipts.append({
            "id": receipt_id, "tool_name": "preview_data",
            "arguments": {"name": name}, "dataset_refs": [name],
            "data_identities": {name: workspace.get_data_identity(name)},
            "result_preview": result,
            "result_sha256": "sha256:" + hashlib.sha256(result.encode()).hexdigest(),
            "publication_contract": publication_contract("preview_data", None, args={"name": name}),
        })
        ids.append(receipt_id)
    return state, workspace, ids


def _packet(state, workspace, ids, *, trial=True):
    return build_publication_packet(
        state, user_input="逐来源列出六个文件的两日金额与变化",
        substantive_tools={"preview_data"}, receipt_ids=ids,
        offline_trust_projection=trial, offline_workspace=workspace if trial else None,
    )


def test_six_complete_previews_render_six_current_source_comparisons():
    state, workspace, ids = _case()
    packet = _packet(state, workspace, ids)
    candidate = produce_offline_comparison_claim_candidate(packet, ids)
    assert candidate is not None
    visible, bindings, issues = parse_answer_bindings(candidate, packet)
    assert not issues and len(bindings["blocks"]) == 6
    rendered = render_bound_claims(visible, packet, bindings)
    assert "src_1" in rendered and "src_6" in rendered
    assert "10" in rendered and "11" in rendered and "60" in rendered and "66" in rendered
    assert packet["requirements"] == []
    assert produce_offline_comparison_claim_candidate(_packet(state, workspace, ids, trial=False), ids) is None


def test_preview_comparison_requires_complete_untampered_same_version_shape():
    for mutation in ("truncated", "hash", "stale", "extra_row", "duplicate_date",
                     "missing_date", "mixed_source", "non_numeric", "nan_amount", "n_zero"):
        state, workspace, ids = _case()
        receipt = state.tool_receipts[0]
        frame = workspace.get("src_1").copy()
        if mutation == "truncated":
            receipt["result_preview"] = receipt["result_preview"][:-1]
        elif mutation == "hash":
            receipt["result_sha256"] = "sha256:forged"
        elif mutation == "stale":
            frame.loc[0, "amount"] = 100
            workspace.add("src_1", frame)
        elif mutation == "extra_row":
            frame = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
            workspace.add("src_1", frame)
        elif mutation == "duplicate_date":
            frame.loc[1, "date"] = frame.loc[0, "date"]
            workspace.add("src_1", frame)
        elif mutation == "missing_date":
            frame.loc[1, "date"] = None
            workspace.add("src_1", frame)
        elif mutation == "mixed_source":
            frame.loc[1, "source"] = "other"
            workspace.add("src_1", frame)
        elif mutation == "non_numeric":
            frame["amount"] = ["ten", "eleven"]
            workspace.add("src_1", frame)
        elif mutation == "nan_amount":
            frame.loc[1, "amount"] = float("nan")
            workspace.add("src_1", frame)
        elif mutation == "n_zero":
            receipt["arguments"]["n"] = 0
        packet = _packet(state, workspace, ids)
        assert produce_offline_comparison_claim_candidate(packet, ids) is None, mutation

    state, workspace, ids = _case()
    assert produce_offline_comparison_claim_candidate(_packet(state, workspace, ids[:-1]), ids) is None
    state, workspace, ids = _case()
    state.tool_receipts[0]["data_identities"] = deepcopy(state.tool_receipts[1]["data_identities"])
    assert produce_offline_comparison_claim_candidate(_packet(state, workspace, ids), ids) is None


def test_opt_in_loop_injects_only_verified_preview_template():
    state, workspace, ids = _case()
    loop = AgentLoop(session_id=state.session_id, typed_trial=True)
    loop.context.analysis_state = state
    loop.context.workspace = workspace
    loop.context.turn_receipt_ids = ids
    loop.messages = [{"role": "user", "content": "逐来源列出六个文件的两日金额与变化"}]
    with use_agent_context(loop.context):
        assert loop._maybe_inject_typed_trial(loop.messages[0]["content"]) is True
        preview_digest = loop._turn_publication_packet["binding_digest"]
        packet = loop._prepare_publication_packet(loop.messages[0]["content"], phase="final", persist=False)
    assert packet["binding_digest"] == preview_digest
    assert "claim_comparison_" in loop.messages[-1]["content"]
    assert "offline_trust_projection" not in loop.messages[-1]["content"]
    candidate = produce_offline_comparison_claim_candidate(packet, ids)
    rendered, error = loop._render_finalized_publication(candidate)
    assert error is None and "src_6" in rendered
    assert len(packet["answer_render_trace"]["entries"]) == 6
