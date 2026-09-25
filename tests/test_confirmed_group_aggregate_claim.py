"""One confirmed R16-shaped continuation must close through the existing bindings."""

import hashlib
import json
from copy import deepcopy
from types import SimpleNamespace

import pandas as pd

from data_agent.agent.confirmation.runtime import (
    build_action_registry, build_aggregate_mapping_candidate,
)
from data_agent.agent.confirmation.service import ConfirmationService
from data_agent.agent.loop import AgentLoop
from data_agent.agent.loop import UserConfirmationRequired
from data_agent.agent.context import use_agent_context
from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.publication_synthesis import (
    build_publication_packet, parse_answer_bindings,
    produce_confirmed_aggregate_claim_candidate,
)
from data_agent.session.history import CanonicalHistorySnapshot, _history_sha256
from data_agent.session.workspace import Workspace


FIRST = "请明确计算并列出订单记录数与 amount 总额。"
LAST = "请恢复技术表达，列出计算方法与证据边界，但不要改变数字。"
SPAN = "订单记录数与 amount 总额"


def _fixture():
    workspace = Workspace()
    workspace.add("sales", pd.DataFrame({"channel": ["A"] * 12,
                                          "order_id": list(range(12)),
                                          "amount": [10] * 12}))
    totals = pd.DataFrame({"channel": ["A"], "order_id_count": [12],
                           "order_id_size": [12], "amount_sum": [120],
                           "amount_mean": [10], "amount_min": [10],
                           "amount_max": [10]})
    assert not workspace.derive(
        "sales", "sales_totals", totals,
        expression='group_aggregate: {"group_by": ["channel"], "agg": {"order_id": ["count", "size"], "amount": ["sum", "mean", "min", "max"]}}',
    ).startswith("Error:")
    state = AnalysisSessionState("aggregate_session")
    state.tool_receipts = [{
        "id": "tr_totals", "tool_name": "transform_data",
        "result_sha256": "sha256:aggregate-result", "result_preview": "group aggregate saved",
        "arguments": {"name": "sales", "save_as": "sales_totals",
                      "operation": "group_aggregate", "group_by": ["channel"],
                      "aggregations": [{"column": "order_id", "functions": ["count", "size"]},
                                       {"column": "amount", "functions": ["sum", "mean", "min", "max"]}]},
        "data_identities": {name: workspace.get_data_identity(name)
                            for name in ("sales", "sales_totals")},
        "publication_facts": [
            {"path": "operation", "value": "group_aggregate"},
            {"path": "rows", "value": "1"},
            {"path": "dataset", "value": "sales_totals"},
            {"path": "source_dataset", "value": "sales"},
            *({"path": f"columns[{index}]", "value": name}
              for index, name in enumerate(totals.columns)),
        ],
    }]
    return state, workspace


def _case(tmp_path, answer="row_count_sum"):
    state, workspace = _fixture()
    state.session_id = "aggregate_session"
    messages = [{"role": "user", "content": FIRST}, {"role": "user", "content": LAST}]
    history = CanonicalHistorySnapshot(messages, 2, _history_sha256(messages), 2)
    target = dict(
        session_id=state.session_id, turn_id="turn_2", workspace=workspace,
        receipt=state.tool_receipts[0],
        canonical_history=history,
        source_message_ref="msg_" + hashlib.sha256(FIRST.encode()).hexdigest()[:12],
        current_message_ref="msg_" + hashlib.sha256(LAST.encode()).hexdigest()[:12],
        exact_span=SPAN, dataset="sales", derived_dataset="sales_totals",
        receipt_id="tr_totals", order_column="order_id", amount_column="amount",
    )
    candidate = build_aggregate_mapping_candidate(**target)
    assert candidate is not None
    service = ConfirmationService(tmp_path, action_registry=build_action_registry())
    service.request(candidate)
    if answer == "skipped":
        service.skip(state.session_id, candidate.confirmation_id,
                     service.checkpoint(state.session_id).version, "skip_aggregate")
    else:
        service.respond(state.session_id, candidate.confirmation_id, answer,
                        service.checkpoint(state.session_id).version, "answer_aggregate")
    return state, workspace, history, target, candidate


def _packet(state, workspace, history, root):
    return build_publication_packet(
        state, user_input=LAST, substantive_tools=set(), receipt_ids=["tr_totals"],
        offline_trust_projection=True, offline_confirmed_aggregate=True,
        offline_workspace=workspace, canonical_history=history,
        confirmation_sessions_root=root,
    )


def test_confirmed_row_count_and_amount_sum_render_two_typed_claims(tmp_path):
    state, workspace, history, target, candidate = _case(tmp_path)
    assert candidate.question.count("？") == 2
    assert ConfirmationService(tmp_path, action_registry=build_action_registry()).request(
        build_aggregate_mapping_candidate(**{**target, "turn_id": "turn_3"})
    ).reused_confirmation_id == candidate.confirmation_id
    packet = _packet(state, workspace, history, tmp_path)
    claim = produce_confirmed_aggregate_claim_candidate(packet, "tr_totals")
    visible, bindings, issues = parse_answer_bindings(claim, packet)
    assert not issues and len(bindings["blocks"]) == 2 and visible
    loop = SimpleNamespace(_turn_publication_packet=packet,
                           _turn_origin_revision_issued=False,
                           context=SimpleNamespace(turn_state=None))
    rendered, error = AgentLoop._render_finalized_publication(loop, claim)
    assert error is None and rendered
    assert "12" in rendered and "120" in rendered and "单位未确认" in rendered
    assert "group_aggregate" in rendered and "channel" in rendered and "当前仅一组" in rendered
    assert [item["answer_coverage"] for item in packet["requirements"]] == ["answered", "answered"]
    assert len(packet["answer_render_trace"]["entries"]) == 2


