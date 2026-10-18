"""Tools for persisting structured analysis planning artifacts."""

from __future__ import annotations

from data_agent.tools.evidence_input import EVIDENCE_INPUT_SCHEMA
from data_agent.agent.analysis_plan_contracts import analysis_plan_schema

import json
from datetime import datetime

from data_agent.tools.registry import registry


_STAT_DETAIL_FIELDS = [
    "metrics",
    "sample_size",
    "time_scope",
    "calculation_method",
    "method_detail",
    "significance",
    "correlation",
    "confidence_interval",
]


def _mark_statistical_detail_status(payload: dict) -> dict:
    fields = payload.get("statistical_detail_required_fields", _STAT_DETAIL_FIELDS)
    gaps = [field for field in fields if payload.get(field) in (None, "", [], {})]
    projection_gaps = payload.get("statistical_projection_gaps") or []
    if any(not isinstance(item, dict) or item.get("blocking", True) for item in projection_gaps):
        gaps.append("statistical_projection")
    payload["statistical_detail_gaps"] = gaps
    payload["statistical_detail_status"] = "complete" if not gaps else "missing"
    return payload

def _session_id() -> str:
    try:
        from data_agent.agent.context import get_current_context
        ctx = get_current_context()
        if ctx is not None:
            return ctx.session_id
    except Exception:
        pass
    try:
        from data_agent.tools.visualization import current_session_id
        return current_session_id()
    except Exception:
        return ""


def _current_state():
    try:
        from data_agent.agent.analysis_state import current_analysis_state
        return current_analysis_state()
    except Exception:
        return None


def _current_turn_receipts() -> list[dict]:
    try:
        from data_agent.agent.context import get_current_context

        context = get_current_context()
        state = getattr(context, "analysis_state", None) if context is not None else None
        receipt_ids = getattr(context, "turn_receipt_ids", None) if context is not None else None
        # Older callers may populate the execution-state receipts directly;
        # an empty context list is not evidence that this turn has no
        # receipts.  Prefer the context chain when present, then use that
        # equivalent current-turn source as a fallback.
        if not isinstance(receipt_ids, list) or not receipt_ids:
            turn_state = getattr(context, "turn_state", None) if context is not None else None
            receipt_ids = getattr(turn_state, "tool_receipt_ids", None)
        receipts = getattr(state, "tool_receipts", None)
        if not isinstance(receipt_ids, list) or not isinstance(receipts, list):
            return []
        by_id = {
            str(item.get("id")): item
            for item in receipts
            if isinstance(item, dict) and item.get("id")
        }
        return [by_id[receipt_id] for receipt_id in receipt_ids if receipt_id in by_id]
    except Exception:
        return []


def _tool_names(tool_calls) -> set[str]:
    if not isinstance(tool_calls, list):
        return set()
    names: set[str] = set()
    for call in tool_calls:
        if isinstance(call, str) and call.strip():
            names.add(call.strip())
        elif isinstance(call, dict):
            name = call.get("name")
            if not name and isinstance(call.get("function"), dict):
                name = call["function"].get("name")
            if isinstance(name, str) and name.strip():
                names.add(name.strip())
    return names


def _write_analysis_artifact(kind: str, payload: dict) -> dict:
    from data_agent.config import get_config
    from data_agent.session.history import register_artifact

    sid = _session_id()
    if not sid:
        return {"error": "无当前会话，无法保存分析产物"}

    out_dir = get_config().sessions_resolved / sid / "analysis_flow"
    out_dir.mkdir(parents=True, exist_ok=True)
    import hashlib
    from data_agent.utils.atomic_files import write_text_atomic
    content = json.dumps({k: v for k, v in payload.items() if k != "artifact_path"}, ensure_ascii=False, sort_keys=True, indent=2)
    digest = hashlib.sha256((kind + "\0" + content).encode("utf-8")).hexdigest()
    # The payload includes the evidence identity; bound the filename for
    # Windows paths instead of repeating arbitrarily long plan/step IDs.
    path = out_dir / f"af_{digest[:40]}.json"
    # Content-addressed revisions preserve prior bodies, including same-ID
    # evidence updates. Repeating exactly the same write is idempotent.
    if path.exists():
        if path.read_text(encoding="utf-8") != content:
            raise ValueError("Immutable analysis artifact content mismatch")
    else:
        write_text_atomic(path, content)

    artifact_path = f"sessions/{sid}/analysis_flow/{path.name}"
    register_artifact(sid, artifact_path, kind, payload.get("goal") or payload.get("claim") or kind)
    return {"saved": artifact_path, "type": kind, "payload": payload}


