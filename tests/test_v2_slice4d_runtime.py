import json

import numpy as np
import pandas as pd
import data_agent.v2.slice4d as slice4d_module

from data_agent.v2.models import FindingKind, OutcomeStatus
from data_agent.v2.recommendation import ActionRisk, RecommendationIntent
from data_agent.v2.slice4d import Slice4DMultiFindingRuntime
from data_agent.v2.store import V2FactStore
from data_agent.v2.time_series import TimeAggregation, TimeFrequency


def _frame(groups=2):
    dates = pd.date_range("2026-01-01", periods=70, freq="D")
    index = np.arange(70, dtype=float)
    if groups == 2:
        channel = np.where(index % 2 == 0, "A", "B")
    else:
        channel = np.asarray(["A", "B", "C", "A", "B"] * 14)
    return pd.DataFrame(
        {
            "date": dates,
            "unit_id": [f"u{i}" for i in range(70)],
            "channel": channel,
            "sales": 100 + 1.2 * index + np.where(channel == "B", 12, 0),
        }
    )


def _run(
    tmp_path,
    frame,
    *,
    intent=RecommendationIntent.NONE,
    frequency=TimeFrequency.DAILY,
    aggregation=TimeAggregation.MEAN,
):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    frame.to_csv(inbox / "combined.csv", index=False)
    events = list(
        Slice4DMultiFindingRuntime(tmp_path / "sessions", inbox).stream(
            session_id="session_multi",
            turn_id="turn_multi",
            filename="combined.csv",
            time_field="date",
            metric="sales",
            frequency=frequency,
            aggregation=aggregation,
            group="channel",
            analysis_unit="unit_id",
            question="销售如何变化，不同渠道是否存在差异？",
            recommendation_intent=intent,
            action_risk=ActionRisk.LOW,
            reversible=True,
        )
    )
    store = V2FactStore(tmp_path / "sessions", "session_multi")
    return events, store, store.read_turn_blocks("turn_multi")


def test_two_supported_findings_publish_pyramid_with_adjacent_charts(tmp_path):
    events, store, turn = _run(tmp_path, _frame(), intent=RecommendationIntent.ACT)
    findings = store.read_findings()
    blocks = turn["blocks"]
    rendered = json.dumps(turn, ensure_ascii=False)

    assert any(item.finding_kind is FindingKind.TIME_TREND for item in findings)
    assert any(item.finding_kind is FindingKind.GROUP_COMPARISON for item in findings)
    assert len(store.read_commitments()) == 2
    assert events[-1].event == "turn_completed"
    assert [item["block_type"] for item in blocks[:3]] == [
        "executive_answer", "key_finding", "comparison"
    ]
    assert len(blocks[1]["chart_refs"]) == 1
    assert len(blocks[2]["chart_refs"]) == 1
    assert blocks[1]["chart_refs"] != blocks[2]["chart_refs"]
    assert len(turn["artifacts"]) == 2
    assert "不证明渠道导致时间趋势" in rendered
    assert "Welch" in rendered and "HAC" in rendered
    assert any(item["block_type"] == "next_investigation" for item in blocks)


def test_multi_finding_answer_reports_data_scope_sample_and_missingness(tmp_path):
    _, _, turn = _run(tmp_path, _frame())

    method = next(
        item for item in turn["blocks"] if item["block_type"] == "method"
    )

    assert "2026-01-01 至 2026-03-11" in method["narrative"]
    assert "70 个已观测日周期" in method["narrative"]
    assert "缺失周期 0" in method["narrative"]
    assert "70 个有效 unit_id" in method["narrative"]
    assert "完整记录 70，剔除 0" in method["narrative"]
    assert "适用总体限于当前上传数据" in method["narrative"]


def test_multi_finding_rejects_partial_boundary_weeks_and_reports_true_scope(
    tmp_path,
):
    frame = _frame().iloc[:42].copy()
    _, store, turn = _run(
        tmp_path,
        frame,
        frequency=TimeFrequency.WEEKLY,
        aggregation=TimeAggregation.SUM,
    )
    findings = store.read_findings()
    time_finding = next(
        item for item in findings if item.method_capability == "analysis.time_trend"
    )
    trend = next(
        item for item in turn["blocks"] if item["block_type"] == "key_finding"
    )
    method = next(
        item for item in turn["blocks"] if item["block_type"] == "method"
    )

    assert time_finding.finding_kind is FindingKind.LIMITATION
    assert time_finding.uncertainty["reason_code"] == "incomplete_boundary_periods"
    assert "不完整边界周期" in trend["narrative"]
    assert "2026-01-01 至 2026-02-11" in method["narrative"]
    assert "不完整边界周期 2" in method["narrative"]
    assert "HAC" not in trend["narrative"]


def test_multi_group_degrades_to_descriptive_ranking_alongside_trend(tmp_path):
    events, store, turn = _run(tmp_path, _frame(groups=3))
    projection_event = next(item for item in events if item.event == "outcome_snapshot")
    statuses = {
        value["status"] for value in projection_event.data["outcomes"].values()
    }
    rendered = json.dumps(turn, ensure_ascii=False)

    # Both commitments are now satisfied: the trend inferentially, the
    # multi-group part as a descriptive ranking instead of a dead end.
    assert OutcomeStatus.SUPPORTED.value in statuses
    assert OutcomeStatus.LIMITED.value not in statuses
    assert len(turn["artifacts"]) == 1
    assert "历史趋势" in rendered
    assert "描述性排序" in rendered
    assert events[-1].event == "turn_completed"


def test_user_without_recommendation_gets_no_advice_block(tmp_path):
    _, _, turn = _run(tmp_path, _frame())

    assert not any(
        item["block_type"] in {"recommendation", "next_investigation"}
        for item in turn["blocks"]
    )


def test_group_chart_failure_keeps_trend_chart_and_both_findings(tmp_path, monkeypatch):
    def fail_group_chart(*args, **kwargs):
        raise RuntimeError("forced group chart failure")

    monkeypatch.setattr(slice4d_module, "build_group_distribution_chart", fail_group_chart)
    events, store, turn = _run(tmp_path, _frame())
    kinds = {item.finding_kind for item in store.read_findings()}

    assert FindingKind.TIME_TREND in kinds
    assert FindingKind.GROUP_COMPARISON in kinds
    assert len(turn["artifacts"]) == 1
    assert turn["blocks"][1]["chart_refs"]
    assert turn["blocks"][2]["chart_refs"] == []
    assert any(
        item.event == "artifact_failed" and item.data["analysis"] == "group_comparison"
        for item in events
    )
    assert events[-1].event == "turn_completed"
