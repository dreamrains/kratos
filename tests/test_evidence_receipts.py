"""Evidence records must bind to successful tool receipts from the current turn."""

from __future__ import annotations

import json

import pytest

from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.context import use_agent_context
from data_agent.agent.execution_control import TurnExecutionState
from data_agent.agent.loop import AgentLoop
from data_agent.agent.workbench_view import build_workbench_view
from data_agent.tools.analysis_flow import record_evidence_record
from data_agent.tools.result_reference import load_result_reference


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


def test_repeated_tool_call_id_keeps_each_structured_result_bound_to_its_receipt():
    """A provider may reuse an ID in a later round; result files must not collide."""
    loop = AgentLoop(client=object(), session_id="repeated-tool-call-id")
    state = AnalysisSessionState(session_id="repeated-tool-call-id")
    loop.context.analysis_state = state
    loop.context.turn_state = TurnExecutionState()

    first_result = {
        "period_a": {"range": ["2026-09-01", "2026-09-01"]},
        "period_b": {"range": ["2026-09-02", "2026-09-02"]},
        "combined": {"row_count": 2},
        "metrics": {"amount": {"period_a": 10, "period_b": 20, "diff": 10}},
    }
    # A later round can reuse the provider call ID for a different result.
    # Both immutable payloads must remain available to their receipts.
    second_result = json.loads(json.dumps(first_result))
    second_result["metrics"]["amount"] = {"period_a": 10, "period_b": 15, "diff": 5}

    with use_agent_context(loop.context):
        first_receipt = loop._record_turn_tool_result(
            "compare_periods",
            json.dumps(first_result),
            {"name": "hyp", "date_col": "date", "metrics": "amount"},
            "provider-reused-id",
            structured_data=first_result,
        )
        second_receipt = loop._record_turn_tool_result(
            "compare_periods",
            json.dumps(second_result),
            {"name": "hyp", "date_col": "date", "metrics": "amount"},
            "provider-reused-id",
            structured_data=second_result,
        )
        result = json.loads(record_evidence_record(json.dumps(_payload(tool_calls=["compare_periods"]))))

    assert "error" not in result
    record = state.evidence_records[0]
    assert record["tool_receipt_ids"] == [first_receipt, second_receipt]
    assert len({source["result_ref"] for source in record["computed_statistics_sources"]}) == 2


def test_repeated_identical_result_can_bind_each_receipt_sharing_one_detail_file():
    """Identical immutable results may share storage without merging receipts."""
    loop = AgentLoop(client=object(), session_id="repeated-identical-result")
    state = AnalysisSessionState(session_id="repeated-identical-result")
    loop.context.analysis_state = state
    loop.context.turn_state = TurnExecutionState()
    structured_result = {
        "period_a": {"range": ["2026-09-01", "2026-09-01"]},
        "period_b": {"range": ["2026-09-02", "2026-09-02"]},
        "combined": {"row_count": 2},
        "metrics": {"amount": {"period_a": 10, "period_b": 20, "diff": 10}},
    }

    with use_agent_context(loop.context):
        first_receipt = loop._record_turn_tool_result(
            "compare_periods",
            json.dumps(structured_result),
            {"name": "hyp", "date_col": "date", "metrics": "amount"},
            "provider-reused-id",
            structured_data=structured_result,
        )
        second_receipt = loop._record_turn_tool_result(
            "compare_periods",
            json.dumps(structured_result),
            {"name": "hyp", "date_col": "date", "metrics": "amount"},
            "provider-reused-id",
            structured_data=structured_result,
        )
        result = json.loads(record_evidence_record(json.dumps(_payload(tool_calls=["compare_periods"]))))

    assert "error" not in result
    record = state.evidence_records[0]
    assert record["tool_receipt_ids"] == [first_receipt, second_receipt]
    assert len(record["computed_statistics_sources"]) == 2
    assert {source["receipt_id"] for source in record["computed_statistics_sources"]} == {
        first_receipt,
        second_receipt,
    }
    assert len({source["result_ref"] for source in record["computed_statistics_sources"]}) == 1


def test_structured_result_reference_has_a_bounded_filename_for_long_provider_call_id():
    loop = AgentLoop(client=object(), session_id="bounded-result-reference")
    state = AnalysisSessionState(session_id="bounded-result-reference")
    loop.context.analysis_state = state
    loop.context.turn_state = TurnExecutionState()
    structured_result = {"metrics": {"amount": {"value": 10}}}

    with use_agent_context(loop.context):
        receipt_id = loop._record_turn_tool_result(
            "compare_periods",
            json.dumps(structured_result),
            {"name": "hyp", "metrics": "amount"},
            "provider-" + ("x" * 500),
            structured_data=structured_result,
        )

    assert receipt_id
    detail_name = state.tool_receipts[0]["detail_ref"]["path"].split("/")[-1]
    assert len(detail_name) < 100


def test_new_receipt_rejects_legacy_path_even_when_payload_digest_matches(tmp_path, monkeypatch):
    from data_agent.config import get_config
    from data_agent.tools._utils import persist_detail

    monkeypatch.setattr(get_config(), "sessions_dir", tmp_path / "sessions")
    loop = AgentLoop(client=object(), session_id="strict-result-reference")
    state = AnalysisSessionState(session_id="strict-result-reference")
    loop.context.analysis_state = state
    loop.context.turn_state = TurnExecutionState()
    structured_result = {"metrics": {"amount": {"value": 10}}}

    with use_agent_context(loop.context):
        receipt_id = loop._record_turn_tool_result(
            "compare_periods",
            json.dumps(structured_result),
            {"name": "hyp", "metrics": "amount"},
            "legacy-call",
            structured_data=structured_result,
        )
        persist_detail(loop.session_id, "legacy-call", structured_result)
        with pytest.raises(ValueError, match="does not match"):
            load_result_reference("tool_outputs/legacy-call_detail.json")

    assert receipt_id


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
    assert build_workbench_view(state)["verified_conclusions"][0]["claim"] == payload["claim"]


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
