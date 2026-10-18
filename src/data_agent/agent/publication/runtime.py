"""Application ownership of one current publication snapshot and answer."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from data_agent.config import get_config
from data_agent.session.history import load_canonical_history
from .contracts import ContractError, HostSnapshot, encode, digest, SCHEMA, parse_draft
from .facts import load_receipt_result, resolve_artifact
from .native import resolve_native_claims, resolve_hypothesis_claims
from .requirements import update_requirements, bind_requirements, project_requirements, target_datasets, presentation_applies
from .service import PublicationService



CONSULTATION_INTENTS = {"simple_response","knowledge_qa","analysis_consultation","intent_negotiation","data_requirement"}


def current_request_uses_data(loop):
    latest=next((m.get("request_id") for m in reversed(loop.messages) if m.get("role")=="user" and m.get("request_id")),None)
    current=set(loop.context.turn_requirement_ids)
    return any(r.get("lifecycle_status")=="active" and (r["semantic_kind"]!="knowledge" or r.get("necessary_deliveries")) and (r["id"] in current or r.get("source_message_ref")==latest) for r in loop.context.analysis_state.answer_requirements)


def register_request(loop,user_input,intent):
    state=loop.context.analysis_state
    message=next((m for m in reversed(loop.messages) if m.get("role")=="user" and m.get("content")==user_input and m.get("request_id")),None)
    if message is None:
        # Confirmation machinery is not another user requirement/planner.
        loop.context.turn_requirement_ids=[r["id"] for r in state.answer_requirements if r.get("lifecycle_status")=="active"]
        return
    loop._auto_save()
    snapshot=load_canonical_history(loop.session_id)
    proposals=[]
    for item in intent.requested_outputs:
        span=item.get("exact_span")
        if not isinstance(span,str) or user_input.count(span)!=1:
            raise ContractError("request_span", "需求片段没有唯一原文位置。")
        start=user_input.index(span)
        proposal={"op":item.get("op","add"),"start":start,"end":start+len(span),"kind":item["kind"]}
        for key in ("target_id","business_scope","source_answer_id","presentation_style","presentation_role","presentation_scope","purposes"):
            if key in item: proposal[key]=deepcopy(item[key])
        proposals.append(proposal)
    if not proposals:
        consultation=intent.intent_type in CONSULTATION_INTENTS
        proposals=[{"op":"add","start":0,"end":len(user_input),"kind":"knowledge" if consultation else "presentation" if intent.intent_type=="result_followup" else "result"}]
    for proposal in proposals:
        if proposal["op"] in {"add", "replace"} and proposal["kind"]=="presentation" and "source_answer_id" not in proposal:
            prior=next((m for m in reversed(history_before_request(loop.messages,message)) if m.get("answer_ref")),None)
            if prior: proposal["source_answer_id"]=prior["answer_ref"]["answer_id"]
    ids=update_requirements(state,snapshot,message["request_id"],proposals,expected_revision=state.requirement_revision)
    for req in state.answer_requirements:
        if req["id"] in ids:
            if req.get("source_binding",{}).get("status")=="pending":
                pending=req["source_binding"]
                pending.setdefault("initial_data_identities",{n:i for n in target_datasets(req)
                    if (i:=loop.context.workspace._publication_data_identity(n))})
                continue
            expected=req.setdefault("source_data_identities",{})
            for name in target_datasets(req):
                identity=loop.context.workspace._publication_data_identity(name)
                if identity and name not in expected: expected[name]=identity
    loop.context.turn_requirement_ids=ids
    loop.context.requirement_revision=state.requirement_revision
    if intent.intent_type in CONSULTATION_INTENTS and not current_request_uses_data(loop):
        message["context_kind"]="knowledge"
    state.save()


def _chart_completion_binding(session_id, receipt, result, binding):
    if receipt.get("tool_name") != "create_chart" or (receipt.get("arguments", {}).get("chart_type") != "heatmap" and not result.get("chart_metadata_ref")):
        return {}
    root = (get_config().sessions_resolved / session_id).resolve()
    ref = result.get("chart_metadata_ref", "")
    full = (root / ref).resolve()
    if not ref.startswith("charts/") or full.parent != root / "charts" or full.suffix != ".json":
        raise ContractError("chart_metadata", "图表元数据引用越界。")
    raw = full.read_bytes()
    sha = "sha256:" + hashlib.sha256(raw).hexdigest()
    if sha != result.get("chart_metadata_sha256"):
        raise ContractError("chart_metadata", "图表元数据字节已变化。")
    metadata = json.loads(raw.decode("utf-8"))
    if any(metadata.get(key) != result.get(key) for key in ("correlation_audit", "observation_audit", "aggregation_audit", "completion_gap")):
        raise ContractError("chart_metadata", "图表范围与原回执不一致。")
    if result.get("artifact_path") != f"sessions/{session_id}/charts/{full.stem}.html":
        raise ContractError("chart_metadata", "图表回执与元数据文件不一致。")
    if metadata.get("filename") != full.with_suffix(".html").name:
        raise ContractError("chart_metadata", "图表元数据与图文件不一致。")
    identity = binding.get("data_identities", {}).get(metadata.get("dataset"), {})
    if identity and any(metadata.get("data_identity", {}).get(k) != identity.get(k) for k in ("version_id", "fingerprint")):
        raise ContractError("chart_metadata", "图表来源版本与回执不一致。")
    return {"completion_gap": deepcopy(metadata.get("completion_gap")),
            "chart_binding": {"metadata_ref": ref, "metadata_sha256": sha, "result_sha256": binding["result_sha256"]}}


def collect_products(state, session_id, *, receipt_ids=None):
    """Rebuild current products from the existing immutable receipt ledger."""
    claims,identities,gaps,artifacts,artifact_targets,effects=[],{},[],[],{},[]
    for receipt in state.tool_receipts:
        rid=receipt.get("id")
        if not rid or receipt_ids is not None and rid not in receipt_ids: continue
        try:
            from .native import OPERATION_TOOLS,operation_requested,resolve_operation_effect
            if operation_requested(receipt.get("tool_name"),receipt.get("arguments",{})):
                effect=resolve_operation_effect(session_id=session_id,receipt_id=rid)
                if effect is not None:
                    effects.append(effect);identities.update(effect["data_identities"])
                if receipt["tool_name"] not in {"transform_data","top_n","synthesize_time_series"}:continue
            _,_,result,binding=load_receipt_result(session_id=session_id,receipt_id=rid)
            if isinstance(result, dict) and result.get("artifact_path"):
                target = {"dataset": receipt.get("arguments", {}).get("name") or next(iter(binding["data_identities"])), "tool": receipt["tool_name"], "parameters": deepcopy(receipt.get("arguments", {})), "data_identities":deepcopy(binding["data_identities"]), "receipt_id":rid}
                target.update(_chart_completion_binding(session_id, receipt, result, binding))
                artifact_targets[result["artifact_path"]] = target
                identities.update(binding["data_identities"])
            resolved=resolve_native_claims(session_id=session_id,receipt_id=rid,result_paths=())
            claims.extend(resolved)
            for claim in resolved:
                gaps.extend(claim.get("target",{}).get("source_unit_gaps",[]))
            identities.update(binding["data_identities"])
            for claim in resolved:
                for proof in claim["basis_refs"]: identities.update(proof["data_identities"])
        except (ValueError,OSError,KeyError,TypeError,OverflowError) as exc:
            from .native import RESULT_FIELDS
            if receipt.get("tool_name") in set(RESULT_FIELDS) | OPERATION_TOOLS | {"describe_dataset","compare_periods","create_chart"}:
                gaps.append({"receipt_id":rid,"reason":str(exc),"code":getattr(exc,"code","receipt_unavailable")})
    for reference in state.hypothesis_sets:
        try:
            path=Path(reference["artifact_path"])
            candidate=json.loads(path.read_text(encoding="utf-8"))
            resolved,missing=resolve_hypothesis_claims(session_id=session_id,hypothesis_set=candidate,evidence_records=state.evidence_records)
            claims.extend(resolved); gaps.extend(missing)
            for claim in resolved:
                for basis in claim["basis_refs"]: identities.update(basis["data_identities"])
        except (ValueError,OSError,KeyError,TypeError) as exc:
            gaps.append({"hypothesis_id":reference.get("id"),"reason":str(exc)})
    # Actual existing artifact manifest; no model-created path or synthetic chart.
    from data_agent.session.history import list_artifacts
    for reference in list_artifacts(session_id):
        try:
            path=reference.get("path","")
            if reference.get("source")=="publication": continue
            root=(get_config().sessions_resolved/session_id).resolve()
            full=Path(path)
            if not full.is_absolute():
                parts=Path(path.replace("\\", "/")).parts
                full=root.joinpath(*parts[2:]) if len(parts)>2 and parts[:2]==("sessions",session_id) else (get_config().sessions_resolved.parent/path).resolve()
            if not full.is_relative_to(root): continue
            sha=reference["sha256"]
            artifact=resolve_artifact(session_id=session_id,artifact_id=reference["id"],path=full.relative_to(root).as_posix(),
                kind=reference.get("type","artifact"),description=reference.get("description") or full.name,expected_sha256=sha)
            if path not in artifact_targets:
                continue
            artifact["target"] = artifact_targets[path]
            artifacts.append(artifact)
        except (ValueError,OSError,KeyError,TypeError): continue
    return claims,artifacts,gaps,identities,effects


def snapshot_for_turn(loop):
    state=loop.context.analysis_state
    loop._auto_save()
    history=load_canonical_history(loop.session_id)
    from data_agent.session.history import list_artifacts
    confirmations=current_confirmation_refs(loop)
    # Prior completion is a projection of the same accepted objects, not a second ledger.
    answers={}
    prior_outcomes={}
    for reference in state.accepted_answers:
        try:
            answer=read_answer(loop.session_id,reference)
            answers[answer["answer_id"]]=answer
            prior_outcomes.update({r["requirement_id"]:r["status"] for r in answer["requirement_outcomes"]})
        except (ValueError,OSError,KeyError,TypeError):
            continue
    kind=getattr(loop.context.turn_intent,"intent_type","")
    mode="result_followup" if kind=="result_followup" else "consultation" if kind in CONSULTATION_INTENTS else "analysis"
    current=set(loop.context.turn_requirement_ids)
    last_request=next((m.get("request_id") for m in reversed(history.messages) if m.get("role")=="user" and m.get("request_id")),None)
    current.update(r["id"] for r in state.answer_requirements if r.get("source_message_ref")==last_request or r.get("retired_by",{}).get("source_message_ref")==last_request or any(ref["source_message_ref"]==last_request for ref in r.get("continuation_refs",[])))
    from types import SimpleNamespace
    scoped=SimpleNamespace(answer_requirements=[r for r in state.answer_requirements if presentation_applies(r,last_request) and (r["id"] in current or (mode!="consultation" and r.get("lifecycle_status")=="active" and prior_outcomes.get(r["id"])!="answered"))])
    # A consultation label does not erase explicit same-turn data obligations.
    # Pure knowledge still scopes out old unfinished analysis requirements above.
    if mode=="consultation" and current_request_uses_data(loop):
        mode="analysis"
    source_answers={r["source_answer_id"]:answers[r["source_answer_id"]] for r in scoped.answer_requirements if r.get("source_answer_id") in answers}
    current_deliveries={d["id"] for req in scoped.answer_requirements for d in req.get("necessary_deliveries",[])}
    relevant=set(loop.context.turn_receipt_ids) | {p["receipt_id"] for answer in source_answers.values() for c in answer["source_snapshot"]["claims"] for p in c["basis_refs"]}
    relevant.update(e["receipt_id"] for answer in source_answers.values() for e in answer["source_snapshot"].get("effects",[]))
    relevant.update(r["id"] for r in state.tool_receipts if current_deliveries.intersection(r.get("required_delivery_ids",[])))
    claims,artifacts,gaps,identities,effects=collect_products(state,loop.session_id,receipt_ids=relevant)
    # Data existence alone cannot turn pure knowledge into an analysis.
    if mode=="consultation" or not any(r.get("lifecycle_status")=="active" for r in scoped.answer_requirements): claims,identities,artifacts,effects=[],{},[],[]
    bindings=bind_requirements(scoped,claims,artifacts,effects=effects,source_answers=source_answers,product_gaps=gaps)
    for req in scoped.answer_requirements:
        if (mode == "result_followup" and req.get("lifecycle_status") == "active"
                and req["id"] in current and req["semantic_kind"] == "presentation" and not req.get("source_answer_id")):
            binding = bindings.setdefault(req["id"], {})
            binding.update(claim_ids=[], artifact_ids=[], open_purposes=[], gap={"status":"evidence_insufficient",
                "reason":"当前请求没有可定位的原接受答案。下一步：请指定需要解释的原答案。"})
        if req.get("lifecycle_status")=="active":
            # A concrete host execution failure is the reason no dataset was
            # installed; a generic missing-input diagnosis must not overwrite it.
            if bindings.get(req["id"], {}).get("gap", {}).get("status") == "failed":
                continue
            if any(not loop.context.workspace._receipt_identity_matches(name,identity) for name,identity in req.get("source_data_identities",{}).items()):
                bindings.setdefault(req["id"],{})["gap"]={"status":"evidence_insufficient","reason":"原业务目标的来源版本已变化："+", ".join(name for name,identity in req.get("source_data_identities",{}).items() if not loop.context.workspace._receipt_identity_matches(name,identity))+"；保留其他同版独立交付，变化来源须显式换版。"}
                continue
            missing=[name for name in target_datasets(req) if not loop.context.workspace._publication_dataset_exists(name)]
            if missing:
                binding=bindings.setdefault(req["id"],{})
                binding["gap"]={"status":"evidence_insufficient","reason":"当前会话没有数据集："+", ".join(missing)+"。下一步：请上传对应文件。"}
    if mode=="result_followup":
        owned={cid for value in bindings.values() for key in ("claim_ids","context_claim_ids") for cid in value.get(key,[])}
        claims=[c for c in claims if c["id"] in owned]
    projected=project_requirements(scoped,history,bindings)
    snapshot=HostSnapshot.freeze(session_id=loop.session_id,turn_id=getattr(loop,"_publication_turn_id","turn"),
        history_revision=history.revision,requirement_revision=state.requirement_revision,mode=mode,
        requirements=projected,claims=claims,artifacts=artifacts,effects=effects,data_identities=identities,
        plan_id=(state.analysis_plan or {}).get("id", ""),uses_result_context=mode=="result_followup",confirmation_refs=confirmations)
    loop._publication_runtime=(None,snapshot,history,gaps)
    return snapshot


def publication_prompt(loop, *, base_prompt=""):
    snapshot=snapshot_for_turn(loop)
    instruction="""<accepted_answer_contract>
