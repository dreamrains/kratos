"""Canonical request identities in the existing AnalysisSessionState ledger.

Semantic operations are intent proposals; exact origin validates identity,
not their linguistic interpretation. This module does not decide completion.
"""
from copy import deepcopy
import hashlib

from data_agent.session.history import CanonicalHistorySnapshot, _history_sha256
from .contracts import ContractError, fields, text, encode

KINDS = {"result", "knowledge", "presentation", "conditional_action", "gap"}
ORIGIN = "canonical_requirement.v4"


def _history(snapshot):
    if (not isinstance(snapshot, CanonicalHistorySnapshot) or type(snapshot.revision) is not int
            or snapshot.revision < 0 or snapshot.message_count != len(snapshot.messages)
            or snapshot.sha256 != _history_sha256(snapshot.messages)):
        raise ContractError("requirement_history", "需求必须来自完整且摘要匹配的规范历史。")
    return snapshot.messages


def _source(snapshot, ref):
    matches=[m["content"] for m in _history(snapshot) if isinstance(m,dict) and m.get("role")=="user"
             and isinstance(m.get("content"),str) and m.get("request_id")==ref]
    if len(matches)>1: raise ContractError("requirement_source", "原用户消息身份重复。")
    if not matches:
        # Follow only host byte-bound transcripts in canonical history, never an LLM summary.
        from data_agent.agent.context import get_current_context
        ctx=get_current_context()
        queue=[m.get("canonical_transcript") for m in snapshot.messages if m.get("canonical_transcript")]
        visited=set()
        while queue and ctx is not None:
            if len(visited)>=32: raise ContractError("requirement_archive_limit","原历史来源超过读取预算。")
            reference=queue.pop()
            from data_agent.session.history import read_canonical_transcript
            identity=(reference["filename"], reference["sha256"])
            if identity in visited: continue
            visited.add(identity)
            try:
                _, archived=read_canonical_transcript(ctx.session_id,reference)
            except ValueError as exc:
                raise ContractError("requirement_archive_digest", str(exc)) from exc
            found=[m["content"] for m in archived if m.get("role")=="user" and m.get("request_id")==ref]
            if found:
                if len(found)!=1: raise ContractError("requirement_source","原历史消息身份重复。")
                matches=found;break
            queue.extend(m["canonical_transcript"] for m in archived if m.get("canonical_transcript"))
    if len(matches)!=1:
        raise ContractError("requirement_source", "需求没有唯一的真实用户消息来源。")
    return matches[0]


def presentation_applies(requirement, current_request_id):
    return not (requirement.get("presentation_role") == "style"
        and requirement.get("presentation_scope") == "turn"
        and requirement.get("source_message_ref") != current_request_id)


def target_datasets(requirement):
    if requirement.get("scope_issue"): return []
    return sorted(set(requirement.get("business_scope",{}).get("datasets",[])) |
                  {n for d in requirement.get("necessary_deliveries",[]) for n in d["scope"].get("datasets",[])})


