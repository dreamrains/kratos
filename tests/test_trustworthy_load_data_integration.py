import json
from pathlib import Path

import pandas as pd

from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.context import AgentContext, use_agent_context
from data_agent.config import AgentConfig
from data_agent.session.workspace import Workspace


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
        pd.DataFrame({
            "date": pd.date_range("2026-01-01", periods=8),
            "channel": ["app", "web"] * 4,
            "gmv": [100, 120, 90, 150, 160, 170, 130, 180],
        }).to_csv(source, index=False)

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

        ref_with_artifact = state.dataset_contracts[0]
        artifact_path = Path(ref_with_artifact["artifact_path"])
        assert artifact_path.exists()
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        assert artifact["id"] == ref_with_artifact["id"]
        assert artifact["dataset"] == "orders"

        saved_state = tmp_path / "sessions" / "trust_load" / "analysis_state.json"
        assert saved_state.exists()
    finally:
        config._config = old_cfg
