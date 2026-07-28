from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from data_agent.agent.analysis_execution import StepBindingResult
from data_agent.agent.evidence_contracts import (
    COMPUTATION_REF_CONTRACT_VERSION,
    analysis_plan_semantic_digest,
    analysis_step_semantic_digest,
    computation_ref_key,
    computation_digest,
    measurement_key_for,
    persist_computation_output,
    project_structured_computation_evidence,
    validate_evidence_record,
)


PLAN_ID = "plan_current"
STEP_ID = "step_correlation"
SESSION_ID = "sess_current"
TURN_ID = "turn_1"
TOOL_CALL_ID = "call_corr_1"
DATASET_VERSION = "ds_main_v1"


def bind_validated_measurement_identity(
    record: dict,
    *,
    computation_ref: dict,
    metric_label: str,
    metric_aliases: list[str],
    allowed_claim_class: str,
    metric_key: str | None = None,
) -> dict:
    """Bind one test measurement through the production v2 validators."""

    bound = copy.deepcopy(record)
    ref = copy.deepcopy(computation_ref)
    measurements = bound.get("measurements")
    if (
        not isinstance(measurements, list)
        or len(measurements) != 1
        or not isinstance(measurements[0], dict)
    ):
        raise AssertionError("validated fixture requires exactly one measurement")
    measurement = measurements[0]
    requirement_ids = sorted(str(item) for item in ref.get("requirement_ids") or [])
    dataset_versions = sorted(str(item) for item in ref.get("dataset_versions") or [])
    if not requirement_ids or not dataset_versions:
        raise AssertionError("validated fixture requires requirement and dataset identities")

    bound.update({
        "contract_version": "evidence_record.v2",
        "source_tool_call_ids": [str(ref.get("tool_call_id") or "")],
        "requirement_ids": requirement_ids,
        "dataset_versions": dataset_versions,
        "computation_refs": [ref],
        "provenance_status": "bound",
        "verification_level": str(ref.get("verification_level") or "structured_checked"),
        "allowed_claim_class": allowed_claim_class,
    })
    identity = {
        "contract_version": "measurement_identity.v1",
        "metric_key": metric_key or str(measurement.get("metric") or ""),
        "metric_label": metric_label,
        "metric_aliases": list(metric_aliases),
        "claim_key": str(bound.get("claim_key") or ""),
        "computation_ref_id": computation_ref_key(ref),
        "plan_id": str(bound.get("plan_id") or ""),
        "plan_version": str(ref.get("plan_digest") or ""),
        "step_id": str(bound.get("step_id") or ""),
        "requirement_ids": requirement_ids,
        "dataset_versions": dataset_versions,
        "time_scope": str(measurement.get("time_scope") or ""),
        "population_scope": str(measurement.get("population_scope") or ""),
        "value": measurement.get("value"),
        "unit": str(measurement.get("unit") or ""),
        "direction": str(measurement.get("direction") or ""),
        "allowed_claim_class": allowed_claim_class,
    }
    identity["measurement_key"] = measurement_key_for(identity)
    measurement["identity"] = identity
    validation = validate_evidence_record(
        bound,
        current_plan_id=str(bound.get("plan_id") or ""),
        require_measurement_identity=True,
    )
    if not validation.ok:
        raise AssertionError(
            f"{validation.error_type}: {validation.message} {validation.details}"
        )
    return validation.record


@dataclass
class ProjectionContext:
    plan: dict
    capability: dict
    dataset_contracts: list[dict]
    session_id: str
    turn_id: str
    sessions_root: Path

    @property
    def analysis_requirements(self) -> dict:
        return self.plan["analysis_requirements"]


def correlation_capability() -> dict:
    return {
        "capability_id": "analysis.correlation",
        "category": "relationship",
        "evidence_fields": [
            "pairs.correlation",
            "pairs.effective_sample_size",
            "pairs.p_value",
            "allowed_claim_class",
        ],
    }


def correlation_output() -> dict:
    return {
        "summary": "Pearson correlation: r=0.40, n=100, p=0.001",
        "data": {
            "method": "pearson",
            "pairs": [
                {
                    "variables": ["revenue", "cost"],
                    "correlation": 0.4,
                    "effective_sample_size": 100,
                    "p_value": 0.001,
                },
            ],
            "allowed_claim_class": "association",
        },
    }


def current_plan() -> dict:
    return {
        "id": PLAN_ID,
        "contract_version": "analysis_plan.v1",
        "review_status": "executable",
        "goal": "describe correlation between revenue and cost",
        "method_plan": [
            {
                "step_id": STEP_ID,
                "goal": "Compute revenue/cost correlation",
                "dataset_inputs": ["main"],
                "dataset_contract_ids": ["contract_main_v1"],
                "required_capability": "analysis.correlation",
                "claim_type": "correlation",
                "required_claim_keys": ["revenue_cost_correlation"],
                "requirement_ids": ["req_corr_effect", "req_corr_interval"],
            }
        ],
        "analysis_requirements": {
            STEP_ID: [
                {
                    "id": "req_corr_effect",
                    "step_id": STEP_ID,
                    "name": "correlation",
                    "necessity": "required",
                    "trigger": "relationship",
                },
                {
                    "id": "req_corr_interval",
                    "step_id": STEP_ID,
                    "name": "confidence_interval",
                    "necessity": "required",
                    "trigger": "relationship",
                },
            ]
        },
    }


PLAN_DIGEST = analysis_plan_semantic_digest(current_plan())
STEP_DIGEST = analysis_step_semantic_digest(current_plan()["method_plan"][0])


def current_dataset_contracts() -> list[dict]:
    return [
        {
            "id": "contract_main_v1",
            "dataset": "main",
            "dataset_id": DATASET_VERSION,
            "quality_status": "ready",
        }
    ]


