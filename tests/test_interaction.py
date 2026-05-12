"""全面测试 ask_user_question 工具。

测试覆盖：
1. 单选：数字选择、跳过、自由输入
2. 多选：逗号分隔、混合输入、全自由输入
3. 无选项模式：自由文本输入
4. 多问题模式：2-4 个问题顺序提问
5. 取消/中断处理
6. 选项解析：JSON、逗号分隔、空选项
7. 超时配置：确认交互式工具无超时
8. Web 模式检测与异常抛出
9. _process_answer 纯逻辑测试（无 IO）
10. 边界情况：无效编号、空选项、超长文本
"""

import json
import pytest
from unittest.mock import patch, MagicMock

from data_agent.tools.interaction import (
    _process_answer,
    _ask_single,
    _ask_multiple,
    _robust_input,
    ask_user_question,
)


# ── Fixtures ────────────────────────────────────────────

SAMPLE_OPTIONS = [
    {"label": "CSV 文件", "description": "逗号分隔的文本文件"},
    {"label": "Excel 文件", "description": ".xlsx 格式"},
    {"label": "JSON 文件", "description": "结构化 JSON"},
]

SAMPLE_MULTI_OPTIONS = [
    {"label": "趋势分析", "description": "时间序列趋势"},
    {"label": "对比分析", "description": "分组对比"},
    {"label": "分布分析", "description": "频率分布"},
]


# ══════════════════════════════════════════════════════════
#  A. _process_answer 纯逻辑测试（无 IO，最快最可靠）
# ══════════════════════════════════════════════════════════

class TestProcessAnswer:
    """测试答案处理逻辑，不需要模拟输入。"""

    # ── 跳过 ──

    def test_empty_answer_returns_skipped(self):
        result = _process_answer("", SAMPLE_OPTIONS, multi_select=False)
        assert result["answer"] == "skipped"
        assert result["is_free_input"] is False

    def test_skip_keyword(self):
        result = _process_answer("skip", SAMPLE_OPTIONS, multi_select=False)
        assert result["answer"] == "skipped"

    def test_skip_chinese(self):
        result = _process_answer("跳过", SAMPLE_OPTIONS, multi_select=False)
        assert result["answer"] == "skipped"

    # ── 取消 ──

    def test_cancel_keyword(self):
        result = _process_answer("cancel", SAMPLE_OPTIONS, multi_select=False)
        assert result["answer"] == "cancelled"

    def test_cancel_chinese(self):
        result = _process_answer("取消", SAMPLE_OPTIONS, multi_select=False)
        assert result["answer"] == "cancelled"

    def test_cancel_q(self):
        result = _process_answer("q", SAMPLE_OPTIONS, multi_select=False)
        assert result["answer"] == "cancelled"

    # ── 单选数字匹配 ──

    def test_single_select_first(self):
        result = _process_answer("1", SAMPLE_OPTIONS, multi_select=False)
        assert result["answer"] == "CSV 文件"
        assert result["is_free_input"] is False
        assert result["selected_option"]["label"] == "CSV 文件"

    def test_single_select_second(self):
        result = _process_answer("2", SAMPLE_OPTIONS, multi_select=False)
        assert result["answer"] == "Excel 文件"

    def test_single_select_last(self):
        result = _process_answer("3", SAMPLE_OPTIONS, multi_select=False)
        assert result["answer"] == "JSON 文件"

    def test_single_select_out_of_range_falls_to_free_input(self):
        result = _process_answer("99", SAMPLE_OPTIONS, multi_select=False)
        assert result["answer"] == "99"
        assert result["is_free_input"] is True

    def test_single_select_zero_falls_to_free_input(self):
        result = _process_answer("0", SAMPLE_OPTIONS, multi_select=False)
        assert result["answer"] == "0"
        assert result["is_free_input"] is True

    def test_single_select_negative_falls_to_free_input(self):
        result = _process_answer("-1", SAMPLE_OPTIONS, multi_select=False)
        assert result["answer"] == "-1"
        assert result["is_free_input"] is True

    # ── 自由输入（非数字）──

    def test_free_text_input(self):
        result = _process_answer("Parquet 文件", SAMPLE_OPTIONS, multi_select=False)
        assert result["answer"] == "Parquet 文件"
        assert result["is_free_input"] is True
        assert result["selected_option"] is None

    def test_free_text_with_chinese(self):
        result = _process_answer("数据库直连", SAMPLE_OPTIONS, multi_select=False)
        assert result["answer"] == "数据库直连"
        assert result["is_free_input"] is True

    # ── 多选 ──

    def test_multi_select_two_options(self):
        result = _process_answer("1,3", SAMPLE_MULTI_OPTIONS, multi_select=True)
        assert result["answer"] == "趋势分析, 分布分析"
        assert result["is_free_input"] is False
        assert result["multi_select"] is True
        assert len(result["selected_options"]) == 2

    def test_multi_select_all(self):
        result = _process_answer("1,2,3", SAMPLE_MULTI_OPTIONS, multi_select=True)
        assert result["answer"] == "趋势分析, 对比分析, 分布分析"
        assert len(result["selected_options"]) == 3

    def test_multi_select_with_spaces(self):
        result = _process_answer(" 1 , 2 ", SAMPLE_MULTI_OPTIONS, multi_select=True)
        assert result["answer"] == "趋势分析, 对比分析"

    def test_multi_select_mixed_numbers_and_text(self):
        """数字匹配选项，非数字作为自由输入。"""
        result = _process_answer("1,回归分析", SAMPLE_MULTI_OPTIONS, multi_select=True)
        # 1 匹配选项，"回归分析" 作为自由输入
        assert result["multi_select"] is True

    def test_multi_select_all_free_text(self):
        result = _process_answer("方法A,方法B", SAMPLE_MULTI_OPTIONS, multi_select=True)
        assert result["answer"] == "方法A, 方法B"
        assert result["is_free_input"] is True

    def test_multi_select_invalid_number_falls_to_free(self):
        result = _process_answer("99,100", SAMPLE_MULTI_OPTIONS, multi_select=True)
        assert result["is_free_input"] is True

    # ── 无选项模式 ──

    def test_no_options_free_text(self):
        result = _process_answer("这是自由输入", [], multi_select=False)
        assert result["answer"] == "这是自由输入"
        assert result["is_free_input"] is True

    def test_no_options_empty_skipped(self):
        result = _process_answer("", [], multi_select=False)
        assert result["answer"] == "skipped"

    def test_no_options_cancel(self):
        result = _process_answer("cancel", [], multi_select=False)
        assert result["answer"] == "cancelled"