工具调用按现有协议进行；终局必须只返回 answer_bindings.v2 JSON，无 Markdown 包裹。
结构：{"schema":"answer_bindings.v2","snapshot_digest":"宿主摘要","sections":[{"requirement_ids":["需求ID"],"parts":[{"kind":"claim","ref":"claimID"},{"kind":"text","purpose":"knowledge|interpretation|limitation|conditional_action","text":"解释","claim_refs":["当前claimID"]},{"kind":"artifact","ref":"产物ID"},{"kind":"effect","ref":"操作效果ID"}]}]}。
claim/产物/操作效果节点只引用宿主ID，不写替代值。一般咨询可用 text 示例；数据结果只能从当前 claim 引用。
按用户要求组织并改变表达、深度和语言；不自报全部完成。缺口由宿主生成，未来行动保留全部条件，不抢跑。
对存在宿主gap的需求，可分别用limitation给出具体缺口说明、conditional_action给出补充数据/确认或后续检验的条件性建议，逐项绑定该原需求ID。它们沿同一次开放片段审核，不替代宿主缺口、不授予事实或完成；无法说明时保留未核，不编造动作。
用户的原文需求与草案均在同一快照中；不把一个事实挪给不同目标、单位或窗口。
执行前调用现有record_analysis_plan，声明原需求ID、有类型必要交付及scope（datasets、metrics、quantity、parameters窗口）。measurement必须给明确业务统计量；多个来源、指标和图逐项声明，不靠成功结果倒推分母。纯操作使用kind=operation及scope.operation={action:原操作名,arguments:调用参数}，数据操作同时声明datasets；文件/扩展操作dataset_inputs=[]，不借用数据事实。宿主生成交付ID。
目录元数据使用table及scope.parameters={catalog_scope:"current_visible",catalog_output:"datasets"或"transform_history"}，真实空目录可声明datasets=[]、独立步骤dataset_inputs=[]；绑定宿主会话及授权范围快照，不把不可见范围判为空。普通测量仍须绑定真实数据版本。文件原文片段/目录也仅用table：parameters.file_scope=current_readable，file_output=content时声明file_path、file_offset（可选file_limit/file_max_chars/file_sha256），file_output=entries时声明file_pattern；datasets=[]、独立步骤dataset_inputs=[]。宿主绑定会话/路径权限/原SHA/实际读取或枚举时点，不核验文件内数据结论。
交付目录catalogue仅由真实已核回执生成，ID直接引用。不重复猜工具、统计键或结果路径；若需选择产品，调用record_answer_targets：
{target_json:{requirement_revision:当前版本,bindings:[{delivery_id:原必要交付ID,catalogue_ids:[宿主目录ID]}]}}。
绑定不能改变原来源、版本、指标、窗口或类型。原业务目标和开放解释分别验收；存在缺口时保留独立正确事实并说明下一步。

