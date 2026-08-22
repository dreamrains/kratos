import numpy as np
import pandas as pd
import pytest

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


def test_repeated_units_within_one_group_are_aggregated_per_unit():
    """Rows repeated within one group (order-level data) aggregate to unit level."""

    frame = _frame(rows_per_group=12)
    frame.loc[1, "unit_id"] = frame.loc[0, "unit_id"]
    # a0 carries a second zero-value order: the per-unit sum keeps a0 comparable.
    frame.loc[1, "revenue"] = 0.0

    result = analyze_group_comparison(
        frame, GroupComparisonSpec("revenue", "channel", "unit_id")
    )

    assert result.design == "aggregated_independent"
    assert result.unit_aggregation == "sum"
    assert result.status == "supported"
    assert result.effective_units == 23
    # a0's two orders are aggregated per unit instead of being rejected.
    assert any(
        summary.group_value == "A" and summary.sample_size == 11
        for summary in result.groups
    )
    assert result.assumed_independent_units is True


def test_paired_design_uses_matched_units_and_reports_paired_tests():
    """Units observed in both groups form a paired design, not a dead end."""

    rows = []
    for index in range(30):
        baseline = 100 + np.sin(index * 1.7) * 3 + (index % 5)
        wobble = 0.3 if index % 2 else -0.3
        rows.append({"unit_id": f"u{index}", "channel": "A", "revenue": baseline})
        rows.append(
            {"unit_id": f"u{index}", "channel": "B", "revenue": baseline + 5.0 + wobble}
        )
    frame = pd.DataFrame(rows)

    result = analyze_group_comparison(
        frame, GroupComparisonSpec("revenue", "channel", "unit_id")
    )

    assert result.design == "paired"
    assert result.status == "supported"
    assert result.paired_sample_size == 30
    assert result.excluded_unpaired_units == 0
    assert result.difference == pytest.approx(5.0)
    assert result.confidence_low > 0
    assert result.p_value < 0.001
    assert result.wilcoxon_signed_rank_p_value < 0.001
    assert result.paired_cohens_dz > 1
    assert result.hedges_g is None
    assert result.mann_whitney_p_value is None
    assert result.assumed_independent_units is False


def test_paired_design_excludes_and_discloses_unpaired_units():
    rows = []
    for index in range(20):
        baseline = 50 + (index % 7)
        wobble = 0.2 if index % 2 else -0.2
        rows.append({"unit_id": f"u{index}", "channel": "A", "revenue": baseline})
        rows.append(
            {"unit_id": f"u{index}", "channel": "B", "revenue": baseline + 1.0 + wobble}
        )
    rows.append({"unit_id": "solo1", "channel": "A", "revenue": 80.0})
    rows.append({"unit_id": "solo2", "channel": "A", "revenue": 90.0})
    rows.append({"unit_id": "solo3", "channel": "B", "revenue": 70.0})
    frame = pd.DataFrame(rows)

    result = analyze_group_comparison(
        frame, GroupComparisonSpec("revenue", "channel", "unit_id")
    )

    assert result.design == "paired"
    assert result.paired_sample_size == 20
    assert result.excluded_unpaired_units == 3
    assert result.status == "supported"


def test_unit_aggregation_mean_is_selectable_for_paired_design():
    rows = []
    for index in range(24):
        wobble = 0.5 if index % 2 else -0.5
        rows.append({"unit_id": f"u{index}", "channel": "A", "revenue": 40 + index % 4})
        rows.append(
            {
                "unit_id": f"u{index}",
                "channel": "B",
                "revenue": 50 + index % 4 + wobble,
            }
        )
    frame = pd.DataFrame(rows)

    result = analyze_group_comparison(
        frame,
        GroupComparisonSpec("revenue", "channel", "unit_id", unit_aggregation="mean"),
    )

    assert result.design == "paired"
    assert result.unit_aggregation == "mean"
    assert result.difference == pytest.approx(10.0)


def test_paired_design_with_too_few_pairs_is_limited():
    rows = [
        {"unit_id": "u0", "channel": "A", "revenue": 10.0},
        {"unit_id": "u0", "channel": "B", "revenue": 12.0},
    ]
    frame = pd.DataFrame(rows)

    result = analyze_group_comparison(
        frame, GroupComparisonSpec("revenue", "channel", "unit_id")
    )

    assert result.status == "limited"
    assert result.reason_code == "insufficient_paired_units"


def test_group_comparison_with_a_single_group_is_limited():
    frame = _frame(rows_per_group=8)
    frame["channel"] = "A"

    result = analyze_group_comparison(
        frame, GroupComparisonSpec("revenue", "channel", "unit_id")
    )

    assert result.status == "limited"
    assert result.reason_code == "requires_exactly_two_groups"


def test_more_than_two_groups_degrades_to_descriptive_ranking():
    rows = []
    levels = {"A": 10.0, "B": 30.0, "C": 20.0, "D": 25.0}
    for index, (group_value, base) in enumerate(levels.items()):
        for offset in range(6):
            rows.append(
                {"unit_id": f"{group_value}{offset}", "channel": group_value, "revenue": base + offset}
            )
    frame = pd.DataFrame(rows)

    result = analyze_group_comparison(
        frame, GroupComparisonSpec("revenue", "channel", "unit_id")
    )

    assert result.status == "descriptive_ranking"
    assert result.reason_code == "more_than_two_groups_descriptive_ranking"
    assert result.design == "ranking"
    assert result.group_order == ("B", "D", "C", "A")
    assert [item.group_value for item in result.groups] == ["B", "D", "C", "A"]
    assert result.p_value is None
    assert result.maximum_claim_class.value == "descriptive"
    assert any("描述性排序" in item for item in result.limitations)


def test_ranking_aggregates_repeated_units_before_sorting():
    rows = []
    levels = {"A": 10.0, "B": 30.0, "C": 20.0}
    for group_value, base in levels.items():
        for offset in range(5):
            unit = f"{group_value}{offset}"
            rows.append({"unit_id": unit, "channel": group_value, "revenue": base + offset})
            if offset == 0:
                # a second order for the same unit doubles its summed revenue
                rows.append({"unit_id": unit, "channel": group_value, "revenue": base + offset})
    frame = pd.DataFrame(rows)

    result = analyze_group_comparison(
        frame, GroupComparisonSpec("revenue", "channel", "unit_id")
    )

    assert result.status == "descriptive_ranking"
    assert result.unit_aggregation == "sum"
    assert result.group_order[0] == "B"
    assert any("聚合" in item for item in result.limitations)


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
