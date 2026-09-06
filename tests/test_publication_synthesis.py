from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.loop import AgentLoop
from data_agent.agent.publication_synthesis import (
    build_publication_packet,
    extract_publication_facts,
    render_verified_appendix,
)


def _curve_data():
    return {
        "method": "curve_family_comparison",
        "status": "supported",
        "effective_n": 62,
        "best_family": "exponential",
        "fits": [{"family": "exponential", "parameters": {"a": 0.18800129}, "r_squared": 0.98240474}],
        "limitations": ["拟合只描述当前观测范围。"],
    }


def _period_data():
    return {
        "metric": "revenue",
        "period_a": {"value": 1818, "day_count": 15},
        "period_b": {"value": 684, "day_count": 15},
        "total_change": -1134,
        "order_count": 71,
        "natural_days": 30,
    }


def _receipt(tool_name, receipt_id, data):
    from data_agent.agent.publication_synthesis import publication_contract

    return {
        "id": receipt_id,
        "tool_name": tool_name,
        "result_sha256": "sha256:test",
        "result_preview": f"{tool_name} completed",
        "publication_facts": extract_publication_facts(data),
        "publication_contract": publication_contract(tool_name, data),
    }


def test_packet_carries_curve_values_that_the_final_model_must_not_reconstruct_from_history():
    state = AnalysisSessionState(session_id="publication_curve")
    state.add_tool_receipt(_receipt("curve_fitting", "tr_curve", _curve_data()))

    packet = build_publication_packet(
        state,
        user_input="拟合留存曲线并说明边界",
        substantive_tools={"curve_fitting"},
    )

    assert packet["status"] == "ready"
    values = {fact["value"] for fact in packet["sources"][0]["facts"]}
    assert {"0.18800129", "0.98240474", "62"} <= values
    rendered = render_verified_appendix(packet)
    assert "0.18800129" in rendered
    assert "0.98240474" in rendered
    assert "tr_curve" in rendered


def test_packet_renders_period_comparison_anchors_from_receipts_not_model_text():
    state = AnalysisSessionState(session_id="publication_period")
    state.add_tool_receipt(_receipt("compare_periods", "tr_period", _period_data()))
    packet = build_publication_packet(
        state,
        user_input="比较前后两个周期",
        substantive_tools={"compare_periods"},
    )

    rendered = render_verified_appendix(packet)
    for anchor in ("1818", "684", "71", "30"):
        assert anchor in rendered


def test_metric_period_totals_outscore_calendar_detail_in_the_fact_budget():
    facts = extract_publication_facts({
        "period_a": {"day_count": 15, "weekday_count": 11},
        "period_b": {"day_count": 15, "weekday_count": 11},
        "metrics": {"revenue": {"period_a": 1818, "period_b": 684, "diff": -1134}},
    })
    values = {item["value"] for item in facts}

    assert {"1818", "684", "-1134"} <= values


def test_combined_period_scope_is_retained_in_the_bounded_fact_budget():
    facts = extract_publication_facts({
        "period_a": {
            "rows": 47, "day_count": 15, "weekday_count": 11, "weekend_count": 4,
            "label": "前期", "range": "2026-04-07~2026-04-21",
        },
        "period_b": {
            "rows": 24, "day_count": 15, "weekday_count": 11, "weekend_count": 4,
            "label": "后期", "range": "2026-04-22~2026-05-06",
        },
        "combined": {"row_count": 71, "day_count": 30},
        "metrics": {"revenue": {
            "period_a": 1818, "period_b": 684, "diff": -1134,
            "change_pct": -62.38, "daily_avg_a": 121.2,
            "daily_avg_b": 45.6, "daily_avg_change_pct": -62.38,
        }},
    })
    by_path = {item["path"]: item["value"] for item in facts}

    assert by_path["combined.row_count"] == "71"
    assert by_path["combined.day_count"] == "30"
    assert by_path["metrics.revenue.period_a"] == "1818"
    assert by_path["metrics.revenue.period_b"] == "684"


def test_structured_result_preview_does_not_duplicate_raw_json_into_publication():
    state = AnalysisSessionState(session_id="publication_compact_preview")
    receipt = _receipt("compare_periods", "tr_compact", _period_data())
    receipt["result_preview"] = '{"period_a":{"rows":46,"dates":["2026-04-07"]}}'
    state.add_tool_receipt(receipt)

    packet = build_publication_packet(
        state,
        user_input="比较前后两个周期",
        substantive_tools={"compare_periods"},
    )
    rendered = render_verified_appendix(packet)

    assert "结构化计算结果" in rendered
    assert '"dates"' not in rendered


def test_loop_persists_packet_without_exposing_receipts_after_finalization(monkeypatch):
    from data_agent.config import get_config

    monkeypatch.setattr(get_config(), "wrap_up_round", 1)
    loop = AgentLoop(client=None, session_id="publication_loop")
    loop._reset_turn_tracking()
    loop._record_turn_tool_result(
        "curve_fitting",
        "curve completed",
        structured_data=_curve_data(),
    )
    loop._maybe_inject_wrap_up(1, "拟合留存曲线")

    assert loop._turn_finalization_mode is False
    assert loop._turn_publication_packet["status"] == "ready"
    assert loop.context.analysis_state.publication_packets[-1]["id"] == loop._turn_publication_packet["id"]

    published, error = loop._render_finalized_publication("结论：曲线拟合良好，但仅限当前观测范围。")
    assert error is None
    assert published == "结论：曲线拟合良好，但仅限当前观测范围。"
    assert "本轮计算收据" not in published