</accepted_answer_contract>
"""
    from data_agent.llm.request_policy import resolve_request_budget
    from data_agent.llm.client import _convert_tools
    cfg = get_config()
    model = getattr(loop.client, "model_id", None)
    if not isinstance(model, str): model = cfg.model_id
    output = getattr(loop.client, "max_tokens", None)
    if type(output) is not int: output = cfg.max_tokens
    policy = resolve_request_budget(model, cfg, output)
    messages = loop._provider_messages() or []
    messages = [{k:v for k,v in m.items() if k not in {"reply_id", "publication_rejected"}} for m in messages]
    tools = loop._tools_for_current_round()
    tools = _convert_tools(tools) if tools else None
    def measure(value):
        system = base_prompt + "\n\n" + instruction + encode(value)
        return policy.estimate([{"role":"system","content":system}] + messages, tools)["tokens"]
    context = model_publication_context(snapshot, loop.context.analysis_state,
                                        budget=policy.input_allowance, measure=measure,
                                        soft_budget=cfg.publication_soft_tokens, product_gaps=loop._publication_runtime[3])
    loop._publication_model_view_issue = context.get("model_view_issue")
    return instruction+encode(context)


def model_publication_context(snapshot, state, *, budget,product_gaps=(),measure=None,soft_budget=None):
    """Project the same immutable authority; proofs never occupy model slots.

    Necessary products and explanation context keep complete values and limits.
    Unrequested details remain in original receipts. Shared metadata is interned
    without changing it; a soft token target never removes a required item.
    """
    host = snapshot.as_dict()
    if measure is None:
        from data_agent.llm.request_policy import count_request_tokens
        cfg = get_config()
        measure = lambda value: count_request_tokens(cfg.model_id, [{"role":"system","content":encode(value)}], tokenizer_path=cfg.model_tokenizer)["tokens"]
    # A model view has no completion authority. The complete host snapshot and
    # original receipts remain unchanged, including unrequested audit tables.
    visible = {cid for req in host["requirements"] if not req["withdrawn"] for cid in req["claim_ids"]}
    for req in host["requirements"]:
        if not req["withdrawn"] and req["open_purposes"]:
            visible.update(req.get("context_claim_ids", req["claim_ids"]))
    deferred = [c for c in host["claims"] if c["id"] not in visible]
    view_host = deepcopy(host)
    view_host["claims"] = [c for c in view_host["claims"] if c["id"] in visible]
    for req in view_host["requirements"]:
        if "context_claim_ids" in req:
            req["context_claim_ids"] = [cid for cid in req["context_claim_ids"] if cid in visible]
    context = {"snapshot_digest":snapshot.digest, **view_host,
        "execution_targets":[{k:r[k] for k in ("id","semantic_kind","business_scope","necessary_deliveries","catalogue_bindings","continuation_refs","scope_issue","presentation_role","presentation_style","presentation_scope","purposes") if k in r}
                             for r in state.answer_requirements if r.get("lifecycle_status")=="active" and r["id"] in {q["id"] for q in host["requirements"]}]}
    from .deliveries import project_deliveries
    rows, projection=project_deliveries(state.answer_requirements,host["claims"],host["artifacts"],effects=host.get("effects",[]),product_gaps=product_gaps)
    context["catalogue_fields"]=["id","kind","metrics","quantity","parameters","declared_delivery_ids"]
    context["delivery_projection"]={did:{"catalogue_ids":r["catalogue_ids"],"gap":r["gap"]} for did,r in projection.items()}
    # Show only business-matched ownership. The complete predispatch step
    # membership stays in immutable receipts and need not repeat on every row.
    matched_ids = {}
    for did, produced in projection.items():
        for cid in produced["catalogue_ids"]:
            matched_ids.setdefault(cid, []).append(did)
    for row in rows:
        row["declared_delivery_ids"] = matched_ids.get(row["id"], [])
    context["catalogue"]=[[row[k] for k in context["catalogue_fields"]] for row in rows if row["artifact_ids"] or row.get("effect_ids")]
    catalogue_by_claim={r["id"]:r for r in rows if r["claim_ids"]}
    tables = {"scopes":[],"limitations":[],"targets":[],"parameters":[]}
    indexes = {key:{} for key in tables}
    def intern(key, value):
        encoded = encode(value)
        if encoded not in indexes[key]:
            indexes[key][encoded] = len(tables[key])
            tables[key].append(deepcopy(value))
        return indexes[key][encoded]
    context["execution_targets"]=deepcopy(context["execution_targets"])
    for execution_target in context["execution_targets"]:
        if "business_scope" in execution_target:
            execution_target["business_scope_ref"]=intern("scopes",execution_target.pop("business_scope"))
        for delivery in execution_target.get("necessary_deliveries",[]):
            delivery["scope_ref"]=intern("scopes",delivery.pop("scope"))
    def target_view(target):
        value=deepcopy(target)
        if "parameters" in value:value["parameters_ref"]=intern("parameters",value.pop("parameters"))
        product=value.get("business_product")
        if isinstance(product,dict) and "parameters" in product:
            product["parameters_ref"]=intern("parameters",product.pop("parameters"))
        return value
    # A fixed column schema removes repeated field names without losing IDs.
    context["claim_fields"] = ["id","label","value","unit","scope_ref","limitations_ref","target_ref","delivery_kind","quantity","declared_delivery_ids"]
    context["claims"] = [[c["id"],c["label"],deepcopy(c["value"]),c["unit"],
                          intern("scopes",c["scope"]),intern("limitations",c["limitations"]),
                          intern("targets",target_view(c["target"])) if "target" in c else None,
                          catalogue_by_claim.get(c["id"],{}).get("kind"),catalogue_by_claim.get(c["id"],{}).get("quantity"),
                          catalogue_by_claim.get(c["id"],{}).get("declared_delivery_ids",[])]
                         for c in view_host["claims"]]
    # Missing context_claim_ids means precisely claim_ids, as in the host contract.
    for requirement in context["requirements"]:
        if requirement.get("context_claim_ids") == requirement["claim_ids"]:
            requirement.pop("context_claim_ids")
    context["catalog_context"] = tables
    context["model_view_schema"] = "publication_model_view.v1"
    context["model_view_instruction"] = "claims每行按claim_fields命名；delivery_kind非空的claim ID同时是宿主目录ID；scope_ref/limitations_ref/target_ref为catalog_context数组精确索引；target及其business_product的parameters_ref精确引用catalog_context.parameters，参数没有省略或改变；execution_targets.business_scope_ref及necessary_deliveries.scope_ref也精确引用catalog_context.scopes。完整证明只在宿主，引用原ID，不补值或猜路径。context_claim_ids缺省时等于claim_ids。"
    receipts = {r["id"]:r for r in state.tool_receipts}
    deferred_details = {}
    for claim in deferred:
        for proof in claim["basis_refs"]:
            receipt = receipts.get(proof["receipt_id"])
            if receipt is None: continue
            key = (receipt["id"], proof["result_sha256"])
            item = deferred_details.setdefault(key, {"receipt_id":receipt["id"], "result_ref":receipt["detail_ref"]["path"],
                         "result_sha256":proof["result_sha256"], "file_sha256":receipt["detail_ref"]["sha256"].removeprefix("sha256:"), "claim_ids":[]})
            if claim["id"] not in item["claim_ids"]: item["claim_ids"].append(claim["id"])
    context["deferred_details"] = list(deferred_details.values())
    # The soft target never truncates a required value or excludes a source.
    # Expand to the actual whole-request allowance; split only at its hard bound.
    context["model_view_instruction"] += " 未请求且非解释所需的结果仅列于deferred_details；原件可用read_file及expected_sha256=file_sha256读取，不得把未读详情编成结论。预算按完整请求token核算，软目标不改变必答分母。"
    if soft_budget is not None:
        from data_agent.llm.request_policy import count_request_tokens
        cfg = get_config()
        view_tokens = count_request_tokens(cfg.model_id, [{"role":"system","content":encode(context)}], tokenizer_path=cfg.model_tokenizer)["tokens"]
        context["model_view_budget"] = {"soft_target_tokens":soft_budget, "expanded_past_soft_target":view_tokens > soft_budget}
    if measure(context) <= budget:
        return context
    # Metadata alone can exceed the budget. Retain every goal identity, expose
    # the boundary, and let the same service deliver all verified host facts.
    # The model cannot approve open prose when it did not consume this view.
    return {"snapshot_digest":snapshot.digest,"model_view_schema":"publication_model_view.v1",
            "model_view_issue":{"code":"publication_context_size","reason":"必要交付及上下文超过当前模型完整请求的token容量预算；宿主保留全部已核事实，开放解释本轮未核，需分批完成。"},
            "requirements":[{"id":r["id"],"source_turn":r["source_turn"],"withdrawn":r["withdrawn"]} for r in host["requirements"]],
            "claims":[],"artifacts":[],"model_view_instruction":"目录超预算，返回原snapshot_digest和sections=[]。不得生成解释、补值或宣称全部完成。"}


def _archive_candidate(loop, snapshot, raw, reasons):
    from data_agent.session.history import _write_json_atomic
    raw_digest = digest(raw)
    identity = digest(encode([snapshot.digest, raw_digest]))[7:]
    path = get_config().sessions_resolved / loop.session_id / "publication_rejected" / ("candidate_" + identity[:24] + ".json")
    path.parent.mkdir(parents=True,exist_ok=True)
    _write_json_atomic(path, {"schema":"publication_candidate.v2", "session_id":loop.session_id,
        "turn_id":snapshot.as_dict()["turn_id"], "snapshot_digest":snapshot.digest,
        "draft_digest":raw_digest, "raw_draft":raw, "reasons":reasons})


def publish(loop,raw):
    snapshot=snapshot_for_turn(loop)
    try: parse_draft(raw,snapshot.digest)
    except ContractError as exc:
        _archive_candidate(loop,snapshot,raw,[{"code":exc.code,"reason":str(exc)}])
        if not getattr(loop,"_turn_finalization_recovery_used",False):
            loop._turn_finalization_recovery_used=True
            loop._turn_finalization_mode=True
            loop.messages.append({"role":"system","content":"终局结构未接受："+str(exc)+"。仅在已有共享格式恢复额度内纠正为上述 JSON；不要重做分析或调用工具。"})
            return None,str(exc)
    def auditor(request):
        client=loop.auxiliary_llm_client or loop.client
        from data_agent.llm.client import LLMClient
        if isinstance(client,LLMClient): client=client.for_purpose()
        system=("审核数据相关开放片段，保持事实权威：只能 accept/reject/unassessed，不能新增或改写事实。"
            '核对原需求、当前证据、范围、单位、因果/推断/外推强度与全部行动条件。宿主gap下的limitation/conditional_action只可说明该需求的具体缺口和条件性补证/确认/检验建议，不能伪称已经完成或把现有缺口改为事实。claims是唯一的当前全篇事实目录，answer_context提供同一冻结全篇节点、产物和已核操作效果；操作效果只证明真实动作和对象，不属于数据事实或推断，事实/来源/限制块已交代的边界不要求每段逐字重复；可能误导的解释仍须附近限定。只按当前有效表达要求裁决，拒绝无据因果/外推/上线/对账。finding只能引用本part的requirement_ids/claim_refs；其他全篇事实是背景，不能当该part引用。'
            "返回 JSON：schema=publication_audit.v2，原 snapshot_digest/draft_digest，decisions 每项含 part_id,disposition,reason,evidence_refs（当前片段的需求/claim ID）。每项必须定位。")
        response=client.chat([{ "role":"user","content":encode(request)}],system=system,tools=None)
        return response.text
    cache=getattr(loop,"_publication_service",None)
    if cache is None or cache.snapshot.digest!=snapshot.digest:
        # One audit budget belongs to this turn even if a late snapshot changed.
        used=getattr(loop,"_publication_audit_used",False)
        def once(request):
            if getattr(loop,"_publication_audit_used",False): raise ContractError("audit_budget","本轮审核额度已使用。")
            loop._publication_audit_used=True
            return auditor(request)
        cache=PublicationService(snapshot,auditor=None if used else once,model_view_issue=getattr(loop,"_publication_model_view_issue",None))
        loop._publication_service=cache
    answer=cache.publish(raw)
    loop._accepted_answer=answer.as_dict()
    rejected=[t for t in loop._accepted_answer["render_trace"] if t["disposition"] in {"reject","rejected","unassessed"}]
    if rejected or loop._accepted_answer["issues"]:
        _archive_candidate(loop,snapshot,raw,loop._accepted_answer["issues"]+rejected)
    return loop._accepted_answer["body"],None


def read_answer(session_id,reference):
    root=(get_config().sessions_resolved/session_id).resolve()
    path=(root/reference["path"]).resolve()
    if not path.is_relative_to(root/"analyses") or path.suffix!=".json":
        raise ContractError("answer_path","接受答案引用越界。")
    raw=path.read_bytes()
    if "sha256:"+hashlib.sha256(raw).hexdigest()!=reference["sha256"]:
        raise ContractError("answer_digest","接受答案产物摘要不一致。")
    answer=json.loads(raw)
    if answer["session_id"]!=session_id or answer["answer_id"]!=reference["answer_id"] or answer["schema"]!=SCHEMA:
        raise ContractError("answer_identity","接受答案身份不一致。")
    if digest(answer["body"])!=answer["content_sha256"] or answer["content_sha256"]!=reference["content_sha256"]:
        raise ContractError("answer_body","接受答案正文摘要不一致。")
    return answer


def commit(loop,assistant_msg,final_text):
    from data_agent.session.history import commit_accepted_answer
    answer=getattr(loop,"_accepted_answer",None)
    if not answer or answer["body"]!=final_text:
        return "终局没有同一接受答案身份，未发布。"
    try:
        previous=[m for m in loop.messages if m.get("answer_id")==answer["answer_id"]]
        if previous:
            if len(previous)!=1 or read_answer(loop.session_id,previous[0]["answer_ref"])["body"]!=final_text:
                raise ContractError("answer_replay", "答案重复提交身份冲突。")
            return None
        snapshot=loop._publication_service.snapshot
        current=load_canonical_history(loop.session_id)
        if current.revision!=snapshot.as_dict()["history_revision"] or loop.context.analysis_state.requirement_revision!=snapshot.as_dict()["requirement_revision"]:
            raise ContractError("publication_revision","终局生成后规范历史或需求已变化。")
        if (loop.context.analysis_state.analysis_plan or {}).get("id", "")!=snapshot.as_dict()["plan_id"]:
            raise ContractError("publication_plan","终局生成后原计划身份已变化。")
        for claim in snapshot.as_dict()["claims"]:
            source=claim.get("derivation",{}).get("source_artifact")
            if source:
                refs=[r for r in loop.context.analysis_state.hypothesis_sets if r.get("id")==source["id"] and r.get("sha256")==source["sha256"]]
                if len(refs)!=1: raise ContractError("publication_hypothesis","终局生成后注册假设来源已变化。")
                resolve_artifact(session_id=loop.session_id,artifact_id=source["id"],path=source["path"],kind=source["type"],description=source["description"],expected_sha256=source["sha256"])
        from data_agent.session.workspace import workspace
        for dataset,identity in snapshot.as_dict()["data_identities"].items():
            if not workspace._receipt_identity_matches(dataset,identity):
                raise ContractError("publication_data_version","终局生成后相关数据版本已变化。")
        if current_confirmation_refs(loop)!=snapshot.as_dict()["confirmation_refs"]:
            raise ContractError("publication_confirmation", "终局生成后确认身份已变化。")
        proofs={p["receipt_id"]:p for c in snapshot.as_dict()["claims"] for p in c["basis_refs"]}
        for rid,proof in proofs.items():
            _,_,_,binding=load_receipt_result(session_id=loop.session_id,receipt_id=rid)
            if binding["result_sha256"]!=proof["result_sha256"] or binding.get("catalog_binding")!=proof.get("catalog_binding") or binding.get("file_binding")!=proof.get("file_binding") or binding.get("skills_binding")!=proof.get("skills_binding") or binding.get("mcp_binding")!=proof.get("mcp_binding"):
                raise ContractError("publication_receipt", "终局生成后原结果已变化。")
        from .native import resolve_operation_effect
        for effect in snapshot.as_dict().get("effects",[]):
            if resolve_operation_effect(session_id=loop.session_id,receipt_id=effect["receipt_id"])!=effect:
                raise ContractError("publication_effect","终局生成后操作对象、参数或权限已变化。")
        for artifact in answer["artifact_refs"]:
            resolve_artifact(session_id=loop.session_id,artifact_id=artifact["id"],path=artifact["path"],kind=artifact["type"],description=artifact["description"],expected_sha256=artifact["sha256"])
            if artifact.get("target", {}).get("chart_binding"):
                _, receipt, result, binding = load_receipt_result(session_id=loop.session_id, receipt_id=artifact["target"]["receipt_id"])
                checked = _chart_completion_binding(loop.session_id, receipt, result, binding)
                if any(artifact["target"].get(k) != checked[k] for k in checked):
                    raise ContractError("chart_metadata", "热图范围证明在终局生成后已变化。")
        # A new relevant receipt can change the final answer without changing
        # any proof already present in the earlier publication snapshot.
        if snapshot_for_turn(loop).digest != snapshot.digest:
            raise ContractError("publication_snapshot", "终局生成后当前交付快照已变化。")
        if snapshot.as_dict()["mode"]=="consultation" and not snapshot.as_dict()["uses_result_context"]:
            assistant_msg["context_kind"]="knowledge"
        committed=commit_accepted_answer(loop.session_id,loop.messages,assistant_msg,loop.context.analysis_state,answer,current,loop._build_session_meta())
        loop.messages[:]=committed
        loop._last_jsonl_idx=len(loop.messages)
        return None
    except Exception as exc:
        return "最终回答未能可靠保存，未发布成功结果："+type(exc).__name__+"。"


def export_current_answer_deliveries(loop):
    """Approved post-commit operation: preserve the sole AcceptedAnswer bytes."""
    from data_agent.tools.report import export_assistant_reply,_conversation_outputs
    from .native import operation_spec,resolve_operation_effect
    from .renderer import effect_text
    from data_agent.utils.atomic_files import rollback_atomic_writes
    answer=getattr(loop,"_accepted_answer",None)
    if not answer:return
    owners=[m for m in loop.messages if m.get("answer_id")==answer["answer_id"]]
    if len(owners)!=1 or not owners[0].get("reply_id"):raise ContractError("operation_reply","Saved answer has no unique reply owner.")
    owner=owners[0];source={"reply_id":owner["reply_id"],"answer_ref":deepcopy(owner["answer_ref"])}
    if read_answer(loop.session_id,source["answer_ref"])!=answer:raise ContractError("operation_reply","Saved answer changed before export.")
    state=loop.context.analysis_state;plan=state.analysis_plan or {}
    current={r["id"] for r in answer["source_snapshot"]["requirements"] if not r["withdrawn"]}
    for req in state.answer_requirements:
        if req["id"] not in current or req.get("lifecycle_status")!="active":continue
        for delivery in req.get("necessary_deliveries",[]):
            op=delivery.get("scope",{}).get("operation",{})
            if delivery["kind"]!="operation" or op.get("action")!="export_conversation" or op.get("arguments",{}).get("reply_target")!="current_answer":continue
            steps=[step for step in plan.get("method_plan",[]) if req["id"] in step.get("requirement_ids",[]) and any(d.get("id")==delivery["id"] for d in step.get("required_deliveries",[]))]
            if len(steps)!=1:continue
            args=operation_spec("export_conversation",op["arguments"])["arguments"]
            prior=[r for r in state.tool_receipts if r.get("tool_name")=="export_conversation" and delivery["id"] in r.get("required_delivery_ids",[])]
            done=False
            for receipt in prior:
                try:
                    effect=resolve_operation_effect(session_id=loop.session_id,receipt_id=receipt["id"])
                    if effect and effect.get("details",{}).get("source_reply")==source:done=True;break
                except (ValueError,OSError,KeyError,TypeError):pass
            if done:continue
            failure=req.get("source_binding",{}).get("operation_failures",{}).get(delivery["id"],{})
            if failure.get("source_reply")==source:
                loop._post_commit_export_failed=True
                loop._post_commit_export_notice=failure["reason"]
                continue
            before_receipts=deepcopy(state.tool_receipts)
            before_requirements=deepcopy(state.answer_requirements)
            before_turn_receipts=list(loop.context.turn_receipt_ids)
            binding=loop._capture_tool_execution_binding("export_conversation",args)
            binding.update(plan_id=plan["id"],plan_sha256=plan["plan_sha256"],step_id=steps[0]["step_id"],requirement_ids=[req["id"]],required_delivery_ids=[delivery["id"]])
            binding["operation_binding"]["source_reply"]=deepcopy(source)
            turn_state=getattr(loop.context,"turn_state",None)
            try:
                if turn_state is not None:
                    turn_state.ensure_can_call("export_conversation",args,source_version=source["answer_ref"]["sha256"])
                    turn_state.record_tool_call("export_conversation",args,source_version=source["answer_ref"]["sha256"])
                with rollback_atomic_writes():
                    result=export_assistant_reply(loop.session_id,format=args["format"],reply_id=source["reply_id"],title=args["title"],include_charts=args["include_charts"],_in_transaction=True)
                    if result.get("error"):raise ValueError(result["error"])
                    result.update(parameters=args,source_reply=deepcopy(source))
                    result["outputs"]=_conversation_outputs(loop.session_id,result)
                    if read_answer(loop.session_id,source["answer_ref"])!=answer:raise ValueError("Original accepted answer changed during export")
                    rid=loop._record_turn_tool_result("export_conversation",encode(result),args,"post_commit_"+delivery["id"],result,execution_binding=binding)
                    if not rid:raise ValueError("Original export receipt could not be saved")
                    effect=resolve_operation_effect(session_id=loop.session_id,receipt_id=rid)
                    notice=effect_text(effect);state.save()
                    if turn_state is not None:turn_state.record_tool_success()
            except Exception as exc:
                state.tool_receipts=before_receipts
                state.answer_requirements=before_requirements
                loop.context.turn_receipt_ids=before_turn_receipts
                result={"error":"Current accepted report export failed: "+str(exc),"error_type":"conversation_export_failed","source_reply":source}
                loop._record_turn_tool_result("export_conversation",encode(result),args,"post_commit_failed_"+delivery["id"],result,execution_binding=binding)
                notice="报告导出失败；原分析答案已保存。"+result["error"]
                failed_req=next(r for r in state.answer_requirements if r["id"]==req["id"])
                failed_req.setdefault("source_binding",{}).setdefault("operation_failures",{}).setdefault(delivery["id"],{"code":"conversation_export_failed","reason":notice}).update(source_reply=deepcopy(source))
                state.save()
                loop._post_commit_export_failed=True
                if turn_state is not None:turn_state.record_tool_error("export_conversation",args,result["error"])
            loop._post_commit_export_events.append({"type":"tool_call","name":"export_conversation","tool_call_id":"post_commit_"+delivery["id"],"arguments":args,"round":0})
            loop._post_commit_export_notice="；".join(filter(None,[getattr(loop,"_post_commit_export_notice",""),notice]))
            loop._post_commit_export_events.append({"type":"tool_result","name":"export_conversation","tool_call_id":"post_commit_"+delivery["id"],"web":{"summary":notice,"data":result},"duration_ms":0})


class ReadOnlySessionError(ValueError):
    """Stored sessions from a different runtime protocol remain read only."""


def is_read_only_session(stored):
    """Explicit incompatible protocols stay read only even without messages."""
    return bool(stored and stored.get("publication_schema") != SCHEMA
                and (stored.get("messages") or stored.get("publication_schema") not in (None, "")))


def require_writable(session_id):
    from data_agent.session.history import load_session
    if is_read_only_session(load_session(session_id)):
        raise ReadOnlySessionError("旧会话仅供查阅和导出，请新建会话开始分析。")


def current_confirmation_refs(loop):
    from data_agent.agent.confirmation.store import ConfirmationStore
    from data_agent.agent.confirmation.models import ConfirmationStatus
    loaded=ConfirmationStore(get_config().sessions_resolved,loop.session_id).load()
    if loaded.integrity_status!="ok": return []
    return [dict({k:getattr(r,k) for k in ("confirmation_id","response_id","session_id","decision_key","data_version","spec_version","response","status")},record_version=r.version)
        for r in loaded.records.values() if r.status in {ConfirmationStatus.RESOLVED,ConfirmationStatus.SKIPPED,ConfirmationStatus.CANCELLED} and r.response_id]


def resumed_answer(loop,confirmation_id):
    """Resolved replay cannot execute another continuation or reinterpret a choice."""
    current={r["confirmation_id"]:r for r in current_confirmation_refs(loop)}
    for ref in reversed(loop.context.analysis_state.accepted_answers):
        answer=read_answer(loop.session_id,ref)
        saved=[r for r in answer["source_snapshot"].get("confirmation_refs",[]) if r["confirmation_id"]==confirmation_id]
        if not saved: continue
        if len(saved)!=1 or current.get(confirmation_id)!=saved[0]:
            raise ContractError("confirmation_replay", "恢复确认身份已经改变。")
        from data_agent.session.workspace import workspace
        if not all(workspace._receipt_identity_matches(n,i) for n,i in answer["source_snapshot"]["data_identities"].items()):
            raise ContractError("confirmation_replay", "恢复后原答案的数据范围已经改变。")
        # Replay the original publication identity; a later failed execution
        # is another reply and must not become this answer's SSE/export owner.
        messages = load_canonical_history(loop.session_id).messages
        owners = [m for m in messages if m.get("answer_ref") == ref]
        if (len(owners) != 1 or owners[0].get("content") != answer["body"]
                or not owners[0].get("reply_id")):
            raise ContractError("confirmation_replay", "原接受答案的回复身份不可唯一核定。")
        return {"body": answer["body"], "reply_id": owners[0]["reply_id"]}
    return None


def history_before_request(messages,request):
    return messages[:next(i for i,m in enumerate(messages) if m is request)]