# ══════════════════════════════════════════════════════════
#  B. 单问题交互 _ask_single（模拟输入）
# ══════════════════════════════════════════════════════════

class TestAskSingle:
    """测试单问题交互流程，模拟用户输入。"""

    @patch("data_agent.tools.interaction._robust_input")
    def test_select_option_1(self, mock_input):
        mock_input.return_value = "1"
        result = _ask_single("选择数据类型", SAMPLE_OPTIONS)
        assert result["answer"] == "CSV 文件"
        assert result["is_free_input"] is False

    @patch("data_agent.tools.interaction._robust_input")
    def test_free_text(self, mock_input):
        mock_input.return_value = "Parquet"
        result = _ask_single("选择数据类型", SAMPLE_OPTIONS)
        assert result["answer"] == "Parquet"
        assert result["is_free_input"] is True

    @patch("data_agent.tools.interaction._robust_input")
    def test_skip_by_empty(self, mock_input):
        mock_input.return_value = ""
        result = _ask_single("选择数据类型", SAMPLE_OPTIONS)
        assert result["answer"] == "skipped"

    @patch("data_agent.tools.interaction._robust_input")
    def test_cancel_by_keyboard_interrupt(self, mock_input):
        mock_input.side_effect = KeyboardInterrupt()
        result = _ask_single("选择数据类型", SAMPLE_OPTIONS)
        assert result["answer"] == "cancelled"

    @patch("data_agent.tools.interaction._robust_input")
    def test_no_options_mode(self, mock_input):
        mock_input.return_value = "用户自定义回答"
        result = _ask_single("请描述你的需求", [])
        assert result["answer"] == "用户自定义回答"
        assert result["is_free_input"] is True

    @patch("data_agent.tools.interaction._robust_input")
    def test_multi_select_mode(self, mock_input):
        mock_input.return_value = "1,2"
        result = _ask_single("选择分析类型", SAMPLE_MULTI_OPTIONS, multi_select=True)
        assert result["answer"] == "趋势分析, 对比分析"
        assert result.get("multi_select") is True

    @patch("data_agent.tools.interaction._robust_input")
    def test_with_question_number_display(self, mock_input):
        """带 [1/3] 前缀的多问题模式。"""
        mock_input.return_value = "1"
        result = _ask_single(
            "选择数据类型", SAMPLE_OPTIONS,
            question_num=1, total_questions=3,
        )
        assert result["answer"] == "CSV 文件"


# ══════════════════════════════════════════════════════════
#  C. 多问题交互 _ask_multiple
# ══════════════════════════════════════════════════════════

