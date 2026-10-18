from data_agent.agent.analysis_entry import decide_analysis_entry
from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.intent import TurnIntent


def _intent(intent_type="directed_analysis", **overrides):
    values = {
        "intent_type": intent_type,
        "clarity": "clear",
        "data_state": "data_loaded",
        "analysis_stage": "execute",
        "recommended_action": "run_analysis",
        "execution_readiness": "ready",
        "reason": "test",
        "ambiguities": [],
    }
    values.update(overrides)
    return TurnIntent(**values)


def _state():
    state = AnalysisSessionState(session_id="entry_tests", data_state="data_loaded")
    state.dataset_contracts = [{
        "id": "duc_sales",
        "dataset": "sales",
        "quality": {"status": "ready", "score": 96},
        "field_roles": {
            "date": ["date"],
            "metrics": ["revenue", "orders"],
            "dimensions": ["channel"],
            "ids": ["user_id"],
        },
        "supported_analyses": ["trend", "period_compare", "dimension_decomposition"],
        "unsupported_analyses": [],
    }]
    state.route_proposals = [
        {
            "id": "route_trend",
            "dataset": "sales",
            "direction": "trend",
            "limitations": ["Descriptive trend only"],
            "evidence_requirements": ["date", "metric"],
        },
        {
            "id": "route_compare",
            "dataset": "sales",
            "direction": "period_compare",
            "limitations": ["Requires comparable periods"],
            "evidence_requirements": ["date", "metric", "period coverage"],
        },
    ]
    return state


def test_supported_trend_request_returns_direct_analysis():
    decision = decide_analysis_entry("show revenue trend", _intent(), _state())

    assert decision["decision"] == "direct_analysis"
    assert decision["dataset"] == "sales"
    assert decision["route"] == "trend"
    assert decision["reason"] == "The request matches a supported data route."
    assert decision["confidence"] == "medium"
    assert decision["required_user_action"] == ""
    assert decision["limitations"] == ["Descriptive trend only"]
    assert decision["evidence_requirements"] == ["date", "metric"]


def test_vague_request_with_multiple_routes_returns_clarify_intent():
    vague = _intent(
        "intent_negotiation",
        clarity="vague",
        analysis_stage="discover",
        recommended_action="guide_analysis",
    )

    decision = decide_analysis_entry("help me analyze this data", vague, _state())

    assert decision["decision"] == "clarify_intent"
    assert decision["reason"] in {
        "Multiple data-supported analysis routes are available.",
        "Multiple data-supported analysis routes are available and the user goal is vague.",
    }
    assert decision["route"] == ""
    assert decision["required_user_action"] in {"choose_analysis_route", "ask_user_question"}
    assert decision["route_options"] or decision["confirmation_gate"]["confirmation_type"] == "route_selection"


def test_source_bound_delivery_keeps_internal_route_choice_internal():
    request = "请评估实验的净贡献及成本，并说明还缺什么证据。"
    vague = _intent(
        "intent_negotiation", clarity="vague", analysis_stage="discover",
        recommended_action="guide_analysis",
        requested_outputs=[{"exact_span": "评估实验的净贡献及成本", "kind": "result"}],
    )

    decision = decide_analysis_entry(request, vague, _state())

    assert decision["decision"] == "direct_analysis"
    assert decision["required_user_action"] == ""
    assert "source_bound_delivery" in decision["reason"]


