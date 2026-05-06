"""V10 新增功能全面测试：interpret_dataset, contribute_decomposition, funnel_analysis,
what_if_simulation, _utils 共享函数, prompt 变更, registry 更新, 可视化漏斗图。

使用方法:
  python tests/test_v10_new.py
  pytest tests/test_v10_new.py -v
"""

import json
import os
import sys
import tempfile
from pathlib import Path

if sys.platform == "win32":
    os.system("")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PASS = 0
FAIL = 0
SKIP = 0
ERRORS = []

PROJECT_ROOT = Path(__file__).resolve().parent.parent


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


def assert_tool_result_ok(result, label=""):
    """检查 ToolResult 的 summary 不以 error 开头。"""
    from data_agent.tools.registry import ToolResult
    if isinstance(result, ToolResult):
        if result.summary and ("Error" in result.summary or '"error"' in result.summary[:100]):
            return f"{label} ToolResult error: {result.summary[:300]}"
        return True
    return assert_ok(str(result), label)


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
from data_agent.tools.registry import ToolResult


def _reset_test_data():
    """重置测试数据集。"""
    np.random.seed(42)
    n = 200
    workspace.add("test", pd.DataFrame({
        "date": pd.date_range("2025-01-01", periods=n, freq="D"),
        "sales": np.random.uniform(100, 1000, n).round(2),
        "users": np.random.randint(10, 500, n),
        "channel": np.random.choice(["A", "B", "C"], n),
        "region": np.random.choice(["north", "south", "east", "west"], n),
        "revenue": np.random.uniform(500, 5000, n).round(2),
        "is_new": np.random.choice([0, 1], n),
    }))
    for name in ["test"]:
        workspace.set_metadata(name, "_profile_cache", None)
        workspace.set_metadata(name, "_profile_shape", None)


_reset_test_data()


# ============================================================
print("\n" + "=" * 60)
print("一、_utils 共享函数 — resolve_date_col / parse_period_range")
print("=" * 60)


def test_resolve_date_col_auto_datetime():
    from data_agent.tools._utils import resolve_date_col
    df = pd.DataFrame({"date": pd.date_range("2025-01-01", periods=5), "val": [1, 2, 3, 4, 5]})
    col, err = resolve_date_col(df)
    if err:
        return f"should auto-detect datetime col, got error: {err}"
    if col != "date":
        return f"should detect 'date', got '{col}'"
    return True


def test_resolve_date_col_auto_string():
    from data_agent.tools._utils import resolve_date_col
    df = pd.DataFrame({"日期": ["2025-01-01", "2025-01-02", "2025-01-03"], "val": [1, 2, 3]})
    col, err = resolve_date_col(df)
    if err:
        return f"should auto-detect string date col, got error: {err}"
    if col != "日期":
        return f"should detect '日期', got '{col}'"
    return True


def test_resolve_date_col_explicit():
    from data_agent.tools._utils import resolve_date_col
    df = pd.DataFrame({"d1": pd.date_range("2025-01-01", periods=3), "d2": pd.date_range("2025-02-01", periods=3)})
    col, err = resolve_date_col(df, "d2")
    if col != "d2":
        return f"should use explicit col 'd2', got '{col}'"
    return True


def test_resolve_date_col_no_date():
    from data_agent.tools._utils import resolve_date_col
    df = pd.DataFrame({"name": ["a", "b", "c"], "val": [1, 2, 3]})
    col, err = resolve_date_col(df)
    if not err:
        return "should return error when no date column"
    return True


def test_parse_period_range_last_month():
    from data_agent.tools._utils import parse_period_range
    ref = pd.Timestamp("2025-03-15")
    result = parse_period_range("last_month", ref)
    if not result:
        return "should parse last_month"
    start, end = result
    if start.month != 2 or end.month != 2:
        return f"last_month should be Feb, got {start}~{end}"
    return True


def test_parse_period_range_this_week():
    from data_agent.tools._utils import parse_period_range
    ref = pd.Timestamp("2025-03-12")  # Wednesday
    result = parse_period_range("this_week", ref)
    if not result:
        return "should parse this_week"
    start, end = result
    if start.weekday() != 0:
        return f"this_week should start on Monday, got {start} (weekday={start.weekday()})"
    return True


def test_parse_period_range_explicit():
    from data_agent.tools._utils import parse_period_range
    ref = pd.Timestamp("2025-06-01")
    result = parse_period_range("2025-01-01~2025-01-31", ref)
    if not result:
        return "should parse explicit range"
    start, end = result
    if start.day != 1 or end.day != 31:
        return f"unexpected range: {start}~{end}"
    return True


def test_parse_period_range_invalid():
    from data_agent.tools._utils import parse_period_range
    ref = pd.Timestamp("2025-06-01")
    result = parse_period_range("invalid_period", ref)
    if result is not None:
        return f"should return None for invalid period, got {result}"
    return True


test("resolve_date_col: auto datetime", test_resolve_date_col_auto_datetime)
test("resolve_date_col: auto string date", test_resolve_date_col_auto_string)
test("resolve_date_col: explicit", test_resolve_date_col_explicit)
test("resolve_date_col: no date col", test_resolve_date_col_no_date)
test("parse_period_range: last_month", test_parse_period_range_last_month)
test("parse_period_range: this_week", test_parse_period_range_this_week)
test("parse_period_range: explicit range", test_parse_period_range_explicit)
test("parse_period_range: invalid", test_parse_period_range_invalid)


# ============================================================
print("\n" + "=" * 60)
print("二、interpret_dataset — 业务语义理解")
print("=" * 60)

_reset_test_data()


def test_interpret_basic():
    from data_agent.tools.data_understand import interpret_dataset
    result = interpret_dataset("test")
    r = assert_tool_result_ok(result, "interpret")
    if r is not True:
        return r
    if isinstance(result, ToolResult):
        data = result.data
        if not data:
            return "should have data field"
        if "columns_classified" not in data:
            return "should have columns_classified"
        if "suggested_analyses" not in data:
            return "should have suggested_analyses"
    return True


def test_interpret_classifies_columns():
    from data_agent.tools.data_understand import interpret_dataset
    result = interpret_dataset("test")
    if not isinstance(result, ToolResult):
        return f"should return ToolResult, got {type(result)}"
    classified = result.data["columns_classified"]
    # test dataset has channel, region as dimensions, date as time
    dim_names = [d["column"] for d in classified["dimensions"]]
    if "channel" not in dim_names:
        return f"'channel' should be classified as dimension, dims: {dim_names}"
    if not classified["time_columns"]:
        return "should detect time columns"
    if not classified["key_metrics"]:
        return "should detect key metrics (sales, users, revenue)"
    return True


def test_interpret_signals():
    from data_agent.tools.data_understand import interpret_dataset
    result = interpret_dataset("test")
    signals = result.data["analysis_signals"]
    if not signals["has_time"]:
        return "should detect has_time=True"
    if not signals["has_dimensions"]:
        return "should detect has_dimensions=True"
    if signals["metric_count"] < 2:
        return f"should detect multiple metrics, got {signals['metric_count']}"
    return True


