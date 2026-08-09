"""Server-owned canonical execution envelope and exact step binding.

This module is *orchestration only*. It defines two result dataclasses and two
orchestration entry points; it does not introduce a new plan, requirement, or
evidence schema. All plan authority flows through
``normalize_analysis_plan_contract`` and all persistence flows through
``AnalysisSessionState``.

``ensure_canonical_execution_envelope`` runs before the first substantive
analytical tool call in a directed/comprehensive turn. It guarantees that the
server has materialized an executable ``AnalysisPlan`` (even when the model
never calls ``record_analysis_plan``) and bound the active dataset identity
into every analytical step.

``bind_tool_call_to_plan_step`` deterministically binds a substantive tool
call to exactly one compatible plan step. Ambiguous or unmatched calls stay
untrusted computation references with a structured diagnostic; the caller
never invents identity later.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from data_agent.agent.analysis_plan_contracts import (
    ContractValidationResult,
    normalize_analysis_plan_contract,
)
from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.intent import TurnIntent


@dataclass(frozen=True)
class EnvelopeResult:
    """Outcome of materializing the canonical execution envelope."""

    ok: bool
    plan: dict[str, Any] = field(default_factory=dict)
    current_step_id: str = ""
    error_type: str = ""
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StepBindingResult:
    """Outcome of binding a single tool call to a plan step."""

    ok: bool
    plan_id: str = ""
    step_id: str = ""
    claim_key: str = ""
    claim_keys: tuple[str, ...] = ()
    requirement_ids: tuple[str, ...] = ()
    error_type: str = ""
    candidate_step_ids: tuple[str, ...] = ()


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


def _has_executable_method_plan(plan: Any) -> bool:
    if not isinstance(plan, dict):
        return False
    method_plan = plan.get("method_plan")
    if not isinstance(method_plan, list) or not method_plan:
        return False
    return all(isinstance(item, dict) for item in method_plan)


def _select_playbook_plan(
    state: AnalysisSessionState,
    intent: TurnIntent,
    user_input: str,
) -> dict[str, Any] | None:
    """Run playbook selection lazily; return the resulting display-only plan.

    The envelope runs after route/playbook selection in ``prepare_turn``. When
    a caller invokes the envelope directly (e.g. in tests) the selection may
    not have happened yet. We run it here so the server always owns a
    canonical plan, but we never replace an existing executable plan.
    """

    if isinstance(state.analysis_plan, dict) and state.analysis_plan.get("review_status") == "executable":
        return state.analysis_plan

    from data_agent.agent.method_playbooks import apply_selection_to_state, select_playbooks

    dataset_profile = ""
    selection = select_playbooks(user_input, intent, state, dataset_profile)
    plan = selection.analysis_plan if selection and selection.analysis_plan else None
    if not plan:
        return None
    apply_selection_to_state(state, selection)
    return state.analysis_plan if isinstance(state.analysis_plan, dict) else None


def _build_executable_candidate(
    plan: dict[str, Any],
    active_dataset_name: str,
) -> dict[str, Any]:
    """Inject the active dataset identity into each analytical step.

    Goal/step_id are filled from existing step fields so the executable
    validator can accept the playbook plan shape. Route/playbook/contract
    metadata is preserved unchanged.
    """

    candidate = dict(plan)
    candidate.pop("review_status", None)
    new_steps: list[dict[str, Any]] = []
    for index, raw_step in enumerate(candidate.get("method_plan") or [], 1):
        if not isinstance(raw_step, dict):
            continue
        step = dict(raw_step)
        step["dataset_inputs"] = [active_dataset_name]
        if not _text(step.get("goal")):
            step["goal"] = (
                _text(step.get("step"))
                or _text(step.get("expected_output"))
                or f"Step {index}"
            )
        if not _text(step.get("step_id")):
            step["step_id"] = f"step_{index}"
        new_steps.append(step)
    candidate["method_plan"] = new_steps
    return candidate


def ensure_canonical_execution_envelope(
    state: AnalysisSessionState,
    intent: TurnIntent,
    user_input: str,
    active_dataset_contracts: list[dict[str, Any]],
) -> EnvelopeResult:
    """Materialize the canonical executable plan for the current turn.

    Pre-conditions: dataset identity must be present (one active contract).
    On any failure, ``state.analysis_plan`` is left untouched; nothing is
    persisted and no evidence is minted. On success the validated plan is
    persisted through ``state.set_analysis_plan`` (the single plan authority).
    """

    if not active_dataset_contracts:
        return EnvelopeResult(
            ok=False,
            error_type="analysis_dataset_identity_missing",
            details={"active_dataset_contracts": []},
        )

    active_contract = active_dataset_contracts[0]
    active_dataset_name = _text(
        active_contract.get("dataset")
        or active_contract.get("dataset_name")
        or active_contract.get("name")
    )
    if not active_dataset_name:
        return EnvelopeResult(
            ok=False,
            error_type="analysis_dataset_identity_missing",
            details={"active_dataset_contracts": list(active_dataset_contracts)},
        )

    existing_plan = state.analysis_plan if isinstance(state.analysis_plan, dict) else None
    if existing_plan and existing_plan.get("review_status") == "executable":
        return EnvelopeResult(ok=True, plan=existing_plan)

    plan = existing_plan if existing_plan else _select_playbook_plan(state, intent, user_input)
    if not plan or not _has_executable_method_plan(plan):
        return EnvelopeResult(
            ok=False,
            error_type="analysis_plan_missing",
            details={"plan_id": _text(plan.get("id")) if isinstance(plan, dict) else ""},
        )

    candidate = _build_executable_candidate(plan, active_dataset_name)

    inputs = state.analysis_requirement_inputs(candidate)
    validation: ContractValidationResult = normalize_analysis_plan_contract(
        candidate,
        require_executable=True,
        dataset_contracts=list(active_dataset_contracts),
        route=inputs.get("route"),
        playbook=inputs.get("playbook"),
        user_intent=inputs.get("user_intent") or user_input,
    )
    if not validation.ok:
        return EnvelopeResult(
            ok=False,
            error_type=validation.error_type,
            details={"message": validation.message, **validation.details},
        )

    state.set_analysis_plan(validation.plan)
    return EnvelopeResult(ok=True, plan=validation.plan)


def _capability_matches_step(capability: dict[str, Any] | None, step: dict[str, Any]) -> bool:
    """A step is compatible when capability IDs align exactly.

    Tools without capability metadata cannot be bound deterministically and
    fall through to the "untrusted computation" path.
    """

    if not capability:
        return False
    cap_id = _text(capability.get("capability_id"))
    if not cap_id:
        return False
    return _text(step.get("required_capability")) == cap_id


def _dataset_inputs_match(step: dict[str, Any], dataset_names: Sequence[str]) -> bool:
    """A step's dataset inputs must all be visible to the tool call."""

    declared = _text_list(step.get("dataset_inputs"))
    if not declared:
        # Steps without declared datasets (e.g. synthesis) do not constrain by dataset.
        return True
    tool_datasets = {_text(name) for name in dataset_names if _text(name)}
    return all(name in tool_datasets for name in declared)