def update_requirements(state, snapshot, source_message_ref, changes, *, expected_revision):
    if type(expected_revision) is not int or expected_revision != state.requirement_revision:
        raise ContractError("requirement_revision", "需求 revision 已变化。")
    content = _source(snapshot, source_message_ref)
    if not isinstance(changes, list) or len(changes) > 128:
        raise ContractError("requirement_changes", "需求变更必须为有界列表。")
    staged = deepcopy(state.answer_requirements)
    if any(not isinstance(r, dict) or r.get("origin") != ORIGIN for r in staged):
        raise ContractError("legacy_requirements", "旧需求协议不能继续运行，请新建会话。")
    original = encode(staged)
    ids, touched = [], set()
    for proposal in changes:
        fields(proposal, {"op", "start", "end", "kind"}, {"target_id","business_scope","source_answer_id","presentation_style","presentation_role","presentation_scope","purposes"})
        op, start, end, kind = (proposal[k] for k in ("op", "start", "end", "kind"))
        if (not isinstance(op,str) or op not in {"add", "replace", "withdraw", "reuse"}
                or not isinstance(kind,str) or kind not in KINDS
                or type(start) is not int or type(end) is not int or not 0 <= start < end <= len(content)):
            raise ContractError("requirement_change", "需求操作、类型或原文范围无效。")
        if "source_answer_id" in proposal: text(proposal["source_answer_id"],limit=128)
        scope_issue=None
        if "business_scope" in proposal:
            from .deliveries import validate_business_scope
            try: validate_business_scope(proposal["business_scope"])
            except (ContractError,TypeError) as exc:
                if op!="add" or any(p.get("op","add")!="add" for p in changes):
                    raise ContractError("unresolved_business_scope", str(exc)) from exc
                scope_issue={"code":"unresolved_business_scope","field":"business_scope","reason":str(exc),"proposal":deepcopy(proposal["business_scope"])}
        if "presentation_style" in proposal and proposal["presentation_style"] not in {"business","analyst","manager","plain","technical"}:
            raise ContractError("requirement_style", "表达偏好无效。")
        if "presentation_role" in proposal and (kind!="presentation" or proposal["presentation_role"] not in {"style","delivery","explanation"}):
            raise ContractError("requirement_role", "表达需求职责无效。")
        if "presentation_scope" in proposal and (
                kind != "presentation" or proposal.get("presentation_role") != "style"
                or not proposal.get("presentation_style")
                or not isinstance(proposal["presentation_scope"], str)
                or proposal["presentation_scope"] not in {"turn", "session"}):
            raise ContractError("requirement_presentation_scope", "表达偏好生效范围无效。")
        if "purposes" in proposal:
            purposes=proposal["purposes"]
            if not isinstance(purposes,list) or not 1<=len(purposes)<=4 or any(not isinstance(v,str) or v not in {"knowledge","interpretation","limitation","conditional_action"} for v in purposes) or len(set(purposes))!=len(purposes):
                raise ContractError("requirement_purposes", "交付用途无效。")
        span = text(content[start:end])
        source = {"source_message_ref":source_message_ref,"source_start":start,"source_end":end}
        temporary_override = False
        if op != "add":
            target = proposal.get("target_id")
            found = [r for r in staged if r["id"] == target and r["lifecycle_status"] == "active"]
            if len(found) != 1 or target in touched:
                raise ContractError("requirement_target", "需求目标未知、已撤回或在同批重复修改。")
            touched.add(target)
            if op == "reuse":
                if kind != found[0]["semantic_kind"] or set(proposal) - {"op", "start", "end", "kind", "target_id"}:
                    raise ContractError("requirement_reuse", "等价复用必须引用同类原目标，不能改变执行范围或身份。")
                reference = dict(source, original_text=span, source_history_revision=snapshot.revision, source_history_digest=snapshot.sha256)
                references = found[0].setdefault("continuation_refs", [])
                if reference not in references:
                    references.append(reference)
                ids.append(target)
                continue
            temporary_override = (op == "replace" and kind == "presentation"
                and proposal.get("presentation_role") == "style" and proposal.get("presentation_style")
                and proposal.get("presentation_scope", "turn") == "turn"
                and found[0].get("presentation_role") == "style"
                and found[0].get("presentation_scope", "session") == "session")
            if not temporary_override:
                found[0].update(lifecycle_status="withdrawn",retired_by=source)
        elif "target_id" in proposal:
            raise ContractError("requirement_target", "新增需求不能携带替换目标。")
        if op == "withdraw":
            continue
        rid = "rq_" + hashlib.sha256(encode([state.session_id,source_message_ref,start,end,kind]).encode()).hexdigest()[:20]
        existing = [r for r in staged if r["id"] == rid]
        if existing:
            if existing[0]["lifecycle_status"] != "active":
                raise ContractError("requirement_revival", "旧输入不能复活已撤回需求。")
        else:
            staged.append(dict(id=rid,original_text=span,semantic_kind=kind,lifecycle_status="active",origin=ORIGIN,
                               business_scope={},source_history_revision=snapshot.revision,source_history_digest=snapshot.sha256,**source))
        if "business_scope" in proposal:
            req=next(r for r in staged if r["id"]==rid)
            if scope_issue: req["scope_issue"]=scope_issue
            else: req["business_scope"]=deepcopy(proposal["business_scope"])
        if "source_answer_id" in proposal: next(r for r in staged if r["id"]==rid)["source_answer_id"]=proposal["source_answer_id"]
        req=next(r for r in staged if r["id"]==rid)
        if op=="replace" and not temporary_override:
            req["source_binding"]={"status":"pending","replaces_requirement_id":target}
        for key in ("presentation_style","presentation_role","presentation_scope","purposes"):
            if key in proposal: req[key]=deepcopy(proposal[key])
        if req.get("presentation_role")=="style" and req.get("presentation_style"):
            # New unspecified preferences belong only to their source request.
            # Missing scope in historical records retains its original semantics.
            req.setdefault("presentation_scope", "turn")
            for prior in staged:
                same_scope = (prior.get("presentation_scope", "session") == req["presentation_scope"]
                    and (req["presentation_scope"] == "session" or prior.get("source_message_ref") == source_message_ref))
                if prior["id"]!=rid and prior.get("presentation_role")=="style" and prior.get("presentation_style") and prior["lifecycle_status"]=="active" and same_scope:
                    prior.update(lifecycle_status="withdrawn",retired_by=source)

        ids.append(rid)
    # History retains retired obligations; the current snapshot and each
    # change batch have their own bounds. History length is not a turn budget.
    if encode(staged) != original:
        state.answer_requirements = staged
        state.requirement_revision += 1
    return ids


