import json

import pytest

from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.multi_file_scope import (
    build_analysis_scope_plan,
    canonical_entity_fields,
    infer_file_grain,
)


def _profile(file_id, *, dataset=None, filename=None, status="loaded", **overrides):
    item = {
        "file_id": file_id,
        "filename": filename or f"{file_id}.csv",
        "dataset": dataset or file_id,
        "status": status,
    }
    item.update(overrides)
    return item


def _add_contract(state, dataset, *, status="ready"):
    state.dataset_contracts.append({
        "id": f"duc_{dataset}",
        "dataset": dataset,
        "quality_status": status,
    })


def _state(*profiles):
    state = AnalysisSessionState(session_id="scope_contract", data_state="data_loaded")
    state.data_pool = list(profiles)
    for profile in profiles:
        dataset = profile.get("dataset")
        if dataset and profile.get("status") != "failed":
            _add_contract(state, dataset)
    return state


def test_canonical_entity_fields_recognize_user_aliases():
    profile = {
        "file_id": "coupon",
        "filename": "代金券明细订单.xlsx",
        "columns": ["主用户ID", "产品用户ID", "优惠券ID", "核销时间"],
        "key_fields": [],
        "time_fields": ["核销时间"],
    }

    fields = canonical_entity_fields(profile)

    assert fields["user"] == ["主用户ID", "产品用户ID"]
    assert fields["coupon"] == ["优惠券ID"]
    assert fields["time"] == ["核销时间"]


def test_infer_file_grain_prefers_order_level_when_order_id_exists():
    profile = {
        "file_id": "orders",
        "columns": ["order_id", "user_id", "paid_at", "amount"],
        "key_fields": ["order_id", "user_id"],
        "time_fields": ["paid_at"],
    }

    assert infer_file_grain(profile)["grain"] == "order_level"


@pytest.mark.parametrize("alias", ["customer_id", "member_id", "account_id"])
def test_user_identifier_aliases_produce_user_grain(alias):
    profile = {
        "file_id": f"profile_{alias}",
        "filename": "customer_profile.xlsx",
        "columns": [alias, "segment"],
    }

    assert canonical_entity_fields(profile)["user"] == [alias]
    assert infer_file_grain(profile)["grain"] == "user_level"


def test_scope_without_current_task_keeps_eligible_files_available():
    state = _state(_profile("orders"), _profile("users"))

    plan = build_analysis_scope_plan(state, "analyze revenue")

    assert [item["file_id"] for item in plan["eligible_files"]] == ["orders", "users"]
    assert plan["used_files"] == []
    assert [item["reason_code"] for item in plan["available_files"]] == [
        "eligible_not_yet_assigned",
        "eligible_not_yet_assigned",
    ]


def test_scope_keeps_explicit_files_available_until_plan_has_bindings():
    state = _state(_profile("orders"), _profile("users"))
    state.analysis_plan = {"method_plan": [{"step": "legacy step without dataset bindings"}]}

    plan = build_analysis_scope_plan(state, "analyze orders.csv and users.csv")

    assert plan["used_files"] == []
    assert [item["reason_code"] for item in plan["available_files"]] == [
        "explicit_in_scope_pending_plan",
        "explicit_in_scope_pending_plan",
    ]


def test_scope_separates_eligibility_from_plan_assignment():
    state = _state(
        _profile("orders"),
        _profile("users"),
        _profile("campaigns"),
    )
    state.analysis_plan = {
        "method_plan": [
            {"step_id": "task_orders", "dataset_inputs": ["orders"]},
            {"step_id": "task_users", "dataset_inputs": ["users"]},
        ]
    }

    plan = build_analysis_scope_plan(state, "analyze orders, users, and campaigns")

    assert [item["file_id"] for item in plan["eligible_files"]] == [
        "orders",
        "users",
        "campaigns",
    ]
    assert [item["file_id"] for item in plan["used_files"]] == ["orders", "users"]
    assert [item["file_id"] for item in plan["not_needed_files"]] == ["campaigns"]
    assert plan["used_files"][0]["reason_code"] == "plan_task_binding"
    assert plan["not_needed_files"][0]["reason_code"] == "no_current_task"
    assert plan["file_decisions"][0]["task_refs"] == ["task_orders"]
    assert plan["file_decisions"][0]["dataset_contract_id"] == "duc_orders"
    assert set(plan["file_decisions"][0]) == {
        "file_id",
        "filename",
        "dataset",
        "dataset_contract_id",
        "grain",
        "canonical_fields",
        "eligibility",
        "assignment",
        "reason_code",
        "reason",
        "confidence",
        "task_refs",
    }
    assert set(plan["used_files"][0]) == {
        "file_id",
        "filename",
        "dataset",
        "reason_code",
    }
    assert set(plan) == {
        "scope_status",
        "goal",
        "file_decisions",
        "eligible_files",
        "used_files",
        "available_files",
        "not_needed_files",
        "decision_files",
        "unavailable_files",
        "notes",
        "context_budget",
    }


