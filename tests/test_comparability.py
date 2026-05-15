#!/usr/bin/env python3
"""验证时间对比可比性功能的测试。

覆盖：
1. analyze_period_structure — 时段结构分析
2. compare_period_structures — 时段结构可比性评估
3. compare_periods — 日均值输出和可比性警告
4. contribute_decomposition — 日均值归一化

运行: python tests/test_comparability.py
"""

import json
import os
import sys

if sys.platform == "win32":
    os.system("")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PASS = 0
FAIL = 0
ERRORS = []


def _test(name, func):
    global PASS, FAIL
    print(f"  {name}...", end=" ", flush=True)
    try:
        result = func()
        if result is True:
            PASS += 1
            print("PASS")
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


# ── 初始化 ────────────────────────────────────────────────
print("=" * 60)
print("初始化")
print("=" * 60)

from data_agent.config import get_config
from data_agent.tools import discover_tools
discover_tools()

import numpy as np
import pandas as pd
import pandas as pd
from data_agent.session.workspace import workspace
from data_agent.tools._utils import analyze_period_structure, compare_period_structures


def _reset_test_data():
    """创建并注册测试数据集。"""
    np.random.seed(42)
    n = 30
    df = pd.DataFrame({
        "date": pd.date_range("2025-09-28", periods=n, freq="D"),
        "revenue": np.random.uniform(1000, 5000, n).round(2),
        "dau": np.random.randint(5000, 20000, n),
        "channel": np.random.choice(["organic", "paid"], n),
    })
    workspace.add("test", df)


# ── analyze_period_structure 测试 ─────────────────────────
print("\n--- analyze_period_structure ---")


def test_7day_period():
    """7天时段：应包含5个工作日和2个周末日。"""
    # 2025-10-06 (Mon) ~ 2025-10-12 (Sun)
    struct = analyze_period_structure(
        pd.Timestamp("2025-10-06"), pd.Timestamp("2025-10-12")
    )
    assert struct["day_count"] == 7, f"day_count should be 7, got {struct['day_count']}"
    assert struct["weekday_count"] == 5, f"weekday_count should be 5, got {struct['weekday_count']}"
    assert struct["weekend_count"] == 2, f"weekend_count should be 2, got {struct['weekend_count']}"
    assert len(struct["dates"]) == 7, f"dates should have 7 entries"
    assert struct["dates"][0]["dow"] == "Monday"
    assert struct["dates"][6]["dow"] == "Sunday"
    assert struct["dates"][5]["is_weekend"] is True  # Saturday
    return True


_test("7天时段结构", test_7day_period)


def test_3day_period():
    """3天时段：应正确计算天数和日期列表。"""
    # 2025-09-28 (Sun) ~ 2025-09-30 (Tue)
    struct = analyze_period_structure(
        pd.Timestamp("2025-09-28"), pd.Timestamp("2025-09-30")
    )
    assert struct["day_count"] == 3, f"day_count should be 3, got {struct['day_count']}"
    assert struct["weekend_count"] == 1, f"weekend_count should be 1, got {struct['weekend_count']}"
    assert struct["dates"][0]["dow"] == "Sunday"
    assert struct["dates"][2]["dow"] == "Tuesday"
    return True


_test("3天时段结构", test_3day_period)


def test_single_day():
    """单天时段。"""
    struct = analyze_period_structure(
        pd.Timestamp("2025-10-01"), pd.Timestamp("2025-10-01")
    )
    assert struct["day_count"] == 1, f"day_count should be 1, got {struct['day_count']}"
    assert "dates" in struct
    return True


_test("单天时段结构", test_single_day)


def test_long_period_omits_dates():
    """超过31天的时段应省略逐日列表。"""
    struct = analyze_period_structure(
        pd.Timestamp("2025-01-01"), pd.Timestamp("2025-12-31")
    )
    assert struct["day_count"] == 365
    assert "dates" not in struct, "dates should be omitted for periods > 31 days"
    assert "dates_note" in struct
    return True


_test("长期时段省略逐日列表", test_long_period_omits_dates)


# ── compare_period_structures 测试 ────────────────────────
print("\n--- compare_period_structures ---")


def test_equal_lengths():
    """等长时段应标记 lengths_equal=True，无警告。"""
    sa = analyze_period_structure(pd.Timestamp("2025-10-06"), pd.Timestamp("2025-10-12"))
    sb = analyze_period_structure(pd.Timestamp("2025-10-13"), pd.Timestamp("2025-10-19"))
    comp = compare_period_structures(sa, sb)
    assert comp["lengths_equal"] is True, "lengths should be equal"
    assert comp["daily_avg_recommended"] is False, "daily_avg should not be recommended"
    assert len(comp["warnings"]) == 0, f"should have no warnings, got {comp['warnings']}"
    return True


