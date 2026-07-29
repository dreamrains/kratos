"""Standalone deterministic server used by the actual-browser Gate E.

The normal success path retains the real page, upload route, ``/api/chat``,
``AgentLoop``, tool execution, audit, publication, and SSE serialization.
Only provider responses, isolated storage roots, event observation, and the
timing of already-audited final text are controlled here.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Iterator, Sequence


FIXTURE_ID = "web_sse_fixture_v1"
BROWSER_NORMAL_PROMPT = "运行流式显示验收"
SUSPEND_PROMPT = "触发暂停验收"
ERROR_PROMPT = "触发错误验收"
CONTROL_PROMPTS = frozenset({SUSPEND_PROMPT, ERROR_PROMPT})
CONFIRMATION_ID = "confirm_fixture"
CONFIRMATION_VERSION = 1
BROWSER_FINAL_DRAFT = (
    "# 分析结果\n\n"
    "第一段：已完成合成数据的分析流程。"
    "第二段：已检查数据质量和字段范围。\n\n"
    "| 检查项 | 状态 |\n|---|---|\n"
    "| 数据质量 | 已检查 |\n| 分析流程 | 已完成 |\n\n"
    "## 局限\n\n此页面只验证合成数据的流式显示。"
)


def split_audited_fixture_text(text: str) -> tuple[str, str, str]:
    """Split audited text into three timed chunks without changing a byte."""

    required = ("# 分析结果", "第一段", "第二段", "|", "## 局限")
    missing = [anchor for anchor in required if anchor not in text]
    assert text and not missing, f"missing audited fixture anchor: {missing}"

    first = text.index("第一段")
    second = text.index("第二段", first + len("第一段"))
    table = text.index("|", second + len("第二段"))
    chunks = (text[:second], text[second:table], text[table:])
    assert all(chunks), "missing audited fixture anchor: empty split"
    assert "".join(chunks) == text
    return chunks


def write_browser_fixture_csv(output_dir: Path) -> Path:
    """Write a privacy-safe, deterministic 120-row synthetic dataset."""

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "browser_fixture.csv"
    channels = ("自然", "广告", "合作")
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(("日期", "收入", "成本", "渠道"))
        for index in range(120):
            month = index // 28 + 1
            day = index % 28 + 1
            channel = channels[index % len(channels)]
            cost = 520 + index * 3 + (index % 11) * 7
            channel_effect = {"自然": 45, "广告": 120, "合作": 80}[channel]
            revenue = 760 + round(cost * 1.25) + channel_effect + (index % 7) * 9
            writer.writerow(
                (f"2026-{month:02d}-{day:02d}", revenue, cost, channel)
            )
    return path


def make_observed_event_queue(
    trace_path: Path,
    *,
    started_ns: int | None = None,
    monotonic_ns: Callable[[], int] = time.monotonic_ns,
):
    """Return a production-queue subclass that appends payload-free JSONL."""

    from data_agent.web.event_bus import EventQueue

    trace_path = Path(trace_path)
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    start = monotonic_ns() if started_ns is None else started_ns
    trace_lock = threading.Lock()

    class ObservedEventQueue(EventQueue):
        def __init__(self):
            super().__init__()
            self._observed_session_id = ""

        def put(self, event) -> None:
            super().put(event)
            session_id = str(event.data.get("session_id") or "")
            if session_id:
                self._observed_session_id = session_id
            record = {
                "event": event.event,
                "monotonic_ms": max(0, (monotonic_ns() - start) // 1_000_000),
                "session_id": self._observed_session_id,
            }
            line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
            with trace_lock:
                with trace_path.open("a", encoding="utf-8", newline="\n") as handle:
                    handle.write(line + "\n")

    return ObservedEventQueue


class ScriptedProvider:
    """Deterministic LLM boundary that drives the real analysis tool path."""

    def __init__(self, fixture_source: Path):
        self.fixture_source = Path(fixture_source)
        self.calls = 0

    def _response(self):
        from data_agent.llm.client import Response, ToolCall

        self.calls += 1
        if self.calls == 1:
            return Response(
                tool_calls=[
                    ToolCall(
                        "fixture_load",
                        "load_data",
                        {
                            "source": str(self.fixture_source),
                            "name": "browser_fixture",
                        },
                    )
                ]
            )
        if self.calls == 2:
            return Response(
                tool_calls=[
                    ToolCall(
                        "fixture_profile",
                        "quick_profile",
                        {"name": "browser_fixture"},
                    )
                ]
            )
        if self.calls == 3:
            return Response(
                tool_calls=[
                    ToolCall(
                        "fixture_correlation",
                        "correlation_analysis",
                        {
                            "name": "browser_fixture",
                            "columns": "收入,成本",
                            "method": "pearson",
                        },
                    )
                ]
            )
        if self.calls == 4:
            return Response(
                tool_calls=[
                    ToolCall(
                        "fixture_factor",
                        "factor_relationship_analysis",
                        {
                            "name": "browser_fixture",
                            "target_col": "收入",
                            "features": "成本",
                        },
                    )
                ]
            )
        return Response(text=BROWSER_FINAL_DRAFT)

    def stream_chat_structured(
        self,
        messages,
        tools=None,
        system=None,
        max_tokens=None,
    ) -> Iterator[Any]:
        from data_agent.llm.client import StreamComplete, StreamTextDelta

        response = self._response()
        if response.text:
            yield StreamTextDelta(response.text)
        yield StreamComplete(response)

    def chat(self, messages, tools=None, system=None, max_tokens=None):
        return self._response()


class _ScriptedIntentProvider:
    """Keep semantic intent classification inside the scripted boundary."""

    def chat(self, messages, system=None):
        del messages, system
        from data_agent.llm.client import Response

        return Response(
            text=json.dumps(
                {
                    "intent_type": "directed_analysis",
                    "reason": "deterministic browser fixture",
                    "ambiguities": [],
                },
                ensure_ascii=False,
            )
        )


def _install_scripted_provider_boundaries() -> Callable[[], None]:
    from data_agent.agent import llm_intent

    previous = llm_intent._client
    scripted = _ScriptedIntentProvider()
    llm_intent._client = scripted

    def restore() -> None:
        if llm_intent._client is scripted:
            llm_intent._client = previous

    return restore


class _FixtureConfirmationRuntime:
    def get(self, session_id: str, confirmation_id: str):
        if confirmation_id != CONFIRMATION_ID:
            raise KeyError(confirmation_id)
        return {
            "confirmation_id": CONFIRMATION_ID,
            "session_id": session_id,
            "version": CONFIRMATION_VERSION,
        }


class DelayedAuditedLoop:
    """Delay only the final text already emitted by the real audited loop."""

    def __init__(self, inner):
        self.inner = inner
        self.interrupted = threading.Event()
        self._runtime = _FixtureConfirmationRuntime()

    @property
    def session_id(self) -> str:
        return self.inner.session_id

    @property
    def messages(self) -> list[dict[str, Any]]:
        return self.inner.messages

    @messages.setter
    def messages(self, value: list[dict[str, Any]]) -> None:
        self.inner.messages = value

    def __getattr__(self, name: str):
        return getattr(self.inner, name)

    def _auto_save(self) -> None:
        self.inner._auto_save()

    def _confirmation_runtime(self):
        return self._runtime

    def request_interrupt(self) -> None:
        self.interrupted.set()

    def _control_stream(self, message: str):
        if message == ERROR_PROMPT:
            raise RuntimeError("synthetic_acceptance_error")
        if message != SUSPEND_PROMPT:
            raise ValueError(f"unsupported fixture control prompt: {message}")
        yield {
            "type": "suspended",
            "confirmation_id": CONFIRMATION_ID,
            "suspension_id": CONFIRMATION_ID,
            "version": CONFIRMATION_VERSION,
            "question": "是否继续暂停验收？",
            "options": ["继续"],
            "context": {"fixture_id": FIXTURE_ID},
            "multi_select": False,
            "allow_free_text": False,
            "confirmation_type": "fixture_control",
            "blocking_reason": "browser_acceptance",
            "related_task_id": None,
            "related_spec_id": None,
        }

    def stream_turn(self, message: str):
        if message in CONTROL_PROMPTS:
            yield from self._control_stream(message)
            return

        self.interrupted.clear()
        final_text = ""
        for event in self.inner.stream_turn(message):
            if event.get("type") == "text_delta":
                final_text += str(event.get("text") or "")
            else:
                yield event
        for chunk in split_audited_fixture_text(final_text):
            if self.interrupted.wait(0.6):
                yield {"type": "error", "message": "已中断验收"}
                return
            yield {"type": "text_delta", "text": chunk}

    def resume_turn_streaming(
        self,
        confirmation_id: str,
        user_response: str,
        *,
        expected_version: int | None = None,
        idempotency_key: str = "",
    ):
        if (
            confirmation_id != CONFIRMATION_ID
            or expected_version != CONFIRMATION_VERSION
            or not idempotency_key
        ):
            raise ValueError("invalid fixture confirmation identity or version")
        text = "恢复后内容"
        self.messages.append(
            {
                "role": "user",
                "content": (
                    f"<confirmation_response suspension_id=\"{CONFIRMATION_ID}\">"
                    f"{user_response}</confirmation_response>"
                ),
            }
        )
        self.messages.append({"role": "assistant", "content": text})
        self._auto_save()
        yield {"type": "text_delta", "text": text}


class ScriptedManager:
    """Own one real wrapped loop per session for frontend state-map testing."""

    def __init__(self, fixture_source: Path):
        self.fixture_source = Path(fixture_source)
        self._loops: dict[str, DelayedAuditedLoop] = {}
        self._lock = threading.Lock()

    def get_or_create(
        self,
        session_id: str | None = None,
        model_id: str | None = None,
    ) -> DelayedAuditedLoop:
        del model_id
        sid = session_id or uuid.uuid4().hex[:12]
        with self._lock:
            existing = self._loops.get(sid)
            if existing is not None:
                return existing

        from data_agent.agent.loop import AgentLoop, set_interaction_mode

        set_interaction_mode("web")
        loop = AgentLoop(
            client=ScriptedProvider(self.fixture_source),
            session_id=sid,
        )
        wrapped = DelayedAuditedLoop(loop)
        with self._lock:
            self._loops[sid] = wrapped
        return wrapped

    def get(self, session_id: str) -> DelayedAuditedLoop | None:
        return self._loops.get(session_id)

    def remove(self, session_id: str) -> None:
        with self._lock:
            self._loops.pop(session_id, None)


def _configure_isolated_roots(output_dir: Path) -> Callable[[], None]:
    keys = (
        "WORKSPACE_DIR",
        "SESSIONS_DIR",
        "MCP_ENABLED",
        "SKILL_AUTO_DISCOVER",
        "LITELLM_LOCAL_MODEL_COST_MAP",
    )
    previous_environment = {key: os.environ.get(key) for key in keys}
    import data_agent.config

    previous_config = data_agent.config._config
    os.environ["WORKSPACE_DIR"] = str(output_dir / "workspace")
    os.environ["SESSIONS_DIR"] = str(output_dir / "sessions")
    os.environ.setdefault("MCP_ENABLED", "false")
    os.environ.setdefault("SKILL_AUTO_DISCOVER", "false")
    os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    data_agent.config._config = None

    def restore() -> None:
        data_agent.config._config = previous_config
        for key, value in previous_environment.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    return restore


def build_fixture_app(output_dir: Path):
    """Create the normal Flask app after isolating every persistent root."""

    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    fixture_csv = write_browser_fixture_csv(output_dir)
    restore_isolated_roots = _configure_isolated_roots(output_dir)
    restore_provider_boundaries = _install_scripted_provider_boundaries()

    from data_agent.lifecycle import AgentLifecycle

    lifecycle = AgentLifecycle()
    lifecycle.initialize()

    from data_agent.web.app import create_app

    app = create_app()
    from data_agent.config import get_config

    uploaded_fixture = get_config().inbox_dir / fixture_csv.name
    app.config["agent_manager"] = ScriptedManager(uploaded_fixture)
    app.config["lifecycle"] = lifecycle

    trace_path = output_dir / "browser_fixture_events.jsonl"
    from data_agent.web.blueprints import chat as chat_blueprint

    previous_event_queue = chat_blueprint.EventQueue
    observed_event_queue = make_observed_event_queue(trace_path)
    chat_blueprint.EventQueue = observed_event_queue

    def restore_event_queue() -> None:
        if chat_blueprint.EventQueue is observed_event_queue:
            chat_blueprint.EventQueue = previous_event_queue

    app.config["fixture_event_trace"] = str(trace_path)
    app.config["fixture_output_dir"] = str(output_dir)
    app.config["fixture_csv"] = str(fixture_csv)
    app.config["fixture_restore_event_queue"] = restore_event_queue
    app.config["fixture_restore_provider_boundaries"] = restore_provider_boundaries
    app.config["fixture_restore_isolated_roots"] = restore_isolated_roots
    return app


def shutdown_fixture_app(app) -> None:
    """Release fixture-owned process globals and lifecycle resources."""

    lifecycle = app.config.get("lifecycle")
    if lifecycle is not None:
        lifecycle.shutdown()
    for key in (
        "fixture_restore_event_queue",
        "fixture_restore_provider_boundaries",
        "fixture_restore_isolated_roots",
    ):
        restore = app.config.pop(key, None)
        if callable(restore):
            restore()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the deterministic real-pipeline browser SSE fixture."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5013)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.host != "127.0.0.1":
        raise SystemExit("fixture host must be 127.0.0.1")
    if not 1 <= args.port <= 65535:
        raise SystemExit("fixture port must be between 1 and 65535")

    app = build_fixture_app(args.output_dir)
    print(f"fixture_id={FIXTURE_ID}")
    print(f"url=http://127.0.0.1:{args.port}")
    print(f"fixture_csv={app.config['fixture_csv']}")
    print(f"event_trace={app.config['fixture_event_trace']}")
    try:
        app.run(
            host="127.0.0.1",
            port=args.port,
            threaded=True,
            debug=False,
            use_reloader=False,
        )
    finally:
        shutdown_fixture_app(app)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
