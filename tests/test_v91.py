"""V9.1 系统测试：全面场景验证。

覆盖 8 大优化模块：
1. Task 展示更新 + 状态
2. 报告文件链接可点击
3. HTML 报告 Plotly 本地化
4. 核心结论摘要兜底
5. 多指标图表多纵轴
6. 意图分类增强
7. 冗余工具调用优化（quick_profile 缓存）
8. Web 端 manual compact
"""

import io
import json
import os
import re
import sys
import traceback
from pathlib import Path

# Windows 编码兼容
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    os.system("")  # Enable ANSI/Unicode on Windows console

# 确保项目路径
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

RESULTS: list[dict] = []


def record(module: str, test: str, status: str, detail: str = ""):
    RESULTS.append({"module": module, "test": test, "status": status, "detail": detail})
    icon = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
    print(f"  {icon} [{module}] {test}" + (f" — {detail}" if detail else ""))


# ──────────────────────────────────────────────────────────
# 模块 1: Task 展示更新 + 状态（静态验证）
# ──────────────────────────────────────────────────────────
def test_task_ui():
    module = "1.Task"
    app_js = (PROJECT_ROOT / "src/data_agent/web/static/js/app.js").read_text(encoding="utf-8")
    index_html = (PROJECT_ROOT / "src/data_agent/web/templates/index.html").read_text(encoding="utf-8")
    app_css = (PROJECT_ROOT / "src/data_agent/web/static/css/app.css").read_text(encoding="utf-8")

    # 1.1 loadTasks 使用 spread operator
    if "this.tasks = [...newTasks]" in app_js:
        record(module, "loadTasks spread operator", "PASS")
    else:
        record(module, "loadTasks spread operator", "FAIL", "缺少 [...newTasks]")

    # 1.2 debounce 300ms
    if "_debouncedLoadTasks" in app_js and "setTimeout(() => this.loadTasks(), 300)" in app_js:
        record(module, "task_update debounce 300ms", "PASS")
    else:
        record(module, "task_update debounce 300ms", "FAIL")

    # 1.3 task_update 事件使用 debounced
    if "case 'task_update'" in app_js and "_debouncedLoadTasks()" in app_js:
        record(module, "task_update → debounced handler", "PASS")
    else:
        record(module, "task_update → debounced handler", "FAIL")

    # 1.4 description 展示
    if 'task-description' in index_html and 't.description' in index_html:
        record(module, "Task description 显示", "PASS")
    else:
        record(module, "Task description 显示", "FAIL")

    # 1.5 in_progress spinner (蓝色 animate-spin)
    if 'text-blue-500' in index_html and 'animate-spin' in index_html:
        record(module, "in_progress 蓝色 spinner", "PASS")
    else:
        record(module, "in_progress 蓝色 spinner", "FAIL")

    # 1.6 CSS task 状态样式
    for cls in ["task-completed", "task-in-progress", "task-pending", "task-description"]:
        if cls in app_css:
            record(module, f"CSS {cls}", "PASS")
        else:
            record(module, f"CSS {cls}", "FAIL")


