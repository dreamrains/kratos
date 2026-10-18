"""Workbench projection of exact accepted answers and explicit gaps."""
from data_agent.agent.publication.runtime import read_answer
from data_agent.agent.publication.renderer import claim_text, STATUS_LABELS


def _basis_text(claim):
    """Project the original accepted result without exposing its JSON payload."""
    value = claim["value"]
    if value is None or isinstance(value, (int, float, bool)) or claim.get("unit") == "hypothesis_status":
        return claim_text(claim)
    dataset = claim["scope"]["dataset"]
    return claim["label"] + ("（来源：" + dataset + "；完整结果见原回答）" if dataset else "（完整结果见原回答）")


def _reviewed_guidance(answer, requirement, current_claim_ids, sources_current):
    """Read typed, reviewed original spans; never infer actions from prose."""
    result = []
    if not sources_current:
        return result
    for trace in answer["render_trace"]:
        value = trace.get("rendered_text")
        start, end = trace.get("start"), trace.get("end")
        refs = trace.get("claim_refs")
        if (trace.get("kind") != "text" or trace.get("disposition") != "accepted"
                or trace.get("semantic_reviewed") is not True
                or trace.get("purpose") not in {"limitation", "conditional_action"}
                or requirement["id"] not in trace.get("requirement_ids", [])
                or not isinstance(value, str) or not value
                or type(start) is not int or type(end) is not int or not 0 <= start < end <= len(answer["body"])
                or answer["body"][start:end] != value
                or not isinstance(refs, list) or not set(refs).issubset(current_claim_ids)):
            continue
        result.append({"answer_id": answer["answer_id"], "snapshot_digest": answer["snapshot_digest"],
                       "requirement_id": requirement["id"], "source_turn": requirement["source_turn"],
                       "part_id": trace["part_id"], "purpose": trace["purpose"], "claim_refs": refs,
                       "start": start, "end": end, "text": value})
    return result


def build_workbench_view(state):
    conclusions, pending, seen, bases = [], [], set(), {}
    if state is None:
        return {"verified_conclusions": [], "verified_total": 0, "pending_findings": []}
    from data_agent.session.workspace import workspace,persisted_receipt_identity_matches
    from data_agent.agent.publication.facts import artifact_identity_matches
    from data_agent.agent.context import get_current_context
    ctx=get_current_context()
    receipts, original_bytes = {}, {}
    for receipt in state.tool_receipts:
        receipts.setdefault(receipt.get("id"), []).append(receipt)
    def original_receipt_matches(proof):
        matches = receipts.get(proof.get("receipt_id"), [])
        if len(matches) != 1:
            return False
        receipt = matches[0]
        if (receipt.get("tool_name") != proof.get("tool_name")
                or receipt.get("structured_result_sha256") != proof.get("result_sha256")
                or receipt.get("data_identities") != proof.get("data_identities")):
            return False
        rid = receipt["id"]
        if rid not in original_bytes:
            detail = receipt.get("detail_ref") or {}
            # Reuse the bounded, own-session original-byte authority. This
            # checks integrity only; no raw data read or new analysis grant.
            original_bytes[rid] = artifact_identity_matches(state.session_id,
                {"session_id": state.session_id, "path": detail.get("path", ""),
                 "sha256": detail.get("sha256", "")})
        return original_bytes[rid]
    def identities_current(identities):
        return all(workspace._receipt_identity_matches(n, i) if ctx is not None and ctx.session_id == state.session_id
                   else persisted_receipt_identity_matches(state.session_id, n, i) for n, i in identities.items())
    for reference in reversed(state.accepted_answers):
        try:
            answer = read_answer(state.session_id, reference)
            host = answer["source_snapshot"]
            accepted = {t["ref"]: t["rendered_text"] for t in answer["render_trace"] if t["kind"] == "claim" and t["disposition"] == "accepted"}
            for claim in host["claims"]:
                if claim["id"] in seen or claim["id"] not in accepted:
                    continue
                seen.add(claim["id"])
                sources = {n:i for proof in claim["basis_refs"] for n,i in proof["data_identities"].items()}
                current = identities_current(sources)
                current = current and all(original_receipt_matches(p) for p in claim["basis_refs"])
                source=claim.get("derivation",{}).get("source_artifact")
                if source: current=current and artifact_identity_matches(state.session_id,source)
                if not current:
                    pending.append({"id": claim["id"], "claim": claim["label"], "status": "stale", "status_label": "失效历史结果（当前源身份无法核实）", "basis": "历史已接受结果：" + _basis_text(claim), "gap": "数据版本、原回执或原假设产物身份已变化/无法核实", "next_step": "在当前数据范围重新计算"})
                    continue
                bases[claim["id"]] = _basis_text(claim)
                conclusions.append({"id": claim["id"], "claim": claim["label"], "summary": accepted[claim["id"]], "confidence": "host_verified", "dataset": claim["scope"]["dataset"], "answer_id": reference["answer_id"]})
            for outcome in answer["requirement_outcomes"]:
                rid = outcome["requirement_id"]
                if rid in seen:
                    continue
                seen.add(rid)
                if outcome["status"] not in {"answered", "withdrawn"}:
                    req = next(r for r in host["requirements"] if r["id"] == rid)
                    context_ids = set(req["claim_ids"] + req.get("context_claim_ids", []))
                    scoped_sources = {n: i for c in host["claims"] if c["id"] in context_ids
                                      for proof in c["basis_refs"] for n, i in proof["data_identities"].items()}
                    guidance = _reviewed_guidance(answer, req, set(accepted) & set(bases),
                        identities_current(scoped_sources or host["data_identities"]))
                    # Only this requirement's accepted deliveries and explicitly
                    # cited, reviewed evidence belong in its visible basis.
                    basis_ids = list(dict.fromkeys(req.get("claim_ids", []) + [cid for g in guidance for cid in g["claim_refs"]]))
                    basis = "；".join(bases[cid] for cid in basis_ids if cid in accepted and cid in bases)
                    if not basis:
                        basis = "该需求尚无已核且已接受的结果；具体证据缺口见下方。"
                    explanations = [g["text"] for g in guidance if g["purpose"] == "limitation"]
                    actions = [g["text"] for g in guidance if g["purpose"] == "conditional_action"]
                    pending.append({"id": rid, "claim": req["text"], "status": outcome["status"],
                        "status_label": STATUS_LABELS.get(outcome["status"],outcome["status"]), "basis": basis,
                        "gap": outcome["reason"], "gap_explanation": "\n".join(explanations),
                        "next_step": "\n".join(actions) if actions else "该原接受答案没有可核的同需求已审条件性建议。",
                        "next_step_status": "reviewed" if actions else "unassessed", "guidance_refs": guidance})
        except (ValueError, OSError, KeyError, TypeError):
            pending.append({"id": reference.get("answer_id", ""), "claim": "接受答案来源不可核实", "status": "unassessed", "status_label": "未核实", "basis": "", "gap": "原答案身份或产物不完整", "next_step": "保留历史正文，重新计算当前需求"})
    return {"verified_conclusions": conclusions, "verified_total": len(conclusions), "pending_findings": pending}
