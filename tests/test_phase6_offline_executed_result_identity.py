"""Offline executed-result identity must preserve values without granting claims."""

import hashlib
import json
import pandas as pd

from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.publication_synthesis import (
    build_publication_packet, render_trusted_core_preview, update_requirement_lifecycle,
    validate_offline_target_selectors, validate_offline_multiturn_metric_links,
)
from data_agent.session.history import CanonicalHistorySnapshot, _history_sha256
from data_agent.session.workspace import Workspace


def _state_and_workspace():
    workspace = Workspace()
    workspace.add("retention", pd.DataFrame({"day": [1, 7], "retention": [0.55, 0.1]}))
    workspace.add("trend_v2", pd.DataFrame({
        "date": pd.to_datetime(["2026-09-01", "2026-09-02", "2026-09-03"]),
        "amount": [10, 10, 10],
    }))
    state = AnalysisSessionState("result_identity_offline")
    state.tool_receipts = [
        {
            "id": "tr_curve", "tool_name": "curve_fitting", "result_sha256": "sha256:curve",
            "result_preview": "fitted", "arguments": {"name": "retention", "x_col": "day", "y_col": "retention"},
            "data_identities": {"retention": workspace.get_data_identity("retention")},
            "publication_facts": [
                {"path": "points[0].x", "value": "1"}, {"path": "points[0].y", "value": "0.55"},
                {"path": "points[1].x", "value": "7"}, {"path": "points[1].y", "value": "0.1"},
                {"path": "status", "value": "supported"},
                {"path": "claim_ceiling", "value": "descriptive"},
            ],
        },
        {
            "id": "tr_trend", "tool_name": "analyze_time_series", "result_sha256": "sha256:trend",
            "result_preview": "flat", "arguments": {"name": "trend_v2", "date_col": "date", "value_col": "amount"},
            "data_identities": {"trend_v2": workspace.get_data_identity("trend_v2")},
            "publication_facts": [
                {"path": "data_points", "value": "3"},
                {"path": "statistics.mean", "value": "10"},
                {"path": "statistics.std", "value": "0"},
                {"path": "trend.slope", "value": "0"},
                {"path": "trend.direction", "value": "flat"},
            ],
        },
    ]
    return state, workspace


def _packet(state, workspace, ids):
    return build_publication_packet(
        state, user_input="解释 D7 留存和新版本趋势", substantive_tools=set(),
        receipt_ids=ids, offline_trust_projection=True, offline_workspace=workspace,
    )


def test_two_executed_result_shapes_keep_raw_scale_and_no_claim_authority():
    state, workspace = _state_and_workspace()
    packet = _packet(state, workspace, ["tr_curve", "tr_trend"])
    results = packet["offline_trust_projection"]["executed_results"]
    assert {item["receipt_id"] for item in results} == {"tr_curve", "tr_trend"}
    curve = next(item for item in results if item["receipt_id"] == "tr_curve")
    assert curve["input_columns"] == {"x": "day", "y": "retention"}
    assert curve["observations"][-1] == {"x": "7", "y": "0.1"}
    assert curve["unit_status"] == "not_confirmed" and curve["status"] == "context_only"
    trend = next(item for item in results if item["receipt_id"] == "tr_trend")
    assert trend["input_columns"] == {"x": "date", "y": "amount"}
    assert trend["observations"] == {"mean": "10", "std": "0", "slope": "0", "direction": "flat"}
    preview = render_trusted_core_preview(packet, None)
    assert "0.1" in preview["text"] and "10%" not in preview["text"]
    assert preview["accepted_claim_ids"] == [] and preview["publication_effect"] == "none"
    ordinary = build_publication_packet(state, user_input="留存", substantive_tools=set(), receipt_ids=["tr_curve"])
    assert ordinary["sources"] == [] and "offline_trust_projection" not in ordinary