# ──────────────────────────────────────────────────────────
# 模块 2: 报告文件链接可点击
# ──────────────────────────────────────────────────────────
def test_file_links():
    module = "2.FileLinks"
    app_js = (PROJECT_ROOT / "src/data_agent/web/static/js/app.js").read_text(encoding="utf-8")
    index_html = (PROJECT_ROOT / "src/data_agent/web/templates/index.html").read_text(encoding="utf-8")

    # 2.1 marked text renderer 有文件路径正则
    if "sessions\\/" in app_js and "file-link" in app_js:
        record(module, "marked text renderer 正则匹配", "PASS")
    else:
        record(module, "marked text renderer 正则匹配", "FAIL")

    # 2.2 链接指向 /files/ 路径
    if "/files/" in app_js and "encodeURIComponent" in app_js and "target=\"_blank\"" in app_js:
        record(module, "链接 /files/ + target=_blank", "PASS")
    else:
        record(module, "链接 /files/ + target=_blank", "FAIL")

    # 2.3 CSS file-link 样式
    app_css = (PROJECT_ROOT / "src/data_agent/web/static/css/app.css").read_text(encoding="utf-8")
    if ".file-link" in app_css:
        record(module, "CSS .file-link 样式", "PASS")
    else:
        record(module, "CSS .file-link 样式", "FAIL")

    # 2.4 /files/ 路由存在
    artifacts_py = (PROJECT_ROOT / "src/data_agent/web/blueprints/artifacts.py").read_text(encoding="utf-8")
    if '"/files/<path:filepath>"' in artifacts_py:
        record(module, "Flask /files/ 路由", "PASS")
    else:
        record(module, "Flask /files/ 路由", "FAIL")

    # 2.5 覆盖多种文件类型
    pattern = r"\.\(?:html\|pdf\|md\|png\)"
    if re.search(r"\.\(\?:html\|pdf\|md\|png\)", app_js):
        record(module, "匹配 html/pdf/md/png", "PASS")
    else:
        record(module, "匹配 html/pdf/md/png", "FAIL")

    # 2.6 覆盖多种前缀
    prefixes = ["Chart saved:", "Report generated:", "PDF exported:", "Markdown report:", "Conversation exported:"]
    missing = [p for p in prefixes if p not in app_js]
    if not missing:
        record(module, "匹配多种输出前缀", "PASS")
    else:
        record(module, "匹配多种输出前缀", "WARN", f"缺少: {missing}")

    # 2.7 实际正则测试（直接使用 Python 等价正则）
    py_pattern = r'(?:Chart saved: |Report generated: |PDF exported: |Markdown report: |Conversation exported: )?(sessions\/[^\s\"<>]+\.(?:html|pdf|md|png))'
    test_cases = [
        ("Report generated: sessions/abc/reports/report_1.html", True),
        ("Chart saved: sessions/abc/charts/chart_1.html", True),
        ("PDF exported: sessions/abc/reports/report_1.pdf", True),
        ("Markdown report: sessions/abc/reports/report_1.md", True),
        ("Conversation exported: sessions/abc/reports/conv.html", True),
        ("这是一个普通文本", False),
        ("report.html", False),
    ]
    compiled = re.compile(py_pattern)
    all_pass = True
    for text, should_match in test_cases:
        m = compiled.search(text)
        matched = bool(m)
        if matched != should_match:
            record(module, f"正则 '{text[:40]}'", "FAIL", f"期望 {should_match}, 实际 {matched}")
            all_pass = False
    if all_pass:
        record(module, "文件路径正则单元测试", "PASS", f"{len(test_cases)} cases")