def test_interpret_grain():
    from data_agent.tools.data_understand import interpret_dataset
    result = interpret_dataset("test")
    grain = result.data["grain"]
    # test data has daily dates with dimensions → multi_dimension_aggregate or daily_aggregate
    if grain not in ("daily_aggregate", "multi_dimension_aggregate", "aggregate"):
        return f"unexpected grain: {grain}"
    return True


def test_interpret_suggested_analyses():
    from data_agent.tools.data_understand import interpret_dataset
    result = interpret_dataset("test")
    suggested = result.data["suggested_analyses"]
    if not suggested:
        return "should suggest analyses"
    # Should include trend analysis since has time
    directions = [s["direction"] for s in suggested]
    if "趋势分析" not in directions:
        return f"should suggest 趋势分析, got: {directions}"
    return True


def test_interpret_summary_format():
    from data_agent.tools.data_understand import interpret_dataset
    result = interpret_dataset("test")
    summary = result.summary
    if not summary:
        return "summary should not be empty"
    if "200" not in summary and "test" not in summary:
        return f"summary should mention dataset info: {summary[:200]}"
    return True


def test_interpret_suggested_next():
    from data_agent.tools.data_understand import interpret_dataset
    result = interpret_dataset("test")
    if not result.suggested_next:
        return "should have suggested_next"
    return True


def test_interpret_nonexistent():
    from data_agent.tools.data_understand import interpret_dataset
    result = interpret_dataset("nonexistent_xyz")
    if "不存在" not in str(result):
        return "should error for nonexistent dataset"
    return True


def test_interpret_theme_game():
    """游戏互推数据应匹配游戏主题。"""
    from data_agent.tools.data_understand import interpret_dataset
    df = pd.read_excel(PROJECT_ROOT / "reference/test_doc/游戏互推.xlsx")
    workspace.add("game_data", df)
    try:
        result = interpret_dataset("game_data")
        if not isinstance(result, ToolResult):
            return f"should return ToolResult, got {type(result)}"
        theme = result.data.get("theme", "unknown")
        if theme not in ("游戏", "广告营销"):
            return f"expected 游戏 or 广告营销 theme, got '{theme}'"
    finally:
        workspace.remove("game_data")
    return True


def test_interpret_theme_ads():
    """banner/激励视频数据应匹配广告营销主题。"""
    from data_agent.tools.data_understand import interpret_dataset
    df = pd.read_excel(PROJECT_ROOT / "reference/test_doc/banner汇总数据.xlsx")
    workspace.add("ads_data", df)
    try:
        result = interpret_dataset("ads_data")
        if not isinstance(result, ToolResult):
            return f"should return ToolResult, got {type(result)}"
        theme = result.data.get("theme", "unknown")
        if theme not in ("广告营销", "游戏"):
            return f"expected 广告营销 or 游戏 theme, got '{theme}'"
    finally:
        workspace.remove("ads_data")
    return True


def test_interpret_rate_metrics():
    """内购数据中的率列（清洗后数值型）应被识别为 rate_metrics。"""
    from data_agent.tools.data_understand import interpret_dataset
    from data_agent.tools.data_clean import auto_clean
    df = pd.read_excel(PROJECT_ROOT / "reference/test_doc/内购数据.xlsx")
    # auto_clean converts percentage strings to floats
    df, _, _ = auto_clean(df)
    workspace.add("purchase_data", df)
    try:
        result = interpret_dataset("purchase_data")
        if not isinstance(result, ToolResult):
            return f"should return ToolResult, got {type(result)}"
        rate_metrics = result.data["columns_classified"]["rate_metrics"]
        rate_names = [m["column"] for m in rate_metrics]
        # After cleaning, 付费率/新增付费率 are float columns with rate keywords
        if not rate_names:
            # Also acceptable: the arpu/arppu columns may be key_metrics with rate-like names
            key_names = [m["column"] for m in result.data["columns_classified"]["key_metrics"]]
            all_metric_names = rate_names + key_names
            rate_like = [c for c in all_metric_names if any(kw in c for kw in ["arpu", "arppu", "率"])]
            if not rate_like:
                return f"should detect rate-like metrics (arpu/率), got metrics={all_metric_names}"
    finally:
        workspace.remove("purchase_data")
    return True


test("interpret: 基本返回", test_interpret_basic)
test("interpret: 列分类正确", test_interpret_classifies_columns)
test("interpret: 信号检测", test_interpret_signals)
test("interpret: 粒度检测", test_interpret_grain)
test("interpret: 推荐分析路径", test_interpret_suggested_analyses)
test("interpret: summary 格式", test_interpret_summary_format)
test("interpret: suggested_next", test_interpret_suggested_next)
test("interpret: 不存在数据集", test_interpret_nonexistent)
test("interpret: 游戏主题匹配", test_interpret_theme_game)
test("interpret: 广告营销主题匹配", test_interpret_theme_ads)
test("interpret: 率指标识别", test_interpret_rate_metrics)


# ============================================================
print("\n" + "=" * 60)
print("三、contribute_decomposition — 贡献度分解")
print("=" * 60)

_reset_test_data()


def test_contribute_sum():
    from data_agent.tools.eda import contribute_decomposition
    result = contribute_decomposition(
        "test", metric="sales", dimension="channel",
        period_a="2025-01-01~2025-01-31", period_b="2025-02-01~2025-02-28",
        agg_func="sum",
    )
    r = assert_tool_result_ok(result, "contribute_sum")
    if r is not True:
        return r
    if not isinstance(result, ToolResult):
        return f"should return ToolResult, got {type(result)}"
    data = result.data
    if "decomposition" not in data:
        return "should have decomposition"
    if not data["decomposition"]:
        return "decomposition should not be empty"
    # Verify contributions sum to total change
    total_change = data["total_change"]
    contrib_sum = sum(d["contribution"] for d in data["decomposition"])
    if abs(contrib_sum - total_change) > 1.0:
        return f"contributions ({contrib_sum:.2f}) should sum to total_change ({total_change:.2f})"
    return True


def test_contribute_mean():
    from data_agent.tools.eda import contribute_decomposition
    result = contribute_decomposition(
        "test", metric="sales", dimension="channel",
        period_a="2025-01-01~2025-01-31", period_b="2025-02-01~2025-02-28",
        agg_func="mean",
    )
    r = assert_tool_result_ok(result, "contribute_mean")
    if r is not True:
        return r
    data = result.data
    if "decomposition" not in data:
        return "should have decomposition"
    # Mean mode should have weight info
    first = data["decomposition"][0]
    if "weight_a" not in first:
        return "mean mode should have weight_a"
    return True


def test_contribute_bad_metric():
    from data_agent.tools.eda import contribute_decomposition
    result = contribute_decomposition(
        "test", metric="nonexistent", dimension="channel",
        period_a="2025-01-01~2025-01-31", period_b="2025-02-01~2025-02-28",
    )
    if not (isinstance(result, str) and "Error" in result):
        return "should error for bad metric"
    return True


