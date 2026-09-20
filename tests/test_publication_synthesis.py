from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.loop import AgentLoop
from data_agent.agent.publication_synthesis import (
    build_publication_packet,
    extract_publication_facts,
    render_publication_receipt_markdown,
    render_verified_appendix,
    validate_final_narrative,
    validate_final_narrative_issues,
)
from datetime import date, timedelta

import pytest


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
    assert loop._turn_publication_packet["phase"] == "preview"
    assert loop.context.analysis_state.publication_packets == []

    published, error = loop._render_terminal_publication(
        "拟合留存曲线",
        "结论：曲线拟合良好，但仅限当前观测范围。",
    )
    assert error is None
    assert published == "结论：曲线拟合良好，但仅限当前观测范围。"
    assert "本轮计算收据" not in published
    final_packet = loop.context.analysis_state.publication_packets[-1]
    assert final_packet["phase"] == "final"
    assert final_packet["answer_sha256"].startswith("sha256:")


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


def test_terminal_publication_rebuilds_a_ready_preview_after_late_evidence():
    loop = AgentLoop(client=None, session_id="publication_refresh")
    loop._reset_turn_tracking()
    early_id = loop._record_turn_tool_result(
        "run_python", "early", structured_data={"metric": "收入", "value": 100},
    )
    preview = loop._prepare_publication_packet("分析收入和复购率", phase="preview", persist=False)
    assert preview and preview["phase"] == "preview"

    late_id = loop._record_turn_tool_result(
        "run_python", "late", structured_data={"metric": "复购率", "value": 0.2},
    )
    loop.context.analysis_state.add_evidence_record({
        "id": "ev_late", "claim": "复购率为20%", "tool_receipt_ids": [late_id],
        "limitations": [],
    })

    published, error = loop._render_terminal_publication(
        "分析收入和复购率", "收入为100，复购率为20%。",
    )

    assert error is None
    assert published
    final = loop.context.analysis_state.publication_packets[-1]
    assert final["phase"] == "final"
    assert final["snapshot_digest"] != preview["snapshot_digest"]
    assert {source["receipt_id"] for source in final["sources"]} == {early_id, late_id}
    assert [item["evidence_id"] for item in final["evidence"]] == ["ev_late"]


def test_packet_digest_changes_when_validation_or_result_content_changes():
    state = _packet_state([_receipt("run_python", "tr_one", {"metric": "收入", "value": 10})])
    state.verification_reports = [{"overall_status": "pass"}]
    packet_a = build_publication_packet(state, user_input="分析收入", substantive_tools={"run_python"})
    state.verification_reports[-1]["overall_status"] = "fail"
    packet_b = build_publication_packet(state, user_input="分析收入", substantive_tools={"run_python"})
    state.tool_receipts[0]["result_sha256"] = "sha256:changed"
    packet_c = build_publication_packet(state, user_input="分析收入", substantive_tools={"run_python"})

    assert packet_a["snapshot_digest"] != packet_b["snapshot_digest"]
    assert packet_b["snapshot_digest"] != packet_c["snapshot_digest"]


def test_python_business_output_outranks_replay_metadata_and_keeps_tail_lines():
    data = {
        "output": "概览完成\nD1普通均值=17.080%\nD1加权均值=16.803%\nweighted_delta=0.00277",
        "risk_level": "low",
        "execution_label": "exploratory_sandbox",
        "replay": {"code": "print('x')", "code_sha256": "abc", "timeout_seconds": 30},
    }
    facts = extract_publication_facts(data, max_facts=20)
    paths = [fact["path"] for fact in facts]
    values = [fact["value"] for fact in facts]

    assert any("weighted_delta=0.00277" in value for value in values)
    assert not any(path.startswith("replay") for path in paths)
    assert "risk_level" not in paths
    assert "execution_label" not in paths


def test_all_group_request_uses_natural_order_and_retains_twelve_complete_groups():
    data = {"groups": [
        {"name": f"segment_{i}", "revenue": i * 100, "count": i * 10}
        for i in range(12)
    ]}
    receipt = {
        "id": "tr_groups_12", "tool_name": "run_python", "result_sha256": "sha256:g12",
        "result_preview": "all groups", "publication_facts": extract_publication_facts(data, max_facts=100),
    }
    packet = build_publication_packet(
        _packet_state([receipt]), user_input="逐一列出全部分组", substantive_tools={"run_python"},
    )
    facts = packet["sources"][0]["facts"]
    names = [fact["value"] for fact in facts if fact["path"].endswith(".name")]

    assert names == [f"segment_{i}" for i in range(12)]
    assert len(facts) == 36


def test_explicit_arithmetic_mismatch_is_rejected_but_correct_rounding_passes():
    packet = {"publication_scope": []}

    bad = validate_final_narrative_issues("日新增22400人，D7留存5.1%，约为1.14万人。", packet)
    good = validate_final_narrative_issues("日新增22400人，D7留存5.1%，约为1142人。", packet)

    assert any(issue["code"] == "arithmetic_mismatch" for issue in bad)
    assert not any(issue["code"] == "arithmetic_mismatch" for issue in good)


