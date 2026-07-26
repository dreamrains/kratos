from __future__ import annotations

import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import pytest

from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.context import AgentContext, use_agent_context
from data_agent.agent.execution_control import ToolExecutionBudget, TurnExecutionState
from data_agent.agent.loop import AgentLoop
from data_agent.agent.data_lineage import frame_fingerprint
from data_agent.llm.client import ToolCall
from data_agent.session.task_manager import TaskManager
from data_agent.session.workspace import Workspace
from data_agent.tools.registry import ToolCapability, ToolDefinition, ToolResult, registry


@pytest.fixture
def computation_env(tmp_path, monkeypatch):
    from data_agent import config
    from data_agent.config import AgentConfig
    import data_agent.session.task_manager as task_manager_module
    import data_agent.tools.task_tools as task_tools_module

    monkeypatch.setattr(
        config,
        "_config",
        AgentConfig(
            PROJECT_DIR=tmp_path / "project",
            SESSIONS_DIR=tmp_path / "sessions",
        ),
    )

    store = Workspace()
    source = pd.DataFrame({
        "group": ["A", "A", "B", "B"],
        "revenue": [10.0, 14.0, 8.0, 9.0],
    })
    raw = store.register_raw_snapshot("orders", source, frame_fingerprint(source))
    active = store.promote_analysis_copy(
        "orders",
        source,
        raw["dataset_id"],
        {"operation": "load_test_fixture"},
    )

    state = AnalysisSessionState(session_id="s1")
    state.dataset_contracts.append({
        "id": "contract_orders",
        "dataset": "orders",
        "quality_status": "ready",
    })
    state.set_analysis_plan({
        "contract_version": "analysis_plan.v1",
        "id": "plan_compare",
        "goal": "Compare group revenue",
        "method_plan": [{
            "step_id": "step_compare",
            "goal": "Estimate the group revenue difference",
            "dataset_inputs": ["orders"],
            "dataset_contract_ids": ["contract_orders"],
            "combination_mode": "independent",
            "expected_output": "Bound comparison evidence",
            "evidence_requirements": [
                "sample_size",
                "effect_size",
                "confidence_interval",
            ],
            "required_claim_keys": ["group_revenue_difference"],
            # Declares the tool capability the step binds to so the
            # server-owned execution envelope can deterministically bind
            # ``test_group_comparison`` calls to this step.
            "required_capability": "analysis.test_group_comparison",
        }],
        "visualization_strategy": "none",
    })

    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    workflow = manager.create_plan(
        session_id="s1",
        goal="Compare group revenue",
        source="analysis_plan",
    )
    task = manager.create(
        "Estimate the group revenue difference",
        session_id="s1",
        plan_id=workflow["id"],
        plan_version=workflow["version"],
        analysis_plan_id="plan_compare",
        step_id="step_compare",
        dataset_inputs=["orders"],
        dataset_contract_ids=["contract_orders"],
        required_claim_keys=["group_revenue_difference"],
        analysis_requirement_ids=[
            item["id"]
            for item in state.analysis_plan["analysis_requirements"]["step_compare"]
        ],
    )
    manager.update(task["id"], status="in_progress")
    monkeypatch.setattr(task_manager_module, "task_manager", manager)
    monkeypatch.setattr(task_tools_module, "task_manager", manager)

    ctx = AgentContext(session_id="s1", workspace=store, analysis_state=state)
    turn_state = TurnExecutionState(ToolExecutionBudget(max_tool_calls=10))
    turn_state.turn_id = "turn_1"
    ctx.turn_state = turn_state

    definition = ToolDefinition(
        name="test_group_comparison",
        description="Return a structured group comparison for provenance tests.",
        func=lambda name: ToolResult(
            summary="A mean 12.0; B mean 8.5; difference 3.5",
            data={
                "dataset": name,
                "effective_sample_size": {"total": 4, "groups": {"A": 2, "B": 2}},
                "effect_estimate": {"value": 3.5, "unit": "CNY", "metric": "mean_difference"},
                "confidence_interval": {"level": 0.95, "lower": 0.2, "upper": 6.8},
                "assumptions": [{
                    "name": "independence",
                    "status": "assumed",
                    "reason": "fixture rows represent separate observations",
                }, {
                    "name": "method_appropriate_for_design",
                    "status": "passed",
                    "reason": "the fixture comparison matches the declared independent-group design",
                }],
                "denominator": {"group_a": 2, "group_b": 2},
                "missingness": {
                    "group": {"missing_count": 0, "missing_rate": 0.0},
                    "revenue": {"missing_count": 0, "missing_rate": 0.0},
                },
                "estimand": {
                    "metric": "revenue",
                    "aggregation": "mean",
                    "contrast": "group_a_minus_group_b",
                },
                "sample_adequacy": {
                    "status": "adequate_with_limits",
                    "design": "independent_groups",
                    "reason": "The fixture is sufficient only for demonstrating the binding contract.",
                },
            },
        ),
        parameters={
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
        capability=ToolCapability(
            "analysis.test_group_comparison",
            category="analysis",
            output_contract={"type": "object"},
            evidence_fields=[
                "effective_sample_size",
                "effect_estimate",
                "confidence_interval",
                "assumptions",
                "denominator",
                "missingness",
                "estimand",
                "sample_adequacy",
            ],
        ),
    )
    monkeypatch.setitem(registry._tools, definition.name, definition)
    monkeypatch.setitem(registry._capabilities, definition.name, definition.capability)

    yield {
        "ctx": ctx,
        "state": state,
        "store": store,
        "active": active,
        "raw": raw,
        "manager": manager,
        "sessions_root": tmp_path / "sessions",
    }


def _execute_computation(env) -> dict:
    return _execute_tool(
        env,
        tool_call_id="call_compare",
        tool_name="test_group_comparison",
        arguments={"name": "orders"},
    )


def _execute_tool(env, *, tool_call_id: str, tool_name: str, arguments: dict) -> dict:
    loop = AgentLoop(client=object(), session_id="s1")
    loop.context = env["ctx"]
    call = ToolCall(
        id=tool_call_id,
        name=tool_name,
        arguments=arguments,
    )
    with use_agent_context(env["ctx"]):
        result = loop._execute_single_tool(
            call,
            [call],
            0,
            _scope_guard=lambda *_args: "",
        )
    assert result is None
    return env["state"].computation_refs[-1]


def _evidence_payload(env, *source_ids: str) -> dict:
    requirements = env["state"].analysis_plan["analysis_requirements"]["step_compare"]
    return {
        "contract_version": "evidence_record.v2",
        "plan_id": "plan_compare",
        "step_id": "step_compare",
        "claim_key": "group_revenue_difference",
        "claim": "Group A mean revenue exceeds group B by 3.5 CNY.",
        "dataset": "orders",
        "dataset_contract_id": "contract_orders",
        "method": "independent group mean comparison",
        "tool_calls": ["test_group_comparison"],
        "source_tool_call_ids": list(source_ids),
        "requirement_ids": [item["id"] for item in requirements],
        "result_summary": "A mean 12.0; B mean 8.5; difference 3.5",
        "sample_size": 4,
        "limitations": ["small fixture"],
        "confidence": "medium",
        "evidence_requirement": "effect_size",
        "measurements": [{
            "metric": "group_revenue_difference",
            "definition": "Group A mean minus group B mean.",
            "value": 3.5,
            "unit": "CNY",
            "grain": "row",
            "population_scope": "fixture orders",
            "time_scope": "fixture period",
            "method": "independent group mean comparison",
            "denominator": "four rows",
            "limitations": ["small fixture"],
        }],
        "statistical_support": {
            "effective_sample_size": {"total": 4, "groups": {"A": 2, "B": 2}},
            "effect_estimate": {"value": 3.5, "unit": "CNY", "metric": "mean_difference"},
            "confidence_interval": {"level": 0.95, "lower": 0.2, "upper": 6.8},
            "assumptions": [{
                "name": "independence",
                "status": "assumed",
                "reason": "fixture rows represent separate observations",
            }, {
                "name": "method_appropriate_for_design",
                "status": "passed",
                "reason": "the fixture comparison matches the declared independent-group design",
            }],
        },
    }


def _record(env, payload: dict) -> dict:
    from data_agent.tools.analysis_flow import record_evidence_record

    with use_agent_context(env["ctx"]):
        return json.loads(record_evidence_record(json.dumps(payload)))


def _artifact_path(env, ref: dict) -> Path:
    path = Path(ref["artifact_path"])
    if path.is_absolute():
        return path
    return env["sessions_root"].parent / path


def test_loop_persists_server_owned_compact_computation_ref(computation_env):
    ref = _execute_computation(computation_env)

    assert ref["contract_version"] == "computation_ref.v1"
    assert ref["session_id"] == "s1"
    assert ref["success"] is True
    assert ref["tool_call_id"] == "call_compare"
    assert ref["tool_name"] == "test_group_comparison"
    assert ref["turn_id"] == "turn_1"
    assert ref["plan_id"] == "plan_compare"
    assert ref["step_id"] == "step_compare"
    assert ref["dataset_versions"] == [computation_env["active"]["dataset_id"]]
    assert ref["arguments_digest"].startswith("sha256:")
    assert ref["output_digest"].startswith("sha256:")
    assert len(ref["arguments_digest"].removeprefix("sha256:")) == 64
    assert len(ref["output_digest"].removeprefix("sha256:")) == 64
    assert "output" not in ref
    assert "data" not in ref
    artifact = _artifact_path(computation_env, ref)
    assert artifact.is_file()
    persisted = json.loads(artifact.read_text(encoding="utf-8"))
    assert persisted["tool_call_id"] == "call_compare"
    assert persisted["output"]["data"]["effect_estimate"]["value"] == 3.5


def test_comparison_requirements_are_satisfied_by_bound_server_fields(computation_env):
    current = computation_env["state"].analysis_plan
    step = dict(current["method_plan"][0])
    step.update({
        # Keep the capability the binder matches; the test exercises the
        # additional claim_type/sampling_structure attributes, not capability
        # remapping.
        "required_capability": "analysis.test_group_comparison",
        "claim_type": "inferential",
        "sampling_structure": "independent_groups",
    })
    computation_env["state"].set_analysis_plan({
        **current,
        "method_plan": [step],
    })
    ref = _execute_computation(computation_env)
    payload = _evidence_payload(computation_env, ref["tool_call_id"])
    payload["statistical_support"].update({
        "denominator": {"group_a": 2, "group_b": 2},
        "missingness": {
            "group": {"missing_count": 0, "missing_rate": 0.0},
            "revenue": {"missing_count": 0, "missing_rate": 0.0},
        },
        "estimand": {
            "metric": "revenue",
            "aggregation": "mean",
            "contrast": "group_a_minus_group_b",
        },
        "sample_adequacy": {
            "status": "adequate_with_limits",
            "design": "independent_groups",
            "reason": "The fixture is sufficient only for demonstrating the binding contract.",
        },
    })

    result = _record(computation_env, payload)

    assert "error" not in result
    saved = computation_env["state"].evidence_records[-1]
    assert saved["denominator"] == {"group_a": 2, "group_b": 2}
    assert saved["sample_adequacy"]["status"] == "adequate_with_limits"
    assert saved["verification_level"] in {"structured_checked", "independently_recomputed"}


def test_computation_ref_records_only_datasets_named_by_the_tool_call(computation_env, monkeypatch):
    from data_agent.agent.execution_scope import WorkspaceScopeSnapshot

    other = pd.DataFrame({"group": ["C"], "revenue": [99.0]})
    other_raw = computation_env["store"].register_raw_snapshot(
        "other_orders",
        other,
        frame_fingerprint(other),
    )
    computation_env["store"].promote_analysis_copy(
        "other_orders",
        other,
        other_raw["dataset_id"],
        {"operation": "load_other_fixture"},
    )
    loop = AgentLoop(client=object(), session_id="s1")
    loop.context = computation_env["ctx"]
    call = ToolCall(
        id="call_only_orders",
        name="test_group_comparison",
        arguments={"name": "orders"},
    )
    result = registry.execute(call.name, call.arguments)
    multi_dataset_scope = WorkspaceScopeSnapshot(
        phase="execution",
        session_id="s1",
        plan_id="plan_compare",
        step_id="",
        allowed_datasets=frozenset({"orders", "other_orders"}),
        dataset_contract_ids=frozenset({"contract_orders", "contract_other"}),
        combination_mode="join",
    )

    monkeypatch.setattr(
        AgentContext,
        "workspace_scope",
        property(lambda _self: multi_dataset_scope),
    )
    loop._compact_tool_output(result, call)

    ref = computation_env["state"].computation_refs[-1]
    assert ref["step_id"] == ""
    assert ref["dataset_versions"] == [computation_env["active"]["dataset_id"]]


def test_task3_exposes_canonical_evidence_and_measurement_validators():
    from data_agent.agent.evidence_contracts import (
        validate_evidence_record,
        validate_measurement,
    )

    assert callable(validate_evidence_record)
    assert callable(validate_measurement)


def test_record_evidence_rejects_unknown_source_tool_call_id(computation_env):
    result = _record(
        computation_env,
        _evidence_payload(computation_env, "call_fabricated"),
    )

    assert result["error_type"] == "unknown_source_tool_call_id"
    assert computation_env["state"].evidence_records == []


def test_record_evidence_rejects_output_digest_mismatch(computation_env):
    ref = _execute_computation(computation_env)
    artifact = _artifact_path(computation_env, ref)
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    payload["output"]["summary"] = "tampered output"
    artifact.write_text(json.dumps(payload), encoding="utf-8")

    result = _record(
        computation_env,
        _evidence_payload(computation_env, ref["tool_call_id"]),
    )

    assert result["error_type"] == "computation_output_digest_mismatch"
    assert computation_env["state"].evidence_records == []


def test_record_evidence_rejects_stale_dataset_version(computation_env):
    ref = _execute_computation(computation_env)
    computation_env["store"].promote_analysis_copy(
        "orders",
        computation_env["store"].get("orders"),
        computation_env["raw"]["dataset_id"],
        {"operation": "intervening_change"},
    )

    result = _record(
        computation_env,
        _evidence_payload(computation_env, ref["tool_call_id"]),
    )

    assert result["error_type"] == "stale_computation_dataset_version"
    assert computation_env["state"].evidence_records == []


@pytest.mark.parametrize(
    ("field_name", "value", "error_type"),
    [
        ("dataset", "other", "evidence_dataset_outside_current_step"),
        ("dataset_contract_id", "contract_other", "evidence_contract_outside_current_step"),
        ("claim_key", "other_claim", "evidence_claim_outside_current_step"),
    ],
)
def test_record_evidence_rejects_dataset_or_contract_outside_current_step(
    computation_env,
    field_name,
    value,
    error_type,
):
    ref = _execute_computation(computation_env)
    payload = _evidence_payload(computation_env, ref["tool_call_id"])
    payload[field_name] = value

    result = _record(computation_env, payload)

    assert result["error_type"] == error_type
    assert computation_env["state"].evidence_records == []


def test_record_evidence_rejects_cross_turn_source(computation_env):
    ref = _execute_computation(computation_env)
    computation_env["ctx"].turn_state.turn_id = "turn_2"

    result = _record(
        computation_env,
        _evidence_payload(computation_env, ref["tool_call_id"]),
    )

    assert result["error_type"] == "computation_outside_current_turn"
    assert computation_env["state"].evidence_records == []


def test_record_evidence_rejects_cross_session_source(computation_env):
    ref = _execute_computation(computation_env)
    computation_env["state"].session_id = "s2"
    cross_session_ctx = AgentContext(
        session_id="s2",
        workspace=computation_env["store"],
        analysis_state=computation_env["state"],
    )
    cross_session_ctx.turn_state = computation_env["ctx"].turn_state
    computation_env["ctx"] = cross_session_ctx

    result = _record(
        computation_env,
        _evidence_payload(computation_env, ref["tool_call_id"]),
    )

    assert result["error_type"] == "computation_outside_current_session"
    assert computation_env["state"].evidence_records == []


def test_plan_scoped_live_evidence_cannot_bypass_binding_as_legacy(computation_env):
    payload = _evidence_payload(computation_env, "call_fabricated")
    payload.pop("contract_version")
    payload.pop("source_tool_call_ids")

    result = _record(computation_env, payload)

    assert result["error_type"] == "missing_source_tool_call_ids"
    assert computation_env["state"].evidence_records == []


def test_unsuccessful_tool_output_cannot_support_evidence(computation_env, monkeypatch):
    definition = ToolDefinition(
        name="test_failed_computation",
        description="Return a structured tool error.",
        func=lambda name: ToolResult(
            summary=json.dumps({"error": "calculation failed", "error_type": "test_failure"}),
            data={
                "effective_sample_size": {"total": 4, "groups": {"A": 2, "B": 2}},
                "effect_estimate": {"value": 3.5, "unit": "CNY", "metric": "mean_difference"},
                "confidence_interval": {"level": 0.95, "lower": 0.2, "upper": 6.8},
            },
        ),
        parameters={
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
        capability=ToolCapability(
            "analysis.test_failed_computation",
            category="analysis",
            output_contract={"type": "object"},
            evidence_fields=["effective_sample_size", "effect_estimate", "confidence_interval"],
        ),
    )
    monkeypatch.setitem(registry._tools, definition.name, definition)
    monkeypatch.setitem(registry._capabilities, definition.name, definition.capability)
    ref = _execute_tool(
        computation_env,
        tool_call_id="call_failed",
        tool_name=definition.name,
        arguments={"name": "orders"},
    )

    assert ref["success"] is False
    assert computation_env["ctx"].turn_state.consecutive_errors == 1
    assert computation_env["ctx"].turn_state.tool_errors[-1]["tool_name"] == definition.name
    result = _record(
        computation_env,
        _evidence_payload(computation_env, ref["tool_call_id"]),
    )

    assert result["error_type"] == "unsuccessful_computation_ref"
    assert computation_env["state"].evidence_records == []


def test_plain_text_tool_error_is_persisted_as_unsuccessful(computation_env, monkeypatch):
    definition = ToolDefinition(
        name="test_plain_error",
        description="Return a legacy plain-text error.",
        func=lambda name: ToolResult(summary="Error: calculation failed"),
        parameters={
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
        capability=ToolCapability("analysis.test_plain_error", category="analysis"),
    )
    monkeypatch.setitem(registry._tools, definition.name, definition)
    monkeypatch.setitem(registry._capabilities, definition.name, definition.capability)

    ref = _execute_tool(
        computation_env,
        tool_call_id="call_plain_error",
        tool_name=definition.name,
        arguments={"name": "orders"},
    )

    assert ref["success"] is False
    assert computation_env["ctx"].turn_state.consecutive_errors == 1
    assert computation_env["ctx"].turn_state.tool_errors[-1]["tool_name"] == definition.name


def test_plain_text_error_without_colon_cannot_support_evidence(computation_env, monkeypatch):
    definition = ToolDefinition(
        name="test_plain_error_without_colon",
        description="Return a legacy plain-text error with structured-looking data.",
        func=lambda name: ToolResult(
            summary="Error calculation failed",
            data={
                "effective_sample_size": {"total": 4, "groups": {"A": 2, "B": 2}},
                "effect_estimate": {"value": 3.5, "unit": "CNY", "metric": "mean_difference"},
                "confidence_interval": {"level": 0.95, "lower": 0.2, "upper": 6.8},
            },
        ),
        parameters={
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
        capability=ToolCapability(
            "analysis.test_plain_error_without_colon",
            category="analysis",
            output_contract={"type": "object"},
            evidence_fields=["effective_sample_size", "effect_estimate", "confidence_interval"],
        ),
    )
    monkeypatch.setitem(registry._tools, definition.name, definition)
    monkeypatch.setitem(registry._capabilities, definition.name, definition.capability)

    ref = _execute_tool(
        computation_env,
        tool_call_id="call_plain_error_without_colon",
        tool_name=definition.name,
        arguments={"name": "orders"},
    )

    assert ref["success"] is False
    assert computation_env["ctx"].turn_state.tool_errors[-1]["tool_name"] == definition.name
    result = _record(
        computation_env,
        _evidence_payload(computation_env, ref["tool_call_id"]),
    )
    assert result["error_type"] == "unsuccessful_computation_ref"


def test_json_error_key_is_unsuccessful_even_when_message_is_empty(
    computation_env,
    monkeypatch,
):
    definition = ToolDefinition(
        name="test_empty_json_error",
        description="Return an empty structured error message.",
        func=lambda name: ToolResult(summary=json.dumps({"error": ""})),
        parameters={
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
        capability=ToolCapability("analysis.test_empty_json_error", category="analysis"),
    )
    monkeypatch.setitem(registry._tools, definition.name, definition)
    monkeypatch.setitem(registry._capabilities, definition.name, definition.capability)

    ref = _execute_tool(
        computation_env,
        tool_call_id="call_empty_json_error",
        tool_name=definition.name,
        arguments={"name": "orders"},
    )

    assert ref["success"] is False
    assert computation_env["ctx"].turn_state.consecutive_errors == 1
    assert computation_env["ctx"].turn_state.tool_errors[-1]["tool_name"] == definition.name


def test_same_tool_call_id_in_later_turn_does_not_overwrite_prior_artifact(computation_env):
    from data_agent.agent.evidence_contracts import hydrate_computation_ref

    loop = AgentLoop(client=object(), session_id="s1")
    loop.context = computation_env["ctx"]
    call = ToolCall(
        id="call_compare",
        name="test_group_comparison",
        arguments={"name": "orders"},
    )
    with use_agent_context(computation_env["ctx"]):
        assert loop._execute_single_tool(call, [call], 0, _scope_guard=lambda *_args: "") is None
    first = computation_env["state"].computation_refs[-1]
    first_path = _artifact_path(computation_env, first)
    computation_env["ctx"].turn_state.turn_id = "turn_2"
    with use_agent_context(computation_env["ctx"]):
        assert loop._execute_single_tool(call, [call], 0, _scope_guard=lambda *_args: "") is None
    second = computation_env["state"].computation_refs[-1]

    assert _artifact_path(computation_env, second) != first_path
    hydrated = hydrate_computation_ref(
        first,
        sessions_root=computation_env["sessions_root"],
        current_session_id="s1",
    )
    assert hydrated["data"]["effect_estimate"]["value"] == 3.5


def test_ref_is_rejected_after_same_id_plan_semantics_change(computation_env):
    ref = _execute_computation(computation_env)
    computation_env["state"].analysis_plan["goal"] = "A semantically different analysis"

    result = _record(
        computation_env,
        _evidence_payload(computation_env, ref["tool_call_id"]),
    )

    assert result["error_type"] == "computation_outside_current_plan_revision"


def test_runtime_requirement_status_change_does_not_change_plan_semantic_revision(
    computation_env,
):
    ref = _execute_computation(computation_env)
    requirements = computation_env["state"].analysis_plan["analysis_requirements"]["step_compare"]
    for requirement in requirements:
        requirement["status"] = "satisfied"
        requirement["evidence_ids"] = ["runtime_progress_only"]

    result = _record(
        computation_env,
        _evidence_payload(computation_env, ref["tool_call_id"]),
    )

    assert result.get("error") is None, result


def test_run_python_ref_captures_actual_dataset_reads_as_traceable(
    computation_env,
    monkeypatch,
):
    import data_agent.tools.sandbox as sandbox

    monkeypatch.setattr(sandbox, "workspace", computation_env["store"])
    ref = _execute_tool(
        computation_env,
        tool_call_id="call_python",
        tool_name="run_python",
        arguments={
            "code": "get_dataset('orders')['revenue'].mean()",
            "purpose": "compute an unsupported descriptive check",
        },
    )

    assert ref["dataset_versions"] == [computation_env["active"]["dataset_id"]]
    assert ref["verification_level"] == "traceable"
    persisted = json.loads(_artifact_path(computation_env, ref).read_text(encoding="utf-8"))
    assert persisted["output"]["data"]["dataset_reads"] == ["orders"]


def test_parallel_compaction_keeps_every_computation_ref_and_valid_state_file(
    computation_env,
):
    loop = AgentLoop(client=object(), session_id="s1")
    loop.context = computation_env["ctx"]
    calls = [
        ToolCall(id=f"parallel_{index}", name="test_group_comparison", arguments={"name": "orders"})
        for index in range(4)
    ]
    results = [registry.execute(call.name, call.arguments) for call in calls]

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda pair: loop._compact_tool_output(*pair), zip(results, calls)))

    ids = {ref["tool_call_id"] for ref in computation_env["state"].computation_refs}
    assert ids == {call.id for call in calls}
    state_path = computation_env["sessions_root"] / "s1" / "analysis_state.json"
    persisted_state = json.loads(state_path.read_text(encoding="utf-8"))
    assert {ref["tool_call_id"] for ref in persisted_state["computation_refs"]} == ids


@pytest.mark.parametrize("field_name", ["computation_refs", "verification_level"])
def test_record_evidence_rejects_llm_supplied_authoritative_provenance(
    computation_env,
    field_name,
):
    ref = _execute_computation(computation_env)
    payload = _evidence_payload(computation_env, ref["tool_call_id"])
    payload[field_name] = [] if field_name == "computation_refs" else "independently_recomputed"

    result = _record(computation_env, payload)

    assert result["error_type"] == "authoritative_provenance_fields_forbidden"


def test_structured_output_is_checked_server_side_and_completes_matching_task(computation_env):
    ref = _execute_computation(computation_env)

    result = _record(
        computation_env,
        _evidence_payload(computation_env, ref["tool_call_id"]),
    )

    assert result.get("error") is None
    evidence = computation_env["state"].evidence_records[-1]
    assert evidence["verification_level"] == "structured_checked"
    assert evidence["provenance_status"] == "bound"
    assert evidence["computation_refs"][0]["verification_level"] == "structured_checked"
    assert evidence["tool_calls"] == [{
        "name": "test_group_comparison",
        "capability_id": "analysis.test_group_comparison",
        "tool_call_id": ref["tool_call_id"],
    }]
    assert evidence["method"] == "analysis.test_group_comparison"
    assert evidence["measurements"][0]["method"] == evidence["method"]
    assert evidence["measurements"][0]["unit"] == "CNY"
    assert result.get("completed_task_ids"), result
    task = computation_env["manager"].get(result["completed_task_ids"][0])
    assert task["status"] == "completed"
    assert task["satisfied_claim_keys"] == ["group_revenue_difference"]
    assert set(task["satisfied_analysis_requirement_ids"]) == set(evidence["requirement_ids"])


def test_structured_checked_trusts_only_capability_declared_fields(computation_env, monkeypatch):
    definition = ToolDefinition(
        name="test_partially_declared_output",
        description="Return more fields than the capability declares.",
        func=lambda name: ToolResult(
            summary="partial declaration",
            data={
                "effective_sample_size": {"total": 4, "groups": {"A": 2, "B": 2}},
                "effect_estimate": {"value": 3.5, "unit": "CNY", "metric": "mean_difference"},
                "confidence_interval": {"level": 0.95, "lower": 0.2, "upper": 6.8},
                "assumptions": [{
                    "name": "method_appropriate_for_design",
                    "status": "passed",
                    "reason": "declared by output but not by the capability",
                }],
            },
        ),
        parameters={
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
        capability=ToolCapability(
            "analysis.partially_declared",
            category="analysis",
            evidence_fields=["effect_estimate"],
        ),
    )
    monkeypatch.setitem(registry._tools, definition.name, definition)
    monkeypatch.setitem(registry._capabilities, definition.name, definition.capability)
    # Re-bind the plan step to the partially-declared capability so the
    # server-owned binder can attach this tool's computation to the step.
    current = computation_env["state"].analysis_plan
    step = dict(current["method_plan"][0])
    step["required_capability"] = "analysis.partially_declared"
    computation_env["state"].set_analysis_plan({**current, "method_plan": [step]})
    ref = _execute_tool(
        computation_env,
        tool_call_id="call_partial",
        tool_name=definition.name,
        arguments={"name": "orders"},
    )

    result = _record(
        computation_env,
        _evidence_payload(computation_env, ref["tool_call_id"]),
    )

    assert ref["structured_checked_fields"] == ["effect_estimate"]
    assert result["error_type"] in {
        "unverified_assumption_check",
        "unsatisfied_analysis_requirements",
    }


def test_llm_cannot_upgrade_an_unchecked_assumption_to_passed(computation_env):
    ref = _execute_computation(computation_env)
    payload = _evidence_payload(computation_env, ref["tool_call_id"])
    payload["statistical_support"]["assumptions"][1]["reason"] = "model-authored substitute"

    result = _record(computation_env, payload)

    assert result["error_type"] == "statistical_support_mismatch"


def test_native_ab_test_is_independently_recomputed_and_projects_significance(
    computation_env,
    monkeypatch,
):
    import data_agent.tools._utils as tool_utils
    import data_agent.tools.statistics  # noqa: F401

    computation_env["state"].set_analysis_plan({
        "contract_version": "analysis_plan.v1",
        "id": "plan_compare",
        "goal": "Test whether group revenue differs",
        "method_plan": [{
            "step_id": "step_compare",
            "goal": "Run a two-group statistical test",
            "dataset_inputs": ["orders"],
            "dataset_contract_ids": ["contract_orders"],
            "combination_mode": "independent",
            "expected_output": "Bound inferential evidence",
            "evidence_requirements": ["sample_size", "effect_size"],
            "required_claim_keys": ["group_revenue_difference"],
        }],
        "visualization_strategy": "none",
    })
    monkeypatch.setattr(tool_utils, "workspace", computation_env["store"])
    ref = _execute_tool(
        computation_env,
        tool_call_id="call_native_ab",
        tool_name="ab_test",
        arguments={
            "name": "orders",
            "group_col": "group",
            "metric_col": "revenue",
            "method": "ttest",
        },
    )
    persisted = json.loads(_artifact_path(computation_env, ref).read_text(encoding="utf-8"))
    native = persisted["output"]["data"]
    assert {"confidence_interval", "test"} <= set(ref["structured_checked_fields"]), ref
    payload = _evidence_payload(computation_env, ref["tool_call_id"])
    payload["method"] = "welch t-test"
    payload["measurements"][0]["value"] = native["difference"]["absolute"]
    payload["measurements"][0]["unit"] = "unspecified"
    payload["claim"] = (
        f"The t-test bound mean-difference magnitude is {abs(native['difference']['absolute'])}."
    )
    payload["result_summary"] = payload["claim"]
    payload["statistical_support"] = {
        "effective_sample_size": {
            "total": sum(group["n"] for group in native["groups"].values()),
            "groups": {name: group["n"] for name, group in native["groups"].items()},
        },
        "effect_estimate": {
            "value": native["difference"]["absolute"],
            "metric": "mean_difference",
        },
        "test": native["test"],
    }

    result = _record(computation_env, payload)

    assert result.get("error") is None, result
    evidence = computation_env["state"].evidence_records[-1]
    assert evidence["verification_level"] == "independently_recomputed"
    assert evidence["significance"] == native["test"]
    assert evidence["assumption_checks"] == native["assumptions"]


def test_native_mann_whitney_rank_effect_is_independently_recomputed(
    computation_env,
    monkeypatch,
):
    import data_agent.tools._utils as tool_utils
    import data_agent.tools.statistics  # noqa: F401

    computation_env["state"].set_analysis_plan({
        "contract_version": "analysis_plan.v1",
        "id": "plan_compare",
        "goal": "Test whether group revenue distributions differ",
        "method_plan": [{
            "step_id": "step_compare",
            "goal": "Run a two-group rank test",
            "dataset_inputs": ["orders"],
            "dataset_contract_ids": ["contract_orders"],
            "combination_mode": "independent",
            "expected_output": "Bound rank-based evidence",
            "evidence_requirements": ["sample_size", "effect_size"],
            "required_claim_keys": ["group_revenue_difference"],
        }],
        "visualization_strategy": "none",
    })
    monkeypatch.setattr(tool_utils, "workspace", computation_env["store"])
    ref = _execute_tool(
        computation_env,
        tool_call_id="call_native_mw",
        tool_name="ab_test",
        arguments={
            "name": "orders",
            "group_col": "group",
            "metric_col": "revenue",
            "method": "mannwhitneyu",
        },
    )
    persisted = json.loads(_artifact_path(computation_env, ref).read_text(encoding="utf-8"))
    native = persisted["output"]["data"]
    payload = _evidence_payload(computation_env, ref["tool_call_id"])
    payload["method"] = "Mann-Whitney U"
    payload["tool_calls"] = ["ab_test"]
    payload["claim"] = f"The rank-biserial effect is {native['effect_estimate']['value']}."
    payload["result_summary"] = payload["claim"]
    payload["measurements"][0].update({
        "definition": "Treatment stochastic superiority minus reverse superiority.",
        "value": native["effect_estimate"]["value"],
        "unit": "unitless",
        "method": "Mann-Whitney U",
    })
    payload["statistical_support"] = {
        "effective_sample_size": native["effective_sample_size"],
        "effect_estimate": native["effect_estimate"],
        "test": native["test"],
    }

    result = _record(computation_env, payload)

    assert result.get("error") is None, result
    saved = computation_env["state"].evidence_records[-1]
    assert saved["effect_estimate"]["metric"] == "rank_biserial_correlation"
    assert saved["verification_level"] == "independently_recomputed"


def test_monthly_seasonality_requirement_rejects_annual_tool_evidence(
    computation_env,
    monkeypatch,
):
    import data_agent.tools._utils as tool_utils
    import data_agent.tools.eda  # noqa: F401

    seasonal = pd.DataFrame({
        "date": pd.date_range("2025-01-01", periods=60, freq="D"),
        "revenue": range(60),
    })
    active = computation_env["store"].promote_analysis_copy(
        "orders",
        seasonal,
        computation_env["raw"]["dataset_id"],
        {"operation": "seasonality_fixture"},
    )
    computation_env["active"] = active
    computation_env["state"].set_analysis_plan({
        "contract_version": "analysis_plan.v1",
        "id": "plan_compare",
        "goal": "Assess monthly seasonality",
        "method_plan": [{
            "step_id": "step_compare",
            "goal": "Assess monthly seasonality",
            "required_capability": "analysis.time_series",
            "claim_type": "seasonality",
            "seasonality_period": "monthly",
            "dataset_inputs": ["orders"],
            "dataset_contract_ids": ["contract_orders"],
            "combination_mode": "independent",
            "expected_output": "Monthly seasonality estimability",
            "evidence_requirements": ["seasonality_estimability"],
            "required_claim_keys": ["group_revenue_difference"],
        }],
        "visualization_strategy": "none",
    })
    monkeypatch.setattr(tool_utils, "workspace", computation_env["store"])
    ref = _execute_tool(
        computation_env,
        tool_call_id="call_annual_for_monthly",
        tool_name="analyze_time_series",
        arguments={
            "name": "orders",
            "date_col": "date",
            "value_col": "revenue",
            "seasonality_period": "annual",
        },
    )
    native = json.loads(_artifact_path(computation_env, ref).read_text(encoding="utf-8"))[
        "output"
    ]["data"]
    payload = _evidence_payload(computation_env, ref["tool_call_id"])
    payload.update({
        "claim": "The requested seasonality estimability was assessed.",
        "result_summary": "A server-bound seasonality assessment is available.",
        "method": "time series analysis",
        "tool_calls": ["analyze_time_series"],
        "evidence_requirement": "seasonality_estimability",
        "statistical_support": {
            field: native[field]
            for field in (
                "time_frequency", "missing_intervals", "window_comparability",
                "autocorrelation_awareness", "effective_sample_size", "missingness",
                "assumptions", "seasonality_estimability",
            )
        },
        "sample_size": native["effective_sample_size"]["total"],
    })
    payload["measurements"][0].update({
        "definition": "Seasonality estimability status.",
        "value": "not_estimable",
        "unit": "status",
        "method": "time series analysis",
    })

    result = _record(computation_env, payload)

    assert result["error_type"] == "unsatisfied_analysis_requirements", result


def test_native_ab_test_satisfies_full_comparison_contract(computation_env, monkeypatch):
    import data_agent.tools._utils as tool_utils
    import data_agent.tools.statistics  # noqa: F401

    computation_env["state"].set_analysis_plan({
        "contract_version": "analysis_plan.v1",
        "id": "plan_compare",
        "goal": "Test and quantify a two-group revenue difference",
        "method_plan": [{
            "step_id": "step_compare",
            "goal": "Run a bounded two-group comparison",
            "required_capability": "analysis.experiment",
            "claim_type": "inferential",
            "sampling_structure": "independent_groups",
            "dataset_inputs": ["orders"],
            "dataset_contract_ids": ["contract_orders"],
            "combination_mode": "independent",
            "expected_output": "Effect magnitude, interval, and method support",
            "evidence_requirements": [
                "effective_sample_size", "denominator", "missingness", "estimand",
                "effect_estimate", "confidence_interval", "calculation_method",
                "assumptions", "sample_adequacy", "significance",
            ],
            "required_claim_keys": ["group_revenue_difference"],
        }],
        "visualization_strategy": "none",
    })
    monkeypatch.setattr(tool_utils, "workspace", computation_env["store"])
    ref = _execute_tool(
        computation_env,
        tool_call_id="call_native_ab_full",
        tool_name="ab_test",
        arguments={
            "name": "orders",
            "group_col": "group",
            "metric_col": "revenue",
            "method": "ttest",
        },
    )
    persisted = json.loads(_artifact_path(computation_env, ref).read_text(encoding="utf-8"))
    native = persisted["output"]["data"]
    payload = _evidence_payload(computation_env, ref["tool_call_id"])
    payload["claim"] = f"The bounded mean difference is {native['effect_estimate']['value']}."
    payload["result_summary"] = payload["claim"]
    payload["measurements"][0].update({
        "value": native["effect_estimate"]["value"],
        "unit": "unspecified",
    })
    payload["evidence_requirement"] = "effect_estimate"
    payload["statistical_support"] = {
        field: native[field]
        for field in (
            "effective_sample_size", "denominator", "missingness", "estimand",
            "effect_estimate", "confidence_interval", "test", "assumptions",
            "sample_adequacy",
        )
    }

    result = _record(computation_env, payload)

    assert result.get("error") is None, result
    saved = computation_env["state"].evidence_records[-1]
    assert saved["confidence_interval"] == native["confidence_interval"]
    assert saved["sample_adequacy"] == native["sample_adequacy"]
    assert saved["verification_level"] == "structured_checked"


def test_model_authored_correlation_cannot_satisfy_canonical_requirement(computation_env):
    computation_env["state"].set_analysis_plan({
        "contract_version": "analysis_plan.v1",
        "id": "plan_compare",
        "goal": "Measure a correlation",
        "method_plan": [{
            "step_id": "step_compare",
            "goal": "Measure a correlation",
            "dataset_inputs": ["orders"],
            "dataset_contract_ids": ["contract_orders"],
            "combination_mode": "independent",
            "expected_output": "Bound correlation evidence",
            "evidence_requirements": ["correlation"],
            "required_claim_keys": ["group_revenue_difference"],
            # Bind to the fixture tool's capability so the server-owned
            # envelope can attach this tool's computation to the step.
            "required_capability": "analysis.test_group_comparison",
        }],
        "visualization_strategy": "none",
    })
    ref = _execute_computation(computation_env)
    payload = _evidence_payload(computation_env, ref["tool_call_id"])
    payload["evidence_requirement"] = "correlation"
    payload["claim"] = "Correlation support was requested."
    payload["result_summary"] = "No authoritative correlation was returned."
    payload["measurements"][0].update({
        "metric": "correlation",
        "value": "not available",
        "unit": "unitless",
    })
    payload["correlation"] = {"correlation": 0.9, "variables": ["group", "revenue"]}
    payload["assumption_checks"] = [{
        "name": "correlation_method_appropriate",
        "status": "passed",
        "reason": "model-authored",
    }]
    payload["statistical_support"] = {
        "correlation": payload["correlation"],
        "assumptions": payload["assumption_checks"],
    }

    result = _record(computation_env, payload)

    assert result["error_type"] in {
        "statistical_support_mismatch",
        "unsatisfied_analysis_requirements",
        "unverified_assumption_check",
    }


def test_v2_validator_does_not_blanket_require_statistical_support(computation_env):
    from data_agent.agent.evidence_contracts import validate_evidence_record

    ref = _execute_computation(computation_env)
    result = _record(computation_env, _evidence_payload(computation_env, ref["tool_call_id"]))
    assert result.get("error") is None
    record = dict(computation_env["state"].evidence_records[-1])
    record.pop("statistical_support", None)

    validation = validate_evidence_record(record, current_plan_id="plan_compare")

    assert validation.ok


def test_record_evidence_rejects_statistical_support_that_differs_from_tool_output(
    computation_env,
):
    ref = _execute_computation(computation_env)
    payload = _evidence_payload(computation_env, ref["tool_call_id"])
    payload["statistical_support"]["effect_estimate"]["value"] = 999.0

    result = _record(computation_env, payload)

    assert result["error_type"] == "statistical_support_mismatch"
    assert computation_env["state"].evidence_records == []


def test_bound_evidence_rejects_claim_and_measurement_numbers_not_in_computation(
    computation_env,
):
    ref = _execute_computation(computation_env)
    payload = _evidence_payload(computation_env, ref["tool_call_id"])
    payload["claim"] = "Group A exceeds group B by 350 CNY."
    payload["result_summary"] = "difference=350"
    payload["measurements"][0]["value"] = 350.0

    result = _record(computation_env, payload)

    assert result["error_type"] == "numeric_evidence_mismatch"


def test_sample_size_number_cannot_masquerade_as_effect_size(computation_env):
    ref = _execute_computation(computation_env)
    payload = _evidence_payload(computation_env, ref["tool_call_id"])
    payload["claim"] = "Group A exceeds group B by 4 CNY."
    payload["result_summary"] = "difference=4 CNY"
    payload["measurements"][0]["value"] = 4

    result = _record(computation_env, payload)

    assert result["error_type"] == "numeric_evidence_mismatch"


def test_small_integer_effect_claim_is_not_ignored(computation_env):
    ref = _execute_computation(computation_env)
    payload = _evidence_payload(computation_env, ref["tool_call_id"])
    payload["claim"] = "The group difference is 4."
    payload["result_summary"] = "difference=4"
    payload["measurements"][0]["value"] = 4

    result = _record(computation_env, payload)

    assert result["error_type"] == "numeric_evidence_mismatch"


def test_model_cannot_change_authoritative_measurement_unit(computation_env):
    ref = _execute_computation(computation_env)
    payload = _evidence_payload(computation_env, ref["tool_call_id"])
    payload["claim"] = "Group A exceeds group B by 3.5 USD."
    payload["result_summary"] = "difference=3.5 USD"
    payload["measurements"][0]["unit"] = "USD"

    result = _record(computation_env, payload)

    assert result["error_type"] == "evidence_unit_mismatch"


def test_model_cannot_relabel_tool_method_or_claim_as_causal(computation_env):
    ref = _execute_computation(computation_env)
    payload = _evidence_payload(computation_env, ref["tool_call_id"])
    payload["claim"] = "Randomized treatment caused higher revenue."
    payload["method"] = "randomized causal experiment"
    payload["tool_calls"] = ["ab_test"]
    payload["measurements"][0]["method"] = "randomized causal experiment"

    result = _record(computation_env, payload)

    assert result["error_type"] == "unsupported_claim_semantics"


def test_model_cannot_relabel_comparison_as_prediction(computation_env):
    ref = _execute_computation(computation_env)
    payload = _evidence_payload(computation_env, ref["tool_call_id"])
    payload["claim"] = "A forecasting model predicts group A will exceed group B by 3.5 CNY."

    result = _record(computation_env, payload)

    assert result["error_type"] == "unsupported_claim_semantics"


def test_model_cannot_relabel_comparison_as_chinese_prediction(computation_env):
    ref = _execute_computation(computation_env)
    payload = _evidence_payload(computation_env, ref["tool_call_id"])
    payload["claim"] = "预测模型显示A组将比B组高3.5 CNY。"

    result = _record(computation_env, payload)

    assert result["error_type"] == "unsupported_claim_semantics"


def test_model_cannot_relabel_comparison_as_chinese_association(computation_env):
    ref = _execute_computation(computation_env)
    payload = _evidence_payload(computation_env, ref["tool_call_id"])
    payload["claim"] = "A组与更高收入相关，差异为3.5 CNY。"

    result = _record(computation_env, payload)

    assert result["error_type"] == "unsupported_claim_semantics"


def test_model_cannot_claim_unexecuted_statistical_method(computation_env):
    ref = _execute_computation(computation_env)
    payload = _evidence_payload(computation_env, ref["tool_call_id"])
    payload["claim"] = "A Mann-Whitney U test found a 3.5 CNY difference."

    result = _record(computation_env, payload)

    assert result["error_type"] == "unsupported_claim_semantics"


def test_model_cannot_claim_unknown_unexecuted_test_method(computation_env):
    ref = _execute_computation(computation_env)
    payload = _evidence_payload(computation_env, ref["tool_call_id"])
    payload["claim"] = "Bootstrap test found a 3.5 CNY difference."

    result = _record(computation_env, payload)

    assert result["error_type"] == "unsupported_claim_semantics"


def test_claim_semantics_bind_ttest_design_and_variance_qualifiers():
    from data_agent.agent.evidence_contracts import _unsupported_claim_semantics

    trusted = {
        "capability_ids": {"analysis.experiment"},
        "tool_names": {"ab_test"},
        "method_tokens": {"ttest", "welch", "independent"},
    }

    assert _unsupported_claim_semantics("A paired t-test found a difference.", **trusted).startswith(
        "unsupported_method_qualifier:paired"
    )
    assert _unsupported_claim_semantics("A Student's t-test found a difference.", **trusted).startswith(
        "unsupported_method_qualifier:student"
    )
    assert _unsupported_claim_semantics("A Welch t-test found a difference.", **trusted) == ""
    assert _unsupported_claim_semantics("An independent t-test found a difference.", **trusted) == ""
    assert _unsupported_claim_semantics("Independent samples t-test found a difference.", **trusted) == ""
    assert _unsupported_claim_semantics("配对 t检验发现差异。", **trusted).startswith(
        "unsupported_method_qualifier:paired"
    )
    assert _unsupported_claim_semantics("配对样本 t 检验发现差异。", **trusted).startswith(
        "unsupported_method_qualifier:paired"
    )
    assert _unsupported_claim_semantics("采用配对的 t 检验发现差异。", **trusted).startswith(
        "unsupported_method_qualifier:paired"
    )
    assert _unsupported_claim_semantics("重复测量 t 检验发现差异。", **trusted).startswith(
        "unknown_method_qualifier:重复测量"
    )
    assert _unsupported_claim_semantics("Student's t 检验发现差异。", **trusted).startswith(
        "unsupported_method_qualifier:student"
    )
    assert _unsupported_claim_semantics("独立样本 t 检验发现差异。", **trusted) == ""
    assert _unsupported_claim_semantics("等方差 t 检验发现差异。", **trusted).startswith(
        "unsupported_method_qualifier:student"
    )
    assert _unsupported_claim_semantics("异方差 t 检验发现差异。", **trusted) == ""
    assert _unsupported_claim_semantics("不等方差 t 检验发现差异。", **trusted) == ""
    assert _unsupported_claim_semantics("方差不齐 t 检验发现差异。", **trusted) == ""
    assert _unsupported_claim_semantics("非配对 t 检验发现差异。", **trusted) == ""

    student_trusted = {
        **trusted,
        "method_tokens": {"ttest", "student", "independent"},
    }
    assert _unsupported_claim_semantics("等方差 t 检验发现差异。", **student_trusted) == ""
    assert _unsupported_claim_semantics("不等方差 t 检验发现差异。", **student_trusted).startswith(
        "unsupported_method_qualifier:welch"
    )


@pytest.mark.parametrize(
    "claim",
    [
        "The test dataset shows a 3.5 CNY difference.",
        "The model-free comparison shows a 3.5 CNY difference.",
        "No predictive model was used; the observed difference is 3.5 CNY.",
        "未采用不等方差 t检验；观测差异为3.5 CNY。",
    ],
)
def test_claim_semantics_do_not_reject_non_method_or_negated_disclosures(claim):
    from data_agent.agent.evidence_contracts import _unsupported_claim_semantics

    assert _unsupported_claim_semantics(
        claim,
        capability_ids={"analysis.test_group_comparison"},
        tool_names={"test_group_comparison"},
        method_tokens=set(),
    ) == ""


def test_incremental_requirement_evidence_remains_fully_traceable(computation_env):
    ref = _execute_computation(computation_env)
    requirements = {
        item["name"]: item
        for item in computation_env["state"].analysis_plan["analysis_requirements"]["step_compare"]
    }
    cases = [
        ("sample_size", "Sample size is 4 observations.", 4, "observations"),
        ("effect_size", "The group difference is 3.5 CNY.", 3.5, "CNY"),
        (
            "confidence_interval",
            "The 95% interval lower bound is 0.2 CNY.",
            0.2,
            "CNY",
        ),
    ]

    for name, claim, value, unit in cases:
        payload = _evidence_payload(computation_env, ref["tool_call_id"])
        payload["requirement_ids"] = [requirements[name]["id"]]
        payload["evidence_requirement"] = name
        payload["claim"] = claim
        payload["result_summary"] = claim
        payload["measurements"][0].update({
            "metric": name,
            "value": value,
            "unit": unit,
        })
        result = _record(computation_env, payload)
        assert result.get("error") is None, result

    evidence_records = computation_env["state"].evidence_records
    assert len(evidence_records) == 3
    assert len({item["id"] for item in evidence_records}) == 3
    assert {
        requirement_id
        for record in evidence_records
        for requirement_id in record["requirement_ids"]
    } == {item["id"] for item in requirements.values()}
    task = computation_env["manager"].list_for_scope(session_id="s1")[0]
    assert task["status"] == "completed"


def test_model_authored_unknown_requirement_field_cannot_satisfy_plan(computation_env):
    computation_env["state"].set_analysis_plan({
        "contract_version": "analysis_plan.v1",
        "id": "plan_compare",
        "goal": "Describe revenue availability",
        "method_plan": [{
            "step_id": "step_compare",
            "goal": "Record a revenue field",
            "dataset_inputs": ["orders"],
            "dataset_contract_ids": ["contract_orders"],
            "combination_mode": "independent",
            "expected_output": "Bound revenue evidence",
            "evidence_requirements": ["revenue"],
            "required_claim_keys": ["group_revenue_difference"],
            # Bind to the fixture tool's capability so the server-owned
            # envelope can attach this tool's computation to the step.
            "required_capability": "analysis.test_group_comparison",
        }],
        "visualization_strategy": "none",
    })
    ref = _execute_computation(computation_env)
    payload = _evidence_payload(computation_env, ref["tool_call_id"])
    payload["claim"] = "Revenue availability was assessed."
    payload["result_summary"] = "Revenue field is available."
    payload["evidence_requirement"] = "revenue"
    payload["measurements"][0]["value"] = "available"
    payload["revenue"] = "model-authored"
    payload.pop("statistical_support")

    result = _record(computation_env, payload)

    assert result["error_type"] == "unsatisfied_analysis_requirements"


def test_one_record_may_satisfy_only_a_subset_of_step_requirements(computation_env):
    ref = _execute_computation(computation_env)
    requirements = computation_env["state"].analysis_plan["analysis_requirements"]["step_compare"]
    sample_requirement = next(item for item in requirements if item["name"] == "sample_size")
    payload = _evidence_payload(computation_env, ref["tool_call_id"])
    payload["requirement_ids"] = [sample_requirement["id"]]
    payload["evidence_requirement"] = "sample_size"
    payload["claim"] = "Sample size is 4 observations."
    payload["result_summary"] = payload["claim"]
    payload["measurements"][0].update({
        "metric": "sample_size",
        "value": 4,
        "unit": "observations",
    })

    result = _record(computation_env, payload)

    assert result.get("error") is None, result
    assert not result.get("completed_task_ids")
    task = computation_env["manager"].list_for_scope(session_id="s1")[0]
    assert task["status"] == "in_progress"
    assert task["satisfied_analysis_requirement_ids"] == [sample_requirement["id"]]


def test_record_evidence_rejects_unsatisfied_compiled_assumption_check(computation_env):
    ref = _execute_computation(computation_env)
    payload = _evidence_payload(computation_env, ref["tool_call_id"])
    payload["statistical_support"]["assumptions"] = [{
        "name": "independence",
        "status": "assumed",
        "reason": "not enough to satisfy the compiled method check",
    }]

    result = _record(computation_env, payload)

    assert result["error_type"] in {
        "statistical_support_mismatch",
        "unsatisfied_analysis_requirements",
    }


def test_restart_hydrates_verified_artifact_without_putting_full_output_in_state(
    computation_env,
):
    from data_agent.agent.analysis_state import load_analysis_state
    from data_agent.agent.evidence_contracts import hydrate_computation_ref

    ref = _execute_computation(computation_env)
    computation_env["state"].save()
    restarted = load_analysis_state("s1")

    assert restarted.computation_refs == [ref]
    assert "A mean 12.0" not in json.dumps(restarted.to_dict())
    hydrated = hydrate_computation_ref(
        restarted.computation_refs[0],
        sessions_root=computation_env["sessions_root"],
    )
    assert hydrated["summary"].startswith("A mean 12.0")
    assert hydrated["data"]["effect_estimate"]["value"] == 3.5


def test_computation_ref_survives_actual_prompt_compaction_and_restart(computation_env):
    from types import SimpleNamespace

    from data_agent.agent.analysis_state import load_analysis_state
    from data_agent.agent.compact import CompactState, compact_history
    from data_agent.agent.evidence_contracts import hydrate_computation_ref

    ref = _execute_computation(computation_env)
    before = json.loads(json.dumps(computation_env["state"].computation_refs))
    messages = [
        {"role": "user", "content": f"early message {index}"}
        for index in range(15)
    ]
    messages[1] = {
        "role": "tool",
        "tool_call_id": ref["tool_call_id"],
        "content": "A mean 12.0; B mean 8.5; difference 3.5",
    }
    fake_client = SimpleNamespace(
        chat=lambda **_kwargs: SimpleNamespace(text="Earlier computation output was compacted."),
    )

    compacted = compact_history(
        "s1",
        fake_client,
        messages,
        CompactState(),
        token_threshold=0,
    )
    restarted = load_analysis_state("s1")

    assert len(compacted) < len(messages)
    assert computation_env["state"].computation_refs == before
    assert restarted.computation_refs == before
    hydrated = hydrate_computation_ref(
        restarted.computation_refs[0],
        sessions_root=computation_env["sessions_root"],
        current_session_id="s1",
    )
    assert hydrated["data"]["effect_estimate"]["value"] == 3.5


def test_saved_legacy_evidence_is_normalized_as_unbound_and_cannot_confirm_inference():
    from data_agent.agent.verification import verify_analysis_claims

    restarted = AnalysisSessionState.from_dict({
        "session_id": "legacy_evidence",
        "analysis_plan": {"id": "plan_legacy"},
        "evidence_records": [{
            "id": "ev_legacy",
            "plan_id": "plan_legacy",
            "claim": "The treatment effect is statistically significant.",
            "dataset": "orders",
            "method": "ab_test",
            "sample_size": 200,
            "time_scope": "2026-06",
            "calculation_method": "Welch t-test",
            "method_detail": "legacy persisted output",
            "limitations": ["legacy evidence"],
            "confidence": "high",
        }],
    }, "legacy_evidence")

    evidence = restarted.evidence_records[0]
    assert evidence["provenance_status"] == "legacy_unbound"
    assert evidence["verification_level"] == "legacy_unbound"
    report = verify_analysis_claims(
        claims=[{"text": evidence["claim"], "evidence_id": evidence["id"]}],
        evidence_records=restarted.evidence_records,
        route_proposals=[],
        cleaning_logs=[],
        current_plan_id="plan_legacy",
    )
    assert report["overall_status"] == "pass_with_downgrades"
    assert report["claim_checks"][0]["strength"] != "confirmed"
    assert any("legacy_unbound" in issue for issue in report["claim_checks"][0]["issues"])


def test_supported_native_statistic_is_independently_recomputed_from_exact_version(
    computation_env,
    monkeypatch,
):
    definition = ToolDefinition(
        name="test_recomputable_group_mean",
        description="Trusted structured mean-difference tool.",
        func=lambda name, group_col, metric_col: ToolResult(
            summary="A mean 12.0; B mean 8.5; difference 3.5",
            data={
                "effective_sample_size": {"total": 4, "groups": {"A": 2, "B": 2}},
                "effect_estimate": {"value": 3.5, "unit": "CNY", "metric": "mean_difference"},
                "confidence_interval": {"level": 0.95, "lower": 0.2, "upper": 6.8},
                "assumptions": [{
                    "name": "independence",
                    "status": "assumed",
                    "reason": "fixture rows represent separate observations",
                }, {
                    "name": "method_appropriate_for_design",
                    "status": "passed",
                    "reason": "the fixture comparison matches the declared independent-group design",
                }],
                "recomputation_spec": {
                    "operation": "group_mean_difference",
                    "dataset": name,
                    "group_column": group_col,
                    "metric_column": metric_col,
                    "left_group": "A",
                    "right_group": "B",
                },
            },
        ),
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "group_col": {"type": "string"},
                "metric_col": {"type": "string"},
            },
            "required": ["name", "group_col", "metric_col"],
        },
        capability=ToolCapability(
            "analysis.group_mean_difference",
            category="analysis",
            evidence_fields=[
                "effective_sample_size",
                "effect_estimate",
                "confidence_interval",
                "assumptions",
            ],
        ),
    )
    monkeypatch.setitem(registry._tools, definition.name, definition)
    monkeypatch.setitem(registry._capabilities, definition.name, definition.capability)
    # Re-bind the plan step to the recomputable capability so the
    # server-owned envelope can attach this tool's computation to the step.
    current = computation_env["state"].analysis_plan
    step = dict(current["method_plan"][0])
    step["required_capability"] = "analysis.group_mean_difference"
    computation_env["state"].set_analysis_plan({**current, "method_plan": [step]})
    ref = _execute_tool(
        computation_env,
        tool_call_id="call_recomputed",
        tool_name=definition.name,
        arguments={"name": "orders", "group_col": "group", "metric_col": "revenue"},
    )

    result = _record(
        computation_env,
        _evidence_payload(computation_env, ref["tool_call_id"]),
    )

    assert result.get("error") is None
    evidence = computation_env["state"].evidence_records[-1]
    assert evidence["verification_level"] == "structured_checked"
    assert evidence["computation_refs"][0]["verification_level"] == "independently_recomputed"


def test_invalid_structured_statistics_remain_only_traceable(
    computation_env,
    monkeypatch,
):
    definition = ToolDefinition(
        name="test_invalid_structured_stats",
        description="Return malformed structured statistics.",
        func=lambda name: ToolResult(
            summary="Malformed statistics",
            data={
                "effective_sample_size": {"total": -4},
                "effect_estimate": {"value": "not-a-number", "unit": "CNY", "metric": "mean_difference"},
                "confidence_interval": {"level": 1.5, "lower": 9.0, "upper": 2.0},
            },
        ),
        parameters={"type": "object", "properties": {}},
        capability=ToolCapability(
            "analysis.invalid_stats_fixture",
            category="analysis",
            evidence_fields=["effective_sample_size", "effect_estimate", "confidence_interval"],
        ),
    )
    monkeypatch.setitem(registry._tools, definition.name, definition)
    monkeypatch.setitem(registry._capabilities, definition.name, definition.capability)

    ref = _execute_tool(
        computation_env,
        tool_call_id="call_invalid_stats",
        tool_name=definition.name,
        arguments={"name": "orders"},
    )

    assert ref["verification_level"] == "traceable"


def test_evidence_v2_identity_is_collision_safe_for_distinct_exact_claim_keys(computation_env):
    from data_agent.agent.evidence_contracts import evidence_v2_id_for

    first = evidence_v2_id_for("plan_compare", "step_compare", "group-revenue-difference")
    second = evidence_v2_id_for("plan_compare", "step_compare", "group revenue difference")

    assert first.startswith("evidence_")
    assert second.startswith("evidence_")
    assert first != second


def test_traceable_hash_alone_cannot_confirm_high_confidence_inference(
    computation_env,
    monkeypatch,
):
    from data_agent.agent.verification import verify_analysis_claims

    definition = ToolDefinition(
        name="test_freeform_result",
        description="Free-form result with no structured output contract.",
        func=lambda name: "A free-form calculation says the difference is 3.5.",
        parameters={"type": "object", "properties": {}},
        capability=ToolCapability("fallback.test_freeform", category="fallback"),
    )
    monkeypatch.setitem(registry._tools, definition.name, definition)
    monkeypatch.setitem(registry._capabilities, definition.name, definition.capability)
    ref = _execute_tool(
        computation_env,
        tool_call_id="call_freeform",
        tool_name=definition.name,
        arguments={"name": "orders"},
    )
    evidence = _evidence_payload(computation_env, ref["tool_call_id"])
    evidence.update({
        "id": "evidence_traceable",
        "confidence": "high",
        "method": "ab_test",
        "time_scope": "fixture period",
        "calculation_method": "free-form calculation",
        "method_detail": "unstructured fallback output",
        "provenance_status": "bound",
        "verification_level": "traceable",
        "computation_refs": [ref],
    })

    report = verify_analysis_claims(
        claims=[{"text": evidence["claim"], "evidence_id": evidence["id"]}],
        evidence_records=[evidence],
        route_proposals=[],
        cleaning_logs=[],
        current_plan_id="plan_compare",
    )
    assert report["overall_status"] == "pass_with_downgrades"
    assert report["claim_checks"][0]["strength"] != "confirmed"
    assert any("traceable" in issue for issue in report["claim_checks"][0]["issues"])


def test_evidence_becomes_stale_after_incompatible_dataset_promotion(computation_env):
    from data_agent.agent.verification import verify_analysis_claims

    ref = _execute_computation(computation_env)
    result = _record(
        computation_env,
        _evidence_payload(computation_env, ref["tool_call_id"]),
    )
    assert result.get("error") is None
    evidence = computation_env["state"].evidence_records[-1]
    promoted = computation_env["store"].promote_analysis_copy(
        "orders",
        computation_env["store"].get("orders"),
        computation_env["raw"]["dataset_id"],
        {"operation": "incompatible_change"},
    )

    report = verify_analysis_claims(
        claims=[{"text": evidence["claim"], "evidence_id": evidence["id"]}],
        evidence_records=[evidence],
        route_proposals=[],
        cleaning_logs=[],
        current_plan_id="plan_compare",
        current_dataset_versions=[promoted["dataset_id"]],
    )

    assert report["overall_status"] == "fail"
    assert report["claim_checks"][0]["strength"] == "unsupported"
    assert any("stale dataset version" in issue.lower() for issue in report["claim_checks"][0]["issues"])


def test_verification_rechecks_artifact_digest_after_evidence_was_recorded(computation_env):
    from data_agent.agent.verification import verify_analysis_claims

    ref = _execute_computation(computation_env)
    result = _record(
        computation_env,
        _evidence_payload(computation_env, ref["tool_call_id"]),
    )
    assert result.get("error") is None
    evidence = computation_env["state"].evidence_records[-1]
    artifact = _artifact_path(computation_env, ref)
    envelope = json.loads(artifact.read_text(encoding="utf-8"))
    envelope["output"]["summary"] = "tampered after evidence recording"
    artifact.write_text(json.dumps(envelope), encoding="utf-8")

    report = verify_analysis_claims(
        claims=[{"text": evidence["claim"], "evidence_id": evidence["id"]}],
        evidence_records=[evidence],
        route_proposals=[],
        cleaning_logs=[],
        current_plan_id="plan_compare",
        current_dataset_versions=[computation_env["active"]["dataset_id"]],
        sessions_root=computation_env["sessions_root"],
    )

    assert report["overall_status"] == "fail"
    assert report["claim_checks"][0]["strength"] == "unsupported"
    assert any("artifact integrity" in issue.lower() for issue in report["claim_checks"][0]["issues"])


def test_synthesis_rejects_evidence_after_same_id_plan_semantics_change(computation_env):
    from data_agent.agent.trust_workflow_runtime import maybe_verify_turn_claims

    ref = _execute_computation(computation_env)
    result = _record(
        computation_env,
        _evidence_payload(computation_env, ref["tool_call_id"]),
    )
    assert result.get("error") is None, result

    with use_agent_context(computation_env["ctx"]):
        first = maybe_verify_turn_claims(
            "summarize group revenue",
            computation_env["state"],
        )
    assert first is not None
    assert first["overall_status"] != "fail"

    computation_env["state"].analysis_plan["goal"] = "A semantically different analysis"
    with use_agent_context(computation_env["ctx"]):
        second = maybe_verify_turn_claims(
            "summarize group revenue",
            computation_env["state"],
        )

    assert second is not None
    assert second["overall_status"] == "fail"
    assert second["failed_count"] >= 1
    assert first["evidence_fingerprint"] != second["evidence_fingerprint"]
