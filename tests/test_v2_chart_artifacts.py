import hashlib

import pandas as pd
import pytest

from data_agent.v2.chart import build_trend_chart, decide_chart
from data_agent.v2.models import (
    AnswerBlockDraft,
    AnswerBlockType,
    ChartArtifact,
    ClaimClass,
    Finding,
    FindingKind,
)
from data_agent.v2.store import FactConflictError, V2FactStore


def _fingerprint(html: str) -> str:
    return f"sha256:{hashlib.sha256(html.encode('utf-8')).hexdigest()}"


def _artifact(html: str = "<html>chart</html>") -> ChartArtifact:
    return ChartArtifact(
        chart_id="chart_sales_trend",
        title="销售额趋势",
        chart_type="line",
        dataset_version_ids=("dv_sales",),
        finding_refs=("f_trend",),
        x_field="date",
        y_fields=("sales",),
        purpose="evidence",
        relative_path="charts/chart_sales_trend.html",
        content_fingerprint=_fingerprint(html),
    )


def _finding() -> Finding:
    return Finding(
        finding_id="f_trend",
        commitment_id="c_trend",
        finding_kind=FindingKind.ESTIMATE,
        dataset_version_ids=("dv_sales",),
        metric_identity="sales.ordered_change",
        method_capability="analysis.describe_trend",
        maximum_claim_class=ClaimClass.DESCRIPTIVE,
        computation_ref="computation:trend",
        estimate=100.0,
    )


def test_chart_decision_requires_both_question_intent_and_valid_ordered_axis():
    frame = pd.DataFrame(
        {"date": ["2026-01-01", "2026-01-02", "2026-01-03"], "sales": [100, 150, 200]}
    )

    mean_decision = decide_chart(frame, metric="sales", question="平均销售额是多少？")
    trend_decision = decide_chart(frame, metric="sales", question="销售额趋势如何？")

    assert mean_decision.warranted is False
    assert mean_decision.reason_code == "no_visual_pattern_requested"
    assert trend_decision.warranted is True
    assert trend_decision.chart_type == "line"
    assert trend_decision.x_field == "date"


def test_trend_chart_is_bound_to_dataset_and_finding_and_uses_local_plotly():
    frame = pd.DataFrame(
        {"date": ["2026-01-01", "2026-01-02", "2026-01-03"], "sales": [100, 150, 200]}
    )
    decision = decide_chart(frame, metric="sales", question="销售额趋势如何？")

    artifact, html = build_trend_chart(
        frame,
        decision=decision,
        metric="sales",
        dataset_version_id="dv_sales",
        finding_refs=("f_trend",),
        title="销售额趋势",
    )

    assert artifact.finding_refs == ("f_trend",)
    assert artifact.dataset_version_ids == ("dv_sales",)
    assert artifact.content_fingerprint == _fingerprint(html)
    assert "/static/js/plotly-3.5.0.min.js" in html
    assert "cdn.plot.ly" not in html


def test_chart_artifact_and_turn_relation_round_trip(tmp_path):
    html = "<html>chart</html>"
    store = V2FactStore(tmp_path, "session_1")
    store.append_finding(_finding())
    artifact = _artifact(html)

    assert store.write_chart_artifact(artifact, html) is True
    assert store.write_chart_artifact(artifact, html) is False
    with pytest.raises(FactConflictError, match="chart_sales_trend"):
        store.write_chart_artifact(artifact, "<html>different</html>")

    block = AnswerBlockDraft(
        block_id="b1",
        block_type=AnswerBlockType.KEY_FINDING,
        support_refs=("f_trend",),
        headline="趋势结论",
        narrative="销售额随时间上升。",
        claim_class=ClaimClass.DESCRIPTIVE,
        chart_refs=(artifact.chart_id,),
    )
    store.write_turn_blocks(
        "turn_1",
        [block],
        status="finalized",
        artifact_ids=(artifact.chart_id,),
    )

    turn = store.read_turn_blocks("turn_1")

    assert turn["artifact_ids"] == [artifact.chart_id]
    assert turn["artifacts"][0]["chart_id"] == artifact.chart_id
    assert store.read_chart_html(artifact.chart_id) == html


def test_evidence_chart_requires_persisted_finding(tmp_path):
    store = V2FactStore(tmp_path, "session_1")

    with pytest.raises(ValueError, match="finding_refs"):
        store.write_chart_artifact(_artifact(), "<html>chart</html>")


def test_turn_rejects_chart_reference_not_in_persisted_artifact_set(tmp_path):
    store = V2FactStore(tmp_path, "session_1")
    block = AnswerBlockDraft(
        block_id="b1",
        block_type=AnswerBlockType.KEY_FINDING,
        support_refs=("f_trend",),
        headline="趋势结论",
        narrative="销售额随时间上升。",
        chart_refs=("chart_missing",),
    )

    with pytest.raises(ValueError, match="chart_refs"):
        store.write_turn_blocks("turn_1", [block], status="finalized")