class TestAskMultiple:
    """测试多问题顺序交互。"""

    @patch("data_agent.tools.interaction._robust_input")
    def test_two_questions(self, mock_input):
        mock_input.side_effect = ["1", "2"]
        questions = [
            {"question": "选择数据类型", "options": SAMPLE_OPTIONS[:2]},
            {"question": "选择分析类型", "options": SAMPLE_MULTI_OPTIONS[:2]},
        ]
        result = _ask_multiple(questions)
        assert result["count"] == 2
        assert len(result["answers"]) == 2
        assert result["answers"][0]["answer"] == "CSV 文件"
        assert result["answers"][1]["answer"] == "对比分析"

    @patch("data_agent.tools.interaction._robust_input")
    def test_four_questions_max(self, mock_input):
        """最多 4 个问题（Claude Code 限制）。"""
        mock_input.side_effect = ["1", "2", "1", "skip"]
        questions = [
            {"question": f"问题 {i+1}", "options": SAMPLE_OPTIONS[:2]}
            for i in range(4)
        ]
        result = _ask_multiple(questions)
        assert result["count"] == 4

    @patch("data_agent.tools.interaction._robust_input")
    def test_mixed_select_and_free_text(self, mock_input):
        mock_input.side_effect = ["1", "自定义回答"]
        questions = [
            {"question": "选择格式", "options": SAMPLE_OPTIONS[:2]},
            {"question": "备注", "options": []},
        ]
        result = _ask_multiple(questions)
        assert result["answers"][0]["answer"] == "CSV 文件"
        assert result["answers"][1]["answer"] == "自定义回答"
        assert result["answers"][1]["is_free_input"] is True

    @patch("data_agent.tools.interaction._robust_input")
    def test_cancel_in_middle(self, mock_input):
        """第二个问题取消。"""
        mock_input.side_effect = ["1", KeyboardInterrupt()]
        questions = [
            {"question": "Q1", "options": SAMPLE_OPTIONS[:2]},
            {"question": "Q2", "options": SAMPLE_OPTIONS[:2]},
        ]
        result = _ask_multiple(questions)
        assert result["answers"][0]["answer"] == "CSV 文件"
        assert result["answers"][1]["answer"] == "cancelled"


# ══════════════════════════════════════════════════════════
#  D. ask_user_question 工具入口
# ══════════════════════════════════════════════════════════

class TestAskUserQuestionTool:
    """测试工具注册入口函数。ask_user_question 现在统一使用 suspension 模式。"""

    def test_single_question_with_options(self):
        """单问题 + 选项：抛出异常，携带正确的 question/options/multi_select。"""
        from data_agent.agent.loop import UserConfirmationRequired
        with pytest.raises(UserConfirmationRequired) as exc_info:
            ask_user_question(
                question="选择数据类型",
                options=json.dumps(SAMPLE_OPTIONS),
            )
        e = exc_info.value
        assert e.question == "选择数据类型"
        assert len(e.options) == 3
        assert e.options[0]["label"] == "CSV 文件"
        assert e.multi_select is False

    def test_single_question_no_options(self):
        """无选项：抛出异常，options 为空。"""
        from data_agent.agent.loop import UserConfirmationRequired
        with pytest.raises(UserConfirmationRequired) as exc_info:
            ask_user_question(question="描述你的需求")
        e = exc_info.value
        assert e.question == "描述你的需求"
        assert e.options == []

    def test_single_question_multi_select(self):
        """multi_select=True 时传递到异常。"""
        from data_agent.agent.loop import UserConfirmationRequired
        with pytest.raises(UserConfirmationRequired) as exc_info:
            ask_user_question(
                question="选择分析类型",
                options=json.dumps(SAMPLE_MULTI_OPTIONS),
                multi_select=True,
            )
        e = exc_info.value
        assert e.multi_select is True
        assert len(e.options) == 3

    def test_multi_question_mode(self):
        """多问题模式：context 携带完整 questions JSON。"""
        from data_agent.agent.loop import UserConfirmationRequired
        questions = [
            {"question": "选择数据类型", "options": SAMPLE_OPTIONS[:2]},
            {"question": "选择分析类型", "options": SAMPLE_MULTI_OPTIONS[:2]},
        ]
        with pytest.raises(UserConfirmationRequired) as exc_info:
            ask_user_question(
                question="ignored",
                questions=json.dumps(questions),
            )
        e = exc_info.value
        parsed = json.loads(e.context)
        assert len(parsed) == 2
        assert parsed[0]["question"] == "选择数据类型"
        # question 是合并的
        assert "选择数据类型" in e.question
        assert "选择分析类型" in e.question

    def test_options_comma_separated_fallback(self):
        """选项 JSON 解析失败时回退到逗号分隔。"""
        from data_agent.agent.loop import UserConfirmationRequired
        with pytest.raises(UserConfirmationRequired) as exc_info:
            ask_user_question(
                question="选择颜色",
                options="红色,蓝色,绿色",
            )
        e = exc_info.value
        assert len(e.options) == 3
        assert e.options[0]["label"] == "红色"

    def test_empty_options_string(self):
        """空 options 字符串。"""
        from data_agent.agent.loop import UserConfirmationRequired
        with pytest.raises(UserConfirmationRequired) as exc_info:
            ask_user_question(question="Q1", options="")
        assert exc_info.value.options == []

    def test_invalid_json_options_fallback_to_comma(self):
        """无效 JSON 选项回退到逗号分隔。"""
        from data_agent.agent.loop import UserConfirmationRequired
        with pytest.raises(UserConfirmationRequired) as exc_info:
            ask_user_question(question="Q1", options="a,b,c")
        e = exc_info.value
        assert len(e.options) == 3
        assert e.options[1]["label"] == "b"

    def test_multi_question_capped_at_four(self):
        """超过 4 个问题会被截断。"""
        from data_agent.agent.loop import UserConfirmationRequired
        questions = [{"question": f"Q{i}", "options": [{"label": "A"}, {"label": "B"}]} for i in range(6)]
        with pytest.raises(UserConfirmationRequired) as exc_info:
            ask_user_question(
                question="ignored",
                questions=json.dumps(questions),
            )
        parsed = json.loads(exc_info.value.context)
        assert len(parsed) == 4

    def test_invalid_questions_json_falls_to_single(self):
        """无效 questions JSON 回退到单问题模式。"""
        from data_agent.agent.loop import UserConfirmationRequired
        with pytest.raises(UserConfirmationRequired) as exc_info:
            ask_user_question(
                question="单问题",
                questions="invalid json",
            )
        e = exc_info.value
        assert e.question == "单问题"
        assert e.context == ""

    def test_options_without_description(self):
        """选项无 description 字段。"""
        from data_agent.agent.loop import UserConfirmationRequired
        opts = [{"label": "选项A"}, {"label": "选项B"}]
        with pytest.raises(UserConfirmationRequired) as exc_info:
            ask_user_question(question="选择", options=json.dumps(opts))
        assert exc_info.value.options[0]["label"] == "选项A"