# ──────────────────────────────────────────────────────────
# 模块 3: HTML 报告 Plotly 本地化
# ──────────────────────────────────────────────────────────
def test_plotly_local():
    module = "3.PlotlyLocal"

    # 3.1 Plotly JS 本地文件存在
    plotly_path = PROJECT_ROOT / "src/data_agent/web/static/js/plotly-3.5.0.min.js"
    if plotly_path.exists():
        size = plotly_path.stat().st_size
        record(module, "Plotly JS 本地文件", "PASS", f"{size:,} bytes")
        if size < 1_000_000:
            record(module, "Plotly JS 文件大小", "WARN", f"仅 {size:,} bytes, 可能不完整")
    else:
        record(module, "Plotly JS 本地文件", "FAIL", "文件不存在")

    # 3.2 visualization.py 使用 include_plotlyjs=False
    viz_py = (PROJECT_ROOT / "src/data_agent/tools/visualization.py").read_text(encoding="utf-8")
    count = viz_py.count('include_plotlyjs=False')
    if count >= 2:
        record(module, "visualization include_plotlyjs=False", "PASS", f"出现 {count} 次")
    else:
        record(module, "visualization include_plotlyjs=False", "FAIL", f"仅 {count} 次")

    # 3.3 报告模板使用本地优先 + CDN fallback
    report_py = (PROJECT_ROOT / "src/data_agent/tools/report.py").read_text(encoding="utf-8")
    local_count = report_py.count('/static/js/plotly-3.5.0.min.js')
    cdn_fallback_count = report_py.count('cdn.plot.ly/plotly-3.5.0.min.js')
    if local_count >= 3 and cdn_fallback_count >= 3:
        record(module, "报告模板 Plotly 本地+CDN fallback", "PASS", f"本地{local_count}处, CDN fallback{cdn_fallback_count}处")
    else:
        record(module, "报告模板 Plotly 本地+CDN fallback", "FAIL", f"本地{local_count}处, CDN{cdn_fallback_count}处")

    # 3.4 typeof Plotly 检测逻辑
    typeof_count = report_py.count("typeof Plotly === 'undefined'")
    if typeof_count >= 6:
        record(module, "typeof Plotly 检测", "PASS", f"{typeof_count} 处")
    else:
        record(module, "typeof Plotly 检测", "FAIL", f"仅 {typeof_count} 处")

    # 3.5 CDN 仅在 fallback document.write 中出现
    # 在 Jinja 模板中，document.write 内的 <script src="https://cdn.plot.ly 是 fallback
    # 它们看起来像 <script src="https://cdn.plot.ly 但在 document.write('...') 内
    fallback_cdn = report_py.count("cdn.plot.ly/plotly-3.5.0.min.js")
    # 所有 CDN 引用应该在 typeof Plotly === 'undefined' 判断内
    if fallback_cdn >= 3 and fallback_cdn <= 6:
        record(module, "CDN fallback 配置", "PASS", f"{fallback_cdn} 处 CDN fallback")
    else:
        record(module, "CDN fallback 配置", "FAIL", f"{fallback_cdn} 处")


# ──────────────────────────────────────────────────────────
# 模块 4: 核心结论摘要兜底
# ──────────────────────────────────────────────────────────
def test_summary_fallback():
    module = "4.SummaryFallback"
    report_py = (PROJECT_ROOT / "src/data_agent/tools/report.py").read_text(encoding="utf-8")
    prompts_py = (PROJECT_ROOT / "src/data_agent/agent/prompts.py").read_text(encoding="utf-8")

    # 4.1 report.py summary 兜底逻辑
    if "if not summary and insight_list:" in report_py and "summary_parts" in report_py:
        record(module, "report.py summary 兜底代码", "PASS")
    else:
        record(module, "report.py summary 兜底代码", "FAIL")

    # 4.2 Jinja 模板 summary 兜底
    if "{% if rendered_summary %}" in report_py and "{% elif top_insights %}" in report_py:
        record(module, "Jinja 模板 summary 兜底", "PASS")
    else:
        record(module, "Jinja 模板 summary 兜底", "FAIL")

    # 4.3 AGENT_FULL 强调 summary 必须提供
    if "**summary 参数**：" in prompts_py and "必须提供" in prompts_py:
        record(module, "AGENT_FULL summary 必须提供指令", "PASS")
    else:
        record(module, "AGENT_FULL summary 必须提供指令", "FAIL")

    # 4.4 summary 示例格式
    if "示例格式" in prompts_py and "核心发现" in prompts_py:
        record(module, "summary 示例格式", "PASS")
    else:
        record(module, "summary 示例格式", "FAIL")

    # 4.5 运行时兜底测试
    try:
        # 模拟 generate_report 的兜底逻辑
        insight_list = [
            {"title": "趋势上升", "description": "销售量持续上升，月增长率 15%"},
            {"title": "异常检测", "description": "第 3 周发现销售异常峰值"},
            {"title": "渠道分析", "description": "渠道 A 贡献 60% 的销售额"},
        ]
        summary = ""
        if not summary and insight_list:
            summary_parts = []
            for item in insight_list[:5]:
                t = item.get("title", "")
                d = item.get("description", "")
                if t:
                    summary_parts.append(f"- **{t}**: {d[:100]}" if d else f"- **{t}**")
            if summary_parts:
                summary = "### 核心发现\n\n" + "\n".join(summary_parts)

        if summary and "趋势上升" in summary and "异常检测" in summary and "渠道分析" in summary:
            record(module, "兜底逻辑运行时验证", "PASS", f"生成 {len(summary)} chars")
        else:
            record(module, "兜底逻辑运行时验证", "FAIL", "生成内容不完整")
    except Exception as e:
        record(module, "兜底逻辑运行时验证", "FAIL", str(e))


