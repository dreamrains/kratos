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
        return path.name == sanitize_filename(receipt.get("tool_call_id", "")) + "_detail.json"

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
        if context.workspace.get_data_identity(name) != identity:
            raise ValueError("Result belongs to an earlier data version; choose the matching result/version")
    return payload, {"receipt_id": receipt["id"], "result_ref": reference,
                     "result_sha256": digest, "data_identities": identities}