def _persist_analysis_record(kind: str, payload: dict) -> dict:
    """Commit an analysis record with its existing state, artifact and manifest."""
    from copy import deepcopy
    import hashlib
    from data_agent.config import get_config
    from data_agent.session.history import list_artifacts
    from data_agent.utils.atomic_files import rollback_atomic_writes

    sid = _session_id()
    if not sid:
        return {"error": "无当前会话，无法保存分析产物"}
    state = _current_state()
    before = deepcopy(vars(state)) if state is not None else None
    try:
        with rollback_atomic_writes():
            if state is not None:
                if kind == "data_requirement":
                    payload = state.add_data_requirement(payload)
                elif kind == "analysis_spec":
                    payload = state.set_analysis_spec(payload)
                elif kind == "evidence_record":
                    payload = (state.upsert_evidence_record(payload)
                               if payload.get("plan_id") and "measurements" in payload
                               else state.add_evidence_record(payload))
                else:
                    raise ValueError("Unsupported analysis record kind")
            result = _write_analysis_artifact(kind, payload)
            if state is not None:
                if kind == "evidence_record":
                    payload["artifact_path"] = result.get("saved", "")
                state_path = state.save()
                if json.loads(state_path.read_text(encoding="utf-8")) != state.to_dict():
                    raise ValueError("Analysis state readback mismatch")
            content = json.dumps({k: v for k, v in payload.items() if k != "artifact_path"},
                                 ensure_ascii=False, sort_keys=True, indent=2)
            digest = hashlib.sha256((kind + "\0" + content).encode("utf-8")).hexdigest()
            expected = f"sessions/{sid}/analysis_flow/af_{digest[:40]}.json"
            path = get_config().sessions_resolved / sid / "analysis_flow" / f"af_{digest[:40]}.json"
            if result.get("saved") != expected or result.get("type") != kind:
                raise ValueError("Analysis artifact identity mismatch")
            if path.read_text(encoding="utf-8") != content:
                raise ValueError("Analysis artifact readback mismatch")
            identity = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
            description = payload.get("goal") or payload.get("claim") or kind
            if not any(item.get("path") == expected and item.get("type") == kind
                       and item.get("sha256") == identity and item.get("description") == description
                       for item in list_artifacts(sid)):
                raise ValueError("Analysis artifact manifest mismatch")
            if state is not None:
                result["state_stage"] = state.stage
            return result
    except BaseException:
        if state is not None:
            vars(state).clear()
            vars(state).update(before)
        raise


@registry.register(
    name="record_data_requirement",
    description=(
        "Save a DataRequirement JSON with goal, must_have_data, recommended_data, "
        "optional_data, missing_limitations, and minimum_viable_analysis."
    ),
)
def record_data_requirement(requirement_json: str) -> str:
    try:
        payload = json.loads(requirement_json)
    except json.JSONDecodeError:
        return json.dumps({"error": "requirement_json 必须是有效 JSON"}, ensure_ascii=False)
    if not isinstance(payload, dict):
        return json.dumps({"error": "requirement_json 必须是 JSON 对象"}, ensure_ascii=False)
    required = [
        "goal",
        "must_have_data",
        "recommended_data",
        "optional_data",
        "missing_limitations",
        "minimum_viable_analysis",
    ]
    missing = [k for k in required if k not in payload]
    if missing:
        return json.dumps({"error": f"DataRequirement 缺少字段: {missing}"}, ensure_ascii=False)

    result = _persist_analysis_record("data_requirement", payload)
    saved_payload = result.pop("payload", None)
    if "state_stage" in result:
        result["requirement_id"] = saved_payload.get("id")
    return json.dumps(result, ensure_ascii=False)