def exact_step_binding() -> StepBindingResult:
    return StepBindingResult(
        ok=True,
        plan_id=PLAN_ID,
        step_id=STEP_ID,
        claim_key="revenue_cost_correlation",
        requirement_ids=("req_corr_effect",),
    )


def ambiguous_binding() -> StepBindingResult:
    return StepBindingResult(
        ok=False,
        plan_id=PLAN_ID,
        error_type="ambiguous_analysis_step",
        candidate_step_ids=(STEP_ID, "step_other"),
    )


def _artifact_filename(turn_id: str, tool_call_id: str) -> str:
    from data_agent.tools._utils import sanitize_filename

    artifact_identity = json.dumps(
        [str(turn_id or ""), str(tool_call_id)],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    suffix = hashlib.sha256(artifact_identity.encode("utf-8")).hexdigest()[:12]
    return f"{sanitize_filename(tool_call_id)}_{suffix}_computation.json"


def _write_correlation_artifact(
    context: ProjectionContext,
    *,
    capability: dict,
    output: dict,
    dataset_versions: list,
) -> Path:
    plan_digest = analysis_plan_semantic_digest(context.plan)
    step_digest = analysis_step_semantic_digest(context.plan["method_plan"][0])
    output_dir = context.sessions_root / context.session_id / "tool_outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    persist_computation_output(
        sessions_root=context.sessions_root,
        session_id=context.session_id,
        turn_id=context.turn_id,
        plan_id=context.plan["id"],
        step_id=context.plan["method_plan"][0]["step_id"],
        tool_call_id=TOOL_CALL_ID,
        tool_name="correlation_analysis",
        arguments={"name": "main", "method": "pearson"},
        output=output,
        dataset_versions=dataset_versions,
        success=True,
        plan_digest=plan_digest,
        step_digest=step_digest,
        capability_id=capability["capability_id"],
        evidence_fields=capability["evidence_fields"],
    )
    return output_dir / _artifact_filename(context.turn_id, TOOL_CALL_ID)


def structured_correlation_ref(
    *,
    artifact_path: Path | str = "",
    dataset_versions: list[str] | None = None,
    output: dict | None = None,
    capability: dict | None = None,
    plan_digest: str = PLAN_DIGEST,
    step_digest: str = STEP_DIGEST,
) -> dict:
    arguments = {"name": "main", "method": "pearson"}
    output = correlation_output() if output is None else output
    capability = correlation_capability() if capability is None else capability
    return {
        "contract_version": COMPUTATION_REF_CONTRACT_VERSION,
        "session_id": SESSION_ID,
        "tool_call_id": TOOL_CALL_ID,
        "tool_name": "correlation_analysis",
        "capability_id": capability["capability_id"],
        "arguments_digest": computation_digest(arguments),
        "output_digest": computation_digest(output),
        "artifact_path": str(artifact_path or Path("/_unused")),
        "dataset_versions": list(
            dataset_versions if dataset_versions is not None else [DATASET_VERSION]
        ),
        "turn_id": TURN_ID,
        "plan_id": PLAN_ID,
        "plan_digest": plan_digest,
        "step_id": STEP_ID,
        "step_digest": step_digest,
        "success": True,
        "structured_checked_fields": capability["evidence_fields"],
        "verification_level": "structured_checked",
        "claim_key": "revenue_cost_correlation",
        "requirement_ids": ["req_corr_effect"],
    }


def failed_ref() -> dict:
    return {**structured_correlation_ref(), "success": False}


def free_form_python_ref() -> dict:
    return {
        **structured_correlation_ref(),
        "tool_name": "run_python",
        "capability_id": "fallback.python",
        "structured_checked_fields": [],
        "verification_level": "traceable",
    }


def stale_dataset_ref() -> dict:
    return structured_correlation_ref(dataset_versions=["ds_main_v0_stale"])


def build_projection_context(tmp_path: Path) -> ProjectionContext:
    sessions_root = tmp_path / "sessions"
    sessions_root.mkdir(parents=True, exist_ok=True)
    return ProjectionContext(
        plan=current_plan(),
        capability=correlation_capability(),
        dataset_contracts=current_dataset_contracts(),
        session_id=SESSION_ID,
        turn_id=TURN_ID,
        sessions_root=sessions_root,
    )


def project_real_correlation(
    context: ProjectionContext,
    *,
    output: dict | None = None,
    capability: dict | None = None,
    dataset_versions: list | None = None,
    binding: StepBindingResult | None = None,
    ref_overrides: dict | None = None,
):
    output = correlation_output() if output is None else output
    capability = context.capability if capability is None else capability
    dataset_versions = (
        list(dataset_versions)
        if dataset_versions is not None
        else [contract["dataset_id"] for contract in context.dataset_contracts]
    )
    plan_digest = analysis_plan_semantic_digest(context.plan)
    step_digest = analysis_step_semantic_digest(context.plan["method_plan"][0])
    artifact_path = _write_correlation_artifact(
        context,
        capability=capability,
        output=output,
        dataset_versions=dataset_versions,
    )
    ref = structured_correlation_ref(
        artifact_path=artifact_path,
        dataset_versions=dataset_versions,
        output=output,
        capability=capability,
        plan_digest=plan_digest,
        step_digest=step_digest,
    )
    if ref_overrides:
        ref.update(ref_overrides)
    return project_structured_computation_evidence(
        computation_ref=ref,
        binding=binding or exact_step_binding(),
        plan=context.plan,
        capability=capability,
        dataset_contracts=context.dataset_contracts,
        current_session_id=context.session_id,
        current_turn_id=context.turn_id,
        sessions_root=context.sessions_root,
    )
