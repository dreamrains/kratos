"""Tests for safe live analysis-progress narration (Task 11).

Progress events are server-authored (closed vocabulary), never leak findings,
and reach the client BEFORE the buffered final audited answer. Step 1 covers
the payload contract and the stream-ordering guarantee; Step 2 covers the
chat-blueprint SSE projection and the browser-side handler presence.
"""

from __future__ import annotations

from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Step 1 — safe payload and pre-final ordering
# ---------------------------------------------------------------------------


def test_progress_payload_is_server_authored_and_contains_no_findings():
    from data_agent.agent.progress import build_analysis_progress

    event = build_analysis_progress(
        code="analysis_step_started",
        step_id="step_relationship",
        status="running",
    )
    payload = event.to_dict()
    assert payload["label"] == "正在评估变量关系"
    # No numeric/claim/reasoning fields are ever present on the wire.
    assert not {"value", "p_value", "ranking", "claim", "reasoning"} & set(payload)
    # Wire format is exactly the closed identity/phase vocabulary.
    assert set(payload) == {"type", "code", "label", "status", "step_id", "phase"}


def test_build_analysis_progress_rejects_unknown_codes():
    from data_agent.agent.progress import build_analysis_progress

    with pytest.raises(ValueError):
        build_analysis_progress(code="leaking_p_value")
    with pytest.raises(ValueError):
        build_analysis_progress(code="analysis_plan_ready", status="finished")


def test_build_analysis_progress_never_includes_extra_kwargs():
    from data_agent.agent.progress import build_analysis_progress

    # Signature is keyword-only with no **kwargs — caller cannot inject a
    # ``value``/``claim``/``reasoning`` field even if they try.
    with pytest.raises(TypeError):
        build_analysis_progress(  # type: ignore[call-arg]
            code="analysis_plan_ready",
            value=0.95,  # rejected: not a declared parameter
        )


# ---------------------------------------------------------------------------
# Streaming fixture — minimal deterministic directed-analysis turn
# ---------------------------------------------------------------------------


@pytest.fixture
def clean_workspace():
    """Isolated agent context so progress events do not leak across tests."""
    from data_agent.agent.context import (
        AgentContext,
        reset_current_context,
        set_current_context,
    )
    from data_agent.session.workspace import Workspace

    ctx = AgentContext(session_id="progress_stream", workspace=Workspace())
    token = set_current_context(ctx)
    yield ctx
    reset_current_context(token)


@pytest.fixture
def agent(clean_workspace):
    """Minimal streaming agent that emits progress before a buffered final text.

    The fake client yields a single directed-analysis final answer. The loop
    is stubbed so the audit-candidate buffer path engages deterministically:
    progress events bracket the buffered final answer without depending on a
    real audit/renderer implementation. Candidate findings remain buffered
    until the (stubbed) gate publishes them.
    """

    from data_agent.agent.loop import AgentLoop
    from data_agent.llm.client import Response, StreamComplete, StreamTextDelta

    finding_text = "显著因素是活跃度，与目标值正相关。"

    class _FakeStreamingClient:
        def stream_chat_structured(self, messages, tools=None, system=""):
            yield StreamTextDelta(finding_text)
            yield StreamComplete(Response(text=finding_text))

        def chat(self, *args, **kwargs):
            raise AssertionError("streaming fixture must not fall back to sync chat")

    loop = AgentLoop(client=_FakeStreamingClient(), session_id="progress_stream")
    loop._get_system_prompt = lambda: ""
    # Engage the audit-candidate buffered path so progress events surround
    # the final answer. The quality-guard buffer path stays off so only the
    # audit-candidate buffer controls publication.
    loop._is_final_answer_audit_candidate = lambda: True
    loop._is_analysis_quality_guard_candidate = lambda: False
    # Deterministic final-answer handling: do not continue for quality, do
    # not inject extra policy messages, and publish the draft verbatim.
    loop._should_continue_for_analysis_quality = lambda *args, **kwargs: False
    loop._maybe_inject_synthesis_policy = lambda *args, **kwargs: None
    loop._maybe_auto_suspend_for_required_question = lambda: None
    loop._runtime_confirmation_checkpoint = lambda: None
    loop._gate_final_analysis_answer = lambda user_input, final_text, **kwargs: {
        "action": "publish",
        "text": final_text,
    }

    class _StreamingAgent:
        """Thin adapter exposing the brief's ``run_stream`` entry point."""

        def __init__(self, inner):
            self.loop = inner

        def run_stream(self, text):
            yield from self.loop.stream_turn(text)

    return _StreamingAgent(loop)


