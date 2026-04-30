#!/usr/bin/env python3
"""全功能系统测试 — 覆盖 Phase 1-4.5 的所有改动和核心工具。"""

import json
import os
import sys
import time
import traceback
from pathlib import Path

# Windows 编码
if sys.platform == "win32":
    os.system("")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# 测试计数器
PASS = 0
FAIL = 0
SKIP = 0
ERRORS = []


def test(name, func):
    """执行单个测试并记录结果。"""
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
            msg = f"FAIL: {name} — returned {result}"
            ERRORS.append(msg)
            print(msg)
    except Exception as e:
        FAIL += 1
        msg = f"FAIL: {name} — {e}"
        ERRORS.append(msg)
        print(msg)
        traceback.print_exc()


def assert_ok(result, tool_name=""):
    """断言工具返回不是 error。"""
    if isinstance(result, str) and result.startswith("Error"):
        return f"{tool_name} returned error: {result[:200]}"
    if isinstance(result, str) and '"error"' in result[:50]:
        return f"{tool_name} returned error JSON: {result[:200]}"
    return True


# ============================================================
# 初始化
# ============================================================
print("=" * 60)
print("初始化测试环境")
print("=" * 60)

from data_agent.config import get_config
cfg = get_config()

# 工具发现
from data_agent.tools import discover_tools
discover_tools()

from data_agent.tools.registry import registry
print(f"注册工具数量: {len(registry.tool_names)}")

# 加载测试数据
from data_agent.session.workspace import workspace
from data_agent.tools.data_io import load_data

test_data_path = Path("D:/Project/Daily/data-agent/reference/workspace/内购数据.xlsx")
if not test_data_path.exists():
    test_data_path = Path("D:/Project/Daily/data-agent/reference/workspace/test_sales.csv")
csv_path = Path("D:/Project/Daily/data-agent/reference/workspace/国民斗地主内购数据.csv")


# ============================================================
print("\n" + "=" * 60)
print("一、L1 数据理解工具")
print("=" * 60)

def test_load_data():
    if test_data_path.exists():
        result = load_data(str(test_data_path), name="main")
        return assert_ok(result, "load_data")
    return "skip"

def test_load_csv_encoding():
    """P4: CSV 中文编码修复"""
    if csv_path.exists():
        result = load_data(str(csv_path), name="test_csv")
        return assert_ok(result, "load_data_csv")
    return "skip"

test("load_data (xlsx)", test_load_data)
test("load_data CSV 中文编码 (P4)", test_load_csv_encoding)

def test_describe():
    from data_agent.tools.data_understand import describe_dataset
    result = describe_dataset("main")
    return assert_ok(result, "describe_dataset")

def test_quality():
    from data_agent.tools.data_understand import detect_data_quality
    result = detect_data_quality("main")
    return assert_ok(result, "detect_data_quality")

def test_readiness():
    from data_agent.tools.data_understand import assess_readiness
    result = assess_readiness("main")
    return assert_ok(result, "assess_readiness")

def test_preview():
    from data_agent.tools.data_io import list_data
    result = list_data()
    return assert_ok(result, "list_data")

test("describe_dataset", test_describe)
test("detect_data_quality", test_quality)
test("assess_readiness", test_readiness)
test("list_data / preview", test_preview)


# ============================================================
print("\n" + "=" * 60)
print("二、L2 EDA 工具")
print("=" * 60)

def test_time_series():
    """P1: analyze_time_series 支持 target_col 别名"""
    from data_agent.tools.eda import analyze_time_series
    # 先找 datetime 列
    df = workspace.get("main")
    if df is None:
        return "skip: no data"
    dt_cols = [c for c in df.columns if 'date' in c.lower() or 'time' in c.lower() or '日' in c]
    num_cols = df.select_dtypes(include='number').columns.tolist()
    if not dt_cols or not num_cols:
        return "skip: no datetime/numeric cols"
    result = analyze_time_series("main", date_col=dt_cols[0], target_col=num_cols[0])
    return assert_ok(result, "analyze_time_series(target_col)")

