"""Offline audit input must be anchored to an accepted host-rendered claim."""

import hashlib
import json
from copy import deepcopy

from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.publication_audit import build_offline_audit_view
from data_agent.agent.publication_synthesis import (
    build_publication_packet,
    extract_publication_facts,
    parse_answer_bindings,
    render_bound_claims,
    update_requirement_lifecycle,
)
from data_agent.session.history import CanonicalHistorySnapshot, _history_sha256


def _accepted_observation(*, extra_prose="", duplicate=False):
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
    candidate = "\n".join(placeholders) + extra_prose + "\n```answer-bindings\n" + json.dumps({
        "schema_version": "answer_bindings.v1", "packet_digest": packet["snapshot_digest"],
        "blocks": blocks,
    }, ensure_ascii=False) + "\n```"
    visible, bindings, issues = parse_answer_bindings(candidate, packet)
    assert issues == []
    accepted_answer = render_bound_claims(visible, packet, bindings).rstrip()
    committed = deepcopy(packet)
    committed["phase"] = "final"
    committed["answer_bindings"] = bindings
    committed["answer_sha256"] = "sha256:" + hashlib.sha256(accepted_answer.encode("utf-8")).hexdigest()
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
    assert claim["location_status"] == "unique_host_reconstruction_match"
    assert answer[claim["answer_span"][0]:claim["answer_span"][1]] == claim["host_rendered_text"]
    assert claim["host_rendered_text"] == "收入：100（回执原始数值尺度；单位未确认）"
    assert set(claim["evidence_refs"]) == {"tr_revenue", packet["sources"][0]["facts"][0]["fact_id"]}
    assert claim["request_anchor"]["status"] == "verbatim_only"
    assert claim["request_anchor"]["exact_span"] == "收入"
    assert claim["answer_coverage"] == "unassessed"
    assert packet == before


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


def test_duplicate_rendered_text_is_not_a_unique_answer_location():
    state, packet, history, answer = _accepted_observation(duplicate=True)
    view = build_offline_audit_view(packet, answer, state=state, canonical_history=history)
    assert view["status"] == "no_locatable_claims"
    assert view["claims"] == []
    assert view["unlocatable_claim_ids"] == ["claim_revenue", "claim_revenue_again"]


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