def test_vague_multi_route_keeps_period_compare_with_conceptual_requirement():
    state = AnalysisSessionState(session_id="entry_period_compare", data_state="data_loaded")
    state.active_scope["active_dataset"] = "orders"
    state.active_scope["active_mode"] = "data_loaded"
    state.dataset_contracts = [{
        "dataset": "orders",
        "field_roles": {"date": ["order_date"], "metrics": ["revenue"]},
    }]
    state.route_proposals = [
        {
            "id": "route_trend",
            "dataset": "orders",
            "direction": "trend",
            "evidence_requirements": ["order_date", "revenue"],
        },
        {
            "id": "route_compare",
            "dataset": "orders",
            "direction": "period_compare",
            "evidence_requirements": ["order_date", "revenue", "period coverage"],
        },
    ]
    vague = _intent(
        "intent_negotiation",
        clarity="vague",
        analysis_stage="discover",
        recommended_action="guide_analysis",
    )

    decision = decide_analysis_entry("help me analyze this data", vague, state)

    assert decision["decision"] == "clarify_intent"
    assert decision["required_user_action"] == "choose_analysis_route"
    assert [option["direction"] for option in decision["route_options"]] == [
        "trend",
        "period_compare",
    ]


def test_metric_ambiguity_returns_ask_user_question_gate():
    state = _state()

    decision = decide_analysis_entry("analyze performance trend", _intent(), state)

    assert decision["decision"] == "clarify_intent"
    assert decision["required_user_action"] == "ask_user_question"
    assert decision["confirmation_gate"]["confirmation_type"] == "metric_scope"


def test_p08_predictive_request_not_gated_by_method_confirmation():
    """P08-01 契约更新：原断言预测请求返回 method_confirmation 门；
    新原则下不再出现方法类确认门（其余澄清类型不受影响）。"""
    decision = decide_analysis_entry("predict revenue next month", _intent(), _state())

    gate_type = (decision.get("confirmation_gate") or {}).get("confirmation_type", "")
    assert gate_type != "method_confirmation"
    assert decision["required_user_action"] != "ask_user_question" or gate_type != "method_confirmation"


def test_entry_decision_uses_active_dataset_for_vague_multi_dataset_routes():
    state = AnalysisSessionState(session_id="entry_tests", data_state="data_loaded")
    state.active_scope["active_dataset"] = "orders"
    state.active_scope["active_mode"] = "data_loaded"
    state.route_proposals = [
        {"id": "old", "dataset": "sales", "direction": "trend"},
        {"id": "new", "dataset": "orders", "direction": "cohort"},
    ]

    decision = decide_analysis_entry("please analyze this dataset", _intent("guide_analysis"), state)

    assert decision["decision"] == "direct_analysis"
    assert decision["dataset"] == "orders"
    assert decision["route"] == "cohort"


def test_retention_unsupported_uses_active_dataset_only():
    state = AnalysisSessionState(session_id="entry_tests", data_state="data_loaded")
    state.active_scope["active_dataset"] = "orders"
    state.active_scope["active_mode"] = "data_loaded"
    state.dataset_contracts = [
        {
            "dataset": "old_sales",
            "unsupported_analyses": [
                {"type": "user_level_retention", "reason": "old aggregate data"}
            ],
        },
        {
            "dataset": "orders",
            "supported_analyses": ["cohort"],
            "unsupported_analyses": [],
        },
    ]
    state.route_proposals = [
        {"id": "route_cohort", "dataset": "orders", "direction": "cohort"}
    ]

    decision = decide_analysis_entry("analyze cohort retention", _intent(), state)

    assert decision["decision"] == "direct_analysis"
    assert decision["dataset"] == "orders"
    assert decision["route"] == "cohort"


def test_decide_analysis_entry_does_not_execute_route_missing_required_data():
    state = AnalysisSessionState(session_id="entry_guard", data_state="data_loaded")
    state.active_scope["active_dataset"] = "orders"
    state.active_scope["active_mode"] = "data_loaded"
    state.dataset_contracts = [{
        "dataset": "orders",
        "field_roles": {"date": ["order_date"], "metrics": ["revenue"]},
    }]
    state.route_proposals = [{
        "id": "route_cohort",
        "dataset": "orders",
        "direction": "cohort",
        "label": "Retention",
        "evidence_requirements": ["user_id", "event_date"],
    }]

    decision = decide_analysis_entry("analyze retention", _intent("directed_analysis"), state)

    assert decision["decision"] == "request_data"
    assert decision["required_user_action"] == "provide_required_data"
    assert decision["limitations"] == ["user_id", "event_date"]