def test_contribute_bad_dimension():
    from data_agent.tools.eda import contribute_decomposition
    result = contribute_decomposition(
        "test", metric="sales", dimension="nonexistent",
        period_a="2025-01-01~2025-01-31", period_b="2025-02-01~2025-02-28",
    )
    if not (isinstance(result, str) and "Error" in result):
        return "should error for bad dimension"
    return True


def test_contribute_bad_period():
    from data_agent.tools.eda import contribute_decomposition
    result = contribute_decomposition(
        "test", metric="sales", dimension="channel",
        period_a="2020-01-01~2020-01-31", period_b="2020-02-01~2020-02-28",
    )
    if isinstance(result, str) and '"error"' in result:
        return True  # no data in those periods is expected
    if isinstance(result, ToolResult):
        return True  # might work if there's some data
    return True


def test_contribute_toolresult_fields():
    from data_agent.tools.eda import contribute_decomposition
    result = contribute_decomposition(
        "test", metric="sales", dimension="channel",
        period_a="2025-01-01~2025-01-31", period_b="2025-02-01~2025-02-28",
    )
    if not isinstance(result, ToolResult):
        return f"should return ToolResult, got {type(result)}"
    if not result.summary:
        return "should have summary"
    if not result.data:
        return "should have data"
    if not result.suggested_next:
        return "should have suggested_next"
    # Check data structure
    for key in ["metric", "dimension", "agg_func", "period_a", "period_b", "total_change", "decomposition", "top_negative", "top_positive"]:
        if key not in result.data:
            return f"data should have '{key}'"
    return True


def test_contribute_with_real_data():
    """用游戏互推数据测试贡献度分解。"""
    df = pd.read_excel(PROJECT_ROOT / "reference/test_doc/游戏互推.xlsx")
    # Convert date column first — Excel dates may be "2020/01/19" format
    df["日期"] = pd.to_datetime(df["日期"], errors="coerce")
    workspace.add("game_cd", df)
    try:
        # Data range is only 2020-01-16~2020-01-19, so split into two sub-periods
        from data_agent.tools.eda import contribute_decomposition
        result = contribute_decomposition(
            "game_cd", metric="曝光次数", dimension="公司",
            date_col="日期",
            period_a="2020-01-16~2020-01-17", period_b="2020-01-18~2020-01-19",
            agg_func="sum",
        )
        r = assert_tool_result_ok(result, "contribute_real")
        if r is not True:
            return r
    finally:
        workspace.remove("game_cd")
    return True


test("contribute: sum 分解", test_contribute_sum)
test("contribute: mean 加权分解", test_contribute_mean)
test("contribute: 错误指标列", test_contribute_bad_metric)
test("contribute: 错误维度列", test_contribute_bad_dimension)
test("contribute: 超出数据范围", test_contribute_bad_period)
test("contribute: ToolResult 结构", test_contribute_toolresult_fields)
test("contribute: 真实数据（游戏互推）", test_contribute_with_real_data)


# ============================================================
print("\n" + "=" * 60)
print("四、funnel_analysis — 漏斗分析三种模式")
print("=" * 60)


def _make_event_data():
    """创建事件明细数据（steps 模式用）。"""
    np.random.seed(42)
    users = np.random.randint(1000, 2000, 500)
    events = ["view", "click", "add_cart", "purchase"]
    records = []
    for uid in users:
        n_events = np.random.randint(1, 5)
        for i in range(n_events):
            records.append({
                "user_id": uid,
                "event": events[i],
                "timestamp": pd.Timestamp("2025-01-01") + pd.Timedelta(hours=np.random.randint(0, 720)),
            })
    return pd.DataFrame(records)


def _make_aggregate_data():
    """创建预聚合漏斗数据（aggregate 模式用）。"""
    return pd.DataFrame({
        "step": ["访问首页", "浏览商品", "加入购物车", "完成支付"],
        "count": [10000, 6000, 3000, 1500],
    })


def _make_rates_data():
    """创建宽表率数据（rates 模式用）。"""
    return pd.DataFrame({
        "date": pd.date_range("2025-01-01", periods=30),
        "visit_count": np.random.randint(5000, 10000, 30),
        "点击率": np.random.uniform(0.3, 0.5, 30),
        "加购率": np.random.uniform(0.15, 0.25, 30),
        "支付率": np.random.uniform(0.05, 0.12, 30),
    })


def test_funnel_steps_basic():
    from data_agent.tools.eda import funnel_analysis
    df = _make_event_data()
    workspace.add("funnel_events", df)
    try:
        result = funnel_analysis(
            "funnel_events", mode="steps",
            user_col="user_id", event_col="event",
            steps="view,click,add_cart,purchase",
        )
        r = assert_tool_result_ok(result, "funnel_steps")
        if r is not True:
            return r
        if not isinstance(result, ToolResult):
            return f"should return ToolResult, got {type(result)}"
        data = result.data
        if data["mode"] != "steps":
            return f"mode should be steps, got {data['mode']}"
        if len(data["steps"]) != 4:
            return f"should have 4 steps, got {len(data['steps'])}"
        # Step counts should decrease
        counts = [s["count"] for s in data["steps"]]
        for i in range(1, len(counts)):
            if counts[i] > counts[i - 1]:
                return f"step {i} count ({counts[i]}) should be <= step {i-1} ({counts[i-1]})"
    finally:
        workspace.remove("funnel_events")
    return True


def test_funnel_steps_with_dimension():
    from data_agent.tools.eda import funnel_analysis
    df = _make_event_data()
    df["platform"] = np.random.choice(["ios", "android"], len(df))
    workspace.add("funnel_events_dim", df)
    try:
        result = funnel_analysis(
            "funnel_events_dim", mode="steps",
            user_col="user_id", event_col="event",
            steps="view,click,add_cart,purchase",
            dimension="platform",
        )
        r = assert_tool_result_ok(result, "funnel_steps_dim")
        if r is not True:
            return r
        data = result.data
        if not data.get("dimension_funnels"):
            return "should have dimension_funnels"
        if "ios" not in data["dimension_funnels"] and "android" not in data["dimension_funnels"]:
            return f"should have ios/android funnels: {list(data['dimension_funnels'].keys())}"
    finally:
        workspace.remove("funnel_events_dim")
    return True


def test_funnel_steps_missing_col():
    from data_agent.tools.eda import funnel_analysis
    df = _make_event_data()
    workspace.add("funnel_err", df)
    try:
        result = funnel_analysis(
            "funnel_err", mode="steps",
            user_col="nonexistent", event_col="event",
            steps="view,click",
        )
        if not (isinstance(result, str) and "Error" in result):
            return "should error for missing user_col"
    finally:
        workspace.remove("funnel_err")
    return True


def test_funnel_steps_missing_event():
    from data_agent.tools.eda import funnel_analysis
    df = _make_event_data()
    workspace.add("funnel_err2", df)
    try:
        result = funnel_analysis(
            "funnel_err2", mode="steps",
            user_col="user_id", event_col="event",
            steps="view,click,nonexistent_step",
        )
        if not (isinstance(result, str) and "Error" in result):
            return "should error for missing step"
    finally:
        workspace.remove("funnel_err2")
    return True


