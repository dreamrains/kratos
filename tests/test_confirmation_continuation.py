import json

import pytest

from data_agent.agent.confirmation.continuation import (
    ContinuationIntegrityError,
    ContinuationRecord,
    ContinuationStatus,
    ContinuationStore,
)


def _continuation(**overrides):
    values = {
        "confirmation_id": "cf_metric_1",
        "session_id": "session_1",
        "turn_id": "turn_1",
        "message_version": 12,
        "completed_tool_call_ids": ("tool_1", "tool_2"),
        "blocked_operation": "period_compare",
        "request_identity": "sha256:request",
        "status": ContinuationStatus.SUSPENDED,
    }
    values.update(overrides)
    return ContinuationRecord(**values)


def test_continuation_round_trip_preserves_completed_tools(tmp_path):
    store = ContinuationStore(tmp_path, "session_1")
    continuation = _continuation()

    store.save(continuation)

    assert store.load("cf_metric_1") == continuation


def test_continuation_rejects_duplicate_completed_tool_ids():
    with pytest.raises(ValueError, match="unique"):
        _continuation(completed_tool_call_ids=("tool_1", "tool_1"))


def test_continuation_detects_payload_tampering(tmp_path):
    store = ContinuationStore(tmp_path, "session_1")
    store.save(_continuation())
    path = store.path_for("cf_metric_1")
    envelope = json.loads(path.read_text(encoding="utf-8"))
    envelope["payload"]["message_version"] = 99
    path.write_text(json.dumps(envelope), encoding="utf-8")

    with pytest.raises(ContinuationIntegrityError, match="checksum"):
        store.load("cf_metric_1")


def test_continuation_rejects_confirmation_id_mismatch(tmp_path):
    store = ContinuationStore(tmp_path, "session_1")
    store.save(_continuation())

    with pytest.raises(ContinuationIntegrityError, match="not found"):
        store.load("cf_other")


def test_store_rejects_continuation_for_another_session(tmp_path):
    store = ContinuationStore(tmp_path, "session_2")

    with pytest.raises(ContinuationIntegrityError, match="session"):
        store.save(_continuation())


def test_continuation_supports_terminal_statuses():
    assert _continuation(status=ContinuationStatus.RESUMED).status == ContinuationStatus.RESUMED
    assert _continuation(status=ContinuationStatus.CANCELLED).status == ContinuationStatus.CANCELLED
    assert _continuation(status=ContinuationStatus.FAILED).status == ContinuationStatus.FAILED


def test_save_fsyncs_and_atomically_replaces_file(tmp_path):
    synced = []
    store = ContinuationStore(
        tmp_path,
        "session_1",
        sync_file=lambda descriptor: synced.append(descriptor),
    )

    store.save(_continuation())

    assert len(synced) == 1
    assert not store.path_for("cf_metric_1").with_suffix(".json.tmp").exists()


from tests.test_trusted_publication_semantics import engine


