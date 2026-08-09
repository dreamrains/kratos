import time
from types import SimpleNamespace

import pandas as pd

from data_agent.agent import execution_control as control
from data_agent.agent import trust_workflow_runtime as runtime
from data_agent.agent.analysis_state import AnalysisSessionState, build_trust_capsule, load_analysis_state
from data_agent.agent.context import use_agent_context
from data_agent.agent.data_lineage import TransformationRecord, frame_fingerprint
from data_agent.agent.execution_control import (
    ToolExecutionBudget,
    TurnExecutionState,
    evaluate_budget_degradation,
)
from data_agent.agent.evidence_contracts import (
    analysis_plan_semantic_digest,
    analysis_step_semantic_digest,
    persist_computation_output,
)
from data_agent.agent.loop import AgentLoop
from data_agent.llm.client import Response
from tests.fixtures.measurement_identity import bind_validated_measurement_identity


class _BudgetClient:
    max_tokens = 8_000

    def __init__(self, level):
        self.level = level
        self.analysis_calls = 0
        self.requested_output_limits = []
        self.evidence_marker = ""

    def chat(self, **kwargs):
        if "数据分析对话摘要专家" in str(kwargs.get("system") or ""):
            return Response(text="Bounded summary of prior analysis context.")

        self.analysis_calls += 1
        self.requested_output_limits.append(int(kwargs["max_tokens"]))
        if self.level == "low" and self.analysis_calls == 1:
            # Force the real audit gate to spend its single synthesis-repair attempt.
            return Response(text="Revenue increased 12%.\nLimitation: descriptive only.")
        return Response(text=(
            f"Revenue increased 12% {self.evidence_marker}.\n"
            "Limitation: descriptive only."
        ))


def _evidence(computation_ref, *, measurement_value=0.12):
    requirement_ids = [
        str(item)
        for item in computation_ref.get("requirement_ids") or []
        if str(item)
    ]
    if len(requirement_ids) != 1:
        raise AssertionError(
            "context-budget evidence requires one canonical requirement binding"
        )
    bound_ref = {
        **computation_ref,
        "claim_key": "revenue_change",
        "requirement_ids": requirement_ids,
    }
    record = {
        "id": "ev_revenue_real",
        "plan_id": "plan_context_budget",
        "step_id": "step_compare",
        "claim_key": "revenue_change",
        "claim": "Revenue increased 12%.",
        "dataset": "orders",
        "dataset_contract_id": "contract_orders",
        "method": "period_compare",
        "tool_calls": ["call_revenue_compare"],
        "result_summary": "April revenue=400; May revenue=448; increase=12%.",
        "sample_size": 8,
        "time_scope": "2026-05",
        "calculation_method": "May revenue divided by April revenue minus one",
        "method_detail": "descriptive period comparison on the real fixture rows",
        "metric_delta": {"value": measurement_value, "unit": "ratio"},
        "limitations": ["descriptive only"],
        "confidence": "medium",
        "evidence_requirement": requirement_ids[0],
        "measurements": [{
            "metric": "revenue_change",
            "definition": "May revenue change versus April revenue.",
            "value": measurement_value,
            "unit": "ratio",
            "grain": "period",
            "population_scope": "all users",
            "time_scope": "2026-05",
            "method": "period_compare",
            "denominator": "April revenue",
            "limitations": ["descriptive only"],
            "direction": "increase",
        }],
    }
    return bind_validated_measurement_identity(
        record,
        computation_ref=bound_ref,
        metric_label="Revenue",
        metric_aliases=["Monthly revenue"],
        allowed_claim_class="comparison",
    )


