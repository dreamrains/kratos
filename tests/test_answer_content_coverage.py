import json

from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.publication_synthesis import (
    build_publication_packet,
    extract_publication_fact_groups,
    extract_publication_facts,
    parse_answer_bindings,
    apply_answer_binding_coverage,
    render_bound_claims,
    update_requirement_lifecycle,
    validate_final_narrative_issues,
)


def _state_with_metrics(metrics: dict) -> AnalysisSessionState:
    state = AnalysisSessionState("coverage")
    state.add_tool_receipt({
        "id": "tr_metrics",
        "tool_name": "run_python",
        "result_sha256": "sha256:result",
        "structured_result_sha256": "sha256:structured",
        "result_preview": "metrics computed",
        "publication_facts": extract_publication_facts(metrics, max_facts=500),
        "publication_fact_groups": extract_publication_fact_groups(metrics, receipt_id="tr_metrics")["groups"],
        "publication_contract": {"schema_version": "publication_scope.v1", "tool": "run_python"},
    })
    return state


def _binding(packet: dict, blocks: list[dict]) -> str:
    return "```answer-bindings\n" + json.dumps({
        "schema_version": "answer_bindings.v1",
        "packet_digest": packet["snapshot_digest"],
        "blocks": blocks,
    }, ensure_ascii=False) + "\n```"


def test_ac16_two_explicit_requirements_cannot_be_satisfied_by_one_metric():
    state = _state_with_metrics({"收入": {"value": 100}, "复购率": {"value": 0.2}})
    packet = build_publication_packet(
        state, user_input="请回答收入和复购率", substantive_tools={"run_python"},
    )
    issues = validate_final_narrative_issues("收入为100元。", packet)
    assert any(issue["code"] == "missing_answer_requirement" and issue["span"] == "复购率" for issue in issues)


def test_ac17_nine_items_allow_eight_answers_and_one_specific_gap():
    labels = [f"指标{i}" for i in range(1, 10)]
    state = _state_with_metrics({label: {"value": index} for index, label in enumerate(labels, 1)})
    request = "\n".join(f"{index}. {label}" for index, label in enumerate(labels, 1))
    packet = build_publication_packet(state, user_input=request, substantive_tools={"run_python"})
    blocks = []
    for index, requirement in enumerate(packet["requirements"][:8], 1):
        fact = next(
            fact for fact in packet["sources"][0]["facts"]
            if fact["path"] == f"指标{index}.value"
        )
        blocks.append({
            "claim_id": f"claim_metric_{index}", "claim_type": "observed_fact",
            "status": "observed", "exact_text": f"[[claim:claim_metric_{index}]]",
            "requirement_refs": [requirement["id"]], "fact_refs": [fact["fact_id"]],
            "derived_refs": [],
        })
    visible = "。".join([block["exact_text"] for block in blocks] + ["指标9缺少分母，证据不足"])
    answer, bindings, binding_issues = parse_answer_bindings(visible + "\n\n" + _binding(packet, blocks), packet)
    assert not binding_issues
    packet["answer_bindings"] = bindings
    assert not [issue for issue in validate_final_narrative_issues(answer, packet) if issue["code"] == "missing_answer_requirement"]


def test_ac18_not_computed_and_evidence_insufficient_stay_distinct():
    packet = {
        "requirements": [
            {"id": "rq_a", "label": "渠道拆分"},
            {"id": "rq_b", "label": "复购率"},
        ],
        "publication_scope": [],
    }
    text = "渠道拆分因本轮预算限制尚未计算。复购率缺少订单分母，证据不足。"
    assert validate_final_narrative_issues(text, packet) == []
    assert packet["requirements"][0]["answer_coverage"] == "not_computed"
    assert packet["requirements"][1]["answer_coverage"] == "evidence_insufficient"


def test_ac19_host_rejects_model_binding_to_unknown_fact():
    state = _state_with_metrics({"收入": {"value": 100}})
    packet = build_publication_packet(state, user_input="请回答收入和复购率", substantive_tools={"run_python"})
    text = "收入为100元。复购率为20%。\n\n" + _binding(packet, [{
        "exact_text": "复购率为20%。",
        "requirement_refs": [packet["requirements"][1]["id"]],
        "fact_refs": ["fact_from_old_version"],
        "derived_refs": [],
    }])
    _, _, issues = parse_answer_bindings(text, packet)
    assert [issue["code"] for issue in issues] == ["unresolved_answer_binding"]


def test_ac20_requirement_retraction_and_window_replacement_are_versioned():
    state = AnalysisSessionState("lifecycle")
    ids = update_requirement_lifecycle(state, "请回答收入和复购率", source_message_ref="msg1")
    assert len(ids) == 2
    revision1 = state.requirement_revision
    active = update_requirement_lifecycle(state, "撤回复购率", source_message_ref="msg2")
    assert len(active) == 1
    assert state.requirement_revision == revision1 + 1
    old = update_requirement_lifecycle(state, "请回答最近7天收入和渠道", source_message_ref="msg3")
    assert old
    new = update_requirement_lifecycle(state, "把最近7天收入改为最近30天收入", source_message_ref="msg4")
    assert len(new) == 1
    assert any(item["label"] == "最近30天收入" and item["lifecycle_status"] == "active" for item in state.answer_requirements)
    assert any(item["label"] == "最近7天收入" and item["lifecycle_status"] == "superseded" for item in state.answer_requirements)


