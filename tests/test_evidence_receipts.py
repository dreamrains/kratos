"""Evidence records must bind to successful tool receipts from the current turn."""

from __future__ import annotations

import json

import pytest
import pandas as pd

from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.context import use_agent_context
from data_agent.agent.execution_control import TurnExecutionState
from data_agent.agent.loop import AgentLoop
from data_agent.agent.publication.native import resolve_native_claims
from data_agent.agent.workbench_view import build_workbench_view
from data_agent.tools.analysis_flow import record_evidence_record
from data_agent.tools.result_reference import load_result_reference
from data_agent.tools.sandbox import run_python
from data_agent.session.workspace import workspace


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


def test_dynamic_python_reads_bind_executed_values_to_all_six_source_versions():
    loop = AgentLoop(client=object(), session_id="dynamic-python-read-set")
    state = AnalysisSessionState(session_id="dynamic-python-read-set")
    loop.context.analysis_state = state
    loop.context.turn_state = TurnExecutionState()
    names = [f"source_{index}" for index in range(1, 7)]
    with use_agent_context(loop.context):
        for index, name in enumerate(names, 1):
            loop.context.workspace.add(name, pd.DataFrame({"value": [index]}))
        code = (
            f"names = {names!r}\n"
            "result = {'table': [{'source': name, 'value': int(get_dataset(name)['value'].sum())} "
            "for name in names]}"
        )
        raw = run_python(code, purpose="six-source comparison")
        data = json.loads(raw)
        receipt_id = loop._record_turn_tool_result(
            "run_python", raw, {"code": code}, "dynamic-read-call", structured_data=data,
        )

    assert receipt_id
    assert data["dataset_reads"] == names
    assert data["result_data_status"] == "available"
    assert data["result_data"]["table"] == [
        {"source": name, "value": index} for index, name in enumerate(names, 1)
    ]
    receipt = state.tool_receipts[-1]
    assert receipt["dataset_refs"] == names
    assert set(receipt["data_identities"]) == set(names)
    assert all(receipt["data_identities"][name]["version_id"] for name in names)
    with use_agent_context(loop.context):
        claims=resolve_native_claims(session_id=loop.session_id,receipt_id=receipt_id)
        table=next(c for c in claims if c["basis_refs"][0]["result_path"]==["result_data"])
        assert table["value"]["table"]==[{"source":name,"value":index} for index,name in enumerate(names,1)]
        assert set(table["basis_refs"][0]["data_identities"])==set(names)
        loop.context.workspace.add("source_6",pd.DataFrame({"value":[99]}))
        with pytest.raises(ValueError): resolve_native_claims(session_id=loop.session_id,receipt_id=receipt_id)


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


def test_evidence_uses_current_recompute_without_erasing_old_receipt():
    loop = AgentLoop(client=object(), session_id="evidence-recompute-version")
    state = AnalysisSessionState(session_id=loop.session_id)
    loop.context.analysis_state = state
    loop.context.turn_state = TurnExecutionState()
    args = {"name": "versioned_sales", "operation": "group_aggregate"}

    with use_agent_context(loop.context):
        workspace.add("versioned_sales", pd.DataFrame({"amount": [20]}))
        workspace.derive("versioned_sales", "versioned_sum_v1", pd.DataFrame({"amount_sum": [20]}))
        old_id = loop._record_turn_tool_result(
            "transform_data", '{"dataset":"versioned_sum_v1"}', args, "first",
            structured_data={"dataset": "versioned_sum_v1", "amount_sum": 20},
        )
        workspace.archive_version("versioned_sales")
        workspace.add("versioned_sales", pd.DataFrame({"amount": [110]}))
        workspace.derive("versioned_sales", "versioned_sum_v2", pd.DataFrame({"amount_sum": [110]}))
        new_id = loop._record_turn_tool_result(
            "transform_data", '{"dataset":"versioned_sum_v2"}', args, "second",
            structured_data={"dataset": "versioned_sum_v2", "amount_sum": 110},
        )
        payload = _payload(tool_calls=["transform_data"])
        payload["dataset"] = "versioned_sum_v2"
        result = json.loads(record_evidence_record(payload))
        assert "error" not in result
        assert state.evidence_records[-1]["tool_receipt_ids"] == [new_id]
        assert [item["id"] for item in state.tool_receipts] == [old_id, new_id]

        payload["tool_receipt_ids"] = [old_id]
        rejected = json.loads(record_evidence_record(payload))
        assert rejected["error_type"] == "stale_data_binding"


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

    # A model annotation linked to an empty result cannot grant Workbench fact authority.
    assert state.verification_reports == []
    assert build_workbench_view(state)["verified_total"] == 0


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