def test_nonzero_mean_cannot_be_described_as_zero_cv_denominator():
    bad = validate_final_narrative_issues(
        "amount 描述统计：mean=10.0、std=0.0、min=10，变差系数 CV 无定义（分母为 0）。"
    )
    good_zero = validate_final_narrative_issues(
        "amount 描述统计：mean=0.0、std=0.0，变差系数 CV 无定义（分母为 0）。"
    )
    good_computed = validate_final_narrative_issues(
        "amount 描述统计：mean=10.0、std=0.0，变差系数 CV=0。"
    )

    assert any(issue["code"] == "coefficient_variation_denominator_mismatch" for issue in bad)
    assert not any(issue["code"] == "coefficient_variation_denominator_mismatch" for issue in good_zero)
    assert not any(issue["code"] == "coefficient_variation_denominator_mismatch" for issue in good_computed)


def test_constant_sample_does_not_license_data_origin_or_population_claims():
    unsupported = validate_final_narrative_issues(
        "amount 全等于 10，极可能是脱敏/占位/示意数据，真实业务波动为零。"
    )
    question = validate_final_narrative_issues(
        "amount 全等于 10；需确认该文件是否为占位或样例数据。"
    )

    assert any(issue["code"] == "unsupported_data_origin_inference" for issue in unsupported)
    assert not any(issue["code"] == "unsupported_data_origin_inference" for issue in question)


def test_plain_language_non_ledger_inference_is_rejected():
    issues = validate_final_narrative_issues(
        "每笔 amount 都是 10。这大概率是份占位/样例数据，不是真账本。"
    )

    assert any(issue["code"] == "unsupported_data_origin_inference" for issue in issues)


def test_unqualified_human_rule_and_constructed_sample_claims_are_rejected():
    human_rule = validate_final_narrative_issues(
        "样本极小（12 行）且为人为规则数据。"
    )
    constructed = validate_final_narrative_issues(
        "各来源均上涨 10%，呈现出构造样例特征，更可能是数据本身为样例。"
    )
    bounded = validate_final_narrative_issues(
        "各来源均上涨 10%；需确认该文件是否为构造样例。"
    )

    assert any(issue["code"] == "unsupported_data_origin_inference" for issue in human_rule)
    assert any(issue["code"] == "unsupported_data_origin_inference" for issue in constructed)
    assert not any(issue["code"] == "unsupported_data_origin_inference" for issue in bounded)


@pytest.mark.parametrize("text", [
    "该数据是测试数据。",
    "该样本由机器生成。",
    "这是合成数据。",
    "这个文件是人工构造的。",
    "这些记录并非真实账本。",
])
def test_unqualified_provenance_assertions_require_evidence(text):
    issues = validate_final_narrative_issues(text)

    assert any(issue["code"] == "unsupported_data_origin_inference" for issue in issues)


@pytest.mark.parametrize("text", [
    "需确认该数据是否为测试数据。",
    "尚不清楚该样本是否由机器生成。",
    "无法判断这些记录是否来自真实账本。",
    "分析文件: M01-sales.csv",
])
def test_bounded_provenance_language_and_source_labels_publish(text):
    issues = validate_final_narrative_issues(text)

    assert not any(issue["code"] == "unsupported_data_origin_inference" for issue in issues)


def test_structured_provenance_fact_licenses_the_matching_assertion_only():
    packet = {
        "publication_scope": [],
        "sources": [{
            "facts": [
                {"path": "metadata.provenance", "value": "synthetic"},
            ],
        }],
    }

    supported = validate_final_narrative_issues("这是合成数据。", packet)
    unsupported = validate_final_narrative_issues("该样本由机器生成。", packet)

    assert not any(issue["code"] == "unsupported_data_origin_inference" for issue in supported)
    assert any(issue["code"] == "unsupported_data_origin_inference" for issue in unsupported)


def test_missing_cost_cannot_be_rewritten_as_zero_by_pronoun():
    bad = validate_final_narrative_issues(
        "渠道成本字段未提供，因此净收益无法计算。口径决定怎么减，数据决定减多少，后者当前为零。"
    )
    explicit_zero = validate_final_narrative_issues(
        "渠道成本由账本计算为零；代金券成本字段未提供，因此净收益无法计算。"
    )

    assert any(issue["code"] == "missing_value_coerced_to_zero" for issue in bad)
    assert not any(issue["code"] == "missing_value_coerced_to_zero" for issue in explicit_zero)


def test_explicit_subquestion_requires_visible_result_or_specific_gap():
    state = _packet_state([_receipt(
        "run_python",
        "tr_requirements",
        {"收入": {"value": 100}, "复购率": {"value": 0.2}},
    )])
    packet = build_publication_packet(
        state,
        user_input="请回答收入和复购率",
        substantive_tools={"run_python"},
    )

    assert [item["label"] for item in packet["requirements"]] == ["收入", "复购率"]
    missing = validate_final_narrative_issues("收入为100元。", packet)
    complete = validate_final_narrative_issues("收入为100元，复购率为20%。", packet)
    explicit_gap = validate_final_narrative_issues("收入为100元；复购率因缺少用户分母而无法计算。", packet)

    assert any(
        issue["code"] == "missing_answer_requirement" and issue["span"] == "复购率"
        for issue in missing
    )
    assert not any(issue["code"] == "missing_answer_requirement" for issue in complete)
    assert not any(issue["code"] == "missing_answer_requirement" for issue in explicit_gap)


def test_requirement_keyword_without_result_or_gap_is_not_complete():
    packet = {
        "publication_scope": [],
        "requirements": [{"id": "rq_repeat", "label": "复购率", "origin": "joined"}],
    }

    issues = validate_final_narrative_issues("复购率方面后续会继续观察。", packet)

    assert any(issue["code"] == "missing_answer_requirement" for issue in issues)


