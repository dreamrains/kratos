"""Model-visible input contract, also used before any receipt lookup."""

CONFIDENCE = ["high", "medium", "low", "speculative"]
DERIVED_OPERATIONS = [
    "sum", "difference", "product", "ratio", "percent_change",
    "percentage_point_change",
]
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
        "measurements": {
            "description": (
                "Optional receipt-bound measurements. For ordinary evidence, concise metric/value/unit or "
                "metric/delta/direction objects are allowed. Executable Stage 3C0B evidence is selected only "
                "by explicit plan_id/step_id and must use the full canonical measurement contract."
            ),
            "anyOf": [{"type": "null"}, {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "metric": {"type": "string"},
                    "value": {"type": ["number", "string", "null"]},
                    "unit": {"type": "string"},
                    "delta": {"type": ["number", "null"]},
                    "change": {"type": ["number", "null"]},
                    "pct_change": {"type": ["number", "null"]},
                    "direction": {"type": "string", "enum": ["increased", "decreased", "flat", "unknown"]},
                },
            }}],
        },
        "competing_hypotheses": {
            "description": (
                "Optional host-validated relations to hypothesis IDs shown in <competing_hypotheses>. "
                "Use one entry per proposed support/refute relation."
            ),
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "hypothesis_id": {"type": "string", "minLength": 1},
                    "relation": {"type": "string", "enum": ["supports", "refutes"]},
                    "metric": {"type": "string", "minLength": 1},
                    "observed": {"type": "string", "enum": ["increased", "decreased", "flat"]},
                },
            },
        },
        "derived_measurements": {
            "description": (
                "Candidate arithmetic over unique canonical operand identities in this EvidenceRecord. "
                "difference, ratio, percent_change and percentage_point_change require exactly two operand_refs; "
                "sum and product require at least one. Reusing one unique operand explicitly is allowed. "
                "Arithmetic validation does not grant source-value, unit or fact authority."
            ),
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "operation", "operand_refs", "result", "unit", "scale", "rounding", "scope_ref"],
                "properties": {
                    "id": {"type": "string", "minLength": 1},
                    "operation": {"type": "string", "enum": DERIVED_OPERATIONS},
                    "operand_refs": {"type": "array", "minItems": 1, "items": {"type": "string", "minLength": 1}},
                    "result": {"anyOf": [{"type": "number"}, {"type": "string", "minLength": 1}]},
                    "unit": {"type": "string", "minLength": 1},
                    "scale": {"anyOf": [{"type": "number"}, {"type": "string", "minLength": 1}]},
                    "rounding": {"type": "string", "minLength": 1},
                    "scope_ref": {"type": "string", "minLength": 1},
                    "scenario": {"type": "boolean"},
                },
            },
        },
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
