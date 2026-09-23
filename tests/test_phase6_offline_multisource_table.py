"""Receipt- and workspace-bound two-date value preview; never live publication."""

import pandas as pd

from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.publication_synthesis import build_publication_packet, render_trusted_core_preview
from data_agent.session.workspace import Workspace


def _six_source_fixture(*, zero_first_source=False):
    workspace = Workspace()
    names = [f"source_{index}" for index in range(1, 7)]
    dates = pd.to_datetime(["2026-09-01", "2026-09-02"])
    aligned = pd.DataFrame({"date": dates})
    facts = [
        {"path": "method_contract", "value": "multi_file_time_synthesis.v1"},
        {"path": "status", "value": "supported"},
        {"path": "claim_ceiling", "value": "descriptive"},
        {"path": "aligned_rows", "value": "2"},
        {"path": "derived_dataset", "value": "combined"},
    ]
    for index, name in enumerate(names, 1):
        values = [0, 10] if zero_first_source and index == 1 else [index * 10, index * 11]
        workspace.add(name, pd.DataFrame({"date": dates, "amount": values}))
        aligned[name] = values
        facts.extend([
            {"path": f"source_datasets[{index - 1}]", "value": name},
            {"path": f"coverage.{name}.metric", "value": "amount"},
            {"path": f"coverage.{name}.rows", "value": "2"},
            {"path": f"coverage.{name}.effective_rows", "value": "2"},
            {"path": f"coverage.{name}.start", "value": "2026-09-01"},
            {"path": f"coverage.{name}.end", "value": "2026-09-02"},
            {"path": f"missing_aligned_dates.{name}", "value": "0"},
            {"path": f"source_identities.{name}.version_id", "value": workspace.get_data_identity(name)["version_id"]},
            {"path": f"source_identities.{name}.fingerprint", "value": workspace.get_data_identity(name)["fingerprint"]},
        ])
    assert not workspace.derive_multi(names, "combined", aligned, expression="date-aligned daily sums").startswith("Error:")
    derived = workspace.get_data_identity("combined")
    facts.extend([
        {"path": "derived_identity.version_id", "value": derived["version_id"]},
        {"path": "derived_identity.fingerprint", "value": derived["fingerprint"]},
    ])
    state = AnalysisSessionState("offline_six_source")
    state.tool_receipts = [{
        "id": "tr_six", "tool_name": "synthesize_time_series",
        "result_sha256": "sha256:host-result", "result_preview": "aligned six sources",
        "publication_facts": facts,
        "data_identities": {name: workspace.get_data_identity(name) for name in [*names, "combined"]},
    }]
    return state, workspace, names


def _project(state, workspace=None, receipt_ids=None):
    return build_publication_packet(
        state, user_input="保留全部六个来源的两日金额、变化和记录数",
        substantive_tools=set(), receipt_ids=receipt_ids,
        offline_trust_projection=True, offline_workspace=workspace,
    )


def test_six_source_two_date_values_are_host_recomputed_from_matching_derived_version():
    state, workspace, names = _six_source_fixture()
    packet = _project(state, workspace, ["tr_six"])
    tables = packet["offline_trust_projection"]["aligned_tables"]
    assert len(tables) == 1
    table = tables[0]
    assert table["receipt_id"] == "tr_six"
    assert table["dates"] == ["2026-09-01", "2026-09-02"]
    assert len(table["rows"]) == 6
    assert [(row["dataset"], row["period_a"], row["period_b"], row["absolute_change"], row["relative_change_percent"], row["source_rows"])
            for row in table["rows"]] == [
                (name, str(index * 10), str(index * 11), str(index), "10", 2)
                for index, name in enumerate(names, 1)
            ]
    preview = render_trusted_core_preview(packet, None)
    assert "source_1" in preview["text"] and "source_6" in preview["text"]
    assert "10→11" in preview["text"] and "60→66" in preview["text"]
    assert "210→231" not in preview["text"]  # 未确认跨来源量纲，不能自造总额。
    assert preview["accepted_claim_ids"] == []


def test_missing_or_stale_workspace_cannot_authorize_six_source_values():
    state, workspace, _names = _six_source_fixture()
    assert _project(state, None, ["tr_six"])["offline_trust_projection"].get("aligned_tables", []) == []
    assert _project(state, workspace, ["other"])["offline_trust_projection"].get("aligned_tables") == []
    assert _project(state, workspace)["offline_trust_projection"].get("aligned_tables") == []
    workspace.add("source_2", pd.DataFrame({"date": pd.to_datetime(["2026-09-01", "2026-09-02"]),
                                             "amount": [200, 220]}))
    stale = _project(state, workspace, ["tr_six"])
    assert stale["offline_trust_projection"].get("aligned_tables") == []


def test_derived_version_or_date_shape_mismatch_cannot_authorize_table():
    state, workspace, _names = _six_source_fixture()
    original = workspace.get("combined")
    workspace.add("combined", original.assign(source_1=[99, 99]))
    assert _project(state, workspace, ["tr_six"])["offline_trust_projection"].get("aligned_tables") == []


def test_receipt_identity_forgery_or_zero_baseline_does_not_invent_change_rate():
    state, workspace, _names = _six_source_fixture(zero_first_source=True)
    packet = _project(state, workspace, ["tr_six"])
    first = packet["offline_trust_projection"]["aligned_tables"][0]["rows"][0]
    assert first["period_a"] == "0" and first["period_b"] == "10"
    assert first["relative_change_percent"] is None
    assert "首日为零，变化比例不适用" in render_trusted_core_preview(packet, None)["text"]
    facts = state.tool_receipts[0]["publication_facts"]
    next(item for item in facts if item["path"] == "source_identities.source_1.version_id")["value"] = "dv_forged"
    assert _project(state, workspace, ["tr_six"])["offline_trust_projection"]["aligned_tables"] == []