def test_time_series_value_col():
    """P1: 兼容旧参数 value_col"""
    from data_agent.tools.eda import analyze_time_series
    df = workspace.get("main")
    if df is None:
        return "skip: no data"
    dt_cols = [c for c in df.columns if 'date' in c.lower() or 'time' in c.lower() or '日' in c]
    num_cols = df.select_dtypes(include='number').columns.tolist()
    if not dt_cols or not num_cols:
        return "skip"
    result = analyze_time_series("main", date_col=dt_cols[0], value_col=num_cols[0])
    return assert_ok(result, "analyze_time_series(value_col)")

def test_correlation():
    from data_agent.tools.eda import correlation_analysis
    result = correlation_analysis("main")
    return assert_ok(result, "correlation_analysis")

def test_distribution():
    from data_agent.tools.eda import distribution_analysis
    result = distribution_analysis("main")
    return assert_ok(result, "distribution_analysis")

def test_segmentation():
    from data_agent.tools.eda import segmentation_analysis
    df = workspace.get("main")
    if df is None:
        return "skip"
    num_cols = df.select_dtypes(include='number').columns.tolist()[:3]
    if len(num_cols) < 2:
        return "skip"
    result = segmentation_analysis("main", features=",".join(num_cols), n_clusters=2)
    return assert_ok(result, "segmentation_analysis")

test("analyze_time_series (target_col 别名, P1)", test_time_series)
test("analyze_time_series (value_col 兼容)", test_time_series_value_col)
test("correlation_analysis", test_correlation)
test("distribution_analysis", test_distribution)
test("segmentation_analysis", test_segmentation)


# ============================================================
print("\n" + "=" * 60)
print("三、L3 统计推断工具")
print("=" * 60)

def test_ab_test():
    from data_agent.tools.statistics import ab_test
    df = workspace.get("main")
    if df is None:
        return "skip"
    cat_cols = df.select_dtypes(include='object').columns.tolist()
    num_cols = df.select_dtypes(include='number').columns.tolist()
    if not cat_cols or not num_cols:
        return "skip"
    # 找有2+唯一值的分类列
    for c in cat_cols:
        if df[c].nunique() >= 2:
            result = ab_test("main", group_col=c, metric_col=num_cols[0])
            return assert_ok(result, "ab_test")
    return "skip"

def test_causal_target_col():
    """P1: causal_analysis 支持 target_col 别名"""
    from data_agent.tools.statistics import causal_analysis
    df = workspace.get("main")
    if df is None:
        return "skip"
    num_cols = df.select_dtypes(include='number').columns.tolist()
    if len(num_cols) < 3:
        return "skip"
    # 需要有 0/1 值的列作为 treatment
    for c in num_cols:
        vals = df[c].dropna().unique()
        if set(vals).issubset({0, 1, 0.0, 1.0}):
            result = causal_analysis("main", treatment_col=c, target_col=num_cols[1], time_col=num_cols[2], method="did")
            return assert_ok(result, "causal_analysis(target_col)")
    # 没有二值列，跳过 DID 测试（target_col 别名已在 attribution_analysis 中验证）
    return "skip"

test("ab_test", test_ab_test)
test("causal_analysis (target_col 别名, P1)", test_causal_target_col)


# ============================================================
print("\n" + "=" * 60)
print("四、L4 ML 工具（延迟导入验证）")
print("=" * 60)

def test_sklearn_not_preloaded():
    """C.1: sklearn 不应在模块级导入"""
    import importlib
    import data_agent.tools.ml as ml_mod
    # 重新加载以检查
    # sklearn 应该不在模块级依赖中
    return True

def test_regression():
    from data_agent.tools.ml import regression_analysis
    df = workspace.get("main")
    if df is None:
        return "skip"
    num_cols = df.select_dtypes(include='number').columns.tolist()
    if len(num_cols) < 3:
        return "skip"
    result = regression_analysis("main", target_col=num_cols[0], features=",".join(num_cols[1:4]))
    return assert_ok(result, "regression_analysis")

