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

from data_agent.tools.eda import (
    correlation_analysis,
    contribute_decomposition,
    distribution_analysis,
)
from data_agent.tools.data_understand import quick_profile as _quick_profile  # noqa: F401
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


def test_distribution_emits_claim_neutral_measurements(workspace):
    """Removing the structured measurement rows would make descriptive
    distribution results impossible to cite even though the tool computed
    them."""

    payload = json.loads(distribution_analysis(
        "factors",
        columns="目标值,活跃度",
    ))

    projected = {
        (item["column"], item["metric"]): (item["value"], item["unit"])
        for item in payload["measurements"]
    }
    assert projected[("目标值", "count")] == (32, "count")
    assert projected[("目标值", "mean")][1] == "value"
    assert projected[("活跃度", "mean")][1] == "value"
    assert projected[("活跃度", "normality_p_value")][1] == "value"

    capability = registry.capability_for("distribution_analysis")
    assert validate_capability_output(capability, payload) == []


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


def test_decomposition_attests_descriptive_noncausal_claim_class(workspace):
    result = registry.execute(
        "contribute_decomposition",
        {
            "name": "factors",
            "metric": "目标值",
            "dimension": "渠道",
            "date_col": "日期",
            "period_a": "2026-01-01~2026-01-16",
            "period_b": "2026-01-17~2026-02-01",
            "agg_func": "sum",
        },
    )
    payload = result.data
    assert isinstance(payload, dict)
    assert payload["allowed_claim_class"] == "descriptive_attribution"
    assert payload["allowed_claim_class"] != "causal_effect"
    capability = registry.capability_for("contribute_decomposition")
    assert "allowed_claim_class" in capability["evidence_fields"]
    assert capability["output_contract"]["allowed_claim_class_ceiling"] == (
        "descriptive_attribution"
    )
    assert validate_capability_output(capability, payload) == []


@pytest.mark.parametrize(
    "tampered_class",
    ["causal", "causal_effect", "unknown_class", "", None],
)
def test_decomposition_rejects_invalid_or_over_ceiling_claim_attestation(
    workspace,
    tampered_class,
):
    result = registry.execute(
        "contribute_decomposition",
        {
            "name": "factors",
            "metric": "目标值",
            "dimension": "渠道",
            "date_col": "日期",
            "period_a": "2026-01-01~2026-01-16",
            "period_b": "2026-01-17~2026-02-01",
            "agg_func": "sum",
        },
    )
    payload = dict(result.data or {})
    payload["allowed_claim_class"] = tampered_class

    capability = registry.capability_for("contribute_decomposition")

    assert validate_capability_output(capability, payload) == [
        "allowed_claim_class"
    ]


@pytest.mark.parametrize(("tool_name", "arguments"), [
    ("quick_profile", {"name": "factors"}),
    ("detect_data_quality", {"name": "factors"}),
    ("quick_profile", {"name": "factors", "compact": True}),
    ("correlation_analysis", {"name": "factors", "columns": "目标值,活跃度"}),
    ("distribution_analysis", {"name": "factors", "columns": "目标值,活跃度"}),
    ("segmentation_analysis", {
        "name": "factors",
        "features": "目标值,活跃度",
        "n_clusters": 3,
    }),
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
