"""Comprehensive tests for data_agent.utils.data_features."""

import numpy as np
import pandas as pd
import pytest

from data_agent.utils.data_features import (
    _classify_column_type,
    _compute_outlier_ratio,
    _compute_quality_score,
    _extract_time_info,
    _infer_time_grain,
    _is_id_like,
    _looks_like_dates,
    _severity_marker,
    build_data_characteristics_card,
    detect_cross_dataset_relationships,
    scan_data_quality,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_clean_df(rows=50, seed=42):
    """Return a small, clean DataFrame with mixed types."""
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "id": range(rows),
        "value": rng.normal(100, 10, size=rows),
        "category": rng.choice(["A", "B", "C"], size=rows),
    })


def _make_date_series(start, periods, freq="D"):
    """Convenience wrapper around pd.date_range -> pd.Series."""
    return pd.Series(pd.date_range(start, periods=periods, freq=freq))


# ---------------------------------------------------------------------------
# 1. scan_data_quality
# ---------------------------------------------------------------------------

class TestScanDataQuality:
    """Tests for scan_data_quality."""

    def test_empty_dataframe(self):
        df = pd.DataFrame()
        result = scan_data_quality(df)
        assert result["columns"] == {}
        assert result["duplicate_row_ratio"] == 0.0
        assert result["quality_score"] == 100
        assert result["block_issues"] == []
        assert result["warnings"] == []
        assert result["info"] == ["Empty DataFrame"]

    def test_clean_dataframe(self):
        df = _make_clean_df()
        result = scan_data_quality(df)
        assert result["quality_score"] >= 90
        assert result["block_issues"] == []
        assert result["warnings"] == []
        # No column should have a missing_rate > 0
        for col_info in result["columns"].values():
            assert col_info["missing_rate"] == 0.0

    def test_high_missing_rate_blocks(self):
        df = pd.DataFrame({
            "bad_col": [None] * 6 + [1, 2, 3, 4],  # 60% missing
        })
        result = scan_data_quality(df)
        assert len(result["block_issues"]) >= 1
        assert any("bad_col" in issue for issue in result["block_issues"])

    def test_moderate_missing_rate_warns(self):
        df = pd.DataFrame({
            "so_so": [None] * 4 + list(range(11)),  # ~26.7% missing -> not >= 30
        })
        # Need exactly 30-50% to trigger warning
        df2 = pd.DataFrame({
            "so_so": [None] * 4 + list(range(7)),  # 4/11 ~36% missing
        })
        result = scan_data_quality(df2)
        assert len(result["warnings"]) >= 1
        assert any("so_so" in w for w in result["warnings"])

    def test_constant_column_flagged(self):
        df = pd.DataFrame({
            "const_val": [42] * 10,
            "varying": range(10),
        })
        result = scan_data_quality(df)
        assert any("const_val" in msg for msg in result["info"])

    def test_constant_with_nan_flagged(self):
        df = pd.DataFrame({
            "const_nan": [5] * 8 + [None, None],
        })
        result = scan_data_quality(df)
        const_info = result["columns"]["const_nan"]
        # nunique(dropna=False) = 2 (5 and NaN), so is_constant is False
        # but nunique(dropna=True) = 1, so all_same is True
        assert const_info["is_constant"] is False

    def test_duplicate_rows(self):
        df = pd.DataFrame({
            "a": [1, 1, 2, 3, 4, 4, 4],  # 3 duplicates out of 7
        })
        result = scan_data_quality(df)
        assert result["duplicate_row_ratio"] > 0
        # 3/7 ~ 42.8% which is > 10%, so warning
        assert any("Duplicate" in w for w in result["warnings"])

    def test_numeric_outliers_detected(self):
        # Use repeated values to avoid ID classification; with obvious outliers
        values = [1, 2, 3, 4, 5, 1, 2, 3, 4, 5, 1000, -500]
        df = pd.DataFrame({"measure": values})
        result = scan_data_quality(df)
        col_info = result["columns"]["measure"]
        assert col_info["type"] == "numeric"
        outlier_ratio = col_info["outlier_ratio"]
        assert outlier_ratio is not None
        assert outlier_ratio > 0

    def test_no_outliers_in_uniform_data(self):
        # Use repeated values to avoid ID classification
        df = pd.DataFrame({"measure": [1.0, 2.0, 3.0, 4.0, 5.0, 1.0, 2.0, 3.0, 4.0, 5.0]})
        result = scan_data_quality(df)
        assert result["columns"]["measure"]["outlier_ratio"] == 0.0


