from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass

import pandas as pd
import plotly.graph_objects as go

from data_agent.tools.chart_contract import infer_semantic_role, validate_chart_request
from data_agent.v2.models import ChartArtifact


_TREND_TERMS = (
    "趋势",
    "走势",
    "变化",
    "随时间",
    "时间序列",
    "trend",
    "over time",
)


@dataclass(frozen=True, slots=True)
class ChartDecision:
    warranted: bool
    reason_code: str
    chart_type: str = ""
    x_field: str = ""


def _time_candidates(frame: pd.DataFrame, metric: str) -> list[str]:
    candidates: list[str] = []
    for column in frame.columns:
        name = str(column)
        if name == metric:
            continue
        series = frame[column]
        if infer_semantic_role(name, series) != "time":
            continue
        parsed = pd.to_datetime(series, errors="coerce", format="mixed")
        if parsed.notna().sum() >= 2 and parsed.nunique(dropna=True) >= 2:
            candidates.append(name)
    return candidates


def decide_chart(frame: pd.DataFrame, *, metric: str, question: str) -> ChartDecision:
    normalized_question = str(question or "").casefold()
    if not any(term in normalized_question for term in _TREND_TERMS):
        return ChartDecision(False, "no_visual_pattern_requested")
    if metric not in frame.columns:
        return ChartDecision(False, "metric_not_found")
    numeric = pd.to_numeric(frame[metric], errors="coerce")
    if numeric.notna().sum() < 2:
        return ChartDecision(False, "insufficient_numeric_points")
    candidates = _time_candidates(frame, metric)
    if len(candidates) != 1:
        return ChartDecision(False, "ordered_axis_not_unique")
    paired = pd.DataFrame(
        {
            "time": pd.to_datetime(frame[candidates[0]], errors="coerce", format="mixed"),
            "value": numeric,
        }
    ).dropna()
    if len(paired) < 2 or paired["time"].nunique() < 2:
        return ChartDecision(False, "insufficient_complete_pairs")
    return ChartDecision(True, "trend_with_ordered_axis", "line", candidates[0])


def build_trend_chart(
    frame: pd.DataFrame,
    *,
    decision: ChartDecision,
    metric: str,
    dataset_version_id: str,
    finding_refs: tuple[str, ...],
    title: str,
) -> tuple[ChartArtifact, str]:
    if not decision.warranted or decision.chart_type != "line":
        raise ValueError("a warranted line-chart decision is required")
    contract = validate_chart_request(
        frame,
        "line",
        decision.x_field,
        [metric],
    )
    if not contract.valid:
        raise ValueError(f"chart contract rejected request: {contract.error_code}")
    plot_frame = contract.dataframe[[decision.x_field, metric]].copy()
    plot_frame[decision.x_field] = pd.to_datetime(
        plot_frame[decision.x_field], errors="coerce", format="mixed"
    )
    plot_frame[metric] = pd.to_numeric(plot_frame[metric], errors="coerce")
    plot_frame = plot_frame.dropna().sort_values(decision.x_field)
    if len(plot_frame) < 2:
        raise ValueError("trend chart requires at least two complete points")

    figure = go.Figure(
        go.Scatter(
            x=plot_frame[decision.x_field],
            y=plot_frame[metric],
            mode="lines+markers",
            name=metric,
            hovertemplate="%{x|%Y-%m-%d}<br>%{y}<extra></extra>",
        )
    )
    figure.update_layout(
        template="plotly_white",
        xaxis_title=decision.x_field,
        yaxis_title=metric,
        margin={"l": 58, "r": 24, "t": 58, "b": 52},
        autosize=True,
    )
    html = figure.to_html(
        full_html=True,
        include_plotlyjs="/static/js/plotly-3.5.0.min.js",
        config={"responsive": True, "displaylogo": False},
    )
    chart_id = f"chart_{uuid.uuid4().hex}"
    fingerprint = f"sha256:{hashlib.sha256(html.encode('utf-8')).hexdigest()}"
    artifact = ChartArtifact(
        chart_id=chart_id,
        title=title,
        chart_type="line",
        dataset_version_ids=(dataset_version_id,),
        finding_refs=finding_refs,
        x_field=decision.x_field,
        y_fields=(metric,),
        purpose="evidence",
        relative_path=f"charts/{chart_id}.html",
        content_fingerprint=fingerprint,
    )
    return artifact, html
