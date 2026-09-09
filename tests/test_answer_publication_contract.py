import hashlib
import json

import pytest

from data_agent.agent.analysis_state import AnalysisSessionState, load_analysis_state
from data_agent.agent.compact import _preserved_identity_and_obligations
from data_agent.agent.loop import AgentLoop
from data_agent.agent.publication_synthesis import (
    build_publication_packet,
    extract_publication_fact_groups,
    extract_publication_facts,
    publication_packet_prompt,
    read_publication_detail,
)
from data_agent.session.public_messages import assistant_replies, public_messages


def _receipt(rid, data, *, identity="v1", detail_ref=None):
    grouped = extract_publication_fact_groups(data, receipt_id=rid, detail_ref=detail_ref)
    return {
        "id": rid,
        "tool_name": "run_python",
        "result_sha256": "sha256:" + hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest(),
        "structured_result_sha256": "sha256:structured-" + rid,
        "result_preview": "computed",
        "data_identities": {"orders": {"version_id": identity, "fingerprint": identity}},
        "publication_facts": extract_publication_facts(data, max_facts=500),
        "publication_fact_groups": grouped["groups"],
        "publication_scan": grouped["scan"],
        "detail_ref": detail_ref or {},
        "publication_contract": {"schema_version": "publication_scope.v1", "tool": "run_python", "source_dataset": "orders"},
    }


def test_ac02_digest_changes_for_value_limit_version_and_verification():
    state = AnalysisSessionState("digest")
    state.tool_receipts = [_receipt("tr1", {"value": 10}, identity="v1")]
    state.evidence_records = [{"id": "ev1", "claim": "value", "limitations": ["descriptive"], "measurements": []}]
    state.verification_reports = [{"overall_status": "pass"}]
    first = build_publication_packet(state, user_input="分析value", substantive_tools={"run_python"})
    state.evidence_records[0]["limitations"] = ["missing denominator"]
    second = build_publication_packet(state, user_input="分析value", substantive_tools={"run_python"})
    state.tool_receipts[0]["data_identities"]["orders"]["version_id"] = "v2"
    third = build_publication_packet(state, user_input="分析value", substantive_tools={"run_python"})
    state.verification_reports[0]["overall_status"] = "fail"
    fourth = build_publication_packet(state, user_input="分析value", substantive_tools={"run_python"})
    assert len({item["snapshot_digest"] for item in (first, second, third, fourth)}) == 4


def test_ac03_packet_keeps_current_data_identity_without_cross_session_lookup():
    state = AnalysisSessionState("session-a")
    state.tool_receipts = [_receipt("tr1", {"value": 10}, identity="v2")]
    packet = build_publication_packet(state, user_input="分析value", substantive_tools={"run_python"})
    assert packet["session_id"] == "session-a"
    assert packet["sources"][0]["data_identities"]["orders"]["version_id"] == "v2"


def test_ac04_reply_projection_keeps_exact_publication_binding():
    messages = [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1", "publication_packet_id": "ps1", "answer_sha256": "sha256:a1"},
        {"role": "user", "content": "q2"},
        {"role": "assistant", "content": "a2", "publication_packet_id": "ps2", "answer_sha256": "sha256:a2"},
    ]
    replies = assistant_replies(messages, "session")
    assert [(item["publication_packet_id"], item["answer_sha256"]) for item in replies] == [
        ("ps1", "sha256:a1"), ("ps2", "sha256:a2")
    ]


def test_ac04_same_snapshot_answer_is_idempotent_and_revision_gets_new_binding(monkeypatch):
    loop = AgentLoop(client=None, session_id="binding_revision")
    packet = {"id": "ps_snapshot", "status": "ready", "snapshot_digest": "sha256:snapshot", "sources": []}
    monkeypatch.setattr(loop, "_register_publication_receipt_artifact", lambda packet, state: None)
    first = loop._commit_publication_packet(packet, "answer one")
    repeat = loop._commit_publication_packet(packet, "answer one")
    revised = loop._commit_publication_packet(packet, "answer two")
    assert first["id"] == repeat["id"]
    assert revised["id"] != first["id"]
    assert revised["content_revision"] == 2
    assert revised["supersedes_packet_id"] == first["id"]


