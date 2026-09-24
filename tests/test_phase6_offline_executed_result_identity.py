"""Offline executed-result identity must preserve values without granting claims."""

import pandas as pd

from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.publication_synthesis import build_publication_packet, render_trusted_core_preview
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