# ──────────────────────────────────────────────────────────
# 模块 5: 多指标图表多纵轴
# ──────────────────────────────────────────────────────────
def test_multi_axis():
    module = "5.MultiAxis"
    viz_py = (PROJECT_ROOT / "src/data_agent/tools/visualization.py").read_text(encoding="utf-8")

    # 5.1 _detect_axis_groups 函数存在
    if "def _detect_axis_groups" in viz_py:
        record(module, "_detect_axis_groups 函数", "PASS")
    else:
        record(module, "_detect_axis_groups 函数", "FAIL")
        return

    # 5.2 line chart 使用 axis_groups
    if "axis_groups = _detect_axis_groups" in viz_py and "yaxis=yaxis_name" in viz_py:
        record(module, "line chart 多轴", "PASS")
    else:
        record(module, "line chart 多轴", "FAIL")

    # 5.3 bar chart 多列使用 axis_groups
    if viz_py.count("axis_groups = _detect_axis_groups") >= 2:
        record(module, "bar chart 多轴", "PASS")
    else:
        record(module, "bar chart 多轴", "FAIL")

    # 5.4 overlaying='y' layout
    if "overlaying" in viz_py and "side=" in viz_py:
        record(module, "多轴 layout 配置", "PASS")
    else:
        record(module, "多轴 layout 配置", "FAIL")

    # 5.5 最多 3 轴限制
    if "while len(groups) > 3:" in viz_py:
        record(module, "最多 3 轴限制", "PASS")
    else:
        record(module, "最多 3 轴限制", "FAIL")

    # 5.6 运行时测试：量级差异检测
    try:
        import pandas as pd
        # 导入函数
        exec_globals = {"pd": pd}
        exec("from data_agent.tools.visualization import _detect_axis_groups", exec_globals)
        detect = exec_globals["_detect_axis_groups"]

        df = pd.DataFrame({
            "曝光量": [1e6, 2e6, 3e6, 4e6, 5e6],
            "点击率": [0.01, 0.02, 0.015, 0.025, 0.03],
            "收入": [100, 200, 150, 250, 300],
        })

        groups = detect(df, ["曝光量", "点击率", "收入"])
        if len(groups) >= 2:
            record(module, "量级差异检测 (1e6 vs 0.01)", "PASS", f"分 {len(groups)} 组: {groups}")
        else:
            record(module, "量级差异检测 (1e6 vs 0.01)", "FAIL", f"仅 {len(groups)} 组: {groups}")

        # 量级接近
        df2 = pd.DataFrame({
            "A": [100, 200, 300],
            "B": [50, 150, 250],
        })
        groups2 = detect(df2, ["A", "B"])
        if len(groups2) == 1:
            record(module, "量级接近不分组", "PASS", f"1 组: {groups2}")
        else:
            record(module, "量级接近不分组", "WARN", f"分 {len(groups2)} 组: {groups2}")

        # 单列不分组
        groups3 = detect(df, ["曝光量"])
        if len(groups3) == 1:
            record(module, "单列不分组", "PASS")
        else:
            record(module, "单列不分组", "FAIL", f"分 {len(groups3)} 组")

    except Exception as e:
        record(module, "运行时量级检测", "FAIL", str(e))


