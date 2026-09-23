"""Phase 3: provenance questions cannot acquire a blocking field gap by wording."""

import pytest

from data_agent.agent.confirmation import QuestionPolicy, RequestDisposition
from data_agent.agent.confirmation.runtime import (
    build_direct_question_candidate,
    build_required_question_candidate,
)


def _direct(question, options, *, confirmation_type="data_quality_confirmation", **extra):
    return build_direct_question_candidate(
        session_id="phase3",
        turn_id="m01",
        message_version=1,
        request={
            "question": question,
            "options": [{"label": value, "value": value} for value in options],
            "confirmation_type": confirmation_type,
            "blocking_reason": "模型称该选择会影响后续分析。",
            **extra,
        },
    )


@pytest.mark.parametrize(
    ("question", "options"),
    [
        ("这份 M01-sales 数据的性质是？", ["示例/模板数据", "真实完整数据"]),
        ("它是完整、抽样还是测试数据？", ["完整", "抽样", "测试"]),
        ("channel 全为 all 且 amount 全为 10：这些是真实值常量吗？", ["占位/演示", "真实值，就是常量", "取数有误"]),
        ("请选择该数据的来源和覆盖状态", ["甲", "乙", "丙"]),
    ],
)
def test_model_data_quality_without_host_risk_is_advisory_regardless_of_words(question, options):
    candidate = _direct(question, options)
    result = QuestionPolicy().evaluate(candidate)
    assert result.disposition == RequestDisposition.ADVISORY
    assert "条件" in result.reason


def test_model_cannot_self_certify_field_risk():
    candidate = _direct(
        "确认订单日期的清洗方式？",
        ["按本地日", "按 UTC 日"],
        risk_fields=["order_date"],
        affected_routes=["period_compare"],
        decision_context={
            "decision_kind": "field_semantics",
            "missing_value": "order_date 时区",
            "affected_operations": ["period_compare"],
        },
    )
    assert QuestionPolicy().evaluate(candidate).disposition == RequestDisposition.ADVISORY


def test_host_cleaning_risk_with_affected_route_still_pauses():
    candidate = build_required_question_candidate(
        session_id="phase3",
        turn_id="cleaning",
        message_version=1,
        source="question_need_detector",
        operation="data_quality_confirmation",
        request={
            "question": "请确认订单日期的清洗方式。",
            "confirmation_type": "data_quality_confirmation",
            "risk_fields": ["order_date"],
            "affected_routes": ["period_compare"],
        },
    )
    assert candidate.resolution_params["host_risk_fields"] == ["order_date"]
    assert candidate.resolution_params["host_affected_routes"] == ["period_compare"]
    assert QuestionPolicy().evaluate(candidate).disposition == RequestDisposition.CONFIRMATION


@pytest.mark.parametrize(
    ("risk_fields", "affected_routes"),
    [([], []), (["order_date"], []), ([], ["period_compare"])],
)
def test_internal_data_quality_without_both_risk_and_route_is_advisory(
    risk_fields, affected_routes
):
    candidate = build_required_question_candidate(
        session_id="phase3",
        turn_id="generic",
        message_version=1,
        source="question_need_detector",
        operation="data_quality_confirmation",
        request={
            "question": "确认数据性质",
            "confirmation_type": "data_quality_confirmation",
            "risk_fields": risk_fields,
            "affected_routes": affected_routes,
        },
    )
    assert QuestionPolicy().evaluate(candidate).disposition == RequestDisposition.ADVISORY


def test_detector_route_risk_survives_loop_adapter(tmp_path, monkeypatch):
    """The real auto-suspend path must not discard deterministic detector evidence."""
    import data_agent.agent.loop as loop_module
    from data_agent.agent.loop import AgentLoop

    cfg = loop_module.get_config()
    monkeypatch.setattr(cfg, "sessions_dir", tmp_path)
    monkeypatch.setattr(cfg, "skill_auto_discover", False)
    monkeypatch.setattr(loop_module, "get_config", lambda: cfg)
    loop = AgentLoop(client=None, session_id="phase3_route_risk")
    loop._turn_question_need = {
        "status": "hard_question",
        "question_type": "data_quality_confirmation",
        "question": "请确认 order_date 的清洗方式。",
        "risk_fields": ["order_date"],
        "affected_routes": ["period_compare"],
    }
    loop._pending_confirmation_for_auto_suspend = lambda _state: None
    captured = {}

    def _capture(payload, *, source, operation):
        captured.update(payload)
        captured["source"] = source
        return None

    loop._suspend_for_required_question_payload = _capture
    assert loop._maybe_auto_suspend_for_required_question() is None
    assert captured["source"] == "question_need_detector"
    assert captured["risk_fields"] == ["order_date"]
    assert captured["affected_routes"] == ["period_compare"]


@pytest.mark.parametrize(
    ("confirmation_type", "question"),
    [
        ("metric_scope", "净收益是否扣除渠道成本？"),
        ("metric_scope", "复购率分母是注册用户还是付费用户？"),
        ("time_window", "比较窗口是近 7 天还是近 30 天？"),
    ],
)
def test_explicit_business_gap_still_pauses(confirmation_type, question):
    candidate = _direct(question, ["甲", "乙"], confirmation_type=confirmation_type)
    assert QuestionPolicy().evaluate(candidate).disposition == RequestDisposition.CONFIRMATION
