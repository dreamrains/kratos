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
        return {"error": "无当前会话，无法保存分析产物"}

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
        return json.dumps({"error": "requirement_json 必须是有效 JSON"}, ensure_ascii=False)
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
        return json.dumps({"error": f"DataRequirement 缺少字段: {missing}"}, ensure_ascii=False)

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
        return json.dumps({"error": "spec_json 必须是有效 JSON"}, ensure_ascii=False)
    required = ["goal", "question_type", "metrics", "dimensions", "required_data", "method_plan", "limitations"]
    missing = [k for k in required if k not in payload]
    if missing:
        return json.dumps({"error": f"AnalysisSpec 缺少字段: {missing}"}, ensure_ascii=False)

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

    # Optional fields - pass through if present
    _valid_depths = {"lightweight", "standard", "comprehensive"}
    if payload.get("depth") is not None:
        depth = str(payload["depth"]).strip().lower()
        if depth not in _valid_depths:
            return json.dumps({
                "error": f"Invalid depth: {payload.get('depth')}",
                "error_type": "invalid_depth",
                "allowed": sorted(_valid_depths),
            }, ensure_ascii=False)
        payload["depth"] = depth
    # expected_dimensions is optional - just pass through if present

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
        return json.dumps({"error": "record_json 必须是有效 JSON"}, ensure_ascii=False)
    required = ["claim", "dataset", "method", "tool_calls", "result_summary", "limitations", "confidence"]
    missing = [k for k in required if k not in payload]
    if missing:
        return json.dumps({"error": f"EvidenceRecord 缺少字段: {missing}"}, ensure_ascii=False)

    allowed_confidence = {"high", "medium", "low", "speculative"}
    confidence = str(payload.get("confidence", "")).strip().lower()
    if confidence not in allowed_confidence:
        return json.dumps({
            "error": f"Invalid confidence level: {payload.get('confidence')}",
            "error_type": "invalid_confidence",
            "allowed": sorted(allowed_confidence),
        }, ensure_ascii=False)
    payload["confidence"] = confidence

    # Optional fields - pass through if present
    if payload.get("competing_hypotheses") is not None:
        hypotheses = payload["competing_hypotheses"]
        if not isinstance(hypotheses, list):
            return json.dumps({
                "error": "competing_hypotheses must be a list of dicts",
                "error_type": "invalid_competing_hypotheses",
            }, ensure_ascii=False)
        payload["competing_hypotheses"] = hypotheses

    _valid_insight_types = {"trend", "anomaly", "contribution", "driver", "evaluation"}
    if payload.get("insight_type") is not None:
        insight_type = str(payload["insight_type"]).strip().lower()
        if insight_type not in _valid_insight_types:
            return json.dumps({
                "error": f"Invalid insight_type: {payload.get('insight_type')}",
                "error_type": "invalid_insight_type",
                "allowed": sorted(_valid_insight_types),
            }, ensure_ascii=False)
        payload["insight_type"] = insight_type

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
