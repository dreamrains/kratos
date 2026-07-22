import json

from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.intent import TurnIntent
from data_agent.agent.multi_file_scope import (
    build_analysis_scope_plan,
    build_material_ambiguity_groups,
)
from data_agent.agent.question_need_detector import detect_question_need
import pytest


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
    state = AnalysisSessionState(session_id="question_need", data_state="data_loaded")
    state.active_scope["active_dataset"] = "orders"
    state.active_scope["active_mode"] = "data_loaded"
    state.dataset_contracts = [{
        "dataset": "orders",
        "quality": {"status": "ready"},
        "field_roles": {
            "date": ["order_date"],
            "metrics": ["revenue", "orders"],
            "rate_metrics": ["conversion_rate"],
            "dimensions": ["channel"],
        },
    }]
    state.route_proposals = [
        {
            "id": "route_trend",
            "dataset": "orders",
            "direction": "trend",
            "label": "Revenue trend",
            "evidence_requirements": ["order_date", "revenue"],
        },
        {
            "id": "route_compare",
            "dataset": "orders",
            "direction": "period_compare",
            "label": "Period comparison",
            "evidence_requirements": ["order_date", "revenue", "period coverage"],
        },
    ]
    return state


def _duplicate_file_state():
    state = AnalysisSessionState(session_id="duplicate_file_scope", data_state="data_loaded")
    state.data_pool = [
        {
            "file_id": "sales_a",
            "filename": "sales.csv",
            "dataset": "sales_a",
            "status": "loaded",
        },
        {
            "file_id": "sales_b",
            "filename": "sales.csv",
            "dataset": "sales_b",
            "status": "loaded",
        },
    ]
    state.dataset_contracts = [
        {"id": "duc_sales_a", "dataset": "sales_a", "quality_status": "ready"},
        {"id": "duc_sales_b", "dataset": "sales_b", "quality_status": "ready"},
    ]
    return state


def _multiple_duplicate_file_state():
    state = _duplicate_file_state()
    state.data_pool.extend([
        {
            "file_id": "cost_a",
            "filename": "cost.csv",
            "dataset": "cost_a",
            "status": "loaded",
        },
        {
            "file_id": "cost_b",
            "filename": "cost.csv",
            "dataset": "cost_b",
            "status": "loaded",
        },
    ])
    state.dataset_contracts.extend([
        {"id": "duc_cost_a", "dataset": "cost_a", "quality_status": "ready"},
        {"id": "duc_cost_b", "dataset": "cost_b", "quality_status": "ready"},
    ])
    return state


def _ordered_same_filename_state(count):
    state = AnalysisSessionState(session_id="ordered_scope_candidates", data_state="data_loaded")
    state.data_pool = [
        {
            "file_id": f"sales_{index}",
            "filename": "sales.csv",
            "dataset": f"sales_{index}",
            "status": "loaded",
        }
        for index in range(1, count + 1)
    ]
    state.dataset_contracts = [
        {"id": f"duc_sales_{index}", "dataset": f"sales_{index}", "quality_status": "ready"}
        for index in range(1, count + 1)
    ]
    return state


def _positioned_sales_state(total_count, sales_positions):
    state = AnalysisSessionState(session_id="positioned_scope_candidates", data_state="data_loaded")
    state.data_pool = []
    state.dataset_contracts = []
    for position in range(1, total_count + 1):
        is_sales = position in sales_positions
        file_id = f"sales_{position}" if is_sales else f"other_{position}"
        dataset = file_id
        state.data_pool.append({
            "file_id": file_id,
            "filename": "sales.csv" if is_sales else f"other_{position}.csv",
            "dataset": dataset,
            "status": "loaded",
        })
        state.dataset_contracts.append({
            "id": f"duc_{dataset}",
            "dataset": dataset,
            "quality_status": "ready",
        })
    return state