def test_scope_reports_all_unavailable_reasons():
    state = AnalysisSessionState(session_id="scope_unavailable", data_state="data_loaded")
    state.data_pool = [
        _profile("failed", status="failed"),
        _profile("missing_contract"),
        _profile("blocked"),
        {"filename": "anonymous.csv", "dataset": "anonymous", "status": "loaded"},
    ]
    _add_contract(state, "failed")
    _add_contract(state, "blocked", status="blocked")
    _add_contract(state, "anonymous")

    plan = build_analysis_scope_plan(state, "inspect data quality")

    assert [item["reason_code"] for item in plan["unavailable_files"]] == [
        "load_failed",
        "missing_dataset_contract",
        "contract_blocked",
        "missing_file_identity",
    ]
    assert plan["scope_status"] == "ready_with_notes"


def test_explicit_exclusion_overrides_unavailable_and_never_blocks():
    state = AnalysisSessionState(session_id="scope_exclusion", data_state="data_loaded")
    state.data_pool = [_profile("broken", status="failed")]

    plan = build_analysis_scope_plan(state, "exclude broken.csv")

    decision = plan["file_decisions"][0]
    assert decision["eligibility"] == "unavailable"
    assert decision["assignment"] == "not_needed"
    assert decision["reason_code"] == "explicit_user_exclusion"
    assert plan["scope_status"] == "ready_with_notes"


def test_unavailable_optional_file_does_not_block_eligible_work():
    state = _state(_profile("orders"), _profile("broken", status="failed"))

    plan = build_analysis_scope_plan(state, "analyze orders")

    assert plan["scope_status"] == "ready_with_notes"
    assert plan["unavailable_files"][0]["reason_code"] == "load_failed"


@pytest.mark.parametrize("binding", [False, True])
def test_unavailable_required_file_blocks_scope(binding):
    state = AnalysisSessionState(session_id="scope_required_unavailable", data_state="data_loaded")
    state.data_pool = [_profile("broken", status="failed")]
    if binding:
        state.analysis_plan = {
            "method_plan": [{"step_id": "task_broken", "dataset_inputs": ["broken"]}]
        }
        goal = "analyze current data"
    else:
        goal = "analyze broken.csv"

    plan = build_analysis_scope_plan(state, goal)

    assert plan["scope_status"] == "blocked"
    assert plan["unavailable_files"][0]["reason_code"] == "load_failed"


def test_relationship_flags_never_change_eligibility_or_assignment():
    state = _state(_profile("orders"), _profile("coupon"))
    state.file_relationships = [{
        "relationship_id": "rel_orders_coupon",
        "file_ids": ["orders", "coupon"],
        "status": "possibly_linked",
        "requires_confirmation": True,
    }]

    plan = build_analysis_scope_plan(state, "analyze the uploaded files")

    assert plan["used_files"] == []
    assert [item["file_id"] for item in plan["available_files"]] == ["orders", "coupon"]
    assert [item["reason_code"] for item in plan["available_files"]] == [
        "explicit_all_pending_plan",
        "explicit_all_pending_plan",
    ]
    assert plan["decision_files"] == []
    assert all("relationship" not in item for item in plan["file_decisions"])


