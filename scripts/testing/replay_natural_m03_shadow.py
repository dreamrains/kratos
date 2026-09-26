"""Zero-call content-equivalent replay of archived natural M03 answers."""
from __future__ import annotations

import hashlib
import json
import sys
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path("src").resolve()))

from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.publication_audit import build_offline_audit_view, build_shadow_audit_request
from data_agent.agent.publication_synthesis import partition_typed_trial_answer, render_bound_claims_with_trace
from data_agent.session.history import CanonicalHistorySnapshot, _history_sha256, _read_canonical_snapshot


def digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


root = Path("tmp/typed-trial-natural-m03-20260925-r2/sessions")
oracle_path = Path("docs/audit/2026-09-27-shadow-natural-m03-oracle.json")
oracles = {item["source_session"]: item for item in json.loads(
    oracle_path.read_text(encoding="utf-8")
)["cases"]}
bundles = []
for case, session in (("M03-P", "d2cb0464bb3a"), ("M03-N", "7e6dfed8a125")):
    folder = root / session
    raw = json.loads((folder / "analysis_state.json").read_text(encoding="utf-8"))
    state = AnalysisSessionState.from_dict(raw, session)
    old_packet = state.publication_packets[-1]
    history = _read_canonical_snapshot(folder)
    old_answer = next(
        item["content"] for item in reversed(history.messages)
        if item.get("role") == "assistant" and item.get("publication_packet_id") == old_packet["id"]
    )
    old_trace = old_packet["answer_render_trace"]
    assert digest(old_answer) == old_packet["answer_sha256"] == old_trace["answer_sha256"]
    draft = old_answer
    placeholders = {
        block["claim_id"]: block["exact_text"]
        for block in old_packet["answer_bindings"]["blocks"]
    }
    for entry in sorted(old_trace["entries"], key=lambda item: item["start"], reverse=True):
        old_span = draft[entry["start"]:entry["end"]]
        assert digest(old_span) == entry["text_sha256"]
        draft = draft[:entry["start"]] + placeholders[entry["claim_id"]] + draft[entry["end"]:]
    partitioned, pending = partition_typed_trial_answer(draft, old_packet["answer_bindings"], [])
    answer, entries = render_bound_claims_with_trace(partitioned, old_packet, old_packet["answer_bindings"])
    answer = answer.rstrip()
    shift = len(answer) - len(partitioned)
    located = []
    for item in pending:
        start, end = item["start"] + shift, item["end"] + shift
        assert answer[start:end] == partitioned[item["start"]:item["end"]]
        located.append({
            "span_id": item["span_id"], "start": start, "end": end,
            "text_sha256": digest(answer[start:end]),
        })
    packet = deepcopy(old_packet)
    packet["answer_sha256"] = digest(answer)
    packet["id"] = "pub_" + hashlib.sha256(
        f"{packet['snapshot_digest']}|{packet['answer_sha256']}".encode("utf-8")
    ).hexdigest()[:12]
    trace = {
        "schema_version": "answer_render_trace.v1", "packet_digest": packet["snapshot_digest"],
        "answer_sha256": packet["answer_sha256"], "entries": entries,
        "pending_spans": located,
    }
    trace["trace_digest"] = digest(json.dumps(
        trace, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ))
    packet["answer_render_trace"] = trace
    state.publication_packets[-1] = packet
    messages = deepcopy(history.messages)
    matches = [item for item in messages if item.get("role") == "assistant"
               and item.get("publication_packet_id") == old_packet["id"]]
    assert len(matches) == 1
    matches[0]["content"] = answer
    matches[0]["publication_packet_id"] = packet["id"]
    matches[0]["answer_sha256"] = packet["answer_sha256"]
    replay_history = CanonicalHistorySnapshot(
        messages, history.revision, _history_sha256(messages), len(messages),
    )
    view = build_offline_audit_view(packet, answer, state=state, canonical_history=replay_history)
    request = build_shadow_audit_request(packet, answer, state=state,
                                         canonical_history=replay_history)
    assert view["status"] == request["status"] == "ready"
    expected = oracles[session]
    actual_span_ids = {item["span_id"] for item in view["pending_spans"]}
    assert set(expected["oracle"]["preserve_prose_span_ids"]) <= actual_span_ids
    assert set(expected["oracle"]["review_prose_span_ids"]) <= actual_span_ids
    source_files = [folder / "analysis_state.json", folder / "conversation.json"]
    bundles.append({
        "case_id": expected["id"], "oracle": expected["oracle"],
        "state": state.to_dict(), "packet": packet,
        "history": {"messages": replay_history.messages, "revision": replay_history.revision,
                    "sha256": replay_history.sha256,
                    "message_count": replay_history.message_count},
        "answer": answer,
        "request_identity": {key: request[key] for key in (
            "prompt_version", "prompt_sha256", "input_digest", "audit_view_digest",
            "packet_digest", "answer_sha256",
        )},
        "source_file_sha256": {
            str(path): "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
            for path in source_files
        },
        "original_answer_sha256": old_packet["answer_sha256"],
    })
    print(json.dumps({
        "case": case, "source": "archived_natural_content_equivalent_zero_call_replay",
        "old_answer_sha256": old_packet["answer_sha256"],
        "replayed_answer_sha256": packet["answer_sha256"],
        "view_status": view["status"], "request_status": request["status"],
        "claim_count": len(view.get("claims", [])),
        "pending_span_count": len(view.get("pending_spans", [])),
        "pending_chars": sum(len(item["text_untrusted"]) for item in view.get("pending_spans", [])),
        "input_bytes": len(json.dumps(request.get("audit_input", {}), ensure_ascii=False).encode("utf-8")),
        "publication_effect": request.get("publication_effect"),
    }, ensure_ascii=False))
Path("tmp/shadow-natural-m03-prepared-20260927.json").write_text(json.dumps({
    "schema_version": "shadow_c_prepared_bundles.v1",
    "source_class": "archived_natural_answer_content_equivalent_replay",
    "oracle_path": str(oracle_path),
    "replay_builder_sha256": "sha256:" + hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    "cases": bundles,
}, ensure_ascii=False, sort_keys=True, separators=(",", ":")), encoding="utf-8")
