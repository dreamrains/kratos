from __future__ import annotations

import hashlib
import uuid

import plotly.graph_objects as go

from data_agent.v2.factor import FactorAnalysisResult
from data_agent.v2.models import ChartArtifact


def build_factor_coefficient_chart(
    result: FactorAnalysisResult,
    *,
    dataset_version_id: str,
    finding_refs: tuple[str, ...],
    title: str,
) -> tuple[ChartArtifact, str]:
    if not result.reliable_factors:
        raise ValueError("coefficient chart requires reliable factors")
    factors = list(reversed(result.reliable_factors))
    coefficients = [item.coefficient for item in factors]
    figure = go.Figure(
        go.Scatter(
            x=coefficients,
            y=[item.feature for item in factors],
            mode="markers",
            error_x={
                "type": "data",
                "symmetric": False,
                "array": [item.confidence_high - item.coefficient for item in factors],
                "arrayminus": [item.coefficient - item.confidence_low for item in factors],
            },
            hovertemplate=(
                "%{y}<br>标准化系数=%{x:.3f}<br>95% CI=[%{customdata[0]:.3f}, "
                "%{customdata[1]:.3f}]<extra></extra>"
            ),
            customdata=[
                [item.confidence_low, item.confidence_high] for item in factors
            ],
        )
    )
    figure.add_vline(x=0, line_dash="dash", line_color="#87928d")
    figure.update_layout(
        template="plotly_white",
        xaxis_title="标准化调整后系数（95% 置信区间）",
        yaxis_title="因素",
        margin={"l": 110, "r": 28, "t": 30, "b": 58},
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
        chart_type="coefficient_interval",
        dataset_version_ids=(dataset_version_id,),
        finding_refs=finding_refs,
        x_field="standardized_coefficient",
        y_fields=tuple(item.feature for item in result.reliable_factors),
        purpose="evidence",
        relative_path=f"charts/{chart_id}.html",
        content_fingerprint=(
            f"sha256:{hashlib.sha256(html.encode('utf-8')).hexdigest()}"
        ),
    )
    return artifact, html