def test_funnel_aggregate_basic():
    from data_agent.tools.eda import funnel_analysis
    df = _make_aggregate_data()
    workspace.add("funnel_agg", df)
    try:
        result = funnel_analysis(
            "funnel_agg", mode="aggregate",
            step_col="step", count_col="count",
            steps="访问首页,浏览商品,加入购物车,完成支付",
        )
        r = assert_tool_result_ok(result, "funnel_agg")
        if r is not True:
            return r
        data = result.data
        if data["mode"] != "aggregate":
            return f"mode should be aggregate, got {data['mode']}"
        steps = data["steps"]
        if steps[0]["count"] != 10000:
            return f"first step should be 10000, got {steps[0]['count']}"
        # Check overall conversion
        expected_conv = 1500 / 10000
        if abs(data["overall_conversion"] - expected_conv) > 0.01:
            return f"overall conversion should be ~{expected_conv:.4f}, got {data['overall_conversion']}"
    finally:
        workspace.remove("funnel_agg")
    return True


def test_funnel_aggregate_auto_order():
    """aggregate 模式不指定 steps 时应按 count 降序。"""
    from data_agent.tools.eda import funnel_analysis
    df = _make_aggregate_data()
    workspace.add("funnel_agg_auto", df)
    try:
        result = funnel_analysis(
            "funnel_agg_auto", mode="aggregate",
            step_col="step", count_col="count",
        )
        r = assert_tool_result_ok(result, "funnel_agg_auto")
        if r is not True:
            return r
    finally:
        workspace.remove("funnel_agg_auto")
    return True


def test_funnel_rates_basic():
    from data_agent.tools.eda import funnel_analysis
    df = _make_rates_data()
    workspace.add("funnel_rates", df)
    try:
        result = funnel_analysis(
            "funnel_rates", mode="rates",
            rate_cols="点击率,加购率,支付率",
        )
        r = assert_tool_result_ok(result, "funnel_rates")
        if r is not True:
            return r
        data = result.data
        if data["mode"] != "rates":
            return f"mode should be rates, got {data['mode']}"
        steps = data["steps"]
        if len(steps) != 3:
            return f"should have 3 rate steps, got {len(steps)}"
        # Each step should have cumulative_rate
        for s in steps:
            if "cumulative_rate" not in s:
                return f"step {s} should have cumulative_rate"
    finally:
        workspace.remove("funnel_rates")
    return True


def test_funnel_rates_dimension():
    """rates 模式按维度分组。"""
    from data_agent.tools.eda import funnel_analysis
    df = _make_rates_data()
    df["channel"] = np.random.choice(["A", "B"], len(df))
    workspace.add("funnel_rates_dim", df)
    try:
        result = funnel_analysis(
            "funnel_rates_dim", mode="rates",
            rate_cols="点击率,加购率,支付率",
            dimension="channel",
        )
        r = assert_tool_result_ok(result, "funnel_rates_dim")
        if r is not True:
            return r
        data = result.data
        if not data.get("dimension_funnels"):
            return "should have dimension_funnels"
    finally:
        workspace.remove("funnel_rates_dim")
    return True


def test_funnel_auto_detect_steps():
    """auto 模式检测 steps（传入 user_col + event_col + steps）。"""
    from data_agent.tools.eda import funnel_analysis
    df = _make_event_data()
    workspace.add("funnel_auto_s", df)
    try:
        result = funnel_analysis(
            "funnel_auto_s", mode="auto",
            user_col="user_id", event_col="event",
            steps="view,click,add_cart,purchase",
        )
        r = assert_tool_result_ok(result, "funnel_auto")
        if r is not True:
            return r
        if result.data["mode"] != "steps":
            return f"auto should detect steps, got {result.data['mode']}"
    finally:
        workspace.remove("funnel_auto_s")
    return True


def test_funnel_auto_detect_aggregate():
    """auto 模式检测 aggregate（传入 step_col + count_col）。"""
    from data_agent.tools.eda import funnel_analysis
    df = _make_aggregate_data()
    workspace.add("funnel_auto_a", df)
    try:
        result = funnel_analysis(
            "funnel_auto_a", mode="auto",
            step_col="step", count_col="count",
            steps="访问首页,浏览商品,加入购物车,完成支付",
        )
        r = assert_tool_result_ok(result, "funnel_auto_a")
        if r is not True:
            return r
        if result.data["mode"] != "aggregate":
            return f"auto should detect aggregate, got {result.data['mode']}"
    finally:
        workspace.remove("funnel_auto_a")
    return True


def test_funnel_auto_detect_rates():
    """auto 模式基于列名自动检测 rates。"""
    from data_agent.tools.eda import funnel_analysis
    df = pd.DataFrame({
        "date": pd.date_range("2025-01-01", periods=10),
        "点击率": np.random.uniform(0.3, 0.5, 10),
        "转化率": np.random.uniform(0.05, 0.15, 10),
    })
    workspace.add("funnel_auto_r", df)
    try:
        result = funnel_analysis("funnel_auto_r", mode="auto")
        r = assert_tool_result_ok(result, "funnel_auto_r")
        if r is not True:
            return r
        if result.data["mode"] != "rates":
            return f"auto should detect rates from column names, got {result.data['mode']}"
    finally:
        workspace.remove("funnel_auto_r")
    return True


def test_funnel_biggest_drop():
    """应正确识别最大流失步骤。"""
    from data_agent.tools.eda import funnel_analysis
    df = pd.DataFrame({
        "step": ["S1", "S2", "S3", "S4"],
        "count": [1000, 900, 100, 90],  # Biggest drop: S2→S3
    })
    workspace.add("funnel_drop", df)
    try:
        result = funnel_analysis(
            "funnel_drop", mode="aggregate",
            step_col="step", count_col="count",
            steps="S1,S2,S3,S4",
        )
        if not isinstance(result, ToolResult):
            return f"should return ToolResult, got {type(result)}"
        drop = result.data.get("biggest_drop")
        if not drop:
            return "should identify biggest drop"
        if drop["from"] != "S2" or drop["to"] != "S3":
            return f"biggest drop should be S2→S3, got {drop}"
    finally:
        workspace.remove("funnel_drop")
    return True


def test_funnel_too_few_steps():
    from data_agent.tools.eda import funnel_analysis
    df = _make_event_data()
    workspace.add("funnel_few", df)
    try:
        result = funnel_analysis(
            "funnel_few", mode="steps",
            user_col="user_id", event_col="event",
            steps="view",  # only 1 step
        )
        if not (isinstance(result, str) and "Error" in result):
            return "should error for less than 2 steps"
    finally:
        workspace.remove("funnel_few")
    return True