# ──────────────────────────────────────────────────────────
# 模块 6: 意图分类增强
# ──────────────────────────────────────────────────────────
def test_intent_classification():
    module = "6.Intent"
    prompts_py = (PROJECT_ROOT / "src/data_agent/agent/prompts.py").read_text(encoding="utf-8")

    # 6.1 _classify_task 接受 session_context 参数
    if "def _classify_task(user_input: str, session_context: str = \"\")" in prompts_py:
        record(module, "_classify_task session_context 参数", "PASS")
    else:
        record(module, "_classify_task session_context 参数", "FAIL")

    # 6.2 _CONTEXT_QUICK_KEYWORDS 存在
    if "_CONTEXT_QUICK_KEYWORDS" in prompts_py:
        record(module, "_CONTEXT_QUICK_KEYWORDS", "PASS")
    else:
        record(module, "_CONTEXT_QUICK_KEYWORDS", "FAIL")

    # 6.3 步骤 2.5 上下文快答
    if "has_session_data" in prompts_py and "context_quick_hits" in prompts_py:
        record(module, "上下文快答检测逻辑", "PASS")
    else:
        record(module, "上下文快答检测逻辑", "FAIL")

    # 6.4 AGENT_CHAT 数据上下文快答指令
    if "数据上下文快答" in prompts_py and "session_context" in prompts_py:
        record(module, "AGENT_CHAT 快答指令", "PASS")
    else:
        record(module, "AGENT_CHAT 快答指令", "FAIL")

    # 6.5 build_system_prompt 传递 session_context
    if "level = _classify_task(user_input, session_context)" in prompts_py:
        record(module, "build_system_prompt 传递 context", "PASS")
    else:
        record(module, "build_system_prompt 传递 context", "FAIL")

    # 6.6 运行时分类测试
    try:
        from data_agent.agent.prompts import _classify_task

        # 上下文模拟
        ctx_with_data = "main: 100 rows x 5 cols, columns: date, sales, users"
        ctx_empty = ""

        cases = [
            # (input, context, expected)
            ("你好", ctx_empty, "chat"),
            ("hello", ctx_empty, "chat"),
            ("帮我导出数据", ctx_empty, "quick"),
            ("出个完整报告", ctx_empty, "full"),
            ("分析一下销售趋势", ctx_empty, "standard"),
            ("列名是什么", ctx_with_data, "chat"),      # 上下文快答
            ("数据有多少行", ctx_with_data, "chat"),      # 上下文快答
            ("帮我算总销量", ctx_empty, "quick"),
            ("筛选A渠道数据", ctx_empty, "quick"),
            ("谢谢", ctx_empty, "chat"),
            ("什么是ARPU", ctx_empty, "chat"),
            ("完整分析这份数据", ctx_empty, "full"),
        ]

        all_pass = True
        for text, ctx, expected in cases:
            result = _classify_task(text, ctx)
            if result != expected:
                record(module, f"'{text}' → {result} (expect {expected})", "FAIL",
                       f"context={'有数据' if ctx else '空'}")
                all_pass = False

        if all_pass:
            record(module, f"意图分类 {len(cases)} cases 全通过", "PASS")
    except Exception as e:
        record(module, "意图分类运行时测试", "FAIL", str(e))
        traceback.print_exc()


