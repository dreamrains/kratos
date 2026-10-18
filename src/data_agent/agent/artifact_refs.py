"""Shared hydration for compact JSON artifact references."""

from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any


def hydrate_refs(items: list[dict[str, Any]], *, trust_records: bool = False) -> list[dict[str, Any]]:
    pairs = [(item, _hydrate_ref(item, trust_records=trust_records)) for item in items if isinstance(item, dict)]
    current = {}
    for original, view in pairs:
        if view.get("trust_resolution", {}).get("status") == "current":
            current.setdefault((view.get("dataset"), original.get("artifact_type")), []).append(original)
    result = []
    for original, view in pairs:
        binding = original.get("source_binding")
        binding = binding if isinstance(binding, dict) else {}
        identity = binding.get("data_identity")
        identity = identity if isinstance(identity, dict) else {}
        old_version = identity.get("version_id")
        aliases = original.get("host_aliases")
        aliases = aliases if isinstance(aliases, dict) else {}
        group_names = {name for name in [original.get("dataset"), view.get("dataset"), *aliases] if isinstance(name, str)}
        fresh = [r for name in group_names for r in current.get((name, original.get("artifact_type")), [])]
        # Only a verified new producer in the same original owner/permission
        # namespace proves a version historical. No stored record is rewritten.
        permission = binding.get("permission_scope")
        permission = permission if isinstance(permission, dict) else {}
        if (view.get("trust_resolution", {}).get("status") == "unassessed" and old_version
                and any(r["source_binding"]["session_id"] == binding.get("session_id")
                    and all(r["source_binding"]["permission_scope"][key] == permission.get(key)
                            for key in ("project_root", "sessions_root"))
                    and r["source_binding"]["data_identity"]["version_id"] != old_version for r in fresh)):
            continue
        result.append(view)
    return result


def _hydrate_ref(item: dict[str, Any], *, trust_records: bool = False) -> dict[str, Any]:
    artifact_path = _text(item.get("artifact_path"))
    from data_agent.agent.context import get_current_context
    if (item.get("artifact_type") in {"dataset_contract", "route_proposal", "cleaning_log", "preview_digest"}
            or (trust_records and get_current_context() is not None)):
        return _hydrate_current_trust_ref(item)
    if not artifact_path:
        return item
    artifact = _read_json_artifact(artifact_path)
    if artifact is None:
        return item
    hydrated = {**item, **artifact}
    if item.get("host_aliases"):
        from data_agent.agent.context import get_current_context
        ctx = get_current_context()
        if ctx is not None:
            aliases = [name for name, identity in item["host_aliases"].items()
                       if identity and ctx.workspace._publication_data_identity(name) == identity]
            if len(aliases) == 1:
                hydrated["dataset"] = aliases[0]
    return hydrated


def _read_json_artifact(artifact_path: str) -> dict[str, Any] | None:
    try:
        path = Path(artifact_path)
        if path.suffix.lower() != ".json" or not path.is_file():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _text(value: Any) -> str:
    return " ".join(value.split()) if isinstance(value, str) else ""


def bind_trust_record(path, *, state, dataset, frame, producer_receipt_id=None):
    """The actual producer binds its original bytes to the current host object."""
    from data_agent.agent.context import get_current_context
    from data_agent.config import get_config
    from data_agent.session.workspace import Workspace
    ctx = get_current_context()
    if ctx is None or ctx.analysis_state is not state or ctx.session_id != state.session_id:
        return None
    identity = ctx.workspace._publication_data_identity(dataset)
    scope = ctx.workspace_scope
    derived = verified_child_contract_producer(ctx, dataset, producer_receipt_id) if producer_receipt_id else None
    if scope.phase in {"synthesis", "error"} or (scope.phase != "legacy" and dataset not in scope.allowed_datasets and derived is None):
        return None
    if producer_receipt_id and derived is None:return None
    if not identity or identity.get("fingerprint") != Workspace._frame_fingerprint(frame):
        return None
    cfg = get_config()
    return {"session_id":ctx.session_id, "dataset":dataset, "data_identity":identity,
            **({"producer_receipt_id":producer_receipt_id} if derived is not None else {}),
            "artifact_sha256":hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            "permission_scope":{"project_root":str(cfg.project_resolved.resolve()),
                "sessions_root":str(cfg.sessions_resolved.resolve()), "phase":scope.phase,
                "allowed_datasets":sorted(scope.allowed_datasets)}}