@registry.register(
    name="record_analysis_spec",
    description=(
        "Save an AnalysisSpec JSON with goal, question_type, metrics, "
        "dimensions, required_data, method_plan, and limitations."
    ),
)
def record_analysis_spec(spec_json: str) -> str:
    try:
        payload = json.loads(spec_json)
    except json.JSONDecodeError:
        return json.dumps({"error": "spec_json 必须是有效 JSON"}, ensure_ascii=False)
    if not isinstance(payload, dict):
        return json.dumps({"error": "spec_json 必须是 JSON 对象"}, ensure_ascii=False)
    required = ["goal", "question_type", "metrics", "dimensions", "required_data", "method_plan", "limitations"]
    missing = [k for k in required if k not in payload]
    if missing:
        return json.dumps({"error": f"AnalysisSpec 缺少字段: {missing}"}, ensure_ascii=False)

    if payload.get("contract_version"):
        return json.dumps({"error":"Executable plans must use record_analysis_plan.","error_type":"analysis_spec_display_only"})
    result = _persist_analysis_record("analysis_spec", payload)
    saved_payload = result.pop("payload", None)
    if "state_stage" in result:
        result["analysis_spec_id"] = saved_payload.get("id")

    result["workflow"] = {"created":0,"task_ids":[],"reason":"legacy_analysis_spec_display_only","display_only":True}
    return json.dumps(result, ensure_ascii=False)