def test_unselected_or_stale_execution_identity_cannot_enter_offline_packet():
    state, workspace = _state_and_workspace()
    assert [item["receipt_id"] for item in _packet(state, workspace, ["tr_curve"])[
        "offline_trust_projection"]["executed_results"]] == ["tr_curve"]
    workspace.add("retention", pd.DataFrame({"day": [1, 7], "retention": [0.55, 0.99]}))
    assert _packet(state, workspace, ["tr_curve"])["offline_trust_projection"]["executed_results"] == []
    state.tool_receipts[1]["arguments"]["value_col"] = "missing"
    assert _packet(state, workspace, ["tr_trend"])["offline_trust_projection"]["executed_results"] == []


def test_arbitrary_text_cells_are_redacted_from_derived_snapshot():
    workspace = Workspace()
    workspace.add("raw", pd.DataFrame({"email": ["secret@example.com"], "amount": [120]}))
    workspace.derive("raw", "filtered", pd.DataFrame({"email": ["secret@example.com"], "amount": [120]}),
                     expression="filter")
    state = AnalysisSessionState("redact_offline")
    state.tool_receipts = [{
        "id": "tr_filter", "tool_name": "transform_data", "result_sha256": "sha256:filter",
        "result_preview": "filtered", "data_identities": {name: workspace.get_data_identity(name)
                                                   for name in ("raw", "filtered")},
        "publication_facts": [
            {"path": "operation", "value": "filter"}, {"path": "rows", "value": "1"},
            {"path": "dataset", "value": "filtered"}, {"path": "source_dataset", "value": "raw"},
            {"path": "columns[0]", "value": "email"}, {"path": "columns[1]", "value": "amount"},
        ],
    }]
    packet = _packet(state, workspace, ["tr_filter"])
    snapshot = packet["offline_trust_projection"]["derived_snapshots"][0]
    assert snapshot["rows"][0]["email"] == {"type": "redacted"}
    assert snapshot["rows"][0]["amount"] == {"type": "number", "value": "120"}
    assert "secret@example.com" not in str(packet)
    assert "secret@example.com" not in render_trusted_core_preview(packet, None)["text"]


def test_point_budget_is_reported_without_partial_observation_claim():
    state, workspace = _state_and_workspace()
    workspace.add("retention", pd.DataFrame({"day": list(range(1, 18)),
                                              "retention": [0.1] * 17}))
    receipt = state.tool_receipts[0]
    receipt["data_identities"] = {"retention": workspace.get_data_identity("retention")}
    receipt["publication_facts"] = [
        *({"path": f"points[{index}].{axis}", "value": str(value)}
          for index in range(17) for axis, value in (("x", index + 1), ("y", 0.1))),
        {"path": "status", "value": "supported"},
        {"path": "claim_ceiling", "value": "descriptive"},
    ]
    packet = _packet(state, workspace, ["tr_curve"])
    projection = packet["offline_trust_projection"]
    assert projection["executed_results"] == []
    assert projection["result_omissions"] == [{"receipt_id": "tr_curve", "reason": "point_budget"}]
    assert "超出当前离线" in render_trusted_core_preview(packet, None)["text"]


def _target_binding(packet, *, receipt="tr_curve", x_col="day", y_col="retention",
                    x="7", y="0.1", version=None):
    curve = packet["offline_trust_projection"]["executed_results"][0]
    return {
        "schema_version": "answer_bindings.v1", "packet_digest": packet["binding_digest"],
        "blocks": [{
            "claim_id": "claim_d7", "exact_text": "[[claim:claim_d7]]",
            "claim_type": "observed_fact", "status": "unassessed",
            "requirement_refs": [], "fact_refs": [], "derived_refs": [],
            "target_selector": {
                "receipt_ref": receipt, "dataset_version_id": version or curve["dataset_version_id"],
                "x_column": x_col, "y_column": y_col, "x_value": x, "expected_y": y,
            },
        }],
    }


def test_offline_selector_verifies_same_receipt_raw_point_but_not_answer_coverage():
    state, workspace = _state_and_workspace()
    packet = _packet(state, workspace, ["tr_curve", "tr_trend"])
    checked = validate_offline_target_selectors(packet, _target_binding(packet))
    assert checked["publication_effect"] == "none"
    assert checked["results"] == [{
        "claim_id": "claim_d7", "target_status": "verified_result_identity",
        "answer_coverage": "unassessed", "receipt_id": "tr_curve",
        "dataset_version_id": packet["offline_trust_projection"]["executed_results"][0]["dataset_version_id"],
        "x_column": "day", "y_column": "retention", "x_value": "7", "raw_value": "0.1",
        "unit_status": "not_confirmed",
    }]
    assert render_trusted_core_preview(packet, None)["accepted_claim_ids"] == []