def test_ac21_binding_is_removed_and_stale_or_malformed_protocol_is_not_trusted():
    state = _state_with_metrics({"收入": {"value": 100}})
    packet = build_publication_packet(state, user_input="请回答收入和复购率", substantive_tools={"run_python"})
    fact_id = packet["sources"][0]["facts"][0]["fact_id"]
    visible = "收入为100元。"
    text = visible + "\n\n" + _binding(packet, [{
        "exact_text": visible,
        "requirement_refs": [packet["requirements"][0]["id"]],
        "fact_refs": [fact_id],
        "derived_refs": [],
    }])
    clean, bindings, issues = parse_answer_bindings(text, packet)
    assert clean == visible and bindings and not issues
    assert "answer-bindings" not in clean

    stale = text.replace(packet["snapshot_digest"], "sha256:old")
    assert parse_answer_bindings(stale, packet)[2][0]["code"] == "stale_answer_bindings"
    assert parse_answer_bindings(visible + "\n```answer-bindings\n{bad}\n```", packet)[2][0]["code"] == "invalid_answer_bindings_json"


def test_cr03_unbound_number_cannot_answer_an_explicit_requirement():
    packet = build_publication_packet(
        _state_with_metrics({"收入": {"value": 100}}),
        user_input="1. 复购率", substantive_tools={"run_python"},
    )
    issues = validate_final_narrative_issues("复购率为20%。", packet)
    assert any(item["code"] == "missing_answer_requirement" for item in issues)
    assert packet["requirements"][0]["answer_coverage"] != "answered"


def test_cr03_gap_marker_cannot_launder_an_unbound_number():
    packet = build_publication_packet(
        _state_with_metrics({"收入": {"value": 100}}),
        user_input="1. 复购率", substantive_tools={"run_python"},
    )
    issues = validate_final_narrative_issues("复购率为20%，缺少分母。", packet)
    assert any(item["code"] == "missing_answer_requirement" for item in issues)
    assert packet["requirements"][0]["answer_coverage"] != "answered"


def test_cr03_later_gap_cannot_launder_an_earlier_numeric_claim():
    packet = build_publication_packet(
        _state_with_metrics({"收入": {"value": 100}}),
        user_input="1. 复购率", substantive_tools={"run_python"},
    )
    issues = validate_final_narrative_issues("复购率为20%。复购率缺少分母，证据不足。", packet)
    assert any(item["code"] == "unbound_requirement_numeric" for item in issues)


def test_cr03_valid_bound_claim_does_not_exempt_a_second_raw_number():
    packet = build_publication_packet(
        _state_with_metrics({"复购率": {"value": 0.2}}),
        user_input="1. 复购率", substantive_tools={"run_python"},
    )
    placeholder = "[[claim:claim_repeat]]"
    visible = placeholder + "。复购率另有40%的结果。"
    text = visible + "\n\n" + _binding(packet, [{
        "claim_id": "claim_repeat", "claim_type": "observed_fact", "status": "observed",
        "exact_text": placeholder,
        "requirement_refs": [packet["requirements"][0]["id"]],
        "fact_refs": [packet["sources"][0]["facts"][0]["fact_id"]],
        "derived_refs": [],
    }])
    clean, bindings, binding_issues = parse_answer_bindings(text, packet)
    assert not binding_issues
    packet["answer_bindings"] = bindings
    issues = validate_final_narrative_issues(clean, packet)
    assert any(item["code"] == "unbound_requirement_numeric" for item in issues)


def test_cr03_current_but_unrelated_fact_cannot_authorize_requirement():
    packet = build_publication_packet(
        _state_with_metrics({"收入": {"value": 100}}),
        user_input="1. 复购率", substantive_tools={"run_python"},
    )
    visible = "复购率为20%。"
    text = visible + "\n\n" + _binding(packet, [{
        "exact_text": visible,
        "claim_type": "observed_fact",
        "requirement_refs": [packet["requirements"][0]["id"]],
        "fact_refs": [packet["sources"][0]["facts"][0]["fact_id"]],
        "derived_refs": [],
    }])
    _, bindings, issues = parse_answer_bindings(text, packet)
    assert any(item["code"] == "invalid_observed_binding" for item in issues)
    apply_answer_binding_coverage(packet, bindings)
    assert packet["requirements"][0]["answer_coverage"] != "answered"