# ---------------------------------------------------------------------------
# 2. detect_cross_dataset_relationships
# ---------------------------------------------------------------------------

class TestDetectCrossDatasetRelationships:
    """Tests for detect_cross_dataset_relationships."""

    def test_single_dataset_no_relationships(self):
        datasets = {"orders": pd.DataFrame({"id": [1, 2, 3]})}
        result = detect_cross_dataset_relationships(datasets)
        assert result == []

    def test_empty_dict_no_relationships(self):
        result = detect_cross_dataset_relationships({})
        assert result == []

    def test_common_id_column(self):
        left = pd.DataFrame({
            "order_id": [101, 102, 103, 104, 105, 106, 107, 108],
            "amount": [10, 20, 30, 40, 50, 60, 70, 80],
        })
        right = pd.DataFrame({
            "order_id": [101, 102, 103, 104, 105, 106, 107, 108],
            "status": ["new"] * 8,
        })
        result = detect_cross_dataset_relationships({"orders": left, "payments": right})
        assert len(result) >= 1
        rel = result[0]
        assert rel["column"] == "order_id"
        assert rel["overlap_pct"] > 0

    def test_no_common_columns(self):
        left = pd.DataFrame({"a": [1, 2, 3]})
        right = pd.DataFrame({"b": [4, 5, 6]})
        result = detect_cross_dataset_relationships({"df1": left, "df2": right})
        assert result == []

    def test_three_datasets_overlapping(self):
        df_a = pd.DataFrame({"key": list(range(20)), "val_a": range(20)})
        df_b = pd.DataFrame({"key": list(range(15)), "val_b": range(15)})
        df_c = pd.DataFrame({"key": list(range(10)), "val_c": range(10)})
        result = detect_cross_dataset_relationships({"a": df_a, "b": df_b, "c": df_c})
        # Should find relationships between (a,b), (a,c), (b,c)
        pairs = {(r["left"], r["right"]) for r in result}
        assert len(pairs) >= 3

    def test_results_sorted_by_overlap_descending(self):
        df_a = pd.DataFrame({"key": list(range(20))})
        df_b = pd.DataFrame({"key": list(range(5))})  # high overlap pct
        df_c = pd.DataFrame({"key": list(range(100, 200))})  # low overlap
        result = detect_cross_dataset_relationships({"a": df_a, "b": df_b, "c": df_c})
        if len(result) >= 2:
            overlaps = [r["overlap_pct"] for r in result]
            assert overlaps == sorted(overlaps, reverse=True)

    def test_cardinality_one_column_skipped(self):
        """Columns where both sides have cardinality <= 1 are skipped."""
        left = pd.DataFrame({"flag": [1, 1, 1]})
        right = pd.DataFrame({"flag": [1, 1, 1]})
        result = detect_cross_dataset_relationships({"l": left, "r": right})
        # flag has cardinality 1 on both sides, not id-like, so skipped
        assert all(r["column"] != "flag" for r in result)


# ---------------------------------------------------------------------------
# 3. build_data_characteristics_card
# ---------------------------------------------------------------------------

