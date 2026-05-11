"""Method playbooks for consulting-style data analysis workflows.

Playbooks are intentionally medium-structured.  They guide data requirements,
workflow tasks, evidence, and limitations without hard-coding final business
conclusions.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.intent import TurnIntent


@dataclass(frozen=True)
class MethodPlaybook:
    id: str
    name: str
    description: str
    question_types: list[str]
    typical_user_goals: list[str]
    applicability: dict[str, Any]
    data_requirements: dict[str, Any]
    method_plan_template: list[dict[str, Any]]
    confirmation_policy: dict[str, Any]
    evidence_policy: dict[str, Any]
    limitation_policy: dict[str, Any]
    output_policy: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PlaybookSelection:
    primary_playbook_id: str
    supporting_playbook_ids: list[str] = field(default_factory=list)
    selection_reason: str = ""
    recommended_paths: list[dict[str, Any]] = field(default_factory=list)
    data_requirement: dict[str, Any] | None = None
    analysis_spec: dict[str, Any] | None = None
    requires_confirmation: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "primary_playbook_id": self.primary_playbook_id,
            "supporting_playbook_ids": self.supporting_playbook_ids,
            "selection_reason": self.selection_reason,
            "recommended_paths": self.recommended_paths,
            "data_requirement": self.data_requirement,
            "analysis_spec": self.analysis_spec,
            "requires_confirmation": self.requires_confirmation,
        }


def _pb(
    *,
    id: str,
    name: str,
    description: str,
    question_types: list[str],
    typical_user_goals: list[str],
    must_have: list[str],
    recommended: list[str],
    minimum: str,
    method_plan: list[dict[str, Any]],
    evidence: list[str],
    limitations: list[str],
    confirmation: dict[str, Any] | None = None,
    optional: list[str] | None = None,
    risk_level: str = "low",
) -> MethodPlaybook:
    return MethodPlaybook(
        id=id,
        name=name,
        description=description,
        question_types=question_types,
        typical_user_goals=typical_user_goals,
        applicability={
            "risk_level": risk_level,
            "not_suitable_when": ["the available data cannot satisfy the minimum viable data"],
        },
        data_requirements={
            "must_have_data": must_have,
            "recommended_data": recommended,
            "optional_data": optional or [],
            "minimum_viable_data": minimum,
            "missing_limitations": limitations,
        },
        method_plan_template=method_plan,
        confirmation_policy=confirmation or {"requires_confirmation": False, "confirmation_type": ""},
        evidence_policy={
            "required_evidence": evidence,
            "confidence_rules": "Base confidence on data completeness, method fit, and whether assumptions are verified.",
            "forbidden_claims": ["do not claim causality or certainty beyond the evidence"],
        },
        limitation_policy={
            "required_limitations": limitations,
            "default_confidence": "medium",
        },
        output_policy={
            "default_outputs": ["data requirement or analysis plan", "evidence-backed conclusion", "limitations", "next steps"],
            "style": "explain methods and boundaries in plain language for non-expert users",
        },
    )


PLAYBOOKS: dict[str, MethodPlaybook] = {
    "data_understanding": _pb(
        id="data_understanding",
        name="Data Understanding",
        description="Understand dataset structure, quality, fields, and feasible analysis paths.",
        question_types=["description", "diagnostic"],
        typical_user_goals=["understand data", "find useful analysis directions", "check data quality"],
        must_have=["dataset schema", "row count", "column semantics"],
        recommended=["sample rows", "missingness", "unique keys", "time fields", "metric fields"],
        optional=["business definitions"],
        minimum="At least one dataset with readable columns and sample rows.",
        method_plan=[
            {"step": "profile dataset schema and sample rows", "node_type": "data_check", "required_capability": "data.profile", "expected_output": "schema, row count, missingness", "evidence_requirements": ["schema", "missingness"]},
            {"step": "identify feasible analysis paths", "node_type": "method", "required_capability": "data.describe", "expected_output": "2-3 recommended analysis paths", "evidence_requirements": ["field semantics"]},
        ],
        evidence=["schema", "missingness", "field semantics"],
        limitations=["field names may not reveal business meaning without user confirmation"],
    ),
    "metric_overview": _pb(
        id="metric_overview",
        name="Metric Overview",
        description="Summarize key metrics, distributions, rankings, and basic comparisons.",
        question_types=["description"],
        typical_user_goals=["summarize metrics", "show top items", "describe distribution"],
        must_have=["metric value", "optional dimension"],
        recommended=["time field", "dimension field", "business metric definition"],
        minimum="One numeric metric or countable event field.",
        method_plan=[
            {"step": "describe metric distribution", "node_type": "analysis", "required_capability": "data.describe", "expected_output": "summary statistics", "evidence_requirements": ["metric distribution"]},
            {"step": "rank important dimensions", "node_type": "analysis", "required_capability": "analysis.top_n", "expected_output": "top/bottom contributors", "evidence_requirements": ["dimension", "metric"]},
        ],
        evidence=["metric distribution", "top dimensions"],
        limitations=["overview does not explain root causes by itself"],
    ),
    "trend_period_comparison": _pb(
        id="trend_period_comparison",
        name="Trend & Period Comparison",
        description="Analyze time trends, period-over-period changes, and abnormal shifts.",
        question_types=["description", "diagnostic", "monitoring"],
        typical_user_goals=["compare periods", "find trend", "explain recent change"],
        must_have=["metric value", "event time or period"],
        recommended=["comparison window", "dimension fields", "seasonality context"],
        minimum="A metric with a usable time or period field.",
        method_plan=[
            {"step": "compare periods for the target metric", "node_type": "analysis", "required_capability": "analysis.period_compare", "expected_output": "metric delta by period", "evidence_requirements": ["periods", "metric_delta"]},
            {"step": "inspect time trend and anomalies", "node_type": "analysis", "required_capability": "analysis.time_series", "expected_output": "trend and anomaly summary", "evidence_requirements": ["trend"]},
        ],
        evidence=["period delta", "trend direction"],
        limitations=["period comparison can be distorted by seasonality or data freshness"],
    ),
    "driver_decomposition": _pb(
        id="driver_decomposition",
        name="Driver Decomposition",
        description="Decompose metric movement by dimensions and candidate drivers.",
        question_types=["diagnostic"],
        typical_user_goals=["explain decline", "find drivers", "attribute metric change"],
        must_have=["target metric", "comparison period or baseline", "one or more dimensions"],
        recommended=["candidate factor fields", "volume and rate components"],
        minimum="A target metric, comparison basis, and at least one dimension.",
        method_plan=[
            {"step": "compare target metric across periods", "node_type": "analysis", "required_capability": "analysis.period_compare", "expected_output": "overall change", "evidence_requirements": ["metric_delta"]},
            {"step": "decompose change by dimensions", "node_type": "analysis", "required_capability": "analysis.dimension_decomposition", "expected_output": "driver contribution table", "evidence_requirements": ["drivers", "contribution"]},
        ],
        evidence=["metric delta", "driver contribution"],
        limitations=["descriptive decomposition is not causal proof"],
    ),
    "funnel_conversion": _pb(
        id="funnel_conversion",
        name="Funnel Conversion",
        description="Analyze conversion steps, largest drop-offs, and funnel measurement boundaries.",
        question_types=["diagnostic"],
        typical_user_goals=["find largest funnel loss", "analyze conversion", "optimize funnel"],
        must_have=["ordered funnel steps", "step count or user-level events"],
        recommended=["entity_id", "event_time", "step order", "segment dimensions"],
        minimum="Aggregated ordered step counts, or user-level event records with step semantics.",
        method_plan=[
            {"step": "calculate step conversion and drop-off", "node_type": "analysis", "required_capability": "analysis.funnel", "expected_output": "largest drop-off step", "evidence_requirements": ["steps", "conversion_rate", "dropoff"]},
            {"step": "check aggregation and user path limitations", "node_type": "evidence", "required_capability": "artifact.evidence_record", "expected_output": "funnel limitation summary", "evidence_requirements": ["data grain"]},
        ],
        evidence=["step conversion", "largest drop-off", "data grain"],
        limitations=["aggregate counts do not prove user-level journey order"],
    ),
    "retention_lifecycle": _pb(
        id="retention_lifecycle",
        name="Retention & Lifecycle",
        description="Analyze cohorts, retention, repeat behavior, lifecycle stages, and churn tendency.",
        question_types=["diagnostic", "prediction", "monitoring"],
        typical_user_goals=["analyze retention", "predict churn", "understand repeat purchase"],
        must_have=["entity_id", "event_time", "activity or purchase event"],
        recommended=["cohort basis", "segment dimensions", "revenue or value metric", "target label for prediction"],
        optional=["intervention exposure", "user attributes"],
        minimum="Entity-level events with timestamps and a definable cohort or activity event.",
        method_plan=[
            {"step": "build cohorts and calculate retention curve", "node_type": "analysis", "required_capability": "analysis.cohort", "expected_output": "retention table by cohort and period", "evidence_requirements": ["cohort size", "retention_rate"]},
            {"step": "model churn or repeat tendency when target labels are available", "node_type": "analysis", "required_capability": "fallback.python", "expected_output": "model-ready target and feature summary", "evidence_requirements": ["target definition", "validation metric"], "confirmation_policy": {"requires_confirmation": True, "confirmation_type": "method_confirmation"}},
        ],
        evidence=["cohort size", "retention rate", "target definition"],
        limitations=["retention patterns are sensitive to cohort definition and observation window"],
        confirmation={"requires_confirmation": True, "confirmation_type": "method_confirmation", "blocking_reason": "predictive retention/churn modeling needs target and window confirmation"},
        risk_level="medium",
    ),
    "evaluation_causal": _pb(
        id="evaluation_causal",
        name="Evaluation & Causal",
        description="Evaluate experiments, campaign effects, quasi-causal designs, and causal boundaries.",
        question_types=["evaluation", "causal", "decision"],
        typical_user_goals=["evaluate effect", "decide whether to continue", "measure campaign impact"],
        must_have=["treatment or exposure", "outcome metric", "time window"],
        recommended=["control group", "pre-period outcome", "cost", "confounders", "assignment rule"],
        optional=["randomization metadata"],
        minimum="Treatment/exposure and outcome data; causal confidence requires a comparable control or experimental design.",
        method_plan=[
            {"step": "validate treatment, outcome, and comparison design", "node_type": "data_check", "required_capability": "data.profile", "expected_output": "design readiness", "evidence_requirements": ["treatment", "outcome", "comparison group"], "confirmation_policy": {"requires_confirmation": True, "confirmation_type": "method_confirmation"}},
            {"step": "estimate effect with experiment or causal method", "node_type": "analysis", "required_capability": "analysis.causal", "expected_output": "effect estimate and assumptions", "evidence_requirements": ["effect", "assumptions"]},
        ],
        evidence=["effect estimate", "comparison design", "assumptions"],
        limitations=["without randomization or a credible control group, causal claims are limited"],
        confirmation={"requires_confirmation": True, "confirmation_type": "method_confirmation", "blocking_reason": "causal or decision analysis needs method and metric confirmation"},
        risk_level="high",
    ),
    "forecast_decision_simulation": _pb(
        id="forecast_decision_simulation",
        name="Forecast & Decision Simulation",
        description="Forecast metrics, estimate ROI, run what-if simulations, and support decisions.",
        question_types=["prediction", "decision", "monitoring"],
        typical_user_goals=["forecast revenue", "estimate ROI", "simulate scenarios", "decide budget"],
        must_have=["target metric", "time field or scenario assumptions"],
        recommended=["cost", "baseline", "drivers", "historical periods", "decision alternatives"],
        optional=["confidence interval inputs", "external assumptions"],
        minimum="Historical target metric for forecasting, or explicit assumptions for scenario simulation.",
        method_plan=[
            {"step": "forecast target metric or baseline", "node_type": "analysis", "required_capability": "analysis.forecast", "expected_output": "forecast with uncertainty or validation", "evidence_requirements": ["training window", "forecast window", "validation"]},
            {"step": "simulate ROI or decision scenarios", "node_type": "analysis", "required_capability": "fallback.python", "expected_output": "scenario table with assumptions", "evidence_requirements": ["cost", "benefit", "assumptions"], "confirmation_policy": {"requires_confirmation": True, "confirmation_type": "method_confirmation"}},
        ],
        evidence=["forecast window", "assumptions", "sensitivity or confidence"],
        limitations=["forecast and ROI are assumption-dependent and should not be treated as guaranteed"],
        confirmation={"requires_confirmation": True, "confirmation_type": "method_confirmation", "blocking_reason": "forecast or ROI decisions need target, time window, and assumptions confirmed"},
        risk_level="high",
    ),
}


def get_playbook(playbook_id: str) -> MethodPlaybook | None:
    return PLAYBOOKS.get(playbook_id)


def list_playbooks() -> list[MethodPlaybook]:
    return list(PLAYBOOKS.values())


def select_playbooks(
    user_input: str,
    intent: TurnIntent,
    state: AnalysisSessionState | None = None,
    dataset_profile: str = "",
) -> PlaybookSelection:
    text = (user_input or "").lower()
    has_data = intent.data_state == "data_loaded" or bool(dataset_profile.strip())
    primary = _choose_primary(text, intent, has_data)
    supporting = _choose_supporting(text, primary)
    playbook = PLAYBOOKS[primary]

    recommended_paths = _recommended_paths(primary, supporting)
    requirement = _build_data_requirement(playbook, user_input, supporting)
    analysis_spec = _build_analysis_spec(playbook, user_input, supporting) if has_data and intent.intent_type in {"direct_analysis", "analysis_guidance", "report"} else None

    if not has_data or intent.intent_type == "data_requirement":
        analysis_spec = None

    return PlaybookSelection(
        primary_playbook_id=primary,
        supporting_playbook_ids=supporting,
        selection_reason=_selection_reason(playbook, has_data, supporting),
        recommended_paths=recommended_paths,
        data_requirement=requirement,
        analysis_spec=analysis_spec,
        requires_confirmation=bool(playbook.confirmation_policy.get("requires_confirmation")),
    )


def apply_selection_to_state(state: AnalysisSessionState, selection: PlaybookSelection) -> None:
    paths = selection.recommended_paths
    if paths:
        state.last_recommended_paths = paths
    if selection.data_requirement and state.data_state in {"no_data", "insufficient_data", "unknown"}:
        if not _contains_playbook_artifact(state.data_requirements, selection.primary_playbook_id):
            state.add_data_requirement(selection.data_requirement)
    if selection.analysis_spec and not state.analysis_spec:
        state.set_analysis_spec(selection.analysis_spec)
    if selection.requires_confirmation and selection.analysis_spec:
        confirmation_id = f"method_{selection.primary_playbook_id}"
        if not any(c.get("id") == confirmation_id for c in state.pending_confirmations):
            state.add_confirmation({
                "id": confirmation_id,
                "confirmation_type": selection.analysis_spec.get("confirmation_policy", {}).get("confirmation_type", "method_confirmation"),
                "blocking_reason": selection.analysis_spec.get("confirmation_policy", {}).get("blocking_reason", "method confirmation required"),
                "related_spec_id": selection.analysis_spec.get("id", ""),
                "status": "pending",
            })


def _contains_playbook_artifact(items: list[dict[str, Any]], playbook_id: str) -> bool:
    return any(item.get("playbook_id") == playbook_id for item in items)


def _choose_primary(text: str, intent: TurnIntent, has_data: bool) -> str:
    if _has_any(text, ["funnel", "conversion", "drop-off", "dropoff", "漏斗", "转化"]):
        return "funnel_conversion"
    if _has_any(text, ["evaluate", "evaluation", "effect", "causal", "ab test", "a/b", "worth", "continue operating", "keep operating", "long term operation", "long-term operation", "long-term", "长期运营", "是否值得"]):
        return "evaluation_causal"
    if _has_any(text, ["retention", "churn", "repeat", "lifecycle", "cohort", "keep purchasing", "first order", "purchase again", "留存", "复购", "生命周期"]):
        return "retention_lifecycle"
    if _has_any(text, ["forecast", "predict", "prediction", "roi", "what-if", "simulate", "budget", "预测", "预估"]):
        return "forecast_decision_simulation"
    if _has_any(text, ["decline", "drop", "why", "driver", "decomposition", "attribution", "下降", "为什么", "归因"]):
        return "driver_decomposition"
    if _has_any(text, ["trend", "period", "month", "week", "同比", "环比", "趋势"]):
        return "trend_period_comparison"
    if _has_any(text, ["top", "overview", "summary", "distribution", "概览", "分布", "排名"]):
        return "metric_overview"
    if intent.intent_type == "analysis_guidance" and has_data:
        return "data_understanding"
    return "data_understanding" if has_data else "data_understanding"


def _choose_supporting(text: str, primary: str) -> list[str]:
    supporting: list[str] = []
    if primary == "evaluation_causal":
        supporting.extend(["retention_lifecycle", "forecast_decision_simulation", "metric_overview"])
    elif primary == "forecast_decision_simulation":
        supporting.extend(["trend_period_comparison", "metric_overview"])
    elif primary == "driver_decomposition":
        supporting.extend(["trend_period_comparison", "metric_overview"])
    elif primary == "retention_lifecycle":
        supporting.extend(["metric_overview"])
    elif primary == "data_understanding":
        supporting.extend(["metric_overview", "trend_period_comparison"])
    if _has_any(text, ["roi", "cost", "budget", "成本", "预算"]) and "forecast_decision_simulation" not in supporting and primary != "forecast_decision_simulation":
        supporting.append("forecast_decision_simulation")
    return [sid for sid in supporting if sid != primary]


def _recommended_paths(primary: str, supporting: list[str]) -> list[dict[str, Any]]:
    ids = [primary] + supporting
    return [
        {
            "playbook_id": pid,
            "title": PLAYBOOKS[pid].name,
            "goal": PLAYBOOKS[pid].description,
            "required_capabilities": sorted({step.get("required_capability", "") for step in PLAYBOOKS[pid].method_plan_template if step.get("required_capability")}),
        }
        for pid in ids[:3]
    ]


def _build_data_requirement(playbook: MethodPlaybook, user_input: str, supporting: list[str]) -> dict[str, Any]:
    req = playbook.data_requirements
    must = list(req.get("must_have_data") or [])
    recommended = list(req.get("recommended_data") or [])
    optional = list(req.get("optional_data") or [])
    limitations = list(req.get("missing_limitations") or [])
    for sid in supporting[:2]:
        sreq = PLAYBOOKS[sid].data_requirements
        recommended.extend(x for x in sreq.get("must_have_data", []) if x not in recommended and x not in must)
    return {
        "goal": user_input.strip() or playbook.name,
        "playbook_id": playbook.id,
        "must_have_data": must,
        "recommended_data": recommended,
        "optional_data": optional,
        "missing_limitations": limitations,
        "minimum_viable_analysis": req.get("minimum_viable_data", ""),
    }


def _build_analysis_spec(playbook: MethodPlaybook, user_input: str, supporting: list[str]) -> dict[str, Any]:
    steps = [dict(step) for step in playbook.method_plan_template]
    for sid in supporting[:2]:
        steps.append({
            "step": f"supporting check: {PLAYBOOKS[sid].name}",
            "node_type": "method",
            "required_capability": PLAYBOOKS[sid].method_plan_template[0].get("required_capability", ""),
            "expected_output": PLAYBOOKS[sid].description,
            "evidence_requirements": PLAYBOOKS[sid].evidence_policy.get("required_evidence", [])[:2],
        })
    metrics = _infer_metrics(user_input)
    dimensions = _infer_dimensions(user_input)
    return {
        "goal": user_input.strip() or playbook.name,
        "playbook_id": playbook.id,
        "supporting_playbook_ids": supporting,
        "question_type": playbook.question_types[0] if playbook.question_types else "description",
        "metrics": metrics,
        "dimensions": dimensions,
        "time_scope": "confirm with user or infer from dataset",
        "required_data": playbook.data_requirements.get("must_have_data", []),
        "method_plan": steps,
        "limitations": playbook.limitation_policy.get("required_limitations", []),
        "evidence_policy": playbook.evidence_policy,
        "confirmation_policy": playbook.confirmation_policy,
    }


def _selection_reason(playbook: MethodPlaybook, has_data: bool, supporting: list[str]) -> str:
    base = f"Selected {playbook.id} because it matches {', '.join(playbook.question_types)} analysis."
    if not has_data:
        base += " Data is not loaded, so the playbook is used to produce data requirements first."
    if supporting:
        base += f" Supporting playbooks: {', '.join(supporting)}."
    return base


def _infer_metrics(text: str) -> list[str]:
    metrics = []
    lower = text.lower()
    for term in ("revenue", "income", "roi", "retention", "conversion", "cost", "users", "orders"):
        if term in lower:
            metrics.append(term)
    return metrics or ["target_metric"]


def _infer_dimensions(text: str) -> list[str]:
    dims = []
    lower = text.lower()
    for term in ("channel", "city", "segment", "product", "month", "cohort"):
        if term in lower:
            dims.append(term)
    return dims


def _has_any(text: str, needles: list[str]) -> bool:
    return any(needle.lower() in text for needle in needles)