_test("等长时段无可比性警告", test_equal_lengths)


def test_different_lengths():
    """不等长时段应有警告并推荐日均值。"""
    sa = analyze_period_structure(pd.Timestamp("2025-09-28"), pd.Timestamp("2025-09-30"))
    sb = analyze_period_structure(pd.Timestamp("2025-10-01"), pd.Timestamp("2025-10-07"))
    comp = compare_period_structures(sa, sb)
    assert comp["lengths_equal"] is False, "lengths should not be equal"
    assert comp["daily_avg_recommended"] is True, "daily_avg should be recommended"
    assert len(comp["warnings"]) >= 1, "should have at least 1 warning"
    assert "3 days" in comp["warnings"][0] and "7 days" in comp["warnings"][0]
    return True


_test("不等长时段产生警告", test_different_lengths)


def test_same_length_diff_composition():
    """等长但星期构成不同的时段应有结构偏差警告。"""
    # Mon-Wed (3 weekday, 0 weekend)
    sa = analyze_period_structure(pd.Timestamp("2025-10-06"), pd.Timestamp("2025-10-08"))
    # Fri-Sun (1 weekday, 2 weekend)
    sb = analyze_period_structure(pd.Timestamp("2025-10-10"), pd.Timestamp("2025-10-12"))
    comp = compare_period_structures(sa, sb)
    assert comp["lengths_equal"] is True, "lengths should be equal"
    assert comp["weekday_ratio_diff"] > 0.1, f"should detect composition diff, got {comp['weekday_ratio_diff']}"
    assert any("ratio" in w for w in comp["warnings"]), "should warn about composition"
    return True


_test("等长不同星期构成产生警告", test_same_length_diff_composition)


# ── compare_periods 工具测试 ──────────────────────────────
print("\n--- compare_periods 工具 ---")


def test_compare_periods_daily_avg():
    """3天 vs 7天对比应输出日均值和可比性警告。"""
    _reset_test_data()
    from data_agent.tools.eda import compare_periods

    result_str = compare_periods(
        "test",
        date_col="date",
        metrics="revenue,dau",
        period_a="2025-09-28~2025-09-30",
        period_b="2025-10-01~2025-10-07",
    )
    result = json.loads(result_str)

    # 基本结构检查
    assert "comparability" in result, "should have comparability block"
    assert result["period_a"]["day_count"] == 3, f"period_a day_count should be 3"
    assert result["period_b"]["day_count"] == 7, f"period_b day_count should be 7"
    assert "dates" in result["period_a"], "period_a should have dates"
    assert "dates" in result["period_b"], "period_b should have dates"

    # 可比性警告
    assert len(result["comparability"]["warnings"]) >= 1, "should have comparability warnings"
    assert result["comparability"]["daily_avg_recommended"] is True

    # 日均值字段
    for col in ["revenue", "dau"]:
        m = result["metrics"][col]
        assert "daily_avg_a" in m, f"{col} should have daily_avg_a"
        assert "daily_avg_b" in m, f"{col} should have daily_avg_b"
        assert "daily_avg_diff" in m, f"{col} should have daily_avg_diff"
        assert "daily_avg_change_pct" in m, f"{col} should have daily_avg_change_pct"

        # 日均值计算正确性
        expected_da = m["period_a"] / 3
        expected_db = m["period_b"] / 7
        assert abs(m["daily_avg_a"] - expected_da) < 0.01, f"{col} daily_avg_a mismatch"
        assert abs(m["daily_avg_b"] - expected_db) < 0.01, f"{col} daily_avg_b mismatch"

    return True


_test("3天 vs 7天对比输出日均值", test_compare_periods_daily_avg)


def test_compare_periods_equal_lengths():
    """等长时段对比应有日均值但标记不需要特别关注。"""
    _reset_test_data()
    from data_agent.tools.eda import compare_periods

    result_str = compare_periods(
        "test",
        date_col="date",
        metrics="revenue",
        period_a="2025-09-28~2025-10-04",
        period_b="2025-10-05~2025-10-11",
    )
    result = json.loads(result_str)

    assert result["comparability"]["lengths_equal"] is True
    assert result["comparability"]["daily_avg_recommended"] is False
    # 等长时日均值仍然输出
    assert "daily_avg_a" in result["metrics"]["revenue"]
    return True