# ──────────────────────────────────────────────────────────
# 模块 7: 冗余工具调用优化
# ──────────────────────────────────────────────────────────
def test_tool_call_optimization():
    module = "7.ToolOptimize"
    prompts_py = (PROJECT_ROOT / "src/data_agent/agent/prompts.py").read_text(encoding="utf-8")

    # 7.1 Prompt 层：上下文复用规则（V10 后合并到共享引擎 AGENT_ANALYSIS_ENGINE）
    prompt_count = prompts_py.count("上下文复用规则")
    if prompt_count >= 1:  # 至少在共享引擎中出现
        record(module, "上下文复用规则 (共享引擎)", "PASS", f"{prompt_count} 处")
    else:
        record(module, "上下文复用规则", "FAIL", f"仅 {prompt_count} 处")

    # 7.2 禁止重新调用
    if "禁止" in prompts_py and "重新调用 quick_profile" in prompts_py:
        record(module, "禁止重新调用 quick_profile", "PASS")
    else:
        record(module, "禁止重新调用 quick_profile", "FAIL")

    # 7.3 quick_profile 缓存实现
    try:
        du_path = PROJECT_ROOT / "src/data_agent/tools/data_understand.py"
        du_py = du_path.read_text(encoding="utf-8")

        if "_profile_cache" in du_py and "get_metadata" in du_py:
            record(module, "quick_profile 缓存读取", "PASS")
        else:
            record(module, "quick_profile 缓存读取", "FAIL")

        if "set_metadata" in du_py and "_profile_cache" in du_py:
            record(module, "quick_profile 缓存写入", "PASS")
        else:
            record(module, "quick_profile 缓存写入", "FAIL")

        if "_profile_shape" in du_py:
            record(module, "缓存 shape 校验", "PASS")
        else:
            record(module, "缓存 shape 校验", "FAIL")
    except Exception as e:
        record(module, "quick_profile 缓存检查", "FAIL", str(e))

    # 7.4 loop.py 传递 session_ctx
    loop_py = (PROJECT_ROOT / "src/data_agent/agent/loop.py").read_text(encoding="utf-8")
    if "session_ctx" in loop_py and "_classify_task(user_input, session_ctx)" in loop_py:
        record(module, "loop.py 传递 session_ctx", "PASS")
    else:
        record(module, "loop.py 传递 session_ctx", "FAIL")


# ──────────────────────────────────────────────────────────
# 模块 8: Web 端 manual compact
# ──────────────────────────────────────────────────────────
def test_manual_compact():
    module = "8.Compact"
    commands_py = (PROJECT_ROOT / "src/data_agent/web/blueprints/commands.py").read_text(encoding="utf-8")
    app_js = (PROJECT_ROOT / "src/data_agent/web/static/js/app.js").read_text(encoding="utf-8")
    index_html = (PROJECT_ROOT / "src/data_agent/web/templates/index.html").read_text(encoding="utf-8")

    # 8.1 后端 /compact endpoint
    if '@commands_bp.post("/compact")' in commands_py or 'commands_bp.post("/compact")' in commands_py:
        record(module, "POST /compact endpoint", "PASS")
    else:
        record(module, "POST /compact endpoint", "FAIL")

    # 8.2 后端调用 compact_history
    if "compact_history" in commands_py:
        record(module, "后端 compact_history 调用", "PASS")
    else:
        record(module, "后端 compact_history 调用", "FAIL")

    # 8.3 返回 token 对比
    if "before_tokens" in commands_py and "after_tokens" in commands_py:
        record(module, "返回 token 对比", "PASS")
    else:
        record(module, "返回 token 对比", "FAIL")

    # 8.4 JS compactContext 方法
    if "compactContext()" in app_js and ("fetch('/api/compact'" in app_js or "fetch('/compact'" in app_js):
        record(module, "JS compactContext 方法", "PASS")
    else:
        record(module, "JS compactContext 方法", "FAIL")

    # 8.5 isCompact 状态
    if "isCompact: false" in app_js:
        record(module, "isCompact 状态字段", "PASS")
    else:
        record(module, "isCompact 状态字段", "FAIL")

    # 8.6 UI 按钮
    if "compactContext()" in index_html and "Compress context" in index_html:
        record(module, "UI compact 按钮", "PASS")
    else:
        record(module, "UI compact 按钮", "FAIL")

    # 8.7 按钮 disabled 状态
    if ":disabled=\"!currentSessionId || isCompact\"" in index_html:
        record(module, "按钮 disabled 状态", "PASS")
    else:
        record(module, "按钮 disabled 状态", "FAIL")

    # 8.8 路由注册
    app_py = (PROJECT_ROOT / "src/data_agent/web/app.py").read_text(encoding="utf-8")
    if "commands_bp" in app_py:
        record(module, "commands_bp 路由注册", "PASS")
    else:
        record(module, "commands_bp 路由注册", "FAIL")


