"""Deterministic contracts for the actual-browser SSE acceptance fixture.

These tests prepare Gate E but never execute or satisfy it.  A PASS browser
receipt still requires observations made by the in-app browser in Task 4.
"""

from __future__ import annotations

import hashlib
import io
import json
import subprocess
import threading
from pathlib import Path

import pytest

from scripts.acceptance.browser_gate_contract import (
    validate_browser_gate_receipt,
    write_browser_gate_receipt,
)
from scripts.acceptance.release_source import release_source_digest
from scripts.acceptance.run_web_sse_fixture import (
    BROWSER_FINAL_DRAFT,
    BROWSER_NORMAL_PROMPT,
    CONFIRMATION_ID,
    CONFIRMATION_VERSION,
    ERROR_PROMPT,
    SUSPEND_PROMPT,
    DelayedAuditedLoop,
    ScriptedManager,
    ScriptedProvider,
    build_fixture_app,
    make_observed_event_queue,
    shutdown_fixture_app,
    split_audited_fixture_text,
    write_browser_fixture_csv,
)


EXPECTED_DIGEST = "sha256:" + "a" * 64


def _valid_observation() -> dict:
    return {
        "contract_version": "analysis_browser_gate.v1",
        "status": "PASS",
        "observer": "in_app_browser",
        "fixture_id": "web_sse_fixture_v1",
        "source_digest": EXPECTED_DIGEST,
        "source_commit": "a" * 40,
        "url": "http://127.0.0.1:5013",
        "observations": [
            {
                "name": "upload_starts_analysis",
                "observed_text": "browser_fixture.csv",
                "browser_ms": 40,
                "server_event_ms": 0,
                "turn_end_browser_ms": 900,
            },
            {
                "name": "progress_before_answer",
                "observed_text": "正在分析字段质量",
                "browser_ms": 100,
                "server_event_ms": 80,
                "turn_end_browser_ms": 900,
            },
            {
                "name": "first_chunk_before_second",
                "observed_text": "第一段",
                "browser_ms": 350,
                "server_event_ms": 300,
                "turn_end_browser_ms": 900,
            },
            {
                "name": "complete_answer_before_turn_end",
                "observed_text": "第一段第二段",
                "browser_ms": 700,
                "server_event_ms": 650,
                "turn_end_browser_ms": 900,
            },
            {
                "name": "persisted_after_refresh",
                "observed_text": "第一段第二段",
                "browser_ms": 1200,
                "server_event_ms": 900,
                "turn_end_browser_ms": 900,
            },
            {
                "name": "markdown_table_and_limitation_rendered",
                "observed_text": "局限",
                "browser_ms": 750,
                "server_event_ms": 650,
                "turn_end_browser_ms": 900,
            },
            {
                "name": "retained_after_session_switch",
                "observed_text": "第一段第二段",
                "browser_ms": 1400,
                "server_event_ms": 900,
                "turn_end_browser_ms": 900,
            },
            {
                "name": "suspend_resume_nonblank",
                "observed_text": "恢复后内容",
                "browser_ms": 1600,
                "server_event_ms": 1500,
                "turn_end_browser_ms": 1550,
            },
            {
                "name": "interruption_nonblank",
                "observed_text": "已中断验收",
                "browser_ms": 1800,
                "server_event_ms": 1750,
                "turn_end_browser_ms": 1760,
            },
            {
                "name": "error_nonblank",
                "observed_text": "synthetic_acceptance_error",
                "browser_ms": 2000,
                "server_event_ms": 1950,
                "turn_end_browser_ms": 1960,
            },
        ],
    }


def test_browser_receipt_accepts_complete_actual_browser_observation():
    result = validate_browser_gate_receipt(
        _valid_observation(),
        expected_source_digest=EXPECTED_DIGEST,
    )
    assert result.status == "PASS"
    assert result.reason_codes == ()


