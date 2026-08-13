from __future__ import annotations

import hashlib
import uuid

import pandas as pd
import plotly.graph_objects as go

from data_agent.v2.forecasting import ForecastResult
from data_agent.v2.models import ChartArtifact


def build_forecast_chart(
    result: ForecastResult,
    *,
    dataset_version_id: str,
    finding_refs: tuple[str, ...],
    title: str,
) -> tuple[ChartArtifact, str]:
    if not result.forecast_times:
        raise ValueError("forecast chart requires publishable future periods")
    history_times = pd.to_datetime(list(result.historical_times))
    future_times = pd.to_datetime(list(result.forecast_times))
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=history_times,
            y=list(result.historical_values),
            mode="lines+markers",
            name="历史观测",
            line={"color": "#3974b8", "width": 2},
            hovertemplate="%{x|%Y-%m-%d}<br>观测=%{y:.3f}<extra></extra>",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=future_times,
            y=list(result.interval_high),
            mode="lines",
            line={"width": 0},
            hoverinfo="skip",
            showlegend=False,
        )
    )
    figure.add_trace(
        go.Scatter(
            x=future_times,
            y=list(result.interval_low),
            mode="lines",
            line={"width": 0},
            fill="tonexty",
            fillcolor="rgba(213,107,63,.18)",
            name="经验预测区间",
            hovertemplate="%{x|%Y-%m-%d}<br>下界=%{y:.3f}<extra></extra>",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=[history_times[-1], *future_times],
            y=[result.historical_values[-1], *result.forecast_values],
            mode="lines+markers",
            name="基线预测",
            line={"color": "#d56b3f", "dash": "dash", "width": 2},
            hovertemplate="%{x|%Y-%m-%d}<br>预测=%{y:.3f}<extra></extra>",
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
        chart_type="forecast_line_interval",
        dataset_version_ids=(dataset_version_id,),
        finding_refs=finding_refs,
        x_field=result.time_field,
        y_fields=(result.metric,),
        purpose="evidence",
        relative_path=f"charts/{chart_id}.html",
        content_fingerprint=f"sha256:{hashlib.sha256(html.encode('utf-8')).hexdigest()}",
    )
    return artifact, html
