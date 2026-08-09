"""Period-comparability contracts collected by the normal pytest suite."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from data_agent.session.workspace import workspace
from data_agent.tools._utils import analyze_period_structure, compare_period_structures
from data_agent.tools.eda import compare_periods, contribute_decomposition


@pytest.fixture
def comparison_dataset():
    name = "period_comparability"
    rng = np.random.default_rng(42)
    workspace.add(
        name,
        pd.DataFrame(
            {
                "date": pd.date_range("2025-09-28", periods=30, freq="D"),
                "revenue": rng.uniform(1000, 5000, 30).round(2),
                "dau": rng.integers(5000, 20000, 30),
                "channel": rng.choice(["organic", "paid"], 30),
            }
        ),
    )
    yield name
    workspace.remove(name)


@pytest.mark.parametrize(
    ("start", "end", "days", "weekdays", "weekends", "first", "last"),
    [
        ("2025-10-06", "2025-10-12", 7, 5, 2, "Monday", "Sunday"),
        ("2025-09-28", "2025-09-30", 3, 2, 1, "Sunday", "Tuesday"),
        ("2025-10-01", "2025-10-01", 1, 1, 0, "Wednesday", "Wednesday"),
    ],
)
def test_period_structure_counts(
    start, end, days, weekdays, weekends, first, last
):
    structure = analyze_period_structure(pd.Timestamp(start), pd.Timestamp(end))

    assert structure["day_count"] == days
    assert structure["weekday_count"] == weekdays
    assert structure["weekend_count"] == weekends
    assert len(structure["dates"]) == days
    assert structure["dates"][0]["dow"] == first
    assert structure["dates"][-1]["dow"] == last


def test_long_period_omits_daily_details():
    structure = analyze_period_structure(
        pd.Timestamp("2025-01-01"), pd.Timestamp("2025-12-31")
    )

    assert structure["day_count"] == 365
    assert "dates" not in structure
    assert "dates_note" in structure


def test_equal_period_structures_need_no_normalization_warning():
    first = analyze_period_structure(
        pd.Timestamp("2025-10-06"), pd.Timestamp("2025-10-12")
    )
    second = analyze_period_structure(
        pd.Timestamp("2025-10-13"), pd.Timestamp("2025-10-19")
    )

    comparison = compare_period_structures(first, second)

    assert comparison["lengths_equal"] is True
    assert comparison["daily_avg_recommended"] is False
    assert comparison["warnings"] == []


def test_different_period_lengths_recommend_daily_normalization():
    first = analyze_period_structure(
        pd.Timestamp("2025-09-28"), pd.Timestamp("2025-09-30")
    )
    second = analyze_period_structure(
        pd.Timestamp("2025-10-01"), pd.Timestamp("2025-10-07")
    )

    comparison = compare_period_structures(first, second)

    assert comparison["lengths_equal"] is False
    assert comparison["daily_avg_recommended"] is True
    assert any("3 days" in item and "7 days" in item for item in comparison["warnings"])


def test_equal_lengths_with_different_weekday_mix_warn():
    first = analyze_period_structure(
        pd.Timestamp("2025-10-06"), pd.Timestamp("2025-10-08")
    )
    second = analyze_period_structure(
        pd.Timestamp("2025-10-10"), pd.Timestamp("2025-10-12")
    )

    comparison = compare_period_structures(first, second)

    assert comparison["lengths_equal"] is True
    assert comparison["weekday_ratio_diff"] > 0.1
    assert any("ratio" in item for item in comparison["warnings"])


def test_compare_periods_exposes_daily_averages(comparison_dataset):
    result = json.loads(
        compare_periods(
            comparison_dataset,
            date_col="date",
            metrics="revenue,dau",
            period_a="2025-09-28~2025-09-30",
            period_b="2025-10-01~2025-10-07",
        )
    )

    assert result["period_a"]["day_count"] == 3
    assert result["period_b"]["day_count"] == 7
    assert result["comparability"]["daily_avg_recommended"] is True
    for metric in ("revenue", "dau"):
        values = result["metrics"][metric]
        assert values["daily_avg_a"] == pytest.approx(values["period_a"] / 3)
        assert values["daily_avg_b"] == pytest.approx(values["period_b"] / 7)
        assert "daily_avg_diff" in values
        assert "daily_avg_change_pct" in values


def test_compare_periods_equal_lengths_keep_daily_values(comparison_dataset):
    result = json.loads(
        compare_periods(
            comparison_dataset,
            date_col="date",
            metrics="revenue",
            period_a="2025-09-28~2025-10-04",
            period_b="2025-10-05~2025-10-11",
        )
    )

    assert result["comparability"]["lengths_equal"] is True
    assert result["comparability"]["daily_avg_recommended"] is False
    assert "daily_avg_a" in result["metrics"]["revenue"]


def test_segmented_compare_periods_exposes_daily_averages(comparison_dataset):
    result = json.loads(
        compare_periods(
            comparison_dataset,
            date_col="date",
            metrics="revenue",
            period_a="2025-09-28~2025-09-30",
            period_b="2025-10-01~2025-10-07",
            dimensions="channel",
        )
    )

    for row in result["comparisons"]:
        assert "daily_avg_a" in row["revenue"]
        assert "daily_avg_b" in row["revenue"]


def test_unequal_contribution_periods_include_daily_normalization(
    comparison_dataset,
):
    result = contribute_decomposition(
        comparison_dataset,
        metric="revenue",
        dimension="channel",
        date_col="date",
        period_a="2025-09-28~2025-09-30",
        period_b="2025-10-01~2025-10-07",
        agg_func="sum",
    )
    data = result.data

    assert data["comparability"]["daily_avg_recommended"] is True
    assert {"daily_avg_a", "daily_avg_b"} <= data["daily_normalized"].keys()
    assert data["period_a"]["day_count"] == 3
    assert data["period_b"]["day_count"] == 7
    assert "可比性" in result.summary


def test_equal_contribution_periods_omit_daily_normalization(comparison_dataset):
    result = contribute_decomposition(
        comparison_dataset,
        metric="revenue",
        dimension="channel",
        date_col="date",
        period_a="2025-09-28~2025-10-04",
        period_b="2025-10-05~2025-10-11",
        agg_func="sum",
    )

    assert result.data["comparability"]["lengths_equal"] is True
    assert "daily_normalized" not in result.data


def test_compare_periods_preserves_legacy_result_keys(comparison_dataset):
    result = json.loads(
        compare_periods(
            comparison_dataset,
            date_col="date",
            metrics="revenue",
            period_a="2025-09-28~2025-09-30",
            period_b="2025-10-01~2025-10-07",
        )
    )

    assert {"label", "range", "rows"} <= result["period_a"].keys()
    assert {"label", "range", "rows"} <= result["period_b"].keys()
    assert {"period_a", "period_b", "diff", "change_pct"} <= result["metrics"][
        "revenue"
    ].keys()