def test_vague_goal_with_multiple_routes_requires_route_question():
    gate = detect_question_need(
        "please analyze this dataset",
        _intent("intent_negotiation", clarity="vague", analysis_stage="discover", recommended_action="guide_analysis"),
        _state(),
    )

    assert gate["status"] == "hard_question"
    assert gate["question_type"] == "route_selection"
    assert gate["blocking_surfaces"] == ["direct_recommendation", "analysis_execution", "report_generation"]
    assert [option["value"] for option in gate["options"]] == ["trend", "period_compare"]


def test_materially_ambiguous_period_estimand_requires_user_definition():
    state = _state()
    route = next(item for item in state.route_proposals if item["direction"] == "period_compare")
    route.update({
        "estimand_requires_confirmation": True,
        "estimand_options": [
            {"label": "总额差异", "value": "sum", "description": "compare totals"},
            {"label": "平均值差异", "value": "mean", "description": "compare means"},
        ],
    })

    ambiguous = detect_question_need(
        "revenue 最近 7 天对比前 7 天",
        _intent(),
        state,
    )
    explicit = detect_question_need(
        "revenue 最近 7 天对比前 7 天总额",
        _intent(),
        state,
    )

    assert ambiguous["question_type"] == "estimand_definition"
    assert [item["value"] for item in ambiguous["options"]] == ["sum", "mean"]
    assert explicit["status"] == "clear"


def test_duplicate_material_file_reference_requires_scope_selection_first():
    gate = detect_question_need("analyze sales.csv", _intent(), _duplicate_file_state())

    assert gate["status"] == "hard_question"
    assert gate["question_type"] == "file_scope_selection"
    assert "multiple" in gate["reason"].lower()
    assert "file" in gate["question"].lower()
    assert gate["blocking_surfaces"] == [
        "direct_recommendation",
        "analysis_execution",
        "report_generation",
    ]
    assert [option["value"] for option in gate["options"]] == ["sales_a", "sales_b"]
    assert [option["label"] for option in gate["options"]] == [
        "sales.csv [sales_a]",
        "sales.csv [sales_b]",
    ]
    assert all(option["description"] for option in gate["options"])
    assert gate["state_updates"] == {"stage": "scope"}
    assert gate["metadata"] == {"file_ids": ["sales_a", "sales_b"]}


def test_explicit_unique_file_id_skips_scope_gate_and_continues_detection():
    state = _duplicate_file_state()
    state.route_proposals = [
        {
            "id": "route_trend",
            "dataset": "sales_b",
            "direction": "trend",
            "label": "Sales trend",
        }
    ]
    state.active_scope["active_dataset"] = "sales_b"
    state.dataset_contracts[1]["field_roles"] = {
        "date": ["sale_date"],
        "metrics": ["revenue", "orders"],
    }

    gate = detect_question_need(
        "analyze sales.csv using sales_b trend",
        _intent(),
        state,
    )

    assert gate["question_type"] == "metric_scope"
    assert gate["question_type"] != "file_scope_selection"


def test_multiple_ambiguous_alias_groups_are_confirmed_one_at_a_time():
    state = _multiple_duplicate_file_state()

    first = detect_question_need(
        "compare sales.csv with cost.csv",
        _intent(),
        state,
    )
    second = detect_question_need(
        "compare sales.csv using sales_b with cost.csv",
        _intent(),
        state,
    )

    assert first["question_type"] == "file_scope_selection"
    assert [option["value"] for option in first["options"]] == ["sales_a", "sales_b"]
    assert first["metadata"] == {"file_ids": ["sales_a", "sales_b"]}
    assert "sales.csv" in first["question"]
    assert second["question_type"] == "file_scope_selection"
    assert [option["value"] for option in second["options"]] == ["cost_a", "cost_b"]
    assert second["metadata"] == {"file_ids": ["cost_a", "cost_b"]}
    assert "cost.csv" in second["question"]


def test_scope_group_deduplicates_aliases_from_the_same_file():
    state = AnalysisSessionState(session_id="normalized_alias_group", data_state="data_loaded")
    state.data_pool = [
        {
            "file_id": "sales_a",
            "filename": "sales.csv",
            "dataset": "Sales",
            "status": "loaded",
        },
        {
            "file_id": "sales_b",
            "filename": "cost.csv",
            "dataset": "Sales",
            "status": "loaded",
        },
    ]
    state.dataset_contracts = [
        {"id": "duc_sales", "dataset": "Sales", "quality_status": "ready"},
    ]

    gate = detect_question_need("analyze sales", _intent(), state)

    assert [option["value"] for option in gate["options"]] == ["sales_a", "sales_b"]
    assert gate["metadata"] == {"file_ids": ["sales_a", "sales_b"]}


