"""Structured-output and capability-truth tests (Task 7, Step 2).

These tests assert that analytical tool output actually contains the evidence
fields advertised by capability metadata, and that the new inferential
factor-relationship tool emits the diagnostics required for an honest
inferential claim (effective N, robust standard errors, adjusted p-values,
collinearity, time-dependence, limitations, claim class).
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pandas as pd
import pytest

from data_agent.tools.eda import correlation_analysis
from data_agent.tools.registry import registry, validate_capability_output
from data_agent.tools.statistics import factor_relationship_analysis
from data_agent.session.workspace import Workspace

from tests.fixtures.analysis_reliability import build_factor_relationship_frame


@pytest.fixture(autouse=True)
def workspace(monkeypatch):
    """Bind a fresh in-memory workspace exposing the ``factors`` dataset.

    Applied automatically to every test in this module so the parametrized
    capability-truth test (which does not name the fixture as a parameter)
    still observes the seeded workspace.
    """

    import data_agent.tools._utils as tool_utils
    import data_agent.tools.statistics as statistics_module
    import data_agent.tools.eda as eda_module
    import data_agent.tools.ml as ml_module

    ws = Workspace()
    ws.add("factors", build_factor_relationship_frame())
    monkeypatch.setattr(tool_utils, "workspace", ws)
    monkeypatch.setattr(statistics_module, "workspace", ws)
    monkeypatch.setattr(eda_module, "workspace", ws)
    monkeypatch.setattr(ml_module, "workspace", ws)
    return ws


def test_correlation_emits_effective_n_and_validated_p_value(workspace):
    payload = json.loads(correlation_analysis("factors", "目标值,活跃度"))
    pair = payload["pairs"][0]
    assert {"var1", "var2", "correlation", "effective_sample_size", "p_value"} <= set(pair)
    assert payload["allowed_claim_class"] == "exploratory_association"


def test_correlation_returns_structured_insufficient_data_error(workspace):
    """A pair with fewer than three pairwise-complete rows must produce a
    structured insufficient-data diagnostic, not a coerced matrix value."""
    ws = workspace
    ws.add("thin", pd.DataFrame({"x": [1.0, 2.0], "y": [2.0, None]}))
    payload = json.loads(correlation_analysis("thin", "x,y"))
    assert payload["allowed_claim_class"] == "exploratory_association"
    assert payload["pairs"][0]["effective_sample_size"] < 3
    assert "insufficient" in payload["pairs"][0].get("status", "").lower() or (
        payload["pairs"][0].get("p_value") is None
        and payload["pairs"][0].get("correlation") is None
    )


def test_factor_relationship_emits_inferential_diagnostics(workspace):
    payload = json.loads(factor_relationship_analysis(
        "factors",
        target_col="目标值",
        features="活跃度,价格",
        time_col="日期",
    ))
    coefficient = payload["coefficients"][0]
    assert {"estimate", "std_error", "confidence_interval", "p_value", "adjusted_p_value"} <= set(coefficient)
    assert {"effective_sample_size", "collinearity", "time_dependence", "limitations"} <= set(payload)
    assert payload["allowed_claim_class"] == "inferential_associations"


@pytest.mark.parametrize(("tool_name", "arguments"), [
    ("correlation_analysis", {"name": "factors", "columns": "目标值,活跃度"}),
    ("factor_relationship_analysis", {
        "name": "factors",
        "target_col": "目标值",
        "features": "活跃度,价格",
        "time_col": "日期",
    }),
    ("regression_analysis", {
        "name": "factors",
        "target_col": "目标值",
        "features": "活跃度,价格",
    }),
    ("attribution_analysis", {
        "name": "factors",
        "target_col": "目标值",
        "features": "活跃度,价格",
    }),
])
def test_declared_evidence_fields_exist_in_representative_output(tool_name, arguments):
    result = registry.execute(tool_name, arguments)
    payload = json.loads(result.summary)
    capability = registry.capability_for(tool_name)
    assert validate_capability_output(capability, payload) == []