@registry.register(
    name="record_analysis_plan",
    description=(
        "Save an executable Stage 3C0B AnalysisPlan before recording plan-scoped evidence. Required top-level "
        "fields: requirement_revision (exact current revision), contract_version='stage3c0b.v2', goal and method_plan; visualization_strategy is optional. Every method_plan "
        "item requires goal, expected_output, evidence_requirements, dataset_inputs and required_deliveries=[{requirement_id,kind,label,scope}]. Use original active requirement IDs and business deliveries, never tool/statistic/result-path selectors. Operation kind uses scope.operation={action:registered operation name,arguments:exact invocation parameters}; dataset operations also bind datasets; file/skill-only steps use dataset_inputs=[]. Effects are not data claims. Directory metadata uses table with scope.parameters.catalog_scope=current_visible and catalog_output=datasets/transform_history; a real empty visible scope can bind datasets=[] and dataset_inputs=[] without inventing a data version. File excerpt/catalogue uses table parameters.file_scope=current_readable and file_output=content (file_path,file_offset, optional file_limit/file_max_chars/file_sha256) or entries (file_pattern), with datasets=[] and dataset_inputs=[]. Host verifies current session/path permissions, SHA and exact page/enumeration scope; this does not verify conclusions within the file. Ordinary measurements still require actual datasets. Host assigns delivery IDs; reuse existing deliveries with {id} instead of repeating labels. A replan cannot narrow its goals. An "
        "independent item binds 1 to 16 explicit current datasets; a synthesis item uses combination_mode='synthesis', "
        "dataset_inputs=[], and required_evidence_step_ids. Use the returned analysis_plan_id as evidence plan_id "
        "and the normalized step_id as evidence step_id."
    ),
    schema_overrides={"plan_json": analysis_plan_schema()},
)
def record_analysis_plan(plan_json: str | dict) -> str:
    try:
        payload = json.loads(plan_json) if isinstance(plan_json, str) else plan_json
    except (json.JSONDecodeError, TypeError):
        return json.dumps({"error": "plan_json must be valid JSON"}, ensure_ascii=False)
    if not isinstance(payload, dict):
        return json.dumps({"error": "AnalysisPlan must be a JSON object."}, ensure_ascii=False)
    state = _current_state()
    if payload.get("contract_version"):
        from data_agent.agent.analysis_plan_contracts import validate_analysis_plan_contract

        dataset_contracts = None
        if state is not None:
            from data_agent.agent.artifact_refs import hydrate_refs
            dataset_contracts = hydrate_refs(list(getattr(state, "dataset_contracts", []) or []))
        from data_agent.session.history import load_canonical_history
        validation = validate_analysis_plan_contract(
            payload, dataset_contracts=dataset_contracts,
            answer_requirements=state.answer_requirements if state is not None else None,
            requirement_revision=state.requirement_revision if state is not None else None,
            canonical_history=load_canonical_history(state.session_id) if state is not None else None,
        )
        if not validation.ok:
            return json.dumps({
                "error": validation.message,
                "error_type": validation.error_type,
                "details": validation.details,
            }, ensure_ascii=False)
        payload = validation.plan
    else:
        from data_agent.agent.analysis_plan_contracts import STAGE3C0B_CONTRACT_VERSION

        return json.dumps({
            "error": f"AnalysisPlan missing executable contract_version={STAGE3C0B_CONTRACT_VERSION}; legacy plans are display-only.",
            "error_type": "legacy_plan_display_only",
        }, ensure_ascii=False)

    if state is not None:
        from copy import deepcopy
        before = deepcopy((state.answer_requirements, state.requirement_revision, state.analysis_plan, state.analysis_spec, state.goal, state.stage))
        try:
            from data_agent.session.workspace import workspace
            from data_agent.agent.publication.requirements import target_datasets
            planned_requirements={d["requirement_id"] for step in payload["method_plan"] for d in step["required_deliveries"]}
            for req in validation.requirements:
                if req.get("lifecycle_status") != "active" or req["id"] not in planned_requirements: continue
                expected=req.setdefault("source_data_identities",{})
                for name in target_datasets(req):
                    identity=workspace._publication_data_identity(name)
                    pending=req.get("source_binding",{})
                    if pending.get("status")=="pending" and (name in pending.get("required_load_datasets", []) or identity!=pending.get("initial_data_identities",{}).get(name)):
                        receipt_id=pending.get("verified_load_receipts",{}).get(name)
                        loaded=next((r for r in state.tool_receipts if r.get("id")==receipt_id),None)
                        if not loaded or not workspace._receipt_identity_matches(name,loaded.get("data_identities",{}).get(name,{})):
                            from data_agent.agent.publication.contracts import ContractError
                            raise ContractError("replacement_source_unverified","替换目标的新来源尚无成功加载核验。")
                    if name in expected and identity!=expected[name]:
                        from data_agent.agent.publication.contracts import ContractError
                        raise ContractError("requirement_version","Original business source version changed; replace the original requirement first.")
                    if identity: expected[name]=identity
                if req.get("source_binding",{}).get("status")=="pending":
                    if not target_datasets(req) or any(n not in expected for n in target_datasets(req)):
                        from data_agent.agent.publication.contracts import ContractError
                        raise ContractError("replacement_source_unverified","替换目标的来源尚未加载。")
                    req["source_binding"]["status"]="frozen"
            if state.answer_requirements != validation.requirements:
                state.answer_requirements = validation.requirements
                state.requirement_revision += 1
            from data_agent.session.task_manager import task_manager
            from data_agent.tools.task_tools import create_workflow_tasks_from_spec
            with task_manager.plan_transaction():
                payload = state.set_analysis_plan(payload)
                workflow = create_workflow_tasks_from_spec(payload)
                if workflow.get("error"):raise ValueError(workflow["error"])
                result = _write_analysis_artifact("analysis_plan", payload)
                state.save()
        except Exception as exc:
            (state.answer_requirements, state.requirement_revision, state.analysis_plan, state.analysis_spec, state.goal, state.stage) = before
            from data_agent.agent.publication.contracts import ContractError
            if isinstance(exc,ContractError):
                return json.dumps({"error":str(exc),"error_type":exc.code,"details":{"stage":"plan_source_binding"}},ensure_ascii=False)
            raise

    if state is None:result = _write_analysis_artifact("analysis_plan", payload)
    result.pop("payload", None)
    result["analysis_plan_id"] = payload.get("id")
    result["plan_sha256"] = payload["plan_sha256"]
    result["required_deliveries"] = [d for step in payload["method_plan"] for d in step["required_deliveries"]]
    if state is not None:
        result["requirement_revision"] = state.requirement_revision
        from data_agent.agent.context import get_current_context
        ctx = get_current_context()
        if ctx is not None: ctx.requirement_revision = state.requirement_revision
    if state is not None:
        result["state_stage"] = state.stage

    result["workflow"] = workflow if state is not None else {"created":0,"task_ids":[],"reason":"no_session_state"}
    return json.dumps(result, ensure_ascii=False)