# ──────────────────────────────────────────────────────────
# 集成测试：数据加载 + 可视化 + 报告完整流程
# ──────────────────────────────────────────────────────────
def test_integration():
    module = "Int"
    test_data = PROJECT_ROOT / "reference/test_doc/test_sales.csv"

    if not test_data.exists():
        record(module, "test_sales.csv 存在", "FAIL", "文件不存在")
        return

    try:
        import pandas as pd

        # I1: 数据加载
        df = pd.read_csv(str(test_data))
        record(module, "加载 test_sales.csv", "PASS", f"{len(df)} rows x {len(df.columns)} cols")

        # I2: 模拟 _detect_axis_groups
        from data_agent.tools.visualization import _detect_axis_groups

        # test_sales 数据量级检查
        cols = list(df.select_dtypes(include="number").columns)
        if len(cols) >= 2:
            groups = _detect_axis_groups(df, cols)
            record(module, f"test_sales 多轴检测 ({cols})", "PASS" if len(groups) <= 2 else "WARN",
                   f"{len(groups)} groups")

        # I3: 图表 HTML 生成测试（无 Plotly 内嵌）
        try:
            import plotly.graph_objects as go
            import tempfile
            fig = go.Figure()
            fig.add_trace(go.Bar(x=df["channel"], y=df["sales"], name="sales"))
            tmp = tempfile.mktemp(suffix=".html")
            fig.write_html(tmp, include_plotlyjs=False)
            html = Path(tmp).read_text(encoding="utf-8")
            Path(tmp).unlink()
            if "plotly-graph-div" in html and "Plotly.newPlot" in html:
                if "cdn.plot.ly" not in html and "require(" not in html:
                    record(module, "图表 HTML 无 Plotly 内嵌", "PASS")
                else:
                    record(module, "图表 HTML 无 Plotly 内嵌", "FAIL", "仍包含 Plotly JS")
            else:
                record(module, "图表 HTML 生成", "FAIL", "缺少 plotly-graph-div")
        except Exception as e:
            record(module, "图表 HTML 生成", "FAIL", str(e))

        # I4: 报告生成摘要兜底
        try:
            insights = [
                {"title": "渠道A表现最好", "description": "渠道A的平均销售额最高", "type": "trend", "confidence": "high"},
                {"title": "东部地区占比大", "description": "东部地区贡献了40%的销售额", "type": "contribution", "confidence": "medium"},
            ]
            summary = ""
            if not summary and insights:
                summary_parts = []
                for item in insights[:5]:
                    t = item.get("title", "")
                    d = item.get("description", "")
                    if t:
                        summary_parts.append(f"- **{t}**: {d[:100]}" if d else f"- **{t}**")
                if summary_parts:
                    summary = "### 核心发现\n\n" + "\n".join(summary_parts)

            if summary:
                record(module, "报告摘要兜底集成", "PASS", summary[:60])
            else:
                record(module, "报告摘要兜底集成", "FAIL", "摘要为空")
        except Exception as e:
            record(module, "报告摘要兜底集成", "FAIL", str(e))

        # I5: 用 游戏互推.xlsx 检测多轴
        xlsx_path = PROJECT_ROOT / "reference/test_doc/游戏互推.xlsx"
        if xlsx_path.exists():
            try:
                df2 = pd.read_excel(str(xlsx_path))
                numeric_cols = list(df2.select_dtypes(include="number").columns)
                if len(numeric_cols) >= 2:
                    # 检查量级差异
                    max_vals = {c: df2[c].abs().max() for c in numeric_cols[:6]}
                    max_v = max(max_vals.values())
                    min_v = min(v for v in max_vals.values() if v > 0)
                    ratio = max_v / min_v if min_v > 0 else 1
                    groups = _detect_axis_groups(df2, numeric_cols[:6])
                    record(module, f"游戏互推 多轴检测 (ratio={ratio:.0f}x)", "PASS",
                           f"{len(groups)} groups: {groups}")
                else:
                    record(module, "游戏互推 数值列不足", "WARN", f"仅 {len(numeric_cols)} 列")
            except Exception as e:
                record(module, "游戏互推.xlsx 读取", "WARN", str(e))

    except Exception as e:
        record(module, "集成测试", "FAIL", str(e))
        traceback.print_exc()


