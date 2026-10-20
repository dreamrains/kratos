"""Canonical-history and complete-turn compaction contracts.

These tests replay the R4 M03 failure shape without contacting a Provider.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from flask import Flask

from data_agent.agent import compact as compact_module
from data_agent.agent.compact import CompactState, _find_safe_boundary, compact_history
from data_agent.session import history
from data_agent.web.blueprints.commands import commands_bp
from data_agent.web.blueprints.sessions import sessions_bp


def _use_session_root(monkeypatch, tmp_path):
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    monkeypatch.setattr(history, "_sessions_dir", lambda: sessions)
    def scoped_dir(session_id: str, child: str):
        path = sessions / session_id / child
        path.mkdir(parents=True, exist_ok=True)
        return path
    monkeypatch.setattr(
        compact_module,
        "_session_transcripts_dir",
        lambda session_id: scoped_dir(session_id, "transcripts"),
    )
    monkeypatch.setattr(
        compact_module,
        "_session_tool_outputs_dir",
        lambda session_id: scoped_dir(session_id, "tool_outputs"),
    )
    return sessions


def _m03_single_turn_shape() -> list[dict]:
    def assistant_calls(*ids: str) -> dict:
        return {
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "id": call_id,
                "type": "function",
                "function": {"name": "read_data", "arguments": json.dumps({"name": call_id})},
            } for call_id in ids],
        }

    messages: list[dict] = [
        {"role": "user", "content": "compare six uploaded sources"},
        {"role": "system", "content": "upload context"},
        assistant_calls("c0", "c1", "c2", "c3", "c4", "c5"),
        *({"role": "tool", "tool_call_id": f"c{i}", "content": "ok"} for i in range(6)),
        assistant_calls("c6", "c7"),
        {"role": "tool", "tool_call_id": "c6", "content": "ok"},
        {"role": "tool", "tool_call_id": "c7", "content": "ok"},
    ]
    for index in range(8, 14):
        messages.extend([
            assistant_calls(f"c{index}"),
            {"role": "tool", "tool_call_id": f"c{index}", "content": "ok"},
        ])
    messages.extend([
        {"role": "system", "content": "publication packet"},
        {"role": "system", "content": "publication policy"},
        {"role": "assistant", "content": "final answer with 210 -> 231"},
    ])
    assert len(messages) == 27
    return messages


def test_r4_m03_single_turn_is_not_split_into_false_early_summary(tmp_path, monkeypatch):
    sessions = _use_session_root(monkeypatch, tmp_path)
    messages = _m03_single_turn_shape()

    assert _find_safe_boundary(messages, keep_recent=10) == 0

    client = MagicMock()
    state = CompactState()
    result = compact_history("m03", client, messages, state, token_threshold=0)

    assert result == messages
    assert state.has_compacted is False
    client.chat.assert_not_called()
    meta_paths = list((sessions / "m03" / "transcripts").glob("*.meta.json"))
    assert len(meta_paths) == 1
    transcript_meta = json.loads(meta_paths[0].read_text(encoding="utf-8"))
    assert transcript_meta["message_count"] == 27
    assert transcript_meta["split_index"] == 0


def test_complete_previous_turn_is_the_only_compaction_unit():
    messages = [
        {"role": "user", "content": "first request"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "a", "function": {"name": "read", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "a", "content": "result"},
        {"role": "assistant", "content": "first final"},
        {"role": "user", "content": "second request"},
        {"role": "assistant", "content": "second final"},
    ]

    assert _find_safe_boundary(messages, keep_recent=2) == 4


def test_canonical_snapshot_merges_json_and_jsonl_deterministically(tmp_path, monkeypatch):
    sessions = _use_session_root(monkeypatch, tmp_path)
    sdir = sessions / "s1"
    sdir.mkdir()
    base = [{"role": "user", "content": "one"}]
    tail = {"role": "assistant", "content": "two"}
    (sdir / "conversation.json").write_text(json.dumps(base), encoding="utf-8")
    (sdir / "conversation.jsonl").write_text(json.dumps(tail) + "\n", encoding="utf-8")
    (sdir / "meta.json").write_text(json.dumps({"history_revision": 7}), encoding="utf-8")

    first = history.load_canonical_history("s1")
    second = history.load_canonical_history("s1")

    assert first.messages == base + [tail]
    assert first.revision == 7
    assert first.message_count == 2
    assert first.sha256 == second.sha256


def test_canonical_hash_detects_same_length_content_change(tmp_path, monkeypatch):
    sessions = _use_session_root(monkeypatch, tmp_path)
    sdir = sessions / "s2"
    sdir.mkdir()
    path = sdir / "conversation.json"
    path.write_text(json.dumps([{"role": "user", "content": "left"}]), encoding="utf-8")
    before = history.load_canonical_history("s2")
    path.write_text(json.dumps([{"role": "user", "content": "right"}]), encoding="utf-8")
    after = history.load_canonical_history("s2")

    assert before.message_count == after.message_count == 1
    assert before.sha256 != after.sha256


def test_jsonl_append_changes_hash_and_next_save_advances_revision(tmp_path, monkeypatch):
    _use_session_root(monkeypatch, tmp_path)
    original = [{"role": "user", "content": "one"}]
    history.save_session(original, "s-append")
    before = history.load_canonical_history("s-append")
    tail = {"role": "assistant", "content": "two"}
    history.push_message("s-append", tail)
    appended = history.load_canonical_history("s-append")

    assert appended.revision == before.revision + 1
    assert appended.sha256 != before.sha256
    history.save_session(original + [tail], "s-append")
    saved = history.load_canonical_history("s-append")
    assert saved.revision >= appended.revision
    assert saved.message_count == appended.message_count == 2
    assert saved.messages[1]["content"] == "two"


def test_compaction_write_uses_revision_and_hash_cas(tmp_path, monkeypatch):
    _use_session_root(monkeypatch, tmp_path)
    history.save_session([{"role": "user", "content": "original"}], "s3")
    snapshot = history.load_canonical_history("s3")

    history.save_session([{"role": "user", "content": "concurrent"}], "s3", merge_protect=False)

    with pytest.raises(history.CanonicalHistoryConflict):
        history.save_session(
            [{"role": "user", "content": "stale compacted"}],
            "s3",
            merge_protect=False,
            expected_history_revision=snapshot.revision,
            expected_history_sha256=snapshot.sha256,
        )

    assert history.load_canonical_history("s3").messages == [
        {"role": "user", "content": "concurrent"}
    ]


def test_legacy_session_gets_identity_on_first_safe_write(tmp_path, monkeypatch):
    sessions = _use_session_root(monkeypatch, tmp_path)
    sdir = sessions / "legacy"
    sdir.mkdir()
    messages = [{"role": "user", "content": "legacy"}]
    (sdir / "conversation.json").write_text(json.dumps(messages), encoding="utf-8")
    (sdir / "meta.json").write_text(json.dumps({"session_id": "legacy"}), encoding="utf-8")

    before = history.load_canonical_history("legacy")
    assert before.revision == 0
    history.save_session(messages, "legacy", merge_protect=False)
    after = history.load_canonical_history("legacy")

    assert after.revision == 1
    meta = json.loads((sdir / "meta.json").read_text(encoding="utf-8"))
    assert meta["history_revision"] == after.revision
    assert meta["history_sha256"] == after.sha256


def _multi_turn_messages() -> list[dict]:
    messages = []
    for index in range(8):
        messages.extend([
            {"role": "user", "content": f"question {index}"},
            {"role": "assistant", "content": f"answer {index}"},
        ])
    return messages


def _compact_app(loop):
    app = Flask(__name__)
    app.config["agent_manager"] = SimpleNamespace(get=lambda session_id: loop)
    app.register_blueprint(commands_bp, url_prefix="/api")
    return app


def _sessions_app(loop):
    app = Flask(__name__)
    app.config["agent_manager"] = SimpleNamespace(get=lambda session_id: loop)
    app.register_blueprint(sessions_bp, url_prefix="/api")
    return app


def _loop(messages, client):
    return SimpleNamespace(
        messages=list(messages),
        client=client,
        _compact_state=CompactState(),
        _last_data_file="",
        _last_jsonl_idx=len(messages),
        _build_session_meta=lambda: {},
        invalidate_prompt_cache=MagicMock(),
    )


def test_web_compact_reads_canonical_snapshot_not_stale_cache(tmp_path, monkeypatch):
    _use_session_root(monkeypatch, tmp_path)
    messages = _multi_turn_messages()
    history.save_session(messages, "web")
    client = MagicMock()
    client.chat.return_value = SimpleNamespace(text="earlier answers are complete")
    loop = _loop([{"role": "user", "content": "stale cache"}], client)

    response = _compact_app(loop).test_client().post("/api/compact", json={"session_id": "web"})

    assert response.status_code == 200
    written = history.load_canonical_history("web")
    assert loop.messages == written.messages
    assert loop._compact_state.has_compacted is True
    assert "question 0" in client.chat.call_args.kwargs["messages"][0]["content"]
    assert response.get_json()["history_revision"] == written.revision


def test_web_compact_cas_conflict_preserves_new_message_and_cache_state(tmp_path, monkeypatch):
    _use_session_root(monkeypatch, tmp_path)
    messages = _multi_turn_messages()
    history.save_session(messages, "conflict")
    snapshot = history.load_canonical_history("conflict")

    client = MagicMock()
    def concurrent_append(**kwargs):
        history.save_session(
            snapshot.messages + [{"role": "user", "content": "arrived during summary"}],
            "conflict",
            merge_protect=False,
        )
        return SimpleNamespace(text="summary")
    client.chat.side_effect = concurrent_append
    loop = _loop(snapshot.messages, client)

    response = _compact_app(loop).test_client().post("/api/compact", json={"session_id": "conflict"})

    assert response.status_code == 409
    assert response.get_json()["error"] == "canonical_history_conflict"
    assert loop._compact_state.has_compacted is False
    assert loop.messages == snapshot.messages
    assert history.load_canonical_history("conflict").messages[-1]["content"] == "arrived during summary"
    loop.invalidate_prompt_cache.assert_not_called()


@pytest.mark.parametrize("publication_schema", ["", "answer_bindings.v2"])
def test_rewind_uses_canonical_snapshot_and_advances_identity(tmp_path, monkeypatch, publication_schema):
    _use_session_root(monkeypatch, tmp_path)
    messages = [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "first answer"},
        {"role": "user", "content": "second"},
        {"role": "assistant", "content": "second answer"},
    ]
    history.save_session(messages, "rewind", extra_meta={"publication_schema": publication_schema})
    before = history.load_canonical_history("rewind")
    loop = _loop([{"role": "user", "content": "stale cache"}], MagicMock())

    response = _sessions_app(loop).test_client().post(
        "/api/sessions/rewind/rewind",
        json={"round": 2},
    )

    assert response.status_code == 200
    written = history.load_canonical_history("rewind")
    assert written.revision > before.revision
    assert history.load_session("rewind")["publication_schema"] == publication_schema
    assert [item["content"] for item in written.messages] == ["first", "first answer"]
    assert loop.messages == written.messages
    assert loop._last_jsonl_idx == 2
    loop.invalidate_prompt_cache.assert_called_once()


def test_long_complete_analysis_then_short_followup_is_actually_compacted(tmp_path, monkeypatch):
    sessions = _use_session_root(monkeypatch, tmp_path)
    messages = _m03_single_turn_shape() + [
        {"role": "user", "content": "好的，继续。"},
        {"role": "assistant", "content": "six sources remain independently available"},
    ]
    client = MagicMock()
    client.chat.return_value = SimpleNamespace(text="read_data 已执行，六个来源仍分别保留。")
    state = CompactState()
    compacted = compact_history("two-turns", client, messages, state, token_threshold=0)
    assert state.has_compacted and len(compacted) == 4
    assert compacted[2:] == messages[-2:]
    assert "read_data" in compacted[0]["content"]
    archive = next((sessions / "two-turns" / "transcripts").glob("*.jsonl"))
    assert [json.loads(line) for line in archive.read_text("utf-8").splitlines()] == messages
    meta = json.loads(archive.with_suffix(".meta.json").read_text("utf-8"))
    assert meta["split_index"] == 27 and meta["recent_message_count"] == 2


@pytest.mark.parametrize("changed_field", ["reply_id", "tool_preview"])
def test_repeated_compaction_preserves_each_original_turn_once(tmp_path, monkeypatch, changed_field):
    """Retained messages may change without becoming another original turn."""
    from copy import deepcopy
    from data_agent.session.public_messages import public_messages

    _use_session_root(monkeypatch, tmp_path)
    client = MagicMock()
    client.chat.return_value = SimpleNamespace(text="read_data executed: 12 observations")
    state = CompactState()

    def pair(value):
        # Reuse across closed blocks is legal; it must not be global-deduped.
        return [
            {"role": "assistant", "content": "", "reply_id": "before",
             "tool_calls": [{"id": "reusable", "type": "function",
                             "function": {"name": "read_data", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "reusable", "content": value},
        ]

    messages = [{"role": "user", "request_id": "request_first", "content": "same original question"}]
    for i in range(5):
        messages.extend(pair(f"first result {i}"))
    messages.append({"role": "assistant", "content": "first accepted original", "answer_id": "answer_first"})
    messages.append({"role": "user", "request_id": "request_second", "content": "same original question"})
    for i in range(5):
        messages.extend(pair(f"second result {i}"))
    for generation in range(3):
        messages = compact_history("repeated", client, messages, state, token_threshold=0)
        for message in messages[2:]:
            if changed_field == "reply_id" and message.get("role") == "assistant":
                message["reply_id"] = f"after_{generation}"
            elif changed_field == "tool_preview" and message.get("role") == "tool":
                message["content"] = f"[Compacted: result_{generation}.txt]"
        messages.extend(pair(f"new result {generation}"))
    messages.append({"role": "assistant", "content": "second accepted original", "answer_id": "answer_second"})
    before = deepcopy(messages)

    public = public_messages(messages, "repeated")

    assert messages == before  # Expansion is read-only.
    assert [m["request_id"] for m in public if m.get("role") == "user"] == ["request_first", "request_second"]
    assert [m["answer_id"] for m in public if m.get("answer_id")] == ["answer_first", "answer_second"]
    assert [m["content"] for m in public if m.get("answer_id")] == ["first accepted original", "second accepted original"]
    assert len([m for m in public if m.get("role") == "tool"]) == 13


@pytest.mark.parametrize("fault", [None, "legacy", "range", "prefix_sha", "unknown", "legacy_unknown", "cycle"])
def test_archive_prefix_requires_verified_codec_and_complete_range(tmp_path, monkeypatch, fault):
    from copy import deepcopy
    from data_agent.session.public_messages import public_messages

    sessions = _use_session_root(monkeypatch, tmp_path)
    original = _m03_single_turn_shape() + [
        {"role": "user", "content": "followup", "request_id": "last"},
        {"role": "assistant", "content": "last answer"},
    ]
    client = MagicMock()
    client.chat.return_value = SimpleNamespace(text="read_data executed")
    compacted = compact_history("prefix", client, original, CompactState())
    ref = compacted[0]["canonical_transcript"]
    archive = sessions / "prefix" / "transcripts" / ref["filename"]
    before = archive.read_bytes()
    if fault in {"legacy", "legacy_unknown"}:
        ref.pop("early_range")
        # An unsigned sidecar cannot select a different early range.
        archive.with_suffix(".meta.json").write_text('{"split_index":1}', encoding="utf-8")
        if fault == "legacy_unknown": compacted[0]["content"] = "unknown codec"
    if fault == "range": ref["early_range"]["stop"] = True
    if fault == "prefix_sha": ref["early_range"]["sha256"] = "sha256:" + "0" * 64
    if fault == "unknown": ref["early_range"]["schema"] = "unknown"
    if fault == "cycle":
        monkeypatch.setattr(history, "read_canonical_prefix", lambda *a: [deepcopy(compacted[0])])
    public = public_messages(compacted, "prefix")
    assert archive.read_bytes() == before
    if fault in {None, "legacy"}:
        assert [m["content"] for m in public] == [m["content"] for m in original]
    else:
        assert any("历史归档不可核" in m.get("content", "") for m in public)
    assert [m.get("request_id") for m in public if m.get("request_id")] == ["last"]