def test_offline_selector_rejects_wrong_column_point_receipt_version_and_stale_packet():
    state, workspace = _state_and_workspace()
    packet = _packet(state, workspace, ["tr_curve", "tr_trend"])
    variants = [
        {"x_col": "retention"}, {"y_col": "amount"}, {"x": "30"},
        {"y": "0.99"}, {"receipt": "tr_trend"}, {"version": "stale"},
    ]
    for variant in variants:
        checked = validate_offline_target_selectors(packet, _target_binding(packet, **variant))
        assert checked["results"] == [], variant
        assert checked["issues"], variant
    stale = _target_binding(packet)
    stale["packet_digest"] = "sha256:stale"
    assert validate_offline_target_selectors(packet, stale)["results"] == []


def test_offline_selector_does_not_promote_model_requirement_or_live_parser():
    state, workspace = _state_and_workspace()
    packet = _packet(state, workspace, ["tr_curve"])
    binding = _target_binding(packet)
    binding["blocks"][0]["requirement_refs"] = ["model_says_d7"]
    assert validate_offline_target_selectors(packet, binding)["results"] == []
    binding["blocks"][0]["requirement_refs"] = []
    from data_agent.agent.publication_synthesis import parse_answer_bindings
    import json
    answer = "[[claim:claim_d7]]\n```answer-bindings\n" + json.dumps(binding) + "\n```"
    _, accepted, issues = parse_answer_bindings(answer, packet)
    assert accepted["blocks"] == []
    assert issues


def test_offline_selector_cannot_use_projection_value_without_same_receipt_fact():
    state, workspace = _state_and_workspace()
    packet = _packet(state, workspace, ["tr_curve"])
    binding = _target_binding(packet)
    source = next(item for item in packet["sources"] if item["receipt_id"] == "tr_curve")
    point = next(item for item in source["facts"] if item["path"] == "points[1].y")
    point["value"] = "0.99"
    assert validate_offline_target_selectors(packet, binding)["results"] == []


def _canonical(messages):
    return CanonicalHistorySnapshot(
        messages=messages, revision=2, sha256=_history_sha256(messages),
        message_count=len(messages),
    )


def test_offline_request_anchor_uses_persisted_user_source_across_style_turn():
    state, workspace = _state_and_workspace()
    original = "请回答 retention"
    later = "请改写表达，但保留原先结果与证据边界"
    source_ref = "msg_" + hashlib.sha256(original.encode("utf-8")).hexdigest()[:12]
    requirement_ids = update_requirement_lifecycle(state, original, source_message_ref=source_ref)
    assert len(requirement_ids) == 1
    packet = build_publication_packet(
        state, user_input=later, substantive_tools=set(), receipt_ids=["tr_curve"],
        offline_trust_projection=True, offline_workspace=workspace,
    )
    binding = _target_binding(packet)
    binding["blocks"][0]["requirement_refs"] = requirement_ids
    history = _canonical([{"role": "user", "content": original},
                          {"role": "user", "content": later}])
    checked = validate_offline_target_selectors(packet, binding, canonical_history=history)
    assert checked["results"][0]["request_anchor_status"] == "verified_source_and_column"
    assert checked["results"][0]["request_history_sha256"] == history.sha256
    assert checked["results"][0]["request_history_revision"] == history.revision
    assert checked["results"][0]["answer_coverage"] == "unassessed"
    assert checked["results"][0]["unit_status"] == "not_confirmed"
    assert checked["publication_effect"] == "none"


