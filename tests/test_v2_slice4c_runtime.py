import json

import numpy as np
import pandas as pd

from data_agent.v2.models import FindingKind
from data_agent.v2.recommendation import ActionRisk, RecommendationIntent
from data_agent.v2.slice4c import Slice4CForecastRuntime
from data_agent.v2.store import V2FactStore
from data_agent.v2.time_series import TimeAggregation, TimeFrequency


def _run(tmp_path, values, *, intent=RecommendationIntent.NONE):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    dates = pd.date_range("2026-01-01", periods=len(values), freq="D")
    pd.DataFrame({"date": dates, "sales": values}).to_csv(
        inbox / "forecast.csv", index=False
    )
    events = list(
        Slice4CForecastRuntime(tmp_path / "sessions", inbox).stream(
            session_id="session_forecast",
            turn_id="turn_forecast",
            filename="forecast.csv",
            time_field="date",
            metric="sales",
            frequency=TimeFrequency.DAILY,
            aggregation=TimeAggregation.SUM,
            horizon=7,
            question="未来七天销售基线是多少？",
            recommendation_intent=intent,
            action_risk=ActionRisk.LOW,
            reversible=True,
        )
    )
    store = V2FactStore(tmp_path / "sessions", "session_forecast")
    return events, store, store.read_turn_blocks("turn_forecast")


def test_supported_forecast_publishes_predictive_finding_chart_and_backtest(tmp_path):
    index = np.arange(70, dtype=float)
    events, store, turn = _run(tmp_path, 100 + 2 * index + np.sin(index))
    findings = store.read_findings()
    rendered = json.dumps(turn, ensure_ascii=False)

    assert any(item.finding_kind is FindingKind.FORECAST for item in findings)
    assert any(item.finding_kind is FindingKind.ESTIMATE for item in findings)
    assert events[-1].event == "turn_completed"
    assert len(turn["artifacts"]) == 1
    assert turn["blocks"][0]["chart_refs"] == [turn["artifacts"][0]["chart_id"]]
    assert "未来 7 个日周期" in rendered
    assert "时间外" in rendered
    assert "经验预测区间" in rendered
    assert "预算承诺" in rendered
    assert not any(item["block_type"] == "recommendation" for item in turn["blocks"])


def test_forecast_action_request_is_scenario_monitoring_not_operational_claim(tmp_path):
    index = np.arange(70, dtype=float)
    _, _, turn = _run(
        tmp_path, 100 + 2 * index + np.sin(index), intent=RecommendationIntent.ACT
    )
    rendered = json.dumps(turn, ensure_ascii=False)

    assert turn["request_context"]["recommendation_mode"] == "investigative_next_step"
    assert any(item["block_type"] == "next_investigation" for item in turn["blocks"])
    assert "监控" in rendered
    assert "干预" in rendered


def test_low_quality_forecast_is_publishable_limit_without_future_chart(tmp_path):
    values = np.random.default_rng(41).normal(0, 100, size=80)
    events, store, turn = _run(tmp_path, values)
    rendered = json.dumps(turn, ensure_ascii=False)

    assert any(item.finding_kind is FindingKind.LIMITATION for item in store.read_findings())
    assert events[-1].event == "turn_completed"
    assert turn["artifacts"] == []
    assert "回测质量" in rendered
    assert "未发布未来点预测" in rendered
