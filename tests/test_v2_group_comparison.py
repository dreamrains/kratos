import numpy as np
import pandas as pd

from data_agent.v2.group_comparison import (
    GroupComparisonSpec,
    analyze_group_comparison,
)


def _frame(effect: float = 8.0, rows_per_group: int = 36) -> pd.DataFrame:
    index = np.arange(rows_per_group, dtype=float)
    baseline = 100 + np.sin(index * 1.7) * 3 + (index % 5)
    return pd.DataFrame(
        {
            "unit_id": [f"a{i}" for i in range(rows_per_group)]
            + [f"b{i}" for i in range(rows_per_group)],
            "channel": ["A"] * rows_per_group + ["B"] * rows_per_group,
            "revenue": np.concatenate([baseline, baseline + effect]),
        }
    )


def test_welch_comparison_reports_direction_interval_effect_and_sensitivity():
    result = analyze_group_comparison(
        _frame(), GroupComparisonSpec("revenue", "channel", "unit_id")
    )

    assert result.status == "supported"
    assert result.group_order == ("A", "B")
    assert result.difference == 8.0
    assert result.confidence_low > 0
    assert result.confidence_high > result.confidence_low
    assert result.p_value < 0.001
    assert result.hedges_g > 1
    assert result.welch_degrees_of_freedom > 0
    assert result.mann_whitney_p_value < 0.001
    assert [item.sample_size for item in result.groups] == [36, 36]


def test_no_reliable_difference_is_publishable_null_with_interval():
    result = analyze_group_comparison(
        _frame(effect=0.0), GroupComparisonSpec("revenue", "channel", "unit_id")
    )

    assert result.status == "null_result"
    assert result.reason_code == "no_reliable_mean_difference"
    assert result.confidence_low <= 0 <= result.confidence_high
    assert result.difference == 0


def test_repeated_analysis_units_are_limited_not_counted_as_independent():
    frame = _frame(rows_per_group=12)
    frame.loc[1, "unit_id"] = frame.loc[0, "unit_id"]

    result = analyze_group_comparison(
        frame, GroupComparisonSpec("revenue", "channel", "unit_id")
    )

    assert result.status == "limited"
    assert result.reason_code == "repeated_analysis_units"
    assert result.complete_case_rows == 24
    assert result.effective_units == 23


def test_group_comparison_requires_exactly_two_nonempty_groups():
    frame = _frame(rows_per_group=8)
    frame.loc[len(frame)] = ["c0", "C", 110]

    result = analyze_group_comparison(
        frame, GroupComparisonSpec("revenue", "channel", "unit_id")
    )

    assert result.status == "limited"
    assert result.reason_code == "requires_exactly_two_groups"


def test_small_identifiable_groups_are_not_rejected_by_fixed_n_rule():
    result = analyze_group_comparison(
        _frame(rows_per_group=8), GroupComparisonSpec("revenue", "channel", "unit_id")
    )

    assert result.reason_code != "fixed_small_sample_rule"
    assert result.status in {"supported", "null_result"}


def test_missing_values_are_reported_as_complete_case_scope():
    frame = _frame(rows_per_group=12)
    frame.loc[[0, 13], "revenue"] = np.nan

    result = analyze_group_comparison(
        frame, GroupComparisonSpec("revenue", "channel", "unit_id")
    )

    assert result.source_rows == 24
    assert result.complete_case_rows == 22
    assert result.dropped_rows == 2