def test_browser_receipt_requires_all_dom_observations():
    receipt = _valid_observation()
    receipt["observations"] = receipt["observations"][:2]
    result = validate_browser_gate_receipt(
        receipt,
        expected_source_digest=EXPECTED_DIGEST,
    )
    assert result.status == "FAIL"
    assert "missing_browser_observations" in result.reason_codes


@pytest.mark.parametrize(
    "name",
    [
        "progress_before_answer",
        "first_chunk_before_second",
        "complete_answer_before_turn_end",
    ],
)
def test_browser_receipt_rejects_post_turn_end_only_observation(name):
    receipt = _valid_observation()
    item = next(item for item in receipt["observations"] if item["name"] == name)
    item["browser_ms"] = item["turn_end_browser_ms"]
    result = validate_browser_gate_receipt(
        receipt,
        expected_source_digest=EXPECTED_DIGEST,
    )
    assert result.status == "FAIL"
    assert "not_observed_before_turn_end" in result.reason_codes


def test_raw_sse_transcript_cannot_satisfy_browser_receipt():
    receipt = _valid_observation()
    receipt["observer"] = "raw_http"
    result = validate_browser_gate_receipt(
        receipt,
        expected_source_digest=EXPECTED_DIGEST,
    )
    assert result.status == "FAIL"
    assert "invalid_browser_observer" in result.reason_codes


def test_browser_receipt_rejects_stale_source_or_malformed_timing():
    stale = validate_browser_gate_receipt(
        _valid_observation(),
        expected_source_digest="sha256:" + "b" * 64,
    )
    assert stale.status == "FAIL"
    assert "stale_browser_receipt" in stale.reason_codes

    malformed = _valid_observation()
    malformed["observations"][1]["browser_ms"] = True
    result = validate_browser_gate_receipt(
        malformed,
        expected_source_digest=EXPECTED_DIGEST,
    )
    assert result.status == "FAIL"
    assert "invalid_browser_timing" in result.reason_codes


def test_browser_receipt_writer_validates_before_atomic_persistence(tmp_path):
    receipt_path = tmp_path / "analysis_browser_gate.v1.json"
    write_browser_gate_receipt(
        receipt_path,
        _valid_observation(),
        expected_source_digest=EXPECTED_DIGEST,
    )
    assert json.loads(receipt_path.read_text(encoding="utf-8")) == _valid_observation()

    unsafe = _valid_observation()
    unsafe["prompt"] = "customer@example.com asked for the complete answer"
    with pytest.raises(ValueError, match="unsafe_browser_receipt_field"):
        write_browser_gate_receipt(
            receipt_path,
            unsafe,
            expected_source_digest=EXPECTED_DIGEST,
        )
    assert json.loads(receipt_path.read_text(encoding="utf-8")) == _valid_observation()


def test_browser_receipt_writer_rejects_unknown_observation_payload(tmp_path):
    receipt = _valid_observation()
    receipt["observations"].append(
        {
            "name": "complete_production_answer",
            "observed_text": "Customer alice@example.com requested the raw answer.",
            "browser_ms": 2100,
            "server_event_ms": 2050,
            "turn_end_browser_ms": 2060,
        }
    )
    with pytest.raises(ValueError, match="unsafe_browser_observation_name"):
        write_browser_gate_receipt(
            tmp_path / "analysis_browser_gate.v1.json",
            receipt,
            expected_source_digest=EXPECTED_DIGEST,
        )


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _make_digest_repo(tmp_path: Path) -> tuple[Path, list[str]]:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init")
    files = {
        "pyproject.toml": b"[project]\nname='fixture'\n",
        "src/pkg.py": b"VALUE = 1\n",
        "scripts/check.py": b"print('check')\n",
        "tests/test_pkg.py": b"def test_value(): assert 1\n",
        "docs/notes.md": b"documentation v1\n",
    }
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    _git(root, "add", ".")
    return root, sorted(relative for relative in files if not relative.startswith("docs/"))


def test_release_source_digest_hashes_exact_selected_paths_and_bytes(tmp_path):
    root, selected = _make_digest_repo(tmp_path)
    expected = hashlib.sha256()
    for relative in selected:
        expected.update(relative.encode("utf-8"))
        expected.update(b"\0")
        expected.update((root / relative).read_bytes())

    digest = release_source_digest(root)
    assert digest == f"sha256:{expected.hexdigest()}"