@pytest.mark.parametrize("streaming", [False, True])
def test_s3_p3_no_record_and_reused_questions_close_original_tool_calls(engine, streaming):
    from collections import Counter
    from tests.test_trusted_publication_runtime import _NativeProductModel
    from data_agent.llm.client import Response
    from data_agent.agent.publication.contracts import encode
    from data_agent.agent.loop import SuspendedForConfirmation
    from data_agent.agent.publication.runtime import read_answer
    from data_agent.session.history import load_session
    from data_agent.tools.report import export_assistant_reply
    loop, cfg = engine
    content = "加载p3.csv并计算orders的amount两期差值，窗口由我选择，不需要批准技术方法。"
    raw = loop.context.workspace.get("orders").to_csv(index=False).encode("utf-8")
    loop.context.workspace.remove("orders")
    source = cfg.workspace_resolved / "inbox" / "p3.csv"
    source.parent.mkdir(parents=True, exist_ok=True); source.write_bytes(raw)
    scope = {"datasets": ["orders"], "metrics": ["amount"], "quantity": "difference"}
    question = {"question": "前后窗口采用9月1至6日和7至12日吗？", "confirmation_type": "time_window", "options": [{"label": "两个六天窗口", "value": "split6"}, {"label": "另定", "value": "custom"}]}
    method = {"question": "是否使用留存方法继续？", "confirmation_type": "method_confirmation", "options": [{"label": "同意", "value": "yes"}]}
    malformed = {"question": "Choose time window", "confirmation_type": "time_window", "options": [{"label": "First", "value": "duplicate"}, {"label": "Second", "value": "duplicate"}]}
    class Model(_NativeProductModel):
        def chat(self, messages, system="", **kwargs):
            if system == "你是一个JSON输出器，只返回JSON，不要其他内容。":
                return Response(text=encode({"intent_type": "directed_analysis", "requested_outputs": [{"kind": "result", "exact_span": content, "business_scope": scope}]}))
            if self.step == 5:
                original = next(m["content"] for m in messages if m.get("role") == "tool" and "Suspended for user confirmation. confirmation_id=" in str(m.get("content")))
                reference = original.partition("confirmation_id=")[2].strip()
                self.preparatory_calls[3] = ("ask_user_question", dict(question, question="换个说法：这次采用哪两个六天窗口？", reuse_decision_id=reference))
            if self.step == 0:
                from data_agent.llm.client import ToolCall
                self.step = 1; self.calls.append("load_data")
                return Response(tool_calls=[ToolCall("native_call_1", "load_data", {"source": str(source), "name": "orders"})])
            return super().chat(messages, system=system, **kwargs)
    args = {"name": "orders", "date_col": "day", "metrics": "amount", "period_a": "2026-09-01~2026-09-06", "period_b": "2026-09-07~2026-09-12"}
    model = Model(content, "orders", "compare_periods", args, [{"kind": "measurement", "scope": scope}], preparatory_calls=[("ask_user_question", method), ("ask_user_question", malformed), ("ask_user_question", question), ("ask_user_question", question)])
    loop.client = model; loop.auxiliary_llm_client = model
    if streaming:
        first = list(loop.stream_turn(content))
        assert len([e for e in first if e["type"] == "suspended"]) == 1 and not [e for e in first if e["type"] == "error"]
        active = loop._confirmation_runtime().checkpoint(loop.session_id)
        final = list(loop.resume_turn_streaming(active.confirmation_id, "split6", expected_version=active.version, idempotency_key="p3_once"))
        assert not [e for e in final if e["type"] in {"error", "suspended"}]
        body = "".join(e["text"] for e in final if e["type"] == "text_delta")
    else:
        first = loop.run_turn_structured(content)
        assert isinstance(first, SuspendedForConfirmation)
        active = loop._confirmation_runtime().checkpoint(loop.session_id)
        body = loop.resume_turn(active.confirmation_id, "split6", expected_version=active.version, idempotency_key="p3_once").content
    stored = load_session(loop.session_id)
    call_ids = [c["id"] for m in stored["messages"] if m["role"] == "assistant" for c in m.get("tool_calls", [])]
    responses = [m["tool_call_id"] for m in stored["messages"] if m["role"] == "tool"]
    assert Counter(call_ids) == Counter(responses) and all(n == 1 for n in Counter(responses).values())
    assert model.calls == ["load_data", "record_analysis_plan"] + ["ask_user_question"] * 4 + ["compare_periods"]
    assert any(m.get("tool_call_id") == "native_call_4" and "option values must be unique" in m.get("content", "") for m in stored["messages"])
    records = loop._confirmation_runtime()._store(loop.session_id).load_records()
    assert len(records) == 1 and next(iter(records.values())).response == "split6"
    last = next(m for m in reversed(stored["messages"]) if m.get("answer_ref"))
    answer = read_answer(loop.session_id, last["answer_ref"])
    assert answer["body"] == last["content"] == body and answer["requirement_outcomes"][0]["status"] == "answered"
    accepted = {t["ref"] for t in answer["render_trace"] if t["kind"] == "claim" and t["disposition"] == "accepted"}
    claims = [c for c in answer["source_snapshot"]["claims"] if c["id"] in accepted]
    assert [(c["label"], c["value"]) for c in claims] == [("amount：差值", 60)]
    export = export_assistant_reply(loop.session_id, body, "md", reply_id=last["reply_id"])
    assert export["status"] == "exported" and body in (cfg.sessions_resolved / loop.session_id / "reports" / export["artifact_path"].split("/")[-1]).read_text(encoding="utf-8")