def project_requirements(state, snapshot, bindings):
    _history(snapshot)
    if not isinstance(bindings, dict) or set(bindings) - {r.get("id") for r in state.answer_requirements}:
        raise ContractError("requirement_binding", "绑定包含未知需求。")
    result = []
    for req in state.answer_requirements:
        if req.get("origin") != ORIGIN:
            raise ContractError("legacy_requirements", "旧需求不转换为当前运行协议。")
        binding = deepcopy(bindings.get(req["id"], {}))
        fields(binding, set(), {"claim_ids","context_claim_ids","artifact_ids","effect_ids","open_purposes","gap"})
        try:
            source = _source(snapshot, req["source_message_ref"])
            if source[req["source_start"]:req["source_end"]] != req["original_text"]:
                raise ContractError("requirement_origin", "需求原文身份已改变。")
            for ref in req.get("continuation_refs", []):
                if _source(snapshot, ref["source_message_ref"])[ref["source_start"]:ref["source_end"]] != ref["original_text"]:
                    raise ContractError("requirement_origin", "续问复用的原文身份已改变。")
        except (ContractError,OSError,KeyError,TypeError,ValueError):
            result.append(dict(id=req["id"],text=req["original_text"],source_turn=req["source_message_ref"],
                claim_ids=[],artifact_ids=[],open_purposes=[],withdrawn=req["lifecycle_status"] == "withdrawn",
                gap={"status":"evidence_insufficient","reason":"无法在当前规范历史核实该需求的唯一原文来源。"}))
            continue
        if req.get("scope_issue"):
            result.append(dict(id=req["id"],text=req["original_text"],source_turn=req["source_message_ref"],claim_ids=[],artifact_ids=[],open_purposes=[],withdrawn=req["lifecycle_status"]=="withdrawn",gap={"status":"failed","reason":"unresolved_business_scope: "+req["scope_issue"]["reason"]}))
            continue
        purposes = binding.get("open_purposes", [])
        if not binding and req["semantic_kind"] == "knowledge": purposes = ["knowledge"]
        if not binding and req["semantic_kind"] in {"presentation", "conditional_action"}:
            purposes = ["interpretation" if req["semantic_kind"] == "presentation" else "conditional_action"]
        gap = binding.get("gap")
        if not (binding.get("claim_ids") or binding.get("artifact_ids") or binding.get("effect_ids") or purposes or gap):
            gap = ({"status":"evidence_insufficient","reason":"该判断尚无对应的当前可核证据。"} if req["semantic_kind"]=="gap"
                   else {"status":"not_computed","reason":"该需求尚无对应的成功计算或宿主交付绑定。"})
        result.append(dict(id=req["id"],text=req["original_text"],source_turn=req["source_message_ref"],
            claim_ids=binding.get("claim_ids",[]),context_claim_ids=binding.get("context_claim_ids",[]),artifact_ids=binding.get("artifact_ids",[]),effect_ids=binding.get("effect_ids",[]),open_purposes=purposes,
            gap=gap,withdrawn=req["lifecycle_status"] == "withdrawn"))
    return result