def test_adjacent_requirement_number_does_not_cover_the_next_requirement():
    packet = {
        "publication_scope": [],
        "requirements": [
            {"id": "rq_revenue", "label": "收入", "origin": "joined"},
            {"id": "rq_repeat", "label": "复购率", "origin": "joined"},
        ],
    }

    issues = validate_final_narrative_issues("收入为100元。复购率方面后续观察。", packet)

    assert any(
        issue["code"] == "missing_answer_requirement" and issue["span"] == "复购率"
        for issue in issues
    )


def test_arithmetic_ignores_date_prefix_and_an_explicitly_corrected_quote():
    packet = {"publication_scope": []}

    dated = validate_final_narrative_issues(
        "2026年新增22400人，D7留存5.1%，约为1142人。", packet,
    )
    correction = validate_final_narrative_issues(
        "“22400人乘5.1%约为1.14万人”这个说法错误，正确约为1142人。", packet,
    )

    assert not any(issue["code"] == "arithmetic_mismatch" for issue in dated)
    assert not any(issue["code"] == "arithmetic_mismatch" for issue in correction)


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


# ── P3 (D02): claim-scoped publication checks (N01–N09, N11) ──


def _retention_curve_data(max_day: int = 7) -> dict:
    return {
        "method": "curve_family_comparison",
        "status": "supported",
        "points": [{"x": day, "y": round(0.5 * day ** -0.4, 4)} for day in range(1, max_day + 1)],
        "fits": [{"family": "power", "parameters": {"a": 0.5, "b": -0.4}, "r_squared": 0.97}],
        "limitations": ["拟合只描述观测区间。"],
    }


def _receipt_with_args(tool_name, receipt_id, data, args=None):
    from data_agent.agent.publication_synthesis import publication_contract

    return {
        "id": receipt_id,
        "tool_name": tool_name,
        "result_sha256": "sha256:test",
        "result_preview": f"{tool_name} completed",
        "publication_facts": extract_publication_facts(data),
        "publication_contract": publication_contract(tool_name, data, args=args),
    }


def _retention_packet(extra_receipts=(), substantive=None):
    state = AnalysisSessionState(session_id="n_series_packet")
    # P7-F01/R1：曲线来源必须携带 dataset 身份，主张按来源绑定范围检查。
    state.add_tool_receipt(_receipt_with_args(
        "curve_fitting", "tr_ret", _retention_curve_data(), args={"name": "渠道 A"},
    ))
    for receipt in extra_receipts:
        state.add_tool_receipt(receipt)
    return build_publication_packet(
        state,
        user_input="留存分析",
        substantive_tools=substantive or {"curve_fitting", "ab_test", "causal_analysis"},
    )


def _retention_packet_for_fits(fits):
    state = AnalysisSessionState(session_id="n_series_multi_fit")
    data = _retention_curve_data()
    data["fits"] = fits
    state.add_tool_receipt(_receipt_with_args(
        "curve_fitting", "tr_multi_fit", data, args={"name": "渠道 A"},
    ))
    return build_publication_packet(
        state,
        user_input="留存拟合敏感性分析",
        substantive_tools={"curve_fitting"},
    )


def _ab_test_data() -> dict:
    return {
        "metric": "revenue",
        "test": {"statistic": 2.4, "p_value": 0.02, "significant": True},
        "limitations": [],
    }


def _causal_data() -> dict:
    return {
        "method": "DID",
        "effect": 12.3,
        "p_value": 0.03,
        "limitations": [],
    }


LEGAL_D30_BOUNDARIES = [
    "目前暂不具备 D30 预测条件。",
    "D30 预测尚缺外推基础。",
    "D30 无从推算。",
    "现有证据无法支持 D30 的点估计。",
    "对 D30 暂不作方向判断。",
    "是否可以预测 D30？",
    "为什么当前阻断 D30 预测？",
    "建议继续观测至第 30 天再判断。",
    "如果 D30 达到预先阈值，则继续试点。",
    "D7 留存为 10%，当前不能预测 D30。",
    "D30 目前不可预测，只有 D1 至 D7 的观测。",
    "当前数据不足以支持对 D30 的预测，因此不报告 D30 数值。",
    "观测区间内的拟合不构成 D30 预测依据。",
    "能否预测 D30——当前证据分级。",
    "请把任何 D30 数字视为假设而非预测。",
    "D30 尚未观测。",
    "D30 缺少验证窗口。",
    "暂时没有 D30 的证据基础。",
    "D30 方向未知。",
    "现阶段无法形成 D30 结论。",
    "不应从 D7 直接外推 D30。",
    "当前不发布 D30 趋势判断。",
    "D30 外推条件尚未满足。",
    "已有数据不能用于估计 D30。",
    "D30 的变化方向仍不清楚。",
    "D30 不在当前观测窗口内。",
    "需要补充 D8 至 D30 数据后再验证。",
    "关于 D30 的结论仍待验证。",
    "D30 应保持为未知项。",
    "当前没有经过验证的 D30 结果。",
    "本轮没有计算 D30。",
    "D30 标记为未计算。",
]


ILLEGAL_D30_CLAIMS = [
    "预计 D30 将达到 5%。",
    "D30 留存大约是 5%。",
    "预测 D30 会继续下降。",
    "D30 将保持稳定。",
    "D30 预计处于低位。",
    "不能预测 D30，但 D30 大约是 5%。",
    "D30 留存为 0.05。",
    "D30 约 0.05。",
    "D30 会继续上升。",
    "D30 将出现反弹。",
    "D30 预计改善。",
    "D30 会回落。",
    "D30 将保持高位。",
    "D30 留存将翻倍。",
    "D30 将提高 8 个百分点。",
    "D30 留存将在 4% 至 6% 之间。",
    "D30 不低于 5%。",
    "渠道 A 的 D30 留存为 5%。",
]