def _claim_keys_for(
    step: dict[str, Any], capability: dict[str, Any] | None
) -> tuple[str, ...]:
    """Return the exact material claims owned by the bound plan step.

    ``required_claim_keys`` is the canonical workflow contract.  Earlier
    code collapsed a multi-claim step to the capability id, which made a
    successful structured computation incapable of satisfying the claims
    the plan actually declared.  Fallback identity is retained only for
    legacy steps that do not declare exact claim keys.
    """

    raw_required = step.get("required_claim_keys")
    if isinstance(raw_required, list):
        required = tuple(
            dict.fromkeys(_text(item) for item in raw_required if _text(item))
        )
        if required:
            return required
    cap_id = _text(capability.get("capability_id")) if capability else ""
    fallback = (
        _text(step.get("claim_type"))
        or cap_id
        or _text(step.get("expected_output"))
        or _text(step.get("step_id"))
    )
    return (fallback,) if fallback else ()


def bind_tool_call_to_plan_step(
    plan: dict[str, Any],
    tool_name: str,
    capability: dict[str, Any] | None,
    dataset_names: Sequence[str],
    preferred_step_id: str = "",
) -> StepBindingResult:
    """Bind a tool call to exactly one compatible plan step.

    Strategy: when ``preferred_step_id`` is supplied and compatible, bind it.
    Otherwise require exactly one compatible step. Zero candidates returns
    ``analysis_step_not_found``; multiple returns ``ambiguous_analysis_step``.

    Compatibility is filtered by dataset inputs and capability ID. Plans that
    predate capability declarations (legacy display-only projections) fall back
    to a single unambiguous dataset-compatible step when no step anywhere in
    the plan declares ``required_capability``; this preserves deterministic
    binding without weakening capability specificity for capability-declaring
    plans.

    Note: binding intentionally does NOT filter by completed/pending workflow
    status — it attributes evidence identity, not workflow state. A tool call
    binds to the step whose capability/dataset contract it satisfies even when
    that step was already completed or is not yet active. The absence of a
    current/pending filter is deliberate, not an oversight.
    """

    plan_id = _text(plan.get("id")) if isinstance(plan, dict) else ""
    method_plan = plan.get("method_plan") if isinstance(plan, dict) else None
    if not isinstance(method_plan, list):
        return StepBindingResult(ok=False, plan_id=plan_id, error_type="analysis_step_not_found")

    candidates: list[dict[str, Any]] = []
    legacy_candidates: list[dict[str, Any]] = []
    for raw_step in method_plan:
        if not isinstance(raw_step, dict):
            continue
        step_id = _text(raw_step.get("step_id"))
        if not step_id:
            continue
        if not _dataset_inputs_match(raw_step, dataset_names):
            continue
        if _capability_matches_step(capability, raw_step):
            candidates.append(raw_step)
        elif not _text(raw_step.get("required_capability")):
            # Steps that do not declare a required capability are legacy
            # projections. They remain eligible only when the plan itself
            # has no capability declarations anywhere (see plan-level guard
            # below), and only when exactly one such step exists.
            legacy_candidates.append(raw_step)

    # Legacy fallback is plan-level, not per-step: only allow the lax path
    # when NO step in the plan declares any capability. This prevents a
    # wrong-capability tool from silently binding to a capability-less
    # synthesis step (whose empty ``dataset_inputs`` matches everything) in
    # mixed plans that also contain capability-declaring analytical steps.
    plan_has_any_capability = any(
        _text(step.get("required_capability"))
        for step in method_plan
        if isinstance(step, dict)
    )
    if not candidates and not plan_has_any_capability:
        if len(legacy_candidates) == 1:
            candidates = legacy_candidates
        elif len(legacy_candidates) > 1:
            candidate_ids = sorted(_text(step.get("step_id")) for step in legacy_candidates)
            return StepBindingResult(
                ok=False,
                plan_id=plan_id,
                error_type="ambiguous_analysis_step",
                candidate_step_ids=tuple(candidate_ids),
            )

    preferred = _text(preferred_step_id)
    if preferred:
        for step in candidates:
            if _text(step.get("step_id")) == preferred:
                return _successful_binding(plan_id, step, capability)

    if not candidates:
        return StepBindingResult(
            ok=False,
            plan_id=plan_id,
            error_type="analysis_step_not_found",
        )
    if len(candidates) > 1:
        candidate_ids = sorted(_text(step.get("step_id")) for step in candidates)
        return StepBindingResult(
            ok=False,
            plan_id=plan_id,
            error_type="ambiguous_analysis_step",
            candidate_step_ids=tuple(candidate_ids),
        )

    return _successful_binding(plan_id, candidates[0], capability)


def _successful_binding(
    plan_id: str,
    step: dict[str, Any],
    capability: dict[str, Any] | None,
) -> StepBindingResult:
    step_id = _text(step.get("step_id"))
    raw_requirement_ids = step.get("requirement_ids")
    if not isinstance(raw_requirement_ids, list):
        raw_requirement_ids = []
    requirement_ids = tuple(_text(item) for item in raw_requirement_ids if _text(item))
    claim_keys = _claim_keys_for(step, capability)
    return StepBindingResult(
        ok=True,
        plan_id=plan_id,
        step_id=step_id,
        claim_key=claim_keys[0] if claim_keys else "",
        claim_keys=claim_keys,
        requirement_ids=requirement_ids,
    )