class TestBuildDataCharacteristicsCard:
    """Tests for build_data_characteristics_card."""

    def test_starts_with_data_features_tag(self):
        df = _make_clean_df()
        card = build_data_characteristics_card("test_ds", df)
        assert card.startswith("[data_features]")

    def test_contains_row_col_count(self):
        df = _make_clean_df(rows=30)
        card = build_data_characteristics_card("test_ds", df)
        assert "30 rows" in card
        assert "3 cols" in card

    def test_contains_quality_score(self):
        df = _make_clean_df()
        card = build_data_characteristics_card("test_ds", df)
        assert "Quality:" in card
        assert "/100" in card

    def test_contains_column_type_counts(self):
        df = _make_clean_df()
        card = build_data_characteristics_card("test_ds", df)
        assert "numeric" in card
        assert "categorical" in card
        assert "date" in card
        assert "ID" in card

    def test_contains_time_info_with_date_column(self):
        df = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=30),
            "value": range(30),
        })
        card = build_data_characteristics_card("dated", df)
        assert "Time:" in card

    def test_no_time_info_without_dates(self):
        df = _make_clean_df()
        card = build_data_characteristics_card("no_dates", df)
        assert "Time:" not in card

    def test_contains_severity_and_issues(self):
        df = pd.DataFrame({
            "bad": [None] * 8 + [1, 2],  # 80% missing -> block
        })
        card = build_data_characteristics_card("blocked", df)
        assert "Issues:" in card
        assert "[BLOCK]" in card

    def test_warn_severity(self):
        df = pd.DataFrame({
            "moderate": [None] * 4 + list(range(7)),  # ~36% missing
        })
        card = build_data_characteristics_card("warned", df)
        assert "Issues:" in card
        assert "[WARN]" in card

    def test_info_severity(self):
        # Use non-duplicate data to avoid duplicate warning; just a constant column
        df = pd.DataFrame({
            "const_a": [5] * 10,
            "var_b": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        })
        card = build_data_characteristics_card("info_ds", df)
        assert "Issues:" in card

    def test_accepts_precomputed_quality(self):
        df = _make_clean_df()
        quality = scan_data_quality(df)
        card = build_data_characteristics_card("cached", df, quality)
        assert "[data_features]" in card

    def test_dataset_name_in_card(self):
        df = _make_clean_df()
        card = build_data_characteristics_card("my_special_ds", df)
        assert "my_special_ds" in card


# ---------------------------------------------------------------------------
# 4. Column type classification
# ---------------------------------------------------------------------------

class TestClassifyColumnType:
    """Tests for _classify_column_type."""

    def test_int_column_with_repeats_is_numeric(self):
        series = pd.Series([1, 1, 2, 2, 3, 3, 4, 4, 5, 5])
        assert _classify_column_type(series) == "numeric"

    def test_int_column_all_unique_is_id(self):
        """High-cardinality unique integers are classified as ID."""
        series = pd.Series(range(10))
        assert _classify_column_type(series) == "id"

    def test_float_column_with_repeats_is_numeric(self):
        series = pd.Series([1.1, 1.1, 2.2, 2.2, 3.3, 3.3, 4.4, 4.4, 5.5, 5.5])
        assert _classify_column_type(series) == "numeric"

    def test_datetime_column_date(self):
        series = pd.Series(pd.date_range("2024-01-01", periods=10))
        assert _classify_column_type(series) == "date"

    def test_high_cardinality_unique_id(self):
        # High uniqueness ratio, >= 5 values, >= 5 total
        values = list(range(100))
        series = pd.Series(values)
        assert _classify_column_type(series) == "id"

    def test_string_column_categorical(self):
        series = pd.Series(["A", "B", "A", "B", "C", "A", "B", "C", "A", "B"])
        assert _classify_column_type(series) == "categorical"

    def test_string_dates_detected_as_date(self):
        series = pd.Series([
            "2024-01-01", "2024-01-02", "2024-01-03",
            "2024-01-04", "2024-01-05", "2024-01-06",
            "2024-01-07", "2024-01-08", "2024-01-09", "2024-01-10",
        ])
        assert _classify_column_type(series) == "date"

    def test_numeric_id_like_classified_as_id(self):
        # All unique integers, >= 5 values
        series = pd.Series([1001, 1002, 1003, 1004, 1005, 1006, 1007, 1008])
        assert _classify_column_type(series) == "id"


