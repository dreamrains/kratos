from __future__ import annotations

import hashlib
import uuid

import pandas as pd
import plotly.graph_objects as go

from data_agent.v2.models import ChartArtifact
from data_agent.v2.time_series import TimeSeriesResult


def build_time_series_chart(
    result: TimeSeriesResult,
    *,
    dataset_version_id: str,
    finding_refs: tuple[str, ...],
    title: str,
) -> tuple[ChartArtifact, str]:
    if not result.series_times:
        raise ValueError("time-series chart requires observed periods")
    times = pd.to_datetime(list(result.series_times))
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=times,
            y=list(result.series_values),
            mode="lines+markers",
            name="聚合观测",
            line={"color": "#3974b8", "width": 2},
            hovertemplate="%{x|%Y-%m-%d}<br>观测=%{y:.3f}<extra></extra>",
        )
    )
    if result.fitted_values:
        figure.add_trace(
            go.Scatter(
                x=times,
                y=list(result.fitted_values),
                mode="lines",
                name="规格内线性拟合",
                line={"color": "#d56b3f", "dash": "dash", "width": 2},
                hovertemplate="%{x|%Y-%m-%d}<br>拟合=%{y:.3f}<extra></extra>",
            )
        )
    figure.update_layout(
        template="plotly_white",
        xaxis_title=result.time_field,
        yaxis_title=result.metric,
        margin={"l": 72, "r": 28, "t": 30, "b": 58},
        legend={"orientation": "h", "y": 1.08},
        autosize=True,
    )
    html = figure.to_html(
        full_html=True,
        include_plotlyjs="/static/js/plotly-3.5.0.min.js",
        config={"responsive": True, "displaylogo": False},
    )
    chart_id = f"chart_{uuid.uuid4().hex}"
    artifact = ChartArtifact(
        chart_id=chart_id,
        title=title,
        chart_type="time_series_line",
        dataset_version_ids=(dataset_version_id,),
        finding_refs=finding_refs,
        x_field=result.time_field,
        y_fields=(result.metric,),
        purpose="evidence",
        relative_path=f"charts/{chart_id}.html",
        content_fingerprint=f"sha256:{hashlib.sha256(html.encode('utf-8')).hexdigest()}",
    )
    return artifact, html