def _hydrate_current_trust_ref(item):
    from data_agent.agent.context import get_current_context
    from data_agent.config import get_config
    from data_agent.session.artifact_paths import resolve_reference, ARTIFACT_DIRS
    ctx = get_current_context()
    def unavailable(reason):
        # Neither compact self-reported fields nor stale expanded bytes grant authority.
        return {key:value for key,value in dict(item,
            trust_resolution={"status":"unassessed", "reason":reason}).items()
            if key not in {"field_roles", "evidence_requirements", "decisions", "risk_fields", "quality"}}
    binding = item.get("source_binding")
    if ctx is None or not isinstance(binding, dict) or binding.get("session_id") != ctx.session_id:
        return unavailable("Original host object/version/permission binding is unavailable.")
    cfg = get_config()
    permission = binding.get("permission_scope", {})
    if not isinstance(permission, dict):
        return unavailable("Original permission binding is malformed.")
    if (permission.get("project_root") != str(cfg.project_resolved.resolve())
            or permission.get("sessions_root") != str(cfg.sessions_resolved.resolve())):
        return unavailable("Original artifact permission roots changed.")
    dataset = item.get("dataset") if isinstance(item.get("dataset"), str) else ""
    expected = binding.get("data_identity")
    if binding.get("dataset") != dataset or not isinstance(expected, dict) or not expected.get("version_id"):
        return unavailable("Original dataset identity is missing.")
    derived = verified_child_contract_producer(ctx, dataset, binding.get("producer_receipt_id")) if binding.get("producer_receipt_id") else None
    if binding.get("producer_receipt_id") and derived is None:
        return unavailable("Original supported child producer/parent/child receipt cannot be verified.")
    if permission.get("phase") != "legacy" and dataset not in permission.get("allowed_datasets", []) and derived is None:
        return unavailable("Original producer had no declared dataset permission.")
    aliases = item.get("host_aliases", {})
    if not isinstance(aliases, dict):
        return unavailable("Host aliases are malformed.")
    try:
        matches = [name for name, identity in aliases.items()
            if identity == expected and ctx.workspace._publication_data_identity(name) == expected]
        if len(matches) > 1:
            return unavailable("Host alias is not unique.")
        current = matches[0] if matches else dataset
        # Control-plane identity checks do not acquire raw-frame permission.
        # Publication synthesis still verifies the exact originally read object.
        if ctx.workspace._publication_data_identity(current) != expected:
            return unavailable("Current object/version or read permission no longer matches.")
        scope = ctx.workspace_scope
        if scope.phase == "error" or (scope.phase not in {"legacy", "synthesis"} and current not in scope.allowed_datasets):
            return unavailable("Current scope cannot read this original.")
        own = cfg.sessions_resolved.resolve() / ctx.session_id
        original = Path(item["artifact_path"]).resolve()
        relative = original.relative_to(own)
        if not relative.parts or relative.parts[0] not in ARTIFACT_DIRS:
            return unavailable("Original is not a readable session artifact.")
        path = resolve_reference("sessions/"+ctx.session_id+"/"+relative.as_posix(),
            project=cfg.project_resolved, sessions=cfg.sessions_resolved, session_id=ctx.session_id)
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != binding.get("artifact_sha256"):
            return unavailable("Original artifact bytes changed.")
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict) or payload.get("id") != item.get("id") or payload.get("dataset") != dataset:
            return unavailable("Original record does not match its reference.")
        return dict(item, **{key:value for key,value in payload.items() if key != "dataset"},
                    dataset=current, trust_resolution={"status":"current"})
    except (ValueError, OSError, KeyError, TypeError, PermissionError, UnicodeError):
        return unavailable("Original artifact cannot be verified in the current permission scope.")