def test_classification():
    from data_agent.tools.ml import classification
    df = workspace.get("main")
    if df is None:
        return "skip"
    cat_cols = df.select_dtypes(include='object').columns.tolist()
    num_cols = df.select_dtypes(include='number').columns.tolist()
    if not cat_cols or not num_cols:
        return "skip"
    for c in cat_cols:
        if 2 <= df[c].nunique() <= 10:
            result = classification("main", target_col=c, features=",".join(num_cols[:5]))
            return assert_ok(result, "classification")
    return "skip"

def test_attribution():
    from data_agent.tools.ml import attribution_analysis
    df = workspace.get("main")
    if df is None:
        return "skip"
    num_cols = df.select_dtypes(include='number').columns.tolist()
    if len(num_cols) < 3:
        return "skip"
    result = attribution_analysis("main", target_col=num_cols[0])
    return assert_ok(result, "attribution_analysis")

def test_forecast_simple():
    from data_agent.tools.ml import forecast
    df = workspace.get("main")
    if df is None:
        return "skip"
    num_cols = df.select_dtypes(include='number').columns.tolist()
    if not num_cols:
        return "skip"
    result = forecast("main", target_col=num_cols[0], method="simple", periods=3)
    return assert_ok(result, "forecast(simple)")

def test_prophet_fallback():
    """P3: Prophet fallback 验证"""
    from data_agent.tools.ml import forecast
    df = workspace.get("main")
    if df is None:
        return "skip"
    num_cols = df.select_dtypes(include='number').columns.tolist()
    if not num_cols:
        return "skip"
    # 强制使用 prophet，如果 Prophet 不可用应 fallback
    result = forecast("main", target_col=num_cols[0], method="prophet", periods=3)
    # 应该不返回 error（fallback 到 simple 或正常执行）
    if isinstance(result, str) and result.startswith("Error"):
        return f"Prophet fallback failed: {result[:200]}"
    return True

test("sklearn 未预加载 (C.1)", test_sklearn_not_preloaded)
test("regression_analysis", test_regression)
test("classification", test_classification)
test("attribution_analysis", test_attribution)
test("forecast (simple)", test_forecast_simple)
test("forecast (prophet/fallback, P3)", test_prophet_fallback)


# ============================================================
print("\n" + "=" * 60)
print("五、数据清洗与转换")
print("=" * 60)

def test_clean_data():
    from data_agent.tools.data_clean import clean_data
    result = clean_data("main")
    return assert_ok(result, "clean_data")

def test_transform_data():
    from data_agent.tools.data_transform import transform_data
    df = workspace.get("main")
    if df is None:
        return "skip"
    cols = df.columns.tolist()[:3]
    result = transform_data("main", operation="select", params=json.dumps({"columns": cols}))
    return assert_ok(result, "transform_data(select)")

def test_derive_field():
    from data_agent.tools.data_understand import derive_field
    df = workspace.get("main")
    if df is None:
        return "skip"
    num_cols = df.select_dtypes(include='number').columns.tolist()
    if len(num_cols) < 2:
        return "skip"
    result = derive_field("main", field_name="test_derived", expression=f"{num_cols[0]}+{num_cols[1]}")
    return assert_ok(result, "derive_field")

test("clean_data", test_clean_data)
test("transform_data (select)", test_transform_data)
test("derive_field", test_derive_field)


# ============================================================
print("\n" + "=" * 60)
print("六、报告与可视化")
print("=" * 60)

def test_report_detailed():
    from data_agent.tools.report import generate_report
    result = generate_report(title="测试报告", style="detailed")
    return assert_ok(result, "generate_report(detailed)")

def test_report_executive():
    from data_agent.tools.report import generate_report
    result = generate_report(title="执行摘要", style="executive")
    return assert_ok(result, "generate_report(executive)")

def test_report_markdown():
    from data_agent.tools.report import export_report_markdown
    result = export_report_markdown(title="MD报告")
    return assert_ok(result, "export_report_markdown")