AUDITABLE_D30_SCENARIO = (
    "以下仅为拟合外推情景，不是经过验证的预测；假设 D1-D7 的幂律关系延续至 D30。"
    "幂律模型 R²=0.97，未做留出、回测或 D30 验证；不同模型结果应作为敏感性分析。"
    "幂律情景下 D30 留存约为 12.83%。"
)


class TestNSeriesPublication:

    @pytest.mark.parametrize("text", LEGAL_D30_BOUNDARIES)
    def test_n01_legal_d30_paraphrases_publish(self, text):
        assert validate_final_narrative(text, _retention_packet()) is None

    @pytest.mark.parametrize("text", ILLEGAL_D30_CLAIMS)
    def test_n03_affirmative_d30_claims_are_rejected(self, text):
        assert validate_final_narrative(text, _retention_packet()) is not None

    def test_n03_receipt_bound_scenario_extrapolation_with_full_disclosure_publishes(self):
        assert validate_final_narrative(AUDITABLE_D30_SCENARIO, _retention_packet()) is None

    def test_n03_scenario_caveats_do_not_rescue_wrong_extrapolation_arithmetic(self):
        wrong = AUDITABLE_D30_SCENARIO.replace("12.83%", "5%")
        assert validate_final_narrative(wrong, _retention_packet()) is not None

    def test_n03_scenario_requires_validation_and_sensitivity_disclosures(self):
        incomplete = (
            "假设 D1-D7 的幂律关系延续，幂律模型 R²=0.97。"
            "幂律情景下 D30 留存约为 12.83%。"
        )
        assert validate_final_narrative(incomplete, _retention_packet()) is not None

    def test_n03_inline_multi_family_sensitivity_recomputes_each_value(self):
        packet = _retention_packet_for_fits([
            {"family": "power", "parameters": {"a": 0.5, "b": -0.4}, "r_squared": 0.97},
            {"family": "exponential", "parameters": {"a": 0.5, "b": -0.1}, "r_squared": 0.91},
        ])
        disclosure = (
            "以下仅为拟合外推情景，不是经过验证的预测；幂律 R²=0.97，指数 R²=0.91，"
            "未做留出、回测或 D30 验证；不同模型结果仅作敏感性分析。"
        )
        correct = disclosure + "延伸至 D30：指数约 2.49%，幂律约 12.83%。"
        wrong_second = disclosure + "延伸至 D30：指数约 2.49%，幂律约 3.27%。"

        assert validate_final_narrative(correct, packet) is None
        assert validate_final_narrative(wrong_second, packet) is not None

    def test_n03_markdown_d30_column_audits_each_row_value(self):
        prefix = (
            "以下仅为拟合外推情景，不是经过验证的预测；幂律模型 R²=0.97，"
            "未做留出、回测或 D30 验证；不同模型结果仅作敏感性分析。\n"
        )
        correct = prefix + "| 模型 | D30 |\n| --- | --- |\n| 幂律 | 12.83% |"
        wrong = prefix + "| 模型 | D30 |\n| --- | --- |\n| 幂律 | 5.00% |"

        assert validate_final_narrative(correct, _retention_packet()) is None
        assert validate_final_narrative(wrong, _retention_packet()) is not None

    def test_n03_markdown_d30_column_does_not_bind_another_percentage_column(self):
        text = (
            "以下仅为拟合外推情景，不是经过验证的预测；幂律模型 R²=0.97，"
            "未做留出、回测或 D30 验证；不同模型结果仅作敏感性分析。\n"
            "| 模型 | R² | D30 |\n| --- | --- | --- |\n| 幂律 | 97% | 12.83% |"
        )

        assert validate_final_narrative(text, _retention_packet()) is None


def test_provenance_question_is_not_misread_as_an_asserted_origin():
    assert validate_final_narrative(
        "请确认该文件是完整、抽样还是测试数据？", _retention_packet()
    ) is None


def test_ordinary_sample_size_language_is_not_a_provenance_classification():
    assert validate_final_narrative(
        "The observed sample size is 7, so uncertainty remains high.", _retention_packet()
    ) is None


@pytest.mark.parametrize("text", [
    "下面用一个样例说明计算过程。",
    "附上演示数据的加载代码。",
    "这不是占位数据，是真实流水。",
    "请问这是不是测试数据？",
])
def test_non_assertive_or_negated_provenance_mentions_publish(text):
    issues = validate_final_narrative_issues(text, _retention_packet())

    assert not any(issue["code"] == "unsupported_data_origin_inference" for issue in issues)


