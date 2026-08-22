"""Runtime-level real-data replay: retention curve fitting through the slice."""

import json
import shutil
from pathlib import Path

import pandas as pd
import pytest

from data_agent.v2.models import FindingKind
from data_agent.v2.slice_curve import SliceCurveFittingRuntime
from data_agent.v2.store import V2FactStore


TEST_DOC_DIR = Path("reference/test_doc")
SOURCE = TEST_DOC_DIR / "游戏B留存.xlsx"


@pytest.fixture()
def replay_env(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    shutil.copy(SOURCE, inbox / SOURCE.name)
    return inbox, tmp_path / "sessions"


@pytest.mark.skipif(not SOURCE.exists(), reason="游戏B留存.xlsx not found")
def test_retention_fit_replay_publishes_formula_method_and_chart(replay_env):
    inbox, sessions_root = replay_env
    frame = pd.read_excel(SOURCE)
    columns = [column for column in frame.columns if column.endswith("天后")]

    events = list(
        SliceCurveFittingRuntime(sessions_root, inbox).stream(
            session_id="session_curve",
            turn_id="turn_curve",
            filename=SOURCE.name,
            question="这是一个游戏的新用户留存率数据，请根据数据为我拟合留存率的公式",
            series_columns=columns,
        )
    )
    store = V2FactStore(sessions_root, "session_curve")
    turn = store.read_turn_blocks("turn_curve")
    rendered = json.dumps(turn, ensure_ascii=False)

    assert events[-1].event == "turn_completed"
    assert turn["status"] == "finalized"
    assert turn["artifacts"], "the fit overlay chart must be produced"
    finding = store.read_findings()[0]
    assert finding.finding_kind is FindingKind.ESTIMATE
    assert finding.maximum_claim_class.value == "descriptive"
    # 5/18-session ground truth rendered in the answer
    assert "幂律" in rendered
    assert "y = a·x^b" in rendered
    assert "0.98" in rendered  # R² ≈ 0.9824
    assert "不支持外推" in rendered
    assert "截断" in rendered  # zero-exclusion disclosure
    fit = finding.uncertainty["fits"][0]
    assert fit["family"] == "power"
    assert fit["params"]["a"] == pytest.approx(0.1880, abs=0.002)
    assert fit["params"]["b"] == pytest.approx(-0.7167, abs=0.003)
