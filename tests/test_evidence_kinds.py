import json

from data_agent.knowledge.evidence import EvidenceStore
from data_agent.knowledge.models import EvidenceKind


def test_index_session_extracts_tool_calls_and_user_corrections(tmp_path):
    sessions_dir = tmp_path / "sessions"
    session_dir = sessions_dir / "s1"
    session_dir.mkdir(parents=True)
    (session_dir / "meta.json").write_text(
        json.dumps({"project_name": "ecommerce", "saved_at": "2026-05-23T10:00:00"}, ensure_ascii=False),
        encoding="utf-8",
    )
    (session_dir / "conversation.json").write_text(
        json.dumps(
            [
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {"id": "call_1", "function": {"name": "record_evidence_record", "arguments": "{}"}}
                    ],
                },
                {
                    "role": "tool",
                    "tool_call_id": "call_1",
                    "name": "record_evidence_record",
                    "content": '{"claim":"GMV excludes canceled orders","confidence":0.9}',
                },
                {"role": "user", "content": "纠正一下：GMV 还要排除退款订单"},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    store = EvidenceStore(tmp_path / "knowledge", sessions_dir=sessions_dir)
    assert store.index_session("s1") >= 3

    tool_call = store.get("ev_s1_0")
    assert tool_call is not None
    assert tool_call.kind == EvidenceKind.TOOL_CALL

    records = store.search("GMV", project_id="ecommerce")
    kinds = {record.kind for record in records}

    assert EvidenceKind.ANALYSIS_RESULT in kinds
    assert EvidenceKind.USER_CORRECTION in kinds