def test_stream_emits_progress_before_buffered_final_answer(agent):
    events = list(agent.run_stream("分析显著影响因素"))
    types = [ev.get("type") for ev in events]
    assert "analysis_progress" in types, f"no analysis_progress in {types}"
    assert "text_delta" in types, f"no text_delta in {types}"

    progress_index = next(
        i for i, event in enumerate(events) if event["type"] == "analysis_progress"
    )
    final_index = next(
        i for i, event in enumerate(events) if event["type"] == "text_delta"
    )
    assert progress_index < final_index
    # Server-authored labels only — no candidate finding text leaks through
    # any progress payload before the buffered final answer is published.
    assert all(
        "显著因素是" not in event.get("label", "") for event in events[:final_index]
    )


def test_progress_events_use_closed_vocabulary_only(agent):
    events = list(agent.run_stream("分析显著影响因素"))
    from data_agent.agent.progress import PROGRESS_LABELS

    progress_events = [ev for ev in events if ev.get("type") == "analysis_progress"]
    assert progress_events, "expected at least one analysis_progress event"
    for event in progress_events:
        assert event["code"] in PROGRESS_LABELS
        assert event["label"] == PROGRESS_LABELS[event["code"]] or event["label"] in {
            "正在评估变量关系",
            "正在检查颗粒度与缺失",
            "正在执行单变量分析",
            "正在尝试多变量方法",
            "正在整理局限说明",
        }
        # Hard guard: no findings/numeric/claim fields ever reach the wire.
        forbidden = {"value", "p_value", "ranking", "claim", "reasoning"}
        assert not forbidden & set(event)