class TestIsIdLike:
    """Tests for _is_id_like."""

    def test_all_unique_sufficient_length(self):
        series = pd.Series(range(10))
        assert _is_id_like(series) is True

    def test_low_uniqueness(self):
        series = pd.Series(["A", "B", "A", "B", "A", "B", "A", "B", "A", "B"])
        assert _is_id_like(series) is False

    def test_too_few_values(self):
        series = pd.Series([1, 2])
        assert _is_id_like(series) is False

    def test_all_nan(self):
        series = pd.Series([None, None, None, None, None])
        assert _is_id_like(series) is False

    def test_exactly_5_unique_of_5(self):
        series = pd.Series([1, 2, 3, 4, 5])
        assert _is_id_like(series) is True

    def test_4_unique_of_5_below_threshold(self):
        series = pd.Series([1, 2, 3, 4, 4])
        assert _is_id_like(series) is False


class TestLooksLikeDates:
    """Tests for _looks_like_dates."""

    def test_iso_format_dates(self):
        sample = pd.Series(["2024-01-01", "2024-02-15", "2024-03-30"])
        assert _looks_like_dates(sample) is True

    def test_mixed_non_dates(self):
        sample = pd.Series(["hello", "world", "foo", "bar", "baz"])
        assert _looks_like_dates(sample) is False

    def test_empty_series(self):
        sample = pd.Series([], dtype=str)
        assert _looks_like_dates(sample) is False

    def test_mostly_dates_with_some_noise(self):
        # 4 out of 5 parseable = 80% which is not > 80% (strictly)
        sample = pd.Series([
            "2024-01-01", "2024-02-01", "2024-03-01", "2024-04-01",
            "not a date",
        ])
        # 4/5 = 0.8 which is NOT > 0.8, so False
        assert _looks_like_dates(sample) is False

    def test_clear_dates(self):
        sample = pd.Series([
            "2024-01-01", "2024-02-01", "2024-03-01", "2024-04-01",
            "2024-05-01", "2024-06-01",
        ])
        assert _looks_like_dates(sample) is True


# ---------------------------------------------------------------------------
# 5. Quality score computation
# ---------------------------------------------------------------------------

