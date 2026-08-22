from __future__ import annotations

import hashlib
import uuid

import numpy as np
import plotly.graph_objects as go

from data_agent.v2.curve_fitting import CurveFitResult
from data_agent.v2.models import ChartArtifact


_FAMILY_COLORS = {
    "power": "#3974b8",
    "exponential": "#d56b3f",
    "logarithmic": "#5a9a58",
}


def _family_curve(family: str, params: dict[str, float], x: np.ndarray) -> np.ndarray:
    if family == "power":
        return params["a"] * np.power(x, params["b"])
    if family == "exponential":
        return params["a"] * np.exp(params["b"] * x)
    return params["a"] + params["b"] * np.log(x)


def build_curve_fit_chart(
    result: CurveFitResult,
    *,
    dataset_version_id: str,
    finding_refs: tuple[str, ...],
    title: str,
) -> tuple[ChartArtifact, str]:
    if not result.points:
        raise ValueError("curve chart requires fitted points")
    x = np.array([point.x for point in result.points], dtype=float)
    y = np.array([point.y for point in result.points], dtype=float)
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=x,
            y=y,
            mode="markers",
            name="观测点（各列均值）",
            marker={"color": "#333333", "size": 8},
            hovertemplate="x=%{x:.0f}<br>观测=%{y:.4f}<extra></extra>",
        )
    )
    # Curves are drawn strictly within the observed x range: no extrapolation.
    dense_x = np.linspace(float(x.min()), float(x.max()), 200)
    for fit in result.fits[:3]:
        figure.add_trace(
            go.Scatter(
                x=dense_x,
                y=_family_curve(fit.family, fit.params, dense_x),
                mode="lines",
                name=f"{fit.formula}（R²={fit.r_squared:.3f}）",
                line={
                    "color": _FAMILY_COLORS.get(fit.family, "#888888"),
                    "dash": "dash" if fit.family != result.best_family else "solid",
                    "width": 2,
                },
                hovertemplate="x=%{x:.0f}<br>拟合=%{y:.4f}<extra></extra>",
            )
        )
    figure.update_layout(
        template="plotly_white",
        xaxis_title="x（按拟合口径）",
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
        chart_type="curve_fit_overlay",
        dataset_version_ids=(dataset_version_id,),
        finding_refs=finding_refs,
        x_field="fit_x",
        y_fields=(result.metric,),
        purpose="evidence",
        relative_path=f"charts/{chart_id}.html",
        content_fingerprint=f"sha256:{hashlib.sha256(html.encode('utf-8')).hexdigest()}",
    )
    return artifact, html
