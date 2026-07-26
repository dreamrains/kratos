"""Tools for persisting structured analysis planning artifacts."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from data_agent.agent.analysis_plan_contracts import analysis_plan_tool_object_schema
from data_agent.tools.registry import registry


_BASE_STAT_DETAIL_FIELDS = [
    "metrics",
    "sample_size",
    "time_scope",
    "calculation_method",
    "method_detail",
]


def statistical_detail_fields(payload: dict) -> list[str]:
    """Return method-appropriate detail fields without universal significance."""

    fields = list(_BASE_STAT_DETAIL_FIELDS)
    method = str(payload.get("method") or "").strip().lower()
    claim_type = str(payload.get("claim_type") or payload.get("inference_mode") or "").lower()
    comparison = any(
        marker in method
        for marker in ("compare", "comparison", "before-after", "before_after", "paired", "cluster")
    )
    time_series = any(marker in method for marker in ("trend", "time_series", "time series"))
    inferential = claim_type in {
        "inferential", "generalized_difference", "population_difference",
    } or any(
        marker in method
        for marker in ("inferential", "hypothesis", "t_test", "t-test", "ttest", "anova")
    )

    if comparison:
        fields.extend([
            "denominator",
            "missingness",
            "estimand",
            "effect_estimate",
            "sample_adequacy",
        ])
    if time_series:
        fields.extend([
            "time_frequency",
            "missing_intervals",
            "window_comparability",
            "autocorrelation_awareness",
        ])
    if inferential:
        fields.extend(["effect_estimate", "confidence_interval", "sample_adequacy"])
    if payload.get("significance") not in (None, "", [], {}) or any(
        marker in method for marker in ("hypothesis", "t_test", "t-test", "ttest", "anova")
    ):
        fields.append("significance")
    if payload.get("correlation") not in (None, "", [], {}) or "correlation" in method:
        fields.append("correlation")
    return list(dict.fromkeys(fields))


def _mark_statistical_detail_status(payload: dict) -> dict:
    gaps = [
        field
        for field in statistical_detail_fields(payload)
        if payload.get(field) in (None, "", [], {})
    ]
    payload["statistical_detail_gaps"] = gaps
    payload["statistical_detail_status"] = "complete" if not gaps else "missing"
    return payload


def _claim_asserts_significance(payload: dict) -> bool:
    claim_text = " ".join(
        str(payload.get(field) or "")
        for field in ("claim", "claim_type", "inference_mode")
    ).lower()
    return any(
        marker in claim_text
        for marker in (
            "statistically significant",
            "significantly",
            "significant",
            "significance",
            "显著",
        )
    )


def _significance_support_is_known(value: Any) -> bool:
    if value in (None, "", [], {}):
        return False
    if isinstance(value, dict):
        return any(_significance_support_is_known(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(_significance_support_is_known(item) for item in value)
    if isinstance(value, (bool, int, float)):
        return True
    normalized = " ".join(str(value).strip().lower().replace("-", " ").split())
    return not normalized.startswith(
        (
            "unknown",
            "unassessed",
            "not assessed",
            "not applicable",
            "not reported",
            "unreported",
            "not available",
            "n/a",
        )
    )


def _auto_generate_limitations(payload: dict) -> list[str]:
    """Generate limitations from method-specific evidence, never raw n cutoffs."""
    auto = []
    method = str(payload.get("method", "")).lower()
    raw_limitations = payload.get("limitations", [])
    limitations = (
        [raw_limitations]
        if isinstance(raw_limitations, str)
        else list(raw_limitations) if isinstance(raw_limitations, list) else []
    )

    if (
        _claim_asserts_significance(payload)
        and not _significance_support_is_known(payload.get("significance"))
        and not any(
            "统计" in str(item) or "significan" in str(item).lower()
            for item in limitations
        )
    ):
        auto.append("该显著性表述缺少已知统计检验或不确定性支持，不能排除随机波动")

    # Before/after comparison without control group
    if any(kw in method for kw in ["before_after", "前后对比", "period_compare", "compare_periods"]):
        if not any("对照" in l for l in limitations):
            auto.append("无对照组/随机化，结论为描述性关联而非因果关系")

    adequacy = payload.get("sample_adequacy")
    if isinstance(adequacy, dict):
        status = str(adequacy.get("status") or "").strip().lower()
        reason = str(adequacy.get("reason") or "").strip()
        if status in {"inadequate", "insufficient", "not_estimable"} and reason:
            if not any("样本" in str(item) for item in limitations):
                auto.append(f"样本充分性检查未通过：{reason}")
        elif status in {"marginal", "adequate_with_limits", "estimable_with_limits"} and reason:
            if not any("样本" in str(item) for item in limitations):
                auto.append(f"样本充分性有限：{reason}")

    # Short observation period
    time_scope = str(payload.get("time_scope", ""))
    if time_scope and "天" in time_scope and "月" not in time_scope:
        if not any("时间" in l or "观察" in l for l in limitations):
            auto.append("观察期较短，可能受短期波动影响")

    return auto


def _calibrate_confidence(payload: dict) -> list[str]:
    """Auto-calibrate confidence based on evidence quality signals.

    Returns list of warning strings if confidence should be downgraded.
    Only calibrates when confidence is "high" — lower levels are kept as-is.
    """
    confidence = payload.get("confidence", "")
    if confidence != "high":
        return []

    warnings: list[str] = []

    claim_type = str(payload.get("claim_type") or payload.get("inference_mode") or "").lower()
    method = str(payload.get("method") or "").lower()
    inferential = claim_type in {
        "inferential",
        "generalized_difference",
        "population_difference",
    } or any(marker in method for marker in ("inferential", "experiment", "hypothesis_test"))
    comparison = claim_type in {"generalized_difference", "population_difference"} or (
        inferential
        and any(
            marker in method
            for marker in (
                "compare", "comparison", "difference", "paired", "cluster",
                "t_test", "t-test", "ttest", "anova", "mann", "wilcoxon",
            )
        )
    )
    inferential_time_series = inferential and any(
        marker in method for marker in ("trend", "time_series", "time series")
    )

    adequacy = payload.get("sample_adequacy")
    if isinstance(adequacy, dict):
        adequacy_status = str(adequacy.get("status") or "").strip().lower()
        if adequacy_status in {"inadequate", "insufficient", "not_estimable"}:
            reason = str(adequacy.get("reason") or "method-specific sample adequacy failed")
            warnings.append(f"样本充分性不支持高置信度：{reason}")
        elif adequacy_status in {"marginal", "adequate_with_limits", "estimable_with_limits"}:
            reason = str(adequacy.get("reason") or "method-specific sample adequacy is marginal")
            warnings.append(f"样本充分性仅有限支持：{reason}")
    elif comparison:
        warnings.append("推断性比较缺少按设计评估的有效样本充分性，不应标记高置信度")
    elif inferential_time_series:
        warnings.append("推断性时间趋势缺少按依赖结构评估的有效样本充分性，不应标记高置信度")

    if comparison:
        if payload.get("effect_estimate") in (None, "", [], {}):
            warnings.append("推断性比较未报告效应量，不应标记高置信度")
        if payload.get("confidence_interval") in (None, "", [], {}):
            warnings.append("推断性比较未报告置信区间，不应标记高置信度")
    elif inferential_time_series and payload.get("confidence_interval") in (None, "", [], {}):
        warnings.append("推断性时间趋势未报告依赖结构适配的置信区间，不应标记高置信度")

    seasonality = payload.get("seasonality_estimability")
    if isinstance(seasonality, dict):
        status = str(seasonality.get("status") or "").strip().lower()
        if status == "not_estimable":
            warnings.append("季节性不可估计，不应标记高置信度")
        elif status == "estimable_with_limits":
            warnings.append("季节性仅能有限估计，不应标记高置信度")

    comparability = payload.get("window_comparability")
    if isinstance(comparability, dict):
        status = str(comparability.get("status") or "").strip().lower()
        if status in {"comparable_with_adjustment", "not_comparable"}:
            warnings.append("时间窗口不可直接比较或需要调整，不应标记高置信度")

    # Check significance
    significance = str(payload.get("significance", "")).lower()
    if significance and "not significant" in significance:
        warnings.append("统计不显著，不应标记高置信度")
    elif significance and "p>" in significance:
        warnings.append("p值大于0.05，不应标记高置信度")
    elif (
        _claim_asserts_significance(payload)
        and not _significance_support_is_known(payload.get("significance"))
    ):
        warnings.append("显著性表述缺少已知统计检验或不确定性支持，不应标记高置信度")

    # Check for missing limitations
    limitations = payload.get("limitations")
    if not limitations:
        warnings.append("未声明任何局限性，高置信度需要已知限制说明")

    return warnings


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
    from data_agent.agent.analysis_plan_contracts import normalize_analysis_plan_contract

    validation = normalize_analysis_plan_contract(payload, require_executable=False)
    if not validation.ok:
        return json.dumps({
            "error": validation.message,
            "error_type": validation.error_type,
            "details": validation.details,
        }, ensure_ascii=False)
    payload = validation.plan
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
    result["analysis_plan_id"] = payload.get("id")
    result["deprecated_adapter"] = "record_analysis_spec"
    result["workflow"] = {
        "created": 0,
        "task_ids": [],
        "display_only": True,
        "reason": "deprecated_analysis_spec_adapter_display_only",
    }
    return json.dumps(result, ensure_ascii=False)


@registry.register(
    name="record_analysis_plan",
    description="Save a canonical executable AnalysisPlan.",
    argument_aliases={"plan_json": "plan"},
    compatibility_json_object_parameters={"plan"},
    parameters={
        "type": "object",
        "properties": {
            "plan": analysis_plan_tool_object_schema(),
        },
        "required": ["plan"],
        "additionalProperties": False,
    },
)
def record_analysis_plan(plan: dict[str, Any]) -> str:
    payload = plan
    if not isinstance(payload, dict):
        return json.dumps({
            "error": "plan must be an object",
            "error_type": "invalid_analysis_plan",
        }, ensure_ascii=False)
    return _persist_analysis_plan_payload(payload)


def _persist_analysis_plan_payload(payload: dict[str, Any]) -> str:
    required = ["goal", "method_plan", "visualization_strategy"]
    missing = [k for k in required if k not in payload]
    if missing:
        return json.dumps({"error": f"AnalysisPlan missing fields: {missing}"}, ensure_ascii=False)

    state = _current_state()
    from data_agent.agent.analysis_plan_contracts import normalize_analysis_plan_contract

    requirement_inputs: dict[str, Any] = {"dataset_contracts": None}
    if state is not None:
        requirement_inputs = state.analysis_requirement_inputs(payload)
    validation = normalize_analysis_plan_contract(
        payload,
        require_executable=True,
        **requirement_inputs,
    )
    if not validation.ok:
        return json.dumps({
            "error": validation.message,
            "error_type": validation.error_type,
            "details": validation.details,
        }, ensure_ascii=False)
    payload = validation.plan

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

    if state is not None:
        payload = state.set_analysis_plan(payload)
        state.save()

    result = _write_analysis_artifact("analysis_plan", payload)
    result.pop("payload", None)
    result["analysis_plan_id"] = payload.get("id")
    if state is not None:
        result["state_stage"] = state.stage

    try:
        from data_agent.tools.task_tools import create_workflow_tasks_from_plan
        result["workflow"] = create_workflow_tasks_from_plan(payload)
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
    if not isinstance(payload, dict):
        return json.dumps({
            "error": "EvidenceRecord must be a JSON object.",
            "error_type": "invalid_evidence",
        }, ensure_ascii=False)

    state = _current_state()
    current_plan_id = ""
    if state is not None and isinstance(getattr(state, "analysis_plan", None), dict):
        current_plan_id = str(state.analysis_plan.get("id") or "")

    is_stage3c0b_evidence = (
        "plan_id" in payload
        or "step_id" in payload
        or payload.get("measurements") is not None
    )
    if (
        is_stage3c0b_evidence
        or payload.get("contract_version") == "evidence_record.v2"
        or "source_tool_call_ids" in payload
    ):
        from data_agent.agent.context import get_current_context
        from data_agent.agent.evidence_contracts import bind_evidence_to_computations
        from data_agent.config import get_config

        context = get_current_context()
        turn_state = getattr(context, "turn_state", None) if context is not None else None
        binding = bind_evidence_to_computations(
            payload,
            computation_refs=list(getattr(state, "computation_refs", []) or []),
            sessions_root=get_config().sessions_resolved,
            current_session_id=str(getattr(context, "session_id", "") or ""),
            current_turn_id=str(getattr(turn_state, "turn_id", "") or ""),
            current_plan=(getattr(state, "analysis_plan", None) or {}),
            workspace=(context.workspace if context is not None else None),
        )
        if not binding.ok:
            return json.dumps({
                "error": binding.message,
                "error_type": binding.error_type,
                "details": binding.details,
            }, ensure_ascii=False)
        payload = binding.record

    if is_stage3c0b_evidence:
        from data_agent.agent.evidence_contracts import validate_evidence_record

        validation = validate_evidence_record(
            payload,
            current_plan_id=current_plan_id,
        )
        if not validation.ok:
            return json.dumps({
                "error": validation.message,
                "error_type": validation.error_type,
                "details": validation.details,
            }, ensure_ascii=False)
        payload = validation.record

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

    # Phase 3: Auto-calibrate confidence based on evidence quality
    calibration_warnings = _calibrate_confidence(payload)
    if calibration_warnings:
        payload["calibration_warnings"] = calibration_warnings
        original = payload["confidence"]
        if original == "high":
            payload["confidence"] = "medium"
            payload["confidence_auto_downgraded"] = True
            payload["original_confidence"] = original

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

    if not is_stage3c0b_evidence:
        payload.setdefault("provenance_status", "legacy_unbound")
        payload.setdefault("verification_level", "legacy_unbound")
        _mark_statistical_detail_status(payload)

    # Auto-generate limitations based on analysis context
    auto_lim = _auto_generate_limitations(payload)
    if auto_lim:
        payload["auto_generated_limitations"] = auto_lim

    if state is not None:
        if payload.get("plan_id") and "measurements" in payload:
            payload = state.upsert_evidence_record(payload)
        else:
            payload = state.add_evidence_record(payload)
        state.save()

    result = _write_analysis_artifact("evidence_record", payload)
    result.pop("payload", None)
    if state is not None:
        result["state_stage"] = state.stage
        result["evidence_id"] = payload.get("id")
        try:
            from data_agent.session.task_manager import task_manager
            plan = state.analysis_plan if state is not None else {}
            completed_task_ids = task_manager.complete_matching_tasks_from_evidence(
                session_id=state.session_id,
                evidence=payload,
                # Canonical plan/step/claim/requirement identities own v2 matching.
                # The legacy analysis_spec_id filter applies only to unscoped records.
                analysis_spec_id=("" if is_stage3c0b_evidence else (plan or {}).get("id", "")),
            )
            if completed_task_ids:
                result["completed_task_ids"] = completed_task_ids
        except Exception as e:
            result["task_completion_error"] = str(e)
    if not is_stage3c0b_evidence:
        result["statistical_detail_status"] = payload.get("statistical_detail_status")
        result["statistical_detail_gaps"] = payload.get("statistical_detail_gaps", [])
    if auto_lim:
        result["auto_generated_limitations"] = auto_lim
    if calibration_warnings:
        result["calibration_warnings"] = calibration_warnings
        if payload.get("confidence_auto_downgraded"):
            result["confidence_auto_downgraded"] = True
            result["original_confidence"] = payload.get("original_confidence")
    return json.dumps(result, ensure_ascii=False)


@registry.register(
    name="get_analysis_summary",
    description="Read-only query: get a structured summary of the current analysis state including evidence records, insights, and stage. Use in conversation mode to answer questions about previous analysis results.",
)
def get_analysis_summary() -> str:
    """Return a structured summary of current analysis state for conversation mode."""
    state = _current_state()
    if state is None:
        return json.dumps({"info": "No active analysis state found"}, ensure_ascii=False)

    from data_agent.agent.analysis_state import analysis_state_summary

    summary_parts: dict[str, object] = {
        "stage": state.stage,
        "goal": state.goal or "-",
        "data_state": state.data_state,
    }

    # Evidence records summary
    evidence = state.evidence_records or []
    if evidence:
        evidence_summary = []
        for rec in evidence:
            entry = {
                "claim": rec.get("claim", ""),
                "confidence": rec.get("confidence", ""),
                "method": rec.get("method", ""),
            }
            if rec.get("sample_size"):
                entry["sample_size"] = rec.get("sample_size")
            evidence_summary.append(entry)
        summary_parts["evidence_records"] = evidence_summary
        summary_parts["evidence_count"] = len(evidence)
    else:
        summary_parts["evidence_count"] = 0

    # Insight records summary
    insights = state.insight_records or []
    if insights:
        summary_parts["insight_records"] = [
            {"output": ins.get("output", ""), "type": ins.get("output_type", "")}
            for ins in insights
        ]
        summary_parts["insight_count"] = len(insights)
    else:
        summary_parts["insight_count"] = 0

    # Regression history
    if state.regression_history:
        summary_parts["last_regression"] = state.regression_history[-1]

    # Plan info
    if state.analysis_plan:
        summary_parts["has_plan"] = True
        summary_parts["plan_goal"] = state.analysis_plan.get("goal", "")

    return json.dumps(summary_parts, ensure_ascii=False)
