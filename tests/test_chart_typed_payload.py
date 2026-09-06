import base64
import json

import numpy as np
import plotly.graph_objects as go
import pytest

from data_agent.tools.chart_contract import validate_figure_renderability


@pytest.mark.parametrize("kind", ["scatter", "bar", "heatmap"])
@pytest.mark.parametrize("valid", [True, False])
def test_renderability_survives_plotly_binary_roundtrip(kind, valid):
    values = np.array([1.5, np.nan]) if valid else np.array([np.nan, np.inf])
    trace = go.Heatmap(z=values.reshape(1, 2)) if kind == "heatmap" else getattr(go, kind.title())(y=values)
    figure = go.Figure(trace)
    expected = validate_figure_renderability(figure)
    assert bool(expected) is not valid
    reloaded = go.Figure(json.loads(figure.to_json()))
    assert validate_figure_renderability(reloaded) == expected


@pytest.mark.parametrize("payload", [
    {"dtype":"f8","bdata":"not-base64"},
    {"dtype":"O","bdata":base64.b64encode(b"12345678").decode()},
    {"dtype":"f8","bdata":base64.b64encode(b"x").decode()},
    {"dtype":"f8","bdata":base64.b64encode(np.array([1.]).tobytes()).decode(),"shape":"2, 3"},
])
def test_malformed_binary_payload_does_not_bypass_finite_value_guard(payload):
    from types import SimpleNamespace
    figure = SimpleNamespace(data=[SimpleNamespace(type="scatter", y=payload)])
    assert validate_figure_renderability(figure)