@registry.register(
    name="record_evidence_record",
    description=(
        "Save an EvidenceRecord JSON with claim, dataset, method, tool_calls, "
        "result_summary, limitations, confidence, and statistical details such as "
        "metrics, sample_size, calculation_method, significance, correlation, "
        "effect size, or confidence_interval when available. "
        "tool_calls MUST be an array, e.g. [\"curve_fitting\"], never a comma-separated string. "
        "confidence MUST be high, medium, low or speculative (not translated). "
        "Use the exact tool result and data version; parameter errors require correcting the record, not recomputing."
    ),
    schema_overrides={"record_json": {
        "type": ["object", "string"],
        "description": "Evidence object, or a JSON-encoded object for compatibility. Required: claim/dataset/method/result_summary strings; tool_calls array of tool names; limitations string or string array; confidence enum high/medium/low/speculative.",
        "properties": EVIDENCE_INPUT_SCHEMA["properties"],
    }},
)
def record_evidence_record(record_json: str | dict) -> str:
    try:
        payload = json.loads(record_json) if isinstance(record_json, str) else record_json
    except (json.JSONDecodeError, TypeError):
        return json.dumps({"error": "record_json 必须是有效 JSON"}, ensure_ascii=False)
    if not isinstance(payload, dict):
        return json.dumps({
            "error": "EvidenceRecord must be a JSON object.",
            "error_type": "invalid_evidence",
        }, ensure_ascii=False)

    payload = dict(payload)
    for derived_key in ("statistical_detail_required_fields", "statistical_inference", "computed_statistics_sources",
                        "statistical_projection_gaps", "reported_statistical_details", "sample_size_source",
                        "time_scope_source", "auto_generated_limitations", "calibration_warnings",
                        "confidence_auto_downgraded", "original_confidence"):
        payload.pop(derived_key, None)
    payload["statistical_inference"] = False  # Updated only by actual bound statistics below.

    from data_agent.tools.evidence_input import validate_input, EVIDENCE_INPUT_SCHEMA
    if all(key in payload for key in EVIDENCE_INPUT_SCHEMA["required"]):
        input_error = validate_input(payload)
        if input_error:
            return json.dumps(input_error, ensure_ascii=False)

    state = _current_state()
    current_plan_id = ""
    if state is not None and isinstance(getattr(state, "analysis_plan", None), dict):
        current_plan_id = str(state.analysis_plan.get("id") or "")

    # Stage 3C0B is an explicit plan/step contract.  A model may attach
    # concise receipt-bound measurements to an ordinary EvidenceRecord; that
    # alone must not silently opt the record into the stricter executable
    # contract (and then reject it because no plan exists).  Explicit plan or
    # step identity, or a derived-measurement expression, remains fail-closed.
    is_stage3c0b_evidence = (
        "plan_id" in payload
        or "step_id" in payload
        or payload.get("derived_measurements") is not None
    )
    if is_stage3c0b_evidence:
        from data_agent.agent.evidence_contracts import validate_stage3c0b_evidence

        validation = validate_stage3c0b_evidence(
            payload,
            current_plan_id=current_plan_id,
        )
        if not validation.ok:
            return json.dumps({
                "error": validation.message,
                "error_type": validation.error_type,
                "details": validation.details,
            }, ensure_ascii=False)
        payload = validation.record

    # Ordinary EvidenceRecords belong to the active plan even when the model
    # did not know its generated ID.  Without this binding, the verifier
    # correctly excludes the record as out-of-plan and the UI can never mark
    # the just-created conclusion as verified.
    if not is_stage3c0b_evidence and current_plan_id and not payload.get("plan_id"):
        payload["plan_id"] = current_plan_id

    required = ["claim", "dataset", "method", "tool_calls", "result_summary", "limitations", "confidence"]
    missing = [k for k in required if k not in payload]
    if missing:
        return json.dumps({"error": f"EvidenceRecord 缺少字段: {missing}"}, ensure_ascii=False)

    from data_agent.tools.evidence_input import validate_input
    input_error = validate_input(payload)
    if input_error:
        return json.dumps(input_error, ensure_ascii=False)

    # Bind model-selected tool names to receipts made by this exact execution
    # turn.  The model cannot promote a tool it did not run into evidence.
    current_turn_receipts = _current_turn_receipts()
    from data_agent.agent.context import get_current_context
    context = get_current_context()
    if context is not None and getattr(context, "turn_state", None) is not None and not current_turn_receipts:
        return json.dumps({"error": "EvidenceRecord requires a successful tool receipt in this turn",
                           "error_type": "missing_tool_receipt"}, ensure_ascii=False)
    if current_turn_receipts:
        called_names = _tool_names(payload.get("tool_calls"))
        receipt_names = {
            str(receipt.get("tool_name"))
            for receipt in current_turn_receipts
            if receipt.get("tool_name")
        }
        missing_receipts = sorted(called_names - receipt_names)
        if missing_receipts:
            return json.dumps({
                "error": "EvidenceRecord references tools not executed in this turn",
                "error_type": "unbound_tool_receipt",
                "missing_tool_receipts": missing_receipts,
            }, ensure_ascii=False)
        bound_receipts = [
            receipt for receipt in current_turn_receipts
            if str(receipt.get("tool_name")) in called_names
        ]
        requested_receipts = payload.get("tool_receipt_ids")
        if requested_receipts is not None:
            if not isinstance(requested_receipts, list) or any(not isinstance(i, str) for i in requested_receipts):
                return json.dumps({"error": "tool_receipt_ids must be an array of receipt IDs", "error_type": "invalid_evidence_arguments"})
            if set(requested_receipts) - {str(r["id"]) for r in bound_receipts}:
                return json.dumps({"error": "Receipt IDs do not belong to the named tools in this turn", "error_type": "unbound_tool_receipt"})
            bound_receipts = [r for r in bound_receipts if str(r["id"]) in requested_receipts]
        if not bound_receipts:
            return json.dumps({
                "error": "EvidenceRecord requires at least one successful tool receipt in this turn",
                "error_type": "missing_tool_receipt",
            }, ensure_ascii=False)
        from data_agent.session.workspace import workspace
        if requested_receipts is None:
            current_receipts = [
                receipt for receipt in bound_receipts
                if all(workspace._receipt_identity_matches(name, identity)
                       for name, identity in receipt.get("data_identities", {}).items())
            ]
            # A source may be reloaded and the same tool run again in one turn.
            # Keep every current independent result, but do not bind an older
            # source version to a new EvidenceRecord by tool name alone.
            if (current_receipts and len(current_receipts) != len(bound_receipts)
                    and any(payload["dataset"] in receipt.get("data_identities", {})
                            for receipt in current_receipts)):
                bound_receipts = current_receipts
        for receipt in bound_receipts:
            for name, identity in receipt.get("data_identities", {}).items():
                if not workspace._receipt_identity_matches(name, identity):
                    return json.dumps({"error": "Tool result belongs to an earlier data version", "error_type": "stale_data_binding", "dataset": name})
        payload["tool_receipt_ids"] = [str(receipt["id"]) for receipt in bound_receipts]
        payload["result_bindings"] = [
            {"receipt_id": receipt["id"], "tool_call_id": receipt.get("tool_call_id", ""),
             "result_sha256": receipt.get("structured_result_sha256") or receipt.get("result_sha256", ""),
             "data_identities": receipt.get("data_identities", {})}
            for receipt in bound_receipts
        ]
        from data_agent.tools.evidence_statistics import bind_computed_statistics
        try:
            bind_computed_statistics(payload, bound_receipts)
        except (ValueError, OSError, KeyError) as exc:
            return json.dumps({"error": f"Bound result cannot be verified: {exc}", "error_type": "invalid_result_binding"}, ensure_ascii=False)

    allowed_confidence = {"high", "medium", "low", "speculative"}
    confidence = str(payload.get("confidence", "")).strip().lower()
    if confidence not in allowed_confidence:
        return json.dumps({
            "error": f"Invalid confidence level: {payload.get('confidence')}",
            "error_type": "invalid_confidence",
            "allowed": sorted(allowed_confidence),
        }, ensure_ascii=False)
    payload["confidence"] = confidence

    # Optional fields - pass through if present
    if payload.get("competing_hypotheses") is not None:
        hypotheses = payload["competing_hypotheses"]
        if not isinstance(hypotheses, list):
            return json.dumps({
                "error": "competing_hypotheses must be a list of dicts",
                "error_type": "invalid_competing_hypotheses",
            }, ensure_ascii=False)
        # Structured relation entries are validated on submission (P5):
        # hypothesis_id + relation(supports/refutes) + metric + observed
        # direction. Legacy free-form dicts stay accepted as unvalidated
        # annotations that can never change hypothesis state.
        for entry in hypotheses:
            if isinstance(entry, dict) and ("relation" in entry or "hypothesis_id" in entry):
                valid = (
                    isinstance(entry.get("hypothesis_id"), str) and entry["hypothesis_id"].strip()
                    and entry.get("relation") in {"supports", "refutes"}
                    and isinstance(entry.get("metric"), str) and entry["metric"].strip()
                    and entry.get("observed") in {"increased", "decreased", "flat"}
                )
                if not valid:
                    return json.dumps({
                        "error": (
                            "competing_hypotheses 结构化关系必须包含 hypothesis_id、"
                            "relation(supports/refutes)、metric、observed(increased/decreased/flat)"
                        ),
                        "error_type": "invalid_competing_hypotheses",
                    }, ensure_ascii=False)
        payload["competing_hypotheses"] = hypotheses

    _valid_insight_types = {"trend", "anomaly", "contribution", "driver", "evaluation"}
    if payload.get("insight_type") is not None:
        insight_type = str(payload["insight_type"]).strip().lower()
        if insight_type not in _valid_insight_types:
            return json.dumps({
                "error": f"Invalid insight_type: {payload.get('insight_type')}",
                "error_type": "invalid_insight_type",
                "allowed": sorted(_valid_insight_types),
            }, ensure_ascii=False)
        payload["insight_type"] = insight_type

    if not is_stage3c0b_evidence:
        _mark_statistical_detail_status(payload)

    result = _persist_analysis_record("evidence_record", payload)
    payload = result.pop("payload", payload)
    if state is not None:
        result["state_stage"] = state.stage
        result["evidence_id"] = payload.get("id")
        try:
            from data_agent.session.task_manager import task_manager
            spec = state.analysis_spec if state is not None else {}
            completed_task_ids = task_manager.complete_matching_tasks_from_evidence(
                session_id=state.session_id,
                evidence=payload,
                analysis_spec_id=(spec or {}).get("id", ""),
            )
            if completed_task_ids:
                result["completed_task_ids"] = completed_task_ids
        except Exception as e:
            result["task_completion_error"] = str(e)
    if not is_stage3c0b_evidence:
        result["statistical_detail_status"] = payload.get("statistical_detail_status")
        result["statistical_detail_gaps"] = payload.get("statistical_detail_gaps", [])
        result["statistical_projection_gaps"] = payload.get("statistical_projection_gaps", [])
    return json.dumps(result, ensure_ascii=False)