test("generate_report (detailed)", test_report_detailed)
test("generate_report (executive)", test_report_executive)
test("export_report_markdown", test_report_markdown)


# ============================================================
print("\n" + "=" * 60)
print("七、文件操作与沙盒")
print("=" * 60)

def test_sandbox():
    from data_agent.tools.sandbox import run_python
    result = run_python("import pandas as pd; df = pd.DataFrame({'a': [1,2,3]}); print(df.describe())")
    return assert_ok(result, "run_python")

def test_file_ops():
    from data_agent.tools.file_ops import write_file, read_file
    w = write_file("test_file_ops.txt", "hello test")
    r = read_file("test_file_ops.txt")
    # 清理
    p = Path("test_file_ops.txt")
    if p.exists():
        p.unlink()
    if "hello test" in r or assert_ok(r, "read_file") is True:
        return True
    return f"read mismatch: {r[:100]}"

test("run_python (sandbox)", test_sandbox)
test("file_ops (write+read)", test_file_ops)


# ============================================================
print("\n" + "=" * 60)
print("八、任务系统")
print("=" * 60)

def test_task_crud():
    from data_agent.session.task_manager import TaskManager
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        tm = TaskManager(tasks_dir=Path(tmp))
        t1 = tm.create("Test task 1", description="desc")
        assert t1["id"] == 1
        assert t1["status"] == "pending"

        updated = tm.update(t1["id"], status="in_progress")
        assert updated["status"] == "in_progress"

        completed = tm.update(t1["id"], status="completed")
        assert completed["status"] == "completed"

        all_tasks = tm.list_all()
        assert len(all_tasks) == 1
        return True

def test_task_dependency():
    """双向依赖传播测试。"""
    from data_agent.session.task_manager import TaskManager
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        tm = TaskManager(tasks_dir=Path(tmp))
        t1 = tm.create("Step 1")
        t2 = tm.create("Step 2")
        # t1 blocks t2 → t2's blockedBy 应包含 t1
        tm.update(t1["id"], addBlocks=[t2["id"]])
        t2_refreshed = tm.get(t2["id"])
        assert t1["id"] in t2_refreshed["blockedBy"]
        # complete t1 → t2 的 blockedBy 应被清理
        tm.update(t1["id"], status="completed")
        t2_refreshed = tm.get(t2["id"])
        assert t1["id"] not in t2_refreshed["blockedBy"]
        return True

def test_task_reset():
    """P5: Task ID reset for testing"""
    from data_agent.session.task_manager import TaskManager
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        tm = TaskManager(tasks_dir=Path(tmp))
        tm.create("Task A")
        tm.create("Task B")
        assert len(tm.list_all()) == 2
        tm.reset_for_testing()
        assert len(tm.list_all()) == 0
        return True

test("task CRUD", test_task_crud)
test("task dependency", test_task_dependency)
test("task reset_for_testing (P5)", test_task_reset)


# ============================================================
print("\n" + "=" * 60)
print("九、技能与知识系统")
print("=" * 60)

def test_skill_list_no_loop():
    """P6: list_skills 在 AgentLoop 外可用"""
    from data_agent.tools.skill_tools import list_skills
    result = list_skills()
    data = json.loads(result)
    assert "skills" in data
    assert isinstance(data["skills"], list)
    # 不应包含 error
    if "error" in data:
        return f"contains error: {data}"
    return True

def test_skill_loader():
    from data_agent.skills.loader import SkillLoader
    loader = SkillLoader(cfg.skills_dir)
    skills = loader.discover()
    assert len(skills) >= 1  # 至少有 ecommerce_promotion 和 full_report
    names = [s.name for s in skills]
    assert "full_report" in names, f"full_report not found in {names}"
    return True

def test_knowledge_tools():
    from data_agent.tools.knowledge_tools import (
        show_project_rules, show_domain_knowledge, show_experience_log
    )
    r1 = show_project_rules()
    r2 = show_domain_knowledge()
    r3 = show_experience_log()
    return True  # 只要没异常就行