def test_offline_request_anchor_rejects_foreign_history_or_stale_requirement():
    state, workspace = _state_and_workspace()
    original = "请回答 retention"
    source_ref = "msg_" + hashlib.sha256(original.encode("utf-8")).hexdigest()[:12]
    requirement_ids = update_requirement_lifecycle(state, original, source_message_ref=source_ref)
    packet = _packet(state, workspace, ["tr_curve"])
    binding = _target_binding(packet)
    binding["blocks"][0]["requirement_refs"] = requirement_ids
    history = _canonical([{"role": "user", "content": original},
                          {"role": "user", "content": packet["question"]}])
    assert validate_offline_target_selectors(packet, binding, canonical_history=history)["results"]
    forged = _canonical([{"role": "user", "content": "请回答 revenue"},
                         {"role": "user", "content": packet["question"]}])
    assert validate_offline_target_selectors(packet, binding, canonical_history=forged)["results"] == []
    stale = _canonical(history.messages)
    object.__setattr__(stale, "sha256", "sha256:stale")
    assert validate_offline_target_selectors(packet, binding, canonical_history=stale)["results"] == []
    packet["requirements"][0]["lifecycle_status"] = "retracted"
    assert validate_offline_target_selectors(packet, binding, canonical_history=history)["results"] == []


def test_historical_composite_request_does_not_gain_synthetic_intent_or_percent_unit():
    state, workspace = _state_and_workspace()
    historical = (
        "请计算并解释 D1 至 D7 留存；判断当前数据是否可以预测 D30。"
        "若不能，请明确区分已计算结果、证据不足与下一步所需数据，不要给出无依据的 D30 数值。"
    )
    source_ref = "msg_" + hashlib.sha256(historical.encode("utf-8")).hexdigest()[:12]
    assert update_requirement_lifecycle(state, historical, source_message_ref=source_ref) == []
    packet = _packet(state, workspace, ["tr_curve"])
    binding = _target_binding(packet)
    assert validate_offline_target_selectors(packet, binding)["results"][0]["unit_status"] == "not_confirmed"
    workspace.set_metadata("retention", "unit", "percent")
    assert _packet(state, workspace, ["tr_curve"])["offline_trust_projection"]["executed_results"][0][
        "unit_status"] == "not_confirmed"
    binding["blocks"][0]["requirement_refs"] = ["model_invented_requirement"]
    history = _canonical([{"role": "user", "content": historical},
                          {"role": "user", "content": packet["question"]}])
    assert validate_offline_target_selectors(packet, binding, canonical_history=history)["results"] == []


def test_historical_multi_turn_style_chain_does_not_invent_missing_requirement():
    state, workspace = _state_and_workspace()
    first = "请先基于当前订单给出一份证据受限的事实摘要，明确计算并列出订单记录数与 amount 总额。"
    later = "请恢复技术表达，列出计算方法与证据边界，但不要改变数字、范围、限制和证据等级。"
    first_ref = "msg_" + hashlib.sha256(first.encode("utf-8")).hexdigest()[:12]
    later_ref = "msg_" + hashlib.sha256(later.encode("utf-8")).hexdigest()[:12]
    assert update_requirement_lifecycle(state, first, source_message_ref=first_ref) == []
    assert update_requirement_lifecycle(state, later, source_message_ref=later_ref) == []
    packet = build_publication_packet(
        state, user_input=later, substantive_tools=set(), receipt_ids=["tr_curve"],
        offline_trust_projection=True, offline_workspace=workspace,
    )
    assert packet["requirements"] == []
    binding = _target_binding(packet)
    binding["blocks"][0]["requirement_refs"] = ["claim_from_old_prose"]
    history = _canonical([{"role": "user", "content": first},
                          {"role": "user", "content": later}])
    assert validate_offline_target_selectors(packet, binding, canonical_history=history)["results"] == []