def test_duplicate_explicit_reference_is_prioritized_with_bounded_full_counts():
    profiles = [
        _profile("sales_a", dataset="sales_a", filename="sales.csv"),
        _profile("sales_b", dataset="sales_b", filename="sales.csv"),
        *[_profile(f"extra_{index}") for index in range(1, 6)],
    ]
    state = _state(*profiles)

    first = build_analysis_scope_plan(state, "analyze sales.csv")
    second = build_analysis_scope_plan(state, "analyze sales.csv")

    assert first == second
    assert first["scope_status"] == "needs_decision"
    assert [item["file_id"] for item in first["decision_files"]] == ["sales_a", "sales_b"]
    assert all(
        item["reason_code"] == "ambiguous_file_reference"
        for item in first["decision_files"]
    )
    assert len(first["file_decisions"]) == 5
    assert first["context_budget"] == {
        "eligible_file_count": 7,
        "used_file_count": 0,
        "available_file_count": 5,
        "not_needed_file_count": 0,
        "decision_file_count": 2,
        "unavailable_file_count": 0,
        "total_file_count": 7,
        "returned_file_count": 5,
        "omitted_file_count": 2,
        "max_scope_files": 5,
    }


def test_unique_file_id_resolves_its_duplicate_filename_group():
    state = _state(
        _profile("sales_a", dataset="sales_a", filename="sales.csv"),
        _profile("sales_b", dataset="sales_b", filename="sales.csv"),
    )

    plan = build_analysis_scope_plan(state, "analyze sales.csv using sales_b")

    assert plan["scope_status"] == "ready_with_notes"
    assert plan["decision_files"] == []
    assert [item["file_id"] for item in plan["available_files"]] == [
        "sales_a",
        "sales_b",
    ]


def test_unique_file_id_only_resolves_its_own_duplicate_alias_group():
    state = _state(
        _profile("sales_a", dataset="sales_a", filename="sales.csv"),
        _profile("sales_b", dataset="sales_b", filename="sales.csv"),
        _profile("cost_a", dataset="cost_a", filename="cost.csv"),
        _profile("cost_b", dataset="cost_b", filename="cost.csv"),
    )

    plan = build_analysis_scope_plan(
        state,
        "analyze sales.csv using sales_b and compare cost.csv",
    )

    assert [item["file_id"] for item in plan["decision_files"]] == [
        "cost_a",
        "cost_b",
    ]


def test_unavailable_duplicate_filename_is_not_an_ambiguity_candidate():
    state = AnalysisSessionState(session_id="eligible_aliases", data_state="data_loaded")
    state.data_pool = [
        _profile("sales_ready", dataset="sales_ready", filename="sales.csv"),
        _profile("sales_failed", dataset="sales_failed", filename="sales.csv", status="failed"),
    ]
    _add_contract(state, "sales_ready")

    plan = build_analysis_scope_plan(state, "analyze sales.csv")

    assert plan["decision_files"] == []
    assert [item["file_id"] for item in plan["available_files"]] == ["sales_ready"]
    assert [item["file_id"] for item in plan["unavailable_files"]] == ["sales_failed"]


def test_chinese_dataset_alias_does_not_match_a_longer_business_term():
    state = AnalysisSessionState(session_id="chinese_alias_boundary", data_state="data_loaded")
    state.data_pool = [
        _profile("sales_a", dataset="销售", filename="sales_a.csv"),
        _profile("sales_b", dataset="销售", filename="sales_b.csv"),
    ]
    state.dataset_contracts = [
        {"id": "duc_sales", "dataset": "销售", "quality_status": "ready"},
    ]

    plan = build_analysis_scope_plan(state, "分析销售额趋势")

    assert plan["decision_files"] == []


def test_chinese_dataset_alias_matches_when_delimited_by_quotes():
    state = AnalysisSessionState(session_id="chinese_alias_quoted", data_state="data_loaded")
    state.data_pool = [
        _profile("sales_a", dataset="销售", filename="sales_a.csv"),
        _profile("sales_b", dataset="销售", filename="sales_b.csv"),
    ]
    state.dataset_contracts = [
        {"id": "duc_sales", "dataset": "销售", "quality_status": "ready"},
    ]

    plan = build_analysis_scope_plan(state, "分析“销售”趋势")

    assert [item["file_id"] for item in plan["decision_files"]] == ["sales_a", "sales_b"]


def test_complete_chinese_filename_remains_an_explicit_reference():
    state = _state(
        _profile("sales_a", dataset="sales_a", filename="销售.csv"),
        _profile("sales_b", dataset="sales_b", filename="销售.csv"),
    )

    plan = build_analysis_scope_plan(state, "分析销售.csv")

    assert [item["file_id"] for item in plan["decision_files"]] == ["sales_a", "sales_b"]