def test_scope_group_falls_back_to_shared_dataset_when_filenames_are_empty():
    state = AnalysisSessionState(session_id="dataset_alias_group", data_state="data_loaded")
    state.data_pool = [
        {
            "file_id": "shared_a",
            "filename": "",
            "dataset": "shared",
            "status": "loaded",
        },
        {
            "file_id": "shared_b",
            "filename": "",
            "dataset": "shared",
            "status": "loaded",
        },
    ]
    state.dataset_contracts = [
        {"id": "duc_shared", "dataset": "shared", "quality_status": "ready"},
    ]

    gate = detect_question_need("analyze shared", _intent(), state)

    assert [option["value"] for option in gate["options"]] == ["shared_a", "shared_b"]
    assert [option["label"] for option in gate["options"]] == [
        "shared [shared_a]",
        "shared [shared_b]",
    ]
    assert "shared" in gate["question"]


def test_chinese_dataset_substring_does_not_create_scope_gate():
    state = AnalysisSessionState(session_id="chinese_detector_boundary", data_state="data_loaded")
    state.data_pool = [
        {"file_id": "sales_a", "filename": "a.csv", "dataset": "销售", "status": "loaded"},
        {"file_id": "sales_b", "filename": "b.csv", "dataset": "销售", "status": "loaded"},
    ]
    state.dataset_contracts = [
        {"id": "duc_sales", "dataset": "销售", "quality_status": "ready"},
    ]

    false_match = detect_question_need("分析销售额趋势", _intent(), state)
    quoted_match = detect_question_need("分析“销售”趋势", _intent(), state)

    assert false_match["status"] == "clear"
    assert quoted_match["question_type"] == "file_scope_selection"


def test_six_material_candidates_are_all_present_in_scope_question():
    state = AnalysisSessionState(session_id="six_scope_candidates", data_state="data_loaded")
    state.data_pool = [
        {
            "file_id": f"sales_{index}",
            "filename": "sales.csv",
            "dataset": f"sales_{index}",
            "status": "loaded",
        }
        for index in range(6)
    ]
    state.dataset_contracts = [
        {"id": f"duc_sales_{index}", "dataset": f"sales_{index}", "quality_status": "ready"}
        for index in range(6)
    ]

    gate = detect_question_need("analyze sales.csv", _intent(), state)

    assert [option["value"] for option in gate["options"]] == [
        f"sales_{index}" for index in range(6)
    ]


def test_excessive_material_candidates_use_bounded_free_text_question():
    state = AnalysisSessionState(session_id="many_scope_candidates", data_state="data_loaded")
    state.data_pool = [
        {
            "file_id": f"sales_{index}",
            "filename": "sales.csv",
            "dataset": f"sales_{index}",
            "status": "loaded",
        }
        for index in range(21)
    ]
    state.dataset_contracts = [
        {"id": f"duc_sales_{index}", "dataset": f"sales_{index}", "quality_status": "ready"}
        for index in range(21)
    ]

    gate = detect_question_need("analyze sales.csv", _intent(), state)

    assert gate["question_type"] == "file_scope_selection"
    assert gate["options"] == []
    assert "21" in gate["question"]
    assert "第 N 个文件" in gate["question"]
    assert gate["metadata"]["candidate_count"] == 21
    assert len(gate["metadata"]["candidate_sample"]) == 5
    assert "file_ids" not in gate["metadata"]