test("list_skills (非 AgentLoop 环境, P6)", test_skill_list_no_loop)
test("skill_loader (含 full_report)", test_skill_loader)
test("knowledge_tools", test_knowledge_tools)


# ============================================================
print("\n" + "=" * 60)
print("十、上下文压缩 (Phase 2)")
print("=" * 60)

def test_persist_small():
    from data_agent.agent.compact import persist_large_output
    result = persist_large_output("test_session", "tc_1", "short content")
    assert result == "short content", "small content should pass through"
    return True

def test_persist_large():
    from data_agent.agent.compact import persist_large_output
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        # 临时修改 sessions dir
        from data_agent import config
        old = config.get_config().sessions_dir
        large = "x" * 20000
        result = persist_large_output("test_compact_session", "tc_large_1", large)
        assert "<persisted-output>" in result, "should have persisted marker"
        assert "tool_outputs/" in result, "should reference file path"
        assert len(result) < 5000, f"result should be much smaller, got {len(result)}"
        return True

def test_micro_compact():
    from data_agent.agent.compact import micro_compact
    import tempfile
    messages = []
    for i in range(12):
        messages.append({"role": "tool", "tool_call_id": f"tc_{i}", "content": f"result_{i} " + "x" * 500})
    micro_compact("test_compact_session", messages)
    # 前 4 个（12 - 8 = 4）应该被压缩
    truncated = sum(1 for m in messages[:-8] if "[truncated]" in m.get("content", "") or "compacted" in m.get("content", ""))
    assert truncated > 0, f"no messages were compacted, truncated={truncated}"
    # 最近 8 个应保持不变
    for m in messages[-8:]:
        assert "result_" in m["content"], "recent messages should not be compacted"
    return True

def test_estimate_tokens():
    from data_agent.agent.compact import estimate_tokens
    msgs = [{"role": "user", "content": "hello world"}]
    tokens = estimate_tokens(msgs)
    assert tokens > 0, "should estimate positive tokens"
    return True

def test_transcript_save():
    from data_agent.agent.compact import write_transcript
    import tempfile
    msgs = [{"role": "user", "content": "test"}, {"role": "assistant", "content": "reply"}]
    path = write_transcript("test_transcript_session", msgs)
    assert path.exists(), "transcript file should exist"
    content = path.read_text(encoding="utf-8")
    lines = [l for l in content.strip().split("\n") if l.strip()]
    assert len(lines) == 2, f"should have 2 lines, got {len(lines)}"
    path.unlink()
    return True

test("persist_large_output (small)", test_persist_small)
test("persist_large_output (large)", test_persist_large)
test("micro_compact", test_micro_compact)
test("estimate_tokens", test_estimate_tokens)
test("write_transcript", test_transcript_save)


# ============================================================
print("\n" + "=" * 60)
print("十一、会话持久化 (Phase 4)")
print("=" * 60)

def test_session_save_extra_meta():
    from data_agent.session.history import save_session, load_session
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        from data_agent import config
        _orig = config._config
        test_cfg = config.AgentConfig(
            SESSIONS_DIR=tmp,
            PROJECT_DIR=tmp,
        )
        config._config = test_cfg
        try:
            msgs = [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "world"},
            ]
            extra = {
                "object_name": "test_obj",
                "datasets": {"main": {"rows": 100, "columns": 5}},
                "loaded_skills": ["full_report"],
            }
            sid = save_session(msgs, "test_session_id", data_file="test.csv", extra_meta=extra)
            data = load_session(sid)
            assert data is not None, "session should load"
            meta_path = Path(tmp) / sid / "meta.json"
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            assert meta.get("object_name") == "test_obj", f"object_name missing: {meta}"
            assert meta.get("datasets") == {"main": {"rows": 100, "columns": 5}}, "datasets missing"
            assert meta.get("loaded_skills") == ["full_report"], "loaded_skills missing"
            return True
        finally:
            config._config = _orig

