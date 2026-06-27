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
