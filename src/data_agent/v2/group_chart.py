from __future__ import annotations

import hashlib
import uuid

import pandas as pd
import plotly.graph_objects as go

from data_agent.v2.models import ChartArtifact


def build_group_distribution_chart(
    frame: pd.DataFrame,
    *,
    metric: str,
    group: str,
    group_order: tuple[str, str],
    dataset_version_id: str,
    finding_refs: tuple[str, ...],
    title: str,
) -> tuple[ChartArtifact, str]:
    figure = go.Figure()
    colors = ("#5778d7", "#d9843b")
    for index, group_value in enumerate(group_order):
        values = pd.to_numeric(
            frame.loc[frame[group].astype(str) == group_value, metric], errors="coerce"
        ).dropna()
        figure.add_trace(
            go.Box(
                y=values,
                name=group_value,
                boxmean=True,
                marker_color=colors[index % len(colors)],
                boxpoints="outliers",
                hovertemplate=f"{group}={group_value}<br>{metric}=%{{y:.3f}}<extra></extra>",
            )
        )
    figure.update_layout(
        template="plotly_white",
        xaxis_title=group,
        yaxis_title=metric,
        margin={"l": 70, "r": 28, "t": 28, "b": 58},
        showlegend=False,
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
        chart_type="group_boxplot",
        dataset_version_ids=(dataset_version_id,),
        finding_refs=finding_refs,
        x_field=group,
        y_fields=(metric,),
        purpose="evidence",
        relative_path=f"charts/{chart_id}.html",
        content_fingerprint=f"sha256:{hashlib.sha256(html.encode('utf-8')).hexdigest()}",
    )
    return artifact, html
