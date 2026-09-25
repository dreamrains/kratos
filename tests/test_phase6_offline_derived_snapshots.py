"""One bounded, identity-bound derived-result snapshot for existing tool families."""

import json

import pandas as pd

from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.publication_synthesis import (
    build_publication_packet,
    render_trusted_core_preview,
)
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


def test_archived_r16_transform_receipt_replays_values_and_method_when_present():
    """Historical passed prose is context; replay only its executed receipt and frame."""
    from pathlib import Path
    import pytest

    session_root = (Path(__file__).resolve().parents[1]
                    / "tmp/p08-real-provider-20260914-b833501-r1/sessions/58da9082dc02")
    state_path = session_root / "analysis_state.json"
    meta_path = session_root / "workspace_meta.json"
    if not state_path.is_file() or not meta_path.is_file():
        pytest.skip("archived R16 session is not part of a clean checkout")
    state = AnalysisSessionState.from_dict(
        json.loads(state_path.read_text(encoding="utf-8")), "58da9082dc02",
    )
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    workspace = Workspace()
    for name in ("M01-sales", "M01-sales_totals"):
        frame_path = session_root / "data" / f"{name}.pkl"
        if not frame_path.is_file() or name not in meta:
            pytest.skip("archived R16 data frame is not available")
        workspace._datasets[name] = pd.read_pickle(frame_path)
        workspace._metadata[name] = {"data_identity": meta[name]["data_identity"]}
    packet = build_publication_packet(
        state, user_input="订单记录数与 amount 总额",
        substantive_tools={"transform_data"}, receipt_ids=["tr_fb774270b1c9"],
        offline_trust_projection=True, offline_workspace=workspace,
    )
    snapshots = packet["offline_trust_projection"]["derived_snapshots"]
    assert len(snapshots) == 1
    snapshot = snapshots[0]
    assert snapshot["rows"][0]["order_id_size"] == {"type": "number", "value": "12"}
    assert snapshot["rows"][0]["amount_sum"] == {"type": "number", "value": "120"}
    assert snapshot["method_parameters"] == {
        "group_by": ["channel"],
        "agg": {"order_id": ["count", "size"],
                "amount": ["sum", "mean", "min", "max"]},
    }
    assert snapshot["status"] == "context_only"
    assert all(item["answer_coverage"] == "unassessed" for item in packet["requirements"])
    preview = render_trusted_core_preview(packet, None)
    assert preview["publication_effect"] == "none"
    assert "order_id_size" in preview["text"] and "amount_sum" in preview["text"]
    assert "group_by=channel" in preview["text"]
    assert "order_id: count, size" in preview["text"]


def test_archived_r4_m03_synthesis_replays_six_source_values_when_present():
    from pathlib import Path
    import pytest

    root = (Path(__file__).resolve().parents[1]
            / "tmp/p08-glm-operator-20260922-r4/sessions/50e734df7af7")
    if not (root / "analysis_state.json").is_file() or not (root / "workspace_meta.json").is_file():
        pytest.skip("archived R4 M03 session is not part of a clean checkout")
    state = AnalysisSessionState.from_dict(
        json.loads((root / "analysis_state.json").read_text(encoding="utf-8")),
        "50e734df7af7",
    )
    meta = json.loads((root / "workspace_meta.json").read_text(encoding="utf-8"))
    workspace = Workspace()
    names = [f"M03-source-{index}" for index in range(1, 7)] + ["sources_combined"]
    for name in names:
        frame_path = root / "data" / f"{name}.pkl"
        if name not in meta or not frame_path.is_file():
            pytest.skip("archived R4 M03 frame is not available")
        workspace._datasets[name] = pd.read_pickle(frame_path)
        workspace._metadata[name] = {"data_identity": meta[name]["data_identity"]}
    packet = build_publication_packet(
        state, user_input="六来源两日金额与变化",
        substantive_tools={"synthesize_time_series"},
        receipt_ids=["tr_3e70ccb10380"], offline_trust_projection=True,
        offline_workspace=workspace,
    )
    snapshots = packet["offline_trust_projection"]["derived_snapshots"]
    assert len(snapshots) == 1
    snapshot = snapshots[0]
    assert snapshot["derived_dataset"] == "sources_combined"
    assert len(snapshot["rows"]) == 2
    assert snapshot["rows"][0]["M03-source-1"] == {"type": "number", "value": "10"}
    assert snapshot["rows"][1]["M03-source-6"] == {"type": "number", "value": "66"}
    assert snapshot["status"] == "context_only"
    assert render_trusted_core_preview(packet, None)["publication_effect"] == "none"