def _run_budget_scenario(tmp_path, level, token_budget, usage_ratio):
    session_id = f"context_budget_{level}"
    client = _BudgetClient(level)
    loop = AgentLoop(client=client, session_id=session_id)
    frame = pd.DataFrame({
        "month": ["2026-04"] * 4 + ["2026-05"] * 4,
        "revenue": [100.0, 80.0, 120.0, 100.0, 112.0, 89.6, 134.4, 112.0],
    })
    source_fingerprint = frame_fingerprint(frame)
    raw = loop.context.workspace.register_raw_snapshot("orders", frame, source_fingerprint)
    record = TransformationRecord(
        parent_dataset_id=raw["dataset_id"],
        raw_dataset_id=raw["dataset_id"],
        source_fingerprint=source_fingerprint,
        logical_name="orders",
    ).to_dict()
    active = loop.context.workspace.promote_analysis_copy(
        "orders", frame.copy(), raw["dataset_id"], record
    )
    state = AnalysisSessionState(
        session_id=session_id,
        goal="Compare April and May revenue without implying causality.",
        explicit_user_requirements="Show calculation and limitations.",
    )
    plan = {
        "id": "plan_context_budget",
        "contract_version": "analysis_plan.v1",
        "goal": state.goal,
        "method_plan": [{
            "step_id": "step_compare",
            "goal": "Compare April and May revenue",
            "dataset_inputs": ["orders"],
            "dataset_contract_ids": ["contract_orders"],
            "required_claim_keys": ["revenue_change"],
            "evidence_requirements": ["metric_delta"],
        }],
    }
    state.dataset_contracts = [{
        "id": "contract_orders",
        "dataset": "orders",
        "quality_status": "ready",
    }]
    plan = state.set_analysis_plan(plan)
    compiled_requirements = plan["analysis_requirements"]["step_compare"]
    assert len(compiled_requirements) == 1
    canonical_requirement_id = compiled_requirements[0]["id"]
    plan["method_plan"][0]["requirement_ids"] = [canonical_requirement_id]
    state.data_requirements = [{"id": "req_explain_calculation"}]
    loop.context.analysis_state = state
    loop.context.user_quality_requirements = state.explicit_user_requirements
    loop.context.turn_state = TurnExecutionState(ToolExecutionBudget(
        token_budget=token_budget,
        synthesis_reserve_tokens=max(80, int(token_budget * 0.18)),
        audit_reserve_tokens=max(60, int(token_budget * 0.12)),
        revision_reserve_tokens=max(60, int(token_budget * 0.10)),
    ))
    loop._reset_turn_tracking()
    loop._last_turn_intent = SimpleNamespace(
        intent_type="directed_analysis",
        execution_readiness="ready",
    )
    loop._ensure_mcp_initialized = lambda: None
    computation_ref = persist_computation_output(
        sessions_root=tmp_path / "sessions",
        session_id=session_id,
        turn_id=loop.context.turn_state.turn_id,
        plan_id=plan["id"],
        step_id="step_compare",
        tool_call_id="call_revenue_compare",
        tool_name="period_compare",
        arguments={"dataset": "orders", "period": "month"},
        output={
            "summary": "April revenue=400; May revenue=448; increase=12%.",
            "data": {
                "metric_delta": {
                    "metric": "revenue_change",
                    "value": 0.12,
                    "unit": "ratio",
                },
            },
        },
        dataset_versions=[active["dataset_id"]],
        success=True,
        plan_digest=analysis_plan_semantic_digest(plan),
        step_digest=analysis_step_semantic_digest(plan["method_plan"][0]),
        capability_id="analysis.period_compare",
        evidence_fields=["metric_delta"],
    )
    computation_ref = {
        **computation_ref,
        "claim_key": "revenue_change",
        "requirement_ids": [canonical_requirement_id],
    }
    state.computation_refs = [computation_ref]
    state.evidence_records = [_evidence(computation_ref)]
    evidence = state.evidence_records[0]
    client.evidence_marker = (
        f"[[evidence:{evidence['id']}#"
        f"{evidence['measurements'][0]['identity']['measurement_key']}]]"
    )
    loop.messages = [
        {"role": "user", "content": "Analyze the real order rows. " + ("x" * 500)},
        *[
            {"role": "assistant", "content": f"exploration round {index} " + ("y" * 500)}
            for index in range(14)
        ],
    ]
    turn = loop.context.turn_state
    turn.record_token_usage(
        int(turn.exploration_token_budget * usage_ratio),
        phase="exploration",
    )

    started = time.monotonic()
    with use_agent_context(loop.context):
        result = loop._loop_impl("analyze")
    latency_ms = int((time.monotonic() - started) * 1_000)

    ref = state.verification_reports[-1]
    audit = runtime.hydrate_final_answer_audit_ref(ref)
    restored = load_analysis_state(session_id)
    restored_capsule = build_trust_capsule(
        restored,
        active_datasets=loop._active_dataset_capsule_inputs(),
    )
    assert active["dataset_id"] in {
        version
        for dataset in restored_capsule["datasets"]
        for version in dataset["version_ids"]
    }
    assert restored_capsule["evidence_bindings"][0]["id"] == evidence["id"]
    assert audit is not None

    claim_classes = [
        "descriptive" if claim.get("claim_type") == "comparison" else "diagnostic"
        for claim in audit.get("claims") or []
    ] or ["diagnostic"]
    return {
        "budget_level": level,
        "claim_classes": claim_classes,
        "retained_requirement_ids": [item["id"] for item in state.data_requirements],
        "evidence_ids": control.evidence_semantic_bindings(
            state.evidence_records,
            selected_measurement_keys=[
                evidence["measurements"][0]["identity"]["measurement_key"],
            ],
        ),
        "audit_status": ref["status"],
        "completed": bool(result.content),
        "round_count": turn.llm_rounds,
        "latency_ms": latency_ms,
        "revision_available": turn.can_run_phase("revision"),
        "revision_attempts": turn.revision_attempts,
        "analysis_calls": client.analysis_calls,
        "requested_output_limits": client.requested_output_limits,
        "prompt_tokens": turn.approximate_prompt_tokens,
        "compaction_count": loop._compact_state.compaction_count,
        "public_text": result.content,
    }