def test_large_scope_question_uses_global_upload_ordinals_not_group_positions():
    state = _positioned_sales_state(22, set(range(2, 23)))

    gate = detect_question_need("analyze sales.csv", _intent(), state)
    resolved = detect_question_need(
        "analyze sales.csv using 第 22 个文件",
        _intent(),
        state,
    )

    assert "全局上传顺序" in gate["question"]
    assert "2-22" in gate["question"]
    assert "1-21" not in gate["question"]
    assert gate["metadata"]["sample_ordinals"] == [2, 3, 4, 5, 6]
    assert resolved["status"] == "clear"


def test_large_scope_question_compresses_non_contiguous_global_ordinals():
    sales_positions = set(range(1, 26)) - {1, 3, 9}
    state = _positioned_sales_state(25, sales_positions)

    gate = detect_question_need("analyze sales.csv", _intent(), state)
    selected = detect_question_need(
        "analyze sales.csv using 第 25 个文件",
        _intent(),
        state,
    )
    unrelated = detect_question_need(
        "analyze sales.csv using 第 3 个文件",
        _intent(),
        state,
    )
    out_of_range = detect_question_need(
        "analyze sales.csv using 第 26 个文件",
        _intent(),
        state,
    )

    assert "2、4-8、10-25" in gate["question"]
    assert selected["status"] == "clear"
    assert unrelated["question_type"] == "file_scope_selection"
    assert out_of_range["question_type"] == "file_scope_selection"


def test_sparse_global_ordinals_use_honest_bounded_fallback_text():
    sales_positions = set(range(2, 101, 2))
    state = _positioned_sales_state(100, sales_positions)

    gate = detect_question_need("analyze sales.csv", _intent(), state)

    assert "2-100" in gate["question"]
    assert "并非区间内每个序号都属于本组" in gate["question"]
    assert "2、4、6、8、10" in gate["question"]
    assert len(gate["question"]) < 300


@pytest.mark.parametrize("reference", ["第 1 个文件", "第21个文件", "file 21"])
def test_upload_order_reference_resolves_large_ambiguity_group(reference):
    state = _ordered_same_filename_state(21)
    goal = f"analyze sales.csv using {reference}"

    gate = detect_question_need(goal, _intent(), state)

    assert gate["status"] == "clear"
    plan = build_analysis_scope_plan(state, goal)
    assert plan["decision_files"] == []
    assert build_material_ambiguity_groups(state, goal) == []


@pytest.mark.parametrize("reference", ["第 22 个文件", "21", "第1个文件和第2个文件"])
def test_invalid_or_ambiguous_upload_order_reference_does_not_resolve_group(reference):
    state = _ordered_same_filename_state(21)

    gate = detect_question_need(
        f"analyze sales.csv using {reference}",
        _intent(),
        state,
    )

    assert gate["question_type"] == "file_scope_selection"
    assert gate["metadata"]["candidate_count"] == 21


def test_upload_order_reference_only_resolves_its_own_ambiguity_group():
    state = _ordered_same_filename_state(21)
    state.data_pool.extend([
        {"file_id": "cost_a", "filename": "cost.csv", "dataset": "cost_a", "status": "loaded"},
        {"file_id": "cost_b", "filename": "cost.csv", "dataset": "cost_b", "status": "loaded"},
    ])
    state.dataset_contracts.extend([
        {"id": "duc_cost_a", "dataset": "cost_a", "quality_status": "ready"},
        {"id": "duc_cost_b", "dataset": "cost_b", "quality_status": "ready"},
    ])

    gate = detect_question_need(
        "compare sales.csv using 第 21 个文件 with cost.csv",
        _intent(),
        state,
    )

    assert [option["value"] for option in gate["options"]] == ["cost_a", "cost_b"]


def test_conflicting_scope_options_include_stable_file_identity():
    state = AnalysisSessionState(session_id="scope_display_identity", data_state="data_loaded")
    state.data_pool = [
        {"file_id": "sales_a", "filename": "sales.csv", "dataset": "sales", "status": "loaded"},
        {"file_id": "sales_b", "filename": "sales.csv", "dataset": "sales", "status": "loaded"},
    ]
    state.dataset_contracts = [
        {"id": "duc_sales", "dataset": "sales", "quality_status": "ready"},
    ]

    gate = detect_question_need("analyze sales.csv", _intent(), state)

    assert [option["value"] for option in gate["options"]] == ["sales_a", "sales_b"]
    assert len({option["label"] for option in gate["options"]}) == 2
    assert len({option["description"] for option in gate["options"]}) == 2
    assert all(option["value"] in option["label"] for option in gate["options"])
    assert all(option["value"] in option["description"] for option in gate["options"])