def test_release_source_digest_changes_for_source_but_not_docs_or_receipts(tmp_path):
    root, _selected = _make_digest_repo(tmp_path)
    baseline = release_source_digest(root)

    source = root / "src/pkg.py"
    source.write_bytes(b"VALUE = 2\n")
    assert release_source_digest(root) != baseline
    source.write_bytes(b"VALUE = 1\n")
    assert release_source_digest(root) == baseline

    (root / "docs/notes.md").write_bytes(b"documentation v2\n")
    assert release_source_digest(root) == baseline

    generated = root / "scripts/acceptance/generated/analysis_browser_gate.v1.json"
    generated.parent.mkdir(parents=True)
    generated.write_text('{"status":"PASS"}', encoding="utf-8")
    assert release_source_digest(root) == baseline


def test_audited_fixture_text_is_split_without_substitution():
    chunks = split_audited_fixture_text(BROWSER_FINAL_DRAFT)
    assert len(chunks) == 3
    assert all(chunks)
    assert "".join(chunks) == BROWSER_FINAL_DRAFT
    assert "第一段" in chunks[0]
    assert "第二段" not in chunks[0]
    assert chunks[1].startswith("第二段")

    with pytest.raises(AssertionError, match="missing audited fixture anchor"):
        split_audited_fixture_text("# 分析结果\n\n第一段")


def test_scripted_provider_drives_exact_real_analysis_tool_sequence(tmp_path):
    from data_agent.llm.client import StreamComplete

    provider = ScriptedProvider(tmp_path / "browser_fixture.csv")
    responses = []
    for _ in range(5):
        events = list(provider.stream_chat_structured([], tools=[], system=""))
        responses.append(
            next(event.response for event in events if isinstance(event, StreamComplete))
        )

    assert [
        response.tool_calls[0].name if response.tool_calls else "synthesis"
        for response in responses
    ] == [
        "load_data",
        "quick_profile",
        "correlation_analysis",
        "factor_relationship_analysis",
        "synthesis",
    ]
    assert responses[0].tool_calls[0].arguments == {
        "source": str(tmp_path / "browser_fixture.csv"),
        "name": "browser_fixture",
    }
    assert responses[-1].text == BROWSER_FINAL_DRAFT


class _AuditedInner:
    session_id = "fixture_inner"

    def __init__(self):
        self.messages = []
        self.saved = 0

    def stream_turn(self, message):
        self.messages.append({"role": "user", "content": message})
        yield {
            "type": "analysis_progress",
            "code": "analysis_plan_ready",
            "label": "分析方案已准备",
            "status": "completed",
        }
        yield {"type": "text_delta", "text": BROWSER_FINAL_DRAFT[:23]}
        yield {"type": "text_delta", "text": BROWSER_FINAL_DRAFT[23:]}
        self.messages.append({"role": "assistant", "content": BROWSER_FINAL_DRAFT})

    def _auto_save(self):
        self.saved += 1


def test_delayed_loop_forwards_progress_then_exactly_three_audited_chunks():
    loop = DelayedAuditedLoop(_AuditedInner())
    events = list(loop.stream_turn(BROWSER_NORMAL_PROMPT))
    assert events[0]["type"] == "analysis_progress"
    deltas = [event["text"] for event in events if event["type"] == "text_delta"]
    assert len(deltas) == 3
    assert "".join(deltas) == BROWSER_FINAL_DRAFT
    assert "第二段" not in deltas[0]
    assert deltas[1].startswith("第二段")


