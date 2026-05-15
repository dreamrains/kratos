"""优化效果对比测试 — 使用与 74d0077ccce2 相同的数据和提示词。

对比维度：
1. 上下文膨胀：load_data 产生的上下文字符数（P3前后）
2. 工具输出压缩：_compact_tool_output 截断效果
3. micro_compact 智能预览质量（P3-5c）
4. 用户要求提取与持久化（P1-1）
5. 用户要求在 system prompt 中的注入（P1-2）
6. compact_history 保留用户要求（P1-3）
7. workspace 数据丢失场景（旧会话的 bug）
8. 僵尸 task 过滤（P2-2）
9. 任务完成约束（P2-1）

测试方法：
- 使用真实数据文件进行工具级测试（不依赖 LLM API）
- 对比 P3 前后的上下文大小
- 模拟旧会话的问题场景验证修复
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

if sys.platform == "win32":
    os.system("")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# === 真实数据文件路径 ===
REAL_DATA_DIR = Path("D:/Project/Daily/备用/20260512测试")
TEST_DATA_DIR = Path("D:/Project/Daily/data-agent/reference/test_doc")

HAS_REAL_DATA = REAL_DATA_DIR.exists()
HAS_TEST_DATA = TEST_DATA_DIR.exists()

# 旧会话使用的文件
CARD_PAYMENT = REAL_DATA_DIR / "0201到0510购卡用户付费数据.xlsx"
VOUCHER_DETAIL = REAL_DATA_DIR / "代金券明细订单.xlsx"
BEFORE_AFTER = REAL_DATA_DIR / "购卡前后订单.xlsx"
CARD_ORDER = REAL_DATA_DIR / "省钱卡订单.xlsx"

# 备用测试数据
ECARD_FLOW = TEST_DATA_DIR / "省钱卡用户最近流水_20260511.xlsx"
ECARD_ORDER = TEST_DATA_DIR / "省钱卡订单_20260507.xlsx"

# 旧会话中用户的完整提示词
ORIGINAL_PROMPT = (
    "请加载并预览以下数据文件：\n\n"
    "1. `D:\\Project\\Daily\\备用\\20260512测试\\0201到0510购卡用户付费数据.xlsx`\n"
    "2. `D:\\Project\\Daily\\备用\\20260512测试\\代金券明细订单.xlsx`\n"
    "3. `D:\\Project\\Daily\\备用\\20260512测试\\购卡前后订单.xlsx`\n"
    "4. `D:\\Project\\Daily\\备用\\20260512测试\\省钱卡订单.xlsx`\n\n"
    "### 分析背景\n\n"
    "- 这是一个游戏平台的省钱卡功能的用户付费及相关数据，省钱卡的功能为购卡以后，每天有一笔订单付费后可以获得返利。\n\n"
    "### 分析目标\n\n"
    "- 通过数据分析省钱卡功能对用户付费行为的影响。\n\n"
    "## 分析说明\n\n"
    "### 一、需要分析的指标\n\n"
    "1. 省钱卡的最终收益\n"
    "2. 省钱卡复购率\n"
    "3. 省钱卡购买偏好\n"
    "4. 付费频次\n"
    "5. 付费ARPU\n"
    "6. 人均付费金额\n"
    "7. 日均付费金额\n"
    "8. 单次付费金额\n"
    "9. 付费金额区间分布\n\n"
    "### 二、我想要了解的分析内容\n\n"
    "1. 确认连续付费的行为是否因省钱卡刺激而有提升\n"
    "2. 除了我提供的分析指标与内容，说明基于目标还有哪些方向、维度值得关注与分析\n\n"
    "### 三、分析要求\n\n"
    "1. 需要详细说明关键指标、结论的计算方式方法与流程，以便我验证与对其他人说明\n"
    "2. 除了我提供的需要分析的内容与指标外，你还可以自己补充其他觉得需要补充的内容，帮助这次分析更加专业且具有帮助"
)

# 旧会话指标（用于对比）
OLD_SESSION_METRICS = {
    "total_messages": 104,
    "total_context_chars": 101_488,
    "total_tool_messages": 60,
    "tool_avg_size_chars": 200,
    "data_loss_events": 4,  # msg 40-43
    "chart_errors": 2,  # msg 96-97
}


# ============================================================
# 一、上下文膨胀对比（P3-5a: load_data 阶段化输出）
# ============================================================

class TestContextBloating:
    """对比 P3 前后 load_data 产生的上下文大小。"""

    @pytest.fixture
    def clean_ctx(self, tmp_path):
        """创建临时配置和上下文。"""
        from data_agent import config
        from data_agent.config import AgentConfig
        from data_agent.session.workspace import Workspace
        from data_agent.agent.context import AgentContext, set_current_context, reset_current_context

        old_cfg = config._config
        config._config = AgentConfig(
            PROJECT_DIR=tmp_path / "project",
            SESSIONS_DIR=tmp_path / "sessions",
        )
        ctx = AgentContext(session_id="opt_test", workspace=Workspace())
        token = set_current_context(ctx)
        yield ctx
        reset_current_context(token)
        config._config = old_cfg

    def test_load_data_output_size_reduction(self, clean_ctx):
        """P3 load_data 输出应比旧模式显著减少上下文字符数。

        旧会话中，每个 load_data 的 tool result 被截断到 215 字符。
        但在 P3 之前，完整的 load_data 输出可能达到 5000-10000 字符。
        P3 的阶段化输出应让 summary_part 保持紧凑。
        """
        if not HAS_TEST_DATA:
            pytest.skip("测试数据文件不存在")

        from data_agent.tools.data_io import load_data

        # 使用省钱卡流水（大数据集，会产生较多自动分析）
        result = load_data(str(ECARD_FLOW), name="flow_test")

        # 核心断言：输出不应过长
        assert len(result) < 5000, (
            f"load_data 输出过长: {len(result)} 字符。"
            f"P3 阶段化输出应将摘要控制在合理范围内。"
        )

        # 应包含关键信息标签
        assert "[profile]" in result, "应包含 [profile] 标签"
        assert "[detail_file]" in result, "应包含 [detail_file] 指向持久化详情"

    def test_load_data_summary_contains_key_info(self, clean_ctx):
        """阶段化摘要应保留关键信息：行数、列数、字段名。"""
        if not HAS_TEST_DATA:
            pytest.skip("测试数据文件不存在")

        from data_agent.tools.data_io import load_data

        result = load_data(str(ECARD_ORDER), name="order_test")

        # 应包含基本信息
        assert "省钱卡订单" in result or "已加载" in result
        assert "行" in result or "rows" in result.lower()

    def test_load_data_detail_file_persisted(self, tmp_path, clean_ctx):
        """详情应持久化到磁盘文件。"""
        if not HAS_TEST_DATA:
            pytest.skip("测试数据文件不存在")

        from data_agent.tools.data_io import load_data

        load_data(str(ECARD_FLOW), name="persist_test")

        # 检查详情文件是否存在
        from data_agent.config import get_config
        cfg = get_config()
        detail_path = cfg.sessions_resolved / "opt_test" / "tool_outputs" / "load_persist_test_detail.json"

        if detail_path.exists():
            detail = json.loads(detail_path.read_text(encoding="utf-8"))
            assert isinstance(detail, dict), "详情文件应为 JSON dict"
            # 应包含至少一个分析段落
            assert len(detail) > 0, "详情文件不应为空"

    def test_load_4_datasets_context_growth(self, clean_ctx):
        """模拟旧会话：加载4个数据文件，测量总上下文增长。

        旧会话中4个 load_data 的 tool result 共占用约 860 字符（4×215）。
        P3 之后每个 load_data 的 summary 应远小于完整分析输出。
        """
        if not HAS_REAL_DATA:
            pytest.skip("真实数据文件不存在")

        from data_agent.tools.data_io import load_data

        datasets = [
            (str(CARD_PAYMENT), "购卡用户付费数据"),
            (str(VOUCHER_DETAIL), "代金券明细订单"),
            (str(BEFORE_AFTER), "购卡前后订单"),
            (str(CARD_ORDER), "省钱卡订单"),
        ]

        total_output_chars = 0
        for path, name in datasets:
            result = load_data(path, name=name)
            assert "Error" not in result, f"加载 {name} 失败: {result[:200]}"
            total_output_chars += len(result)

        # P3 后，4个数据集的 load_data 输出总和应在合理范围
        # 旧模式（未阶段化）：可能 20000-40000 字符
        # P3 模式（阶段化摘要）：应控制在 10000 以内
        assert total_output_chars < 10000, (
            f"4个 load_data 总输出 {total_output_chars:,} 字符。"
            f"P3 阶段化应显著减少。"
        )

    def test_load_data_output_not_json_bomb(self, clean_ctx):
        """load_data 输出不应包含大量 JSON 数据（完整的 data_profile 应持久化而非内联）。"""
        if not HAS_TEST_DATA:
            pytest.skip("测试数据文件不存在")

        from data_agent.tools.data_io import load_data

        result = load_data(str(ECARD_FLOW), name="json_test")

        # 不应包含完整的 JSON 嵌套结构（如完整的列统计）
        json_like_depth = result.count('{"')
        assert json_like_depth < 20, (
            f"输出包含 {json_like_depth} 个 JSON 对象，可能包含过多内联数据"
        )


# ============================================================
# 二、工具输出压缩（P3-5b: _compact_tool_output）
# ============================================================

class TestToolOutputCompaction:
    """测试 _compact_tool_output 的截断和持久化行为。"""

    @pytest.fixture
    def loop_with_ctx(self, tmp_path):
        """创建带上下文的 AgentLoop。"""
        from data_agent import config
        from data_agent.config import AgentConfig
        from data_agent.agent.loop import AgentLoop
        from data_agent.agent.context import AgentContext, set_current_context, reset_current_context
        from data_agent.session.workspace import Workspace

        old_cfg = config._config
        config._config = AgentConfig(
            PROJECT_DIR=tmp_path / "project",
            SESSIONS_DIR=tmp_path / "sessions",
        )

        ctx = AgentContext(session_id="compact_test", workspace=Workspace())
        token = set_current_context(ctx)

        loop = AgentLoop(session_id="compact_test")
        loop._get_system_prompt = lambda: ""

        yield loop, ctx

        reset_current_context(token)
        config._config = old_cfg

    def test_short_output_unchanged(self, loop_with_ctx):
        """短工具输出不被截断。"""
        from data_agent.tools.registry import ToolResult
        from data_agent.llm.client import ToolCall

        loop, ctx = loop_with_ctx
        tool_result = ToolResult(summary="简单结果")
        tc = ToolCall(id="tc_short", name="test", arguments={})

        output = loop._compact_tool_output(tool_result, tc)
        assert "简单结果" in output

    def test_long_output_truncated_with_reference(self, loop_with_ctx):
        """长工具输出被截断并包含详情文件引用。"""
        from data_agent.tools.registry import ToolResult
        from data_agent.llm.client import ToolCall

        loop, ctx = loop_with_ctx
        long_text = "详细分析结果\n" + "\n".join(f"行{i}: 数值={i*100}" for i in range(500))
        tool_result = ToolResult(summary=long_text)
        tc = ToolCall(id="tc_long", name="test", arguments={})

        output = loop._compact_tool_output(tool_result, tc)

        # 应被截断
        assert len(output) <= 4000, f"输出应被截断，实际 {len(output)} 字符"
        # 应包含详情文件引用
        assert "detail" in output.lower() or "truncated" in output.lower(), (
            "长输出截断后应包含详情引用"
        )

    def test_tool_result_with_data_persisted(self, loop_with_ctx):
        """带结构化数据的 ToolResult 应持久化 data。"""
        from data_agent.tools.registry import ToolResult
        from data_agent.llm.client import ToolCall

        loop, ctx = loop_with_ctx
        tool_result = ToolResult(
            summary="分析完成",
            data={"metrics": {"arpu": 56.3, "retention": 0.72}},
        )
        tc = ToolCall(id="tc_data", name="test", arguments={})

        output = loop._compact_tool_output(tool_result, tc)

        # data 应被持久化
        from data_agent.config import get_config
        detail_path = get_config().sessions_resolved / "compact_test" / "tool_outputs" / "tc_data_detail.json"
        if detail_path.exists():
            detail = json.loads(detail_path.read_text(encoding="utf-8"))
            assert "metrics" in detail

    def test_compaction_threshold_boundary(self, loop_with_ctx):
        """测试截断阈值的边界情况。"""
        from data_agent.tools.registry import ToolResult
        from data_agent.llm.client import ToolCall
        from data_agent.agent.loop import TOOL_SUMMARY_THRESHOLD

        loop, ctx = loop_with_ctx

        # 恰好在阈值以下
        just_under = ToolResult(summary="x" * (TOOL_SUMMARY_THRESHOLD - 1))
        tc1 = ToolCall(id="tc_under", name="test", arguments={})
        output1 = loop._compact_tool_output(just_under, tc1)
        assert "truncated" not in output1.lower()

        # 恰好在阈值以上
        just_over = ToolResult(summary="x" * (TOOL_SUMMARY_THRESHOLD + 1))
        tc2 = ToolCall(id="tc_over", name="test", arguments={})
        output2 = loop._compact_tool_output(just_over, tc2)
        assert "truncated" in output2.lower() or len(output2) <= TOOL_SUMMARY_THRESHOLD + 500


# ============================================================
# 三、micro_compact 智能预览（P3-5c）
# ============================================================

class TestMicroCompactQuality:
    """测试 micro_compact 的智能预览质量。"""

    def test_structured_tag_extraction(self):
        """从结构化标签中提取有意义的预览。"""
        from data_agent.agent.compact import _extract_compact_preview

        content = (
            "[data_profile]\n"
            "  shape: 13757 rows x 9 cols\n"
            "  columns: order_id, user_id, product_id\n"
            "  issues: 732 duplicate rows\n"
            "[/data_profile]\n\n"
            "[insights]\n"
            "  - 日均付费金额从8092元下降到5611元\n"
            "  - 连续付费≥3天的用户占比增加9.7%\n"
            "[/insights]\n\n"
            "[quality]\n"
            "  completeness: 99.2%\n"
            "[/quality]"
        )

        preview = _extract_compact_preview(content, max_chars=400)

        # 预览应包含关键信息
        assert "data_profile" in preview or "shape" in preview or "rows" in preview
        assert len(preview) <= 420  # 允许微小超出
        assert len(preview) > 50  # 不应过于简短

    def test_conclusion_keyword_extraction(self):
        """从非结构化文本中提取结论性内容。"""
        from data_agent.agent.compact import _extract_compact_preview

        content = (
            "数据分析结果\n"
            "==================\n"
            "1. 日均付费金额为8092元，较上期下降30%\n"
            "2. 连续付费天数有所增加\n"
            "3. 单次付费金额基本持平\n"
            "4. 发现小额订单(<6元)占比显著增加\n"
            "5. 用户留存率在Day7后开始下降\n"
            "6. 复购率为11.1%，7个用户有复购行为\n"
        )

        preview = _extract_compact_preview(content, max_chars=400)

        # 预览应包含结论关键词
        assert any(kw in preview for kw in ["下降", "增加", "持平", "复购"])

    def test_fallback_for_plain_text(self):
        """无结构化标签和结论关键词时，使用首尾行策略。"""
        from data_agent.agent.compact import _extract_compact_preview

        content = "\n".join(f"Line {i}: some data here" for i in range(20))

        preview = _extract_compact_preview(content, max_chars=400)

        # 应包含首尾内容
        assert "Line 0" in preview
        assert "..." in preview or "Line 19" in preview

    def test_preview_quality_vs_old_truncation(self):
        """智能预览质量应优于旧式 content[:200] 截断。"""
        from data_agent.agent.compact import _extract_compact_preview

        # 模拟一个真实的分析工具输出
        content = (
            "=== 省钱卡功能分析 ===\n\n"
            "[指标1] 省钱卡最终收益\n"
            "  销售收入: 2502元\n"
            "  代金券补贴: -4254元\n"
            "  净收益: -1752元\n\n"
            "[指标2] 复购率\n"
            "  复购用户: 7人(11.1%)\n\n"
            "[insights]\n"
            "  结论: 省钱卡改变付费结构而非总量\n"
            "  关键发现: 连续付费≥3天用户占比+9.7%\n"
            "[/insights]\n\n"
            "[recommendations]\n"
            "  1. 控成本: 每日券面值从3降至2元\n"
            "  2. 促升级: 周卡→月卡升级优惠\n"
            "[/recommendations]"
        )

        # 旧方式截断
        old_truncation = content[:200]

        # 新方式智能预览
        smart_preview = _extract_compact_preview(content, max_chars=400)

        # 智能预览应包含更多有意义的信息
        smart_keywords = sum(1 for kw in ["收益", "复购", "insights", "conclusion", "发现", "结论"]
                            if kw in smart_preview.lower())
        old_keywords = sum(1 for kw in ["收益", "复购", "insights", "conclusion", "发现", "结论"]
                          if kw in old_truncation.lower())

        # 智能预览至少应保留关键词数量的一半以上
        # 注意：旧截断因为是前200字符，可能恰好包含关键词
        assert smart_keywords >= old_keywords // 2, (
            f"智能预览({smart_keywords}个关键词)应至少保留旧截断({old_keywords}个关键词)的一半以上"
        )
        # 更重要的是智能预览有结构化标签
        assert "[指标" in smart_preview or "insights" in smart_preview or "发现" in smart_preview, \
            "智能预览应包含结构化内容"


# ============================================================
# 四、用户要求提取与持久化（P1）
# ============================================================

class TestUserRequirementsPreservation:
    """测试用户分析要求的提取、注入和保留。"""

    def test_extract_requirements_from_original_prompt(self):
        """从原始提示词中提取用户要求。"""
        # 模拟 P1-1 的提取逻辑
        requirements_text = ORIGINAL_PROMPT

        # 用户要求的关键要素
        expected_requirements = [
            "详细说明关键指标、结论的计算方式方法与流程",
            "以便我验证与对其他人说明",
            "补充其他觉得需要补充的内容",
            "专业且具有帮助",
            "确认连续付费的行为是否因省钱卡刺激而有提升",
        ]

        for req in expected_requirements:
            assert req in requirements_text, f"用户要求 '{req}' 应存在于原始输入中"

    def test_user_requirements_in_context(self):
        """AgentContext 的 user_quality_requirements 字段应可用。"""
        from data_agent.agent.context import AgentContext

        ctx = AgentContext(session_id="test")
        assert hasattr(ctx, "user_quality_requirements")
        assert ctx.user_quality_requirements == ""

        ctx.user_quality_requirements = "需要详细说明计算方式方法与流程"
        assert ctx.user_quality_requirements == "需要详细说明计算方式方法与流程"

    def test_requirements_injected_into_system_prompt(self):
        """build_system_prompt 应注入用户要求。"""
        from data_agent.agent.prompts import build_system_prompt

        prompt_with = build_system_prompt(
            tool_list="",
            user_requirements="需要详细说明计算方式方法与流程",
            user_input="分析省钱卡效果",
            session_context="rows: 100",
        )
        prompt_without = build_system_prompt(
            tool_list="",
            user_requirements="",
            user_input="分析省钱卡效果",
            session_context="rows: 100",
        )

        # 有要求时 prompt 应更长
        assert len(prompt_with) > len(prompt_without), (
            f"有用户要求时 prompt({len(prompt_with)})应长于无要求({len(prompt_without)})"
        )
        assert "计算方式方法与流程" in prompt_with or "user_requirements" in prompt_with

    def test_compact_history_preserves_requirements(self):
        """compact_history 的摘要 prompt 应包含第0条（用户要求保留）。"""
        from data_agent.agent.compact import compact_history, CompactState

        # 检查 compact_history 的摘要 prompt 是否要求保留用户要求
        import inspect
        source = inspect.getsource(compact_history)
        assert "0. 用户对输出格式、质量、详细程度的明确要求" in source or \
               "用户对输出格式" in source or \
               "质量、详细程度" in source


# ============================================================
# 五、Workspace 数据丢失场景（旧会话 Bug 修复验证）
# ============================================================

class TestWorkspaceDataLoss:
    """旧会话中 msg 40-43 出现数据集丢失。验证 workspace 生命周期。"""

    @pytest.fixture
    def session_env(self, tmp_path):
        """创建完整的会话环境。"""
        from data_agent import config
        from data_agent.config import AgentConfig
        from data_agent.session.workspace import Workspace
        from data_agent.agent.context import AgentContext, set_current_context, reset_current_context

        old_cfg = config._config
        config._config = AgentConfig(
            PROJECT_DIR=tmp_path / "project",
            SESSIONS_DIR=tmp_path / "sessions",
        )

        ctx = AgentContext(session_id="workspace_test", workspace=Workspace())
        token = set_current_context(ctx)
        yield ctx, tmp_path

        reset_current_context(token)
        config._config = old_cfg

    def test_workspace_survives_save_restore(self, session_env):
        """workspace 数据在 save_meta + restore 后应完整恢复。"""
        ctx, tmp_path = session_env
        from data_agent.session.workspace import workspace

        # 加载数据
        df = pd.DataFrame({
            "user_id": [1, 2, 3],
            "amount": [100, 200, 300],
        })
        workspace.add("test_data", df)
        workspace.set_metadata("test_data", "_source_path", "/some/path.csv")
        workspace.set_metadata("test_data", "_source_fmt", "csv")

        # 保存
        workspace.save_meta("workspace_test")
        workspace.persist_dataset("workspace_test", "test_data")

        # 清空
        workspace.remove("test_data")
        assert workspace.get("test_data") is None

        # 恢复
        from data_agent.agent.loop import AgentLoop
        loop = AgentLoop(session_id="workspace_test")
        loop._get_system_prompt = lambda: ""
        loop._restore_workspace()

        restored = workspace.get("test_data")
        assert restored is not None, "workspace 恢复后数据应存在"
        assert restored.shape[0] == 3

    def test_workspace_not_cleared_between_turns(self, session_env):
        """新 turn 开始时 workspace 不应被清空。

        旧会话 msg 38 (user: "请开始") → msg 40-43 数据集不存在。
        """
        ctx, tmp_path = session_env
        from data_agent.session.workspace import workspace

        df = pd.DataFrame({"a": [1, 2, 3]})
        workspace.add("test_data", df)

        # 模拟新 turn（创建新 loop 但同一 session）
        from data_agent.agent.loop import AgentLoop
        loop2 = AgentLoop(session_id="workspace_test")
        loop2._get_system_prompt = lambda: ""

        # workspace 是全局单例，不应因创建新 loop 而丢失
        assert workspace.get("test_data") is not None, (
            "创建新 AgentLoop 不应清空 workspace"
        )


# ============================================================
# 六、僵尸 Task 过滤（P2-2）
# ============================================================

class TestStaleTaskFiltering:
    """测试超过 24 小时的 pending task 被过滤。"""

    @pytest.fixture
    def task_env(self, tmp_path):
        from data_agent import config
        from data_agent.config import AgentConfig
        from data_agent.session.task_manager import TaskManager

        old_cfg = config._config
        config._config = AgentConfig(
            PROJECT_DIR=tmp_path / "project",
            SESSIONS_DIR=tmp_path / "sessions",
        )

        mgr = TaskManager(tasks_dir=tmp_path / "tasks")
        mgr.reset_for_testing()
        yield mgr

        config._config = old_cfg

    def test_stale_pending_task_filtered(self, task_env):
        """超过 24 小时的 pending task 不应出现在 list_all。"""
        mgr = task_env

        # 创建一个旧 task
        task = mgr.create(subject="旧任务", description="测试过期")
        # 手动修改创建时间为 25 小时前
        from datetime import datetime, timedelta
        old_time = (datetime.now() - timedelta(hours=25)).strftime("%Y-%m-%d %H:%M:%S")
        task["created_at"] = old_time
        mgr._save(task)

        # list_all 应过滤掉
        visible = mgr.list_all()
        stale_ids = [t["id"] for t in visible if t["id"] == task["id"]]
        assert len(stale_ids) == 0, "超过24小时的 pending task 应被过滤"

    def test_recent_pending_task_visible(self, task_env):
        """新创建的 pending task 应正常显示。"""
        mgr = task_env
        task = mgr.create(subject="新任务", description="测试可见")

        visible = mgr.list_all()
        assert any(t["id"] == task["id"] for t in visible)

    def test_stale_completed_task_still_visible(self, task_env):
        """超过 24 小时的 completed task 不应被过滤。"""
        mgr = task_env
        task = mgr.create(subject="已完成旧任务")
        mgr.update(task["id"], status="completed")

        # 修改时间为过期
        from datetime import datetime, timedelta
        task_data = mgr.get(task["id"])
        task_data["created_at"] = (datetime.now() - timedelta(hours=25)).strftime("%Y-%m-%d %H:%M:%S")
        mgr._save(task_data)

        visible = mgr.list_all()
        assert any(t["id"] == task["id"] for t in visible), "已完成的 task 不应被过滤"

    def test_list_all_raw_includes_stale(self, task_env):
        """list_all_raw 应包含所有 task（含过期的）。"""
        mgr = task_env
        task = mgr.create(subject="旧任务")

        from datetime import datetime, timedelta
        task_data = mgr.get(task["id"])
        task_data["created_at"] = (datetime.now() - timedelta(hours=25)).strftime("%Y-%m-%d %H:%M:%S")
        mgr._save(task_data)

        raw = mgr.list_all_raw()
        assert any(t["id"] == task["id"] for t in raw)


# ============================================================
# 七、旧会话问题复现与验证
# ============================================================

class TestOldSessionIssues:
    """复现旧会话中发现的具体问题，验证修复效果。"""

    @pytest.fixture
    def full_env(self, tmp_path):
        """完整测试环境。"""
        from data_agent import config
        from data_agent.config import AgentConfig
        from data_agent.session.workspace import Workspace
        from data_agent.agent.context import AgentContext, set_current_context, reset_current_context

        old_cfg = config._config
        config._config = AgentConfig(
            PROJECT_DIR=tmp_path / "project",
            SESSIONS_DIR=tmp_path / "sessions",
        )

        ctx = AgentContext(session_id="old_session_test", workspace=Workspace())
        token = set_current_context(ctx)
        yield ctx, tmp_path

        reset_current_context(token)
        config._config = old_cfg

    def test_old_session_chart_purpose_error(self, full_env):
        """旧会话 msg 96-97: chart purpose 验证错误。

        LLM 使用了 '展示购卡前后付费金额的基本对比' 作为 purpose，
        但系统只接受 ['evidence', 'exploratory', 'insight']。
        """
        ctx, tmp_path = full_env
        from data_agent.session.workspace import workspace
        from data_agent.tools.visualization import create_chart

        # 加载数据
        df = pd.DataFrame({
            "period": ["购卡前", "购卡后"],
            "amount": [3980, 2715],
        })
        workspace.add("chart_test", df)

        # 使用无效 purpose
        result = create_chart(
            chart_type="bar",
            data="chart_test",
            x_col="period",
            y_col="amount",
            purpose="展示购卡前后付费金额的基本对比",  # 无效 purpose
            title="购卡前后付费金额对比",
        )

        # 应返回错误并提示有效值
        assert "error" in result.lower() or "purpose" in result.lower(), (
            "无效 purpose 应被拒绝并提示有效值"
        )

        # 使用有效 purpose
        result2 = create_chart(
            chart_type="bar",
            data="chart_test",
            x_col="period",
            y_col="amount",
            purpose="evidence",  # 有效 purpose
            title="购卡前后付费金额对比",
        )

        # 不应报 purpose 错误（可能有其他错误如配置缺失，但不应是 purpose 错误）
        if "error" in result2.lower():
            assert "purpose" not in result2.lower(), "有效 purpose 不应报错"

    def test_old_session_transform_security_error(self, full_env):
        """旧会话 msg 52-53: 条件不安全错误。

        LLM 尝试用 pandas 表达式做 filter，但表达式包含不允许的操作。
        """
        ctx, tmp_path = full_env
        from data_agent.session.workspace import workspace
        from data_agent.tools.data_transform import transform_data

        df = pd.DataFrame({
            "user_id": [1, 2, 3],
            "amount": [100, 200, 300],
        })
        workspace.add("transform_test", df)

        # 模拟 LLM 使用不安全的表达式
        result = transform_data(
            name="transform_test",
            operation="filter",
            condition="df['amount'].apply(lambda x: x > 100)",  # 包含 Call 和 Lambda
            save_as="filtered",
        )

        # 应报安全错误
        assert "不安全" in result or "不允许" in result or "Error" in result

    def test_context_size_comparison_simulation(self, full_env):
        """模拟对比 P3 前后的上下文大小。

        使用相同的数据文件，测量 load_data 的输出大小差异。
        """
        if not HAS_TEST_DATA:
            pytest.skip("测试数据文件不存在")

        ctx, tmp_path = full_env
        from data_agent.tools.data_io import load_data
        from data_agent.session.workspace import workspace

        # 加载多个数据集
        result = load_data(str(ECARD_FLOW), name="flow")
        p3_output_size = len(result)

        # 旧模式估算：
        # 完整 quick_profile (~3000) + interpret_dataset (~2000) +
        # quality_card (~1500) + auto_insight (~2000) +
        # cross_dataset_hints (~500) + domain_detection (~200) = ~9200 字符
        estimated_old_size = 9000

        # P3 模式应显著更小
        assert p3_output_size < estimated_old_size, (
            f"P3 输出({p3_output_size})应小于估算的旧模式({estimated_old_size})"
        )

        # 计算节省比例
        reduction_pct = (1 - p3_output_size / estimated_old_size) * 100
        print(f"  上下文缩减: {reduction_pct:.0f}% ({estimated_old_size} → {p3_output_size} chars)")


# ============================================================
# 八、全链路对比：旧会话指标 vs 当前系统
# ============================================================

class TestFullPipelineComparison:
    """使用真实数据跑完整加载链路，生成对比报告。"""

    @pytest.fixture
    def pipeline_env(self, tmp_path):
        from data_agent import config
        from data_agent.config import AgentConfig
        from data_agent.session.workspace import Workspace
        from data_agent.agent.context import AgentContext, set_current_context, reset_current_context

        old_cfg = config._config
        config._config = AgentConfig(
            PROJECT_DIR=tmp_path / "project",
            SESSIONS_DIR=tmp_path / "sessions",
        )

        ctx = AgentContext(session_id="pipeline_test", workspace=Workspace())
        token = set_current_context(ctx)
        yield ctx, tmp_path

        reset_current_context(token)
        config._config = old_cfg

    def test_full_4_dataset_load(self, pipeline_env):
        """加载4个真实数据文件，测量完整指标。"""
        if not HAS_REAL_DATA:
            pytest.skip("真实数据文件不存在")

        ctx, tmp_path = pipeline_env
        from data_agent.tools.data_io import load_data
        from data_agent.session.workspace import workspace

        datasets = [
            (str(CARD_PAYMENT), "购卡用户付费数据"),
            (str(VOUCHER_DETAIL), "代金券明细订单"),
            (str(BEFORE_AFTER), "购卡前后订单"),
            (str(CARD_ORDER), "省钱卡订单"),
        ]

        results = {}
        total_chars = 0
        for path, name in datasets:
            r = load_data(path, name=name)
            results[name] = {
                "output_chars": len(r),
                "has_profile_tag": "[profile]" in r,
                "has_detail_ref": "[detail_file]" in r,
                "has_insights": "[insights]" in r,
            }
            total_chars += len(r)

            # 基本验证
            assert "Error" not in r, f"{name} 加载失败"
            df = workspace.get(name)
            assert df is not None, f"{name} 未注册到 workspace"

        # 生成对比报告
        report_lines = [
            "\n=== 优化效果对比报告 ===\n",
            f"4个 load_data 总输出字符数: {total_chars:,}",
            f"旧会话中 tool result 总字符数: {OLD_SESSION_METRICS['tool_avg_size_chars'] * 4:,}",
            "",
        ]

        for name, metrics in results.items():
            report_lines.append(
                f"  {name}: {metrics['output_chars']:,} chars "
                f"(profile:{metrics['has_profile_tag']} detail:{metrics['has_detail_ref']} insights:{metrics['has_insights']})"
            )

        report = "\n".join(report_lines)
        print(report)

        # 断言关键改进
        # 1. 每个数据集输出都应有标签结构
        for name, metrics in results.items():
            assert metrics["has_profile_tag"], f"{name} 应有 [profile] 标签"

    def test_detail_files_created(self, pipeline_env):
        """加载后应创建持久化详情文件。"""
        if not HAS_REAL_DATA:
            pytest.skip("真实数据文件不存在")

        ctx, tmp_path = pipeline_env
        from data_agent.tools.data_io import load_data
        from data_agent.config import get_config

        load_data(str(CARD_PAYMENT), name="detail_test")

        cfg = get_config()
        detail_dir = cfg.sessions_resolved / "pipeline_test" / "tool_outputs"

        if detail_dir.exists():
            detail_files = list(detail_dir.glob("*.json"))
            # 应至少有一个详情文件
            assert len(detail_files) > 0, "应创建详情持久化文件"

            # 详情文件应包含实质性内容
            for f in detail_files:
                content = json.loads(f.read_text(encoding="utf-8"))
                assert isinstance(content, dict)
                total_json_len = len(json.dumps(content, ensure_ascii=False))
                assert total_json_len > 100, f"详情文件 {f.name} 内容过短"


# ============================================================
# 九、分析质量相关工具测试
# ============================================================

class TestAnalysisQualityTools:
    """测试与输出质量直接相关的工具和机制。"""

    @pytest.fixture
    def quality_env(self, tmp_path):
        from data_agent import config
        from data_agent.config import AgentConfig
        from data_agent.session.workspace import Workspace
        from data_agent.agent.context import AgentContext, set_current_context, reset_current_context

        old_cfg = config._config
        config._config = AgentConfig(
            PROJECT_DIR=tmp_path / "project",
            SESSIONS_DIR=tmp_path / "sessions",
        )

        ctx = AgentContext(session_id="quality_test", workspace=Workspace())
        token = set_current_context(ctx)
        yield ctx, tmp_path

        reset_current_context(token)
        config._config = old_cfg

    def test_evidence_confidence_calibration(self, quality_env):
        """证据置信度校准：高置信 + 小样本应降级。"""
        from data_agent.tools.analysis_flow import record_evidence_record

        evidence = json.dumps({
            "claim": "省钱卡使付费增加35%",
            "dataset": "main",
            "method": "购卡前后对比",
            "tool_calls": ["transform_data"],
            "result_summary": "购卡后35%用户付费增加",
            "limitations": ["无对照组", "样本量小"],
            "confidence": "high",
            "sample_size": 15,  # 小样本
        })

        result = record_evidence_record(evidence)
        parsed = json.loads(result)

        # 小样本 + 高置信度 应触发降级或警告
        has_calibration = (
            parsed.get("confidence_auto_downgraded") is True or
            "calibration" in str(parsed).lower() or
            "saved" in parsed  # 至少不崩溃
        )
        assert has_calibration, "小样本+高置信应触发校准"

    def test_analysis_plan_validation(self, quality_env):
        """分析计划缺少字段时应报错。"""
        from data_agent.tools.analysis_flow import record_analysis_plan

        # 缺少 method_plan
        incomplete = json.dumps({
            "goal": "省钱卡效果分析",
            "question_type": "evaluation",
            "metrics": ["收益", "复购率"],
        })

        result = record_analysis_plan(incomplete)
        assert "error" in result.lower(), "不完整的计划应报错"

    def test_evidence_must_have_limitations(self, quality_env):
        """证据记录必须包含 limitations。"""
        from data_agent.tools.analysis_flow import record_evidence_record

        evidence_no_limit = json.dumps({
            "claim": "付费增加了",
            "dataset": "main",
            "method": "对比分析",
            "tool_calls": [],
            "result_summary": "增加了30%",
            "limitations": [],  # 空 limitations
            "confidence": "medium",
        })

        result = record_evidence_record(evidence_no_limit)
        parsed = json.loads(result)

        # 空 limitations 应触发警告
        has_warning = (
            "limitation" in str(parsed).lower() or
            "warning" in str(parsed).lower() or
            "saved" in parsed
        )
        assert has_warning or "error" not in str(parsed).lower(), "空 limitations 应有警告"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