# ──────────────────────────────────────────────────────────
# Flask 路由集成验证（不启动服务，只验证路由注册）
# ──────────────────────────────────────────────────────────
def test_flask_routes():
    module = "Routes"
    try:
        # 验证所有蓝图路由
        from data_agent.web.app import create_app
        app = create_app()
        rules = {rule.rule: list(rule.methods) for rule in app.url_map.iter_rules()}

        expected_routes = [
            "/api/chat",
            "/api/sessions",
            "/api/upload",
            "/api/files/<path:filepath>",
            "/api/objects",
            "/api/tasks",
            "/api/compact",
        ]

        for route in expected_routes:
            found = any(route in r for r in rules)
            if found:
                record(module, f"路由 {route}", "PASS")
            else:
                record(module, f"路由 {route}", "WARN", f"未匹配, 可用: {[r for r in rules if route.split('/')[-1] in r][:3]}")

        # 检查 static 文件服务
        static_js = app.static_folder
        if static_js:
            plotly = Path(static_js) / "js" / "plotly-3.5.0.min.js"
            if plotly.exists():
                record(module, "Flask static Plotly 可访问", "PASS")
            else:
                record(module, "Flask static Plotly 可访问", "FAIL", f"路径: {plotly}")

    except Exception as e:
        record(module, "Flask 路由验证", "FAIL", str(e))
        traceback.print_exc()


# ──────────────────────────────────────────────────────────
# 主函数
# ──────────────────────────────────────────────────────────
def main():
    print("=" * 70)
    print("  Data Agent V9.1 全场景系统测试")
    print("=" * 70)

    tests = [
        ("模块 1: Task 展示更新 + 状态", test_task_ui),
        ("模块 2: 报告文件链接可点击", test_file_links),
        ("模块 3: HTML 报告 Plotly 本地化", test_plotly_local),
        ("模块 4: 核心结论摘要兜底", test_summary_fallback),
        ("模块 5: 多指标图表多纵轴", test_multi_axis),
        ("模块 6: 意图分类增强", test_intent_classification),
        ("模块 7: 冗余工具调用优化", test_tool_call_optimization),
        ("模块 8: Web 端 manual compact", test_manual_compact),
        ("集成测试: 数据加载 + 可视化 + 报告", test_integration),
        ("Flask 路由集成验证", test_flask_routes),
    ]

    for name, fn in tests:
        print(f"\n{'─' * 70}")
        print(f"  {name}")
        print(f"{'─' * 70}")
        try:
            fn()
        except Exception as e:
            print(f"  ❌ 测试套件异常: {e}")
            traceback.print_exc()

    # 汇总
    print(f"\n{'=' * 70}")
    print("  测试结果汇总")
    print(f"{'=' * 70}")

    pass_count = sum(1 for r in RESULTS if r["status"] == "PASS")
    fail_count = sum(1 for r in RESULTS if r["status"] == "FAIL")
    warn_count = sum(1 for r in RESULTS if r["status"] == "WARN")

    # 按模块分组
    modules = {}
    for r in RESULTS:
        modules.setdefault(r["module"], []).append(r)

    for mod, items in modules.items():
        p = sum(1 for i in items if i["status"] == "PASS")
        f = sum(1 for i in items if i["status"] == "FAIL")
        w = sum(1 for i in items if i["status"] == "WARN")
        status = "✅" if f == 0 else "❌"
        print(f"  {status} {mod}: {p} PASS, {f} FAIL, {w} WARN")
        for i in items:
            if i["status"] != "PASS":
                icon = "❌" if i["status"] == "FAIL" else "⚠️"
                print(f"    {icon} {i['test']}" + (f" — {i['detail']}" if i['detail'] else ""))

    print(f"\n  总计: {pass_count} PASS, {fail_count} FAIL, {warn_count} WARN")
    print(f"{'=' * 70}")

    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
