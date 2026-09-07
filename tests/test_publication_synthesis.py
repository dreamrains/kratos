from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.loop import AgentLoop
from data_agent.agent.publication_synthesis import (
    build_publication_packet,
    extract_publication_facts,
    render_publication_receipt_markdown,
    render_verified_appendix,
    validate_final_narrative,
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


class TestNSeriesPublication:

    def test_n01_boundary_statement_with_d30_publishes(self):
        packet = _retention_packet()
        assert validate_final_narrative(
            "D7 留存为 10%。当前不能预测 D30，需补充数据。", packet,
        ) is None

    def test_n02_collection_plan_with_day30_publishes(self):
        packet = _retention_packet()
        assert validate_final_narrative(
            "D7 留存为 10%。建议继续收集至第30天再验证。", packet,
        ) is None

    def test_n03_unsupported_d30_prediction_rejected(self):
        packet = _retention_packet()
        error = validate_final_narrative("D30 留存预计为 5%。", packet)
        assert error is not None
        assert "外推" in error

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