_test("等长时段对比结构正确", test_compare_periods_equal_lengths)


def test_compare_periods_dimension_path():
    """dimension 分组路径也应有日均值。"""
    _reset_test_data()
    from data_agent.tools.eda import compare_periods

    result_str = compare_periods(
        "test",
        date_col="date",
        metrics="revenue",
        period_a="2025-09-28~2025-09-30",
        period_b="2025-10-01~2025-10-07",
        dimensions="channel",
    )
    result = json.loads(result_str)

    assert "comparability" in result
    assert result["period_a"]["day_count"] == 3
    assert result["period_b"]["day_count"] == 7

    for comp_row in result["comparisons"]:
        assert "daily_avg_a" in comp_row["revenue"], "dimension path should have daily_avg_a"
        assert "daily_avg_b" in comp_row["revenue"], "dimension path should have daily_avg_b"

    return True


_test("dimension 分组路径包含日均值", test_compare_periods_dimension_path)


# ── contribute_decomposition 测试 ─────────────────────────
print("\n--- contribute_decomposition ---")


def test_contribute_daily_normalized():
    """不等时段的贡献度分解应包含 daily_normalized 块。"""
    _reset_test_data()
    from data_agent.tools.eda import contribute_decomposition

    result = contribute_decomposition(
        "test",
        metric="revenue",
        dimension="channel",
        date_col="date",
        period_a="2025-09-28~2025-09-30",
        period_b="2025-10-01~2025-10-07",
        agg_func="sum",
    )

    data = result.data if hasattr(result, "data") else json.loads(str(result))

    assert "comparability" in data, "should have comparability"
    assert data["comparability"]["daily_avg_recommended"] is True
    assert "daily_normalized" in data, "should have daily_normalized block"
    assert "daily_avg_a" in data["daily_normalized"]
    assert "daily_avg_b" in data["daily_normalized"]

    # 时段结构
    assert data["period_a"]["day_count"] == 3
    assert data["period_b"]["day_count"] == 7

    # CLI summary 应包含可比性警告
    if hasattr(result, "summary"):
        assert "可比性" in result.summary, "summary should mention comparability"

    return True


_test("不等时段贡献度分解含 daily_normalized", test_contribute_daily_normalized)


def test_contribute_equal_lengths():
    """等时段贡献度分解不应有 daily_normalized。"""
    _reset_test_data()
    from data_agent.tools.eda import contribute_decomposition

    result = contribute_decomposition(
        "test",
        metric="revenue",
        dimension="channel",
        date_col="date",
        period_a="2025-09-28~2025-10-04",
        period_b="2025-10-05~2025-10-11",
        agg_func="sum",
    )

    data = result.data if hasattr(result, "data") else json.loads(str(result))

    assert "comparability" in data
    assert data["comparability"]["lengths_equal"] is True
    assert "daily_normalized" not in data, "equal lengths should not have daily_normalized"

    return True


_test("等时段贡献度分解无 daily_normalized", test_contribute_equal_lengths)


# ── 向后兼容性测试 ────────────────────────────────────────
print("\n--- 向后兼容性 ---")


def test_backward_compat_existing_keys():
    """旧代码依赖的 key 仍然存在。"""
    _reset_test_data()
    from data_agent.tools.eda import compare_periods

    result_str = compare_periods(
        "test",
        date_col="date",
        metrics="revenue",
        period_a="2025-09-28~2025-09-30",
        period_b="2025-10-01~2025-10-07",
    )
    result = json.loads(result_str)

    # 旧字段仍在
    assert "period_a" in result
    assert "period_b" in result
    assert "label" in result["period_a"]
    assert "range" in result["period_a"]
    assert "rows" in result["period_a"]
    assert "metrics" in result
    assert "period_a" in result["metrics"]["revenue"]
    assert "period_b" in result["metrics"]["revenue"]
    assert "diff" in result["metrics"]["revenue"]
    assert "change_pct" in result["metrics"]["revenue"]

    return True


_test("旧字段向后兼容", test_backward_compat_existing_keys)


# ── 结果汇总 ──────────────────────────────────────────────
print("\n" + "=" * 60)
print(f"结果: {PASS} PASS, {FAIL} FAIL")
if ERRORS:
    print("\n失败详情:")
    for e in ERRORS:
        print(f"  {e}")
print("=" * 60)

sys.exit(0 if FAIL == 0 else 1)
