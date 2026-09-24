"""One bounded, identity-bound derived-result snapshot for existing tool families."""

import hashlib
import json
from copy import deepcopy

import pandas as pd

from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.publication_synthesis import (
    build_publication_packet,
    parse_answer_bindings,
    render_trusted_core_preview,
    validate_offline_multiturn_metric_links,
)
from data_agent.session.history import CanonicalHistorySnapshot, _history_sha256
from data_agent.session.workspace import Workspace


def _fixture():
    workspace = Workspace()
    dates = pd.to_datetime(["2026-09-01", "2026-09-02"])
    workspace.add("source_a", pd.DataFrame({"date": dates, "amount": [10, 11]}))
    workspace.add("source_b", pd.DataFrame({"date": dates, "amount": [20, 22]}))
    aligned = pd.DataFrame({"date": dates, "source_a": [10, 11], "source_b": [20, 22]})
    assert not workspace.derive_multi(["source_a", "source_b"], "combined", aligned,
                                      expression="date-aligned daily sums").startswith("Error:")
    workspace.add("sales", pd.DataFrame({"channel": ["A"] * 12, "order_id": list(range(12)),
                                          "amount": [10] * 12}))
    totals = pd.DataFrame({"channel": ["A"], "order_id_count": [12], "order_id_size": [12],
                           "amount_sum": [120], "amount_mean": [10], "amount_min": [10],
                           "amount_max": [10]})
    assert not workspace.derive(
        "sales", "sales_totals", totals,
        expression='group_aggregate: {"group_by": ["channel"], "agg": {"order_id": ["count", "size"], "amount": ["sum", "mean", "min", "max"]}}',
    ).startswith("Error:")

    state = AnalysisSessionState("derived_snapshot_calibration")
    state.tool_receipts = [{
        "id": "tr_aligned", "tool_name": "synthesize_time_series",
        "result_sha256": "sha256:aligned-result", "result_preview": "aligned",
        "data_identities": {name: workspace.get_data_identity(name)
                            for name in ("source_a", "source_b", "combined")},
        "publication_facts": [
            {"path": "method_contract", "value": "multi_file_time_synthesis.v1"},
            {"path": "status", "value": "supported"},
            {"path": "claim_ceiling", "value": "descriptive"},
            {"path": "aligned_rows", "value": "2"},
            {"path": "derived_dataset", "value": "combined"},
            {"path": "derived_identity.version_id", "value": workspace.get_data_identity("combined")["version_id"]},
            {"path": "derived_identity.fingerprint", "value": workspace.get_data_identity("combined")["fingerprint"]},
            *({"path": f"source_datasets[{index}]", "value": name}
              for index, name in enumerate(("source_a", "source_b"))),
            *({"path": f"coverage.{name}.{field}", "value": value}
              for name in ("source_a", "source_b")
              for field, value in (("metric", "amount"), ("rows", "2"),
                                   ("effective_rows", "2"), ("start", "2026-09-01"),
                                   ("end", "2026-09-02"))),
            *({"path": f"source_identities.{name}.{field}", "value": workspace.get_data_identity(name)[field]}
              for name in ("source_a", "source_b") for field in ("version_id", "fingerprint")),
            *({"path": f"missing_aligned_dates.{name}", "value": "0"}
              for name in ("source_a", "source_b")),
        ],
    }, {
        "id": "tr_totals", "tool_name": "transform_data",
        "result_sha256": "sha256:totals-result", "result_preview": "group aggregate saved",
        "arguments": {
            "name": "sales", "save_as": "sales_totals", "operation": "group_aggregate",
            "group_by": ["channel"], "aggregations": [
                {"column": "order_id", "functions": ["count", "size"]},
                {"column": "amount", "functions": ["sum", "mean", "min", "max"]},
            ],
        },
        "data_identities": {name: workspace.get_data_identity(name) for name in ("sales", "sales_totals")},
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


def _packet(state, workspace, receipt_ids):
    return build_publication_packet(
        state, user_input="保留六来源比较以及订单数量和金额结果",
        substantive_tools=set(), receipt_ids=receipt_ids,
        offline_trust_projection=True, offline_workspace=workspace,
    )


def test_generic_snapshot_covers_two_derived_tool_families_without_answer_authority():
    state, workspace = _fixture()
    packet = _packet(state, workspace, ["tr_aligned", "tr_totals"])
    snapshots = packet["offline_trust_projection"]["derived_snapshots"]
    assert {item["receipt_id"] for item in snapshots} == {"tr_aligned", "tr_totals"}
    aligned = next(item for item in snapshots if item["receipt_id"] == "tr_aligned")
    totals = next(item for item in snapshots if item["receipt_id"] == "tr_totals")
    assert aligned["derived_dataset"] == "combined" and len(aligned["rows"]) == 2
    assert totals["derived_dataset"] == "sales_totals" and len(totals["rows"]) == 1
    assert totals["rows"][0]["amount_sum"] == {"type": "number", "value": "120"}
    assert totals["rows"][0]["order_id_count"] == {"type": "number", "value": "12"}
    assert totals["rows"][0]["channel"] == {"type": "redacted"}
    assert totals["method_parameters"] == {
        "group_by": ["channel"], "agg": {"order_id": ["count", "size"],
                                      "amount": ["sum", "mean", "min", "max"]},
    }
    assert all(item["status"] == "context_only" for item in snapshots)
    preview = render_trusted_core_preview(packet, None)
    assert "amount_sum" in preview["text"] and "120" in preview["text"]
    assert "group_by" in preview["text"] and "channel" in preview["text"]
    assert preview["accepted_claim_ids"] == []
    normal = build_publication_packet(
        state, user_input="订单数量和金额", substantive_tools=set(),
        receipt_ids=["tr_totals"],
    )
    assert "offline_trust_projection" not in normal
    assert normal["sources"] == []
    assert packet["snapshot_digest"] != normal["snapshot_digest"]


def test_snapshot_requires_selected_receipt_and_current_parent_and_derived_versions():
    state, workspace = _fixture()
    assert [item["receipt_id"] for item in _packet(
        state, workspace, ["tr_totals"]
    )["offline_trust_projection"]["derived_snapshots"]] == ["tr_totals"]
    assert _packet(state, workspace, ["tr_aligned"])["offline_trust_projection"]["derived_snapshots"][0]["receipt_id"] == "tr_aligned"
    assert _packet(state, None, ["tr_totals"])["offline_trust_projection"].get("derived_snapshots", []) == []
    workspace.add("sales", pd.DataFrame({"channel": ["A"], "order_id": [1], "amount": [99]}))
    projection = _packet(state, workspace, ["tr_totals"])["offline_trust_projection"]
    assert projection["derived_snapshots"] == []
    assert projection["snapshot_omissions"] == []  # stale identity is not a budget omission


def test_over_budget_derived_frame_is_not_silently_promoted():
    state, workspace = _fixture()
    workspace.add("many", pd.DataFrame({"value": list(range(17))}))
    assert not workspace.derive(
        "many", "many_derived", pd.DataFrame({"value": list(range(17))}),
        expression="identity",
    ).startswith("Error:")
    receipt = state.tool_receipts[1]
    receipt["data_identities"] = {
        name: workspace.get_data_identity(name) for name in ("many", "many_derived")
    }
    receipt["publication_facts"] = [
        {"path": "operation", "value": "identity"},
        {"path": "rows", "value": "17"},
        {"path": "dataset", "value": "many_derived"},
        {"path": "source_dataset", "value": "many"},
        {"path": "columns[0]", "value": "value"},
    ]
    packet = _packet(state, workspace, ["tr_totals"])
    projection = packet["offline_trust_projection"]
    assert projection["derived_snapshots"] == []
    assert projection["snapshot_omissions"] == [
        {"receipt_id": "tr_totals", "reason": "shape_budget"}
    ]
    assert "超出当前离线快照" in render_trusted_core_preview(packet, None)["text"]


def test_mismatched_executed_method_parameters_do_not_gain_method_context():
    state, workspace = _fixture()
    state.tool_receipts[1]["arguments"]["group_by"] = ["order_id"]
    snapshots = _packet(state, workspace, ["tr_totals"])["offline_trust_projection"]["derived_snapshots"]
    assert len(snapshots) == 1
    assert "method_parameters" not in snapshots[0]


def _multiturn_snapshot(messages, revision):
    return CanonicalHistorySnapshot(
        messages=[{"role": "user", "content": item} for item in messages],
        revision=revision,
        sha256=_history_sha256([{"role": "user", "content": item} for item in messages]),
        message_count=len(messages),
    )


def _multiturn_case():
    state, workspace = _fixture()
    first = (
        "请先基于当前订单给出一份证据受限的事实摘要，明确计算并列出订单记录数与 amount 总额。\n"
        "分析文件: M01-sales.csv"
    )
    later = [
        "请改成业务负责人表达，强调可行动含义，但不要改变数字、范围、限制和证据等级。",
        "请改成分析师表达，保留指标、计算和来源绑定，但不要改变数字、范围、限制和证据等级。",
        "请改成管理者表达，突出决策条件，但不要改变数字、范围、限制和证据等级。",
        "请用大白话重述，但不要改变数字、范围、限制和证据等级。",
        "请恢复技术表达，列出计算方法与证据边界，但不要改变数字、范围、限制和证据等级。",
    ]
    prior = build_publication_packet(
        state, user_input=first, substantive_tools=set(), receipt_ids=["tr_totals"],
        offline_trust_projection=True, offline_workspace=workspace,
    )
    state.add_publication_packet(prior)
    current = build_publication_packet(
        state, user_input=later[-1], substantive_tools=set(), receipt_ids=[],
        offline_trust_projection=True, offline_workspace=workspace,
    )
    source_ref = "msg_" + hashlib.sha256(first.encode("utf-8")).hexdigest()[:12]
    proposal = {
        "schema_version": "answer_bindings.v1",
        "packet_digest": current["binding_digest"],
        "blocks": [{
            "claim_id": "claim_amount", "exact_text": "[[claim:claim_amount]]",
            "claim_type": "observed_fact", "status": "unassessed",
            "requirement_refs": [], "fact_refs": [], "derived_refs": [],
            "source_span_selector": {
                "source_message_ref": source_ref,
                "exact_span": "amount 总额",
                "prior_packet_id": prior["id"],
                "receipt_ref": "tr_totals",
                "result_version_id": workspace.get_data_identity("sales_totals")["version_id"],
                "metric_column": "amount",
            },
        }],
    }
    return state, workspace, prior, current, proposal, _multiturn_snapshot([first], 1), _multiturn_snapshot([first, *later], 6)


def test_multiturn_literal_metric_link_preserves_identity_without_answer_authority():
    state, workspace, _, current, proposal, prior_history, current_history = _multiturn_case()

    checked = validate_offline_multiturn_metric_links(
        current, proposal, state=state, offline_workspace=workspace,
        prior_history=prior_history, current_history=current_history,
    )

    assert checked["publication_effect"] == "none"
    assert checked["issues"] == []
    assert checked["results"][0]["link_status"] == "verified_history_and_tool_column"
    assert checked["results"][0]["metric_column"] == "amount"
    assert "sum" in checked["results"][0]["available_functions"]
    assert checked["results"][0]["intervening_user_turns"] == 5
    assert checked["results"][0]["answer_coverage"] == "unassessed"
    assert checked["results"][0]["continuation_intent_status"] == "unassessed"
    assert checked["results"][0]["unit_status"] == "not_confirmed"
    assert current["offline_trust_projection"]["derived_snapshots"] == []
    _, formal, issues = parse_answer_bindings(
        "[[claim:claim_amount]]\n```answer-bindings\n"
        + json.dumps(proposal, ensure_ascii=False) + "\n```",
        current,
    )
    assert formal is None or formal["blocks"] == []
    assert any(item["code"] == "invalid_observed_binding" for item in issues)


def test_multiturn_link_rejects_unmatched_metric_and_stale_lineage():
    state, workspace, prior, current, proposal, prior_history, current_history = _multiturn_case()
    selector = proposal["blocks"][0]["source_span_selector"]
    selector["metric_column"] = "order_id"
    assert validate_offline_multiturn_metric_links(
        current, proposal, state=state, offline_workspace=workspace,
        prior_history=prior_history, current_history=current_history,
    )["results"] == []
    selector["metric_column"] = "amount"
    selector["exact_span"] = "订单记录数"
    assert validate_offline_multiturn_metric_links(
        current, proposal, state=state, offline_workspace=workspace,
        prior_history=prior_history, current_history=current_history,
    )["results"] == []
    selector["exact_span"] = "amount 总额"
    workspace.add("sales", pd.DataFrame({"channel": ["B"], "order_id": [1], "amount": [99]}))
    assert validate_offline_multiturn_metric_links(
        current, proposal, state=state, offline_workspace=workspace,
        prior_history=prior_history, current_history=current_history,
    )["results"] == []
    assert prior["offline_trust_projection"]["derived_snapshots"]


def test_multiturn_link_rejects_forged_history_packet_and_unpersisted_prior():
    state, workspace, prior, current, proposal, prior_history, current_history = _multiturn_case()
    forged = CanonicalHistorySnapshot(
        messages=current_history.messages, revision=current_history.revision,
        sha256="sha256:forged", message_count=current_history.message_count,
    )
    assert validate_offline_multiturn_metric_links(
        current, proposal, state=state, offline_workspace=workspace,
        prior_history=prior_history, current_history=forged,
    )["results"] == []
    tampered = deepcopy(prior)
    tampered["sources"][0]["result_sha256"] = "sha256:forged"
    state.publication_packets = [tampered]
    assert validate_offline_multiturn_metric_links(
        current, proposal, state=state, offline_workspace=workspace,
        prior_history=prior_history, current_history=current_history,
    )["results"] == []
    state.publication_packets = []
    assert validate_offline_multiturn_metric_links(
        current, proposal, state=state, offline_workspace=workspace,
        prior_history=prior_history, current_history=current_history,
    )["results"] == []