def test_lower_context_budget_cannot_strengthen_real_analysis_outcome(
    tmp_path,
    monkeypatch,
):
    from data_agent.config import get_config

    monkeypatch.setattr(get_config(), "sessions_dir", tmp_path / "sessions")

    full = _run_budget_scenario(tmp_path, "full", 12_000, 0.35)
    medium = _run_budget_scenario(tmp_path, "medium", 6_000, 0.75)
    low = _run_budget_scenario(tmp_path, "low", 1_200, 1.0)

    medium_result = evaluate_budget_degradation(full, medium)
    low_result = evaluate_budget_degradation(full, low)

    assert medium_result["ok"] is True
    assert low_result["ok"] is True
    assert full["audit_status"] == medium["audit_status"] == low["audit_status"] == "pass"
    assert "[[evidence:" not in low["public_text"]
    assert low["revision_available"] is True
    assert full["analysis_calls"] == medium["analysis_calls"] == 1
    assert low["analysis_calls"] == 2
    assert low["revision_attempts"] == 1
    assert all(limit > 0 for limit in low["requested_output_limits"])
    assert low["requested_output_limits"][-1] <= 120
    assert low["compaction_count"] == 1
    assert low["prompt_tokens"] < full["prompt_tokens"]
    assert low_result["invariants"]["claim_strength_not_increased"] is True
    assert low_result["invariants"]["audit_was_not_skipped"] is True
    assert low_result["invariants"]["requirements_retained"] is True
    assert low_result["invariants"]["evidence_binding_retained"] is True


def test_degradation_evaluation_rejects_stronger_or_unaudited_low_budget_claims():
    baseline = {
        "claim_classes": ["descriptive"],
        "retained_requirement_ids": ["req_limitations"],
        "evidence_ids": ["ev_observed"],
        "audit_status": "pass",
        "completed": True,
    }

    stronger = evaluate_budget_degradation(baseline, {
        **baseline,
        "claim_classes": ["causal"],
        "audit_status": "not_run",
    })

    assert stronger["ok"] is False
    assert stronger["invariants"]["claim_strength_not_increased"] is False
    assert stronger["invariants"]["audit_was_not_skipped"] is False


def test_context_budget_binding_rejects_changed_computation_measurement_or_dataset():
    base_ref = {
        "contract_version": "computation_ref.v1",
        "session_id": "session_full",
        "turn_id": "turn_full",
        "tool_call_id": "call_revenue_compare",
        "tool_name": "period_compare",
        "output_digest": "sha256:revenue_compare",
        "plan_id": "plan_context_budget",
        "plan_digest": "sha256:plan_context_budget",
        "step_id": "step_compare",
        "step_digest": "sha256:step_compare",
        "dataset_versions": ["dataset_orders_v1"],
        "verification_level": "structured_checked",
        "claim_key": "revenue_change",
        "requirement_ids": ["req_revenue_change"],
    }
    def semantic_binding(record):
        return control.evidence_semantic_bindings(
            [record],
            selected_measurement_keys=[
                record["measurements"][0]["identity"]["measurement_key"],
            ],
        )

    baseline_binding = semantic_binding(_evidence(base_ref))
    cross_session_binding = semantic_binding(
        _evidence({
            **base_ref,
            "session_id": "session_low",
            "turn_id": "turn_low",
        })
    )
    assert cross_session_binding == baseline_binding

    mutations = [
        _evidence({
            **base_ref,
            "session_id": "session_low",
            "turn_id": "turn_low",
            "output_digest": "sha256:recomputed_revenue_compare",
        }),
        _evidence(base_ref, measurement_value=0.13),
        _evidence({
            **base_ref,
            "session_id": "session_low",
            "turn_id": "turn_low",
            "dataset_versions": ["dataset_orders_v2"],
        }),
    ]
    baseline = {
        "claim_classes": ["descriptive"],
        "retained_requirement_ids": ["req_revenue_change"],
        "evidence_ids": baseline_binding,
        "audit_status": "pass",
        "completed": True,
    }

    for changed_record in mutations:
        changed_binding = semantic_binding(changed_record)
        assert changed_binding != baseline_binding
        result = evaluate_budget_degradation(
            baseline,
            {**baseline, "evidence_ids": changed_binding},
        )
        assert result["ok"] is False
        assert result["invariants"]["evidence_binding_retained"] is False
