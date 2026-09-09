import json

from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.publication_synthesis import (
    build_publication_packet,
    extract_publication_fact_groups,
    extract_publication_facts,
    parse_answer_bindings,
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
    answer = "。".join([f"{label}为{index}" for index, label in enumerate(labels[:8], 1)] + ["指标9缺少分母，证据不足"])
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