def test_decide_analysis_entry_enforces_missing_data_route_without_explicit_mode():
    state = AnalysisSessionState(session_id="entry_guard_inferred_mode", data_state="data_loaded")
    state.active_scope["active_dataset"] = "orders"
    state.active_scope["active_mode"] = ""
    state.dataset_contracts = [{
        "dataset": "orders",
        "field_roles": {"date": ["order_date"], "metrics": ["revenue"]},
    }]
    state.route_proposals = [{
        "id": "route_cohort",
        "dataset": "orders",
        "direction": "cohort",
        "label": "Retention",
        "evidence_requirements": ["user_id", "event_date"],
    }]

    decision = decide_analysis_entry("analyze retention", _intent("directed_analysis"), state)

    assert decision["decision"] == "request_data"
    assert decision["required_user_action"] == "provide_required_data"
    assert decision["limitations"] == ["user_id", "event_date"]


def test_decide_analysis_entry_does_not_fall_back_to_demoted_raw_route():
    state = AnalysisSessionState(session_id="entry_guard_no_raw_fallback", data_state="data_loaded")
    state.active_scope["active_dataset"] = "orders"
    state.active_scope["active_mode"] = ""
    state.dataset_contracts = [{
        "dataset": "orders",
        "field_roles": {"date": ["event_date"], "metrics": ["revenue"]},
    }]
    state.route_proposals = [{
        "id": "route_user_retention",
        "dataset": "orders",
        "direction": "user_level_retention",
        "evidence_requirements": ["user_id", "event_date"],
    }]

    decision = decide_analysis_entry("analyze retention", _intent("directed_analysis"), state)

    assert decision["decision"] == "request_data"
    assert decision["decision"] != "direct_analysis"
    assert decision["required_user_action"] == "provide_required_data"
    assert "user_id" in decision["limitations"]


def test_consulting_mode_does_not_fall_back_to_raw_routes():
    state = AnalysisSessionState(session_id="entry_tests", data_state="data_loaded")
    state.set_consulting_mode("discuss method")
    state.route_proposals = [
        {"id": "route_trend", "dataset": "sales", "direction": "trend"}
    ]

    decision = decide_analysis_entry("show revenue trend", _intent(), state)

    assert decision["decision"] == "clarify_intent"
    assert decision["route"] == ""
    assert decision["required_user_action"] == "clarify_analysis_goal"


def test_unsupported_retention_request_returns_request_data():
    state = _state()
    state.dataset_contracts[0]["unsupported_analyses"] = [
        {"type": "user_level_retention", "reason": "aggregate grain and missing user id"}
    ]

    decision = decide_analysis_entry("analyze cohort retention", _intent(), state)

    assert decision["decision"] == "request_data"
    assert decision["reason"] == "The loaded data cannot support user-level retention analysis."
    assert decision["route"] == ""
    assert decision["required_user_action"] == "provide_user_level_retention_data"
    assert decision["limitations"] == ["aggregate grain and missing user id"]


def test_cleaning_confirmation_on_required_field_returns_clarify_intent():
    state = _state()
    state.cleaning_logs = [{
        "dataset": "sales",
        "decisions": [{
            "column": "date",
            "decision_type": "needs_confirmation",
            "impact": "Date parsing changed the original column type",
        }],
    }]

    decision = decide_analysis_entry("show revenue trend", _intent(), state)

    assert decision["decision"] == "clarify_intent"
    assert "cleaning" in decision["reason"]
    assert decision["required_user_action"] in {"confirm_cleaning_decision", "ask_user_question"}
    assert decision["risk_fields"] == ["date"]
    assert decision["confirmation_gate"]["confirmation_type"] == "data_quality_confirmation"