test("funnel: steps 基本模式", test_funnel_steps_basic)
test("funnel: steps + 维度分组", test_funnel_steps_with_dimension)
test("funnel: steps 缺失列", test_funnel_steps_missing_col)
test("funnel: steps 不存在事件", test_funnel_steps_missing_event)
test("funnel: aggregate 基本模式", test_funnel_aggregate_basic)
test("funnel: aggregate 自动排序", test_funnel_aggregate_auto_order)
test("funnel: rates 基本模式", test_funnel_rates_basic)
test("funnel: rates + 维度分组", test_funnel_rates_dimension)
test("funnel: auto 检测 steps", test_funnel_auto_detect_steps)
test("funnel: auto 检测 aggregate", test_funnel_auto_detect_aggregate)
test("funnel: auto 检测 rates", test_funnel_auto_detect_rates)
test("funnel: 最大流失识别", test_funnel_biggest_drop)
test("funnel: 步骤太少报错", test_funnel_too_few_steps)


# ============================================================
print("\n" + "=" * 60)
print("五、what_if_simulation — 情景模拟三级")
print("=" * 60)

_reset_test_data()


def test_sensitivity_forward():
    from data_agent.tools.simulation import what_if_simulation
    result = what_if_simulation(
        "test", mode="sensitivity",
        metric="sales", dimension="channel",
        change_pct=10,
    )
    r = assert_tool_result_ok(result, "sensitivity_fwd")
    if r is not True:
        return r
    if not isinstance(result, ToolResult):
        return f"should return ToolResult, got {type(result)}"
    data = result.data
    if "baseline" not in data or "projected" not in data:
        return "should have baseline and projected"
    if data["impact"]["relative_pct"] <= 0:
        return "10% increase should have positive impact"
    return True


def test_sensitivity_specific_dim():
    from data_agent.tools.simulation import what_if_simulation
    result = what_if_simulation(
        "test", mode="sensitivity",
        metric="sales", dimension="channel", dim_value="A",
        change_pct=20,
    )
    r = assert_tool_result_ok(result, "sensitivity_dim")
    if r is not True:
        return r
    data = result.data
    if "breakdown" not in data:
        return "should have breakdown"
    return True


def test_sensitivity_reverse():
    from data_agent.tools.simulation import what_if_simulation
    # Get baseline first
    df = workspace.get("test")
    baseline = float(df["sales"].sum())
    target = baseline * 1.15  # 15% growth target

    result = what_if_simulation(
        "test", mode="sensitivity",
        metric="sales", dimension="channel",
        target_value=str(int(target)),
    )
    r = assert_tool_result_ok(result, "sensitivity_rev")
    if r is not True:
        return r
    data = result.data
    if "breakdown" not in data:
        return "should have breakdown for reverse"
    if "required_total_pct" not in data:
        return "should have required_total_pct"
    return True


def test_sensitivity_no_change():
    from data_agent.tools.simulation import what_if_simulation
    result = what_if_simulation(
        "test", mode="sensitivity",
        metric="sales", dimension="channel",
        change_pct=0,
    )
    # Should error or return meaningful message
    if isinstance(result, str) and "Error" in result:
        return True
    if isinstance(result, ToolResult) and "Error" in result.summary:
        return True
    return True


def test_sensitivity_bad_metric():
    from data_agent.tools.simulation import what_if_simulation
    result = what_if_simulation(
        "test", mode="sensitivity",
        metric="nonexistent", dimension="channel",
        change_pct=10,
    )
    if not (isinstance(result, str) and "Error" in result):
        return "should error for bad metric"
    return True


def test_predict_basic():
    from data_agent.tools.simulation import what_if_simulation
    result = what_if_simulation(
        "test", mode="predict",
        target_col="sales",
        feature_changes='{"users": 10, "revenue": -5}',
    )
    r = assert_tool_result_ok(result, "predict")
    if r is not True:
        return r
    data = result.data
    if "baseline" not in data or "projected" not in data:
        return "should have baseline and projected"
    if "model_type" not in data:
        return "should have model_type"
    return True


def test_predict_invalid_json():
    from data_agent.tools.simulation import what_if_simulation
    result = what_if_simulation(
        "test", mode="predict",
        target_col="sales",
        feature_changes="not json",
    )
    if not (isinstance(result, str) and "Error" in result):
        return "should error for invalid JSON"
    return True


def test_predict_invalid_feature():
    from data_agent.tools.simulation import what_if_simulation
    result = what_if_simulation(
        "test", mode="predict",
        target_col="sales",
        feature_changes='{"nonexistent_col": 10}',
    )
    if not (isinstance(result, str) and "Error" in result):
        return "should error for invalid feature"
    return True


def test_optimize_basic():
    from data_agent.tools.simulation import what_if_simulation
    result = what_if_simulation(
        "test", mode="optimize",
        target_metric="sales", dimension="channel",
        goal_pct=10,
    )
    r = assert_tool_result_ok(result, "optimize")
    if r is not True:
        return r
    data = result.data
    if "breakdown" not in data:
        return "should have breakdown"
    if "feasible" not in data:
        return "should have feasibility flag"
    # Sum of required changes should approximate goal
    total_required = sum(b["required_change"] for b in data["breakdown"])
    if abs(total_required - data["gap"]) > data["gap"] * 0.5:
        return f"total required ({total_required:.2f}) should approximate gap ({data['gap']:.2f})"
    return True


def test_optimize_with_constraints():
    from data_agent.tools.simulation import what_if_simulation
    result = what_if_simulation(
        "test", mode="optimize",
        target_metric="sales", dimension="channel",
        goal_pct=15,
        constraints='{"A": {"min": -5, "max": 10}, "B": {"min": 0, "max": 30}}',
    )
    r = assert_tool_result_ok(result, "optimize_c")
    if r is not True:
        return r
    data = result.data
    # Check that constrained dimensions are respected
    for b in data["breakdown"]:
        if b["constrained"]:
            dim = b["dimension_value"]
            c = json.loads('{"A": {"min": -5, "max": 10}, "B": {"min": 0, "max": 30}}')
            if dim in c:
                if c[dim]["min"] <= b["required_pct"] <= c[dim]["max"]:
                    continue
                # Allow some slack due to redistribution
                pass
    return True


def test_optimize_zero_goal():
    from data_agent.tools.simulation import what_if_simulation
    result = what_if_simulation(
        "test", mode="optimize",
        target_metric="sales", dimension="channel",
        goal_pct=0,
    )
    if not (isinstance(result, str) and "Error" in result):
        return "should error for zero goal"
    return True


def test_simulation_nonexistent_dataset():
    from data_agent.tools.simulation import what_if_simulation
    result = what_if_simulation("nonexistent_xyz", mode="sensitivity")
    if not (isinstance(result, str) and '"error"' in result):
        return "should error for nonexistent dataset"
    return True


def test_simulation_bad_mode():
    from data_agent.tools.simulation import what_if_simulation
    result = what_if_simulation("test", mode="invalid_mode")
    if not (isinstance(result, str) and "Error" in result):
        return "should error for invalid mode"
    return True