def test_terminal_publication_prepares_the_packet_without_waiting_for_wrap_up():
    loop = AgentLoop(client=None, session_id="publication_terminal")
    loop._reset_turn_tracking()
    loop._record_turn_tool_result(
        "compare_periods",
        "period comparison completed",
        structured_data=_period_data(),
    )

    published, error = loop._render_terminal_publication(
        "比较前后两个周期",
        "模型说明：结果是描述性的，不构成因果结论。",
    )

    assert error is None
    assert published == "模型说明：结果是描述性的，不构成因果结论。"
    assert "本轮计算收据" not in published
    assert loop.context.analysis_state.publication_packets[-1]["status"] == "ready"


def test_packet_is_incomplete_without_a_successful_substantive_receipt():
    state = AnalysisSessionState(session_id="publication_empty")
    packet = build_publication_packet(
        state,
        user_input="分析数据",
        substantive_tools={"compare_periods"},
    )

    assert packet["status"] == "incomplete"


def test_packet_uses_only_current_turn_receipts_and_state_roundtrip_preserves_it():
    state = AnalysisSessionState(session_id="publication_isolation")
    state.add_tool_receipt(_receipt("compare_periods", "tr_old", {"total_change": 999}))
    state.add_tool_receipt(_receipt("compare_periods", "tr_current", _period_data()))

    packet = build_publication_packet(
        state,
        user_input="比较本轮上传的数据",
        substantive_tools={"compare_periods"},
        receipt_ids=["tr_current"],
    )
    state.add_publication_packet(packet)
    restored = AnalysisSessionState.from_dict(state.to_dict(), state.session_id)

    assert [source["receipt_id"] for source in packet["sources"]] == ["tr_current"]
    assert restored.publication_packets[-1]["id"] == packet["id"]


def test_streaming_finalization_persists_without_exposing_the_verified_appendix():
    from data_agent.llm.client import Response

    loop = AgentLoop(client=None, session_id="publication_stream")
    loop.context.analysis_state.add_tool_receipt(_receipt("curve_fitting", "tr_stream", _curve_data()))
    original_reset = loop._reset_turn_tracking

    def reset_with_packet():
        original_reset()
        loop._turn_finalization_mode = True
        loop._turn_publication_packet = build_publication_packet(
            loop.context.analysis_state,
            user_input="拟合留存曲线",
            substantive_tools={"curve_fitting"},
        )

    loop._reset_turn_tracking = reset_with_packet
    loop._prepare_analysis_turn = lambda _user_input: None
    loop._ensure_mcp_initialized = lambda: None
    loop._should_continue_for_analysis_quality = lambda *_args: False
    loop._verify_before_publication = lambda *_args: None
    loop._maybe_archive = lambda *_args: None
    loop._auto_save = lambda: None

    def direct_final(_round_num):
        text = "曲线在已观察区间内拟合良好。"
        yield {"type": "text_delta", "text": text, "turn_id": None}
        yield {"type": "_response", "response": Response(text=text), "streamed_text": text}

    loop._stream_llm_round = direct_final
    events = list(loop.stream_turn("拟合留存曲线"))
    published = "".join(str(event.get("text") or "") for event in events if event.get("type") == "text_delta")

    assert published == "曲线在已观察区间内拟合良好。"
    assert "本轮计算收据" not in published
    assert loop.messages[-1]["content"] == published


def test_streaming_publication_rewrites_once_and_never_projects_rejected_narrative():
    from data_agent.llm.client import Response
    from data_agent.session.public_messages import assistant_replies

    loop = AgentLoop(client=None, session_id="publication_repair")
    loop.context.analysis_state.add_tool_receipt(_receipt("curve_fitting", "tr_repair", _curve_data()))
    original_reset = loop._reset_turn_tracking

    def reset_with_packet():
        original_reset()
        loop._turn_finalization_mode = True
        loop._turn_publication_packet = build_publication_packet(
            loop.context.analysis_state,
            user_input="解释留存曲线",
            substantive_tools={"curve_fitting"},
        )

    loop._reset_turn_tracking = reset_with_packet
    loop._prepare_analysis_turn = lambda _user_input: None
    loop._ensure_mcp_initialized = lambda: None
    loop._should_continue_for_analysis_quality = lambda *_args: False
    loop._verify_before_publication = lambda *_args: None
    loop._maybe_archive = lambda *_args: None
    loop._auto_save = lambda: None
    answers = iter([
        "这6个零值均为未观测值而非真实零，可用于LTV预测。",
        "零值含义未知；当前拟合只描述已观察区间，不支持LTV预测。",
    ])

    def direct_final(_round_num):
        text = next(answers)
        yield {"type": "text_delta", "text": text, "turn_id": None}
        yield {"type": "_response", "response": Response(text=text), "streamed_text": text}

    loop._stream_llm_round = direct_final
    events = list(loop.stream_turn("解释留存曲线"))
    published = "".join(str(event.get("text") or "") for event in events if event.get("type") == "text_delta")
    public = assistant_replies(loop.messages, loop.session_id)

    assert "这6个零值" not in published
    assert "这6个零值" not in "\n".join(reply["content"] for reply in public)
    assert "零值含义未知" in published
    assert sum(message.get("publication_rejected") is True for message in loop.messages) == 1