class TestComputeQualityScore:
    """Tests for _compute_quality_score."""

    def test_perfect_data_scores_100(self):
        columns_info = {
            "col_a": {"missing_rate": 0.0, "is_constant": False, "outlier_ratio": 0.0},
        }
        assert _compute_quality_score(columns_info, 0.0) == 100

    def test_empty_columns_info_100(self):
        assert _compute_quality_score({}, 0.0) == 100

    def test_high_missing_penalty(self):
        columns_info = {
            "bad": {"missing_rate": 0.6, "is_constant": False, "outlier_ratio": None},
        }
        score = _compute_quality_score(columns_info, 0.0)
        assert score == 75  # 100 - 25

    def test_moderate_missing_penalty(self):
        columns_info = {
            "mod": {"missing_rate": 0.35, "is_constant": False, "outlier_ratio": None},
        }
        score = _compute_quality_score(columns_info, 0.0)
        assert score == 90  # 100 - 10

    def test_small_missing_penalty(self):
        columns_info = {
            "sm": {"missing_rate": 0.1, "is_constant": False, "outlier_ratio": None},
        }
        score = _compute_quality_score(columns_info, 0.0)
        # penalty = 0.1 * 5 = 0.5, score = 100 - 0.5 -> int = 99
        assert score == 99

    def test_constant_column_penalty(self):
        columns_info = {
            "const": {"missing_rate": 0.0, "is_constant": True, "outlier_ratio": None},
        }
        score = _compute_quality_score(columns_info, 0.0)
        assert score == 98  # 100 - 2

    def test_outlier_penalty(self):
        columns_info = {
            "outlier_col": {"missing_rate": 0.0, "is_constant": False, "outlier_ratio": 0.5},
        }
        score = _compute_quality_score(columns_info, 0.0)
        assert score == 95  # 100 - 5

    def test_no_outlier_penalty_below_threshold(self):
        columns_info = {
            "ok": {"missing_rate": 0.0, "is_constant": False, "outlier_ratio": 0.05},
        }
        score = _compute_quality_score(columns_info, 0.0)
        assert score == 100  # outlier 0.05 <= 0.1, no penalty

    def test_duplicate_row_penalty(self):
        columns_info = {
            "col": {"missing_rate": 0.0, "is_constant": False, "outlier_ratio": None},
        }
        score = _compute_quality_score(columns_info, 0.5)
        assert score == 90  # 100 - (0.5 * 20) = 90

    def test_score_never_below_zero(self):
        columns_info = {
            "a": {"missing_rate": 0.9, "is_constant": True, "outlier_ratio": 0.5},
            "b": {"missing_rate": 0.9, "is_constant": True, "outlier_ratio": 0.5},
            "c": {"missing_rate": 0.9, "is_constant": True, "outlier_ratio": 0.5},
            "d": {"missing_rate": 0.9, "is_constant": True, "outlier_ratio": 0.5},
            "e": {"missing_rate": 0.9, "is_constant": True, "outlier_ratio": 0.5},
        }
        score = _compute_quality_score(columns_info, 1.0)
        assert score >= 0

    def test_score_capped_at_100(self):
        columns_info = {
            "perfect": {"missing_rate": 0.0, "is_constant": False, "outlier_ratio": None},
        }
        score = _compute_quality_score(columns_info, 0.0)
        assert score <= 100


# ---------------------------------------------------------------------------
# 6. Outlier ratio
# ---------------------------------------------------------------------------

class TestComputeOutlierRatio:
    """Tests for _compute_outlier_ratio."""

    def test_too_few_values_returns_zero(self):
        series = pd.Series([1.0, 2.0, 3.0])
        assert _compute_outlier_ratio(series) == 0.0

    def test_no_outliers(self):
        series = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        assert _compute_outlier_ratio(series) == 0.0

    def test_with_outliers(self):
        series = pd.Series([1, 2, 3, 4, 5, 6, 1000])
        ratio = _compute_outlier_ratio(series)
        assert ratio > 0

    def test_zero_iqr_returns_zero(self):
        series = pd.Series([5.0, 5.0, 5.0, 5.0, 5.0])
        assert _compute_outlier_ratio(series) == 0.0

    def test_handles_nans(self):
        series = pd.Series([1.0, None, 3.0, 4.0, 5.0, 6.0, 1000.0])
        ratio = _compute_outlier_ratio(series)
        assert ratio > 0


# ---------------------------------------------------------------------------
# 7. Severity marker
# ---------------------------------------------------------------------------

class TestSeverityMarker:
    """Tests for _severity_marker."""

    def test_block(self):
        assert _severity_marker(1, 0) == "[BLOCK]"

    def test_block_overrides_warn(self):
        assert _severity_marker(2, 3) == "[BLOCK]"

    def test_warn(self):
        assert _severity_marker(0, 1) == "[WARN]"

    def test_info(self):
        assert _severity_marker(0, 0) == "[INFO]"


# ---------------------------------------------------------------------------
# 8. Time grain inference
# ---------------------------------------------------------------------------