@pytest.mark.parametrize("text", [
    "该文件是单一取值的样例数据。",
    "数据来源分类：占位数据。",
    "当前交付的这份文件属于测试数据。",
])
def test_provenance_taxonomy_rejects_unsupported_assertions_without_phrase_enumeration(text):
    error = validate_final_narrative(text, _retention_packet())
    assert error is not None
    assert "unsupported_data_origin_inference" in error

    def test_n01_boundary_statement_with_d30_publishes(self):
        packet = _retention_packet()
        assert validate_final_narrative(
            "D7 留存为 10%。当前不能预测 D30，需补充数据。", packet,
        ) is None

    def test_n01_full_missing_observation_boundary_is_not_misread_as_prediction(self):
        packet = _retention_packet()
        assert validate_final_narrative(
            "D30 目前不可预测：本数据只有 D1–D7，没有 D8–D30 的任何观测，也没有验证窗口。",
            packet,
        ) is None

    def test_n01_withheld_d30_number_is_not_misread_as_prediction(self):
        packet = _retention_packet()
        assert validate_final_narrative(
            "当前数据不足以支持对 D30 的预测，因此我不报告任何 D30 数值。",
            packet,
        ) is None

    def test_n01_not_a_prediction_basis_is_not_misread_as_prediction(self):
        packet = _retention_packet()
        assert validate_final_narrative(
            "曲线拟合为观测区间内的描述，不构成 D30 或任何未来天数的预测依据。",
            packet,
        ) is None

    def test_n01_prediction_question_heading_is_not_misread_as_prediction(self):
        packet = _retention_packet()
        assert validate_final_narrative(
            '## 三、“能否预测 D30”——证据分级\nD30 当前不能预测：只有 D1–D7 观测。',
            packet,
        ) is None

    def test_n01_prediction_barrier_table_heading_is_not_misread_as_prediction(self):
        packet = _retention_packet()
        assert validate_final_narrative(
            "| 判断维度 | 现状（均来自已加载数据） | 为什么阻断 D30 预测 |", packet,
        ) is None

    def test_n01_non_predictive_hypothesis_reference_publishes_without_a_value(self):
        packet = _retention_packet()
        assert validate_final_narrative(
            "在此之前，请把任何 D30 数字视为假设，而非预测。", packet,
        ) is None

    def test_n01_hypothesis_label_does_not_license_an_unobserved_value(self):
        packet = _retention_packet()
        error = validate_final_narrative(
            "D30 的 5% 只是一个假设，而非预测。", packet,
        )
        assert error is not None

    def test_n02_collection_plan_with_day30_publishes(self):
        packet = _retention_packet()
        assert validate_final_narrative(
            "D7 留存为 10%。建议继续收集至第30天再验证。", packet,
        ) is None

    def test_n02_adjacent_dates_cannot_be_labeled_yoy(self):
        error = validate_final_narrative(
            "2026-09-01 与 2026-09-02 的金额均同比增长 10%。",
        )
        assert error is not None
        assert "同比" in error

    def test_n02_same_proportional_growth_is_not_a_yoy_label(self):
        assert validate_final_narrative(
            "2026-09-01 至 2026-09-02，各来源均同比例上升 10%。",
        ) is None

    def test_n02_same_calendar_day_across_years_may_be_labeled_yoy(self):
        assert validate_final_narrative(
            "2025-09-01 与 2026-09-01 相比，金额同比增长 10%。",
        ) is None

    def test_n03_unsupported_d30_prediction_rejected(self):
        packet = _retention_packet()
        error = validate_final_narrative("D30 留存预计为 5%。", packet)
        assert error is not None
        assert "外推" in error

    def test_n03_missing_observation_does_not_qualify_positive_directional_prediction(self):
        packet = _retention_packet()
        error = validate_final_narrative("没有 D8–D30 观测，预测 D30 会继续下降。", packet)
        assert error is not None

    def test_n04_negation_does_not_cover_assertion_in_same_sentence(self):
        packet = _retention_packet()
        error = validate_final_narrative("不能预测 D30，但 D30 大约是 5%。", packet)
        assert error is not None

    def test_n05_conditional_action_publishes(self):
        packet = _retention_packet()
        assert validate_final_narrative(
            "如果 D30 达到预先阈值，则继续试点。", packet,
        ) is None

    def test_n06_other_source_with_valid_d30_not_blocked(self):
        packet = _retention_packet(extra_receipts=[
            _receipt_with_args(
                "curve_fitting", "tr_wide", _retention_curve_data(max_day=30),
                args={"name": "渠道 B"},
            ),
        ])
        assert validate_final_narrative("渠道 B 的 D30 留存为 8%。", packet) is None

    def test_n06_a_extrapolation_still_blocked_when_b_present(self):
        packet = _retention_packet(extra_receipts=[
            _receipt_with_args(
                "curve_fitting", "tr_wide", _retention_curve_data(max_day=30),
                args={"name": "渠道 B"},
            ),
        ])
        # B 的观测不能授权 A 的外推（P7-F01 反例）
        error = validate_final_narrative("渠道 A 的 D30 留存预计为 5%。", packet)
        assert error is not None

    def test_n06_a_scope_still_blocks_when_b_absent(self):
        packet = _retention_packet()
        error = validate_final_narrative("渠道 B 的 D30 留存为 8%。", packet)
        assert error is not None

    def test_n07_significance_claim_without_any_test_rejected(self):
        packet = _retention_packet()
        error = validate_final_narrative("两组转化率差异不显著。", packet)
        assert error is not None
        assert "检验" in error

    def test_n08_unrelated_significance_claim_not_backed_globally(self):
        packet = _retention_packet(extra_receipts=[
            _receipt_with_args(
                "ab_test", "tr_ab", _ab_test_data(),
                args={"metric": "revenue", "group_a": "control", "group_b": "treatment"},
            ),
        ])
        # 检验只做在 revenue 上；“新用户留存差异不显著”不得搭全局便车
        error = validate_final_narrative("新用户的留存差异不显著。", packet)
        assert error is not None
        assert "关联" in error or "绑定" in error

    def test_n08_bound_significance_claim_publishes(self):
        packet = _retention_packet(extra_receipts=[
            _receipt_with_args(
                "ab_test", "tr_ab", _ab_test_data(),
                args={"metric": "revenue", "group_a": "control", "group_b": "treatment"},
            ),
        ])
        assert validate_final_narrative("treatment 组的 revenue 差异不显著时不应加价。", packet) is None

    def test_n09_causal_tool_metadata_counts_as_executed_inference(self):
        packet = _retention_packet(extra_receipts=[
            _receipt_with_args(
                "causal_analysis", "tr_causal", _causal_data(),
                args={"treatment_col": "campaign", "outcome_col": "revenue"},
            ),
        ])
        assert validate_final_narrative("campaign 对 revenue 的差异不显著。", packet) is None

    def test_n11_issues_carry_position_and_stable_code(self):
        from data_agent.agent.publication_synthesis import validate_final_narrative_issues

        packet = _retention_packet()
        text = "D7 为 10%。D30 大约是 5%。"
        issues = validate_final_narrative_issues(text, packet)

        assert issues
        assert issues[0]["code"]
        assert issues[0]["span"]
        assert "5%" in issues[0]["span"]
        error = validate_final_narrative(text, packet)
        assert error is not None
        assert issues[0]["span"][:6] in error


