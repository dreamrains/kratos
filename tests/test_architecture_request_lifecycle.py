from __future__ import annotations

import json
from types import SimpleNamespace as NS

import pytest

from data_agent.llm.client import LLMClient


def test_default_silent_truncation_is_one_request_not_a_budget_upgrade():
    calls = []
    def transport(**kw):
        calls.append(kw)
        return NS(choices=[NS(message=NS(content="", tool_calls=None), finish_reason="length")])
    result = LLMClient(model_id="test/model", max_tokens=2000, transport=transport).chat([])
    assert result.finish_reason == "length"
    assert len(calls) == 1 and calls[0]["max_tokens"] == 2000 and calls[0]["num_retries"] == 0


def test_evidence_nested_parameter_errors_precede_missing_receipts():
    from data_agent.tools.analysis_flow import record_evidence_record
    payload = dict(claim="fit", dataset="retention", method="power", tool_calls="curve_fitting, run_python",
                   result_summary="fit", limitations=[], confidence="高")
    result = json.loads(record_evidence_record(payload))
    assert result["error_type"] == "invalid_evidence_arguments"
    assert {item["path"] for item in result["details"]} == {"record_json.tool_calls", "record_json.confidence"}


def test_artifact_references_resolve_with_session_isolation(tmp_path):
    from data_agent.session.artifact_paths import resolve_reference
    project, sessions = tmp_path / "project", tmp_path / "isolated_sessions"
    options = dict(project=project, sessions=sessions, session_id="own")
    expected = sessions / "own" / "tool_outputs" / "call_detail.json"
    assert resolve_reference("tool_outputs/call_detail.json", **options) == expected
    assert resolve_reference("sessions/own/tool_outputs/call_detail.json", **options) == expected
    for reference in ["sessions/other/tool_outputs/call_detail.json", "tool_outputs/../conversation.json", str(sessions / "other" / "output" / "a")]:
        with pytest.raises(ValueError):
            resolve_reference(reference, **options)


def test_error_event_cannot_end_as_completed(tmp_path, monkeypatch):
    from data_agent.web.blueprints import chat
    from data_agent.web.event_bus import EventQueue
    from data_agent.web import run_state
    monkeypatch.setattr(run_state, "_session_dir", lambda sid: tmp_path / sid)
    monkeypatch.setattr(chat, "_token_usage", lambda loop: None)
    runs = run_state.RunStates()
    runs.begin("one", "turn")
    saved = []
    loop = NS(session_id="one", messages=[], _auto_save=lambda: saved.append(True))
    eq = EventQueue()
    chat._feed_events(eq, loop, "turn", iter([{"type": "error", "message": "Provider failed"}]), runs)
    text = "".join(eq.iter())
    assert '"status": "failed"' in text and '"status": "completed"' not in text
    assert runs.snapshot("one")["status"] == "failed"
    assert loop.messages[-1]["content"] == runs.snapshot("one")["notice"]
    assert "Provider failed" in loop.messages[-1]["content"]
    assert saved


def test_cancelling_stays_busy_until_terminal_state(tmp_path, monkeypatch):
    from data_agent.web import run_state
    monkeypatch.setattr(run_state, "_session_dir", lambda sid: tmp_path / sid)
    runs = run_state.RunStates()
    runs.begin("one", "turn1")
    runs.cancelling("one")
    with pytest.raises(run_state.SessionBusy):
        runs.begin("one", "turn2")
    runs.finish("one", "turn1", "cancelled")
    assert run_state.RunStates().snapshot("one")["status"] == "cancelled"
    runs.begin("one", "turn2")
    assert run_state.RunStates().snapshot("one")["status"] == "unknown"


def test_failed_evidence_does_not_resolve_python_and_corrected_arguments_can_recover():
    from data_agent.agent.execution_control import TurnExecutionState
    state = TurnExecutionState()
    state.record_tool_call("run_python", {})
    state.record_tool_success()
    state.record_tool_call("record_evidence_record", {"bad": 1})
    state.record_tool_error("record_evidence_record", {"bad": 1}, "invalid args")
    assert state.pending_fallback_resolution
    state.consecutive_errors = 3
    state.ensure_can_call("record_evidence_record", {"corrected": True})
    state.record_tool_call("record_evidence_record", {"corrected": True})
    state.record_tool_success()
    assert not state.pending_fallback_resolution


def test_sandbox_timeout_leaves_no_running_child():
    import multiprocessing
    from data_agent.tools.sandbox import _execute_isolated
    before = {child.pid for child in multiprocessing.active_children()}
    with pytest.raises(TimeoutError):
        _execute_isolated("sum(range(10000000000))", 0.1, {})
    assert {child.pid for child in multiprocessing.active_children()} == before


def test_sandbox_process_can_only_read_its_dataset_snapshot():
    import pandas as pd
    from data_agent.tools.sandbox import _execute_isolated
    out, result = _execute_isolated("get_dataset('own')['value'].sum()", 15, {"own": pd.DataFrame({"value": [2, 3]})})
    assert result == "5"
    _, rejected = _execute_isolated("get_dataset('other')", 15, {"own": pd.DataFrame({"value": [2, 3]})})
    assert "dataset_outside_current_task_scope" in rejected


def test_curve_chart_uses_receipted_values_and_rejects_modified_details(tmp_path, monkeypatch):
    import pandas as pd
    from data_agent.agent.loop import AgentLoop
    from data_agent.agent.context import use_agent_context
    from data_agent.config import get_config
    from data_agent.tools.curve_fitting import curve_fitting
    from data_agent.tools.result_reference import load_result_reference
    monkeypatch.setattr(get_config(), "sessions_dir", tmp_path / "sessions")
    loop = AgentLoop(client=object(), session_id="curve-result")
    loop.context.workspace.add("retention", pd.DataFrame({"x": range(1, 7), "y": [0.5, 0.3, 0.24, 0.18, 0.15, 0.14]}))
    with use_agent_context(loop.context):
        result = curve_fitting("retention", x_col="x", y_col="y")
        ref = loop._compact_tool_output(result, NS(id="curve"))
        loop._record_turn_tool_result("curve_fitting", ref, {"name": "retention"}, "curve", result.data)
        payload, binding = load_result_reference("tool_outputs/curve_detail.json")
        assert payload["chart_data"][0]["actual"] == 0.5
        best = payload["fits"][0]
        assert [row[best["family"] + "_fit"] for row in payload["chart_data"]] == best["predicted"]
        path = tmp_path / "sessions/curve-result/tool_outputs/curve_detail.json"
        changed = json.loads(path.read_text(encoding="utf-8"))
        changed["chart_data"][0]["actual"] = 0
        path.write_text(json.dumps(changed), encoding="utf-8")
        with pytest.raises(ValueError, match="does not match"):
            load_result_reference("tool_outputs/curve_detail.json")
