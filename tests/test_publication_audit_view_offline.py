"""Offline audit input must be anchored to an accepted host-rendered claim."""

import hashlib
import json
from copy import deepcopy
from pathlib import Path

from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.loop import AgentLoop
from data_agent.agent.publication_audit import (
    build_offline_audit_view, build_shadow_audit_request, run_shadow_audit_once,
)
from data_agent.agent.publication_synthesis import (
    build_publication_packet,
    extract_publication_facts,
    parse_answer_bindings,
    render_bound_claims_with_trace,
    update_requirement_lifecycle,
    validate_final_narrative,
)
from data_agent.session.history import CanonicalHistorySnapshot, _history_sha256


def _accepted_observation(*, extra_prose="", duplicate=False, lead_prose=""):
    question = "请回答收入"
    state = AnalysisSessionState("offline_audit_view")
    source_ref = "msg_" + hashlib.sha256(question.encode("utf-8")).hexdigest()[:12]
    requirement_ids = update_requirement_lifecycle(state, question, source_message_ref=source_ref)
    state.add_tool_receipt({
        "id": "tr_revenue", "tool_name": "run_python", "result_sha256": "sha256:result",
        "structured_result_sha256": "sha256:structured", "result_preview": "revenue computed",
        "publication_facts": extract_publication_facts({"收入": {"value": 100}}),
        "publication_contract": {"schema_version": "publication_scope.v1", "tool": "run_python"},
    })
    packet = build_publication_packet(
        state, user_input=question, substantive_tools={"run_python"},
        receipt_ids=["tr_revenue"], requirement_ids=requirement_ids,
    )
    assert packet["status"] == "ready"
    fact_id = next(item["fact_id"] for item in packet["sources"][0]["facts"]
                   if item["path"] == "收入.value")
    blocks = []
    placeholders = []
    for claim_id in (["claim_revenue", "claim_revenue_again"] if duplicate else ["claim_revenue"]):
        placeholder = f"[[claim:{claim_id}]]"
        placeholders.append(placeholder)
        blocks.append({
            "claim_id": claim_id, "claim_type": "observed_fact", "status": "observed",
            "exact_text": placeholder, "requirement_refs": requirement_ids,
            "fact_refs": [fact_id], "derived_refs": [],
        })
    candidate = lead_prose + "\n".join(placeholders) + extra_prose + "\n```answer-bindings\n" + json.dumps({
        "schema_version": "answer_bindings.v1", "packet_digest": packet["snapshot_digest"],
        "blocks": blocks,
    }, ensure_ascii=False) + "\n```"
    visible, bindings, issues = parse_answer_bindings(candidate, packet)
    assert issues == []
    accepted_answer, entries = render_bound_claims_with_trace(visible, packet, bindings)
    accepted_answer = accepted_answer.rstrip()
    committed = deepcopy(packet)
    committed["phase"] = "final"
    committed["answer_bindings"] = bindings
    committed["answer_sha256"] = "sha256:" + hashlib.sha256(accepted_answer.encode("utf-8")).hexdigest()
    trace_body = {
        "schema_version": "answer_render_trace.v1",
        "packet_digest": packet["snapshot_digest"],
        "answer_sha256": committed["answer_sha256"],
        "entries": entries,
    }
    trace_seed = json.dumps(trace_body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    committed["answer_render_trace"] = {
        **trace_body, "trace_digest": "sha256:" + hashlib.sha256(trace_seed.encode("utf-8")).hexdigest(),
    }
    committed["snapshot_packet_id"] = packet["id"]
    seed = f"{packet['snapshot_digest']}|{committed['answer_sha256']}"
    committed["id"] = "pub_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]
    state.add_publication_packet(committed)
    messages = [
        {"role": "user", "content": question},
        {"role": "assistant", "content": accepted_answer,
         "publication_packet_id": committed["id"],
         "publication_snapshot_digest": committed["snapshot_digest"],
         "answer_sha256": committed["answer_sha256"]},
    ]
    history = CanonicalHistorySnapshot(
        messages=messages, revision=2, sha256=_history_sha256(messages),
        message_count=len(messages),
    )
    return state, committed, history, accepted_answer


def test_current_accepted_claim_has_unique_host_text_and_verbatim_user_anchor():
    state, packet, history, answer = _accepted_observation()
    before = deepcopy(packet)
    view = build_offline_audit_view(packet, answer, state=state, canonical_history=history)
    assert view["status"] == "ready" and view["publication_effect"] == "none"
    assert view["packet_digest"] == packet["snapshot_digest"]
    assert view["answer_sha256"] == packet["answer_sha256"]
    assert view["history_sha256"] == history.sha256
    assert len(view["claims"]) == 1
    claim = view["claims"][0]
    assert claim["claim_id"] == "claim_revenue"
    assert claim["location_status"] == "host_rendered_at_publication"
    assert answer[claim["answer_span"][0]:claim["answer_span"][1]] == claim["host_rendered_text"]
    assert claim["host_rendered_text"] == "收入：100（回执原始数值尺度；单位未确认）"
    assert set(claim["evidence_refs"]) == {"tr_revenue", packet["sources"][0]["facts"][0]["fact_id"]}
    assert claim["request_anchor"]["status"] == "verbatim_only"
    assert claim["request_anchor"]["exact_span"] == "收入"
    assert claim["answer_coverage"] == "unassessed"
    assert packet == before


def test_shadow_request_is_bounded_to_current_located_claim_and_reproducible():
    state, packet, history, answer = _accepted_observation(extra_prose="\n另一结论为99%。")
    request = build_shadow_audit_request(packet, answer, state=state, canonical_history=history)
    assert request["status"] == "ready"
    assert request["publication_effect"] == "none"
    assert request["prompt_version"] == "publication_audit_shadow.v2"
    assert request["packet_digest"] == packet["snapshot_digest"]
    assert request["answer_sha256"] == packet["answer_sha256"]
    assert len(request["claims"]) == 1
    assert request["claims"][0]["claim_id"] == "claim_revenue"
    assert "99%" not in json.dumps(request, ensure_ascii=False)
    assert request == build_shadow_audit_request(packet, answer, state=state,
                                                  canonical_history=history)


def test_shadow_request_carries_only_same_line_explanation_as_untrusted_context():
    state, packet, history, answer = _accepted_observation(
        lead_prose="模型声称已经完成外部验证，因此可预测：",
        extra_prose="\n另一结论为99%。",
    )
    request = build_shadow_audit_request(packet, answer, state=state,
                                         canonical_history=history)
    assert request["status"] == "ready"
    explanation = request["claims"][0]["local_explanation"]
    assert "recommended_action=advisory_only" in request["system_prompt"]
    assert explanation["status"] == "same_line_untrusted"
    assert explanation["before"] == "模型声称已经完成外部验证，因此可预测："
    assert explanation["after"] == ""
    assert "99%" not in json.dumps(request, ensure_ascii=False)
    assert request["publication_effect"] == "none"


def test_shadow_request_does_not_associate_long_or_multiline_prose():
    state, packet, history, answer = _accepted_observation(
        lead_prose="x" * 501,
        extra_prose="\n另一结论为99%。",
    )
    request = build_shadow_audit_request(packet, answer, state=state,
                                         canonical_history=history)
    assert request["status"] == "ready"
    assert request["claims"][0]["local_explanation"] == {"status": "unavailable"}
    assert "99%" not in json.dumps(request, ensure_ascii=False)


def test_shadow_dispatch_is_explicit_one_shot_and_diagnostic_only():
    from types import SimpleNamespace

    state, packet, history, answer = _accepted_observation(
        lead_prose="这只是已观察数值：",
    )
    calls = []

    class FakeClient:
        def chat_once(self, messages, *, system, response_format, max_tokens):
            calls.append((messages, system, response_format, max_tokens))
            return SimpleNamespace(text=json.dumps({
                "schema_version": "publication_audit.v1",
                "packet_digest": packet["snapshot_digest"],
                "answer_sha256": packet["answer_sha256"],
                "overall": "pass", "findings": [],
                "missing_requirements": [], "contradictions": [],
            }))

    client = FakeClient()
    for enabled, remaining in ((False, 1), (True, 0)):
        result = run_shadow_audit_once(
            packet, answer, state=state, canonical_history=history,
            enabled=enabled, remaining_call_budget=remaining, client=client,
        )
        assert result["status"] == "unavailable"
    assert calls == []
    result = run_shadow_audit_once(
        packet, answer, state=state, canonical_history=history,
        enabled=True, remaining_call_budget=1, client=client,
    )
    assert len(calls) == 1
    assert result["status"] == "valid"
    assert result["publication_effect"] == "none"
    assert result["audit"]["findings"] == []
    assert packet["answer_bindings"]["blocks"][0]["claim_id"] == "claim_revenue"


def test_shadow_dispatch_fails_closed_without_explanation_or_on_client_error():
    state, packet, history, answer = _accepted_observation()
    class FailClient:
        def chat_once(self, *args, **kwargs):
            raise RuntimeError("provider failed")

    result = run_shadow_audit_once(
        packet, answer, state=state, canonical_history=history,
        enabled=True, remaining_call_budget=1, client=FailClient(),
    )
    assert result["status"] == "unavailable"
    assert result["call_attempted"] is False

    state, packet, history, answer = _accepted_observation(lead_prose="仅描述观察：")
    result = run_shadow_audit_once(
        packet, answer, state=state, canonical_history=history,
        enabled=True, remaining_call_budget=1, client=FailClient(),
    )
    assert result["status"] == "unavailable"
    assert result["call_attempted"] is True
    assert result["publication_effect"] == "none"


def test_shadow_wrong_remove_opinion_cannot_change_accepted_answer():
    from types import SimpleNamespace

    state, packet, history, answer = _accepted_observation(
        lead_prose="这里只描述已观测收入：",
    )
    original = deepcopy(packet)
    original_answer = answer
    request = build_shadow_audit_request(packet, answer, state=state,
                                         canonical_history=history)
    refs = request["claims"][0]["evidence_refs"]

    class WrongOpinionClient:
        def chat_once(self, messages, *, system, response_format, max_tokens):
            return SimpleNamespace(text=json.dumps({
                "schema_version": "publication_audit.v1",
                "packet_digest": packet["snapshot_digest"],
                "answer_sha256": packet["answer_sha256"],
                "overall": "pass_with_findings",
                "findings": [{
                    "finding_id": "f_wrong_remove", "claim_id": "claim_revenue",
                    "dimension": "validation_status", "severity": "high",
                    "recommended_action": "remove", "evidence_refs": refs,
                    "reason": "模型误以为正确的观测值应被删除",
                }],
                "missing_requirements": [], "contradictions": [],
            }, ensure_ascii=False))

    result = run_shadow_audit_once(
        packet, answer, state=state, canonical_history=history,
        enabled=True, remaining_call_budget=1, client=WrongOpinionClient(),
    )
    assert result["status"] == "valid"
    assert result["audit"]["findings"][0]["suggested_action"] == "remove"
    assert result["publication_effect"] == "none"
    assert packet == original and answer == original_answer


def test_controlled_shadow_calibration_cases_are_locatable_and_separate_from_99_percent():
    path = (Path(__file__).resolve().parents[1]
            / "docs/audit/2026-09-25-shadow-c-calibration-cases.json")
    matrix = json.loads(path.read_text(encoding="utf-8"))
    assert [item["id"] for item in matrix["cases"]] == [
        "C-P1-observation", "C-N1-unverified-forecast",
        "C-P2-source-boundary", "C-N2-causal-overclaim",
    ]
    for case in matrix["cases"]:
        state, packet, history, answer = _accepted_observation(
            lead_prose=case["lead_prose"], extra_prose=case["extra_prose"],
        )
        request = build_shadow_audit_request(
            packet, answer, state=state, canonical_history=history,
        )
        visible_candidate = (case["lead_prose"] + "[[claim:claim_revenue]]"
                             + case["extra_prose"])
        assert validate_final_narrative(visible_candidate, packet) is None
        assert request["status"] == "ready"
        assert request["claims"][0]["local_explanation"]["before"] == case["lead_prose"]
        assert "99%" not in json.dumps(request, ensure_ascii=False)
        assert request["publication_effect"] == "none"


def test_shadow_request_fails_closed_for_stale_or_unlocatable_claims():
    state, packet, history, answer = _accepted_observation()
    assert build_shadow_audit_request(packet, answer + "!", state=state,
                                      canonical_history=history)["status"] == "unavailable"
    old = deepcopy(packet)
    old.pop("answer_render_trace")
    state.publication_packets[:] = [old]
    assert build_shadow_audit_request(old, answer, state=state,
                                      canonical_history=history)["status"] == "unavailable"


def test_independent_unbound_prose_is_not_granted_audit_claim_authority():
    state, packet, history, answer = _accepted_observation(extra_prose="\n另一结论为99%。")
    view = build_offline_audit_view(packet, answer, state=state, canonical_history=history)
    assert view["status"] == "ready"
    assert len(view["claims"]) == 1
    assert "99%" not in json.dumps(view, ensure_ascii=False)
    assert view["unbound_prose_status"] == "not_audited"
    assert view["publication_effect"] == "none"


def test_missing_or_tampered_persisted_answer_identity_has_no_audit_view():
    state, packet, history, answer = _accepted_observation()
    variants = [
        (packet, answer + "!", history, state),
        ({**packet, "id": "pub_forged"}, answer, history, state),
        (packet, answer, CanonicalHistorySnapshot(history.messages, history.revision,
                                                  "sha256:forged", history.message_count), state),
        (packet, answer, CanonicalHistorySnapshot(
            [{**history.messages[0]}, {**history.messages[1], "content": "forged"}],
            history.revision,
            _history_sha256([{**history.messages[0]}, {**history.messages[1], "content": "forged"}]),
            history.message_count,
        ), state),
    ]
    for candidate_packet, candidate_answer, candidate_history, candidate_state in variants:
        view = build_offline_audit_view(candidate_packet, candidate_answer,
                                        state=candidate_state, canonical_history=candidate_history)
        assert view["status"] == "unavailable" and view["claims"] == []
        assert view["publication_effect"] == "none"


def test_two_identical_host_renderings_have_distinct_recorded_positions():
    state, packet, history, answer = _accepted_observation(duplicate=True)
    view = build_offline_audit_view(packet, answer, state=state, canonical_history=history)
    assert view["status"] == "ready"
    assert len(view["claims"]) == 2
    assert view["claims"][0]["answer_span"] != view["claims"][1]["answer_span"]
    assert view["claims"][0]["host_rendered_text"] == view["claims"][1]["host_rendered_text"]


def test_missing_or_tampered_host_trace_cannot_be_reconstructed_from_matching_text():
    state, packet, history, answer = _accepted_observation()
    for trace in (None, {**packet["answer_render_trace"], "entries": [
        {**packet["answer_render_trace"]["entries"][0], "start": 1}
    ]}):
        old = deepcopy(packet)
        if trace is None:
            old.pop("answer_render_trace")
        else:
            old["answer_render_trace"] = trace
        state.publication_packets[:] = [old]
        view = build_offline_audit_view(old, answer, state=state, canonical_history=history)
        assert view["status"] == "unavailable" and view["claims"] == []


def test_legacy_or_malformed_packet_cannot_become_actionable_through_the_view():
    state, packet, history, answer = _accepted_observation()
    for field, value in (("answer_bindings", None), ("sources", None)):
        old = deepcopy(packet)
        old[field] = value
        state.publication_packets[:] = [old]
        view = build_offline_audit_view(old, answer, state=state, canonical_history=history)
        assert view["status"] == "unavailable" and view["claims"] == []
        assert view["publication_effect"] == "none"


def test_receipt_identity_drift_invalidates_offline_view():
    state, packet, history, answer = _accepted_observation()
    state.tool_receipts[0]["result_sha256"] = "sha256:changed"
    view = build_offline_audit_view(packet, answer, state=state, canonical_history=history)
    assert view["status"] == "unavailable" and view["claims"] == []


def test_terminal_renderer_records_trace_and_clears_it_before_next_candidate():
    state, committed, _history, expected_answer = _accepted_observation()
    packet = deepcopy(committed)
    packet["id"] = packet.pop("snapshot_packet_id")
    packet.pop("answer_sha256")
    packet.pop("answer_render_trace")
    packet.pop("answer_bindings")
    block = committed["answer_bindings"]["blocks"][0]
    candidate = block["exact_text"] + "\n```answer-bindings\n" + json.dumps({
        "schema_version": "answer_bindings.v1", "packet_digest": packet["snapshot_digest"],
        "blocks": [block],
    }, ensure_ascii=False) + "\n```"
    loop = AgentLoop(client=None, session_id=state.session_id)
    loop._reset_turn_tracking()
    loop.context.analysis_state = state
    loop._turn_publication_packet = packet
    answer, error = loop._render_finalized_publication(candidate)
    assert error is None and answer == expected_answer
    trace = packet["answer_render_trace"]
    assert trace["answer_sha256"] == "sha256:" + hashlib.sha256(answer.encode("utf-8")).hexdigest()
    assert trace["entries"][0]["claim_id"] == "claim_revenue"
    assert answer[trace["entries"][0]["start"]:trace["entries"][0]["end"]] == answer

    _answer, error = loop._render_finalized_publication("收入为999，但没有有效绑定。")
    assert error is not None
    assert "answer_render_trace" not in packet
