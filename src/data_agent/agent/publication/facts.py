"""Exact receipt-field binding using the existing session result authority.

A returned field proves what a tool returned; it does not prove causality,
statistical inference or an externally validated forecast. Native adapters
must supply those method contracts before application cutover.
"""
from copy import deepcopy
import hashlib

from data_agent.agent.context import get_current_context
from data_agent.config import get_config
from data_agent.tools.file_ops import _safe_path
from data_agent.tools.result_reference import load_result_reference

from .contracts import ContractError, encode, text

MAX_RESULT_BYTES = 8_000_000


def load_receipt_result(*, session_id, receipt_id, operation=False):
    context = get_current_context()
    state = getattr(context,"analysis_state",None)
    if context is None or context.session_id != session_id or state is None:
        raise ContractError("result_session", "结果没有当前会话执行上下文。")
    matches = [r for r in state.tool_receipts if isinstance(r,dict) and r.get("id")==receipt_id]
    if len(matches)!=1:
        raise ContractError("result_receipt", "必须定位唯一成功工具回执。")
    receipt = matches[0]
    detail = receipt.get("detail_ref")
    if not isinstance(detail,dict) or not detail.get("path") or not detail.get("sha256"):
        raise ContractError("result_detail", "回执缺少精确结果文件及内容摘要。")
    from .native import OPERATION_TOOLS
    nondata=operation and receipt.get("tool_name") in OPERATION_TOOLS and not receipt.get("data_identities") and not receipt.get("dataset_refs")
    nondata = nondata or receipt.get("tool_name")=="list_data" and isinstance(receipt.get("catalog_binding"),dict)
    nondata = nondata or receipt.get("tool_name") in {"read_file","list_files"} and isinstance(receipt.get("file_binding"),dict)
    nondata = nondata or receipt.get("tool_name")=="list_skills" and isinstance(receipt.get("skills_binding"),dict)
    nondata = nondata or receipt.get("tool_name")=="list_mcp_servers" and isinstance(receipt.get("mcp_binding"),dict)
    identities = receipt.get("data_identities")
    if not isinstance(identities,dict) or not identities and not nondata or any(
        not isinstance(v,dict) or not v.get("version_id") or not v.get("fingerprint") for v in identities.values()
    ):
        raise ContractError("result_identity", "结果缺少精确数据身份。")
    declared = receipt.get("dataset_refs")
    if not isinstance(declared,list) or not declared and not nondata or not set(declared).issubset(identities):
        raise ContractError("result_read_scope", "结果未绑定完整数据读取范围。")
    path = _safe_path(detail["path"])
    if path.parent.name != "tool_outputs" or path.stat().st_size > MAX_RESULT_BYTES:
        raise ContractError("result_size", "结果文件位置无效或超过读取上限。")
    byte_digest = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    if byte_digest != detail["sha256"]:
        raise ContractError("result_file_digest", "结果文件内容与回执摘要不一致。")
    payload,binding = load_result_reference(detail["path"],expected_receipt_id=receipt_id)
    if isinstance(payload,dict) and (payload.get("error_type") or isinstance(payload.get("error"),str) and payload["error"]):
        raise ContractError("failed_result", "失败工具结果不能形成已核事实。")
    return context, receipt, payload, binding


def resolve_result_claim(*, session_id, receipt_id, claim_id, label, result_path,
                         unit=None, scope=None, limitations=()):
    _,receipt,payload,binding = load_receipt_result(session_id=session_id,receipt_id=receipt_id)
    identities = binding["data_identities"]
    if not isinstance(result_path,(list,tuple)) or not result_path or len(result_path)>16:
        raise ContractError("result_field_path", "需要具体的有界结果字段路径。")
    value = payload
    for key in result_path:
        if isinstance(value,dict) and isinstance(key,str) and key in value:
            value = value[key]
        elif isinstance(value,list) and type(key) is int and 0<=key<len(value):
            value = value[key]
        else:
            raise ContractError("result_field", "指定结果字段不存在或类型不匹配。")
    # Reject NaN/Infinity and keep a detached, lossless JSON value.
    encode(value)
    scope = dict(scope or {})
    dataset = scope.get("dataset")
    if dataset is None and len(identities)==1:
        dataset = next(iter(identities))
    if dataset not in identities:
        raise ContractError("result_dataset", "结果字段必须绑定具体来源数据。")
    return {"id":text(claim_id,limit=128),"label":text(label),"value":deepcopy(value),"unit":unit,
            "scope":{"dataset":dataset,"population":scope.get("population", "当前工具读取范围"),
                     "time_scope":scope.get("time_scope", ""),"grain":scope.get("grain", "")},
            "limitations":list(limitations) or ["仅描述已执行工具输出，未授予因果或外部验证强度"],
            "basis_refs":[{"receipt_id":receipt_id,"session_id":session_id,"tool_name":receipt["tool_name"],
                           "result_sha256":binding["result_sha256"],"data_identities":deepcopy(identities),
                           "result_path":list(result_path)}]}


def resolve_artifact(*, session_id, artifact_id, path, kind, description, expected_sha256):
    """Verify a host-registered artifact, never a model-created path or digest."""
    context = get_current_context()
    if context is None or context.session_id != session_id:
        raise ContractError("artifact_session", "产物没有当前会话执行上下文。")
    reference = text(path).replace("\\", "/")
    resolved = _safe_path(reference)
    own = (get_config().sessions_resolved / session_id).resolve()
    if not resolved.is_relative_to(own) or not resolved.is_file():
        raise ContractError("artifact_scope", "产物不是当前会话中的真实文件。")
    if resolved.stat().st_size > MAX_RESULT_BYTES:
        raise ContractError("artifact_size", "产物超过本次有界读取上限。")
    actual = "sha256:" + hashlib.sha256(resolved.read_bytes()).hexdigest()
    if actual != expected_sha256:
        raise ContractError("artifact_digest", "产物文件与登记的字节摘要不一致。")
    return {"id":text(artifact_id,limit=128),"session_id":session_id,"path":reference,
            "type":text(kind,limit=128),"description":text(description),"sha256":actual}


def artifact_identity_matches(session_id,reference):
    """Boolean equality for an accepted source artifact, including after restart."""
    from pathlib import Path
    import hashlib
    own=(get_config().sessions_resolved/session_id).resolve()
    try:
        path=(own/reference["path"]).resolve()
        return (reference["session_id"]==session_id and path.is_relative_to(own) and path.is_file()
                and path.stat().st_size<=MAX_RESULT_BYTES
                and "sha256:"+hashlib.sha256(path.read_bytes()).hexdigest()==reference["sha256"])
    except (OSError,ValueError,KeyError,TypeError): return False