def test_material_ambiguity_groups_use_all_candidates_while_scope_stays_bounded():
    profiles = [
        _profile(f"sales_{index}", dataset=f"sales_{index}", filename="sales.csv")
        for index in range(25)
    ]
    state = _state(*profiles)

    plan = build_analysis_scope_plan(state, "analyze sales.csv")

    assert len(plan["file_decisions"]) == 5
    assert len(plan["decision_files"]) == 5
    assert plan["context_budget"]["decision_file_count"] == 25
    assert len(json.dumps(plan, ensure_ascii=False)) < 6000


def test_large_eligible_history_keeps_full_counts_with_bounded_details():
    state = _state(*[_profile(f"history_{index}") for index in range(20)])

    plan = build_analysis_scope_plan(state, "analyze all files")

    assert len(plan["file_decisions"]) == 5
    assert plan["context_budget"]["eligible_file_count"] == 20
    assert plan["context_budget"]["available_file_count"] == 20
    assert plan["context_budget"]["total_file_count"] == 20
    assert plan["context_budget"]["returned_file_count"] == 5
    assert plan["context_budget"]["omitted_file_count"] == 15
    assert len(json.dumps(plan, ensure_ascii=False)) < 6000


def test_material_decision_at_end_of_large_history_is_kept_in_bounded_details():
    profiles = [
        *[_profile(f"history_{index}") for index in range(8)],
        _profile("sales_a", dataset="sales_a", filename="sales.csv"),
        _profile("sales_b", dataset="sales_b", filename="sales.csv"),
    ]
    state = _state(*profiles)

    plan = build_analysis_scope_plan(state, "analyze sales.csv")

    assert len(plan["file_decisions"]) == 5
    assert plan["context_budget"]["decision_file_count"] == 2
    assert any(
        item["assignment"] == "needs_decision"
        for item in plan["file_decisions"]
    )


def test_unique_file_id_does_not_hide_an_unrelated_duplicate_filename():
    state = _state(
        _profile("users"),
        _profile("sales_a", dataset="sales_a", filename="sales.csv"),
        _profile("sales_b", dataset="sales_b", filename="sales.csv"),
    )

    plan = build_analysis_scope_plan(state, "compare users with sales.csv")

    assert plan["scope_status"] == "needs_decision"
    assert [item["file_id"] for item in plan["decision_files"]] == [
        "sales_a",
        "sales_b",
    ]
    assert [item["file_id"] for item in plan["available_files"]] == ["users"]


def test_shared_dataset_plan_binding_requires_a_physical_file_decision():
    state = AnalysisSessionState(session_id="shared_dataset", data_state="data_loaded")
    state.data_pool = [
        _profile("main_a", dataset="main", dataset_contract_id="duc_main_a"),
        _profile("main_b", dataset="main", dataset_contract_id="duc_main_b"),
    ]
    state.dataset_contracts = [
        {"id": "duc_main_a", "dataset": "main", "quality_status": "ready"},
        {"id": "duc_main_b", "dataset": "main", "quality_status": "ready"},
    ]
    state.analysis_plan = {
        "method_plan": [{"step_id": "task_main", "dataset_inputs": ["main"]}]
    }

    plan = build_analysis_scope_plan(state, "run current analysis")

    assert plan["used_files"] == []
    assert [item["file_id"] for item in plan["decision_files"]] == ["main_a", "main_b"]
    assert all(
        item["reason_code"] == "ambiguous_file_reference"
        for item in plan["decision_files"]
    )


def test_explicit_file_selection_narrows_shared_dataset_binding():
    state = AnalysisSessionState(session_id="selected_shared_dataset", data_state="data_loaded")
    state.data_pool = [
        _profile("main_a", dataset="main", dataset_contract_id="duc_main_a"),
        _profile("main_b", dataset="main", dataset_contract_id="duc_main_b"),
    ]
    state.dataset_contracts = [
        {"id": "duc_main_a", "dataset": "main", "quality_status": "ready"},
        {"id": "duc_main_b", "dataset": "main", "quality_status": "ready"},
    ]
    state.analysis_plan = {
        "method_plan": [{"step_id": "task_main", "dataset_inputs": ["main"]}]
    }

    plan = build_analysis_scope_plan(state, "use main_b")

    assert [item["file_id"] for item in plan["used_files"]] == ["main_b"]
    assert [item["file_id"] for item in plan["not_needed_files"]] == ["main_a"]
    decisions = {item["file_id"]: item for item in plan["file_decisions"]}
    assert decisions["main_a"]["task_refs"] == []
    assert decisions["main_b"]["task_refs"] == ["task_main"]


