import json
from pathlib import Path

import pandas as pd

from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.context import AgentContext, use_agent_context
from data_agent.config import AgentConfig
from data_agent.session.workspace import Workspace


def _write_orders_csv(path: Path) -> None:
    pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=8),
        "channel": ["app", "web"] * 4,
        "gmv": [100, 120, 90, 150, 160, 170, 130, 180],
    }).to_csv(path, index=False)


def _assert_under(path: Path, base: Path) -> None:
    assert path.resolve().is_relative_to(base.resolve())


def test_load_data_creates_trust_workflow_records(tmp_path):
    from data_agent import config
    from data_agent.tools.data_io import load_data

    old_cfg = config._config
    config._config = AgentConfig(
        PROJECT_DIR=tmp_path / "project",
        SESSIONS_DIR=tmp_path / "sessions",
    )
    try:
        source = tmp_path / "orders.csv"
        _write_orders_csv(source)

        state = AnalysisSessionState(session_id="trust_load")
        ctx = AgentContext(
            session_id="trust_load",
            workspace=Workspace(),
            analysis_state=state,
        )

        with use_agent_context(ctx):
            result = load_data(str(source), name="orders")

        assert "[trust_workflow]" in result
        assert "contract=duc_orders_" in result
        route_count = len(state.route_proposals)
        assert f"routes={route_count}" in result
        assert len(state.cleaning_logs) == 1
        assert len(state.preview_digests) == 1
        assert len(state.dataset_contracts) == 1
        assert route_count >= 1

        tool_outputs_dir = tmp_path / "sessions" / "trust_load" / "tool_outputs"
        refs_by_kind = {
            "cleaning_log": state.cleaning_logs,
            "preview_digest": state.preview_digests,
            "dataset_contract": state.dataset_contracts,
            "route_proposal": state.route_proposals,
        }
        for refs in refs_by_kind.values():
            for ref in refs:
                artifact_path = Path(ref["artifact_path"])
                assert artifact_path.exists()
                _assert_under(artifact_path, tool_outputs_dir)
                artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
                assert artifact["id"] == ref["id"]
                assert artifact["dataset"] == "orders"

        saved_state = tmp_path / "sessions" / "trust_load" / "analysis_state.json"
        assert saved_state.exists()
        saved = json.loads(saved_state.read_text(encoding="utf-8"))
        assert len(saved["cleaning_logs"]) == 1
        assert len(saved["preview_digests"]) == 1
        assert len(saved["dataset_contracts"]) == 1
        assert len(saved["route_proposals"]) == route_count
    finally:
        config._config = old_cfg


def test_load_data_trust_artifacts_do_not_escape_sessions_dir(tmp_path):
    from data_agent import config
    from data_agent.tools.data_io import load_data

    old_cfg = config._config
    sessions_dir = tmp_path / "sessions"
    config._config = AgentConfig(
        PROJECT_DIR=tmp_path / "project",
        SESSIONS_DIR=sessions_dir,
    )
    try:
        source = tmp_path / "orders.csv"
        _write_orders_csv(source)

        state = AnalysisSessionState(session_id="..\\escape")
        ctx = AgentContext(
            session_id="..\\escape",
            workspace=Workspace(),
            analysis_state=state,
        )

        with use_agent_context(ctx):
            result = load_data(str(source), name="orders")

        assert "[trust_workflow]" in result
        all_refs = (
            state.cleaning_logs
            + state.preview_digests
            + state.dataset_contracts
            + state.route_proposals
        )
        assert all_refs
        for ref in all_refs:
            artifact_path = Path(ref["artifact_path"])
            assert artifact_path.exists()
            _assert_under(artifact_path, sessions_dir)
            assert artifact_path.parent.name == "tool_outputs"
        assert not (tmp_path / "escape" / "tool_outputs").exists()
    finally:
        config._config = old_cfg


def test_second_dataset_becomes_active_without_deleting_first_dataset(tmp_path):
    state = AnalysisSessionState(session_id="multi_upload")

    first = state.add_dataset_contract_ref({"id": "contract_sales", "dataset": "sales"})
    second = state.add_dataset_contract_ref({"id": "contract_orders", "dataset": "orders"})

    assert first["dataset"] == "sales"
    assert second["dataset"] == "orders"
    assert [item["dataset"] for item in state.dataset_contracts] == ["sales", "orders"]
    assert state.active_scope["active_dataset"] == "orders"
    assert state.active_scope["active_mode"] == "data_loaded"
