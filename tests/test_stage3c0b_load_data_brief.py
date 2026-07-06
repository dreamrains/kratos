import json
from pathlib import Path

import pandas as pd

from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.context import AgentContext, use_agent_context
from data_agent.config import AgentConfig
from data_agent.session.workspace import Workspace


def _write_orders_csv(path: Path) -> None:
    pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=4),
        "order_id": ["o1", "o2", "o3", "o4"],
        "customer_id": ["u1", "u2", "u1", "u3"],
        "gmv": [100, 120, 90, 150],
    }).to_csv(path, index=False)


def test_load_data_records_data_understanding_bundle_ref(tmp_path):
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

        state = AnalysisSessionState(session_id="brief_load")
        ctx = AgentContext(
            session_id="brief_load",
            workspace=Workspace(),
            analysis_state=state,
        )

        with use_agent_context(ctx):
            result = load_data(str(source), name="orders")

        assert "[trust_workflow]" in result
        assert state.data_understanding_bundles
        bundle_ref = state.data_understanding_bundles[-1]
        assert bundle_ref["contract_version"] == "data_understanding.v1"
        assert bundle_ref["dataset"] == "orders"
        assert bundle_ref["data_fingerprint"].startswith("sha256:")
        assert state.active_scope["related_ref_ids"]["data_understanding_bundles"]
        assert "contract_version" not in json.dumps(state.dataset_bundles, ensure_ascii=False)
    finally:
        config._config = old_cfg


def test_user_data_brief_is_compact_and_hides_internal_fields():
    from data_agent.agent.data_understanding import (
        build_data_understanding_bundle,
        build_user_data_brief,
    )

    bundle = build_data_understanding_bundle(
        datasets=[{
            "dataset": "orders",
            "dataset_contract_id": "duc_orders",
            "artifact_path": "sessions/s1/tool_outputs/private.json",
            "sample_rows": [{"order_id": "o1", "gmv": 100}],
            "rows": 4,
            "columns": [
                {"name": "date", "type": "datetime"},
                {"name": "order_id", "type": "string"},
                {"name": "customer_id", "type": "string"},
                {"name": "gmv", "type": "number"},
            ],
            "grain": "one row per order",
        }],
        quality_findings=[{"dataset": "orders", "finding": "complete order ids"}],
        relationship_candidates=[],
        supported_questions=["What is GMV by day?"],
        unsupported_questions=["What is acquisition cost?"],
        analysis_constraints=["No ad spend dataset loaded."],
    )

    brief = build_user_data_brief(bundle)

    assert brief["bundle_id"] == bundle["id"]
    assert brief["fingerprint"] == bundle["data_fingerprint"]
    assert brief["datasets"][0]["dataset"] == "orders"
    rendered = json.dumps(brief, ensure_ascii=False)
    assert "artifact_path" not in rendered
    assert "sample_rows" not in rendered
    assert "sessions/s1/tool_outputs/private.json" not in rendered


def test_trust_view_exposes_latest_user_data_brief():
    from data_agent.agent.data_understanding import build_data_understanding_bundle
    from data_agent.agent.trust_view import build_trust_view

    state = AnalysisSessionState(session_id="brief_view", data_state="data_loaded")
    bundle = build_data_understanding_bundle(
        datasets=[{
            "dataset": "orders",
            "dataset_contract_id": "duc_orders",
            "rows": 4,
            "columns": [{"name": "gmv", "type": "number"}],
            "grain": "one row per order",
        }],
        quality_findings=[],
        relationship_candidates=[],
        supported_questions=["What is GMV?"],
        unsupported_questions=[],
        analysis_constraints=[],
    )
    state.add_data_understanding_bundle_ref(bundle)

    view = build_trust_view(state)

    brief = view["workbench"]["user_data_brief"]
    assert brief["bundle_id"] == bundle["id"]
    assert brief["datasets"][0]["dataset"] == "orders"
