import json

import numpy as np
import pandas as pd

from data_agent.v2.models import AnswerBlockType, FindingKind
from data_agent.v2.recommendation import ActionRisk, RecommendationIntent
from data_agent.v2.slice4a import Slice4AGroupComparisonRuntime
from data_agent.v2.store import V2FactStore


def _frame(effect: float = 8.0, rows_per_group: int = 36) -> pd.DataFrame:
    index = np.arange(rows_per_group, dtype=float)
    baseline = 100 + np.sin(index * 1.7) * 3 + (index % 5)
    return pd.DataFrame(
        {
            "unit_id": [f"a{i}" for i in range(rows_per_group)]
            + [f"b{i}" for i in range(rows_per_group)],
            "channel": ["A"] * rows_per_group + ["B"] * rows_per_group,
            "revenue": np.concatenate([baseline, baseline + effect]),
        }
    )


def _run(tmp_path, *, effect=8.0, intent=RecommendationIntent.NONE):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    _frame(effect=effect).to_csv(inbox / "groups.csv", index=False)
    events = list(
        Slice4AGroupComparisonRuntime(tmp_path / "sessions", inbox).stream(
            session_id="session_groups",
            turn_id="turn_groups",
            filename="groups.csv",
            metric="revenue",
            group="channel",
            analysis_unit="unit_id",
            question="A 与 B 的收入是否不同？",
            recommendation_intent=intent,
            action_risk=ActionRisk.LOW,
            reversible=True,
        )
    )
    store = V2FactStore(tmp_path / "sessions", "session_groups")
    return events, store, store.read_turn_blocks("turn_groups")


def test_supported_group_comparison_persists_multi_findings_chart_and_no_forced_advice(tmp_path):
    events, store, turn = _run(tmp_path)
    findings = store.read_findings()

    assert sum(item.finding_kind is FindingKind.ESTIMATE for item in findings) == 2
    assert any(item.finding_kind is FindingKind.GROUP_COMPARISON for item in findings)
    assert events[-1].event == "turn_completed"
    assert "artifact_created" in [item.event for item in events]
    assert len(turn["artifacts"]) == 1
    assert turn["blocks"][0]["chart_refs"] == [turn["artifacts"][0]["chart_id"]]
    assert all(
        item["block_type"] != AnswerBlockType.RECOMMENDATION.value
        for item in turn["blocks"]
    )
    serialized = json.dumps(turn, ensure_ascii=False)
    assert "Welch" in serialized
    assert "Hedges g" in serialized
    assert "因果" in serialized


def test_requested_action_is_downgraded_to_investigative_next_step(tmp_path):
    _, _, turn = _run(tmp_path, intent=RecommendationIntent.ACT)

    recommendation = next(
        item
        for item in turn["blocks"]
        if item["block_type"] == AnswerBlockType.NEXT_INVESTIGATION.value
    )
    assert "验证" in recommendation["narrative"]
    assert "立即" not in recommendation["narrative"]
    assert turn["request_context"]["recommendation_mode"] == "investigative_next_step"


def test_null_group_comparison_is_complete_and_does_not_claim_no_action_needed(tmp_path):
    events, store, turn = _run(tmp_path, effect=0.0, intent=RecommendationIntent.ACT)

    assert any(
        item.finding_kind is FindingKind.NULL_RESULT for item in store.read_findings()
    )
    assert events[-1].event == "turn_completed"
    serialized = json.dumps(turn, ensure_ascii=False)
    assert "未检出可靠均值差异" in serialized
    assert "无需行动" not in serialized


def test_repeated_units_aggregate_to_unit_level_and_stay_publishable(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    frame = _frame(rows_per_group=10)
    frame.loc[1, "unit_id"] = frame.loc[0, "unit_id"]
    frame.to_csv(inbox / "repeated.csv", index=False)

    events = list(
        Slice4AGroupComparisonRuntime(tmp_path / "sessions", inbox).stream(
            session_id="session_repeated",
            turn_id="turn_repeated",
            filename="repeated.csv",
            metric="revenue",
            group="channel",
            analysis_unit="unit_id",
            question="比较收入。",
            recommendation_intent=RecommendationIntent.NONE,
            action_risk=ActionRisk.LOW,
            reversible=True,
        )
    )
    store = V2FactStore(tmp_path / "sessions", "session_repeated")
    turn = store.read_turn_blocks("turn_repeated")

    # Order-level rows are aggregated per unit instead of ending in a dead end.
    assert not any(
        item.finding_kind is FindingKind.LIMITATION for item in store.read_findings()
    )
    assert any(
        item.finding_kind in {FindingKind.GROUP_COMPARISON, FindingKind.NULL_RESULT}
        for item in store.read_findings()
    )
    assert events[-1].event == "turn_completed"
    serialized = json.dumps(turn, ensure_ascii=False)
    assert "聚合" in serialized
    assert "每单位取求和" in serialized