def test_upload_order_selection_narrows_large_shared_dataset_binding():
    state = AnalysisSessionState(session_id="selected_large_dataset", data_state="data_loaded")
    state.data_pool = [_profile("unrelated", dataset="other")]
    state.data_pool.extend(
        _profile(
            f"main_{index}",
            dataset="main",
            dataset_contract_id=f"duc_main_{index}",
        )
        for index in range(1, 22)
    )
    state.dataset_contracts = [
        {"id": "duc_other", "dataset": "other", "quality_status": "ready"},
        *[
            {"id": f"duc_main_{index}", "dataset": "main", "quality_status": "ready"}
            for index in range(1, 22)
        ],
    ]
    state.analysis_plan = {
        "method_plan": [{"step_id": "task_main", "dataset_inputs": ["main"]}]
    }

    plan = build_analysis_scope_plan(state, "use the 第 22 个文件")

    assert plan["context_budget"]["used_file_count"] == 1
    assert plan["context_budget"]["decision_file_count"] == 0
    selected = next(item for item in plan["file_decisions"] if item["file_id"] == "main_21")
    assert selected["assignment"] == "used"
    assert selected["task_refs"] == ["task_main"]


def test_explicit_selection_only_narrows_its_plan_binding_group():
    state = AnalysisSessionState(session_id="selected_one_binding_group", data_state="data_loaded")
    state.data_pool = [
        _profile("sales_a", dataset="sales", dataset_contract_id="duc_sales_a"),
        _profile("sales_b", dataset="sales", dataset_contract_id="duc_sales_b"),
        _profile("cost_a", dataset="cost", dataset_contract_id="duc_cost_a"),
        _profile("cost_b", dataset="cost", dataset_contract_id="duc_cost_b"),
    ]
    state.dataset_contracts = [
        {"id": f"duc_{name}", "dataset": dataset, "quality_status": "ready"}
        for name, dataset in (
            ("sales_a", "sales"),
            ("sales_b", "sales"),
            ("cost_a", "cost"),
            ("cost_b", "cost"),
        )
    ]
    state.analysis_plan = {
        "method_plan": [
            {"step_id": "task_sales", "dataset_inputs": ["sales"]},
            {"step_id": "task_cost", "dataset_inputs": ["cost"]},
        ]
    }

    plan = build_analysis_scope_plan(state, "use sales_b")

    assert [item["file_id"] for item in plan["used_files"]] == ["sales_b"]
    assert [item["file_id"] for item in plan["decision_files"]] == ["cost_a", "cost_b"]
    decisions = {item["file_id"]: item for item in plan["file_decisions"]}
    assert decisions["sales_a"]["task_refs"] == []
    assert decisions["cost_a"]["task_refs"] == ["task_cost"]
    assert decisions["cost_b"]["task_refs"] == ["task_cost"]


def test_unavailable_plan_candidate_does_not_make_the_only_eligible_file_ambiguous():
    state = AnalysisSessionState(session_id="eligible_plan_binding", data_state="data_loaded")
    state.data_pool = [
        _profile("main_ready", dataset="main", filename="ready.csv"),
        _profile("main_failed", dataset="main", filename="failed.csv", status="failed"),
    ]
    state.dataset_contracts = [
        {"id": "duc_main", "dataset": "main", "quality_status": "ready"},
    ]
    state.analysis_plan = {
        "method_plan": [{"step_id": "task_main", "dataset_inputs": ["main"]}]
    }

    plan = build_analysis_scope_plan(state, "run current analysis")

    assert plan["scope_status"] == "ready_with_notes"
    assert plan["decision_files"] == []
    assert [item["file_id"] for item in plan["used_files"]] == ["main_ready"]
    failed = next(item for item in plan["file_decisions"] if item["file_id"] == "main_failed")
    assert failed["task_refs"] == []


