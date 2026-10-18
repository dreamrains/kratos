"""One bounded semantic request; it cannot change the host manifest."""
from copy import deepcopy

from .contracts import ContractError, encode, fields, refs, strict_loads, text

AUDIT_SCHEMA = "publication_audit.v2"
MAX_AUDIT_BYTES = 64_000  # Response parser bound; request capacity is enforced by LLMClient.


def review_parts(request, auditor):
    fallback = {part["part_id"]:{"disposition":"unassessed","reason":"开放片段审核不可用。"}
                for part in request["parts"]}
    if auditor is None:
        return fallback, "unavailable"
    try:
        response = auditor(deepcopy(request))
        response = strict_loads(response,max_bytes=MAX_AUDIT_BYTES) if isinstance(response,str) else strict_loads(encode(response),max_bytes=MAX_AUDIT_BYTES)
        fields(response,{"schema","snapshot_digest","draft_digest","decisions"})
        if (response["schema"] != AUDIT_SCHEMA or response["snapshot_digest"] != request["snapshot_digest"]
                or response["draft_digest"] != request["draft_digest"]):
            raise ContractError("audit_identity", "审核快照或草案身份不一致。")
        parts = {part["part_id"]:part for part in request["parts"]}
        decisions = response["decisions"]
        if not isinstance(decisions,list) or len(decisions)>len(parts):
            raise ContractError("audit_decisions", "审核 decision 数量无效。")
        result, seen, invalid = dict(fallback), set(), set()
        malformed = False
        for row in decisions:
            pid = row.get("part_id") if isinstance(row,dict) else None
            if not isinstance(pid,str) or pid not in parts:
                malformed = True
                continue
            if pid in seen:
                invalid.add(pid)
                result[pid] = fallback[pid]
                continue
            seen.add(pid)
            try:
                fields(row,{"part_id","disposition","reason","evidence_refs"})
                part = parts[pid]
                evidence_refs = refs(row["evidence_refs"])
                if not set(evidence_refs).issubset(set(part["requirement_ids"]+part["claim_refs"])):
                    raise ContractError("audit_evidence", "审核引用了当前片段以外的证据。")
                if not isinstance(row["disposition"],str) or row["disposition"] not in {"accept","reject","unassessed"} or not evidence_refs:
                    raise ContractError("audit_disposition", "审核裁决缺少定位依据。")
                result[pid] = {"disposition":row["disposition"],"reason":text(row["reason"],limit=500)}
            except (ValueError,TypeError,KeyError):
                invalid.add(pid)
                result[pid] = fallback[pid]
        valid = seen-invalid
        return result, ("reviewed" if len(valid)==len(parts) and not malformed else "incomplete" if valid else "unavailable")
    except Exception as exc:
        # An ordinary transport/format failure cannot invalidate closed facts.
        reason = "开放片段审核失败：" + type(exc).__name__ + "。"
        return {pid:{"disposition":"unassessed","reason":reason} for pid in fallback}, "unavailable"