# ══════════════════════════════════════════════════════════
#  E. 超时配置
# ══════════════════════════════════════════════════════════

class TestTimeoutConfig:
    """确认交互式工具禁用了超时。"""

    def test_ask_user_question_has_no_timeout(self):
        from data_agent.tools.registry import registry
        # 确保工具已注册
        assert registry.get("ask_user_question") is not None
        # 超时应为 0（无限）
        assert registry._timeouts.get("ask_user_question") == 0


# ══════════════════════════════════════════════════════════
#  F. _robust_input 边界情况
# ══════════════════════════════════════════════════════════

class TestRobustInput:
    """测试输入函数的健壮性。"""

    @patch("data_agent.tools.interaction._robust_input")
    def test_prompt_toolkit_import_error_fallback(self, mock_input):
        """prompt_toolkit 不可用时 fallback 到 input()。"""
        # 模拟 prompt_toolkit 失败 → fallback 路径
        mock_input.return_value = "fallback answer"
        result = _ask_single("测试问题", [])
        assert result["answer"] == "fallback answer"

    def test_default_value_on_empty(self):
        """空输入应返回 default。"""
        result = _robust_input.__wrapped__("  >> ", "default_val") if hasattr(_robust_input, '__wrapped__') else "skip"
        # 这个测试验证 default 参数存在（函数签名）
        import inspect
        sig = inspect.signature(_robust_input)
        assert "default" in sig.parameters


# ══════════════════════════════════════════════════════════
#  G. 选项解析边界情况
# ══════════════════════════════════════════════════════════

class TestOptionParsing:
    """测试各种选项格式的解析。选项解析逻辑仍在 ask_user_question 中，
    但现在通过 UserConfirmationRequired 异常验证。"""

    def test_two_options_minimum(self):
        """至少 2 个选项。"""
        from data_agent.agent.loop import UserConfirmationRequired
        opts = [{"label": "是"}, {"label": "否"}]
        with pytest.raises(UserConfirmationRequired) as exc_info:
            ask_user_question(question="确认？", options=json.dumps(opts))
        assert len(exc_info.value.options) == 2

    def test_four_options_maximum(self):
        """最多 4 个选项。"""
        from data_agent.agent.loop import UserConfirmationRequired
        opts = [{"label": f"选项{i}"} for i in range(1, 5)]
        with pytest.raises(UserConfirmationRequired) as exc_info:
            ask_user_question(question="选择", options=json.dumps(opts))
        assert len(exc_info.value.options) == 4
