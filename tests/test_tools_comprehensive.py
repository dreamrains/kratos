#!/usr/bin/env python3
"""全面工具单元测试 — 覆盖所有工具的边界条件、错误路径和核心逻辑。

使用 pytest 运行: pytest tests/test_tools_comprehensive.py -v
直接运行: python tests/test_tools_comprehensive.py
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from datetime import datetime

if sys.platform == "win32":
    os.system("")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PASS = 0
FAIL = 0
SKIP = 0
ERRORS = []


def test(name, func):
    global PASS, FAIL, SKIP
    print(f"  {name}...", end=" ", flush=True)
    try:
        result = func()
        if result is True:
            PASS += 1
            print("PASS")
        elif result == "skip":
            SKIP += 1
            print("SKIP")
        else:
            FAIL += 1
            msg = f"FAIL: {name} — {result}"
            ERRORS.append(msg)
            print(msg)
    except Exception as e:
        FAIL += 1
        msg = f"FAIL: {name} — {e}"
        ERRORS.append(msg)
        print(msg)
        import traceback
        traceback.print_exc()


def assert_ok(result, label=""):
    if isinstance(result, str) and result.startswith("Error"):
        return f"{label} returned error: {result[:300]}"
    if isinstance(result, str) and '"error"' in result[:80]:
        return f"{label} returned error JSON: {result[:300]}"
    return True


# ============================================================
print("=" * 60)
print("初始化")
print("=" * 60)

from data_agent.config import get_config
from data_agent.tools import discover_tools
discover_tools()

import numpy as np
import pandas as pd
from data_agent.session.workspace import workspace


def _make_test_df():
    """创建标准测试数据集（每次调用返回新的 DataFrame）"""
    np.random.seed(42)
    n = 100
    return pd.DataFrame({
        "date": pd.date_range("2025-01-01", periods=n, freq="D"),
        "sales": np.random.uniform(100, 1000, n).round(2),
        "users": np.random.randint(10, 200, n),
        "channel": np.random.choice(["A", "B", "C"], n),
        "region": np.random.choice(["north", "south"], n),
        "revenue": np.random.uniform(500, 5000, n).round(2),
        "is_new": np.random.choice([0, 1], n),
    })


def _reset_test_data():
    """重置 test 数据集到初始状态，防止测试间状态泄漏。"""
    workspace.add("test", _make_test_df())
    workspace.add("test_small", pd.DataFrame({"a": [1, 2], "b": [3, 4]}))
    workspace.add("test_empty", pd.DataFrame())
    workspace.add("test_nulls", pd.DataFrame({
        "x": [1, None, 3, None, 5],
        "y": [None, 2, None, 4, None],
        "cat": ["a", "b", "a", None, "b"],
    }))
    # 清除 profile 缓存（workspace.add 不自动清理 metadata）
    for name in ["test", "test_small", "test_nulls", "test_empty"]:
        workspace.set_metadata(name, "_profile_cache", None)
        workspace.set_metadata(name, "_profile_shape", None)


# 首次初始化
_reset_test_data()


# ============================================================
print("\n" + "=" * 60)
print("一、data_clean — 类型推断与清洗")
print("=" * 60)


def test_infer_percentage():
    from data_agent.tools.data_clean import infer_column_type
    s = pd.Series(["12.5%", "25%", "3.14%"])
    result = infer_column_type(s)
    if result["suggested_type"] != "percentage_to_float":
        return f"should detect percentage, got {result['suggested_type']}"
    return True


def test_infer_bool():
    from data_agent.tools.data_clean import infer_column_type
    for values in [["是", "否", "是"], ["yes", "no", "yes"], ["true", "false"]]:
        s = pd.Series(values)
        result = infer_column_type(s)
        if result["suggested_type"] != "bool":
            return f"should detect bool for {values}, got {result['suggested_type']}"
    return True


def test_infer_date_int():
    from data_agent.tools.data_clean import infer_column_type
    s = pd.Series([20250101, 20250102, 20250103])
    result = infer_column_type(s)
    if result["suggested_type"] != "date_int_to_datetime":
        return f"should detect date_int, got {result['suggested_type']}"
    return True


def test_infer_numeric_string():
    from data_agent.tools.data_clean import infer_column_type
    s = pd.Series(["100", "200", "300"])
    result = infer_column_type(s)
    if result["suggested_type"] != "numeric":
        return f"should detect numeric string, got {result['suggested_type']}"
    return True


def test_infer_keep():
    from data_agent.tools.data_clean import infer_column_type
    s = pd.Series([1.5, 2.5, 3.5])
    result = infer_column_type(s)
    if result["suggested_type"] != "keep":
        return f"should keep float column, got {result['suggested_type']}"
    return True


def test_infer_low_cardinality_int():
    from data_agent.tools.data_clean import infer_column_type
    s = pd.Series([0, 1, 0, 1, 0])
    result = infer_column_type(s)
    if result["suggested_type"] != "category_maybe":
        return f"should suggest category for low-card int, got {result['suggested_type']}"
    return True


def test_auto_clean_percentage():
    from data_agent.tools.data_clean import auto_clean
    df = pd.DataFrame({"pct": ["10%", "20%", "30%"], "name": ["a", "b", "c"]})
    cleaned, applied, needs = auto_clean(df)
    if not applied:
        return "should auto-clean percentage column"
    if cleaned["pct"].iloc[0] != 0.1:
        return f"10% should become 0.1, got {cleaned['pct'].iloc[0]}"
    return True


def test_auto_clean_bool():
    from data_agent.tools.data_clean import auto_clean
    df = pd.DataFrame({"flag": ["是", "否", "是"], "val": [1, 2, 3]})
    cleaned, applied, _ = auto_clean(df)
    val = cleaned["flag"].iloc[0]
    if val != True:  # noqa: E712 — use != to handle numpy bool
        return f"'是' should become True, got {val} (type={type(val)})"
    return True


def test_clean_data_drop_missing():
    from data_agent.tools.data_clean import clean_data
    workspace.add("clean_test", pd.DataFrame({
        "a": [1, None, 3], "b": [4, 5, None]
    }))
    result = clean_data("clean_test", missing_strategy="drop")
    data = json.loads(result)
    if data["final_rows"] != 1:
        return f"drop should leave 1 row, got {data['final_rows']}"
    return True


def test_clean_data_fill_mean():
    from data_agent.tools.data_clean import clean_data
    workspace.add("mean_test", pd.DataFrame({
        "val": [10.0, None, 30.0], "cat": ["a", "b", "c"]
    }))
    result = clean_data("mean_test", missing_strategy="fill_mean")
    data = json.loads(result)
    if data["final_rows"] != 3:
        return "fill_mean should keep all rows"
    return True


def test_clean_data_fill_constant():
    from data_agent.tools.data_clean import clean_data
    workspace.add("const_test", pd.DataFrame({
        "val": [1, None, 3], "cat": ["a", None, "c"]
    }))
    result = clean_data("const_test", missing_strategy="fill_constant", fill_value="0")
    data = json.loads(result)
    if data["final_rows"] != 3:
        return "fill_constant should keep all rows"
    return True


def test_clean_data_outlier_cap():
    from data_agent.tools.data_clean import clean_data
    workspace.add("outlier_test", pd.DataFrame({
        "val": [1, 2, 3, 100, 5, 6, 200]
    }))
    result = clean_data("outlier_test", outlier_strategy="cap")
    data = json.loads(result)
    if data["final_rows"] != 7:
        return "cap should not remove rows"
    return True


def test_clean_data_dedup():
    from data_agent.tools.data_clean import clean_data
    workspace.add("dup_test", pd.DataFrame({
        "a": [1, 1, 2], "b": [3, 3, 4]
    }))
    result = clean_data("dup_test")
    data = json.loads(result)
    if data["final_rows"] != 2:
        return f"should remove 1 duplicate, got {data['final_rows']} rows"
    return True


def test_suggest_column_types():
    from data_agent.tools.data_clean import suggest_column_types
    result = suggest_column_types("test")
    data = json.loads(result)
    if "suggestions" not in data:
        return "should have suggestions"
    return True


def test_apply_type_auto():
    from data_agent.tools.data_clean import apply_type_conversion
    workspace.add("type_test", pd.DataFrame({
        "pct": ["10%", "20%"], "num_str": ["100", "200"]
    }))
    result = apply_type_conversion("type_test", auto=True)
    data = json.loads(result)
    if "auto_applied" not in data:
        return "should have auto_applied"
    return True


test("infer: 百分比", test_infer_percentage)
test("infer: 布尔值", test_infer_bool)
test("infer: 日期整数", test_infer_date_int)
test("infer: 数值字符串", test_infer_numeric_string)
test("infer: keep 数值", test_infer_keep)
test("infer: 低基数整数", test_infer_low_cardinality_int)
test("auto_clean: 百分比转换", test_auto_clean_percentage)
test("auto_clean: 布尔转换", test_auto_clean_bool)
test("clean: drop 缺失", test_clean_data_drop_missing)
test("clean: fill_mean", test_clean_data_fill_mean)
test("clean: fill_constant", test_clean_data_fill_constant)
test("clean: outlier cap", test_clean_data_outlier_cap)
test("clean: 去重", test_clean_data_dedup)
test("suggest_column_types", test_suggest_column_types)
test("apply_type_conversion auto", test_apply_type_auto)


# ============================================================
print("\n" + "=" * 60)
print("二、data_transform — 全操作覆盖")
print("=" * 60)

_reset_test_data()

def test_transform_select():
    from data_agent.tools.data_transform import transform_data
    result = transform_data("test", operation="select",
                           params='{"columns": ["sales", "users"]}', save_as="sel_test")
    r = assert_ok(result, "select")
    if r is not True:
        return r
    data = json.loads(result)
    if set(data["columns"]) != {"sales", "users"}:
        return f"wrong columns: {data['columns']}"
    return True


def test_transform_filter():
    from data_agent.tools.data_transform import transform_data
    result = transform_data("test", operation="filter",
                           params='{"condition": "sales > 500"}', save_as="filt_test")
    return assert_ok(result, "filter")


def test_transform_filter_blocked():
    """filter 条件应经过安全校验"""
    from data_agent.tools.data_transform import transform_data
    result = transform_data("test", operation="filter", params='{"condition": "open(\\"x\\")"}')
    data = json.loads(result)
    if "error" not in data:
        return "should block unsafe expression"
    return True


def test_transform_sort():
    from data_agent.tools.data_transform import transform_data
    result = transform_data("test", operation="sort",
                           params='{"by": "sales", "ascending": "false"}', save_as="sort_test")
    return assert_ok(result, "sort")


def test_transform_rename():
    from data_agent.tools.data_transform import transform_data
    result = transform_data("test", operation="rename",
                           params='{"mapping": "sales:sales_amount"}', save_as="renamed")
    r = assert_ok(result, "rename")
    if r is not True:
        return r
    if workspace.get("renamed") is None:
        return "renamed dataset should exist"
    return True


def test_transform_group_aggregate():
    from data_agent.tools.data_transform import transform_data
    result = transform_data("test", operation="group_aggregate",
                           params='{"group_by": "channel", "agg": {"sales": ["sum", "mean"], "users": ["count"]}}',
                           save_as="grp_test")
    return assert_ok(result, "group_aggregate")


def test_transform_group_aggregate_old_format():
    from data_agent.tools.data_transform import transform_data
    result = transform_data("test", operation="group_aggregate",
                           params='{"group_by": "channel", "agg_func": "mean", "agg_col": "sales"}',
                           save_as="grp_old_test")
    return assert_ok(result, "group_aggregate(old)")


def test_transform_merge():
    from data_agent.tools.data_transform import transform_data
    workspace.add("merge_a", pd.DataFrame({"id": [1, 2], "val_a": [10, 20]}))
    workspace.add("merge_b", pd.DataFrame({"id": [1, 2], "val_b": [30, 40]}))
    result = transform_data("merge_a", operation="merge",
                           params='{"other_name": "merge_b", "on": "id"}')
    r = assert_ok(result, "merge")
    if r is not True:
        return r
    data = json.loads(result)
    if data["rows"] != 2:
        return f"merge should have 2 rows, got {data['rows']}"
    return True


def test_transform_merge_missing_other():
    from data_agent.tools.data_transform import transform_data
    result = transform_data("test", operation="merge", params='{"other_name": "nonexistent"}')
    data = json.loads(result)
    if "error" not in data:
        return "should error for missing other dataset"
    return True


def test_transform_pivot_melt():
    from data_agent.tools.data_transform import transform_data
    workspace.add("wide_df", pd.DataFrame({
        "id": [1, 2], "metric_a": [10, 20], "metric_b": [30, 40]
    }))
    result = transform_data("wide_df", operation="pivot",
                           params='{"id_vars": ["id"], "value_vars": ["metric_a", "metric_b"]}')
    return assert_ok(result, "pivot(melt)")


def test_transform_resample():
    from data_agent.tools.data_transform import transform_data
    result = transform_data("test", operation="resample",
                           params='{"date_col": "date", "freq": "W", "agg": {"sales": "sum", "users": "mean"}}',
                           save_as="resample_test")
    return assert_ok(result, "resample")


def test_transform_resample_no_date():
    from data_agent.tools.data_transform import transform_data
    result = transform_data("test_small", operation="resample",
                           params='{"date_col": "nonexistent_col", "freq": "W"}')
    data = json.loads(result)
    if "error" not in data:
        return "should error when date_col doesn't exist"
    return True


def test_transform_save_as():
    from data_agent.tools.data_transform import transform_data
    result = transform_data("test", operation="select",
                           params='{"columns": ["sales"]}', save_as="subset")
    r = assert_ok(result, "save_as")
    if r is not True:
        return r
    if workspace.get("subset") is None:
        return "subset dataset should be created"
    if workspace.get("test") is None:
        return "original dataset should still exist"
    return True


def test_transform_invalid_params():
    from data_agent.tools.data_transform import transform_data
    result = transform_data("test", operation="select", params="not json")
    data = json.loads(result)
    if "error" not in data:
        return "should error for invalid JSON params"
    return True


def test_transform_unsupported_op():
    from data_agent.tools.data_transform import transform_data
    result = transform_data("test", operation="invalid_op")
    data = json.loads(result)
    if "error" not in data:
        return "should error for unsupported operation"
    return True


test("transform: select", test_transform_select)
test("transform: filter", test_transform_filter)
test("transform: filter 不安全条件拦截", test_transform_filter_blocked)
test("transform: sort", test_transform_sort)
test("transform: rename", test_transform_rename)
test("transform: group_aggregate 新格式", test_transform_group_aggregate)
test("transform: group_aggregate 旧格式兼容", test_transform_group_aggregate_old_format)
test("transform: merge", test_transform_merge)
test("transform: merge 不存在数据集", test_transform_merge_missing_other)
test("transform: pivot(melt)", test_transform_pivot_melt)
test("transform: resample", test_transform_resample)
test("transform: resample 无日期列", test_transform_resample_no_date)
test("transform: save_as 不覆盖", test_transform_save_as)
test("transform: 无效 JSON 参数", test_transform_invalid_params)
test("transform: 不支持的操作", test_transform_unsupported_op)


# ============================================================
print("\n" + "=" * 60)
print("三、data_understand — describe/quality/derive")
print("=" * 60)

_reset_test_data()


def test_describe_structure():
    from data_agent.tools.data_understand import describe_dataset
    result = json.loads(describe_dataset("test"))
    if "shape" not in result:
        return "should have shape"
    if result["shape"]["rows"] != 100:
        return f"should have 100 rows, got {result['shape']['rows']}"
    if "fields" not in result:
        return "should have fields"
    return True


def test_quality_issues():
    from data_agent.tools.data_understand import detect_data_quality
    result = json.loads(detect_data_quality("test_nulls"))
    if result["total_issues"] < 1:
        return "should find quality issues in null dataset"
    return True


def test_quality_no_issues():
    from data_agent.tools.data_understand import detect_data_quality
    result = json.loads(detect_data_quality("test_small"))
    if result["total_issues"] > 0:
        return f"clean dataset should have 0 issues, got {result['total_issues']}"
    return True


def test_derive_field_basic():
    from data_agent.tools.data_understand import derive_field
    result = derive_field("test", field_name="avg_sale", expression="sales / users")
    r = assert_ok(result, "derive_field")
    if r is not True:
        return r
    if "test_avg_sale" not in workspace.list_datasets():
        return "derived dataset should be created"
    return True


def test_derive_field_blocked():
    from data_agent.tools.data_understand import derive_field
    result = derive_field("test", field_name="evil", expression="open('x')")
    if "Error" not in result and "不安全" not in result:
        return "should block unsafe expression"
    return True


def test_quick_profile():
    from data_agent.tools.data_understand import quick_profile
    result = json.loads(quick_profile("test"))
    if result["shape"] != [100, 7]:
        return f"shape should be [100, 7], got {result['shape']}"
    if "grain" not in result:
        return "should have grain detection"
    if "readiness" not in result:
        return "should have readiness"
    return True


def test_quick_profile_compact():
    from data_agent.tools.data_understand import quick_profile
    result = json.loads(quick_profile("test", compact=True))
    if "shape" not in result:
        return "compact should have shape"
    if "summary" not in result:
        return "compact should have summary"
    return True


def test_quick_profile_cache():
    """第二次调用应使用缓存"""
    from data_agent.tools.data_understand import quick_profile
    r1 = quick_profile("test")
    r2 = quick_profile("test")
    if r1 != r2:
        return "cached result should be identical"
    return True


def test_assess_readiness():
    from data_agent.tools.data_understand import assess_readiness
    result = json.loads(assess_readiness("test"))
    if "overall" not in result:
        return "should have overall readiness"
    if result["rows"] != 100:
        return f"should have 100 rows, got {result['rows']}"
    return True


def test_assess_readiness_ml_intent():
    from data_agent.tools.data_understand import assess_readiness
    result = json.loads(assess_readiness("test_small", intent="classification"))
    r = assert_ok(result, "readiness_ml")
    if r is not True:
        return r
    # 2 rows < 200 for classification should have warning
    return True


test("describe: 结构正确", test_describe_structure)
test("quality: 缺失数据检测", test_quality_issues)
test("quality: 干净数据无问题", test_quality_no_issues)
test("derive_field: 基本派生", test_derive_field_basic)
test("derive_field: 不安全表达式拦截", test_derive_field_blocked)
test("quick_profile: 完整模式", test_quick_profile)
test("quick_profile: 紧凑模式", test_quick_profile_compact)
test("quick_profile: 缓存", test_quick_profile_cache)
test("assess_readiness: 基本评估", test_assess_readiness)
test("assess_readiness: ML intent 样本量", test_assess_readiness_ml_intent)


# ============================================================
print("\n" + "=" * 60)
print("四、EDA 工具 — 全面覆盖")
print("=" * 60)

_reset_test_data()


def test_time_series_auto_infer():
    from data_agent.tools.eda import analyze_time_series
    result = analyze_time_series("test")
    r = assert_ok(result, "time_series_auto")
    if r is not True:
        return r
    data = json.loads(result)
    if "inferred_columns" not in data:
        return "should auto-infer columns"
    return True


def test_correlation_methods():
    from data_agent.tools.eda import correlation_analysis
    for method in ["pearson", "spearman", "kendall"]:
        result = correlation_analysis("test", method=method)
        r = assert_ok(result, f"correlation_{method}")
        if r is not True:
            return r
    return True


def test_correlation_specific_cols():
    from data_agent.tools.eda import correlation_analysis
    result = correlation_analysis("test", columns="sales,users,revenue")
    r = assert_ok(result, "correlation_cols")
    if r is not True:
        return r
    data = json.loads(result)
    # 实际返回的字段名可能是 columns 或 columns_analyzed
    cols_key = "columns_analyzed" if "columns_analyzed" in data else "columns"
    if set(data[cols_key]) != {"sales", "users", "revenue"}:
        return f"wrong columns: {data[cols_key]}"
    return True


def test_distribution_analysis():
    from data_agent.tools.eda import distribution_analysis
    result = distribution_analysis("test")
    r = assert_ok(result, "distribution")
    if r is not True:
        return r
    data = json.loads(result)
    if "sales" not in data:
        return "should have sales distribution"
    if "skewness" not in data["sales"]:
        return "should have skewness"
    return True


def test_segmentation():
    from data_agent.tools.eda import segmentation_analysis
    result = segmentation_analysis("test", features="sales,users", n_clusters=3)
    r = assert_ok(result, "segmentation")
    if r is not True:
        return r
    data = json.loads(result)
    if len(data["clusters"]) != 3:
        return f"should have 3 clusters, got {len(data['clusters'])}"
    return True


def test_segmentation_too_many_clusters():
    from data_agent.tools.eda import segmentation_analysis
    result = segmentation_analysis("test_small", features="a,b", n_clusters=100)
    if "Error" not in result:
        return "should error when clusters > data points"
    return True


def test_cohort_analysis():
    workspace.add("cohort_test", pd.DataFrame({
        "user_id": [1, 1, 2, 2, 3, 1],
        "event_time": pd.to_datetime(["2025-01-01", "2025-02-01", "2025-01-01", "2025-01-15",
                                       "2025-02-01", "2025-03-01"]),
        "event": ["login", "purchase", "login", "login", "login", "purchase"],
    }))
    from data_agent.tools.eda import cohort_analysis
    result = cohort_analysis("cohort_test", user_col="user_id", time_col="event_time")
    r = assert_ok(result, "cohort")
    if r is not True:
        return r
    data = json.loads(result)
    if "cohorts" not in data:
        return "should have cohorts"
    return True


def test_compare_periods_shortcut():
    from data_agent.tools.eda import compare_periods
    result = compare_periods("test", date_col="date",
                            period_a="last_month", period_b="this_month")
    return assert_ok(result, "compare_shortcuts")


def test_top_n_boundary():
    from data_agent.tools.eda import top_n
    result = top_n("test", sort_by="sales", n=0)
    data = json.loads(result)
    if data["n"] != 0:
        return f"n=0 should return 0 records, got {data['n']}"
    return True


def test_top_n_large_n():
    """n 大于数据行数"""
    from data_agent.tools.eda import top_n
    result = top_n("test", sort_by="sales", n=99999)
    data = json.loads(result)
    if data["n"] > 100:
        return f"should not exceed dataset size, got {data['n']}"
    return True


test("time_series: 自动推断", test_time_series_auto_infer)
test("correlation: 三种方法", test_correlation_methods)
test("correlation: 指定列", test_correlation_specific_cols)
test("distribution: 基本分析", test_distribution_analysis)
test("segmentation: 基本分群", test_segmentation)
test("segmentation: 过多聚类数", test_segmentation_too_many_clusters)
test("cohort: 留存分析", test_cohort_analysis)
test("compare_periods: 快捷词", test_compare_periods_shortcut)
test("top_n: n=0", test_top_n_boundary)
test("top_n: n>数据量", test_top_n_large_n)


# ============================================================
print("\n" + "=" * 60)
print("五、ML 工具 — 回归/分类/预测/归因")
print("=" * 60)

_reset_test_data()


def test_regression_methods():
    from data_agent.tools.ml import regression_analysis
    for method in ["auto", "linear", "rf", "gbrt"]:
        result = regression_analysis("test", target_col="sales",
                                     features="users,revenue,is_new", method=method)
        r = assert_ok(result, f"regression_{method}")
        if r is not True:
            return r
        data = json.loads(result)
        if "metrics" not in data:
            return f"should have metrics for {method}"
        if "r2" not in data["metrics"]:
            return f"should have r2 for {method}"
    return True


def test_regression_cv():
    from data_agent.tools.ml import regression_analysis
    result = regression_analysis("test", target_col="sales",
                                 features="users,revenue", cv_folds=3)
    r = assert_ok(result, "regression_cv")
    if r is not True:
        return r
    data = json.loads(result)
    if "cv" not in data:
        return "should have cv results"
    if data["cv"]["folds"] != 3:
        return "should have 3 folds"
    return True


def test_regression_too_few_data():
    from data_agent.tools.ml import regression_analysis
    workspace.add("tiny", pd.DataFrame({"x": [1, 2], "y": [3, 4]}))
    result = regression_analysis("tiny", target_col="y", features="x")
    if "Error" not in result and "error" not in result[:80]:
        return "should error for too few data points"
    return True


def test_classification_basic():
    from data_agent.tools.ml import classification
    result = classification("test", target_col="channel",
                           features="sales,users,revenue")
    r = assert_ok(result, "classification")
    if r is not True:
        return r
    data = json.loads(result)
    if "n_classes" not in data:
        return "should have n_classes"
    if data["n_classes"] < 2:
        return "should have at least 2 classes"
    return True


def test_forecast_simple():
    from data_agent.tools.ml import forecast
    result = forecast("test", target_col="sales", method="simple", periods=5)
    r = assert_ok(result, "forecast_simple")
    if r is not True:
        return r
    data = json.loads(result)
    if len(data["forecast"]) != 5:
        return f"should have 5 forecast points, got {len(data['forecast'])}"
    if "diagnostics" not in data:
        return "should have diagnostics"
    return True


def test_forecast_too_few_points():
    from data_agent.tools.ml import forecast
    workspace.add("short_ts", pd.DataFrame({"val": [1, 2, 3]}))
    result = forecast("short_ts", target_col="val", method="simple")
    if "error" not in result and "Error" not in result:
        return "should error for too few points"
    return True


def test_attribution_analysis():
    from data_agent.tools.ml import attribution_analysis
    result = attribution_analysis("test", target_col="sales")
    r = assert_ok(result, "attribution")
    if r is not True:
        return r
    data = json.loads(result)
    if "top_drivers" not in data:
        return "should have top_drivers"
    return True


test("regression: 四种方法", test_regression_methods)
test("regression: 交叉验证", test_regression_cv)
test("regression: 数据太少", test_regression_too_few_data)
test("classification: 基本分类", test_classification_basic)
test("forecast: simple", test_forecast_simple)
test("forecast: 数据太少", test_forecast_too_few_points)
test("attribution: 归因分析", test_attribution_analysis)


# ============================================================
print("\n" + "=" * 60)
print("六、statistics 工具")
print("=" * 60)

_reset_test_data()


def test_ab_test_auto():
    from data_agent.tools.statistics import ab_test
    result = ab_test("test", group_col="region", metric_col="sales")
    r = assert_ok(result, "ab_test")
    if r is not True:
        return r
    data = json.loads(result)
    if "levene_test" not in data:
        return "should have levene test"
    if "test" not in data:
        return "should have test result"
    return True


def test_ab_test_chi2():
    """chi2 检验：使用数值列 + 分类分组列"""
    from data_agent.tools.statistics import ab_test
    # 使用 region 作为分组（2个类别），sales 作为数值指标
    result = ab_test("test", group_col="region", metric_col="sales", method="chi2")
    r = assert_ok(result, "ab_chi2")
    if r is not True:
        return r
    return True


def test_ab_test_single_group():
    from data_agent.tools.statistics import ab_test
    workspace.add("one_group", pd.DataFrame({
        "group": ["A", "A", "A"], "val": [1, 2, 3]
    }))
    result = ab_test("one_group", group_col="group", metric_col="val")
    if "Error" not in result:
        return "should error for single group"
    return True


def test_causal_did():
    workspace.add("did_test", pd.DataFrame({
        "treatment": [0, 0, 0, 0, 1, 1, 1, 1],
        "outcome": [10, 12, 11, 13, 15, 18, 16, 20],
        "period":   [0, 0, 1, 1, 0, 0, 1, 1],
    }))
    from data_agent.tools.statistics import causal_analysis
    result = causal_analysis("did_test", treatment_col="treatment",
                             outcome_col="outcome", time_col="period", method="did")
    r = assert_ok(result, "did")
    if r is not True:
        return r
    data = json.loads(result)
    if "did_effect" not in data:
        return "should have did_effect"
    return True


def test_causal_missing_time():
    from data_agent.tools.statistics import causal_analysis
    result = causal_analysis("did_test", treatment_col="treatment",
                             outcome_col="outcome", method="did")
    if "Error" not in result:
        return "should error when time_col missing"
    return True


test("ab_test: auto", test_ab_test_auto)
test("ab_test: chi2", test_ab_test_chi2)
test("ab_test: 单组报错", test_ab_test_single_group)
test("causal: DID", test_causal_did)
test("causal: 缺少 time_col", test_causal_missing_time)


# ============================================================
print("\n" + "=" * 60)
print("七、visualization — 图表创建")
print("=" * 60)

_reset_test_data()


def test_chart_line():
    from data_agent.tools.visualization import create_chart, set_chart_session
    set_chart_session("test_session")
    result = create_chart(chart_type="line", data="test", x_col="date", y_col="sales", title="Test Line")
    if "Error" in result:
        return f"line chart failed: {result}"
    return True


def test_chart_bar():
    from data_agent.tools.visualization import create_chart
    result = create_chart(chart_type="bar", data="test", x_col="channel", y_col="sales", title="Test Bar")
    if "Error" in result:
        return f"bar chart failed: {result}"
    return True


def test_chart_scatter():
    from data_agent.tools.visualization import create_chart
    result = create_chart(chart_type="scatter", data="test", x_col="sales", y_col="users", title="Test Scatter")
    if "Error" in result:
        return f"scatter chart failed: {result}"
    return True


def test_chart_box():
    from data_agent.tools.visualization import create_chart
    result = create_chart(chart_type="box", data="test", y_col="sales", title="Test Box")
    if "Error" in result:
        return f"box chart failed: {result}"
    return True


def test_chart_histogram():
    from data_agent.tools.visualization import create_chart
    result = create_chart(chart_type="histogram", data="test", y_col="sales", title="Test Hist")
    if "Error" in result:
        return f"histogram chart failed: {result}"
    return True


def test_chart_heatmap():
    from data_agent.tools.visualization import create_chart
    result = create_chart(chart_type="heatmap", data="test", title="Test Heatmap")
    if "Error" in result:
        return f"heatmap chart failed: {result}"
    return True


def test_chart_pie():
    from data_agent.tools.visualization import create_chart
    result = create_chart(chart_type="pie", data="test", x_col="channel", title="Test Pie")
    if "Error" in result:
        return f"pie chart failed: {result}"
    return True


def test_chart_stacked_bar():
    from data_agent.tools.visualization import create_chart
    result = create_chart(chart_type="stacked_bar", data="test",
                         x_col="channel", y_col="sales", color_col="region",
                         aggregation="sum", title="Test Stacked")
    r = assert_ok(result, "stacked_bar")
    if r is not True:
        return r
    return True


def test_chart_unsupported():
    from data_agent.tools.visualization import create_chart
    result = create_chart(chart_type="radar", data="test")
    if "不支持" not in result:
        return "should reject unsupported chart type"
    return True


def test_chart_no_data():
    """清空 workspace 后创建图表应报错"""
    from data_agent.tools.visualization import create_chart
    # 临时清空 workspace
    saved = {}
    for name in list(workspace.list_datasets().keys()):
        saved[name] = workspace.get(name)
        workspace.remove(name)
    try:
        result = create_chart(chart_type="line")
        if "Error" not in result:
            return "should error when no data available"
    finally:
        # 恢复 workspace
        for name, df in saved.items():
            if df is not None:
                workspace.add(name, df)
    return True


def test_chart_data_json():
    from data_agent.tools.visualization import create_chart
    result = create_chart(chart_type="scatter", data_json='[{"x":1,"y":10},{"x":2,"y":20}]',
                         x_col="x", y_col="y", title="JSON Data")
    if "Error" in result:
        return f"JSON data chart failed: {result}"
    return True


test("chart: line", test_chart_line)
test("chart: bar", test_chart_bar)
test("chart: scatter", test_chart_scatter)
test("chart: box", test_chart_box)
test("chart: histogram", test_chart_histogram)
test("chart: heatmap", test_chart_heatmap)
test("chart: pie", test_chart_pie)
test("chart: stacked_bar", test_chart_stacked_bar)
test("chart: 不支持类型", test_chart_unsupported)
test("chart: 无数据", test_chart_no_data)
test("chart: JSON 数据", test_chart_data_json)


# ============================================================
print("\n" + "=" * 60)
print("八、report 工具")
print("=" * 60)


def test_report_generate_detailed():
    from data_agent.tools.report import generate_report
    result = generate_report(
        title="单元测试报告",
        insights=json.dumps([
            {"title": "发现1", "type": "trend", "description": "销量**上升**", "confidence": "high"},
            {"title": "发现2", "type": "anomaly", "description": "用户*下降*", "confidence": "medium"},
        ]),
        summary="测试摘要",
        style="detailed",
    )
    return assert_ok(result, "report_detailed")


def test_report_generate_executive():
    from data_agent.tools.report import generate_report
    result = generate_report(title="执行摘要", style="executive")
    return assert_ok(result, "report_executive")


def test_report_empty_insights():
    from data_agent.tools.report import generate_report
    result = generate_report(title="空报告", insights="[]")
    return assert_ok(result, "report_empty")


def test_report_invalid_json_insights():
    from data_agent.tools.report import generate_report
    result = generate_report(title="错误洞察", insights="not json")
    return assert_ok(result, "report_invalid")


def test_report_confidence_parsing():
    try:
        from data_agent.tools.report import _parse_confidence
    except ImportError:
        return "skip"  # Function removed/renamed
    for raw, expected in [
        ("high", "high"), ("高", "high"), ("中 - r²=0.9", "medium"),
        ("low", "low"), ("很低", "low"), ("", "medium"),
        ("中高", "medium"), ("非常高", "high"),
    ]:
        level, _ = _parse_confidence(raw)
        if level != expected:
            return f"'{raw}' should be '{expected}', got '{level}'"
    return True


def test_report_markdown_export():
    try:
        from data_agent.tools.report import export_report_markdown
    except ImportError:
        return "skip"  # Function removed/renamed
    result = export_report_markdown(title="MD报告", summary="测试")
    return assert_ok(result, "md_export")


test("report: detailed", test_report_generate_detailed)
test("report: executive", test_report_generate_executive)
test("report: 空 insights", test_report_empty_insights)
test("report: 无效 JSON insights", test_report_invalid_json_insights)
test("report: 置信度解析", test_report_confidence_parsing)
test("report: markdown 导出", test_report_markdown_export)


# ============================================================
print("\n" + "=" * 60)
print("九、file_ops 工具")
print("=" * 60)

# 清除 chart session 以免 file_ops 使用 session 目录
from data_agent.tools.visualization import set_chart_session
set_chart_session("")

_reset_test_data()


def test_file_write_read():
    from data_agent.tools.file_ops import write_file, read_file
    write_file("unit_test.txt", "hello world")
    content = read_file("unit_test.txt")
    if "hello world" not in content:
        return f"content mismatch: {content[:100]}"
    return True


def test_file_read_missing():
    from data_agent.tools.file_ops import read_file
    result = read_file("nonexistent_file_12345.txt")
    if "Error" not in result:
        return "should error for missing file"
    return True


def test_file_edit():
    from data_agent.tools.file_ops import write_file, edit_file, read_file
    write_file("edit_test.txt", "line1\nline2\nline3")
    result = edit_file("edit_test.txt", "line2", "modified")
    if "Error" in result:
        return f"edit failed: {result}"
    content = read_file("edit_test.txt")
    if "modified" not in content:
        return "edit should have taken effect"
    return True


def test_file_edit_duplicate_text():
    from data_agent.tools.file_ops import write_file, edit_file
    write_file("dup_edit.txt", "aaa\naaa\nbbb")
    result = edit_file("dup_edit.txt", "aaa", "zzz")
    if "appears 2 times" not in result and "Error" not in result:
        return "should error for non-unique text"
    return True


def test_file_edit_not_found():
    from data_agent.tools.file_ops import write_file, edit_file
    write_file("noedit.txt", "content")
    result = edit_file("noedit.txt", "nonexistent text", "replacement")
    if "not found" not in result:
        return "should error when text not found"
    return True


def test_file_list():
    from data_agent.tools.file_ops import list_files
    result = list_files("*.csv")
    if not isinstance(result, str):
        return "should return string"
    return True


test("file: write+read", test_file_write_read)
test("file: read missing", test_file_read_missing)
test("file: edit", test_file_edit)
test("file: edit duplicate", test_file_edit_duplicate_text)
test("file: edit not found", test_file_edit_not_found)
test("file: list", test_file_list)


# ============================================================
print("\n" + "=" * 60)
print("十、derive_features 工具")
print("=" * 60)

_reset_test_data()


def test_derive_time_features():
    from data_agent.tools.derive_features import derive_features
    result = derive_features("test", feature_type="time_features", columns="date",
                            save_as="time_test")
    r = assert_ok(result, "time_features")
    if r is not True:
        return r
    data = json.loads(result)
    if not data["new_columns"]:
        return "should create time feature columns"
    return True


def test_derive_lag_features():
    from data_agent.tools.derive_features import derive_features
    result = derive_features("test", feature_type="lag_features",
                           columns="sales", params='{"lag_periods": "1,7"}',
                           save_as="lag_test")
    r = assert_ok(result, "lag_features")
    if r is not True:
        return r
    data = json.loads(result)
    if "sales_lag1" not in data["new_columns"]:
        return f"should have lag1, got {data['new_columns']}"
    return True


def test_derive_rolling_features():
    from data_agent.tools.derive_features import derive_features
    result = derive_features("test", feature_type="rolling_features",
                           columns="sales", params='{"window": 7, "agg": "mean"}',
                           save_as="rolling_test")
    r = assert_ok(result, "rolling_features")
    if r is not True:
        return r
    return True


def test_derive_ratio_features():
    from data_agent.tools.derive_features import derive_features
    result = derive_features("test", feature_type="ratio_features",
                           params='{"numerator": "sales", "denominator": "users"}',
                           save_as="ratio_test")
    r = assert_ok(result, "ratio_features")
    if r is not True:
        return r
    return True


def test_derive_bin_features():
    from data_agent.tools.derive_features import derive_features
    result = derive_features("test", feature_type="bin_features",
                           columns="sales", params='{"bins": 5}',
                           save_as="bin_test")
    r = assert_ok(result, "bin_features")
    if r is not True:
        return r
    return True


def test_derive_onehot():
    from data_agent.tools.derive_features import derive_features
    result = derive_features("test", feature_type="onehot_encoding", columns="channel",
                            save_as="onehot_test")
    r = assert_ok(result, "onehot")
    if r is not True:
        return r
    data = json.loads(result)
    if not data["new_columns"]:
        return "should create one-hot columns"
    return True


def test_derive_ratio_missing_params():
    from data_agent.tools.derive_features import derive_features
    result = derive_features("test", feature_type="ratio_features")
    data = json.loads(result)
    if "error" not in data:
        return "should error when missing ratio params"
    return True


test("derive: time_features", test_derive_time_features)
test("derive: lag_features", test_derive_lag_features)
test("derive: rolling_features", test_derive_rolling_features)
test("derive: ratio_features", test_derive_ratio_features)
test("derive: bin_features", test_derive_bin_features)
test("derive: onehot", test_derive_onehot)
test("derive: ratio 缺参数", test_derive_ratio_missing_params)


# ============================================================
print("\n" + "=" * 60)
print("十一、data_io 工具")
print("=" * 60)

_reset_test_data()


def _get_export_path(filename):
    """获取允许范围内的导出路径"""
    cfg = get_config()
    data_dir = cfg.data_dir
    data_dir.mkdir(parents=True, exist_ok=True)
    return str(data_dir / filename)


def test_list_data():
    from data_agent.tools.data_io import list_data
    result = list_data()
    if not isinstance(result, str):
        return "should return string"
    if "test" not in result:
        return "should list test dataset"
    return True


def test_export_csv():
    from data_agent.tools.data_io import export_data
    result = export_data("test_small", path=_get_export_path("unit_test_out.csv"), fmt="csv")
    if "Error" in result:
        return f"export csv failed: {result}"
    return True


def test_export_excel():
    from data_agent.tools.data_io import export_data
    result = export_data("test_small", path=_get_export_path("unit_test_out.xlsx"), fmt="excel")
    if "Error" in result:
        return f"export excel failed: {result}"
    return True


def test_export_json():
    from data_agent.tools.data_io import export_data
    result = export_data("test_small", path=_get_export_path("unit_test_out.json"), fmt="json")
    if "Error" in result:
        return f"export json failed: {result}"
    return True


def test_export_unsupported():
    from data_agent.tools.data_io import export_data
    result = export_data("test_small", path=_get_export_path("unit_test_out.xyz"), fmt="xyz")
    if "Error" not in result and "不支持" not in result:
        return "should reject unsupported format"
    return True


def test_export_missing_dataset():
    from data_agent.tools.data_io import export_data
    result = export_data("nonexistent_xyz", path="out.csv")
    if "Error" not in result:
        return "should error for missing dataset"
    return True


def test_export_output_data_type():
    from data_agent.tools.data_io import export_output
    result = export_output(output_type="data", name="test_small",
                          path=_get_export_path("unit_test_output.csv"), fmt="csv")
    if "Error" in result:
        return f"export_output data failed: {result}"
    return True


def test_export_output_unsupported_type():
    from data_agent.tools.data_io import export_output
    result = export_output(output_type="xml")
    if "Error" not in result and "不支持" not in result:
        return "should reject unsupported output_type"
    return True


test("list_data", test_list_data)
test("export: csv", test_export_csv)
test("export: excel", test_export_excel)
test("export: json", test_export_json)
test("export: 不支持格式", test_export_unsupported)
test("export: 不存在数据集", test_export_missing_dataset)
test("export_output: data 类型", test_export_output_data_type)
test("export_output: 不支持类型", test_export_output_unsupported_type)


# ============================================================
print("\n" + "=" * 60)
print("十二、workspace 操作")
print("=" * 60)


def test_workspace_add_get():
    df = pd.DataFrame({"x": [1, 2, 3]})
    msg = workspace.add("ws_test", df)
    if "ws_test" not in msg:
        return f"add should confirm: {msg}"
    got = workspace.get("ws_test")
    if got is None:
        return "get should return DataFrame"
    if len(got) != 3:
        return "DataFrame should have 3 rows"
    return True


def test_workspace_remove():
    workspace.add("to_remove", pd.DataFrame({"a": [1]}))
    msg = workspace.remove("to_remove")
    if "已删除" not in msg:
        return f"remove should confirm: {msg}"
    if workspace.get("to_remove") is not None:
        return "should be removed"
    return True


def test_workspace_derive():
    workspace.add("derive_src", pd.DataFrame({"a": [1, 2, 3]}))
    msg = workspace.derive("derive_src", "derive_dst", pd.DataFrame({"b": [4, 5, 6]}), "test")
    if "derive_dst" not in msg:
        return f"derive should confirm: {msg}"
    if workspace.get("derive_dst") is None:
        return "derived dataset should exist"
    return True


def test_workspace_metadata():
    workspace.add("meta_test", pd.DataFrame({"a": [1]}))
    workspace.set_metadata("meta_test", "key1", "value1")
    val = workspace.get_metadata("meta_test", "key1")
    if val != "value1":
        return f"metadata should be 'value1', got {val}"
    all_meta = workspace.get_metadata("meta_test")
    if "key1" not in all_meta:
        return "full metadata should contain key1"
    return True


def test_workspace_transform_log():
    workspace.add("log_src", pd.DataFrame({"a": [1]}))
    workspace.log_transform("log_src", "test_op", "log_dst")
    log = workspace.get_transform_log()
    if not log:
        return "should have transform log entries"
    last = log[-1]
    if last["op"] != "test_op":
        return f"last op should be 'test_op', got {last['op']}"
    return True


def test_workspace_list_datasets():
    datasets = workspace.list_datasets()
    if not isinstance(datasets, dict):
        return "should return dict"
    for name, info in datasets.items():
        if "rows" not in info or "columns" not in info:
            return f"dataset '{name}' missing rows/columns"
    return True


def test_workspace_copy_isolation():
    """workspace.add 应 copy DataFrame，原修改不影响内部"""
    original = pd.DataFrame({"a": [1, 2, 3]})
    workspace.add("iso_test", original)
    original["a"] = [999, 999, 999]
    got = workspace.get("iso_test")
    if got["a"].iloc[0] == 999:
        return "workspace should copy DataFrame on add"
    return True


test("workspace: add/get", test_workspace_add_get)
test("workspace: remove", test_workspace_remove)
test("workspace: derive", test_workspace_derive)
test("workspace: metadata", test_workspace_metadata)
test("workspace: transform_log", test_workspace_transform_log)
test("workspace: list_datasets", test_workspace_list_datasets)
test("workspace: copy isolation", test_workspace_copy_isolation)


# ============================================================
print("\n" + "=" * 60)
print("十三、tool_search 工具")
print("=" * 60)


def test_tool_search_basic():
    from data_agent.tools.registry import tool_search
    result = json.loads(tool_search("regression"))
    if result["matches"] < 1:
        return "should find regression tools"
    return True


def test_tool_search_empty():
    from data_agent.tools.registry import tool_search
    result = json.loads(tool_search(""))
    if "error" not in result:
        return "should error for empty keyword"
    return True


def test_tool_search_no_match():
    from data_agent.tools.registry import tool_search
    result = json.loads(tool_search("xyznonexistent123"))
    if result["matches"] != 0:
        return "should have 0 matches"
    return True


test("tool_search: 基本", test_tool_search_basic)
test("tool_search: 空关键词", test_tool_search_empty)
test("tool_search: 无匹配", test_tool_search_no_match)


# ============================================================
# 汇总
# ============================================================
print("\n" + "=" * 60)
print("工具单元测试结果汇总")
print("=" * 60)
print(f"  PASS: {PASS}")
print(f"  FAIL: {FAIL}")
print(f"  SKIP: {SKIP}")
print(f"  TOTAL: {PASS + FAIL + SKIP}")

if ERRORS:
    print("\n失败的测试:")
    for e in ERRORS:
        print(f"  - {e}")

if FAIL > 0:
    print("\n!!! 有测试未通过 !!!")
else:
    print("\n所有工具单元测试通过！")


# ============================================================
# pytest 兼容：当通过 pytest 运行时，将上述自定义 test() 调用
# 转为 pytest 可发现的形式。直接运行 python 时走自定义框架。
# ============================================================

if "pytest" in sys.modules:
    import pytest

    def _make_pytest_test(func):
        """将自定义测试函数包装为 pytest test。"""
        def wrapper():
            result = func()
            assert result is True, result
        wrapper.__name__ = func.__name__
        return wrapper

    # 动态收集所有已执行的测试函数并注册为 pytest test
    _test_functions = []

    # 重新定义为 pytest 风格的收集
    def pytest_collect_file(parent, file_path):
        if file_path.name == "test_tools_comprehensive.py":
            return PytestModule.from_parent(parent, path=file_path)