def resolve_confirmation(current_request):
    """Read a durable choice against a fresh host-built request, not model text."""
    from data_agent.agent.context import get_current_context
    from data_agent.agent.confirmation.models import ConfirmationRequest, ConfirmationStatus, AnswerMode
    from data_agent.agent.confirmation.store import ConfirmationStore
    from data_agent.agent.confirmation.decision import DECISION_KINDS
    from data_agent.config import get_config
    ctx = get_current_context()
    if (not isinstance(current_request, ConfirmationRequest) or ctx is None
            or current_request.session_id != ctx.session_id or not current_request.data_version or not current_request.spec_version):
        raise ContractError("confirmation_context", "确认没有当前宿主请求和精确范围版本。")
    loaded = ConfirmationStore(get_config().sessions_resolved, ctx.session_id).load()
    record = loaded.records.get(current_request.confirmation_id)
    if (loaded.integrity_status != "ok" or record is None or record.status != ConfirmationStatus.RESOLVED
            or record.answer_mode != AnswerMode.SINGLE_SELECT or not record.response_id
            or record.resolution_action != "record_confirmation_answer"
            or record.resolution_params.get("decision_kind") not in DECISION_KINDS):
        raise ContractError("confirmation_unresolved", "确认未有效完成或不是业务口径决定。")
    if any(getattr(record,k) != getattr(current_request,k) for k in (
        "session_id","decision_key","data_version","spec_version","resolution_action","resolution_params","options")):
        raise ContractError("confirmation_scope", "确认的业务范围、选项或数据/规格版本已变化。")
    if record.response not in {o.value for o in record.options}:
        raise ContractError("confirmation_response", "确认响应不是原选项的稳定值。")
    return {"confirmation_id":record.confirmation_id,"response_id":record.response_id,"session_id":record.session_id,
            "decision_key":record.decision_key,"data_version":record.data_version,"spec_version":record.spec_version,
            "response":record.response,"record_version":record.version}


def record_execution_targets(state, history, workspace, payload):
    """Bind existing delivery IDs to freshly verified host catalogue IDs."""
    from .deliveries import catalogue, matches
    from .runtime import collect_products
    fields(payload,{"requirement_revision","bindings"})
    if type(payload["requirement_revision"]) is not int or payload["requirement_revision"]!=state.requirement_revision:
        raise ContractError("requirement_revision","需求版本已变化。")
    rows=payload["bindings"]
    if not isinstance(rows,list) or not 1<=len(rows)<=128:
        raise ContractError("delivery_bindings","绑定数量无效。")
    claims,artifacts,_,_,effects=collect_products(state,state.session_id)
    products={r["id"]:r for r in catalogue(claims,artifacts,effects)}
    staged=deepcopy(state.answer_requirements); seen=set()
    for row in rows:
        fields(row,{"delivery_id","catalogue_ids"})
        did=text(row["delivery_id"],limit=128)
        owners=[(req,d) for req in staged if req.get("lifecycle_status")=="active" for d in req.get("necessary_deliveries",[]) if d["id"]==did]
        if len(owners)!=1 or did in seen: raise ContractError("delivery_identity","交付未知、重复或已撤回。")
        req,delivery=owners[0];seen.add(did)
        original=_source(history,req["source_message_ref"])
        if original[req["source_start"]:req["source_end"]]!=req["original_text"]:
            raise ContractError("requirement_origin","原需求来源已变化。")
        ids=row["catalogue_ids"]
        if not isinstance(ids,list) or not 1<=len(ids)<=128 or len(set(encode(i) for i in ids))!=len(ids):
            raise ContractError("catalogue_ids","引用必须是唯一的有界宿主目录ID。")
        expected=req.get("source_data_identities",{})
        if any(not workspace._receipt_identity_matches(n,i) for n,i in expected.items()):
            raise ContractError("requirement_version","原业务来源版本已变化。")
        if any(not isinstance(i,str) or i not in products or products[i].get("source_message_ref") not in {None,req["source_message_ref"]} or not matches(delivery,products[i],expected) for i in ids):
            raise ContractError("delivery_mismatch","目录产品不符合原交付的来源、指标、窗口或类型。")
        req.setdefault("catalogue_bindings",{})[did]=list(ids)
    before=deepcopy(vars(state))
    try:
        if staged!=state.answer_requirements:
            import json
            from data_agent.utils.atomic_files import rollback_atomic_writes
            with rollback_atomic_writes():
                state.answer_requirements=staged
                state.requirement_revision+=1
                path=state.save()
                if json.loads(path.read_text(encoding="utf-8"))!=state.to_dict():
                    raise ContractError("target_persistence", "目标绑定持久化读回不一致。")
    except BaseException:
        vars(state).clear()
        vars(state).update(before)
        raise
    return {"requirement_revision":state.requirement_revision,"bound_delivery_ids":sorted(seen),"status":"host_verified_bindings"}


def _context_claim_ids(requirement, claims, owned, prior_ids):
    scope=set(target_datasets(requirement)); allowed=[]
    for claim in claims:
        if claim["id"] in owned or prior_ids is not None and claim["id"] in prior_ids:
            allowed.append(claim["id"]);continue
        if prior_ids is not None: continue
        sources={n for p in claim["basis_refs"] for n in p["data_identities"]}
        if not sources or not sources.issubset(scope): continue
        parameters=claim.get("target",{}).get("parameters",{})
        if all(parameters.get(k)==v for k,v in requirement.get("business_scope",{}).get("parameters",{}).items()):
            allowed.append(claim["id"])
    return allowed


