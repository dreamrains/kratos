"""Evidence records must bind to successful tool receipts from the current turn."""

from __future__ import annotations

import json

from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.context import use_agent_context
from data_agent.agent.execution_control import TurnExecutionState
from data_agent.agent.loop import AgentLoop
from data_agent.agent.workbench_view import build_action_board
from data_agent.tools.analysis_flow import record_evidence_record


def _payload(*, tool_calls):
    return {
        "claim": "Daily revenue declined in the second half of the observed window.",
        "dataset": "daily_revenue",
        "method": "descriptive daily aggregation",
        "tool_calls": tool_calls,
        "result_summary": "First half revenue was 1818 and second half revenue was 684.",
        "limitations": ["Descriptive result; it does not establish a cause."],
        "confidence": "medium",
        "sample_size": 71,
        "time_scope": "2026-04-07 to 2026-05-06",
        "calculation_method": "sum revenue by day",
        "method_detail": "complete calendar includes zero-order days",
    }


def test_evidence_record_binds_the_successful_receipt_from_its_current_turn():
    loop = AgentLoop(client=object(), session_id="evidence-receipt")
    state = AnalysisSessionState(session_id="evidence-receipt")
    loop.context.analysis_state = state
    loop.context.turn_state = TurnExecutionState()

    with use_agent_context(loop.context):
        receipt_id = loop._record_turn_tool_result(
            "analyze_time_series",
            '{"trend": {"direction": "down"}}',
            {"name": "daily_revenue", "date_col": "date", "value_col": "revenue"},
            "call_daily_trend",
        )
        result = json.loads(record_evidence_record(json.dumps(_payload(tool_calls=["analyze_time_series"]))))

    assert receipt_id
    assert result["evidence_id"]
    record = state.evidence_records[0]
    assert record["tool_receipt_ids"] == [receipt_id]
    receipt = state.tool_receipts[0]
    assert receipt["tool_call_id"] == "call_daily_trend"
    assert receipt["dataset_refs"] == ["daily_revenue"]
    assert receipt["result_sha256"].startswith("sha256:")


def test_evidence_record_rejects_a_tool_not_executed_in_the_current_turn():
    loop = AgentLoop(client=object(), session_id="evidence-receipt-reject")
    state = AnalysisSessionState(session_id="evidence-receipt-reject")
    loop.context.analysis_state = state
    loop.context.turn_state = TurnExecutionState()

    with use_agent_context(loop.context):
        loop._record_turn_tool_result("analyze_time_series", "{}", {"name": "daily_revenue"}, "call_1")
        result = json.loads(record_evidence_record(json.dumps(_payload(tool_calls=["compare_periods"]))))

    assert result["error_type"] == "unbound_tool_receipt"
    assert result["missing_tool_receipts"] == ["compare_periods"]
    assert state.evidence_records == []


def test_publication_boundary_verifies_current_receipted_evidence():
    loop = AgentLoop(client=object(), session_id="publication-verifies-evidence")
    state = AnalysisSessionState(session_id="publication-verifies-evidence")
    loop.context.analysis_state = state
    loop.context.turn_state = TurnExecutionState()

    with use_agent_context(loop.context):
        receipt_id = loop._record_turn_tool_result(
            "analyze_time_series", "{}", {"name": "daily_revenue"}, "call_publish"
        )
        payload = _payload(tool_calls=["analyze_time_series"])
        payload["id"] = "ev_publish"
        result = json.loads(record_evidence_record(json.dumps(payload)))
        assert result["evidence_id"] == "ev_publish"
        assert state.evidence_records[0]["tool_receipt_ids"] == [receipt_id]
        loop._verify_before_publication("分析收入趋势")

    assert state.verification_reports[-1]["overall_status"] == "pass"
    assert build_action_board(state)["confirmed"][0]["claim"] == payload["claim"]


def test_receipt_binding_and_plan_binding_survive_a_turn_state_replan():
    loop = AgentLoop(client=object(), session_id="receipt-survives-replan")
    state = AnalysisSessionState(session_id="receipt-survives-replan")
    state.set_analysis_plan({"id": "plan_r07", "goal": "trend"})
    loop.context.analysis_state = state
    loop.context.turn_state = TurnExecutionState()

    with use_agent_context(loop.context):
        first_receipt = loop._record_turn_tool_result("load_data", "{}", {"name": "d03_orders"}, "call_load")
        # Replanning after load resets tool routing and replaces the execution
        # budget state, but it must not erase the current turn's auditable
        # receipt chain.
        loop.context.reset_turn_state()
        loop.context.turn_state = TurnExecutionState()
        second_receipt = loop._record_turn_tool_result(
            "analyze_time_series", "{}", {"name": "d03_orders"}, "call_trend"
        )
        result = json.loads(record_evidence_record(json.dumps(_payload(
            tool_calls=["load_data", "analyze_time_series"]
        ))))

    record = state.evidence_records[0]
    assert result["evidence_id"] == record["id"]
    assert record["plan_id"] == "plan_r07"
    assert record["tool_receipt_ids"] == [first_receipt, second_receipt]
