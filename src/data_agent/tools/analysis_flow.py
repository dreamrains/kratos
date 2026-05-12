"""Tools for persisting structured analysis planning artifacts."""

from __future__ import annotations

import json
from datetime import datetime

from data_agent.tools.registry import registry


_STAT_DETAIL_FIELDS = [
    "metrics",
    "sample_size",
    "time_scope",
    "calculation_method",
    "method_detail",
    "significance",
    "correlation",
    "confidence_interval",
]


def _mark_statistical_detail_status(payload: dict) -> dict:
    gaps = [field for field in _STAT_DETAIL_FIELDS if payload.get(field) in (None, "", [], {})]
    payload["statistical_detail_gaps"] = gaps
    payload["statistical_detail_status"] = "complete" if not gaps else "missing"
    return payload


def _session_id() -> str:
    try:
        from data_agent.agent.context import get_current_context
        ctx = get_current_context()
        if ctx is not None:
            return ctx.session_id
    except Exception:
        pass
    try:
        from data_agent.tools.visualization import current_session_id
        return current_session_id()
    except Exception:
        return ""


def _current_state():
    try:
        from data_agent.agent.analysis_state import current_analysis_state
        return current_analysis_state()
    except Exception:
        return None


def _write_analysis_artifact(kind: str, payload: dict) -> dict:
    from data_agent.config import get_config
    from data_agent.session.history import register_artifact

    sid = _session_id()
    if not sid:
        return {"error": "鏃犲綋鍓嶄細璇濓紝鏃犳硶淇濆瓨鍒嗘瀽浜х墿"}

    out_dir = get_config().sessions_resolved / sid / "analysis_flow"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = out_dir / f"{kind}_{ts}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    artifact_path = f"sessions/{sid}/analysis_flow/{path.name}"
    register_artifact(sid, artifact_path, kind, payload.get("goal") or payload.get("claim") or kind)
    return {"saved": artifact_path, "type": kind, "payload": payload}


@registry.register(
    name="record_data_requirement",
    description=(
        "Save a DataRequirement JSON with goal, must_have_data, recommended_data, "
        "optional_data, missing_limitations, and minimum_viable_analysis."
    ),
)
def record_data_requirement(requirement_json: str) -> str:
    try:
        payload = json.loads(requirement_json)
    except json.JSONDecodeError:
        return json.dumps({"error": "requirement_json 蹇呴』鏄湁鏁?JSON"}, ensure_ascii=False)
    required = [
        "goal",
        "must_have_data",
        "recommended_data",
        "optional_data",
        "missing_limitations",
        "minimum_viable_analysis",
    ]
    missing = [k for k in required if k not in payload]
    if missing:
        return json.dumps({"error": f"DataRequirement 缂哄皯瀛楁: {missing}"}, ensure_ascii=False)

    state = _current_state()
    if state is not None:
        payload = state.add_data_requirement(payload)
        state.save()

    result = _write_analysis_artifact("data_requirement", payload)
    result.pop("payload", None)
    if state is not None:
        result["state_stage"] = state.stage
        result["requirement_id"] = payload.get("id")
    return json.dumps(result, ensure_ascii=False)


@registry.register(
    name="record_analysis_spec",
    description=(
        "Save an AnalysisSpec JSON with goal, question_type, metrics, "
        "dimensions, required_data, method_plan, and limitations."
    ),
)
def record_analysis_spec(spec_json: str) -> str:
    try:
        payload = json.loads(spec_json)
    except json.JSONDecodeError:
        return json.dumps({"error": "spec_json 蹇呴』鏄湁鏁?JSON"}, ensure_ascii=False)
    required = ["goal", "question_type", "metrics", "dimensions", "required_data", "method_plan", "limitations"]
    missing = [k for k in required if k not in payload]
    if missing:
        return json.dumps({"error": f"AnalysisSpec 缂哄皯瀛楁: {missing}"}, ensure_ascii=False)

    state = _current_state()
    if state is not None:
        payload = state.set_analysis_plan(payload)
        state.save()

    result = _write_analysis_artifact("analysis_spec", payload)
    result.pop("payload", None)
    if state is not None:
        result["state_stage"] = state.stage
        result["analysis_spec_id"] = payload.get("id")

    try:
        from data_agent.tools.task_tools import create_workflow_tasks_from_spec
        result["workflow"] = create_workflow_tasks_from_spec(payload)
    except Exception as e:
        result["workflow_error"] = str(e)
    return json.dumps(result, ensure_ascii=False)


