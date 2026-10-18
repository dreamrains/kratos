from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from data_agent.session.history import CanonicalHistorySnapshot


STAGE3C0B_CONTRACT_VERSION = "stage3c0b.v2"
DELIVERY_KINDS = frozenset({
    "measurement", "table", "series", "fit", "forecast", "scenario", "hypothesis",
    "chart", "artifact", "operation", "knowledge", "interpretation", "limitation", "conditional_action",
})
SUPPORTED_STAGE3C0B_MODES = {"independent", "synthesis"}
MAX_EXECUTABLE_STEPS_PER_BATCH = 12
MAX_DATASET_INPUTS_PER_STEP = 16
MAX_SYNTHESIS_REQUIRED_EVIDENCE = 8


def delivery_schema():
    from data_agent.agent.publication.deliveries import business_scope_schema, OPEN_KINDS, _bounded_text
    declarations=[]
    for kind in sorted(DELIVERY_KINDS):
        declarations.append({"type":"object","additionalProperties":False,
            "required":["requirement_id","kind","label"],
            "properties":{"id":_bounded_text(),"requirement_id":_bounded_text(),
                "kind":{"const":kind},"label":_bounded_text(512),
                "scope":business_scope_schema(required=kind not in OPEN_KINDS,measurement=kind=="measurement",operation=kind=="operation",metadata=kind=="table")},
            **({"required":["requirement_id","kind","label","scope"]} if kind not in OPEN_KINDS else {})})
    return {"oneOf":[{"type":"object","additionalProperties":False,"required":["id"],"properties":{"id":_bounded_text()}}]+declarations}


def analysis_plan_schema():
    from data_agent.agent.publication.deliveries import _bounded_text
    names={"type":"array","items":_bounded_text(),"uniqueItems":True}
    step={"type":"object","additionalProperties":False,
        "required":["goal","expected_output","evidence_requirements","dataset_inputs","required_deliveries"],
        "properties":{k:_bounded_text(12000) for k in ("goal","expected_output","task","subject","title","name","step","description","detail","method","node_type","required_capability")}}
    step["properties"].update({"step_id":_bounded_text(),"plan_id":_bounded_text(),
        "dataset_inputs":dict(names,maxItems=16),"dataset_contract_ids":deepcopy(names),"requirement_ids":deepcopy(names),
        "combination_mode":{"enum":sorted(SUPPORTED_STAGE3C0B_MODES)},"required_evidence_step_ids":deepcopy(names),
        "evidence_requirements":{"type":"array","minItems":1,"items":_bounded_text(12000)},
        "confirmation_policy":{"type":"object"},
        "required_deliveries":{"type":"array","minItems":1,"maxItems":64,"items":delivery_schema()}})
    step["allOf"]=[{"if":{"properties":{"combination_mode":{"const":"synthesis"}},"required":["combination_mode"]},
        "then":{"properties":{"dataset_inputs":{"maxItems":0},"required_evidence_step_ids":{"maxItems":8}}},
        "else":{"if":{"properties":{"required_deliveries":{"items":{"anyOf":[{"required":["kind","scope"],"properties":{"kind":{"const":"table"},"scope":{"required":["parameters"],"properties":{"parameters":{"required":["file_scope","file_output"],"properties":{"file_scope":{"const":"current_readable"},"file_output":{"enum":["content","entries"]}}}}}}},{"properties":{"kind":{"const":"operation"}},"required":["kind"]},{"required":["kind","scope"],"properties":{"kind":{"const":"table"},"scope":{"required":["parameters"],"properties":{"parameters":{"required":["catalog_scope","catalog_output"],"properties":{"catalog_scope":{"const":"current_visible"},"catalog_output":{"enum":["datasets","transform_history","skills","mcp_servers","mcp_health"]}}}}}}},{"type":"object","required":["id"],"properties":{"id":_bounded_text()},"additionalProperties":False}]}}}},
            "then":{},"else":{"properties":{"dataset_inputs":{"minItems":1}}}}}]
    properties={k:_bounded_text(12000) for k in ("goal","question_type")}
    properties.update({k:_bounded_text() for k in ("id","workflow_id","created_at","review_status","plan_sha256")})
    properties.update({k:{"type":"array"} for k in ("visualization_strategy","expected_dimensions","statistical_validation_plan","limitations","assumptions","metrics","dimensions","required_data")})
    properties.update({"contract_version":{"const":STAGE3C0B_CONTRACT_VERSION},"requirement_revision":{"type":"integer","minimum":0},
        "depth":{"enum":["lightweight","standard","comprehensive"]},"method_plan":{"type":"array","minItems":1,"maxItems":12,"items":step}})
    return {"type":"object","additionalProperties":False,
        "required":["contract_version","requirement_revision","goal","method_plan"],"properties":properties}