def test_skip_stale_and_wrong_method_do_not_promote_context(tmp_path):
    state, workspace, history, target, candidate = _case(tmp_path, answer="skipped")
    assert _packet(state, workspace, history, tmp_path).get("confirmed_aggregate") is None
    assert ConfirmationService(tmp_path, action_registry=build_action_registry()).request(
        candidate
    ).disposition.value == "advisory"

    state, workspace, history, _, _ = _case(tmp_path / "stale")
    workspace.add("sales", pd.DataFrame({"channel": ["A"], "order_id": [1], "amount": [999]}))
    assert _packet(state, workspace, history, tmp_path / "stale").get("confirmed_aggregate") is None

    state, workspace, history, _, _ = _case(tmp_path / "wrong")
    state.tool_receipts[0]["arguments"]["group_by"] = ["order_id"]
    assert _packet(state, workspace, history, tmp_path / "wrong").get("confirmed_aggregate") is None


def test_distinct_response_requires_executed_distinct_method(tmp_path):
    state, workspace, history, _, _ = _case(tmp_path, answer="distinct_id_sum")
    packet = _packet(state, workspace, history, tmp_path)
    assert "confirmed_aggregate" not in packet
    assert produce_confirmed_aggregate_claim_candidate(packet, "tr_totals") is None


def test_wrong_aggregate_value_and_unselected_receipt_stay_unassessed(tmp_path):
    state, workspace, history, _, _ = _case(tmp_path)
    bad = workspace.get("sales_totals").copy()
    bad.loc[0, "amount_sum"] = 999
    workspace.add("sales_totals", bad)
    # A changed derived version invalidates both the receipt and the decision.
    assert _packet(state, workspace, history, tmp_path).get("confirmed_aggregate") is None
    state, workspace, history, _, _ = _case(tmp_path / "unselected")
    packet = build_publication_packet(
        state, user_input=LAST, substantive_tools=set(), receipt_ids=[],
        offline_trust_projection=True, offline_confirmed_aggregate=True,
        offline_workspace=workspace, canonical_history=history,
        confirmation_sessions_root=tmp_path / "unselected",
    )
    assert "confirmed_aggregate" not in packet


def test_forged_fact_and_unrelated_turn_fail_closed(tmp_path):
    state, workspace, history, _, _ = _case(tmp_path)
    packet = _packet(state, workspace, history, tmp_path)
    candidate = produce_confirmed_aggregate_claim_candidate(packet, "tr_totals")
    payload = json.loads(candidate.split("```answer-bindings\n", 1)[1].split("\n```", 1)[0])
    payload["blocks"][0]["fact_refs"] = payload["blocks"][1]["fact_refs"]
    forged = "\n\n".join(block["exact_text"] for block in payload["blocks"])
    forged += "\n\n```answer-bindings\n" + json.dumps(payload) + "\n```"
    _, bindings, issues = parse_answer_bindings(forged, packet)
    assert issues and len(bindings["blocks"]) == 1

    changed = deepcopy(history.messages)
    changed[-1]["content"] = "另一个问题"
    unrelated = CanonicalHistorySnapshot(changed, 2, _history_sha256(changed), 2)
    assert _packet(state, workspace, unrelated, tmp_path).get("confirmed_aggregate") is None


def test_existing_question_tool_routes_one_aggregate_confirmation(tmp_path, monkeypatch):
    state, workspace = _fixture()
    loop = AgentLoop(session_id=state.session_id)
    loop.context.workspace = workspace
    loop.context.analysis_state = state
    loop.messages = [{"role": "user", "content": FIRST},
                     {"role": "user", "content": LAST}]
    service = ConfirmationService(tmp_path, action_registry=build_action_registry())
    monkeypatch.setattr(loop, "_confirmation_runtime", lambda: service)
    target = {"kind": "group_aggregate", "exact_span": SPAN,
              "dataset": "sales", "derived_dataset": "sales_totals",
              "receipt_id": "tr_totals", "order_column": "order_id",
              "amount_column": "amount"}
    request = UserConfirmationRequired(
        question="模型建议", options=[],
        measurement_mapping=json.dumps(target, ensure_ascii=False),
    )
    with use_agent_context(loop.context):
        result = loop._suspend_for_confirmation_request(request, turn_id="turn_2")
    assert hasattr(result, "confirmation_id"), result
    record = service.get(state.session_id, result.confirmation_id)
    assert record.source == "host_aggregate_mapping.v1"
    assert "模型建议" not in record.question
    with use_agent_context(loop.context):
        again = loop._suspend_for_confirmation_request(request, turn_id="turn_2")
    assert again.confirmation_id == result.confirmation_id
    forged = UserConfirmationRequired(
        question="模型建议", options=[],
        measurement_mapping=json.dumps({**target, "receipt_id": "tr_fake"}, ensure_ascii=False),
    )
    with use_agent_context(loop.context):
        rejected = loop._suspend_for_confirmation_request(forged, turn_id="turn_2")
    assert isinstance(rejected, str) and "未评估" in rejected