def test_multiturn_executed_result_links_only_literal_tool_column():
    state, workspace = _state_and_workspace()
    first = "请回答 retention"
    later = "请换一种表达，保持原结果"
    prior = build_publication_packet(
        state, user_input=first, substantive_tools=set(), receipt_ids=["tr_curve"],
        offline_trust_projection=True, offline_workspace=workspace,
    )
    state.add_publication_packet(prior)
    current = build_publication_packet(
        state, user_input=later, substantive_tools=set(), receipt_ids=[],
        offline_trust_projection=True, offline_workspace=workspace,
    )
    first_history = _canonical([{"role": "user", "content": first}])
    current_history = _canonical([{"role": "user", "content": first},
                                  {"role": "user", "content": later}])
    selector = {
        "source_message_ref": "msg_" + hashlib.sha256(first.encode("utf-8")).hexdigest()[:12],
        "exact_span": "retention", "prior_packet_id": prior["id"],
        "receipt_ref": "tr_curve",
        "result_version_id": workspace.get_data_identity("retention")["version_id"],
        "metric_column": "retention",
    }
    binding = {
        "schema_version": "answer_bindings.v1", "packet_digest": current["binding_digest"],
        "blocks": [{
            "claim_id": "claim_retention", "exact_text": "[[claim:claim_retention]]",
            "claim_type": "observed_fact", "status": "unassessed",
            "requirement_refs": [], "fact_refs": [], "derived_refs": [],
            "source_span_selector": selector,
        }],
    }
    checked = validate_offline_multiturn_metric_links(
        current, binding, state=state, offline_workspace=workspace,
        prior_history=first_history, current_history=current_history,
    )
    assert checked["results"][0]["link_status"] == "verified_history_and_tool_column"
    assert checked["results"][0]["available_functions"] == []
    assert checked["results"][0]["answer_coverage"] == "unassessed"
    selector["exact_span"] = "留存"
    assert validate_offline_multiturn_metric_links(
        current, binding, state=state, offline_workspace=workspace,
        prior_history=first_history, current_history=current_history,
    )["results"] == []


def test_archived_e4_m04_versioned_trends_replay_separately_when_present():
    from pathlib import Path
    import pytest

    root = (Path(__file__).resolve().parents[1]
            / "tmp/trust-reset-p08-real-20260924-r1/sessions/d4776ba7b746")
    if not (root / "analysis_state.json").is_file() or not (root / "workspace_meta.json").is_file():
        pytest.skip("archived E4 M04 session is not part of a clean checkout")
    state = AnalysisSessionState.from_dict(
        json.loads((root / "analysis_state.json").read_text(encoding="utf-8")),
        "d4776ba7b746",
    )
    meta = json.loads((root / "workspace_meta.json").read_text(encoding="utf-8"))
    workspace = Workspace()
    for name in ("M04-hyp-v1", "M04-hyp-v2"):
        frame_path = root / "data" / f"{name}.pkl"
        if name not in meta or not frame_path.is_file():
            pytest.skip("archived E4 M04 frame is not available")
        workspace._datasets[name] = pd.read_pickle(frame_path)
        workspace._metadata[name] = {"data_identity": meta[name]["data_identity"]}
    receipt_ids = [item["id"] for item in state.tool_receipts
                   if item.get("tool_name") == "analyze_time_series"]
    assert len(receipt_ids) == 2
    packet = build_publication_packet(
        state, user_input="核对两版本的观测趋势与假设边界",
        substantive_tools={"analyze_time_series"}, receipt_ids=receipt_ids,
        offline_trust_projection=True, offline_workspace=workspace,
    )
    results = packet["offline_trust_projection"]["executed_results"]
    by_dataset = {item["dataset"]: item for item in results}
    assert set(by_dataset) == {"M04-hyp-v1", "M04-hyp-v2"}
    assert by_dataset["M04-hyp-v1"]["observations"]["mean"] == "16.6667"
    assert by_dataset["M04-hyp-v2"]["observations"]["mean"] == "10"
    assert by_dataset["M04-hyp-v2"]["observations"]["slope"] == "0"
    assert all(item["status"] == "context_only" for item in results)
    # Model-authored evidence remains context in the packet. This archive has
    # no same-snapshot hypothesis set or validated relation to promote.
    assert len(packet["evidence"]) == 2
    assert packet["offline_trust_projection"]["hypotheses"] == []
    preview = render_trusted_core_preview(packet, None)
    assert preview["publication_effect"] == "none"
    assert preview["accepted_claim_ids"] == []
