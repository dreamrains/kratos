"""Session-scoped analysis workflow state.

The state in this module is intentionally lightweight. It gives the agent a
stable memory for analysis planning artifacts without replacing the chat
history or the task system.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from data_agent.config import get_config


STAGES = {"discover", "scope", "plan", "execute", "report", "follow_up"}
DATA_STATES = {"no_data", "data_loaded", "insufficient_data", "unknown"}


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _state_path(session_id: str) -> Path:
    return get_config().sessions_resolved / session_id / "analysis_state.json"


def _insight_record_to_expert_insight(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": record.get("id"),
        "created_at": record.get("created_at"),
        "conclusion": record.get("title") or record.get("conclusion") or "",
        "business_meaning": record.get("summary") or record.get("business_meaning") or "",
        "evidence_ids": list(record.get("evidence_ids") or []),
        "chart_ids": list(record.get("chart_ids") or []),
        "statistical_explanation": record.get("statistical_explanation") or "",
        "limitations": record.get("limitations") or "",
        "recommendation": record.get("recommendation") or "",
        "recommendation_confidence": record.get("recommendation_confidence") or record.get("confidence") or "medium",
        "next_analysis": record.get("next_analysis") or [],
        "presentation_sufficiency": record.get("presentation_sufficiency") or "sufficient",
    }


@dataclass
class AnalysisSessionState:
    session_id: str
    project_name: Optional[str] = None
    goal: str = ""
    stage: str = "discover"
    data_state: str = "unknown"
    data_requirements: list[dict[str, Any]] = field(default_factory=list)
    analysis_objective: dict[str, Any] | None = None
    analysis_plan: dict[str, Any] | None = None
    analysis_spec: dict[str, Any] | None = None
    exploratory_findings: list[dict[str, Any]] = field(default_factory=list)
    validated_findings: list[dict[str, Any]] = field(default_factory=list)
    evidence_records: list[dict[str, Any]] = field(default_factory=list)
    expert_insights: list[dict[str, Any]] = field(default_factory=list)
    insight_records: list[dict[str, Any]] = field(default_factory=list)
    pending_confirmations: list[dict[str, Any]] = field(default_factory=list)
    last_recommended_paths: list[dict[str, Any]] = field(default_factory=list)
    updated_at: str = field(default_factory=_now)

    @classmethod
    def from_dict(cls, data: dict[str, Any], session_id: str) -> "AnalysisSessionState":
        stage = data.get("stage") if data.get("stage") in STAGES else "discover"
        data_state = data.get("data_state") if data.get("data_state") in DATA_STATES else "unknown"
        return cls(
            session_id=data.get("session_id") or session_id,
            project_name=data.get("project_name"),
            goal=data.get("goal", ""),
            stage=stage,
            data_state=data_state,
            data_requirements=list(data.get("data_requirements") or []),
            analysis_objective=data.get("analysis_objective"),
            analysis_plan=data.get("analysis_plan") or data.get("analysis_spec"),
            analysis_spec=data.get("analysis_spec"),
            exploratory_findings=list(data.get("exploratory_findings") or []),
            validated_findings=list(data.get("validated_findings") or []),
            evidence_records=list(data.get("evidence_records") or []),
            expert_insights=list(data.get("expert_insights") or data.get("insight_records") or []),
            insight_records=list(data.get("insight_records") or []),
            pending_confirmations=list(data.get("pending_confirmations") or []),
            last_recommended_paths=list(data.get("last_recommended_paths") or []),
            updated_at=data.get("updated_at") or _now(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "project_name": self.project_name,
            "goal": self.goal,
            "stage": self.stage,
            "data_state": self.data_state,
            "data_requirements": self.data_requirements,
            "analysis_objective": self.analysis_objective,
            "analysis_plan": self.analysis_plan,
            "analysis_spec": self.analysis_spec,
            "exploratory_findings": self.exploratory_findings,
            "validated_findings": self.validated_findings,
            "evidence_records": self.evidence_records,
            "expert_insights": self.expert_insights,
            "insight_records": self.insight_records,
            "pending_confirmations": self.pending_confirmations,
            "last_recommended_paths": self.last_recommended_paths,
            "updated_at": self.updated_at,
        }

    def touch(self) -> None:
        self.updated_at = _now()

    def save(self) -> Path:
        self.touch()
        path = _state_path(self.session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def add_data_requirement(self, requirement: dict[str, Any]) -> dict[str, Any]:
        item = dict(requirement)
        item.setdefault("id", uuid.uuid4().hex[:10])
        item.setdefault("created_at", _now())
        self.data_requirements.append(item)
        self.goal = item.get("goal") or self.goal
        self.stage = "scope"
        return item

    def set_analysis_spec(self, spec: dict[str, Any]) -> dict[str, Any]:
        item = dict(spec)
        item.setdefault("id", uuid.uuid4().hex[:10])
        item.setdefault("created_at", _now())
        self.analysis_spec = item
        self.analysis_plan = item
        if isinstance(item.get("analysis_objective"), dict):
            self.analysis_objective = item["analysis_objective"]
        self.goal = item.get("goal") or self.goal
        self.stage = "plan"
        return item

    def set_analysis_objective(self, objective: dict[str, Any]) -> dict[str, Any]:
        item = dict(objective)
        item.setdefault("id", uuid.uuid4().hex[:10])
        item.setdefault("created_at", _now())
        self.analysis_objective = item
        self.goal = item.get("goal") or self.goal
        self.stage = "scope"
        return item

    def set_analysis_plan(self, plan: dict[str, Any]) -> dict[str, Any]:
        item = dict(plan)
        item.setdefault("id", uuid.uuid4().hex[:10])
        item.setdefault("created_at", _now())
        self.analysis_plan = item
        self.analysis_spec = item
        if isinstance(item.get("analysis_objective"), dict):
            self.analysis_objective = item["analysis_objective"]
        self.goal = item.get("goal") or self.goal
        self.stage = "plan"
        return item

    def add_exploratory_finding(self, finding: dict[str, Any]) -> dict[str, Any]:
        item = dict(finding)
        item.setdefault("id", uuid.uuid4().hex[:10])
        item.setdefault("created_at", _now())
        self.exploratory_findings.append(item)
        self.stage = "execute"
        return item

    def add_validated_finding(self, finding: dict[str, Any]) -> dict[str, Any]:
        item = dict(finding)
        item.setdefault("id", uuid.uuid4().hex[:10])
        item.setdefault("created_at", _now())
        self.validated_findings.append(item)
        self.stage = "execute"
        return item

    def add_evidence_record(self, record: dict[str, Any]) -> dict[str, Any]:
        item = dict(record)
        item.setdefault("id", uuid.uuid4().hex[:10])
        item.setdefault("created_at", _now())
        self.evidence_records.append(item)
        self.stage = "execute"
        return item

    def add_insight_record(self, record: dict[str, Any]) -> dict[str, Any]:
        item = dict(record)
        item.setdefault("id", uuid.uuid4().hex[:10])
        item.setdefault("created_at", _now())
        item.setdefault("output_type", "finding")
        self.insight_records.append(item)
        self.expert_insights.append(_insight_record_to_expert_insight(item))
        self.stage = "execute"
        return item

    def add_expert_insight(self, record: dict[str, Any]) -> dict[str, Any]:
        item = dict(record)
        item.setdefault("id", uuid.uuid4().hex[:10])
        item.setdefault("created_at", _now())
        item.setdefault("presentation_sufficiency", "sufficient")
        self.expert_insights.append(item)
        self.stage = "execute"
        return item

    def add_confirmation(self, confirmation: dict[str, Any]) -> dict[str, Any]:
        item = dict(confirmation)
        item.setdefault("id", uuid.uuid4().hex[:10])
        item.setdefault("created_at", _now())
        item.setdefault("status", "pending")
        self.pending_confirmations.append(item)
        return item

    def resolve_confirmation(self, confirmation_id: str, answer: str) -> dict[str, Any] | None:
        for item in self.pending_confirmations:
            if item.get("id") == confirmation_id or item.get("suspension_id") == confirmation_id:
                item["status"] = "resolved"
                item["answer"] = answer
                item["resolved_at"] = _now()
                self.apply_state_updates(item.get("state_updates"))
                return item
        return None

    def apply_state_updates(self, updates: Any) -> None:
        if isinstance(updates, str) and updates.strip():
            try:
                updates = json.loads(updates)
            except json.JSONDecodeError:
                return
        if not isinstance(updates, dict):
            return
        for key in ("goal", "stage", "data_state", "last_recommended_paths"):
            if key in updates:
                value = updates[key]
                if key == "stage" and value not in STAGES:
                    continue
                if key == "data_state" and value not in DATA_STATES:
                    continue
                setattr(self, key, value)
        if "analysis_spec" in updates and isinstance(updates["analysis_spec"], dict):
            self.analysis_spec = updates["analysis_spec"]


def load_analysis_state(session_id: str, project_name: Optional[str] = None) -> AnalysisSessionState:
    path = _state_path(session_id)
    if path.exists():
        try:
            state = AnalysisSessionState.from_dict(json.loads(path.read_text(encoding="utf-8")), session_id)
        except (json.JSONDecodeError, OSError):
            state = AnalysisSessionState(session_id=session_id)
    else:
        state = AnalysisSessionState(session_id=session_id)
    if project_name and state.project_name != project_name:
        state.project_name = project_name
    return state


def reset_analysis_state(session_id: str, project_name: Optional[str] = None) -> AnalysisSessionState:
    path = _state_path(session_id)
    path.unlink(missing_ok=True)
    state = AnalysisSessionState(session_id=session_id, project_name=project_name)
    state.save()
    return state


def current_analysis_state() -> AnalysisSessionState | None:
    try:
        from data_agent.agent.context import get_current_context
        ctx = get_current_context()
        if ctx is None:
            return None
        if getattr(ctx, "analysis_state", None) is None:
            ctx.analysis_state = load_analysis_state(ctx.session_id, ctx.project_name)
        return ctx.analysis_state
    except Exception:
        return None


def analysis_state_summary(state: AnalysisSessionState | None) -> str:
    if state is None:
        return ""
    pending = [c for c in state.pending_confirmations if c.get("status") == "pending"]
    lines = [
        f"- session_id: {state.session_id}",
        f"- project_name: {state.project_name or '-'}",
        f"- goal: {state.goal or '-'}",
        f"- stage: {state.stage}",
        f"- data_state: {state.data_state}",
        f"- data_requirements: {len(state.data_requirements)}",
        f"- has_analysis_objective: {bool(state.analysis_objective)}",
        f"- has_analysis_plan: {bool(state.analysis_plan)}",
        f"- has_analysis_spec: {bool(state.analysis_spec)}",
        f"- exploratory_findings: {len(state.exploratory_findings)}",
        f"- validated_findings: {len(state.validated_findings)}",
        f"- evidence_records: {len(state.evidence_records)}",
        f"- expert_insights: {len(state.expert_insights)}",
        f"- insight_records: {len(state.insight_records)}",
        f"- pending_confirmations: {len(pending)}",
    ]
    if state.last_recommended_paths:
        paths = []
        for i, path in enumerate(state.last_recommended_paths[:3], 1):
            if isinstance(path, dict):
                paths.append(f"{i}. {path.get('title') or path.get('name') or path.get('goal') or path}")
            else:
                paths.append(f"{i}. {path}")
        lines.append("- last_recommended_paths:\n  " + "\n  ".join(paths))
    return "\n".join(lines)


def analysis_completeness_summary(state: AnalysisSessionState | None, require_charts: bool = False) -> dict[str, Any]:
    """Compatibility summary for older callers.

    ``require_charts`` is intentionally ignored. Chart presence is no longer a
    hard quality gate; use ``analysis_quality_summary`` for the expert flow.
    """
    if state is None:
        return {"status": "incomplete", "missing": ["analysis_state"], "counts": {}}

    records = list(state.evidence_records or [])
    insights = list(state.insight_records or [])
    missing: list[str] = []

    if not records:
        missing.append("evidence_records")
    if any(record.get("statistical_detail_status") == "missing" for record in records):
        missing.append("statistical_details")
    if not insights:
        missing.append("expert_synthesis")

    return {
        "status": "complete" if not missing else "incomplete",
        "missing": sorted(set(missing)),
        "counts": {
            "evidence_records": len(records),
            "insight_records": len(insights),
        },
    }


def analysis_quality_summary(state: AnalysisSessionState | None) -> dict[str, Any]:
    """Evaluate whether the analysis is ready for expert-facing output."""
    if state is None:
        return {"status": "incomplete_can_continue", "missing": ["analysis_state"], "counts": {}}

    missing: list[str] = []
    objective = state.analysis_objective or {}
    plan = state.analysis_plan or state.analysis_spec or {}
    exploratory = list(state.exploratory_findings or [])
    validated = list(state.validated_findings or [])
    evidence = list(state.evidence_records or [])
    insights = list(state.expert_insights or [])

    if not objective:
        missing.append("analysis_objective")
    if not plan:
        missing.append("analysis_plan")
    if not exploratory and not plan.get("exploration_not_needed_reason"):
        missing.append("exploratory_findings")
    if not validated:
        missing.append("validated_findings")
    if not evidence:
        missing.append("evidence_records")
    if not insights:
        missing.append("expert_insights")

    if any(record.get("statistical_detail_status") == "missing" for record in evidence):
        missing.append("statistical_details")

    for record in evidence:
        if record.get("sample_size") in (None, "", [], {}):
            missing.append("sample_size")
        if record.get("time_scope") in (None, "", [], {}):
            missing.append("time_scope")
        if record.get("calculation_method") in (None, "", [], {}):
            missing.append("calculation_method")
        if record.get("method_detail") in (None, "", [], {}):
            missing.append("method_detail")

    if objective.get("requires_counterfactual"):
        counterfactual_fields = ("counterfactual_check", "control_group_check", "causal_boundary")
        has_explicit_counterfactual_check = any(
            item.get(key) not in (None, "", [], {})
            for item in [plan, *validated, *evidence, *insights]
            for key in counterfactual_fields
        )
        if not has_explicit_counterfactual_check:
            missing.append("counterfactual_check")

    for insight in insights:
        if not insight.get("business_meaning"):
            missing.append("business_meaning")
        if insight.get("recommendation_confidence") not in {"high", "medium", "low"}:
            missing.append("recommendation_confidence")
        if not insight.get("next_analysis"):
            missing.append("next_analysis")
        if insight.get("presentation_sufficiency") not in {"sufficient", "not_needed"}:
            missing.append("presentation_sufficiency")

    status = "complete"
    unique_missing = sorted(set(missing))
    if unique_missing:
        limited_markers = ("data_limited", "not_applicable", "cannot_validate")
        validation_limited = any(str(item.get("validation_status", "")).lower() in limited_markers for item in validated)
        status = "incomplete_data_limited" if validation_limited else "incomplete_can_continue"

    return {
        "status": status,
        "missing": unique_missing,
        "counts": {
            "exploratory_findings": len(exploratory),
            "validated_findings": len(validated),
            "evidence_records": len(evidence),
            "expert_insights": len(insights),
        },
    }