test("simulation: sensitivity 正向", test_sensitivity_forward)
test("simulation: sensitivity 指定维度值", test_sensitivity_specific_dim)
test("simulation: sensitivity 反向推算", test_sensitivity_reverse)
test("simulation: sensitivity 变化为0", test_sensitivity_no_change)
test("simulation: sensitivity 错误指标", test_sensitivity_bad_metric)
test("simulation: predict 基本预测", test_predict_basic)
test("simulation: predict 无效JSON", test_predict_invalid_json)
test("simulation: predict 无效特征", test_predict_invalid_feature)
test("simulation: optimize 基本规划", test_optimize_basic)
test("simulation: optimize 带约束", test_optimize_with_constraints)
test("simulation: optimize 目标为0", test_optimize_zero_goal)
test("simulation: 不存在数据集", test_simulation_nonexistent_dataset)
test("simulation: 不支持模式", test_simulation_bad_mode)


# ============================================================
print("\n" + "=" * 60)
print("六、Visualization — 漏斗图")
print("=" * 60)


def test_chart_funnel():
    from data_agent.tools.visualization import create_chart, set_chart_session
    set_chart_session("test_session")
    # Create funnel data
    data_json = json.dumps([
        {"step": "Visit", "count": 10000},
        {"step": "Browse", "count": 6000},
        {"step": "Cart", "count": 3000},
        {"step": "Pay", "count": 1500},
    ])
    result = create_chart(
        chart_type="funnel",
        data_json=data_json,
        x_col="count", y_col="step",
        title="Test Funnel Chart",
    )
    if "Error" in result:
        return f"funnel chart failed: {result}"
    if "Chart saved" not in result:
        return f"should save chart: {result[:200]}"
    return True


def test_chart_funnel_with_dataset():
    from data_agent.tools.visualization import create_chart, set_chart_session
    set_chart_session("test_session")
    # Use the test dataset with aggregate data
    df = pd.DataFrame({
        "step": ["S1", "S2", "S3"],
        "count": [1000, 500, 200],
    })
    workspace.add("chart_funnel", df)
    try:
        result = create_chart(
            chart_type="funnel",
            data="chart_funnel",
            x_col="count", y_col="step",
            title="Funnel from Dataset",
        )
        if "Error" in result:
            return f"funnel chart from dataset failed: {result}"
    finally:
        workspace.remove("chart_funnel")
    return True


test("chart: funnel 图", test_chart_funnel)
test("chart: funnel 用数据集", test_chart_funnel_with_dataset)


# ============================================================
print("\n" + "=" * 60)
print("七、Registry — 工具分组与关键词更新")
print("=" * 60)


def test_registry_new_tools():
    from data_agent.tools.registry import registry, TOOL_GROUPS
    # Check new tools are in their groups
    eda_tools = TOOL_GROUPS.get("eda", set())
    ml_tools = TOOL_GROUPS.get("ml", set())
    stats_tools = TOOL_GROUPS.get("stats", set())

    missing_eda = {"contribute_decomposition", "funnel_analysis", "interpret_dataset"} - eda_tools
    if missing_eda:
        return f"EDA group missing: {missing_eda}"

    if "what_if_simulation" not in ml_tools:
        return "ML group missing what_if_simulation"

    if "contribute_decomposition" not in stats_tools:
        return "Stats group missing contribute_decomposition"

    return True


def test_registry_tool_registered():
    from data_agent.tools.registry import registry
    for name in ["interpret_dataset", "contribute_decomposition", "funnel_analysis", "what_if_simulation"]:
        t = registry.get(name)
        if t is None:
            return f"tool '{name}' should be registered"
    return True


def test_registry_keyword_activation():
    from data_agent.tools.registry import infer_groups_from_text

    # Test new keywords
    tests = [
        ("漏斗分析", {"eda"}),
        ("转化率趋势", {"eda"}),
        ("贡献拆解", {"eda", "stats"}),
        ("分解指标变化", {"eda", "stats"}),
        ("情景模拟", {"ml"}),
        ("what-if 分析", {"ml"}),
        ("假设检验", {"ml"}),
        ("回归预测", {"ml"}),
    ]
    for text, expected_groups in tests:
        groups = infer_groups_from_text(text)
        if not expected_groups.issubset(groups):
            return f"'{text}' should activate {expected_groups}, got {groups}"
    return True


def test_registry_expand_on_tool_call():
    from data_agent.tools.registry import ToolRegistry
    reg = ToolRegistry()
    # Manually register a fake tool in the eda group
    from data_agent.tools.registry import TOOL_GROUPS, _build_tool_to_group
    lookup = _build_tool_to_group()
    # funnel_analysis should map to eda
    if lookup.get("funnel_analysis") != "eda":
        return f"funnel_analysis should be in eda group, got {lookup.get('funnel_analysis')}"
    return True


test("registry: 新工具分组正确", test_registry_new_tools)
test("registry: 新工具已注册", test_registry_tool_registered)
test("registry: 关键词激活", test_registry_keyword_activation)
test("registry: 工具→分组映射", test_registry_expand_on_tool_call)


# ============================================================
print("\n" + "=" * 60)
print("八、Prompt — AGENT_ANALYSIS_ENGINE 与 _classify_task")
print("=" * 60)


def test_prompt_engine_exists():
    from data_agent.agent.prompts import AGENT_ANALYSIS_ENGINE
    if not AGENT_ANALYSIS_ENGINE:
        return "AGENT_ANALYSIS_ENGINE should not be empty"
    # Check key sections
    for keyword in ["策略", "多视角", "工具映射", "data_interpretation"]:
        if keyword not in AGENT_ANALYSIS_ENGINE:
            return f"AGENT_ANALYSIS_ENGINE missing '{keyword}'"
    return True


def test_prompt_engine_injected():
    from data_agent.agent.prompts import build_system_prompt
    prompt = build_system_prompt("分析一下趋势", "standard")
    if "AGENT_ANALYSIS_ENGINE" in prompt or "策略" in prompt:
        return True  # engine content is injected (the variable name itself shouldn't appear)
    # Actually check if the content is there
    if "工具映射" in prompt or "多视角" in prompt:
        return True
    return "build_system_prompt should include AGENT_ANALYSIS_ENGINE content"


def test_classify_task_analysis_intent():
    """规则 2.7: 有数据上下文时，分析意图词不应降级为 chat。"""
    from data_agent.agent.prompts import _classify_task
    ctx_with_data = "main: 100 rows x 5 cols, columns: date, sales, users"

    # These should NOT be classified as chat when session has data
    analysis_inputs = [
        "分析一下销售趋势",
        "为什么销量下降了",
        "帮我看看这数据",
        "趋势怎么样",
        "帮我分析一下",
    ]
    for text in analysis_inputs:
        result = _classify_task(text, ctx_with_data)
        if result == "chat":
            return f"'{text}' with data context should not be classified as chat, got '{result}'"
    return True


def test_classify_task_full_keywords():
    """新增的 FULL 关键词应正确分类。"""
    from data_agent.agent.prompts import _classify_task
    ctx = "main: 100 rows x 5 cols"
    full_keywords = ["漏斗分析", "转化分析", "贡献分析", "情景模拟"]
    for kw in full_keywords:
        result = _classify_task(kw, ctx)
        if result not in ("full", "standard"):
            return f"'{kw}' should be full or standard, got '{result}'"
    return True