def test_step_started_emits_before_tool_started_when_tool_binds_to_step(
    monkeypatch, tmp_path, clean_workspace
):
    """``analysis_step_started`` narrates the step-specific method before ``tool_started``.

    M1: when a substantive analytical tool call binds to a canonical plan
    step, the loop emits ``analysis_step_started`` with the step-specific
    label (e.g. ``正在评估变量关系``) BEFORE the generic ``tool_started``
    event. Verified in both the streaming event stream and the sync
    diagnostics mirror. The no-leak invariant still holds.
    """
    import data_agent.agent.loop as loop_module
    from data_agent.agent.analysis_execution import StepBindingResult
    from data_agent.agent.analysis_state import AnalysisSessionState
    from data_agent.llm.client import Response, ToolCall
    from data_agent.tools.registry import (
        ToolCapability,
        ToolDefinition,
        ToolResult,
        registry,
    )

    # Route session persistence at tmp_path so no real session dir is touched.
    cfg = loop_module.get_config()
    monkeypatch.setattr(cfg, "sessions_dir", tmp_path)
    monkeypatch.setattr(cfg, "skill_auto_discover", False)

    # Install a substantive fake tool so scope-guard + registry paths run. A
    # declared capability makes the tool "substantive"; without it the loop
    # would treat the call as non-analytical helper traffic.
    capability = ToolCapability(
        "analysis.test_relationship", category="relationship"
    )
    definition = ToolDefinition(
        name="progress_step_started_tool",
        description="test tool",
        func=lambda name: ToolResult(summary="ok"),
        parameters={"type": "object", "properties": {"name": {"type": "string"}}},
        capability=capability,
    )
    monkeypatch.setitem(registry._tools, "progress_step_started_tool", definition)
    monkeypatch.setitem(
        registry._capabilities, "progress_step_started_tool", capability
    )

    loop = loop_module.AgentLoop(
        client=object(), session_id="progress_step_started"
    )
    loop._get_system_prompt = lambda: ""
    # Real analysis_state so the sync ``_record_progress`` diagnostic trail
    # has somewhere to land via ``append_turn_diagnostic``. A trivial flow
    # controller stub satisfies the post-execution regression check (which
    # is otherwise wired up inside ``_prepare_analysis_turn``).
    from types import SimpleNamespace

    state = AnalysisSessionState(session_id="progress_step_started")
    loop.context.analysis_state = state
    loop._flow_controller = SimpleNamespace(check_tool_regression=lambda *a, **kw: None)
    # Deterministic successful binding to a canonical step. Binding internals
    # are covered by their own suite; here we verify the emission wiring.
    loop._bind_tool_call = lambda tc: StepBindingResult(
        ok=True,
        plan_id="plan_1",
        step_id="step_relationship",
        claim_key="rel",
    )

    tc = ToolCall(
        id="tc_step",
        name="progress_step_started_tool",
        arguments={"name": "sales"},
    )

    # --- Streaming path: ``analysis_step_started`` yielded before ``tool_started`` ---
    events = list(
        loop._process_tool_calls(Response(tool_calls=[tc]), round_num=1)
    )
    progress = [ev for ev in events if ev.get("type") == "analysis_progress"]
    codes = [ev["code"] for ev in progress]
    assert "analysis_step_started" in codes, f"step_started missing in {codes}"
    assert "tool_started" in codes, f"tool_started missing in {codes}"
    assert codes.index("analysis_step_started") < codes.index("tool_started")
    step_ev = next(ev for ev in progress if ev["code"] == "analysis_step_started")
    assert step_ev["step_id"] == "step_relationship"
    # Step-specific label from STEP_LABELS — not the generic default.
    assert step_ev["label"] == "正在评估变量关系"
    # No-leak invariant on the streamed payload.
    for ev in progress:
        assert not {"value", "p_value", "ranking", "claim", "reasoning"} & set(ev)

    # --- Sync path: same ordering mirrored into turn diagnostics ---
    state.turn_diagnostics = []
    assert loop._execute_single_tool(tc, [tc], 0) is None
    diag_progress = [
        d for d in state.turn_diagnostics if d.get("kind") == "analysis_progress"
    ]
    diag_codes = [d["code"] for d in diag_progress]
    assert "analysis_step_started" in diag_codes
    assert "tool_started" in diag_codes
    assert diag_codes.index("analysis_step_started") < diag_codes.index("tool_started")
    step_diag = next(
        d for d in diag_progress if d["code"] == "analysis_step_started"
    )
    assert step_diag["step_id"] == "step_relationship"
    assert step_diag["label"] == "正在评估变量关系"
    for d in diag_progress:
        assert not {"value", "p_value", "ranking", "claim", "reasoning"} & set(d)


