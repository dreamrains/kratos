"""Strict model draft and immutable host-owned publication snapshot."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any
from pathlib import PurePosixPath

from data_agent.session.artifact_paths import ARTIFACT_DIRS

SCHEMA = "answer_bindings.v2"
PURPOSES = frozenset({"knowledge", "interpretation", "limitation", "conditional_action"})
GAP_STATUSES = frozenset({"not_computed", "evidence_insufficient", "needs_confirmation", "failed"})
MAX_DRAFT_BYTES = 128_000


class ContractError(ValueError):
    def __init__(self, code: str, reason: str):
        super().__init__(reason)
        self.code = code


def encode(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    try:
        encoded.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ContractError("invalid_unicode", "协议包含无效 Unicode 文本。") from exc
    return encoded


def digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _pairs(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ContractError("duplicate_json_key", "协议包含重复字段。")
        obj[key] = value
    return obj


def strict_loads(raw: str, *, max_bytes: int = MAX_DRAFT_BYTES):
    if not isinstance(raw, str):
        raise ContractError("protocol_size", "协议必须为文本。")
    try:
        size = len(raw.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise ContractError("invalid_unicode", "协议包含无效 Unicode 文本。") from exc
    if size > max_bytes:
        raise ContractError("protocol_size", "协议不是文本或超过大小上限。")
    try:
        return json.loads(raw, object_pairs_hook=_pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")))
    except (ValueError, RecursionError) as exc:
        if isinstance(exc, ContractError):
            raise
        raise ContractError("invalid_json", "无法解析结构化终局协议。") from exc


def fields(obj, required, optional=()):
    if not isinstance(obj, dict) or not set(required).issubset(obj) or set(obj) - set(required) - set(optional):
        raise ContractError("invalid_fields", "协议字段缺失或包含未经允许的字段。")


def text(value, *, limit=12_000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ContractError("invalid_text", "协议文本缺失或超过大小上限。")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ContractError("invalid_unicode", "协议包含无效 Unicode 文本。") from exc
    return value


def refs(value, *, limit=128):
    if not isinstance(value, list) or len(value) > limit:
        raise ContractError("invalid_refs", "引用必须是有界列表。")
    result = [text(item, limit=128) for item in value]
    if len(result) != len(set(result)):
        raise ContractError("duplicate_refs", "同一引用列表包含重复身份。")
    return result


def _unique(items):
    if not isinstance(items, list):
        raise ContractError("invalid_manifest", "宿主清单必须是列表。")
    ids = [text(item.get("id"), limit=128) for item in items if isinstance(item, dict)]
    if len(ids) != len(items) or len(ids) != len(set(ids)):
        raise ContractError("ambiguous_manifest", "宿主清单身份缺失或重复。")


@dataclass(frozen=True)
class HostSnapshot:
    _encoded: str

    @classmethod
    def freeze(cls, *, session_id, turn_id, history_revision, requirement_revision,
               mode, requirements, claims, artifacts, data_identities, plan_id="",
               uses_result_context=False, confirmation_refs=(), effects=None):
        if effects is None:effects=[]
        text(session_id, limit=128)
        text(turn_id, limit=128)
        if mode not in {"consultation", "analysis", "result_followup"}:
            raise ContractError("invalid_mode", "未知宿主路由。")
        if any(type(n) is not int or n < 0 for n in (history_revision, requirement_revision)):
            raise ContractError("invalid_revision", "宿主 revision 必须为非负整数。")
        if type(uses_result_context) is not bool or not isinstance(data_identities, dict):
            raise ContractError("invalid_context", "宿主结果上下文或数据身份无效。")
        for items, limit in ((requirements,128),(claims,2048),(artifacts,128),(effects,128)):
            _unique(items)
            if len(items) > limit:
                raise ContractError("manifest_size", "宿主清单超过上限。")
        for req in requirements:
            fields(req, {"id","text","source_turn","claim_ids","open_purposes","artifact_ids","gap","withdrawn"}, {"context_claim_ids","effect_ids"})
            if "effect_ids" in req:
                refs(req["effect_ids"])
                if not set(req["effect_ids"]).issubset({e["id"] for e in effects}):raise ContractError("effect_ref","操作效果引用不属于当前宿主清单。")
            if "context_claim_ids" in req:
                refs(req["context_claim_ids"],limit=2048)
                if not set(req["context_claim_ids"]).issubset({c["id"] for c in claims}):
                    raise ContractError("context_claim_ref", "解释证据不属于当前宿主事实清单。")
            text(req["text"])
            text(req["source_turn"], limit=128)
            for key in ("claim_ids","open_purposes","artifact_ids"):
                refs(req[key],limit=2048 if key=="claim_ids" else 128)
            if not set(req["open_purposes"]).issubset(PURPOSES) or type(req["withdrawn"]) is not bool:
                raise ContractError("invalid_requirement", "需求类型或生命周期无效。")
            if req["gap"] is not None:
                fields(req["gap"], {"status","reason"})
                if req["gap"]["status"] not in GAP_STATUSES:
                    raise ContractError("invalid_gap", "未知缺口状态。")
                text(req["gap"]["reason"])
            if not req["withdrawn"] and not (req["claim_ids"] or req["open_purposes"] or req["artifact_ids"] or req.get("effect_ids") or req["gap"]):
                raise ContractError("unbound_requirement", "需求必须有具体交付绑定或缺口。")
        proofs = {}
        for claim in claims:
            fields(claim, {"id","label","value","unit","scope","limitations","basis_refs"}, {"derivation","target"})
            if "target" in claim:
                fields(claim["target"], {"dataset","tool","parameters"}, {"metric","statistic","hypothesis_id","deliverable","source_message_ref","completion_gap","business_product","curve_display","source_unit_proof","source_unit_proofs","source_unit_gaps"})
                from .source_units import validate_source_unit_target
                validate_source_unit_target(claim)
                if claim["target"]["dataset"] != claim["scope"]["dataset"] or not isinstance(claim["target"]["parameters"],dict):
                    raise ContractError("invalid_target", "原生事实目标与范围不一致。")
                if "business_product" in claim["target"]:
                    product=claim["target"]["business_product"]
                    if product.get("kind") is None: fields(product,{"kind"})
                    else:
                        from data_agent.agent.analysis_plan_contracts import DELIVERY_KINDS
                        from .deliveries import validate_business_scope
                        fields(product,{"kind","metrics","quantity","parameters"})
                        if product["kind"] not in DELIVERY_KINDS: raise ContractError("invalid_product","Unknown product type.")
                        validate_business_scope({k:v for k,v in product.items() if k in {"quantity","parameters"} or k=="metrics" and v})
                text(claim["target"]["tool"],limit=128)
                for key in ("metric","statistic","hypothesis_id","source_message_ref"):
                    if key in claim["target"]: text(claim["target"][key],limit=128)
                if "completion_gap" in claim["target"]:
                    gap=claim["target"]["completion_gap"]
                    fields(gap,{"status","reason"})
                    if gap["status"] not in GAP_STATUSES: raise ContractError("invalid_gap","未知交付缺口。")
                    text(gap["reason"])
                if "deliverable" in claim["target"] and type(claim["target"]["deliverable"]) is not bool:
                    raise ContractError("invalid_target", "交付标识必须为布尔值。")
                if "curve_display" in claim["target"]:
                    display=claim["target"]["curve_display"]
                    fields(display,{"value_scale","basis","source_unit_verified"})
                    if (claim["target"]["tool"]!="curve_fitting" or display["value_scale"] not in {"fraction","percentage_points"}
                            or display["basis"]!="plan_declaration" or type(display["source_unit_verified"]) is not bool
                            or claim["target"].get("business_product",{}).get("parameters",{}).get("curve_value_scale")!=display["value_scale"]):
                        raise ContractError("curve_display", "声明呈现必须来自同一原曲线交付，不授予源单位事实。")
            if "derivation" in claim:
                derivation = claim["derivation"]
                if not isinstance(derivation, dict):
                    raise ContractError("invalid_derivation", "派生来源必须为对象。")
                if derivation.get("operator") == "inclusive_calendar_days":
                    fields(derivation, {"operator","operand_paths"})
                    if not isinstance(derivation["operand_paths"], list) or len(derivation["operand_paths"]) != 2:
                        raise ContractError("invalid_derivation", "含首尾日期需要两个原端点。")
                elif derivation.get("operator") == "confirmed_sum_difference":
                    fields(derivation,{"operator","confirmation_id","response_id","formula","operand_paths"})
                    if not any(ref["confirmation_id"]==derivation["confirmation_id"] and ref["response_id"]==derivation["response_id"] and ref["response"]==encode(derivation["formula"]) for ref in confirmation_refs):
                        raise ContractError("invalid_derivation","账面公式没有当前原用户确认身份。")
                    if not isinstance(derivation["operand_paths"],list) or not derivation["operand_paths"]:
                        raise ContractError("invalid_derivation","账面公式没有原聚合输入。")
                elif derivation.get("operator") == "confirmed_business_sum":
                    fields(derivation,{"operator","confirmation_id","response_id","column","operand_paths"})
                    text(derivation["column"],limit=128)
                    if not any(ref["confirmation_id"]==derivation["confirmation_id"] and ref["response_id"]==derivation["response_id"] and ref["response"]=="raw" for ref in confirmation_refs):
                        raise ContractError("invalid_derivation","业务名称没有当前原用户确认。")
                    if not derivation["operand_paths"] or derivation["operand_paths"] != [p["result_path"] for p in claim["basis_refs"]] or claim["unit"] is not None:
                        raise ContractError("invalid_derivation","业务名称缺少完整原聚合输入或擅自授予单位。")
                elif derivation.get("operator") == "hypothesis_relation":
                    fields(derivation, {"operator","hypothesis_id","plan_id","evidence_ids","predicate","source_artifact"})
                    source=derivation["source_artifact"]
                    fields(source,{"id","session_id","path","type","description","sha256"})
                    if source["session_id"]!=session_id or source["type"]!="hypothesis_set":
                        raise ContractError("invalid_derivation","假设原产物没有同会话身份。")
                    for key in ("id","path","description","sha256"): text(source[key])
                    if derivation["plan_id"] != plan_id or not refs(derivation["evidence_ids"]):
                        raise ContractError("invalid_derivation", "假设派生没有当前计划及证据身份。")
                else:
                    raise ContractError("invalid_derivation", "未知派生运算。")
            text(claim["label"])
            if claim["unit"] is not None:
                text(claim["unit"],limit=128)
            refs(claim["limitations"])
            fields(claim["scope"], {"dataset","population","time_scope","grain"})
            target=claim.get("target",{})
            product=target.get("business_product",{})
            catalog=target.get("tool")=="list_data" and product.get("kind")=="table" and product.get("parameters",{}).get("catalog_scope")=="current_visible"
            file=target.get("tool") in {"read_file","list_files"} and product.get("kind")=="table" and product.get("parameters",{}).get("file_scope")=="current_readable"
            skills=target.get("tool")=="list_skills" and product.get("kind")=="table" and product.get("parameters",{})=={"catalog_scope":"current_visible","catalog_output":"skills"}
            mcp=target.get("tool")=="list_mcp_servers" and product.get("kind")=="table" and product.get("parameters",{}) in ({"catalog_scope":"current_visible","catalog_output":"mcp_servers"},{"catalog_scope":"current_visible","catalog_output":"mcp_health"})
            dataset = claim["scope"]["dataset"] if catalog or file or skills or mcp else text(claim["scope"]["dataset"],limit=128)
            if (catalog or file or skills or mcp) and (dataset is not None or claim.get("derivation") or claim["unit"] is not None):
                raise ContractError("catalog_scope","目录元数据不能冒充数据测量。")
            if not isinstance(claim["basis_refs"],list) or not claim["basis_refs"]:
                raise ContractError("missing_basis", "数据事实没有成功回执来源。")
            for proof in claim["basis_refs"]:
                fields(proof, {"receipt_id","session_id","tool_name","result_sha256","data_identities","result_path"}, {"catalog_binding"} if catalog else {"file_binding"} if file else {"skills_binding"} if skills else {"mcp_binding"} if mcp else set())
                if catalog:
                    validate_catalog_binding(proof.get("catalog_binding"),session_id)
                    if proof["tool_name"]!="list_data" or proof["result_path"] not in (["datasets"],["transform_history"]) or product["parameters"].get("catalog_output")!=proof["result_path"][0]:
                        raise ContractError("catalog_scope","目录元数据必须引用对应的原目录字段。")
                if file:
                    validate_file_binding(proof.get("file_binding"),session_id)
                    expected_key="content" if target["tool"]=="read_file" else "entries"
                    if proof["tool_name"]!=target["tool"] or proof["result_path"]!=[expected_key] or product["parameters"]!=proof["file_binding"]["parameters"] or proof["data_identities"]:
                        raise ContractError("file_scope","文件原文/目录不能冒充数据测量或改变实际读取范围。")
                if skills:
                    validate_skills_binding(proof.get("skills_binding"),session_id)
                    if proof["tool_name"]!="list_skills" or proof["result_path"]!=["skills"] or proof["data_identities"]:
                        raise ContractError("skills_scope","Skills目录不能冒充数据测量或其他结果。")
                if mcp:
                    validate_mcp_catalog_binding(proof.get("mcp_binding"),session_id)
                    expected_key="servers" if product["parameters"]["catalog_output"]=="mcp_servers" else "health"
                    if proof["tool_name"]!="list_mcp_servers" or proof["result_path"]!=[expected_key] or proof["data_identities"]:
                        raise ContractError("mcp_scope","MCP目录不能冒充数据测量或其他结果。")
                rid = text(proof["receipt_id"],limit=128)
                sha = proof["result_sha256"]
                if not isinstance(sha,str) or not sha.startswith("sha256:") or len(sha)!=71 or any(c not in "0123456789abcdef" for c in sha[7:]):
                    raise ContractError("invalid_basis_digest", "原结果摘要无效。")
                identities = proof["data_identities"]
                if proof["session_id"] != session_id or not isinstance(identities,dict) or not (catalog or file or skills or mcp) and dataset not in identities:
                    raise ContractError("basis_scope", "事实不属于当前会话或数据范围。")
                if any(not isinstance(v,dict) or not v.get("version_id") or not v.get("fingerprint") or data_identities.get(k)!=v
                       for k,v in identities.items()):
                    raise ContractError("stale_basis", "事实来源缺少精确当前数据身份。")
                signature = encode({key:value for key,value in proof.items() if key != "result_path"})
                if rid in proofs and proofs[rid] != signature:
                    raise ContractError("ambiguous_basis", "同一回执绑定了不同的原结果。")
                proofs[rid] = signature
        for effect in effects:
            fields(effect,{"id","session_id","action","arguments","object","before","permission_scope","receipt_id","result_sha256","data_identities"},{"details","completion_gap"})
            if "details" in effect and not isinstance(effect["details"],dict):raise ContractError("effect_details","操作详情必须为对象。")
            if "completion_gap" in effect:
                gap=effect["completion_gap"];fields(gap,{"status","reason"})
                if gap["status"] not in GAP_STATUSES:raise ContractError("effect_gap","操作缺口状态未知。")
                text(gap["reason"])
            from .native import OPERATION_TOOLS
            if effect["session_id"]!=session_id or effect["action"] not in OPERATION_TOOLS or not effect["receipt_id"] or effect["before"].get("session_id")!=session_id:
                raise ContractError("effect_scope","操作效果不属于当前会话和已知操作。")
            if any(data_identities.get(n)!=i for n,i in effect["data_identities"].items()):raise ContractError("effect_identity","操作对象来源身份变化。")
            if effect["object"].get("kind") not in {"dataset","file","skill","memory"} or not effect["object"].get("name") or not isinstance(effect["arguments"],dict):raise ContractError("effect_object","操作对象结构无效。")
            if effect["object"]["kind"]=="memory":
                identity=effect["object"].get("identity",{});fields(identity,{"sha256","status"})
                text(identity["sha256"])
                if identity["status"] not in {"candidate","confirmed"}:raise ContractError("effect_memory","记忆效果状态不支持。")
            text(effect["permission_scope"]);text(effect["result_sha256"])
        for artifact in artifacts:
            fields(artifact,{"id","session_id","path","type","description","sha256"},{"target"})
            if "target" in artifact:
                fields(artifact["target"], {"dataset","tool","parameters"}, {"data_identities","receipt_id","completion_gap","chart_binding"})
                if artifact["target"].get("completion_gap"):
                    gap=artifact["target"]["completion_gap"];fields(gap,{"status","reason"})
                    if gap["status"] not in GAP_STATUSES:raise ContractError("invalid_gap","未知图表范围缺口。")
                    text(gap["reason"])
                if "chart_binding" in artifact["target"]:
                    proof=artifact["target"]["chart_binding"];fields(proof,{"metadata_ref","metadata_sha256","result_sha256"})
                    for value in proof.values():text(value)
                if not isinstance(artifact["target"]["parameters"], dict):
                    raise ContractError("artifact_target", "产物目标参数无效。")
            if artifact["session_id"] != session_id:
                raise ContractError("artifact_scope", "产物不属于当前会话。")
            path = text(artifact["path"]).replace("\\", "/")
            parts = PurePosixPath(path).parts
            if not parts or PurePosixPath(path).is_absolute() or ".." in parts or ":" in path or "\x00" in path:
                raise ContractError("artifact_path", "产物路径不是当前会话内的相对引用。")
            if parts[0] == "sessions":
                if len(parts) < 4 or parts[1] != session_id:
                    raise ContractError("artifact_scope", "产物路径不属于当前会话。")
                parts = parts[2:]
            if len(parts) < 2 or parts[0] not in ARTIFACT_DIRS:
                raise ContractError("artifact_path", "产物路径不是允许的会话产物。")
            text(artifact["type"], limit=128)
            text(artifact["description"])
            sha = artifact["sha256"]
            if not isinstance(sha, str) or not sha.startswith("sha256:") or len(sha) != 71 or any(c not in "0123456789abcdef" for c in sha[7:]):
                raise ContractError("artifact_digest", "产物字节摘要无效。")
        if not isinstance(confirmation_refs,(list,tuple)) or len(confirmation_refs)>128:
            raise ContractError("confirmation_refs", "确认引用超限。")
        for reference in confirmation_refs:
            fields(reference,{"confirmation_id","response_id","session_id","decision_key","data_version","spec_version","response","status","record_version"})
            if type(reference["record_version"]) is not int or reference["record_version"]<1:
                raise ContractError("confirmation_version","确认缺少原记录版本。")
            if reference["status"] not in {"resolved","skipped","cancelled"}:
                raise ContractError("confirmation_terminal", "确认引用必须是原终态。")
            if reference["session_id"]!=session_id or not reference["response_id"] or not isinstance(reference["data_version"],str):
                raise ContractError("confirmation_scope", "确认引用缺少当前身份。")
        payload = dict(session_id=session_id,turn_id=turn_id,history_revision=history_revision,
            requirement_revision=requirement_revision,mode=mode,requirements=requirements,claims=claims,
            artifacts=artifacts,effects=list(effects),data_identities=data_identities,plan_id=plan_id,uses_result_context=uses_result_context,confirmation_refs=list(confirmation_refs))
        encoded = encode(payload)
        if len(encoded.encode("utf-8")) > 2_000_000:
            raise ContractError("snapshot_size", "宿主快照超过大小上限。")
        return cls(encoded)

    @property
    def digest(self):
        return digest(self._encoded)

    def as_dict(self):
        return json.loads(self._encoded)


def parse_draft(raw, snapshot_digest):
    draft = strict_loads(raw)
    fields(draft,{"schema","snapshot_digest","sections"})
    if draft["schema"] != SCHEMA:
        raise ContractError("unsupported_schema", "只接受 answer_bindings.v2。")
    if draft["snapshot_digest"] != snapshot_digest:
        raise ContractError("stale_draft", "终局草案不是当前冻结快照。")
    sections = draft["sections"]
    if not isinstance(sections,list) or len(sections)>64:
        raise ContractError("invalid_sections", "终局 section 超过上限或格式无效。")
    total = sum(len(s.get("parts", [])) for s in sections if isinstance(s, dict) and isinstance(s.get("parts"), list))
    if total > 256:
        raise ContractError("parts_size", "终局节点超过上限。")
    issues = []
    for si,section in enumerate(sections):
        try:
            fields(section,{"requirement_ids","parts"})
            if not refs(section["requirement_ids"]):
                raise ContractError("unbound_section", "终局 section 没有需求来源。")
            if not isinstance(section["parts"],list):
                raise ContractError("invalid_parts", "终局 parts 必须为列表。")
        except ContractError as exc:
            issues.append({"code":exc.code,"reason":str(exc),"part_id":f"s{si}"})
            sections[si] = {"requirement_ids":[],"parts":[]}
            continue
        for pi,part in enumerate(section["parts"]):
            try:
                if not isinstance(part,dict):
                    raise ContractError("invalid_part", "终局节点必须为对象。")
                kind = part.get("kind")
                if not isinstance(kind, str):
                    raise ContractError("invalid_kind", "未知终局节点类型。")
                if kind in {"claim","artifact","effect"}:
                    fields(part,{"kind","ref"})
                    text(part["ref"],limit=128)
                elif kind == "text":
                    fields(part,{"kind","purpose","text"},{"claim_refs"})
                    if not isinstance(part["purpose"], str) or part["purpose"] not in PURPOSES:
                        raise ContractError("invalid_purpose", "未知开放片段用途。")
                    text(part["text"])
                    part["claim_refs"] = refs(part.get("claim_refs",[]))
                else:
                    raise ContractError("invalid_kind", "未知终局节点类型。")
            except ContractError as exc:
                # Keep original positions. Model input cannot create this internal node.
                section["parts"][pi] = {"kind":"invalid","code":exc.code,"reason":str(exc)}
    draft["issues"] = issues
    return draft



@dataclass(frozen=True)
class AcceptedAnswer:
    _encoded: str

    @classmethod
    def create(cls, payload):
        payload = dict(payload)
        payload["answer_id"] = "ans_" + digest(encode(payload))[7:]
        return cls(encode(payload))

    def as_dict(self):
        return json.loads(self._encoded)


def validate_catalog_binding(value, session_id):
    """Validate metadata authority without inventing a dataset identity."""
    from data_agent.agent.execution_scope import WorkspaceScopeSnapshot
    from dataclasses import fields as dataclass_fields
    fields(value,{"session_id","scope","scope_fingerprint","snapshot_sha256"})
    fields(value["scope"],{f.name for f in dataclass_fields(WorkspaceScopeSnapshot)})
    raw=value["scope"]
    if any(not isinstance(raw[k],list) or any(not isinstance(n,str) or not n for n in raw[k]) or sorted(set(raw[k]))!=raw[k] for k in ("allowed_datasets","dataset_contract_ids")):
        raise ContractError("catalog_scope","目录授权范围无效。")
    if type(raw["task_id"]) is not int or any(not isinstance(v,str) for k,v in raw.items() if k not in {"task_id","allowed_datasets","dataset_contract_ids"}):
        raise ContractError("catalog_scope","目录授权范围类型无效。")
    scope=WorkspaceScopeSnapshot(**raw)
    if value["session_id"]!=session_id or raw["session_id"]!=session_id or scope.phase not in {"legacy","execution"} or scope.fingerprint!=value["scope_fingerprint"]:
        raise ContractError("catalog_scope","目录会话或授权范围摘要不一致。")
    sha=value["snapshot_sha256"]
    if not isinstance(sha,str) or len(sha)!=71 or not sha.startswith("sha256:") or any(c not in "0123456789abcdef" for c in sha[7:]):
        raise ContractError("catalog_digest","目录快照摘要无效。")
    return scope


def validate_file_binding(value,session_id):
    """Only original text excerpts and enumerated file metadata can omit datasets."""
    from datetime import datetime
    fields(value,{"schema_version","session_id","tool","arguments","parameters","permission_scope","canonical_path","captured_at","snapshot_sha256"})
    if value["schema_version"]!="file_binding.v1" or value["session_id"]!=session_id or value["tool"] not in {"read_file","list_files"}:raise ContractError("file_scope","文件范围没有当前会话及原工具身份。")
    from data_agent.tools.file_ops import _file_arguments,_file_parameters
    args=_file_arguments(value["tool"],value["arguments"])
    if args!=value["arguments"]:raise ContractError("file_scope","文件调用缺少明确默认参数。")
    params=_file_parameters(value["tool"],args)
    if value["tool"]=="read_file":params["file_sha256"]=value["parameters"].get("file_sha256")
    if params!=value["parameters"]:raise ContractError("file_scope","文件交付范围与调用不一致。")
    from .deliveries import validate_business_scope
    validate_business_scope({"datasets":[],"parameters":params},required=True,metadata=True)
    permission=value["permission_scope"];fields(permission,{"session_id","project_root","sessions_root","artifact_dirs"})
    if permission["session_id"]!=session_id or not isinstance(permission["artifact_dirs"],list) or any(not isinstance(v,str) for v in permission["artifact_dirs"]):raise ContractError("file_scope","文件权限不属于当前会话。")
    for k in ("project_root","sessions_root"):text(permission[k],limit=4096)
    text(value["canonical_path"],limit=4096)
    try:datetime.fromisoformat(value["captured_at"])
    except (ValueError,TypeError):raise ContractError("file_scope","文件枚举时点无效。")
    sha=value["snapshot_sha256"]
    if not isinstance(sha,str) or len(sha)!=71 or not sha.startswith("sha256:") or any(c not in "0123456789abcdef" for c in sha[7:]):raise ContractError("file_scope","文件快照摘要无效。")
    return value


def validate_skills_binding(value,session_id):
    """Shape check for the existing receipt's system catalogue authority."""
    fields(value,{"schema_version","session_id","permission_scope","directories","files","snapshot_sha256"})
    if value["schema_version"]!="skills_catalog_binding.v1" or value["session_id"]!=session_id or value["permission_scope"]!="global_catalog_current_session_loading":
        raise ContractError("skills_scope","Skills目录没有当前会话及全局目录权限绑定。")
    if not isinstance(value["directories"],list) or not isinstance(value["files"],list):raise ContractError("skills_scope","Skills目录范围格式无效。")
    for row in value["directories"]:
        fields(row,{"path","exists"});text(row["path"],limit=4096)
        if type(row["exists"]) is not bool:raise ContractError("skills_scope","Skills目录存在状态无效。")
    for row in value["files"]:
        fields(row,{"path","sha256"});text(row["path"],limit=4096)
    for sha in [value["snapshot_sha256"],*[r["sha256"] for r in value["files"]]]:
        if not isinstance(sha,str) or not sha.startswith("sha256:") or len(sha)!=71 or any(c not in "0123456789abcdef" for c in sha[7:]):raise ContractError("skills_digest","Skills目录/文件摘要无效。")
    return value