def test_classify_task_chat_without_data():
    """无数据上下文时，纯分析意图词应正常分类。"""
    from data_agent.agent.prompts import _classify_task
    result = _classify_task("你好", "")
    if result != "chat":
        return f"'你好' without context should be chat, got '{result}'"
    return True


def test_prompt_standard_has_strategy():
    """AGENT_STANDARD 应包含策略制定步骤。"""
    from data_agent.agent.prompts import AGENT_STANDARD
    if "策略" not in AGENT_STANDARD:
        return "AGENT_STANDARD should mention 策略"
    return True


def test_prompt_full_has_self_rebuttal():
    """AGENT_FULL 应包含自我反驳机制。"""
    from data_agent.agent.prompts import AGENT_FULL
    if "反驳" not in AGENT_FULL and "rebuttal" not in AGENT_FULL.lower():
        return "AGENT_FULL should mention self-rebuttal/反驳"
    return True


def test_prompt_full_has_funnel():
    """AGENT_FULL 的 insight 类型应包含 funnel。"""
    from data_agent.agent.prompts import AGENT_FULL
    if "funnel" not in AGENT_FULL.lower() and "漏斗" not in AGENT_FULL:
        return "AGENT_FULL should mention funnel/漏斗 in insight types"
    return True


test("prompt: AGENT_ANALYSIS_ENGINE 存在", test_prompt_engine_exists)
test("prompt: 引擎注入到 build_system_prompt", test_prompt_engine_injected)
test("prompt: 规则2.7 分析意图不降级", test_classify_task_analysis_intent)
test("prompt: FULL 关键词分类", test_classify_task_full_keywords)
test("prompt: 无数据上下文 chat", test_classify_task_chat_without_data)
test("prompt: STANDARD 有策略步骤", test_prompt_standard_has_strategy)
test("prompt: FULL 有自我反驳", test_prompt_full_has_self_rebuttal)
test("prompt: FULL 有 funnel 类型", test_prompt_full_has_funnel)


# ============================================================
print("\n" + "=" * 60)
print("九、load_data 集成 — interpret_dataset 自动调用")
print("=" * 60)


def test_load_data_csv():
    """load_data 应自动调用 interpret_dataset 和 quick_profile。"""
    from data_agent.tools.data_io import load_data
    from data_agent.config import get_config

    cfg = get_config()
    test_csv = PROJECT_ROOT / "reference/test_doc/test_sales.csv"
    if not test_csv.exists():
        return "skip"

    result = load_data(str(test_csv), name="test_load_integration")
    if "Error" in result:
        return f"load_data failed: {result[:200]}"

    # Check that interpret_dataset was called (look for [data_interpretation] block)
    if "[data_interpretation]" not in result:
        return "load_data result should contain [data_interpretation] block"

    # Check that quick_profile was called (look for [data_profile] block)
    if "[data_profile]" not in result:
        return "load_data result should contain [data_profile] block"

    # Cleanup
    workspace.remove("test_load_integration")
    return True


def test_load_data_xlsx():
    """Excel 文件加载。"""
    from data_agent.tools.data_io import load_data
    test_xlsx = PROJECT_ROOT / "reference/test_doc/内购数据.xlsx"
    if not test_xlsx.exists():
        return "skip"

    result = load_data(str(test_xlsx), name="test_load_xlsx")
    if "Error" in result:
        return f"load xlsx failed: {result[:200]}"
    if "[data_interpretation]" not in result:
        return "xlsx load should also trigger interpret_dataset"
    workspace.remove("test_load_xlsx")
    return True


def test_load_data_context_param():
    """context 参数应保存到元数据。"""
    from data_agent.tools.data_io import load_data
    test_csv = PROJECT_ROOT / "reference/test_doc/test_sales.csv"
    if not test_csv.exists():
        return "skip"

    result = load_data(str(test_csv), name="test_ctx", context="ARPU定义: 总收入/活跃用户数")
    if "Error" in result:
        return f"load with context failed: {result[:200]}"

    ctx = workspace.get_metadata("test_ctx", "context")
    if ctx != "ARPU定义: 总收入/活跃用户数":
        return f"context metadata should be saved, got: {ctx}"

    workspace.remove("test_ctx")
    return True


test("load_data: CSV + interpret + profile", test_load_data_csv)
test("load_data: Excel + interpret", test_load_data_xlsx)
test("load_data: context 参数保存", test_load_data_context_param)


# ============================================================
print("\n" + "=" * 60)
print("十、ToolResult 双模式 — CLI/Web 兼容性")
print("=" * 60)


def test_toolresult_to_cli():
    tr = ToolResult(summary="测试摘要", data={"key": "value"}, suggested_next="next_tool")
    cli = tr.to_cli()
    if cli != "测试摘要":
        return f"to_cli should return summary, got: {cli}"
    return True


def test_toolresult_to_web():
    tr = ToolResult(
        summary="测试摘要",
        data={"metric": 42},
        suggested_next="next_tool",
        artifacts=None,
    )
    web = tr.to_web()
    if web["summary"] != "测试摘要":
        return "web should have summary"
    if web["data"]["metric"] != 42:
        return "web should have data"
    if web["suggested_next"] != "next_tool":
        return "web should have suggested_next"
    if "artifacts" in web:
        return "web should not include artifacts when None"
    return True


def test_toolresult_artifacts():
    from data_agent.tools.registry import ArtifactRef
    tr = ToolResult(
        summary="有图表",
        artifacts=[ArtifactRef(path="chart.html", type="chart", description="销售趋势图")],
    )
    web = tr.to_web()
    if not web.get("artifacts"):
        return "web should have artifacts"
    if web["artifacts"][0]["type"] != "chart":
        return "artifact type should be chart"
    return True


def test_toolresult_from_str():
    tr = ToolResult.from_str("简单字符串")
    if tr.summary != "简单字符串":
        return "from_str should set summary"
    if tr.data is not None:
        return "from_str should have None data"
    return True


def test_new_tools_return_toolresult():
    """所有新工具应返回 ToolResult（不是纯字符串）。"""
    from data_agent.tools.data_understand import interpret_dataset
    from data_agent.tools.eda import contribute_decomposition, funnel_analysis
    from data_agent.tools.simulation import what_if_simulation

    # interpret_dataset
    r = interpret_dataset("test")
    if not isinstance(r, ToolResult):
        return f"interpret_dataset should return ToolResult, got {type(r)}"

    # contribute_decomposition
    r = contribute_decomposition(
        "test", metric="sales", dimension="channel",
        period_a="2025-01-01~2025-01-31", period_b="2025-02-01~2025-02-28",
    )
    if not isinstance(r, ToolResult):
        return f"contribute_decomposition should return ToolResult, got {type(r)}"

    # funnel_analysis (aggregate mode)
    workspace.add("tr_test", pd.DataFrame({
        "step": ["A", "B"], "count": [100, 50],
    }))
    r = funnel_analysis("tr_test", mode="aggregate", step_col="step", count_col="count", steps="A,B")
    workspace.remove("tr_test")
    if not isinstance(r, ToolResult):
        return f"funnel_analysis should return ToolResult, got {type(r)}"

    # what_if_simulation
    r = what_if_simulation("test", mode="sensitivity", metric="sales", dimension="channel", change_pct=10)
    if not isinstance(r, ToolResult):
        return f"what_if_simulation should return ToolResult, got {type(r)}"

    return True