def test_control_paths_suspend_resume_and_error_without_blank_turn():
    inner = _AuditedInner()
    loop = DelayedAuditedLoop(inner)
    suspended = list(loop.stream_turn(SUSPEND_PROMPT))
    assert len(suspended) == 1
    assert suspended[0]["type"] == "suspended"
    assert suspended[0]["confirmation_id"] == CONFIRMATION_ID
    assert suspended[0]["version"] == CONFIRMATION_VERSION

    with pytest.raises(ValueError, match="identity or version"):
        list(
            loop.resume_turn_streaming(
                CONFIRMATION_ID,
                "继续",
                expected_version=CONFIRMATION_VERSION + 1,
                idempotency_key="fixture-resume",
            )
        )

    resumed = list(
        loop.resume_turn_streaming(
            CONFIRMATION_ID,
            "继续",
            expected_version=CONFIRMATION_VERSION,
            idempotency_key="fixture-resume",
        )
    )
    assert resumed == [{"type": "text_delta", "text": "恢复后内容"}]
    assert inner.messages[-1] == {"role": "assistant", "content": "恢复后内容"}
    assert inner.saved == 1

    with pytest.raises(RuntimeError, match="synthetic_acceptance_error"):
        list(loop.stream_turn(ERROR_PROMPT))


def test_delayed_loop_interrupts_during_chunk_delay_with_nonblank_error():
    loop = DelayedAuditedLoop(_AuditedInner())
    stream = loop.stream_turn(BROWSER_NORMAL_PROMPT)
    assert next(stream)["type"] == "analysis_progress"
    interrupt = threading.Timer(0.05, loop.request_interrupt)
    interrupt.start()
    try:
        assert next(stream) == {"type": "error", "message": "已中断验收"}
        with pytest.raises(StopIteration):
            next(stream)
    finally:
        interrupt.cancel()


def test_observed_event_queue_records_only_event_timing_and_session(tmp_path):
    from data_agent.web.event_bus import SSEEvent

    trace_path = tmp_path / "events.jsonl"
    QueueClass = make_observed_event_queue(
        trace_path,
        started_ns=1_000_000,
        monotonic_ns=lambda: 3_500_000,
    )
    queue = QueueClass()
    queue.put(
        SSEEvent(
            "text_delta",
            {
                "session_id": "fixture_session",
                "text": "complete private answer",
                "prompt": "private prompt",
            },
        )
    )
    record = json.loads(trace_path.read_text(encoding="utf-8"))
    assert record == {
        "event": "text_delta",
        "monotonic_ms": 2,
        "session_id": "fixture_session",
    }
    assert "complete private answer" not in trace_path.read_text(encoding="utf-8")


def test_fixture_app_uses_real_page_routes_and_isolated_roots(tmp_path, monkeypatch):
    import data_agent.config
    from data_agent.agent import llm_intent
    from data_agent.web.blueprints import chat as chat_blueprint

    monkeypatch.setenv("MCP_ENABLED", "false")
    monkeypatch.setenv("SKILL_AUTO_DISCOVER", "false")
    monkeypatch.setattr(data_agent.config, "_config", None)
    previous_intent_client = object()
    monkeypatch.setattr(llm_intent, "_client", previous_intent_client)
    previous_event_queue = chat_blueprint.EventQueue
    fixture_csv = write_browser_fixture_csv(tmp_path)
    app = build_fixture_app(tmp_path)
    app.testing = True
    try:
        assert llm_intent._client is not previous_intent_client
        assert fixture_csv == tmp_path / "browser_fixture.csv"
        rows = fixture_csv.read_text(encoding="utf-8-sig").splitlines()
        assert rows[0] == "日期,收入,成本,渠道"
        assert len(rows) == 121
        assert isinstance(app.config["agent_manager"], ScriptedManager)
        assert Path(app.config["fixture_event_trace"]).parent == tmp_path

        rules = {rule.rule for rule in app.url_map.iter_rules()}
        assert "/" in rules
        assert "/api/chat" in rules
        assert app.test_client().get("/").status_code == 200

        upload = app.test_client().post(
            "/api/upload",
            data={"file": (io.BytesIO(fixture_csv.read_bytes()), "browser_fixture.csv")},
            content_type="multipart/form-data",
        )
        assert upload.status_code == 200
        assert upload.get_json()["filename"] == "browser_fixture.csv"

        loop = app.config["agent_manager"].get_or_create(session_id="fixture_contract")
        from data_agent.agent.loop import AgentLoop

        assert isinstance(loop.inner, AgentLoop)
        assert loop.session_id == "fixture_contract"
        assert loop.inner.client.fixture_source.name == "browser_fixture.csv"
        assert BROWSER_NORMAL_PROMPT == "运行流式显示验收"
    finally:
        shutdown_fixture_app(app)
    assert llm_intent._client is previous_intent_client
    assert chat_blueprint.EventQueue is previous_event_queue
    assert data_agent.config._config is None