def bind_requirements(state,claims,artifacts=(),*,effects=(),source_answers=None,product_gaps=()):
    from .deliveries import project_deliveries, OPEN_KINDS
    _,projection=project_deliveries(state.answer_requirements,claims,artifacts,effects=effects,product_gaps=product_gaps)
    bindings={}
    for req in state.answer_requirements:
        if req.get("lifecycle_status")!="active": continue
        binding={};bindings[req["id"]]=binding;prior_ids=None
        pending = req.get("source_binding", {})
        load_failures = [v for name, v in pending.get("load_failures", {}).items() if name in target_datasets(req)]
        if load_failures:
            binding["gap"] = {"status": "failed", "reason": "；".join(dict.fromkeys(v["reason"] for v in load_failures))}
            continue
        if pending.get("status") == "pending" and any(not pending.get("verified_load_receipts", {}).get(n) for n in pending.get("required_load_datasets", [])):
            binding["gap"] = {"status": "evidence_insufficient", "reason": "新版来源尚未成功加载核验；旧版数据与已接受答案保留，不能代替新版目标。"}
            continue
        if req.get("source_answer_id"):
            prior=(source_answers or {}).get(req["source_answer_id"])
            if prior is None:
                binding["gap"]={"status":"evidence_insufficient","reason":"指定原接受答案无法核实，不能猜测最新结果。"};continue
            prior_ids={t["ref"] for t in prior["render_trace"] if t["kind"]=="claim" and t["disposition"]=="accepted"}
            binding["claim_ids"]=[c["id"] for c in claims if c["id"] in prior_ids]
            prior_effects={t["ref"] for t in prior["render_trace"] if t["kind"]=="effect" and t["disposition"]=="accepted"}
            binding["effect_ids"]=[e["id"] for e in effects if e["id"] in prior_effects]
            effect_gaps=[e["completion_gap"] for e in effects if e["id"] in prior_effects and e.get("completion_gap")]
            if effect_gaps:binding["gap"]={"status":"evidence_insufficient","reason":"；".join(dict.fromkeys(g["reason"] for g in effect_gaps))}
            if prior_effects-set(binding["effect_ids"]):binding["gap"]={"status":"evidence_insufficient","reason":"原答案的操作对象或效果已变化，不能复用旧完成凭据。"}
            if prior_ids and not binding["claim_ids"]:
                binding["gap"]={"status":"evidence_insufficient","reason":"原答案没有同版本当前可核结果。"}
        deliveries=req.get("necessary_deliveries",[])
        owned=[];produced=[];operated=[];missing=[]
        for delivery in deliveries:
            if delivery["kind"] in OPEN_KINDS: continue
            result=projection[delivery["id"]]
            owned.extend(result["claim_ids"]);produced.extend(result["artifact_ids"]);operated.extend(result["effect_ids"])
            if result["gap"]: missing.append(result["gap"])
        if owned: binding["claim_ids"]=list(dict.fromkeys(owned))
        if produced: binding["artifact_ids"]=list(dict.fromkeys(produced))
        if operated: binding["effect_ids"]=list(dict.fromkeys(operated))
        if missing: binding["gap"]={"status":"failed" if any(g["status"]=="failed" for g in missing) else "evidence_insufficient" if any(g["status"]=="evidence_insufficient" for g in missing) else "not_computed","reason":"；".join(dict.fromkeys(g["reason"] for g in missing))}
        if req["semantic_kind"]=="result" and not deliveries and prior_ids is None:
            binding["gap"]={"status":"not_computed","reason":"原业务目标尚未在执行前声明必要交付；成功工具调用不自动代表目标完成。"}
        purposes=list(req.get("purposes",[]))
        purposes.extend(d["kind"] for d in deliveries if d["kind"] in OPEN_KINDS)
        if not purposes and req["semantic_kind"] in {"knowledge","presentation","conditional_action"}:
            purposes=[{"knowledge":"knowledge","presentation":"interpretation","conditional_action":"conditional_action"}[req["semantic_kind"]]]
        if purposes: binding["open_purposes"]=list(dict.fromkeys(purposes))
        contextual=_context_claim_ids(req,claims,binding.get("claim_ids",[]),prior_ids)
        if contextual: binding["context_claim_ids"]=contextual
    return bindings
