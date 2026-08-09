from __future__ import annotations

import pandas as pd
import pytest

from data_agent.tools._utils import parse_period_range, resolve_date_col


@pytest.mark.parametrize(
    ("frame", "expected"),
    [
        (pd.DataFrame({"date": pd.date_range("2025-01-01", periods=2)}), "date"),
        (pd.DataFrame({"日期": ["2025-01-01", "2025-01-02"]}), "日期"),
    ],
)
def test_resolve_date_col_detects_datetime_and_parseable_text(frame, expected):
    column, error = resolve_date_col(frame)

    assert error is None
    assert column == expected


def test_resolve_date_col_honors_explicit_column_and_reports_missing_date():
    frame = pd.DataFrame({"left": [1, 2], "right": [3, 4]})

    assert resolve_date_col(frame, "right") == ("right", None)
    column, error = resolve_date_col(frame)
    assert column == ""
    assert "date_col" in error


@pytest.mark.parametrize(
    ("period", "expected"),
    [
        (
            "last_month",
            (pd.Timestamp("2025-01-01"), pd.Timestamp("2025-01-31")),
        ),
        (
            "this_week",
            (pd.Timestamp("2025-02-10"), pd.Timestamp("2025-02-12")),
        ),
        (
            "2025-01-03~2025-01-09",
            (pd.Timestamp("2025-01-03"), pd.Timestamp("2025-01-09")),
        ),
    ],
)
def test_parse_period_range_supported_forms(period, expected):
    assert parse_period_range(period, pd.Timestamp("2025-02-12")) == expected


def test_parse_period_range_rejects_unknown_shortcut():
    assert parse_period_range("invalid_period", pd.Timestamp("2025-02-12")) is None
