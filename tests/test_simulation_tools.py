from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from data_agent.session.workspace import workspace
from data_agent.tools.registry import ToolResult
from data_agent.tools.simulation import what_if_simulation


@pytest.fixture
def simulation_dataset():
    name = "what_if_contract"
    feature = np.arange(1, 31, dtype=float)
    workspace.add(
        name,
        pd.DataFrame(
            {
                "channel": ["organic", "paid"] * 15,
                "revenue": feature * 10,
                "cost": feature * 3,
                "orders": feature * 2 + 5,
            }
        ),
    )
    yield name
    workspace.remove(name)


def test_sensitivity_simulation_returns_traceable_baseline_and_projection(
    simulation_dataset,
):
    result = what_if_simulation(
        simulation_dataset,
        mode="sensitivity",
        metric="revenue",
        dimension="channel",
        change_pct=10,
    )

    assert isinstance(result, ToolResult)
    assert result.data["mode"] == "sensitivity"
    assert result.data["projected"]["total"] == pytest.approx(
        result.data["baseline"]["total"] * 1.1
    )
    assert result.data["impact"]["relative_pct"] == pytest.approx(10.0)


def test_reverse_sensitivity_reports_required_change(simulation_dataset):
    baseline = sum(np.arange(1, 31, dtype=float) * 10)
    result = what_if_simulation(
        simulation_dataset,
        mode="sensitivity",
        metric="revenue",
        dimension="channel",
        target_value=str(baseline * 1.2),
    )

    assert isinstance(result, ToolResult)
    assert result.data["mode"] == "sensitivity_reverse"
    assert result.data["required_total_pct"] == pytest.approx(20.0)
    assert {row["dimension_value"] for row in result.data["breakdown"]} == {
        "organic",
        "paid",
    }


def test_predict_simulation_trains_and_applies_feature_change(simulation_dataset):
    result = what_if_simulation(
        simulation_dataset,
        mode="predict",
        target_col="revenue",
        feature_changes=json.dumps({"cost": 10}),
    )

    assert isinstance(result, ToolResult)
    assert result.data["mode"] == "predict"
    assert result.data["target_col"] == "revenue"
    assert result.data["feature_changes"] == {"cost": 10}
    assert result.data["model_type"]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"name": "missing_dataset", "mode": "sensitivity"},
        {"name": "what_if_contract", "mode": "invalid"},
        {
            "name": "what_if_contract",
            "mode": "sensitivity",
            "metric": "missing",
            "dimension": "channel",
            "change_pct": 10,
        },
        {
            "name": "what_if_contract",
            "mode": "predict",
            "target_col": "revenue",
            "feature_changes": "not-json",
        },
    ],
)
def test_simulation_rejects_invalid_inputs(simulation_dataset, kwargs):
    result = what_if_simulation(**kwargs)
    rendered = result.summary if isinstance(result, ToolResult) else str(result)

    assert "error" in rendered.casefold() or "不存在" in rendered or "不支持" in rendered
