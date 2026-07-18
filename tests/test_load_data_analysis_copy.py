import pandas as pd
from pandas.testing import assert_frame_equal

from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.context import AgentContext, use_agent_context
from data_agent.session.workspace import Workspace
from data_agent.tools.data_io import load_data


def test_load_data_keeps_raw_and_analyzes_prepared_copy(tmp_path):
    source = tmp_path / "rates.csv"
    pd.DataFrame({"rate": ["10%", "20%"], "label": ["A", "B"]}).to_csv(
        source, index=False
    )
    store = Workspace()
    state = AnalysisSessionState(session_id="copy-load")
    ctx = AgentContext(
        session_id="copy-load", workspace=store, analysis_state=state
    )

    with use_agent_context(ctx):
        result = load_data(str(source), name="rates")
        active = ctx.workspace.get("rates")
        info = ctx.workspace.get_active_version_info("rates")
        raw = ctx.workspace.get_raw_snapshot(info["raw_dataset_id"])

    assert "[analysis_copy]" in result
    assert raw["rate"].tolist() == ["10%", "20%"]
    assert active["rate"].tolist() == [0.1, 0.2]
    assert_frame_equal(
        raw,
        pd.DataFrame({"rate": ["10%", "20%"], "label": ["A", "B"]}),
    )
    assert info["role"] == "analysis_copy"


def test_load_data_records_copy_lineage_without_exposing_raw_as_dataset(tmp_path):
    source = tmp_path / "amounts.csv"
    pd.DataFrame({"amount": ["10K", "20K", "30K"]}).to_csv(source, index=False)
    store = Workspace()
    state = AnalysisSessionState(session_id="copy-proposal")
    ctx = AgentContext(
        session_id="copy-proposal", workspace=store, analysis_state=state
    )

    with use_agent_context(ctx):
        result = load_data(str(source), name="amounts")
        active = ctx.workspace.get("amounts")
        metadata = ctx.workspace.get_metadata("amounts")
        listed = ctx.workspace.list_datasets()

    assert set(listed) == {"amounts"}
    assert active["amount"].tolist() == ["10K", "20K", "30K"]
    assert metadata["_raw_dataset_id"].startswith("raw_amounts_")
    assert metadata["_active_dataset_id"] == listed["amounts"]["dataset_id"]
    assert metadata["_transformation_record"]["derived_dataset_id"] == listed["amounts"]["dataset_id"]
    assert "proposals=1" in result
