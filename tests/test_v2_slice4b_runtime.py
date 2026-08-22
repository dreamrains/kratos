import json

import numpy as np
import pandas as pd

from data_agent.v2.models import AnswerBlockType, FindingKind
from data_agent.v2.recommendation import ActionRisk, RecommendationIntent
from data_agent.v2.slice4b import Slice4BTimeSeriesRuntime
from data_agent.v2.store import V2FactStore
from data_agent.v2.time_series import TimeAggregation, TimeFrequency


def _frame(periods=56, trend=1.2):
    dates = pd.date_range("2026-01-01", periods=periods, freq="D")
    index = np.arange(periods, dtype=float)
    return pd.DataFrame(
        {
            "date": dates.strftime("%Y-%m-%d"),
            "sales": 100 + trend * index + 5 * np.sin(2 * np.pi * index / 7),
        }
    )


def _run(tmp_path, *, intent=RecommendationIntent.NONE):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    _frame().to_csv(inbox / "trend.csv", index=False)
    events = list(
        Slice4BTimeSeriesRuntime(tmp_path / "sessions", inbox).stream(
            session_id="session_trend",
            turn_id="turn_trend",
            filename="trend.csv",
            time_field="date",
            metric="sales",
            frequency=TimeFrequency.DAILY,
            aggregation=TimeAggregation.SUM,
            question="历史销售是否有可靠趋势？",
            recommendation_intent=intent,
            action_risk=ActionRisk.LOW,
            reversible=True,
        )
    )
    store = V2FactStore(tmp_path / "sessions", "session_trend")
    return events, store, store.read_turn_blocks("turn_trend")


def test_time_series_runtime_persists_summary_trend_chart_and_no_prediction(tmp_path):
    events, store, turn = _run(tmp_path)
    findings = store.read_findings()

    assert any(item.finding_kind is FindingKind.ESTIMATE for item in findings)
    assert any(item.finding_kind is FindingKind.TIME_TREND for item in findings)
    assert events[-1].event == "turn_completed"
    assert "artifact_created" in [item.event for item in events]
    assert turn["blocks"][0]["chart_refs"] == [turn["artifacts"][0]["chart_id"]]
    assert all(item["block_type"] != "recommendation" for item in turn["blocks"])
    rendered = json.dumps(turn, ensure_ascii=False)
    assert "每个日周期" in rendered
    assert "HAC" in rendered
    assert "不是未来预测" in rendered


def test_requested_time_action_becomes_driver_validation_not_forecast(tmp_path):
    _, _, turn = _run(tmp_path, intent=RecommendationIntent.ACT)

    recommendation = next(
        item for item in turn["blocks"] if item["block_type"] == AnswerBlockType.NEXT_INVESTIGATION.value
    )
    assert "季节" in recommendation["narrative"]
    assert "外部事件" in recommendation["narrative"]
    assert turn["request_context"]["recommendation_mode"] == "investigative_next_step"


def test_missing_interval_is_publishable_limit_without_chart(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    frame = _frame(periods=20).drop(index=7)
    frame.to_csv(inbox / "gap.csv", index=False)
    events = list(
        Slice4BTimeSeriesRuntime(tmp_path / "sessions", inbox).stream(
            session_id="session_gap",
            turn_id="turn_gap",
            filename="gap.csv",
            time_field="date",
            metric="sales",
            frequency=TimeFrequency.DAILY,
            aggregation=TimeAggregation.SUM,
            question="历史销售是否有趋势？",
            recommendation_intent=RecommendationIntent.NONE,
            action_risk=ActionRisk.LOW,
            reversible=True,
        )
    )
    store = V2FactStore(tmp_path / "sessions", "session_gap")
    turn = store.read_turn_blocks("turn_gap")

    assert any(item.finding_kind is FindingKind.LIMITATION for item in store.read_findings())
    assert events[-1].event == "turn_completed"
    assert turn["artifacts"] == []
    assert "缺失" in json.dumps(turn, ensure_ascii=False)