def test_metric_ambiguity_requires_metric_scope_question():
    state = _state()

    gate = detect_question_need("analyze performance trend", _intent(), state)

    assert gate["status"] == "hard_question"
    assert gate["question_type"] == "metric_scope"
    assert [option["value"] for option in gate["options"]] == ["revenue", "orders", "conversion_rate"]


def test_period_comparison_requires_time_window_question_when_missing_window():
    state = _state()

    gate = detect_question_need("compare revenue", _intent(), state)

    assert gate["status"] == "hard_question"
    assert gate["question_type"] == "time_window"
    assert "period" in gate["reason"].lower()


def test_high_risk_predictive_analysis_requires_method_confirmation():
    gate = detect_question_need("predict next month revenue", _intent(), _state())

    assert gate["status"] == "hard_question"
    assert gate["question_type"] == "method_confirmation"
    assert gate["blocking_surfaces"] == ["analysis_execution", "report_generation"]


def test_confirmed_matching_high_risk_plan_skips_generic_gate_but_changed_request_does_not():
    state = _state()
    state.set_analysis_plan({
        "id": "spec_forecast_revenue",
        "goal": "predict next month revenue",
        "playbook_id": "forecast_decision_simulation",
        "confirmation_policy": {"requires_confirmation": True},
    })
    state.add_confirmation({
        "id": "method_forecast_revenue",
        "related_plan_id": "spec_forecast_revenue",
        "state_updates": json.dumps({
            "method_confirmation": {
                "playbook_id": "forecast_decision_simulation",
                "analysis_plan_id": "spec_forecast_revenue",
                "allowed_actions": ["confirm_method", "clarify_method_scope"],
            },
        }),
    })
    state.resolve_confirmation("method_forecast_revenue", "confirm_method")

    matching = detect_question_need("predict next month revenue", _intent(), state)
    changed = detect_question_need("predict next quarter profit", _intent(), state)

    assert matching["status"] == "clear"
    assert changed["status"] == "hard_question"
    assert changed["question_type"] == "method_confirmation"


def test_consulting_and_knowledge_questions_do_not_block():
    state = _state()

    gate = detect_question_need("what is cohort analysis", _intent("knowledge_qa", recommended_action="answer_directly"), state)

    assert gate["status"] == "clear"
    assert gate["blocking_surfaces"] == []


def test_clear_metric_and_route_do_not_ask_unnecessarily():
    gate = detect_question_need("show revenue trend by date", _intent(), _state())

    assert gate["status"] == "clear"
    assert gate["question_type"] == ""


def test_cleaning_risk_on_required_field_requires_data_quality_question():
    state = _state()
    state.cleaning_logs = [{
        "dataset": "orders",
        "decisions": [
            {"column": "order_date", "decision_type": "needs_confirmation"},
        ],
    }]

    gate = detect_question_need("show revenue trend", _intent(), state)

    assert gate["status"] == "hard_question"
    assert gate["question_type"] == "data_quality_confirmation"
    assert gate["risk_fields"] == ["order_date"]


@pytest.mark.parametrize("confirmation_type", [
    "file_relationship_confirmation",
    "file_exclusion_confirmation",
    "join_logic_confirmation",
])
def test_relationship_diagnostics_do_not_trigger_questions(confirmation_type):
    state = _state()
    state.file_relationships = [{
        "relationship_id": "rel_orders_history",
        "status": "possibly_linked",
        "requires_confirmation": True,
        "confirmation_type": confirmation_type,
        "new_files": ["orders_latest.csv"],
        "existing_files": ["orders_history.csv"],
        "uncertainties": ["Shared IDs exist but business theme evidence is unclear."],
    }]

    gate = detect_question_need("show revenue trend by date", _intent(), state)

    assert gate["status"] == "clear"