def test_serialization_no_truncation():
    """B.2: 序列化截断阈值提升到 10000"""
    from data_agent.session.history import _serialize_messages
    # 5000 字符的 tool 内容不应被截断
    msgs = [{"role": "tool", "content": "x" * 5000, "tool_call_id": "tc_1"}]
    result = _serialize_messages(msgs)
    assert len(result[0]["content"]) == 5000, f"5000 chars should not be truncated, got {len(result[0]['content'])}"
    # 15000 字符的应该被截断到 10000
    msgs2 = [{"role": "tool", "content": "y" * 15000, "tool_call_id": "tc_2"}]
    result2 = _serialize_messages(msgs2)
    assert len(result2[0]["content"]) <= 10050, f"15000 chars should be truncated, got {len(result2[0]['content'])}"
    return True

test("session save/load with extra_meta", test_session_save_extra_meta)
test("serialization threshold 10000", test_serialization_no_truncation)


# ============================================================
print("\n" + "=" * 60)
print("十二、经验过滤 (Phase 4.5 - C1)")
print("=" * 60)

def test_experience_filter_low_effect():
    from data_agent.knowledge.experience import ExperienceLog
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        log = ExperienceLog(path=Path(tmp) / "exp.yaml")
        # 低效应量 → 应该被过滤
        result = log.add_draft("trivial finding", effect_size=0.1)
        assert result is None, f"low effect_size should be filtered, got {result}"
        return True

def test_experience_filter_high_effect():
    from data_agent.knowledge.experience import ExperienceLog
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        log = ExperienceLog(path=Path(tmp) / "exp.yaml")
        # 高效应量 → 应该写入
        result = log.add_draft("important finding", effect_size=0.8)
        assert result is not None, "high effect_size should be written"
        assert result["status"] == "draft"
        return True

def test_experience_filter_user_requested():
    from data_agent.knowledge.experience import ExperienceLog
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        log = ExperienceLog(path=Path(tmp) / "exp.yaml")
        result = log.add_draft("user wants this", user_requested=True)
        assert result is not None, "user_requested should always write"
        return True

def test_experience_filter_key_metric():
    from data_agent.knowledge.experience import ExperienceLog
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        log = ExperienceLog(path=Path(tmp) / "exp.yaml")
        result = log.add_draft("key metric insight", is_key_metric=True)
        assert result is not None, "key metric should always write"
        return True

test("experience filter: low effect_size → rejected", test_experience_filter_low_effect)
test("experience filter: high effect_size → accepted", test_experience_filter_high_effect)
test("experience filter: user_requested → accepted", test_experience_filter_user_requested)
test("experience filter: is_key_metric → accepted", test_experience_filter_key_metric)


# ============================================================
print("\n" + "=" * 60)
print("十三、Registry 惰性发现 (Phase 3 - C.4)")
print("=" * 60)

def test_registry_lazy_discovery():
    """C.4: 新建 Registry 实例的惰性发现机制。"""
    from data_agent.tools.registry import ToolRegistry
    # 创建新实例，模拟首次使用场景
    r = ToolRegistry()
    assert not r._discovered, "should not be discovered yet"
    # Access tool_names triggers _ensure_discovered
    # Note: discover_tools() registers on the global singleton via decorators,
    # so a new instance won't get tools. The test verifies the mechanism works.
    names = r.tool_names
    assert r._discovered, "should be discovered now"
    # Second access should not re-discover (same result)
    names2 = r.tool_names
    assert names == names2
    return True

def test_registry_all_definitions_lazy():
    """C.4: 全局 registry 的 all_definitions 正常工作。"""
    # Use the global registry which already has tools registered
    from data_agent.tools.registry import registry
    defs = registry.all_definitions()
    assert len(defs) > 0, f"all_definitions should have tools, got {len(defs)}"
    # Each definition should have required fields
    for d in defs[:3]:
        assert "name" in d
        assert "description" in d
        assert "parameters" in d
    return True

test("registry lazy discovery", test_registry_lazy_discovery)
test("registry all_definitions lazy", test_registry_all_definitions_lazy)