@pytest.mark.parametrize("route", ["single", "stream", "parallel"])
@pytest.mark.parametrize("next_dataset", ["sales", "other"])
@pytest.mark.parametrize("change_source", [False, True])
def test_normal_dispatch_receipt_keeps_the_producing_step_when_tool_advances_tasks(tmp_path, monkeypatch, route, next_dataset, change_source):
    from data_agent.config import get_config
    from data_agent.session.task_manager import TaskManager
    from data_agent.agent.analysis_plan_contracts import STAGE3C0B_CONTRACT_VERSION
    from data_agent.tools.analysis_flow import record_analysis_plan
    from data_agent.tools.registry import registry
    from data_agent.llm.client import ToolCall, Response
    from data_agent.tools import discover_tools
    discover_tools()
    from tests.support.plan_inputs import bind_plan_fixture
    monkeypatch.setattr(get_config(), "sessions_dir", tmp_path / "sessions")
    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    monkeypatch.setattr("data_agent.session.task_manager.task_manager", manager)
    monkeypatch.setattr("data_agent.tools.task_tools.task_manager", manager)
    loop = AgentLoop(client=object(), session_id="dispatch-step-" + route)
    loop.context.workspace.add("sales", pd.DataFrame({"amount": [2, 3]}))
    loop.context.workspace.add("other", pd.DataFrame({"amount": [40, 50]}))
    state = loop.context.analysis_state
    state.dataset_contracts = [{"dataset": "sales", "id": "c_sales"}, {"dataset": "other", "id": "c_other"}]
    raw_plan = {"contract_version": STAGE3C0B_CONTRACT_VERSION, "requirement_revision": 0,
        "goal": "Inspect current sales and explain limitations", "visualization_strategy": [],
        "method_plan": [{"step_id": name, "goal": name, "dataset_inputs": ["sales" if name == "measure" else next_dataset],
            "combination_mode": "independent", "expected_output": name,
            "evidence_requirements": [name], "required_evidence_step_ids": [] if name == "measure" else ["measure"],
            "required_deliveries": [{"requirement_id": "rq_fixture", "kind": "measurement", "label": name, "scope": {"datasets": ['sales' if name == 'measure' else next_dataset], "quantity": "rows" if name == "measure" else "mean", **({"metrics":["amount"]} if name != "measure" else {})}}]}
            for name in ["measure", "explain"]]}
    with use_agent_context(loop.context):
        plan_result = json.loads(record_analysis_plan(bind_plan_fixture(state, raw_plan)))
    assert "error" not in plan_result, plan_result
    producing = next(t for t in manager.list_active_for_scope(session_id=loop.session_id, project_name="") if t["step_id"] == "measure")
    original_execute = registry.execute
    def execute_and_advance(name, arguments):
        result = original_execute(name, arguments)
        if name == "describe_dataset":
            if change_source:
                loop.context.workspace.add("sales", pd.DataFrame({"amount": [200, 300]}))
            assert manager.update(producing["id"], status="completed") is None
            assert loop.context.workspace_scope.step_id == "measure"
        return result
    monkeypatch.setattr(registry, "execute", execute_and_advance)
    call = ToolCall(id="step-call", name="describe_dataset", arguments={"name": "sales"})
    with use_agent_context(loop.context):
        if route == "single":
            loop._execute_single_tool(call, [call], 0)
        elif route == "stream":
            list(loop._process_tool_calls(Response(tool_calls=[call]), round_num=1))
        else:
            rows = loop._execute_tools_parallel([call])
            for tc, content, structured, binding in rows:
                loop._AgentLoop__context_operation("refresh")
                loop._record_turn_tool_result(tc.name, content, tc.arguments, tc.id, structured, execution_binding=binding)
    assert state.tool_receipts, loop.messages
    receipt = state.tool_receipts[-1]
    assert receipt["tool_name"] == "describe_dataset", loop.messages
    assert loop.context.workspace_scope.step_id == ("measure" if change_source else "explain")
    assert receipt["step_id"] == "measure"
    assert receipt["task_id"] == producing["id"]
    assert receipt["plan_sha256"] == plan_result["plan_sha256"]
    assert receipt["required_delivery_ids"] == producing["required_delivery_ids"]
    assert receipt["requirement_ids"] == [state.answer_requirements[0]["id"]]
    assert (receipt["scope_fingerprint"] != loop.context.workspace_scope.fingerprint) == (not change_source)
    if next_dataset == "other" and not change_source:
        assert loop.context.workspace.get_data_identity("sales") == {}
    with use_agent_context(loop.context):
        if change_source:
            assert "sales" not in receipt["data_identities"]
            with pytest.raises(ValueError):
                resolve_native_claims(session_id=loop.session_id, receipt_id=receipt["id"])
        else:
            assert receipt["data_identities"]["sales"]["version_id"]
            assert resolve_native_claims(session_id=loop.session_id, receipt_id=receipt["id"])