def test_unconfirmed_amount_unit_rejects_currency_rewrite_but_allows_explicit_unknown():
    packet = {"publication_scope": [{"unit_status": "not_confirmed"}], "requirements": []}

    error = validate_final_narrative("每单都是10块钱，12单合计120块。", packet)

    assert error is not None
    assert "unconfirmed_currency_unit" in error
    assert validate_final_narrative("amount 合计为120，金额单位未知，不能写成120元。", packet) is None
    assert validate_final_narrative("金额单位未知，但每单10元。", packet) is not None
    assert validate_final_narrative("合计120元（金额单位未知）。", packet) is not None


def test_mixed_observed_future_window_cannot_be_labeled_wholly_future():
    today = date.today()
    packet = {
        "publication_scope": [{
            "unit_status": "not_confirmed",
            "observation_window": {
                "columns": {
                    "date": {
                        "min": (today - timedelta(days=2)).isoformat(),
                        "max": (today + timedelta(days=2)).isoformat(),
                    }
                }
            },
        }],
        "requirements": [],
    }

    error = validate_final_narrative("观测窗口属于未来日期，数据时效未验证。", packet)

    assert error is not None
    assert "incorrect_future_window_label" in error
    assert validate_final_narrative("观测窗口包含部分未来日期，采集截止未知。", packet) is None


def test_presentation_followup_reuses_only_current_bound_publication_snapshot():
    import pandas as pd
    from data_agent.agent.publication_synthesis import publication_contract

    loop = AgentLoop(client=None, session_id="presentation_snapshot")
    loop.context.workspace.add("orders", pd.DataFrame({"amount": [10, 10]}))
    identity = loop.context.workspace.get_data_identity("orders")
    receipt = _receipt("describe_dataset", "tr_profile", {
        "shape": {"rows": 2, "columns": 1},
        "observation_window": {},
    })
    receipt["data_identities"] = {"orders": identity}
    receipt["publication_contract"] = publication_contract(
        "describe_dataset", {"observation_window": {}}, args={"name": "orders"},
    )
    loop.context.analysis_state.add_tool_receipt(receipt)
    loop.context.turn_receipt_ids = ["tr_profile"]
    loop._turn_successful_publication_tools = {"describe_dataset"}
    packet = loop._prepare_publication_packet("给出事实摘要", persist=False)
    packet["answer_sha256"] = "sha256:accepted"
    loop.context.analysis_state.add_publication_packet(packet)

    reused = loop._latest_publication_packet_for_presentation("请用大白话重述，但不要改变事实")

    assert packet["status"] == "ready"
    assert reused is not None
    assert reused["snapshot_digest"] == packet["snapshot_digest"]
    assert loop._latest_publication_packet_for_presentation("请分析另一个业务问题") is None

    loop._turn_publication_packet = None
    published, error = loop._render_terminal_publication(
        "请用大白话重述，但不要改变事实", "每单都是10块钱。", persist=False,
    )
    assert published is None
    assert error is not None and "unconfirmed_currency_unit" in error

    loop.context.workspace.add("orders", pd.DataFrame({"amount": [20, 20]}))
    assert loop._latest_publication_packet_for_presentation("请用大白话重述") is None


# ── P4 (D03): evidence coverage and recoverable packet selection (E01–E05, E09–E10) ──


def _six_question_receipts() -> list[dict]:
    topics = [
        ("tr_q1", "A渠道趋势上升", {"trend": "rising", "metric": "revenue_a"}),
        ("tr_q2", "B渠道对比完成", {"compare": "a_vs_b", "delta": 12}),
        ("tr_q3", "用户分布偏态", {"distribution": "long_tail", "bins": 9}),
        ("tr_q4", "漏斗步骤流失", {"funnel": "checkout", "drop_off": 0.4}),
        ("tr_q5", "留存曲线拟合", {"retention": "power", "d7": 0.1}),
        ("tr_q6", "相关性矩阵计算", {"correlation": "weak", "pairs": 3}),
    ]
    receipts = []
    for receipt_id, preview, data in topics:
        receipts.append({
            "id": receipt_id,
            "tool_name": "run_python",
            "result_sha256": f"sha256:{receipt_id}",
            "result_preview": preview,
            "publication_facts": extract_publication_facts(data),
        })
    return receipts