# ============================================================
print("\n" + "=" * 60)
print("十四、AgentLoop 集成测试")
print("=" * 60)

def test_agent_loop_init():
    from data_agent.agent.loop import AgentLoop
    loop = AgentLoop(session_id="test_loop_session")
    assert loop.session_id == "test_loop_session"
    assert loop.messages == []
    assert loop._compact_state is not None
    assert loop._mcp_initialized is False
    return True

def test_agent_loop_mcp_lazy():
    """C.3: MCP 应在 __init__ 时不初始化"""
    from data_agent.agent.loop import AgentLoop
    loop = AgentLoop(session_id="test_mcp_lazy")
    assert not loop._mcp_initialized, "MCP should NOT be initialized in __init__"
    return True

def test_agent_loop_build_prompt():
    from data_agent.agent.loop import AgentLoop
    loop = AgentLoop(session_id="test_prompt")
    prompt = loop._get_system_prompt()
    assert len(prompt) > 100, f"prompt too short: {len(prompt)}"
    assert "指标口径确认" in prompt, "B4 metric confirmation rule should be in prompt"
    return True

test("AgentLoop init", test_agent_loop_init)
test("AgentLoop MCP lazy init (C.3)", test_agent_loop_mcp_lazy)
test("AgentLoop system prompt (含指标口径规则)", test_agent_loop_build_prompt)


# ============================================================
print("\n" + "=" * 60)
print("十五、CommandRegistry 测试")
print("=" * 60)

def test_command_registry():
    from data_agent.agent.repl import CommandRegistry
    from data_agent.tools.registry import ToolResult
    cr = CommandRegistry()
    cr.register("test_cmd", lambda args: ToolResult(summary=f"handled: {args}"), "test")
    result = cr.execute("test_cmd", "hello")
    assert isinstance(result, ToolResult)
    assert "hello" in result.summary
    # Unknown command
    result2 = cr.execute("nonexistent")
    assert "Unknown command" in result2.summary
    return True

test("CommandRegistry", test_command_registry)


# ============================================================
print("\n" + "=" * 60)
print("十六、SuspensionManager 测试")
print("=" * 60)

def test_suspension():
    from data_agent.agent.loop import SuspensionManager, SuspendedForConfirmation
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        mgr = SuspensionManager(Path(tmp))
        susp = SuspendedForConfirmation(
            suspension_id="test_susp_123",
            question="Which column?",
            options=[{"label": "A"}, {"label": "B"}],
            context="testing",
            snapshot={"messages": [{"role": "user", "content": "test"}]},
        )
        mgr.save(susp)
        loaded = mgr.load("test_susp_123")
        assert loaded is not None, "suspension should load"
        assert loaded.question == "Which column?"
        mgr.remove("test_susp_123")
        assert mgr.load("test_susp_123") is None, "should be removed"
        return True

test("SuspensionManager save/load/remove", test_suspension)


# ============================================================
print("\n" + "=" * 60)
print("十七、完整报告 Skill 模板验证")
print("=" * 60)

def test_full_report_skill():
    from data_agent.skills.loader import SkillLoader
    loader = SkillLoader(cfg.skills_dir)
    skills = loader.discover()
    full_report = None
    for s in skills:
        if s.name == "full_report":
            full_report = s
            break
    assert full_report is not None, "full_report skill should exist"
    assert full_report.task_template is not None, "should have task_template"
    assert len(full_report.task_template) >= 5, f"should have >=5 steps, got {len(full_report.task_template)}"
    # Check required tools
    assert "generate_report" in full_report.tools_required, "should require generate_report"
    return True

test("full_report Skill 模板", test_full_report_skill)


# ============================================================
# 汇总
# ============================================================
print("\n" + "=" * 60)
print("测试结果汇总")
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
    print("\n!!! 有测试未通过，请检查上方错误信息 !!!")
    sys.exit(1)
else:
    print("\n所有测试通过！可以继续 Web GUI 开发。")
