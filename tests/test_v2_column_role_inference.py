"""Numeric self-healing in column role inference (B1.4).

Object columns that are almost entirely numeric-coercible become metric
candidates; identifiers and low-cardinality strings stay out.
"""

import pandas as pd

from data_agent.v2.planner import (
    ColumnRole,
    DatasetPlanningContext,
    _infer_column_role,
    _parameter_schema,
)
from data_agent.v2.router import AnalysisKind


def _context(frame: pd.DataFrame) -> DatasetPlanningContext:
    return DatasetPlanningContext.from_frame(
        filename="probe.csv",
        source_fingerprint="sha256:" + "0" * 64,
        frame=frame,
    )


def test_mostly_numeric_object_column_is_healed_to_numeric():
    values = [f"{1000 + index}.75" for index in range(60)] + ["-"]
    series = pd.Series(values, dtype="object")

    assert _infer_column_role("卖量收入", series) is ColumnRole.NUMERIC


def test_low_cardinality_numeric_strings_stay_categorical():
    series = pd.Series(["1", "2", "1", "2"] * 30, dtype="object")

    assert _infer_column_role("用户类型", series) is ColumnRole.CATEGORICAL


def test_identifier_named_numeric_strings_stay_identifiers():
    series = pd.Series([f"3285072072829829{index:03d}" for index in range(200)], dtype="object")

    assert _infer_column_role("user_id", series) is ColumnRole.IDENTIFIER


def test_date_like_strings_stay_datetime():
    series = pd.Series([f"2021/01/{day:02d}" for day in range(1, 21)] * 5, dtype="object")

    assert _infer_column_role("日期", series) is ColumnRole.DATETIME


def test_healed_column_appears_in_metric_enum():
    frame = pd.DataFrame(
        {
            "日期": pd.date_range("2021-01-01", periods=50),
            "卖量收入": pd.Series(
                [f"{value}.5" for value in range(50)] + ["-"], dtype="object"
            )[:50],
            "公司": ["内部游戏", "外部游戏"] * 25,
        }
    )
    context = _context(frame)

    roles = {column.name: column.role for column in context.columns}
    assert roles["卖量收入"] is ColumnRole.NUMERIC

    schema = _parameter_schema(AnalysisKind.GROUP_COMPARISON, context)
    assert "卖量收入" in schema["properties"]["metric"]["enum"]
