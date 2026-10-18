"""Load a session result only when its immutable receipt still matches."""
import hashlib
import json


def load_result_reference(reference, *, expected_receipt_id=None):
    from data_agent.tools.file_ops import _safe_path
    from data_agent.tools._utils import sanitize_filename
    from data_agent.agent.context import get_current_context

    path = _safe_path(reference)
    context = get_current_context()
    state = getattr(context, "analysis_state", None)
    if state is None or path.parent.name != "tool_outputs":
        raise ValueError("Expected a current-session tool output with a successful receipt")
    payload = json.loads(path.read_text(encoding="utf-8"))
    digest = "sha256:" + hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()
    normalised_reference = str(reference).replace("\\", "/")
    def matches_receipt_path(receipt):
        receipt_reference = str(
            (receipt.get("detail_ref") or {}).get("path") or ""
        ).replace("\\", "/")
        if receipt_reference:
            return normalised_reference == receipt_reference
        return False

    matches = [
        receipt
        for receipt in state.tool_receipts
        if receipt.get("structured_result_sha256") == digest
        and matches_receipt_path(receipt)
    ]
    if not matches:
        raise ValueError("Result file does not match its successful tool receipt")
    if expected_receipt_id is not None:
        matches = [
            receipt for receipt in matches
            if str(receipt.get("id") or "") == str(expected_receipt_id)
        ]
        if not matches:
            raise ValueError("Result file does not match the selected successful tool receipt")
    receipt = matches[-1]
    identities = receipt.get("data_identities", {})
    for name, identity in identities.items():
        # Comparing an existing host receipt does not expose raw data. A
        # narrower task or synthesis scope must not turn unchanged storage
        # into a false stale-version finding.
        if not context.workspace._receipt_identity_matches(name, identity):
            raise ValueError("Result belongs to an earlier data version; choose the matching result/version")
    catalog=receipt.get("catalog_binding")
    if receipt.get("tool_name")=="list_data":
        from data_agent.agent.publication.contracts import encode
        if not isinstance(catalog,dict) or catalog.get("scope_fingerprint")!=receipt.get("scope_fingerprint"):
            raise ValueError("目录缺少执行前授权范围绑定")
        actual=context.workspace._publication_catalog_result(catalog)
        if actual["binding"]!=catalog or actual["data_identities"]!=identities or encode(actual["result"])!=encode(payload):
            raise ValueError("目录快照或当前授权可见对象已变化")
    elif catalog is not None:
        raise ValueError("Only list_data can bind directory metadata")
    file_binding=receipt.get("file_binding")
    if receipt.get("tool_name") in {"read_file","list_files"}:
        from data_agent.tools.file_ops import _verify_file_binding
        _verify_file_binding(context,receipt,payload)
    elif file_binding is not None:raise ValueError("Only file excerpt/catalogue tools can bind file ranges")
    skills_binding=receipt.get("skills_binding")
    if receipt.get("tool_name")=="list_skills":
        from data_agent.tools.skill_tools import _verify_skills_binding
        _verify_skills_binding(context,receipt,payload)
    elif skills_binding is not None:raise ValueError("Only list_skills can bind Skills catalogue metadata")
    mcp_binding=receipt.get("mcp_binding")
    if receipt.get("tool_name")=="list_mcp_servers":
        from data_agent.tools.mcp_tools import _verify_mcp_catalog_binding
        _verify_mcp_catalog_binding(context,receipt,payload)
    elif mcp_binding is not None:raise ValueError("Only list_mcp_servers can bind MCP catalogue metadata")
    return payload, {**({"mcp_binding":mcp_binding} if mcp_binding is not None else {}),**({"skills_binding":skills_binding} if skills_binding is not None else {}),**({"file_binding":file_binding} if file_binding is not None else {}),**({"catalog_binding":catalog} if catalog is not None else {}),"receipt_id": receipt["id"], "result_ref": reference,
                     "result_sha256": digest, "data_identities": identities}

def load_chart_result_reference(reference, *, dataset=""):
    """Resolve one actual chart source; data is only an identity assertion."""
    payload, binding = load_result_reference(reference)
    identities = binding.get("data_identities", {})
    if len(identities) != 1:
        raise ValueError("Chart result_ref requires exactly one receipt dataset source")
    name = next(iter(identities))
    if dataset and dataset != name:
        raise ValueError(f"Explicit chart data '{dataset}' does not match result_ref source '{name}'")
    if not isinstance(payload, dict) or not isinstance(payload.get("chart_data"), list):
        raise ValueError("Result has no chart_data array")
    return payload, binding, name