def test_ac05_artifact_write_failure_does_not_commit_packet(monkeypatch):
    loop = AgentLoop(client=None, session_id="artifact_failure")
    packet = {"id": "ps_fail", "status": "ready", "snapshot_digest": "sha256:packet", "sources": []}

    def fail(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("data_agent.tools.report._write_report_artifact", fail)
    with pytest.raises(OSError, match="disk full"):
        loop._commit_publication_packet(packet, "answer")
    assert loop.context.analysis_state.publication_packets == []


def test_ac05_session_save_failure_rolls_back_public_reply_and_packet(monkeypatch):
    loop = AgentLoop(client=None, session_id="save_failure")
    loop._turn_publication_packet = {
        "id": "ps_save_fail",
        "status": "ready",
        "snapshot_digest": "sha256:packet",
        "sources": [],
    }
    monkeypatch.setattr(loop, "_register_publication_receipt_artifact", lambda packet, state: None)
    monkeypatch.setattr(loop, "_auto_save", lambda: (_ for _ in ()).throw(OSError("save failed")))

    assistant = {"role": "assistant", "content": "answer"}
    failure = loop._persist_accepted_answer(assistant, "answer")

    assert "未发布完整成功结果" in failure
    assert assistant not in loop.messages
    assert loop.context.analysis_state.publication_packets == []


def test_ac06_rejected_candidate_never_enters_public_projection():
    messages = [
        {"role": "user", "content": "question"},
        {"role": "assistant", "content": "bad candidate", "publication_rejected": True},
        {"role": "assistant", "content": "accepted"},
    ]
    projected = public_messages(messages, "session")
    assert [item.get("content") for item in projected] == ["question", "accepted"]


def test_ac10_fact_groups_remain_whole_and_naturally_ordered():
    data = {"groups": [{"name": f"segment_{i}", "count": i * 10, "revenue": i * 100} for i in range(12)]}
    state = AnalysisSessionState("groups")
    state.tool_receipts = [_receipt("tr_groups", data)]
    packet = build_publication_packet(state, user_input="逐一列出全部分组", substantive_tools={"run_python"})
    groups = packet["sources"][0]["fact_groups"]
    assert [group["source_path"] for group in groups] == [f"groups[{i}]" for i in range(12)]
    assert all({field["key"] for field in group["fields"]} == {"name", "count", "revenue"} for group in groups)
    assert packet["coverage"] == []


def test_ac12_scan_limit_is_disclosed_and_detail_ref_closes_omission():
    detail = {"path": "tool_outputs/tr_big_detail.json", "sha256": "sha256:detail"}
    result = extract_publication_fact_groups(
        {"groups": [{"name": f"g{i}", "value": i} for i in range(150)]},
        receipt_id="tr_big",
        detail_ref=detail,
    )
    assert result["scan"]["scan_incomplete"] is True
    assert result["scan"]["omitted_count"] == 50
    assert all(group["detail_ref"] == detail for group in result["groups"])


def test_ac13_detail_reader_checks_session_path_hash_and_missing_file(tmp_path, monkeypatch):
    from data_agent.config import get_config

    cfg = get_config()
    old = cfg.sessions_dir
    cfg.sessions_dir = tmp_path / "sessions"
    try:
        path = cfg.sessions_dir / "s1" / "tool_outputs" / "detail.json"
        path.parent.mkdir(parents=True)
        path.write_text('{"value": 10}', encoding="utf-8")
        digest = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        good = read_publication_detail("s1", {"path": "tool_outputs/detail.json", "sha256": digest})
        bad_hash = read_publication_detail("s1", {"path": "tool_outputs/detail.json", "sha256": "sha256:bad"})
        missing = read_publication_detail("s1", {"path": "tool_outputs/missing.json", "sha256": digest})
        escaped = read_publication_detail("s1", {"path": "../s2/tool_outputs/detail.json", "sha256": digest})
        assert good == {"status": "available", "data": {"value": 10}}
        assert bad_hash["status"] == "invalid"
        assert missing["status"] == "unavailable"
        assert escaped["status"] == "invalid"
    finally:
        cfg.sessions_dir = old


def test_ac14_compaction_appendix_preserves_publication_and_detail_refs():
    messages = [
        {"role": "user", "content": "必须回答收入与复购率"},
        {
            "role": "assistant", "content": "answer", "publication_packet_id": "ps1",
            "publication_snapshot_digest": "sha256:s1", "publication_artifact_path": "sessions/s/reports/p.md",
        },
        {"role": "tool", "content": "[detail: tool_outputs/result_detail.json]"},
    ]
    appendix = _preserved_identity_and_obligations(messages)
    assert "必须回答收入与复购率" in appendix
    assert "publication_packet_id=ps1" in appendix
    assert "detail_ref=tool_outputs/result_detail.json" in appendix


def test_ac36_new_requirement_fields_round_trip_without_rewriting_legacy(tmp_path):
    from data_agent.config import get_config

    cfg = get_config()
    old = cfg.sessions_dir
    cfg.sessions_dir = tmp_path / "sessions"
    try:
        state = AnalysisSessionState("roundtrip")
        state.answer_requirements = [{"id": "rq1", "label": "收入", "lifecycle_status": "active"}]
        state.requirement_revision = 3
        state.save()
        restored = load_analysis_state("roundtrip")
        assert restored.answer_requirements == state.answer_requirements
        assert restored.requirement_revision == 3
        legacy = AnalysisSessionState.from_dict({"schema_version": "legacy"}, "old")
        assert legacy.answer_requirements == [] and legacy.requirement_revision == 0
    finally:
        cfg.sessions_dir = old


def test_ac38_small_medium_large_fixtures_stay_bounded_without_provider_calls():
    manifest = json.loads((__import__("pathlib").Path(__file__).parent / "fixtures/answer_content/manifest.json").read_text(encoding="utf-8"))
    for case in manifest["cases"]:
        data = {
            "groups": [
                {"name": f"segment_{index}", "count": index * 10, "revenue": index * 100}
                for index in range(case["group_count"])
            ]
        }
        grouped = extract_publication_fact_groups(data, receipt_id=f"tr_{case['id']}")
        assert grouped["scan"]["scan_incomplete"] is case["expect_scan_incomplete"]
        state = AnalysisSessionState(case["id"])
        state.tool_receipts = [_receipt(f"tr_{case['id']}", data)]
        packet = build_publication_packet(
            state, user_input="逐一列出全部分组", substantive_tools={"run_python"},
        )
        assert len(publication_packet_prompt(packet)) <= manifest["prompt_max_chars"]
    assert manifest["provider_calls"] == 0
