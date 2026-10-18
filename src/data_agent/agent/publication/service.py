"""One composition boundary for facts, consultation, open text and coverage.

This service has no tool executor, planner, storage or Provider transport. The
application owns receipt resolution, the one turn instance and durable commit.
"""
from .audit import review_parts
from .contracts import AcceptedAnswer, ContractError, SCHEMA, PURPOSES, digest, parse_draft
from .renderer import Renderer, STATUS_LABELS, artifact_text, effect_text


class PublicationService:
    def __init__(self, snapshot, *, auditor=None, model_view_issue=None):
        self.snapshot = snapshot
        self.auditor = auditor
        self.model_view_issue = model_view_issue
        self._review_digest = None
        self._review_result = None
        self._answer_cache = None

    def publish(self, raw_draft):
        try:
            raw_digest = digest(raw_draft if isinstance(raw_draft,str) else "")
        except UnicodeEncodeError:
            # Preserve a deterministic rejected-input identity without passing
            # invalid Unicode into the body or the audit transport.
            raw_digest = digest(ascii(raw_draft))
        if self._answer_cache is not None and self._answer_cache[0] == raw_digest:
            return self._answer_cache[1]
        host = self.snapshot.as_dict()
        requirements = {r["id"]:r for r in host["requirements"]}
        active = {rid:r for rid,r in requirements.items() if not r["withdrawn"]}
        claims = {c["id"]:c for c in host["claims"]}
        artifacts = {a["id"]:a for a in host["artifacts"]}
        effects = {e["id"]:e for e in host.get("effects",[])}
        pure_consultation = host["mode"] == "consultation" and not host["uses_result_context"] and not claims
        issues, nodes, open_parts = [], [], []
        try:
            if self.model_view_issue:
                raise ContractError(self.model_view_issue["code"],self.model_view_issue["reason"])
            draft = parse_draft(raw_draft,self.snapshot.digest)
        except ContractError as exc:
            draft = {"sections":[]}
            issues.append({"code":exc.code,"reason":str(exc),"part_id":None})
        issues.extend(draft.get("issues", []))
        for si,section in enumerate(draft["sections"]):
            rids = section["requirement_ids"]
            if any(rid not in requirements for rid in rids):
                issues.append({"code":"unknown_requirement_ref","reason":"section 引用了未知需求。","part_id":f"s{si}"})
                continue
            rids = [rid for rid in rids if rid in active]
            if not rids:
                continue
            for pi,part in enumerate(section["parts"]):
                pid = f"s{si}p{pi}"
                node = dict(part,part_id=pid,requirement_ids=rids)
                error = None
                if part["kind"] == "invalid":
                    error = (part["code"], part["reason"])
                elif part["kind"] == "claim" and part["ref"] not in claims:
                    error = ("unknown_claim_ref","没有当前宿主 claim。")
                elif part["kind"] == "artifact" and part["ref"] not in artifacts:
                    error = ("unknown_artifact_ref","没有当前宿主产物。")
                elif part["kind"]=="effect" and part["ref"] not in effects:
                    error=("unknown_effect_ref","没有当前已核操作效果。")
                elif part["kind"] in {"claim", "artifact", "effect"}:
                    binding_key = {"claim":"claim_ids","artifact":"artifact_ids","effect":"effect_ids"}[part["kind"]]
                    owners = [rid for rid in rids if part["ref"] in active[rid].get(binding_key,[])]
                    if not owners:
                        error = ("unbound_deliverable_ref", "引用未绑定当前 section 的有效需求。")
                    else:
                        node["requirement_ids"] = owners
                elif part["kind"] == "text":
                    supported_rids = [rid for rid in rids if (pure_consultation and part["purpose"] in PURPOSES)
                        or part["purpose"] in active[rid]["open_purposes"]
                        or part["purpose"] in {"interpretation","limitation"} and active[rid].get("context_claim_ids",active[rid]["claim_ids"])
                        or active[rid]["gap"] is not None and part["purpose"] in {"limitation", "conditional_action"}]
                    if not supported_rids:
                        error = ("unrequested_purpose","片段不属于当前需求的开放交付。")
                    elif any(cid not in claims or not any(cid in active[rid].get("context_claim_ids",active[rid]["claim_ids"]) for rid in supported_rids)
                             for cid in part["claim_refs"]):
                        error = ("unbound_text_claim","开放片段引用不属于该目标的当前同范围解释证据。")
                    else:
                        node["requirement_ids"] = supported_rids
                        open_parts.append(node)
                if error:
                    issues.append({"code":error[0],"reason":error[1],"part_id":pid})
                    node["error"] = error[1]
                nodes.append(node)
        requires_review = host["mode"] != "consultation" or host["uses_result_context"] or bool(claims)
        if open_parts and requires_review:
            if self._review_digest is None:
                # Reserve before dispatch so exceptions and malformed replies use
                # the same one-turn budget as a successful review.
                self._review_digest = raw_digest
                referenced = {cid for part in open_parts for cid in part["claim_refs"]}
                # The host verifies receipt proofs; review consumes immutable values,
                # units, scope and limits without repeating the proof graph per cell.
                context_ids=referenced | {cid for r in active.values() for cid in r["claim_ids"]}
                review_claims={cid:{k:c[k] for k in ("id","label","value","unit","scope","limitations")}
                               for cid,c in claims.items() if cid in context_ids}
                request = {"schema":"publication_audit_request.v3","snapshot_digest":self.snapshot.digest,
                           "draft_digest":raw_digest,"requirements":list(active.values()),
                           "claims":list(review_claims.values()),"parts":open_parts,
                           "answer_context":{"artifacts":[a for aid,a in artifacts.items() if any(aid in r["artifact_ids"] for r in active.values())],
                                             "effects":[e for eid,e in effects.items() if any(eid in r.get("effect_ids",[]) for r in active.values())],
                                             "nodes":[n for n in nodes if "error" not in n]}}
                self._review_result = review_parts(request,self.auditor)
            if self._review_digest == raw_digest:
                decisions, audit_status = self._review_result
            else:
                decisions = {p["part_id"]:{"disposition":"unassessed","reason":"本轮一次审核额度已使用，新片段未审核。"} for p in open_parts}
                audit_status = "unavailable"
        else:
            decisions = {p["part_id"]:{"disposition":"accept","reason":"纯咨询无数据结果语义审核依赖。"} for p in open_parts}
            audit_status = "not_applicable"
        render_context_ids = {cid for r in active.values() for cid in r["claim_ids"] + r.get("context_claim_ids", [])}
        render_context = [c for cid, c in claims.items() if cid in render_context_ids]
        renderer = Renderer()
        published_claims, published_artifacts, published_effects = set(), set(), set()
        delivered_purposes = {rid:set() for rid in active}
        failed_open = {rid:[] for rid in active}
        for node in nodes:
            pid,kind,rids = node["part_id"],node["kind"],node["requirement_ids"]
            value, disposition, reason = None, "accepted", ""
            if "error" in node:
                disposition,reason = "rejected",node["error"]
            elif kind == "claim":
                renderer.add_claim(claims[node["ref"]], context=render_context, part_id=pid, ref=node["ref"], requirement_ids=rids)
                published_claims.add(node["ref"])
                continue
            elif kind == "effect":
                if node["ref"] not in published_effects:
                    value=effect_text(effects[node["ref"]]);published_effects.add(node["ref"])
                else:disposition="duplicate_reference"
            elif kind == "artifact":
                if node["ref"] not in published_artifacts:
                    value = artifact_text(artifacts[node["ref"]])
                    published_artifacts.add(node["ref"])
                else:
                    disposition = "duplicate_reference"
            else:
                decision = decisions[pid]
                if decision["disposition"] == "accept":
                    value = node["text"]
                    for rid in rids:
                        # Gap guidance explains a missing delivery; it does not
                        # supply the missing result or promote its host status.
                        if not (active[rid]["gap"] is not None and node["purpose"] in {"limitation", "conditional_action"}
                                and node["purpose"] not in active[rid]["open_purposes"]):
                            delivered_purposes[rid].add(node["purpose"])
                        if pure_consultation and active[rid]["open_purposes"] == ["knowledge"]:
                            delivered_purposes[rid].add("knowledge")
                else:
                    disposition,reason = decision["disposition"],decision["reason"]
                    for rid in rids:
                        failed_open[rid].append(reason)
            text_identity = ({"purpose": node["purpose"], "claim_refs": node["claim_refs"],
                              "semantic_reviewed": bool(requires_review and disposition == "accepted"
                                  and decisions.get(pid, {}).get("disposition") == "accept")} if kind == "text" else {})
            renderer.add(value,part_id=pid,kind=kind,ref=node.get("ref"),requirement_ids=rids,
                         disposition=disposition,reason=reason,**text_identity)
        # Host facts remain deliverable even when the model omits or corrupts
        # its draft. A withdrawn-only binding is not revived by this recovery.
        withdrawn_only = set().union(*(set(r["claim_ids"]) for r in requirements.values() if r["withdrawn"])) - set().union(*(set(r["claim_ids"]) for r in active.values()))
        for cid,claim in claims.items():
            rids = [rid for rid,r in active.items() if cid in r["claim_ids"]]
            if rids and cid not in published_claims and cid not in withdrawn_only:
                renderer.add_claim(claim, context=render_context, part_id="host:"+cid, ref=cid, requirement_ids=rids)
                published_claims.add(cid)
        for aid,artifact in artifacts.items():
            rids = [rid for rid,r in active.items() if aid in r["artifact_ids"]]
            if rids and aid not in published_artifacts:
                renderer.add(artifact_text(artifact),part_id="host:"+aid,kind="artifact",ref=aid,requirement_ids=rids)
                published_artifacts.add(aid)
        for eid,effect in effects.items():
            rids=[rid for rid,r in active.items() if eid in r.get("effect_ids",[])]
            if rids and eid not in published_effects:
                renderer.add(effect_text(effect),part_id="host:"+eid,kind="effect",ref=eid,requirement_ids=rids);published_effects.add(eid)
        outcomes = []
        for rid,req in requirements.items():
            status,reason = "withdrawn","用户已撤回。"
            if req["withdrawn"] and not active:
                renderer.add(req["text"]+"：用户已撤回。",part_id="withdrawn:"+rid,kind="withdrawn",ref=rid,requirement_ids=[rid])
            if not req["withdrawn"]:
                missing_claims = set(req["claim_ids"])-published_claims
                missing_artifacts = set(req["artifact_ids"])-published_artifacts
                missing_effects=set(req.get("effect_ids",[]))-published_effects
                missing_purposes = set(req["open_purposes"])-delivered_purposes[rid]
                fulfilled = (any(claims[cid]["value"] is not None for cid in set(req["claim_ids"]) & published_claims)
                             or bool(set(req["artifact_ids"]) & published_artifacts) or bool(set(req.get("effect_ids",[])) & published_effects) or bool(delivered_purposes[rid]))
                gap = req["gap"]
                complete = not (gap or missing_claims or missing_artifacts or missing_effects or missing_purposes or failed_open[rid])
                if complete:
                    status,reason = "answered",""
                else:
                    reasons = [gap["reason"]] if gap else []
                    if failed_open[rid] and not missing_purposes:
                        reasons.extend(failed_open[rid])
                    if missing_claims: reasons.append("缺少当前可核结果："+", ".join(sorted(missing_claims))+"。")
                    if missing_effects:reasons.append("缺少当前已核操作效果。")
                    if missing_artifacts: reasons.append("缺少当前可用产物："+", ".join(sorted(missing_artifacts))+"。")
                    if missing_purposes:
                        reasons.append("未交付所需开放内容："+", ".join(sorted(missing_purposes))+"。")
                        reasons.extend(failed_open[rid] or ([issues[0]["reason"]] if issues else ["草案未提供对应片段。 "]))
                    status = "partial" if fulfilled else gap["status"] if gap else "not_computed" if missing_claims else "failed"
                    reason = " ".join(dict.fromkeys(reasons))
                    renderer.add(req["text"]+"："+STATUS_LABELS[status]+"；"+reason,
                                 part_id="gap:"+rid,kind="gap",ref=rid,requirement_ids=[rid])
            outcomes.append({"requirement_id":rid,"source_turn":req["source_turn"],"status":status,"reason":reason})
        payload = {"schema":SCHEMA,"session_id":host["session_id"],"turn_id":host["turn_id"],
                   "snapshot_digest":self.snapshot.digest,"draft_digest":raw_digest,"source_snapshot":host,
                   "body":renderer.body,"content_sha256":digest(renderer.body),"render_trace":renderer.trace,
                   "requirement_outcomes":outcomes,"audit_status":audit_status,"issues":issues,
                   "artifact_refs":[artifacts[aid] for aid in sorted(published_artifacts)]}
        answer = AcceptedAnswer.create(payload)
        self._answer_cache = (raw_digest,answer)
        return answer