def _packet_state(receipts, evidence=None):
    state = AnalysisSessionState(session_id="e_series_packet")
    for receipt in receipts:
        state.add_tool_receipt(receipt)
    for record in evidence or []:
        state.add_evidence_record(record)
    return state


class TestESeriesPacket:

    def test_b03_explicit_all_sources_request_retains_every_source_with_facts(self):
        receipts = _six_question_receipts()
        packet = build_publication_packet(
            _packet_state(receipts),
            user_input="汇总六个来源的金额变化，并保留全部来源",
            substantive_tools={"run_python"},
        )

        assert {source["receipt_id"] for source in packet["sources"]} == {
            f"tr_q{i}" for i in range(1, 7)
        }
        assert not packet["omitted_refs"]
        assert all(source["facts"] for source in packet["sources"])
        rendered = render_publication_receipt_markdown(packet)
        for source in packet["sources"]:
            for fact in source["facts"]:
                assert f"`{fact['path']}`: {fact['value']}" in rendered

    def test_e01_all_primary_subquestion_sources_kept(self):
        receipts = _six_question_receipts()
        question = (
            "分析A渠道趋势、B渠道对比、用户分布、漏斗、留存曲线、相关性"
        )
        packet = build_publication_packet(
            _packet_state(receipts),
            user_input=question,
            substantive_tools={"run_python"},
        )

        source_ids = {source["receipt_id"] for source in packet["sources"]}
        # 六个主问题来源不得因“最近四条”静默丢失：要么入选，要么有显式缺口记录
        tracked = source_ids | {
            item.get("receipt_id") for item in packet.get("omitted_refs", [])
        }
        assert {f"tr_q{i}" for i in range(1, 7)} <= tracked
        # 问题全部覆盖时不应产生缺口——六个来源全部入选且各带事实
        assert source_ids == {f"tr_q{i}" for i in range(1, 7)}
        assert all(source["facts"] for source in packet["sources"])

    def test_e02_current_evidence_not_sliced_before_filter(self):
        receipts = _six_question_receipts()
        evidence = [
            {"id": "ev_current", "claim": "A 渠道趋势上升", "tool_receipt_ids": ["tr_q1"], "limitations": []},
            {"id": "ev_other_1", "claim": "B 渠道对比完成", "tool_receipt_ids": ["tr_q9"], "limitations": []},
            {"id": "ev_other_2", "claim": "分布偏态", "tool_receipt_ids": ["tr_q10"], "limitations": []},
            {"id": "ev_other_3", "claim": "漏斗流失", "tool_receipt_ids": ["tr_q11"], "limitations": []},
            {"id": "ev_other_4", "claim": "留存拟合", "tool_receipt_ids": ["tr_q12"], "limitations": []},
        ]
        packet = build_publication_packet(
            _packet_state(receipts[:1], evidence),
            user_input="分析A渠道趋势",
            substantive_tools={"run_python"},
            receipt_ids={"tr_q1"},
        )

        evidence_ids = [item["evidence_id"] for item in packet["evidence"]]
        assert "ev_current" in evidence_ids

    def test_e03_fourth_group_value_enters_facts_with_its_name(self):
        data = {
            "metric": "amount",
            "groups": [
                {"channel": "A", "amount": 1},
                {"channel": "B", "amount": 2},
                {"channel": "C", "amount": 3},
                {"channel": "D", "amount": 999},
            ],
        }
        packet = build_publication_packet(
            _packet_state([{
                "id": "tr_groups",
                "tool_name": "run_python",
                "result_sha256": "sha256:g",
                "result_preview": "channel group amounts",
                "publication_facts": extract_publication_facts(data),
            }]),
            user_input="各渠道金额最高的是谁",
            substantive_tools={"run_python"},
        )

        facts = packet["sources"][0]["facts"]
        values = {fact["value"] for fact in facts}
        paths = {fact["path"] for fact in facts}
        assert "999" in values, "第四组数值必须进入候选事实"
        assert "D" in values
        assert any("groups[3]" in path for path in paths), "组名与数值必须成对保留"

    def test_e04_comparison_fields_kept_as_a_group(self):
        data = {
            "metric": "revenue",
            "period_a": {"value": 1818, "day_count": 15},
            "period_b": {"value": 684, "day_count": 15},
        }
        facts = extract_publication_facts(data, max_facts=3)

        paths = {fact["path"] for fact in facts}
        # 比较所需的字段组合成组保留：一个期间若保留数值则必须同时保留分母天数，
        # 不允许预算压力把组拆成互不关联的数字。
        for period in ("period_a", "period_b"):
            value_in = f"{period}.value" in paths
            days_in = f"{period}.day_count" in paths
            assert value_in == days_in, f"{period} 的字段组被拆散: {sorted(paths)}"
        assert len(paths) <= 3

    def test_e05_budget_omissions_are_recorded_with_references(self):
        receipts = _six_question_receipts() + [
            {
                "id": f"tr_extra_{i}",
                "tool_name": "run_python",
                "result_sha256": f"sha256:x{i}",
                "result_preview": f"background calc {i}",
                "publication_facts": extract_publication_facts({"value": i}),
            }
            for i in range(10)
        ]
        packet = build_publication_packet(
            _packet_state(receipts),
            user_input="分析A渠道趋势",
            substantive_tools={"run_python"},
        )

        omitted = packet.get("omitted_refs", [])
        assert omitted, "超出预算的来源必须有省略记录"
        assert all(item.get("receipt_id") and item.get("reason") for item in omitted)
        total_facts = sum(len(source["facts"]) for source in packet["sources"])
        assert total_facts <= 8 * 10

    def test_e09_packet_identity_changes_when_evidence_content_changes(self):
        receipts = _six_question_receipts()[:2]
        evidence = [
            {"id": "ev_1", "claim": "A 渠道趋势上升 12%", "tool_receipt_ids": ["tr_q1"], "limitations": []},
        ]
        state = _packet_state(receipts, evidence)
        packet_a = build_publication_packet(
            state, user_input="分析A渠道趋势", substantive_tools={"run_python"},
        )

        state.evidence_records[0]["claim"] = "A 渠道趋势上升 15%"
        packet_b = build_publication_packet(
            state, user_input="分析A渠道趋势", substantive_tools={"run_python"},
        )

        assert packet_a["id"] != packet_b["id"], "相同 id 不同内容的证据不得复用旧发布包"
        assert any("15%" in item["claim"] for item in packet_b["evidence"])

    def test_e10_uncovered_question_terms_become_explicit_gaps(self):
        receipts = _six_question_receipts()[:1]
        packet = build_publication_packet(
            _packet_state(receipts),
            user_input="分析A渠道趋势、漏斗、留存曲线",
            substantive_tools={"run_python"},
        )

        coverage = packet.get("coverage", [])
        covered_terms = {item.get("term") for item in coverage if item.get("status") == "covered"}
        gap_terms = {item.get("term") for item in coverage if item.get("status") == "missing"}
        assert gap_terms, "无来源覆盖的子问题必须成为显式缺口而不是静默缺失"
        assert covered_terms & {"趋势"} or any("趋势" in str(t) for t in covered_terms)