def unassessed_trust_records(state):
    active = getattr(state, "active_scope", {}).get("active_dataset", "")
    return [r for name in ("dataset_contracts", "route_proposals", "cleaning_logs")
        for r in hydrate_refs(getattr(state, name, []) or [], trust_records=True)
        if (not active or _trust_record_concerns(r, {active}))
        and r.get("trust_resolution", {}).get("status") == "unassessed"]


def trust_delivery_gap(state, delivery, candidates=()):
    """Read-only delivery projection; no state, migration, or extra ledger."""
    scope = delivery.get("scope", {})
    if (delivery.get("kind") == "measurement" and set(scope) == {"datasets", "quantity"}
            and scope["quantity"] == "rows"):
        return None  # Exact current full-table cardinality has no field dependency.
    names = set(scope.get("datasets", []))
    records = [r for name in ("dataset_contracts", "route_proposals", "cleaning_logs")
               for r in hydrate_refs(getattr(state, name, []) or [], trust_records=True)
               if _trust_record_concerns(r, names)]
    unresolved = [r for r in records if r.get("trust_resolution", {}).get("status") == "unassessed"]
    if unresolved:
        return {"status":"evidence_insufficient", "reason":"trust_record_unassessed: "
            +"; ".join(dict.fromkeys(r["trust_resolution"]["reason"] for r in unresolved))}
    blocked = [r for r in records if (r.get("quality") or {}).get("status") == "blocked"]
    if blocked and not (_verified_empty_distribution_diagnostic(state,delivery,candidates)
                        or _verified_native_quality_diagnostic(state,delivery,candidates)
                        or _verified_count_chart_diagnostic(state,delivery,candidates)):
        return {"status":"evidence_insufficient", "reason":"data_quality_blocked: "
            +"; ".join(dict.fromkeys(str(r.get("dataset", ""))+": "+str(issue)
                for r in blocked for issue in (r.get("quality", {}).get("block_issues") or ["Original contract blocks formal analysis."])))}
    return None


def _trust_record_concerns(record, names):
    binding = record.get("source_binding")
    binding = binding if isinstance(binding, dict) else {}
    identity = binding.get("data_identity")
    identity = identity if isinstance(identity, dict) else {}
    if (record.get("trust_resolution", {}).get("status") == "unassessed"
            and (not binding.get("dataset") or not identity.get("version_id"))):
        return True  # An unbound label cannot prove that a dependency is unrelated.
    aliases = record.get("host_aliases")
    aliases = aliases if isinstance(aliases, dict) else {}
    associated = {name for name in [record.get("dataset"), binding.get("dataset"), *aliases] if isinstance(name, str)}
    return bool(names.intersection(associated))


def _verified_empty_distribution_diagnostic(state, delivery, candidates):
    """Only host-verified zero-effective-value diagnostics survive a quality block."""
    scope=delivery.get("scope",{})
    if delivery.get("kind") not in {"table","measurement"} or not candidates or len(scope.get("datasets",[]))!=1 or not scope.get("metrics"):return False
    from data_agent.agent.context import get_current_context
    from data_agent.agent.publication.facts import load_receipt_result
    from data_agent.agent.publication.native import _validate_distribution_result
    ctx=get_current_context()
    if ctx is None or ctx.analysis_state is not state:return False
    try:
        for candidate in candidates:
            if not candidate.get("receipt_ids"):return False
            for rid in candidate["receipt_ids"]:
                context,receipt,result,_=load_receipt_result(session_id=ctx.session_id,receipt_id=rid)
                args=receipt["arguments"]
                if receipt["tool_name"]!="distribution_analysis" or args.get("name")!=scope["datasets"][0]:return False
                _validate_distribution_result(context,receipt,result)
                actual=ctx.workspace._publication_distribution_audit(args["name"],args.get("columns",""))
                if not actual or any(m not in actual or actual[m]["observation"]["count"]!=0 for m in scope["metrics"]):return False
        return True
    except (ValueError,OSError,KeyError,TypeError,PermissionError):return False



