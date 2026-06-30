from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


STAGE3C0B_CONTRACT_VERSION = "stage3c0b.v1"
SUPPORTED_STAGE3C0B_MODES = {"independent", "synthesis"}
MAX_EXECUTABLE_STEPS_PER_BATCH = 12
MAX_SYNTHESIS_REQUIRED_EVIDENCE = 8


@dataclass
class ContractValidationResult:
    ok: bool
    plan: dict[str, Any] = field(default_factory=dict)
    error_type: str = ""
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, (int, float, bool)):
        return str(value)
    return ""


def _text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_text(item) for item in value if _text(item)]


def _contract_indexes(dataset_contracts: list[dict[str, Any]]) -> tuple[dict[str, str], dict[str, str]]:
    by_dataset: dict[str, str] = {}
    by_id: dict[str, str] = {}
    for contract in dataset_contracts:
        dataset = _text(contract.get("dataset"))
        contract_id = _text(contract.get("id") or contract.get("contract_id"))
        if dataset and contract_id:
            by_dataset[dataset] = contract_id
        if contract_id:
            by_id[contract_id] = contract_id
    return by_dataset, by_id


def _error(error_type: str, message: str, **details: Any) -> ContractValidationResult:
    return ContractValidationResult(False, error_type=error_type, message=message, details=details)


def _resolve_contract_ids(dataset_inputs: list[str], by_dataset: dict[str, str], by_id: dict[str, str]) -> list[str]:
    resolved: list[str] = []
    for dataset in dataset_inputs:
        contract_id = by_dataset.get(dataset) or by_id.get(dataset)
        if contract_id:
            resolved.append(contract_id)
    return resolved


def validate_analysis_plan_contract(
    plan: dict[str, Any],
    *,
    dataset_contracts: list[dict[str, Any]] | None = None,
) -> ContractValidationResult:
    if not isinstance(plan, dict):
        return _error("invalid_plan", "AnalysisPlan must be a JSON object.")
    if plan.get("contract_version") != STAGE3C0B_CONTRACT_VERSION:
        return _error(
            "legacy_plan_display_only",
            f"AnalysisPlan missing executable contract_version={STAGE3C0B_CONTRACT_VERSION}; legacy plans are display-only.",
        )
    method_plan = plan.get("method_plan")
    if not isinstance(method_plan, list) or not method_plan:
        return _error("missing_method_plan", "Stage 3C0B AnalysisPlan requires a non-empty method_plan.")
    if len(method_plan) > MAX_EXECUTABLE_STEPS_PER_BATCH:
        return _error(
            "execution_batch_too_large",
            "Stage 3C0B execution batch exceeds the maximum executable step budget.",
            max_executable_steps_per_batch=MAX_EXECUTABLE_STEPS_PER_BATCH,
            actual=len(method_plan),
        )

    normalized = dict(plan)
    normalized.setdefault("id", f"plan_{uuid.uuid4().hex[:10]}")
    normalized.setdefault("created_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    normalized["review_status"] = "reviewed"

    by_dataset, by_id = _contract_indexes(dataset_contracts or [])
    normalized_steps: list[dict[str, Any]] = []
    seen_step_ids: set[str] = set()
    for index, raw_step in enumerate(method_plan, 1):
        if not isinstance(raw_step, dict):
            return _error("invalid_step", f"method_plan step {index} must be an object.")
        step = dict(raw_step)
        step_id = _text(step.get("step_id")) or f"step_{index}"
        if step_id in seen_step_ids:
            return _error("duplicate_step_id", f"Duplicate step_id: {step_id}", step_id=step_id)
        seen_step_ids.add(step_id)
        mode = _text(step.get("combination_mode")) or "independent"
        if mode not in SUPPORTED_STAGE3C0B_MODES:
            return _error(
                "unsupported_combination_mode",
                f"Stage 3C0B supports only independent and synthesis, not {mode}.",
                step_id=step_id,
                combination_mode=mode,
            )
        dataset_inputs = _text_list(step.get("dataset_inputs"))
        if mode == "independent" and len(dataset_inputs) != 1:
            return _error(
                "invalid_independent_binding",
                "Stage 3C0B independent steps must bind exactly one dataset.",
                step_id=step_id,
                dataset_inputs=dataset_inputs,
            )
        if mode == "synthesis" and dataset_inputs:
            return _error(
                "invalid_synthesis_binding",
                "Stage 3C0B synthesis steps consume evidence, not raw datasets.",
                step_id=step_id,
            )
        required_evidence = _text_list(step.get("required_evidence_step_ids"))
        if len(required_evidence) > MAX_SYNTHESIS_REQUIRED_EVIDENCE:
            return _error(
                "too_many_required_evidence_dependencies",
                "Synthesis declares too many hard required evidence dependencies.",
                step_id=step_id,
                max_required_evidence_step_ids=MAX_SYNTHESIS_REQUIRED_EVIDENCE,
                actual=len(required_evidence),
            )
        if not _text(step.get("goal")):
            return _error("missing_step_goal", "Every Stage 3C0B step needs a goal.", step_id=step_id)
        if not _text(step.get("expected_output")):
            return _error("missing_expected_output", "Every Stage 3C0B step needs expected_output.", step_id=step_id)
        if not _text_list(step.get("evidence_requirements")):
            return _error(
                "missing_evidence_requirements",
                "Every Stage 3C0B step needs evidence_requirements.",
                step_id=step_id,
            )

        step["plan_id"] = normalized["id"]
        step["step_id"] = step_id
        step["combination_mode"] = mode
        step["dataset_inputs"] = dataset_inputs
        step["dataset_contract_ids"] = _resolve_contract_ids(dataset_inputs, by_dataset, by_id)
        step["required_evidence_step_ids"] = required_evidence
        normalized_steps.append(step)

    normalized["method_plan"] = normalized_steps
    normalized["review_status"] = "executable"
    return ContractValidationResult(True, plan=normalized)