@registry.register(
    name="record_analysis_plan",
    description="Save an AnalysisPlan JSON for the expert analysis flow.",
)
def record_analysis_plan(plan_json: str) -> str:
    try:
        payload = json.loads(plan_json)
    except json.JSONDecodeError:
        return json.dumps({"error": "plan_json must be valid JSON"}, ensure_ascii=False)
    required = ["goal", "method_plan", "visualization_strategy"]
    missing = [k for k in required if k not in payload]
    if missing:
        return json.dumps({"error": f"AnalysisPlan missing fields: {missing}"}, ensure_ascii=False)

    state = _current_state()
    if state is not None:
        payload = state.set_analysis_plan(payload)
        state.save()

    result = _write_analysis_artifact("analysis_plan", payload)
    result.pop("payload", None)
    if state is not None:
        result["state_stage"] = state.stage
        result["analysis_plan_id"] = payload.get("id")

    try:
        from data_agent.tools.task_tools import create_workflow_tasks_from_spec
        result["workflow"] = create_workflow_tasks_from_spec(payload)
    except Exception as e:
        result["workflow_error"] = str(e)
    return json.dumps(result, ensure_ascii=False)


@registry.register(
    name="record_exploratory_finding",
    description="Save an ExploratoryFinding JSON. Exploratory findings are candidates, not final conclusions.",
)
def record_exploratory_finding(finding_json: str) -> str:
    try:
        payload = json.loads(finding_json)
    except json.JSONDecodeError:
        return json.dumps({"error": "finding_json must be valid JSON"}, ensure_ascii=False)
    if "finding" not in payload:
        return json.dumps({"error": "ExploratoryFinding missing fields: ['finding']"}, ensure_ascii=False)

    state = _current_state()
    if state is not None:
        payload = state.add_exploratory_finding(payload)
        state.save()

    result = _write_analysis_artifact("exploratory_finding", payload)
    result.pop("payload", None)
    if state is not None:
        result["state_stage"] = state.stage
        result["exploratory_finding_id"] = payload.get("id")
    return json.dumps(result, ensure_ascii=False)


@registry.register(
    name="record_validated_finding",
    description="Save a ValidatedFinding JSON with validation status, method, statistics, and limitations.",
)
def record_validated_finding(finding_json: str) -> str:
    try:
        payload = json.loads(finding_json)
    except json.JSONDecodeError:
        return json.dumps({"error": "finding_json must be valid JSON"}, ensure_ascii=False)
    required = ["claim", "validation_status", "validation_method", "statistical_explanation", "limitations"]
    missing = [k for k in required if k not in payload]
    if missing:
        return json.dumps({"error": f"ValidatedFinding missing fields: {missing}"}, ensure_ascii=False)

    state = _current_state()
    if state is not None:
        payload = state.add_validated_finding(payload)
        state.save()

    result = _write_analysis_artifact("validated_finding", payload)
    result.pop("payload", None)
    if state is not None:
        result["state_stage"] = state.stage
        result["validated_finding_id"] = payload.get("id")
    return json.dumps(result, ensure_ascii=False)


@registry.register(
    name="record_evidence_record",
    description=(
        "Save an EvidenceRecord JSON with claim, dataset, method, tool_calls, "
        "result_summary, limitations, confidence, and statistical details such as "
        "metrics, sample_size, calculation_method, significance, correlation, "
        "effect size, or confidence_interval when available."
    ),
)
def record_evidence_record(record_json: str) -> str:
    try:
        payload = json.loads(record_json)
    except json.JSONDecodeError:
        return json.dumps({"error": "record_json 蹇呴』鏄湁鏁?JSON"}, ensure_ascii=False)
    required = ["claim", "dataset", "method", "tool_calls", "result_summary", "limitations", "confidence"]
    missing = [k for k in required if k not in payload]
    if missing:
        return json.dumps({"error": f"EvidenceRecord 缂哄皯瀛楁: {missing}"}, ensure_ascii=False)

    allowed_confidence = {"high", "medium", "low", "speculative"}
    confidence = str(payload.get("confidence", "")).strip().lower()
    if confidence not in allowed_confidence:
        return json.dumps({
            "error": f"Invalid confidence level: {payload.get('confidence')}",
            "error_type": "invalid_confidence",
            "allowed": sorted(allowed_confidence),
        }, ensure_ascii=False)
    payload["confidence"] = confidence
    _mark_statistical_detail_status(payload)

    state = _current_state()
    if state is not None:
        payload = state.add_evidence_record(payload)
        state.save()

    result = _write_analysis_artifact("evidence_record", payload)
    result.pop("payload", None)
    if state is not None:
        result["state_stage"] = state.stage
        result["evidence_id"] = payload.get("id")
    result["statistical_detail_status"] = payload.get("statistical_detail_status")
    result["statistical_detail_gaps"] = payload.get("statistical_detail_gaps", [])
    return json.dumps(result, ensure_ascii=False)