def test_pending_confirmation_blocks_direct_analysis_entry():
    state = _state()
    state.pending_confirmations = [{
        "id": "scope_gate",
        "status": "pending",
        "confirmation_type": "scope_confirmation",
        "question": "请先确认分析目标",
        "blocking_reason": "目标会影响分析方向",
    }]

    decision = decide_analysis_entry("show revenue trend", _intent(), state)

    assert decision["decision"] == "clarify_intent"
    assert decision["required_user_action"] == "ask_user_question"
    assert decision["reason"] == "A pending confirmation must be resolved before analysis recommendations or execution."
    assert decision["confirmation_gate"]["question"] == "请先确认分析目标"


def test_file_relationship_diagnostic_does_not_block_analysis_entry():
    state = _state()
    state.file_relationships = [{
        "relationship_id": "rel_sales_history",
        "status": "possibly_linked",
        "requires_confirmation": True,
        "confirmation_type": "join_logic_confirmation",
        "uncertainties": ["Shared IDs exist but business theme evidence is unclear."],
    }]

    decision = decide_analysis_entry("show revenue trend by date", _intent(), state)

    assert decision["decision"] == "direct_analysis"
    assert decision["required_user_action"] == ""


def test_obsolete_pending_confirmation_does_not_hide_new_real_question():
    state = _state()
    state.pending_confirmations = [{
        "id": "legacy_join_gate",
        "status": "pending",
        "confirmation_type": "join_logic_confirmation",
        "question": "Legacy relationship question",
    }]

    decision = decide_analysis_entry("compare revenue", _intent(), state)

    assert decision["decision"] == "clarify_intent"
    assert decision["confirmation_gate"]["confirmation_type"] == "time_window"


def test_flow_controller_ignores_obsolete_pending_confirmation():
    from data_agent.agent.analysis_flow_controller import AnalysisFlowController

    state = _state()
    state.pending_confirmations = [{
        "status": "pending",
        "confirmation_type": "file_exclusion_confirmation",
    }]

    assert not AnalysisFlowController("analysis_entry").has_pending_confirmation(state)

    state.pending_confirmations.append({
        "status": "pending",
        "confirmation_type": "method_confirmation",
    })
    assert AnalysisFlowController("analysis_entry").has_pending_confirmation(state)


def test_blocked_quality_returns_blocked():
    state = _state()
    state.dataset_contracts[0]["quality"] = {
        "status": "blocked",
        "block_issues": ["date column has no usable values"],
    }

    decision = decide_analysis_entry("show revenue trend", _intent(), state)

    assert decision["decision"] == "blocked"
    assert decision["reason"] == "Data quality blocks formal analysis."
    assert decision["required_user_action"] == "resolve_data_quality"
    assert decision["limitations"] == ["date column has no usable values"]


# ── P2 (D06/I11): host scope is never widened by request text ──


def _multi_dataset_state():
    state = _state()
    state.dataset_contracts.append({
        "id": "duc_other",
        "dataset": "other",
        "quality": {"status": "ready"},
        "field_roles": {"date": ["date"], "metrics": ["spend"]},
        "supported_analyses": ["trend"],
        "unsupported_analyses": [],
    })
    state.route_proposals.append({
        "id": "route_other_trend",
        "dataset": "other",
        "direction": "trend",
        "limitations": [],
        "evidence_requirements": ["date", "metric"],
    })
    state.active_scope["active_dataset"] = "sales"
    state.active_scope["active_mode"] = "analysis"
    return state


def test_i11_mentioned_other_dataset_does_not_widen_active_scope():
    decision = decide_analysis_entry("分析 other 的 spend 趋势", _intent(), _multi_dataset_state())

    # The host scope stays on the active dataset: other's routes must not be
    # selected, and the out-of-scope metric wording resolves to a scoped
    # clarification instead of a cross-dataset execution.
    assert decision["dataset"] != "other"
    assert decision["decision"] in {"direct_analysis", "clarify_intent"}


def test_i11_scoped_request_still_runs_on_active_dataset():
    decision = decide_analysis_entry("分析 revenue 趋势", _intent(), _multi_dataset_state())

    assert decision["decision"] == "direct_analysis"
    assert decision["dataset"] == "sales"
    assert decision["route"] == "trend"