def test_cr03_wrong_value_cannot_authorize_correct_fact_reference():
    packet = build_publication_packet(
        _state_with_metrics({"复购率": {"value": 0.2}}),
        user_input="1. 复购率", substantive_tools={"run_python"},
    )
    visible = "复购率为40%。"
    text = visible + "\n\n" + _binding(packet, [{
        "exact_text": visible,
        "claim_type": "observed_fact",
        "requirement_refs": [packet["requirements"][0]["id"]],
        "fact_refs": [packet["sources"][0]["facts"][0]["fact_id"]],
        "derived_refs": [],
    }])
    _, bindings, issues = parse_answer_bindings(text, packet)
    assert any(item["code"] == "invalid_observed_binding" for item in issues)
    apply_answer_binding_coverage(packet, bindings)
    assert packet["requirements"][0]["answer_coverage"] != "answered"


def test_cr03_matching_observed_claim_is_rendered_from_its_own_receipt():
    packet = build_publication_packet(
        _state_with_metrics({"复购率": {"value": 0.2}}),
        user_input="1. 复购率", substantive_tools={"run_python"},
    )
    placeholder = "[[claim:claim_repeat]]"
    text = placeholder + "\n\n" + _binding(packet, [{
        "claim_id": "claim_repeat",
        "claim_type": "observed_fact",
        "status": "observed",
        "exact_text": placeholder,
        "requirement_refs": [packet["requirements"][0]["id"]],
        "fact_refs": [packet["sources"][0]["facts"][0]["fact_id"]],
        "derived_refs": [],
    }])
    clean, bindings, issues = parse_answer_bindings(text, packet)
    assert not issues
    packet["answer_bindings"] = bindings
    assert not validate_final_narrative_issues(clean, packet)
    assert packet["requirements"][0]["answer_coverage"] == "answered"
    assert render_bound_claims(clean, packet, bindings) == "复购率：0.2（回执原始数值尺度；单位未确认）"


def test_cr03_observed_zero_is_a_result_not_a_missing_value():
    packet = build_publication_packet(
        _state_with_metrics({"收入": {"value": 0}}),
        user_input="1. 收入", substantive_tools={"run_python"},
    )
    placeholder = "[[claim:claim_zero]]"
    fact = next(item for item in packet["sources"][0]["facts"] if item["path"] == "收入.value")
    block = {
        "claim_id": "claim_zero", "claim_type": "observed_fact", "status": "observed",
        "exact_text": placeholder,
        "requirement_refs": [packet["requirements"][0]["id"]],
        "fact_refs": [fact["fact_id"]], "derived_refs": [],
    }
    clean, bindings, issues = parse_answer_bindings(placeholder + "\n\n" + _binding(packet, [block]), packet)
    assert not issues
    packet["answer_bindings"] = bindings
    assert not validate_final_narrative_issues(clean, packet)
    assert "收入：0" in render_bound_claims(clean, packet, bindings)


def test_cr03_non_numeric_receipt_value_is_not_an_observed_numeric_answer():
    packet = build_publication_packet(
        _state_with_metrics({"复购率": {"value": "unknown"}}),
        user_input="1. 复购率", substantive_tools={"run_python"},
    )
    placeholder = "[[claim:claim_repeat]]"
    text = placeholder + "\n\n" + _binding(packet, [{
        "claim_id": "claim_repeat", "claim_type": "observed_fact", "status": "observed",
        "exact_text": placeholder,
        "requirement_refs": [packet["requirements"][0]["id"]],
        "fact_refs": [packet["sources"][0]["facts"][0]["fact_id"]],
        "derived_refs": [],
    }])
    assert any(item["code"] == "invalid_observed_binding" for item in parse_answer_bindings(text, packet)[2])


def test_cr03_derived_binding_survives_real_packet_build_and_renders_in_place():
    state = _state_with_metrics({"留存人数": {"value": 1142.4}})
    state.add_evidence_record({
        "id": "ev_retained", "claim": "留存人数由人数和比率计算",
        "tool_receipt_ids": ["tr_metrics"],
        "measurements": [
            {"id": "population", "value": 22400, "unit": "count", "population_scope": "new_users", "time_scope": "2026-09", "data_identity": "v1"},
            {"id": "rate", "value": "0.051", "unit": "ratio", "population_scope": "new_users", "time_scope": "2026-09", "data_identity": "v1"},
        ],
        "derived_measurements": [{
            "id": "dm_retained", "operation": "product", "operand_refs": ["population", "rate"],
            "result": "1142.4", "unit": "count", "scope_ref": "new_users_2026_09",
        }],
    })
    packet = build_publication_packet(state, user_input="1. 留存人数", substantive_tools={"run_python"})
    placeholder = "[[claim:claim_retained]]"
    fact = next(item for item in packet["sources"][0]["facts"] if item["path"] == "留存人数.value")
    block = {
        "claim_id": "claim_retained", "claim_type": "derived_metric", "status": "computed",
        "unit_status": "not_confirmed", "exact_text": placeholder,
        "requirement_refs": [packet["requirements"][0]["id"]],
        "fact_refs": [fact["fact_id"]], "derived_refs": ["dm_retained"],
    }
    clean, bindings, issues = parse_answer_bindings(placeholder + "\n\n" + _binding(packet, [block]), packet)
    assert not issues
    packet["answer_bindings"] = bindings
    assert not validate_final_narrative_issues(clean, packet)
    assert "留存人数：1142.4" in render_bound_claims(clean, packet, bindings)