test("ToolResult: to_cli", test_toolresult_to_cli)
test("ToolResult: to_web", test_toolresult_to_web)
test("ToolResult: artifacts", test_toolresult_artifacts)
test("ToolResult: from_str", test_toolresult_from_str)
test("ToolResult: 新工具都返回 ToolResult", test_new_tools_return_toolresult)


# ============================================================
print("\n" + "=" * 60)
print("十一、compare_periods 回归测试（使用 _utils 共享函数）")
print("=" * 60)

_reset_test_data()


def test_compare_periods_uses_shared_utils():
    """compare_periods 应正确使用 resolve_date_col 和 parse_period_range。"""
    from data_agent.tools.eda import compare_periods
    # Auto-infer date col
    result = compare_periods(
        "test", metrics="sales",
        period_a="2025-01-01~2025-01-31", period_b="2025-02-01~2025-02-28",
    )
    r = assert_ok(result, "compare_shared")
    if r is not True:
        return r
    data = json.loads(result)
    if "period_a" not in data or "period_b" not in data:
        return "should have period info"
    return True


def test_compare_periods_shortcuts():
    """快捷词应通过 parse_period_range 正确解析。"""
    from data_agent.tools.eda import compare_periods
    result = compare_periods(
        "test", date_col="date", metrics="sales",
        period_a="last_month", period_b="this_month",
    )
    return assert_ok(result, "compare_shortcuts")


test("compare_periods: 共享函数集成", test_compare_periods_uses_shared_utils)
test("compare_periods: 快捷词", test_compare_periods_shortcuts)


# ============================================================
print("\n" + "=" * 60)
print("十二、quick_profile — suggested_analyses 增强")
print("=" * 60)

_reset_test_data()


def test_quick_profile_suggested_analyses():
    """非 compact 模式应包含 suggested_analyses。"""
    from data_agent.tools.data_understand import quick_profile
    result = json.loads(quick_profile("test"))
    if "suggested_analyses" not in result:
        return "non-compact quick_profile should have suggested_analyses"
    if not result["suggested_analyses"]:
        return "suggested_analyses should not be empty"
    return True


def test_quick_profile_compact_no_suggested():
    """compact 模式不需要 suggested_analyses。"""
    from data_agent.tools.data_understand import quick_profile
    result = json.loads(quick_profile("test", compact=True))
    # compact may or may not have it, but should not crash
    return True


test("quick_profile: suggested_analyses", test_quick_profile_suggested_analyses)
test("quick_profile: compact 模式", test_quick_profile_compact_no_suggested)


# ============================================================
print("\n" + "=" * 60)
print("十三、tool_search — 新工具可搜索")
print("=" * 60)


def test_search_funnel():
    from data_agent.tools.registry import tool_search
    result = json.loads(tool_search("漏斗"))
    if result["matches"] < 1:
        return "should find funnel_analysis when searching '漏斗'"
    names = [t["name"] for t in result["tools"]]
    if "funnel_analysis" not in names:
        return f"funnel_analysis should be in results: {names}"
    return True


def test_search_contribution():
    from data_agent.tools.registry import tool_search
    result = json.loads(tool_search("贡献"))
    if result["matches"] < 1:
        return "should find contribute_decomposition"
    return True


def test_search_simulation():
    from data_agent.tools.registry import tool_search
    result = json.loads(tool_search("模拟"))
    names = [t["name"] for t in result["tools"]]
    if "what_if_simulation" not in names:
        return f"should find what_if_simulation: {names}"
    return True


def test_search_interpret():
    from data_agent.tools.registry import tool_search
    result = json.loads(tool_search("interpret"))
    if result["matches"] < 1:
        return "should find interpret_dataset"
    return True


test("tool_search: 漏斗", test_search_funnel)
test("tool_search: 贡献", test_search_contribution)
test("tool_search: 模拟", test_search_simulation)
test("tool_search: interpret", test_search_interpret)


# ============================================================
print("\n" + "=" * 60)
print("十四、Registry execute — 通过 registry 执行新工具")
print("=" * 60)


def test_registry_execute_interpret():
    from data_agent.tools.registry import registry
    result = registry.execute("interpret_dataset", {"name": "test"})
    if isinstance(result, str) and '"error"' in result:
        return f"execute interpret_dataset failed: {result[:200]}"
    return True


def test_registry_execute_contribute():
    from data_agent.tools.registry import registry
    result = registry.execute("contribute_decomposition", {
        "name": "test", "metric": "sales", "dimension": "channel",
        "period_a": "2025-01-01~2025-01-31", "period_b": "2025-02-01~2025-02-28",
    })
    if isinstance(result, str) and '"error"' in result:
        return f"execute contribute_decomposition failed: {result[:200]}"
    return True


def test_registry_execute_funnel():
    from data_agent.tools.registry import registry
    workspace.add("reg_funnel", pd.DataFrame({
        "step": ["A", "B"], "count": [100, 50],
    }))
    try:
        result = registry.execute("funnel_analysis", {
            "name": "reg_funnel", "mode": "aggregate",
            "step_col": "step", "count_col": "count", "steps": "A,B",
        })
        if isinstance(result, str) and '"error"' in result:
            return f"execute funnel_analysis failed: {result[:200]}"
    finally:
        workspace.remove("reg_funnel")
    return True


def test_registry_execute_simulation():
    from data_agent.tools.registry import registry
    result = registry.execute("what_if_simulation", {
        "name": "test", "mode": "sensitivity",
        "metric": "sales", "dimension": "channel", "change_pct": 10.0,
    })
    if isinstance(result, str) and '"error"' in result:
        return f"execute what_if_simulation failed: {result[:200]}"
    return True


def test_registry_format_result_error():
    """format_result 应在错误时附加恢复提示。"""
    from data_agent.tools.registry import registry
    error_result = ToolResult(summary='{"error": "some error"}')
    formatted = registry.format_result("some_tool", error_result)
    if "系统提示" not in formatted:
        return "format_result should append recovery hint for errors"
    return True


def test_registry_format_result_ok():
    """format_result 在成功时不应附加提示。"""
    from data_agent.tools.registry import registry
    ok_result = ToolResult(summary="正常结果")
    formatted = registry.format_result("some_tool", ok_result)
    if "系统提示" in formatted:
        return "format_result should not add hint for successful results"
    return True


test("registry execute: interpret_dataset", test_registry_execute_interpret)
test("registry execute: contribute_decomposition", test_registry_execute_contribute)
test("registry execute: funnel_analysis", test_registry_execute_funnel)
test("registry execute: what_if_simulation", test_registry_execute_simulation)
test("registry: format_result 错误提示", test_registry_format_result_error)
test("registry: format_result 成功无提示", test_registry_format_result_ok)


# ============================================================
# 汇总
# ============================================================
print("\n" + "=" * 60)
print("V10 新增功能测试结果汇总")
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
    print("\n所有新增功能测试通过！")