@registry.register(
    name="get_analysis_summary",
    description="Read-only query: get a structured summary of the current analysis state including evidence records, insights, and stage. Use in conversation mode to answer questions about previous analysis results. Navigation only: recorded claims and confidence are research annotations, not current verified data facts.",
)
def get_analysis_summary() -> str:
    """Return a structured summary of current analysis state for conversation mode."""
    state = _current_state()
    if state is None:
        return json.dumps({"info": "No active analysis state found"}, ensure_ascii=False)

    summary_parts: dict[str, object] = {
        "stage": state.stage,
        "goal": state.goal or "-",
        "data_state": state.data_state,
    }

    # Evidence records summary
    evidence = state.evidence_records or []
    if evidence:
        evidence_summary = []
        for rec in evidence:
            entry = {
                "claim": rec.get("claim", ""),
                "confidence": rec.get("confidence", ""),
                "method": rec.get("method", ""),
            }
            if rec.get("sample_size") is not None:
                entry["sample_size"] = rec.get("sample_size")
            evidence_summary.append(entry)
        summary_parts["evidence_records"] = evidence_summary
        summary_parts["evidence_count"] = len(evidence)
    else:
        summary_parts["evidence_count"] = 0

    # Insight records summary
    insights = state.insight_records or []
    if insights:
        summary_parts["insight_records"] = [
            {"output": ins.get("output", ""), "type": ins.get("output_type", "")}
            for ins in insights
        ]
        summary_parts["insight_count"] = len(insights)
    else:
        summary_parts["insight_count"] = 0

    # Regression history
    if state.regression_history:
        summary_parts["last_regression"] = state.regression_history[-1]

    # Plan info
    if state.analysis_plan:
        summary_parts["has_plan"] = True
        summary_parts["plan_goal"] = state.analysis_plan.get("goal", "")

    return json.dumps(summary_parts, ensure_ascii=False)


