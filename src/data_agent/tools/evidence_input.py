"""Model-visible input contract, also used before any receipt lookup."""

CONFIDENCE = ["high", "medium", "low", "speculative"]
TOOL_CALL_SCHEMA = {
    "anyOf": [
        {"type": "string", "minLength": 1},
        {"type": "object", "required": ["name"], "properties": {"name": {"type": "string", "minLength": 1}}},
        {"type": "object", "required": ["function"], "properties": {"function": {
            "type": "object", "required": ["name"], "properties": {"name": {"type": "string", "minLength": 1}},
        }}},
    ],
}
EVIDENCE_INPUT_SCHEMA = {
    "type": "object",
    "required": ["claim", "dataset", "method", "tool_calls", "result_summary", "limitations", "confidence"],
    "properties": {
        "claim": {"type": "string"}, "dataset": {"type": "string"}, "method": {"type": "string"},
        "tool_calls": {"type": "array", "items": TOOL_CALL_SCHEMA},
        "result_summary": {"type": "string"},
        "limitations": {"anyOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}]},
        "confidence": {"type": "string", "enum": CONFIDENCE},
    },
}


def validate_input(payload):
    from jsonschema import Draft7Validator
    errors = sorted(Draft7Validator(EVIDENCE_INPUT_SCHEMA).iter_errors(payload), key=lambda e: str(list(e.path)))
    if not errors:
        return None
    details = [{"path": "record_json" + "".join(f"[{p}]" if isinstance(p, int) else f".{p}" for p in e.path),
                "message": e.message, "rule": e.validator} for e in errors]
    only_confidence = all(list(e.path) == ["confidence"] for e in errors)
    return {"error": "EvidenceRecord 参数错误；请修正以下字段后重试同一证据，无需重新计算或请求用户确认。",
            "error_type": "invalid_confidence" if only_confidence else "invalid_evidence_arguments",
            "details": details, "allowed": CONFIDENCE if only_confidence else None}