def _verified_native_quality_diagnostic(state, delivery, candidates):
    """Approved original diagnostics do not grant analysis or method readiness."""
    scope=delivery.get("scope",{});params=scope.get("parameters",{})
    if delivery.get("kind") not in {"table","measurement"} or not candidates or len(scope.get("datasets",[]))!=1:return False
    quality={"issues","total_issues","column_diagnostics","observation","rows"}
    tool=("detect_data_quality" if params.get("quality_output") in quality else
          "quick_profile" if params.get("diagnostic_output") in {"column_diagnostics","readiness"} else "")
    if not tool:return False
    from data_agent.agent.context import get_current_context
    from data_agent.agent.publication.facts import load_receipt_result
    from data_agent.agent.publication.contracts import encode
    ctx=get_current_context()
    if ctx is None or ctx.analysis_state is not state:return False
    try:
        for candidate in candidates:
            if not candidate.get("receipt_ids"):return False
            for rid in candidate["receipt_ids"]:
                context,receipt,result,_=load_receipt_result(session_id=ctx.session_id,receipt_id=rid)
                if receipt["tool_name"]!=tool or receipt["arguments"].get("name")!=scope["datasets"][0]:return False
                actual=context.workspace._publication_diagnostic_result(tool,receipt["arguments"])
                if actual is None or (encode(actual)!=encode(result) if tool=="detect_data_quality" else actual!=result):return False
        return True
    except (ValueError,OSError,KeyError,TypeError,PermissionError):return False



def verified_child_contract_producer(context, dataset, receipt_id):
    """Original operation proof for a new child; no tool scope or unit grant."""
    if context is None or not isinstance(receipt_id,str) or not receipt_id:return None
    try:
        from data_agent.agent.publication.native import resolve_operation_effect
        effect=resolve_operation_effect(session_id=context.session_id,receipt_id=receipt_id)
        supported=bool(effect and (effect['action']=='top_n' or effect['action']=='transform_data' and effect['arguments'].get('operation') in {'filter','select','rename','sort','group_aggregate','resample','pivot','merge'}))
        target=effect['object'].get('name') if supported else None
        if (not supported or not target or dataset is not None and dataset!=target
                or effect['object'].get('kind')!='dataset'
                or effect['permission_scope']!='current_task_dataset'
                or effect['object'].get('identity')!=context.workspace._publication_data_identity(target)):
            return None
        originals={**effect['before']['source_data_identities'],target:effect['object']['identity']}
        if any(not context.workspace._publication_persisted_identity_matches(n,i) for n,i in originals.items()):return None
        return effect
    except (ValueError,OSError,KeyError,TypeError):return None


def _verified_count_chart_diagnostic(state,delivery,candidates):
    """128 retains exact nonmissing record-count charts,not method readiness."""
    scope=delivery.get('scope',{})
    if delivery.get('kind')!='chart' or len(scope.get('datasets',[]))!=1 or not candidates:return False
    from data_agent.agent.context import get_current_context
    from data_agent.agent.publication.facts import load_receipt_result
    from data_agent.agent.publication.runtime import _chart_completion_binding
    from data_agent.config import get_config
    import json
    ctx=get_current_context()
    if ctx is None or ctx.analysis_state is not state:return False
    try:
        for candidate in candidates:
            if candidate.get('kind')!='chart' or len(candidate.get('artifact_ids',[]))!=1 or len(candidate.get('receipt_ids',[]))!=1:return False
            for rid in candidate['receipt_ids']:
                context,receipt,result,binding=load_receipt_result(session_id=ctx.session_id,receipt_id=rid)
                args=receipt['arguments'];name=args.get('data');identity=binding['data_identities'].get(name)
                if receipt['tool_name']!='create_chart' or name!=scope['datasets'][0] or not identity:return False
                proof=_chart_completion_binding(ctx.session_id,receipt,result,binding)
                if not proof.get('chart_binding') or proof.get('completion_gap'):return False
                import hashlib
                raw=(get_config().sessions_resolved/ctx.session_id/result['chart_metadata_ref']).read_bytes()
                if 'sha256:'+hashlib.sha256(raw).hexdigest()!=proof['chart_binding']['metadata_sha256']:return False
                metadata=json.loads(raw)
                if not context.workspace._publication_chart_count_matches(name,identity,args,metadata):return False
        return True
    except (ValueError,OSError,KeyError,TypeError,PermissionError,AttributeError):return False