def test_step_started_is_skipped_when_binding_has_no_step_id(
    monkeypatch, tmp_path, clean_workspace
):
    """Non-substantive or unbound calls must NOT emit ``analysis_step_started``.

    Guards the "only emit when the binding actually has a step_id" half of
    M1: an unsuccessful binding (or a non-substantive tool returning None)
    must fall straight through to ``tool_started`` without the step-specific
    narration.
    """
    import data_agent.agent.loop as loop_module
    from data_agent.agent.analysis_execution import StepBindingResult
    from data_agent.agent.analysis_state import AnalysisSessionState
    from data_agent.llm.client import Response, ToolCall
    from data_agent.tools.registry import (
        ToolCapability,
        ToolDefinition,
        ToolResult,
        registry,
    )

    cfg = loop_module.get_config()
    monkeypatch.setattr(cfg, "sessions_dir", tmp_path)
    monkeypatch.setattr(cfg, "skill_auto_discover", False)

    capability = ToolCapability("analysis.test_relationship", category="relationship")
    definition = ToolDefinition(
        name="progress_unbound_tool",
        description="test tool",
        func=lambda name: ToolResult(summary="ok"),
        parameters={"type": "object", "properties": {"name": {"type": "string"}}},
        capability=capability,
    )
    monkeypatch.setitem(registry._tools, "progress_unbound_tool", definition)
    monkeypatch.setitem(registry._capabilities, "progress_unbound_tool", capability)

    loop = loop_module.AgentLoop(client=object(), session_id="progress_unbound")
    loop._get_system_prompt = lambda: ""
    from types import SimpleNamespace

    state = AnalysisSessionState(session_id="progress_unbound")
    loop.context.analysis_state = state
    loop._flow_controller = SimpleNamespace(check_tool_regression=lambda *a, **kw: None)
    # Unsuccessful binding (ok=False, empty step_id) — must not trigger the
    # step-specific emission.
    loop._bind_tool_call = lambda tc: StepBindingResult(
        ok=False, plan_id="plan_1", error_type="analysis_step_not_found"
    )

    tc = ToolCall(
        id="tc_unbound", name="progress_unbound_tool", arguments={"name": "sales"}
    )

    events = list(
        loop._process_tool_calls(Response(tool_calls=[tc]), round_num=1)
    )
    codes = [
        ev["code"]
        for ev in events
        if ev.get("type") == "analysis_progress"
    ]
    assert "analysis_step_started" not in codes
    assert "tool_started" in codes

    state.turn_diagnostics = []
    assert loop._execute_single_tool(tc, [tc], 0) is None
    diag_codes = [
        d["code"]
        for d in state.turn_diagnostics
        if d.get("kind") == "analysis_progress"
    ]
    assert "analysis_step_started" not in diag_codes
    assert "tool_started" in diag_codes


# ---------------------------------------------------------------------------
# Step 2 — chat-blueprint SSE projection and browser-side handler
# ---------------------------------------------------------------------------


def feed_one(event_dict):
    """Drive one loop event through the chat blueprint and return the SSE event.

    Reuses ``_feed_events`` directly so the mapping stays in lockstep with
    production. The helper is defined here (rather than in the collect-ignored
    ``tests/test_sse_reactivity.py``) so pytest collects it.
    """

    from data_agent.web.blueprints.chat import _feed_events
    from data_agent.web.event_bus import EventQueue

    captured: list = []
    eq = EventQueue()
    eq.put = lambda sse_event: captured.append(sse_event)

    class _FakeLoop:
        session_id = "feed_one"
        messages: list = []

        def _auto_save(self):
            pass

    generator = iter([event_dict])
    _feed_events(eq, _FakeLoop(), "t_feed_one", generator)
    assert captured, f"no SSE event produced for {event_dict}"
    return captured[0]


def test_chat_blueprint_projects_analysis_progress():
    sse = feed_one(
        {"type": "analysis_progress", "code": "tool_started", "label": "正在运行相关性分析"}
    )
    assert sse.event == "analysis_progress"
    assert sse.data["label"] == "正在运行相关性分析"
    # Only identity/phase fields are projected — never findings or extra keys.
    assert set(sse.data) <= {"code", "label", "status", "step_id", "phase"}


def test_frontend_handles_analysis_progress_without_appending_final_text():
    source = Path("src/data_agent/web/static/js/app.js").read_text(encoding="utf-8")
    assert "case 'analysis_progress':" in source
    assert "turn.analysisProgress" in source
    # The progress label drives the live thinking indicator only. Scope the
    # check to the case body so the assertion is robust to other handlers.
    progress_block_start = source.index("case 'analysis_progress':")
    progress_block_end = source.index("break;", progress_block_start)
    progress_block = source[progress_block_start:progress_block_end]
    assert "turn.thinkingText = data.label" in progress_block
    # No mutation of the final answer text inside the progress handler —
    # findings stay buffered until the audited ``text_delta`` arrives.
    assert "turn.content +=" not in progress_block
    assert "turn.content =" not in progress_block