@registry.register(
    name="record_analysis_objective",
    description="Save an AnalysisObjective JSON for question framing and risk/depth classification.",
)
def record_analysis_objective(objective_json: str) -> str:
    try:
        payload = json.loads(objective_json)
    except json.JSONDecodeError:
        return json.dumps({"error": "objective_json must be valid JSON"}, ensure_ascii=False)
    required = ["question_type", "business_object", "decision_risk", "analysis_depth", "requires_counterfactual", "expected_outputs"]
    missing = [k for k in required if k not in payload]
    if missing:
        return json.dumps({"error": f"AnalysisObjective missing fields: {missing}"}, ensure_ascii=False)

    state = _current_state()
    if state is not None:
        payload = state.set_analysis_objective(payload)
        state.save()

    result = _write_analysis_artifact("analysis_objective", payload)
    result.pop("payload", None)
    if state is not None:
        result["state_stage"] = state.stage
        result["analysis_objective_id"] = payload.get("id")
    return json.dumps(result, ensure_ascii=False)


@registry.register(
    name="record_insight_record",
    description=(
        "Save an InsightRecord JSON with title, summary, evidence_ids, "
        "chart_ids, recommendation, limitations, confidence, and output_type."
    ),
)
def record_insight_record(record_json: str) -> str:
    try:
        payload = json.loads(record_json)
    except json.JSONDecodeError:
        return json.dumps({"error": "record_json 蹇呴』鏄湁鏁?JSON"}, ensure_ascii=False)
    required = ["title", "summary", "evidence_ids", "chart_ids", "recommendation", "limitations", "confidence", "output_type"]
    missing = [k for k in required if k not in payload]
    if missing:
        return json.dumps({"error": f"InsightRecord 缂哄皯瀛楁: {missing}"}, ensure_ascii=False)

    state = _current_state()
    if state is not None:
        payload = state.add_insight_record(payload)
        state.save()

    result = _write_analysis_artifact("insight_record", payload)
    result.pop("payload", None)
    if state is not None:
        result["state_stage"] = state.stage
        result["insight_id"] = payload.get("id")
    return json.dumps(result, ensure_ascii=False)


@registry.register(
    name="record_expert_insight",
    description=(
        "Save an ExpertInsight JSON with conclusion, business_meaning, evidence_ids, "
        "statistical_explanation, limitations, recommendation, recommendation_confidence, and next_analysis."
    ),
)
def record_expert_insight(record_json: str) -> str:
    try:
        payload = json.loads(record_json)
    except json.JSONDecodeError:
        return json.dumps({"error": "record_json must be valid JSON"}, ensure_ascii=False)
    required = [
        "conclusion",
        "business_meaning",
        "evidence_ids",
        "statistical_explanation",
        "limitations",
        "recommendation",
        "recommendation_confidence",
        "next_analysis",
    ]
    missing = [k for k in required if k not in payload]
    if missing:
        return json.dumps({"error": f"ExpertInsight missing fields: {missing}"}, ensure_ascii=False)

    confidence = str(payload.get("recommendation_confidence", "")).strip().lower()
    if confidence not in {"high", "medium", "low"}:
        return json.dumps({
            "error": f"Invalid recommendation_confidence: {payload.get('recommendation_confidence')}",
            "error_type": "invalid_recommendation_confidence",
            "allowed": ["high", "medium", "low"],
        }, ensure_ascii=False)
    payload["recommendation_confidence"] = confidence

    state = _current_state()
    if state is not None:
        payload = state.add_expert_insight(payload)
        state.save()

    result = _write_analysis_artifact("expert_insight", payload)
    result.pop("payload", None)
    if state is not None:
        result["state_stage"] = state.stage
        result["expert_insight_id"] = payload.get("id")
    return json.dumps(result, ensure_ascii=False)