@pytest.mark.parametrize("dataset_input", ["main_failed", "duc_main_failed"])
def test_explicit_file_or_contract_binding_to_unavailable_file_stays_blocked(dataset_input):
    state = AnalysisSessionState(session_id="explicit_unavailable_binding", data_state="data_loaded")
    state.data_pool = [
        _profile(
            "main_failed",
            dataset="main",
            filename="failed.csv",
            status="failed",
            dataset_contract_id="duc_main_failed",
        ),
    ]
    state.dataset_contracts = [
        {"id": "duc_main_failed", "dataset": "main", "quality_status": "ready"},
    ]
    state.analysis_plan = {
        "method_plan": [{"step_id": "task_main", "dataset_inputs": [dataset_input]}]
    }

    plan = build_analysis_scope_plan(state, "run current analysis")

    assert plan["scope_status"] == "blocked"
    assert plan["file_decisions"][0]["task_refs"] == ["task_main"]


def test_dataset_binding_with_no_eligible_candidate_keeps_unavailable_files_required():
    state = AnalysisSessionState(session_id="unavailable_dataset_binding", data_state="data_loaded")
    state.data_pool = [
        _profile("main_failed_a", dataset="main", filename="failed_a.csv", status="failed"),
        _profile("main_failed_b", dataset="main", filename="failed_b.csv", status="failed"),
    ]
    state.dataset_contracts = [
        {"id": "duc_main", "dataset": "main", "quality_status": "ready"},
    ]
    state.analysis_plan = {
        "method_plan": [{"step_id": "task_main", "dataset_inputs": ["main"]}]
    }

    plan = build_analysis_scope_plan(state, "run current analysis")

    assert plan["scope_status"] == "blocked"
    assert plan["decision_files"] == []
    assert all(item["task_refs"] == ["task_main"] for item in plan["file_decisions"])


def test_contract_id_plan_binding_selects_one_file_from_a_shared_dataset():
    state = AnalysisSessionState(session_id="contract_binding", data_state="data_loaded")
    state.data_pool = [
        _profile("main_a", dataset="main", dataset_contract_id="duc_main_a"),
        _profile("main_b", dataset="main", dataset_contract_id="duc_main_b"),
    ]
    state.dataset_contracts = [
        {"id": "duc_main_a", "dataset": "main", "quality_status": "ready"},
        {"id": "duc_main_b", "dataset": "main", "quality_status": "ready"},
    ]
    state.analysis_plan = {
        "method_plan": [{"step_id": "task_main_b", "dataset_inputs": ["duc_main_b"]}]
    }

    plan = build_analysis_scope_plan(state, "analyze main")

    assert [item["file_id"] for item in plan["used_files"]] == ["main_b"]
    assert [item["file_id"] for item in plan["not_needed_files"]] == ["main_a"]


def test_dictionary_dataset_contracts_keep_unique_dataset_binding_supported():
    state = AnalysisSessionState(session_id="dict_contract", data_state="data_loaded")
    state.data_pool = [_profile("orders")]
    state.dataset_contracts = {
        "duc_orders": {"id": "duc_orders", "dataset": "orders", "quality_status": "ready"}
    }
    state.analysis_plan = {
        "method_plan": [{"step_id": "task_orders", "dataset_inputs": ["orders"]}]
    }

    plan = build_analysis_scope_plan(state, "analyze orders")

    assert [item["file_id"] for item in plan["used_files"]] == ["orders"]


def test_dataset_name_substring_does_not_count_as_an_explicit_reference():
    state = AnalysisSessionState(session_id="substring_reference", data_state="data_loaded")
    state.data_pool = [_profile("main", status="failed")]

    plan = build_analysis_scope_plan(state, "domain analysis")

    assert plan["scope_status"] == "ready_with_notes"


def test_exact_dataset_name_still_counts_as_an_explicit_reference():
    state = AnalysisSessionState(session_id="exact_reference", data_state="data_loaded")
    state.data_pool = [_profile("main", status="failed")]

    plan = build_analysis_scope_plan(state, "analyze main")

    assert plan["scope_status"] == "blocked"


@pytest.mark.parametrize(
    ("profile", "goal"),
    [
        (_profile("broken"), "exclude the broken.csv file"),
        (_profile("broken_cn", filename="损坏.csv"), "请不要使用损坏.csv文件"),
    ],
)
def test_explicit_exclusion_allows_connecting_words(profile, goal):
    state = _state(profile)

    plan = build_analysis_scope_plan(state, goal)

    assert plan["file_decisions"][0]["assignment"] == "not_needed"
    assert plan["file_decisions"][0]["reason_code"] == "explicit_user_exclusion"