# ── P7-L3/B03: publication receipt renderer (sources/omissions/pending) ──


def test_b03_render_publication_receipt_markdown_covers_sources_omissions_pending():
    from data_agent.agent.publication_synthesis import render_publication_receipt_markdown

    state = _packet_state(
        _six_question_receipts(),
        evidence=[{
            "id": "ev_b03", "claim": "A 渠道趋势上升",
            "tool_receipt_ids": ["tr_q1"], "limitations": [],
        }],
    )
    packet = build_publication_packet(
        state, user_input="分析A渠道趋势", substantive_tools={"run_python"},
    )
    pending = [{
        "id": "hyps_orders_trend_h2",
        "claim": "收入变化由订单量驱动",
        "status": "inconclusive",
        "status_label": "未决（证据不足或不可判定）",
        "basis": "ev_b03",
        "gap": "orders",
        "next_step": "补齐区分性证据：orders",
    }]

    rendered = render_publication_receipt_markdown(packet, pending_findings=pending, verified_total=3)

    assert "计算来源与省略说明" in rendered
    assert "tr_q1" in rendered  # 收据引用
    assert "已验证结论：3 条" in rendered
    assert "待验证发现" in rendered
    assert "未决（证据不足或不可判定）" in rendered
    assert "补齐区分性证据：orders" in rendered
    # 不导出内部字段与 rejected 候选
    assert "artifact_path" not in rendered
    assert "publication_rejected" not in rendered
    assert "tool_receipt_ids" not in rendered


def test_b03_render_includes_omitted_refs_and_coverage_gaps():
    from data_agent.agent.publication_synthesis import render_publication_receipt_markdown

    receipts = _six_question_receipts() + [{
        "id": "tr_extra_99",
        "tool_name": "run_python",
        "result_sha256": "sha256:x99",
        "result_preview": "background calc 99",
        "publication_facts": extract_publication_facts({"value": 99}),
    }]
    packet = build_publication_packet(
        _packet_state(receipts),
        user_input="分析A渠道趋势、漏斗、留存曲线、相关性、异常检测",
        substantive_tools={"run_python"},
    )

    rendered = render_publication_receipt_markdown(packet)

    assert "tr_extra_99" in rendered
    assert any("省略" in line for line in rendered.splitlines())
    # “异常检测”没有任何来源覆盖，必须成为显式缺口行
    assert any("未覆盖子问题" in line and "异常" in line for line in rendered.splitlines())


def test_b03_publication_packet_registers_receipt_artifact(tmp_path):
    from data_agent.config import get_config
    from data_agent.session.history import list_artifacts

    cfg = get_config()
    old_sessions = cfg.sessions_dir
    cfg.sessions_dir = tmp_path / "sessions"
    try:
        loop = AgentLoop(client=None, session_id="b03_artifact")
        loop._reset_turn_tracking()
        loop._record_turn_tool_result(
            "run_python",
            '{"value": 120}',
            structured_data={"amount_sum": 120, "amount_count": 12},
        )

        packet = loop._prepare_publication_packet("分析订单合计")

        assert packet and packet["status"] == "ready"
        artifacts = list_artifacts("b03_artifact")
        receipts = [a for a in artifacts if a.get("type") == "publication_receipt"]
        assert receipts, "发布包 ready 时必须注册可打开的产出物收据"
        content = (cfg.sessions_dir / "b03_artifact" / receipts[0]["path"].split("sessions/b03_artifact/")[-1]).read_text(encoding="utf-8")
        assert "计算来源与省略说明" in content
        # 同一 packet 重复准备不重复注册
        loop._prepare_publication_packet("分析订单合计")
        assert len([a for a in list_artifacts("b03_artifact") if a.get("type") == "publication_receipt"]) == 1
    finally:
        cfg.sessions_dir = old_sessions