def _parse_sse(chunks):
    pending = ""
    for chunk in chunks:
        if isinstance(chunk, bytes):
            chunk = chunk.decode("utf-8")
        pending += chunk
        while "\n\n" in pending:
            frame, pending = pending.split("\n\n", 1)
            event_name = ""
            payload = None
            for line in frame.splitlines():
                if line.startswith("event: "):
                    event_name = line.removeprefix("event: ")
                elif line.startswith("data: "):
                    payload = json.loads(line.removeprefix("data: "))
            assert event_name and payload is not None
            yield event_name, payload
    assert not pending


def test_real_chat_route_runs_real_agent_tools_audit_and_sse(
    tmp_path, monkeypatch, request
):
    import data_agent.config
    import data_agent.llm.client

    monkeypatch.setenv("MCP_ENABLED", "false")
    monkeypatch.setenv("SKILL_AUTO_DISCOVER", "false")
    monkeypatch.setattr(data_agent.config, "_config", None)
    monkeypatch.setattr(
        data_agent.llm.client,
        "completion",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("fixture made an unscripted provider call")
        ),
    )
    app = build_fixture_app(tmp_path)
    request.addfinalizer(lambda: shutdown_fixture_app(app))
    app.testing = True
    client = app.test_client()
    fixture_csv = Path(app.config["fixture_csv"])
    upload = client.post(
        "/api/upload",
        data={"file": (io.BytesIO(fixture_csv.read_bytes()), fixture_csv.name)},
        content_type="multipart/form-data",
    )
    assert upload.status_code == 200

    response = client.post(
        "/api/chat",
        json={
            "message": BROWSER_NORMAL_PROMPT,
            "session_id": "fixture_real_path",
        },
        buffered=False,
    )
    events = list(_parse_sse(response.response))
    event_names = [name for name, _payload in events]
    assert response.status_code == 200
    assert event_names[0] == "turn_start"
    assert event_names[-1] == "turn_end"
    assert events[-1][1]["status"] == "completed"
    assert [payload["name"] for name, payload in events if name == "tool_call"] == [
        "load_data",
        "quick_profile",
        "correlation_analysis",
        "factor_relationship_analysis",
    ]
    first_progress = event_names.index("analysis_progress")
    first_text = event_names.index("text_delta")
    assert first_progress < first_text
    assert any(
        name == "analysis_progress" and payload["code"] == "audit_started"
        for name, payload in events
    )
    audit_started = next(
        index
        for index, (name, payload) in enumerate(events)
        if name == "analysis_progress" and payload["code"] == "audit_started"
    )
    assert audit_started < first_text
    deltas = [payload["text"] for name, payload in events if name == "text_delta"]
    assert len(deltas) == 3
    publication = "".join(deltas)
    assert "# 分析结果" in publication
    assert "第一段" in publication
    assert "第二段" in publication
    assert "| 检查项 | 状态 |" in publication
    assert "## 局限" in publication

    loop = app.config["agent_manager"].get("fixture_real_path")
    assert loop is not None
    assert loop.messages[-1]["role"] == "assistant"
    assert loop.messages[-1]["content"] == publication
    assert loop.inner._turn_last_final_audit["status"] == "pass"
    assert loop.inner._turn_last_final_audit["public_text"] == publication
    trace = Path(app.config["fixture_event_trace"]).read_text(encoding="utf-8")
    assert BROWSER_FINAL_DRAFT not in trace