@registry.register(
    name="record_answer_targets",
    description="Select verified host catalogue IDs for existing necessary delivery IDs. No tools, statistics, paths, values or completion declarations. target_json={requirement_revision,bindings:[{delivery_id,catalogue_ids}]}. The host revalidates original source versions, business scope and type.",
    schema_overrides={"target_json":{"type":"object","additionalProperties":False,"required":["requirement_revision","bindings"],"properties":{"requirement_revision":{"type":"integer"},"bindings":{"type":"array","minItems":1,"maxItems":128,"items":{"type":"object","additionalProperties":False,"required":["delivery_id","catalogue_ids"],"properties":{"delivery_id":{"type":"string"},"catalogue_ids":{"type":"array","minItems":1,"maxItems":128,"items":{"type":"string"}}}}}}}},
)
def record_answer_targets(target_json: dict) -> str:
    from data_agent.agent.context import get_current_context
    from data_agent.session.history import load_canonical_history
    from data_agent.agent.publication.requirements import record_execution_targets
    ctx=get_current_context()
    if ctx is None: raise ValueError("目标登记需要当前会话。")
    result=record_execution_targets(ctx.analysis_state,load_canonical_history(ctx.session_id),ctx.workspace,target_json)
    ctx.requirement_revision=ctx.analysis_state.requirement_revision
    return json.dumps(result,ensure_ascii=False)
