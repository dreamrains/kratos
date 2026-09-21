"""P1-5b：M01 型"数据性质"问题转条件式发布指引（不挂起）。

RED 素材为 Codex 批次真实轨迹回放：
tmp/p08-real-provider-20260921-8ca3985-r1/sessions/a3e5bd3e8eb3
（M01 终稿已完整可发布——数据事实/限制/条件性建议 A-C 齐备——却在结尾
以 ask_user_question 问"这数据是示例还是真实"导致整轮挂起）。

治理原则：数据性质（来源状态）是宿主发布包的权威表述（按"未经证实"
渲染，见 publication_synthesis 的 provenance 标注）；其答案不改变任何
已计算数值，只改变读者的解读框架。因此此类问题不需要用户确认，应降级
为 advisory 工具响应并指引模型以条件式结论发布。
"""

from dataclasses import replace

from data_agent.agent.confirmation import (
    AnswerMode,
    ConfirmationOption,
    ConfirmationRecord,
    ConfirmationRequest,
    ConfirmationStatus,
    QuestionPolicy,
    RequestDisposition,
)
from data_agent.agent.confirmation.runtime import build_direct_question_candidate
from data_agent.agent.loop import UserConfirmationRequired


def _m01_confirmation() -> UserConfirmationRequired:
    """Codex 批次 a3e5bd3e8eb3 挂起记录 direct_e2741ae211eb22574439b538 的原样载荷。"""
    return UserConfirmationRequired(
        question="这份 M01-sales 数据的性质是？这决定了后续能否做真实分析。",
        options=[
            {
                "label": "示例/模板数据",
                "value": "示例/模板数据",
                "description": "仅用于测试流程，无需业务解读",
            },
            {
                "label": "真实数据但字段被简化",
                "value": "真实数据但字段被简化",
                "description": "真实业务，只是当前导出把 channel 合并成 all、amount 被脱敏/占位",
            },
            {
                "label": "真实完整数据",
                "value": "真实完整数据",
                "description": "这确实是全部内容，请基于它给出能做的分析",
            },
            {
                "label": "我还有更全的数据要上传",
                "value": "我还有更全的数据要上传",
                "description": "会补充更多行/列/更长时段的数据",
            },
        ],
        confirmation_type="data_quality_confirmation",
        blocking_reason=(
            "amount 与 channel 均为常量列，导致数据无法支撑任何趋势/对比/留存分析；"
            "需确认是示例数据（应停止业务解读）还是真实数据（需补齐字段/时段）。"
        ),
    )


def _candidate_from(request: UserConfirmationRequired, session_id: str = "m01_replay"):
    return build_direct_question_candidate(
        session_id=session_id,
        turn_id="turn_replay",
        message_version=8,
        request=request,
    )


def test_m01_data_nature_question_downgrades_to_advisory():
    candidate = _candidate_from(_m01_confirmation())

    result = QuestionPolicy().evaluate(candidate)

    assert result.disposition == RequestDisposition.ADVISORY
    # 指引必须落在"条件式发布"上，而不是让模型原地等待
    assert "条件" in result.reason
    assert "来源" in result.reason


def test_r20_provenance_wording_downgrades_to_advisory():
    """R20 轮真实措辞："请确认它是完整、抽样还是测试数据"。"""
    request = UserConfirmationRequired(
        question="请确认它是完整、抽样还是测试数据。",
        options=[
            {"label": "完整数据", "value": "完整数据"},
            {"label": "抽样数据", "value": "抽样数据"},
            {"label": "测试数据", "value": "测试数据"},
        ],
        confirmation_type="data_quality_confirmation",
        blocking_reason="数据性质未知会影响结论的适用范围。",
    )
    candidate = _candidate_from(request)

    result = QuestionPolicy().evaluate(candidate)

    assert result.disposition == RequestDisposition.ADVISORY


def test_legitimate_metric_gaps_still_block():
    """合法业务缺口（单位/分母/时间窗）不得被数据性质降级误伤。"""
    gaps = [
        UserConfirmationRequired(
            question="amount 的货币单位是元还是万元？",
            options=[{"label": "元", "value": "元"}, {"label": "万元", "value": "万元"}],
            confirmation_type="metric_scope",
            blocking_reason="单位直接改变所有金额结论的数量级。",
        ),
        UserConfirmationRequired(
            question="复购率的分母是全部注册用户还是付费用户？",
            options=[
                {"label": "全部注册用户", "value": "全部注册用户"},
                {"label": "付费用户", "value": "付费用户"},
            ],
            confirmation_type="metric_scope",
            blocking_reason="分母口径改变复购率数值。",
        ),
        UserConfirmationRequired(
            question="对比时间窗用近 7 天还是近 30 天？",
            options=[{"label": "近 7 天", "value": "近 7 天"}, {"label": "近 30 天", "value": "近 30 天"}],
            confirmation_type="time_window",
            blocking_reason="时间窗改变所有对比数值。",
        ),
    ]

    for request in gaps:
        candidate = _candidate_from(request)
        result = QuestionPolicy().evaluate(candidate)
        assert result.disposition == RequestDisposition.CONFIRMATION, request.question


def test_resolved_data_nature_answer_is_reused_before_downgrade():
    """用户已回答过的数据性质问题仍按 REUSED 复用，优先级高于降级。"""
    candidate = _candidate_from(_m01_confirmation())
    request = ConfirmationRequest.from_candidate(candidate)
    resolved = replace(
        ConfirmationRecord.from_request(request, now="2026-09-20T18:48:31Z"),
        status=ConfirmationStatus.RESOLVED,
        version=3,
        response="真实完整数据",
    )

    result = QuestionPolicy().evaluate(candidate, existing=(resolved,))

    assert result.disposition == RequestDisposition.REUSED
    assert result.reused_confirmation_id == resolved.confirmation_id


def test_loop_returns_guidance_response_instead_of_suspension(tmp_path, monkeypatch):
    """端到端：真实 M01 载荷经 _execute_single_tool 得到指引文本而非挂起。"""
    import data_agent.agent.loop as loop_module
    from data_agent.agent.loop import AgentLoop

    cfg = loop_module.get_config()
    monkeypatch.setattr(cfg, "sessions_dir", tmp_path)
    monkeypatch.setattr(cfg, "skill_auto_discover", False)
    monkeypatch.setattr(loop_module, "get_config", lambda: cfg)
    monkeypatch.setattr(loop_module.registry, "expand_from_tool_call", lambda _name: None)

    def _raise_m01(_name, _arguments):
        raise _m01_confirmation()

    monkeypatch.setattr(loop_module.registry, "execute", _raise_m01)

    loop = AgentLoop(client=None, session_id="m01_loop_replay")

    class _ToolCall:
        id = "tc_m01"
        name = "ask_user_question"
        arguments = {"question": "这份 M01-sales 数据的性质是？"}

    result = loop._execute_single_tool(_ToolCall(), [_ToolCall()], 0)

    # 非阻断分支返回 None = 续轮（挂起才会返回 SuspendedForConfirmation）
    assert result is None
    guidance = loop.messages[-1]
    assert guidance["role"] == "tool"
    assert "该问题无需用户确认" in guidance["content"]
    assert "条件" in guidance["content"]
    # 没有挂起记录产生
    assert not (tmp_path / "m01_loop_replay" / "confirmations" / "events.jsonl").exists()