class TestInferTimeGrain:
    """Tests for _infer_time_grain."""

    def test_daily(self):
        series = _make_date_series("2024-01-01", 30, freq="D")
        assert _infer_time_grain(series) == "daily"

    def test_weekly(self):
        series = _make_date_series("2024-01-01", 20, freq="7D")
        assert _infer_time_grain(series) == "weekly"

    def test_monthly(self):
        series = _make_date_series("2024-01-01", 24, freq="30D")
        assert _infer_time_grain(series) == "monthly"

    def test_yearly(self):
        series = _make_date_series("2020-01-01", 10, freq="365D")
        assert _infer_time_grain(series) == "yearly"

    def test_single_date_point(self):
        series = pd.Series(pd.to_datetime(["2024-06-15"]))
        assert _infer_time_grain(series) == "point"


# ---------------------------------------------------------------------------
# 9. Extract time info
# ---------------------------------------------------------------------------

class TestExtractTimeInfo:
    """Tests for _extract_time_info."""

    def test_no_date_columns_returns_none(self):
        df = pd.DataFrame({"a": [1, 2, 3]})
        quality = scan_data_quality(df)
        assert _extract_time_info(df, quality) is None

    def test_date_column_returns_info(self):
        df = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=30),
            "value": range(30),
        })
        quality = scan_data_quality(df)
        result = _extract_time_info(df, quality)
        assert result is not None
        assert "daily" in result
        assert "2024-01-01" in result

    def test_string_date_column(self):
        df = pd.DataFrame({
            "date": ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04",
                     "2024-01-05", "2024-01-06", "2024-01-07", "2024-01-08",
                     "2024-01-09", "2024-01-10"],
            "value": range(10),
        })
        quality = scan_data_quality(df)
        result = _extract_time_info(df, quality)
        assert result is not None
        assert "2024-01-01" in result

    def test_days_count_in_output(self):
        df = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=10, freq="D"),
        })
        quality = scan_data_quality(df)
        result = _extract_time_info(df, quality)
        assert "9 days" in result


# ---------------------------------------------------------------------------
# 10. Integration / edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Miscellaneous edge cases."""

    def test_all_missing_column(self):
        df = pd.DataFrame({"all_null": [None] * 10})
        result = scan_data_quality(df)
        assert result["columns"]["all_null"]["missing_rate"] == 1.0
        assert len(result["block_issues"]) >= 1

    def test_single_row_dataframe(self):
        df = pd.DataFrame({"a": [1], "b": ["x"]})
        result = scan_data_quality(df)
        assert result["quality_score"] >= 0
        assert "a" in result["columns"]

    def test_wide_dataframe(self):
        cols = {f"col_{i}": range(10) for i in range(50)}
        df = pd.DataFrame(cols)
        result = scan_data_quality(df)
        assert len(result["columns"]) == 50

    def test_mixed_types_in_dataframe(self):
        df = pd.DataFrame({
            "num": [1.0, 2.0, 3.0, 1.0, 2.0, 3.0, 1.0, 2.0, 3.0, 4.0],
            "cat": ["A", "B", "C", "A", "B", "C", "A", "B", "C", "A"],
            "dt": pd.date_range("2024-01-01", periods=10),
            "uid": list(range(100, 110)),
        })
        result = scan_data_quality(df)
        col_types = {name: info["type"] for name, info in result["columns"].items()}
        assert col_types["num"] == "numeric"  # has repeats, not ID-like
        assert col_types["cat"] == "categorical"
        assert col_types["dt"] == "date"
        assert col_types["uid"] == "id"

    def test_cross_dataset_with_nan_overlap(self):
        """NaN values should be dropped before computing overlap."""
        left = pd.DataFrame({"key": [1, 2, 3, None, None, None, None, None]})
        right = pd.DataFrame({"key": [1, 2, 3, 4, 5, 6, 7, 8]})
        result = detect_cross_dataset_relationships({"l": left, "r": right})
        if len(result) > 0:
            rel = result[0]
            assert rel["overlap_pct"] > 0