@dataclass
class ContractValidationResult:
    ok: bool
    plan: dict[str, Any] = field(default_factory=dict)
    error_type: str = ""
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    requirements: list[dict[str, Any]] | None = None


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
    answer_requirements: list[dict[str, Any]] | None = None,
    requirement_revision: int | None = None,
    canonical_history: CanonicalHistorySnapshot | None = None,
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

    revision = plan.get("requirement_revision")
    if type(revision) is not int or revision < 0 or (requirement_revision is not None and revision != requirement_revision):
        return _error("requirement_revision", "The plan must bind the exact current requirement revision.")
    normalized = deepcopy(plan)
    normalized.setdefault("created_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    normalized["review_status"] = "reviewed"

    # ``dataset_contracts=None`` keeps the validator usable for pure plan-shape
    # checks; any provided contract list, including an empty one, is enforced.
    enforce_dataset_contracts = dataset_contracts is not None
    by_dataset, by_id = _contract_indexes(dataset_contracts or [])
    normalized_steps: list[dict[str, Any]] = []
    seen_step_ids: set[str] = set()
    declarations: dict[str, dict[str, Any]] = {}
    known_deliveries = {d["id"]: d for req in (answer_requirements or [])
                        if req.get("lifecycle_status") == "active"
                        for d in req.get("necessary_deliveries", [])}
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
        from data_agent.agent.publication.deliveries import is_catalog_scope,is_file_scope
        metadata_only=bool(step.get("required_deliveries")) and all(item.get("kind")=="table" and (is_catalog_scope(item.get("scope")) or is_file_scope(item.get("scope"))) for d in step.get("required_deliveries",[]) if isinstance(d,dict) for item in [known_deliveries.get(d.get("id"),d)])
        operation_only=bool(step.get("required_deliveries")) and all((known_deliveries.get(d.get("id"),d)).get("kind")=="operation" for d in step.get("required_deliveries",[]) if isinstance(d,dict))
        if mode == "independent" and (not (0 if operation_only or metadata_only else 1) <= len(dataset_inputs) <= MAX_DATASET_INPUTS_PER_STEP or len(set(dataset_inputs)) != len(dataset_inputs)):
            return _error(
                "invalid_independent_binding",
                "Independent steps must bind 1 to 16 unique explicit datasets.",
                step_id=step_id,
                dataset_inputs=dataset_inputs,
            )
        if mode == "synthesis" and dataset_inputs:
            return _error(
                "invalid_synthesis_binding",
                "Stage 3C0B synthesis steps consume evidence, not raw datasets.",
                step_id=step_id,
            )
        resolved_contract_ids = (_resolve_contract_ids(dataset_inputs, by_dataset, by_id)
                                 if enforce_dataset_contracts else _text_list(step.get("dataset_contract_ids", [])))
        if mode == "independent" and enforce_dataset_contracts and len(resolved_contract_ids) != len(dataset_inputs):
            return _error(
                "missing_dataset_contract",
                "Independent steps require a current contract for every declared dataset.",
                step_id=step_id,
                dataset_inputs=dataset_inputs,
                dataset_contract_ids=resolved_contract_ids,
            )
        dependency_input = step.get("required_evidence_step_ids", [])
        if not isinstance(dependency_input, list) or any(
            not isinstance(item, str) or not item.strip() for item in dependency_input
        ):
            return _error(
                "invalid_evidence_dependencies",
                "Evidence dependencies must be a list of non-empty step IDs.",
                step_id=step_id,
            )
        required_evidence = _text_list(dependency_input)
        if mode == "synthesis" and len(required_evidence) > MAX_SYNTHESIS_REQUIRED_EVIDENCE:
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

        deliveries = step.get("required_deliveries")
        if not isinstance(deliveries, list) or not 1 <= len(deliveries) <= 64:
            return _error("missing_required_deliveries", "Every step must declare 1 to 64 typed deliveries for original requirement IDs.", step_id=step_id)
        normalized_deliveries = []
        for delivery_index, delivery in enumerate(deliveries):
            if isinstance(delivery, dict) and set(delivery) == {"id"}:
                did = delivery["id"]
                if not isinstance(did, str) or did not in known_deliveries:
                    return _error("unknown_required_delivery", "Reuse must reference a current host delivery ID.", step_id=step_id)
                delivery = known_deliveries[did]
            from jsonschema import Draft7Validator
            declaration_errors=list(Draft7Validator(delivery_schema()).iter_errors(delivery))
            if declaration_errors:
                errors=declaration_errors[0].context or declaration_errors
                return _error("invalid_required_delivery", "Delivery does not satisfy the published typed declaration contract.", step_id=step_id,
                    fields=[{"path":["method_plan",index-1,"required_deliveries",delivery_index]+list(e.path),"reason":e.message} for e in errors])
            item = {k: delivery[k] for k in ("requirement_id", "kind", "label")}
            from data_agent.agent.publication.deliveries import validate_business_scope, OPEN_KINDS
            try:
                item["scope"] = validate_business_scope(delivery.get("scope", {}), required=item["kind"] not in OPEN_KINDS, measurement=item["kind"]=="measurement",operation=item["kind"]=="operation",metadata=item["kind"]=="table")
            except (ValueError, TypeError) as exc:
                return _error("invalid_delivery_scope", str(exc), step_id=step_id)
            if item["kind"]=="operation":
                from data_agent.agent.publication.native import operation_sources
                op=item["scope"]["operation"]
                sources=item["scope"].get("datasets",[])
                if set(sources)!=set(operation_sources(op["action"],op["arguments"])):
                    return _error("operation_scope", "Operation must bind its exact dataset input, or no datasets for file/skill operations.",step_id=step_id)
            did = "dl_" + hashlib.sha256(json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:24]
            if delivery.get("id", did) != did or did in declarations:
                return _error("duplicate_or_invalid_delivery_id", "Delivery identity must be host-derived and occur in exactly one producing step.", step_id=step_id)
            item["id"] = did
            declarations[did] = item
            normalized_deliveries.append(item)
        declared_sources={n for d in normalized_deliveries for n in d["scope"].get("datasets",[])}
        if operation_only and set(dataset_inputs)!=declared_sources:
            return _error("operation_inputs", "Operation step must bind every exact declared source.",step_id=step_id)
        if mode=="independent" and not set(dataset_inputs).issubset(declared_sources):
            return _error("undeclared_step_input", "Every raw step input must belong to a declared business delivery.", step_id=step_id)
        step["required_deliveries"] = normalized_deliveries
        step["requirement_ids"] = sorted({d["requirement_id"] for d in normalized_deliveries})
        step["step_id"] = step_id
        step["combination_mode"] = mode
        step["dataset_inputs"] = dataset_inputs
        step["dataset_contract_ids"] = resolved_contract_ids
        step["required_evidence_step_ids"] = required_evidence
        normalized_steps.append(step)

    # Validate the complete graph before publishing an executable plan. Forward
    # references are valid; missing edges must not disappear in task projection.
    dependencies = {
        step["step_id"]: set(step["required_evidence_step_ids"])
        for step in normalized_steps
    }
    for step_id, required in dependencies.items():
        missing = required - dependencies.keys()
        if missing:
            return _error(
                "unknown_evidence_dependency",
                "Evidence dependencies must reference steps in this plan.",
                step_id=step_id,
                missing_step_ids=sorted(missing),
            )
    from data_agent.agent.publication.deliveries import OPEN_KINDS
    producers={step["step_id"]:any(d["kind"] not in OPEN_KINDS for d in step["required_deliveries"]) for step in normalized_steps}
    while dependencies:
        ready = {step_id for step_id, required in dependencies.items() if not required}
        if not ready:
            return _error(
                "cyclic_evidence_dependencies",
                "Evidence dependencies must form an acyclic graph.",
                blocked_step_ids=sorted(dependencies),
            )
        dependencies = {
            step_id: required - ready for step_id, required in dependencies.items()
            if step_id not in ready
        }

    for step in normalized_steps:
        if producers[step["step_id"]] and any(not producers[dep] for dep in step["required_evidence_step_ids"]):
            return _error("open_only_evidence_dependency", "A successful computation dependency requires a factual product.", step_id=step["step_id"])

    staged = None
    if answer_requirements is not None:
        from data_agent.agent.publication.requirements import ORIGIN, _source
        from data_agent.agent.publication.contracts import ContractError
        staged = deepcopy(answer_requirements)
        active = {r.get("id"): r for r in staged if r.get("lifecycle_status") == "active" and r.get("origin") == ORIGIN}
        grouped: dict[str, list[dict[str, Any]]] = {}
        for delivery in declarations.values():
            rid = delivery["requirement_id"]
            if rid not in active:
                return _error("unknown_plan_requirement", "Plan deliveries must refer to active canonical user requirements.", requirement_id=rid)
            if active[rid]["semantic_kind"] == "presentation" and delivery["kind"] not in {"interpretation", "limitation", "artifact", "chart"}:
                return _error("presentation_delivery_change", "A presentation preference cannot introduce a new computation goal.", requirement_id=rid)
            if active[rid]["semantic_kind"] == "knowledge" and delivery["kind"] != "knowledge":
                return _error("consultation_delivery_change", "A knowledge goal cannot become a data execution goal.", requirement_id=rid)
            from data_agent.agent.publication.deliveries import validate_business_scope
            if active[rid].get("scope_issue"):
                return _error("unresolved_business_scope", "The original business scope is unresolved.", requirement_id=rid, issue=active[rid]["scope_issue"])
            business = active[rid].get("business_scope", {})
            try:
                validate_business_scope(business)
            except (ValueError, TypeError) as exc:
                return _error("invalid_business_scope", str(exc), requirement_id=rid)
            scope = delivery["scope"]
            if (business.get("datasets") and not set(scope.get("datasets", [])).issubset(business["datasets"])
                    or business.get("metrics") and not set(scope.get("metrics", [])).issubset(business["metrics"])
                    or any(scope.get("parameters", {}).get(k) != v for k,v in business.get("parameters", {}).items())
                    or "quantity" in business and delivery["kind"]=="measurement" and scope.get("quantity") != business["quantity"]
                    or "operation" in business and scope.get("operation") != validate_business_scope(business).get("operation")):
                return _error("delivery_business_change", "Delivery cannot change the original sources, metrics, quantity or window.", requirement_id=rid)
            grouped.setdefault(rid, []).append(delivery)
        for rid, deliveries in grouped.items():
            if len(deliveries) > 32:
                return _error("too_many_goal_deliveries", "A goal may declare at most 32 necessary deliveries; no truncation is allowed.", requirement_id=rid)
            if canonical_history is not None:
                req = active[rid]
                try:
                    original = _source(canonical_history, req["source_message_ref"])
                    if original[req["source_start"]:req["source_end"]] != req["original_text"]:
                        raise ValueError("Original requirement text changed")
                except (ContractError, KeyError, TypeError, ValueError, OSError):
                    return _error("invalid_plan_requirement_origin", "The original user requirement cannot be verified in canonical history.", requirement_id=rid)
            deliveries.sort(key=lambda d: d["id"])
            signatures=[json.dumps({"kind":d["kind"],"scope":d["scope"]},sort_keys=True,ensure_ascii=False) for d in deliveries]
            if len(signatures)!=len(set(signatures)):
                return _error("duplicate_business_delivery", "Distinct required products need distinct business scopes or types, not different prose labels.", requirement_id=rid)
            existing = active[rid].get("necessary_deliveries")
            if existing is not None and existing != deliveries:
                old={d["id"]:d for d in existing}; new={d["id"]:d for d in deliveries}
                if any(new.get(did)!=d for did,d in old.items()):
                    return _error("necessary_delivery_change", "A replan cannot shrink or replace the declared delivery set. Change the original goal explicitly first.", requirement_id=rid)
                original_sources={n for d in existing for n in d["scope"].get("datasets",[])}
                windows=[{k:v for k,v in d["scope"].get("parameters",{}).items() if k!="chart_type"} for d in existing]
                additions=[d for d in deliveries if d["id"] not in old]
                if any(not set(d["scope"].get("datasets",[])).issubset(original_sources)
                       or {k:v for k,v in d["scope"].get("parameters",{}).items() if k!="chart_type"} not in windows for d in additions):
                    return _error("delivery_business_change", "An append must retain the original sources and business window.", requirement_id=rid)
                active[rid].setdefault("delivery_additions",[]).append({"requirement_revision":revision,"retained_ids":sorted(old),"added_ids":sorted(set(new)-set(old))})
            active[rid]["necessary_deliveries"] = deepcopy(deliveries)

    from jsonschema import Draft7Validator
    shape_errors=list(Draft7Validator(analysis_plan_schema()).iter_errors(plan))
    if shape_errors:
        return _error("invalid_plan_shape", "Plan does not satisfy its published structure contract.",
                      fields=[{"path":list(e.path),"reason":e.message} for e in shape_errors])
    normalized["method_plan"] = normalized_steps
    # The content digest distinguishes re-used external plan/step names. It is
    # captured before dispatch, never inferred from a model completion label.
    identity = {k: v for k, v in normalized.items() if k not in {"id", "created_at", "review_status", "plan_sha256", "requirement_revision"}}
    for step in identity["method_plan"]:
        step.pop("plan_id", None)
    digest = "sha256:" + hashlib.sha256(json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    normalized.setdefault("id", "plan_" + digest[7:31])
    if not isinstance(normalized["id"], str) or not normalized["id"].strip() or len(normalized["id"]) > 128:
        return _error("invalid_plan_id", "Plan identity must be a bounded non-empty string.")
    normalized["plan_sha256"] = digest
    for step in normalized_steps:
        step["plan_id"] = normalized["id"]
    normalized["review_status"] = "executable"
    return ContractValidationResult(True, plan=normalized, requirements=staged)