def validate_mcp_catalog_binding(value,session_id):
    fields(value,{"schema_version","session_id","permission_scope","configuration","runtime","snapshot_sha256"})
    if value["schema_version"]!="mcp_catalog_binding.v1" or value["session_id"]!=session_id or value["permission_scope"]!="configured_global_mcp_catalog":
        raise ContractError("mcp_scope","MCP目录缺少当前会话及配置读取权限。")
    config=value["configuration"];fields(config,{"path","exists","sha256","configuration"});text(config["path"],limit=4096)
    if type(config["exists"]) is not bool or not isinstance(config["configuration"],dict):raise ContractError("mcp_scope","MCP配置来源格式无效。")
    if not config["exists"] and config["sha256"] is not None:raise ContractError("mcp_scope","不存在的配置文件不能有文件摘要。")
    runtime=value["runtime"];fields(runtime,{"process_id","manager_available","snapshot_sha256"})
    if type(runtime["process_id"]) is not int or runtime["process_id"]<=0 or type(runtime["manager_available"]) is not bool:raise ContractError("mcp_scope","MCP进程快照格式无效。")
    for sha in [value["snapshot_sha256"],runtime["snapshot_sha256"]]+([config["sha256"]] if config["exists"] else []):
        if not isinstance(sha,str) or not sha.startswith("sha256:") or len(sha)!=71 or any(c not in "0123456789abcdef" for c in sha[7:]):raise ContractError("mcp_digest","MCP目录/配置/进程快照摘要无效。")
    return value
