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




@dataclass
class AnalysisSessionState:
    session_id: str
    project_name: Optional[str] = None
    goal: str = ""
    stage: str = "discover"
    data_state: str = "unknown"
    data_requirements: list[dict[str, Any]] = field(default_factory=list)
    analysis_plan: dict[str, Any] | None = None
    analysis_spec: dict[str, Any] | None = None
    evidence_records: list[dict[str, Any]] = field(default_factory=list)
    insight_records: list[dict[str, Any]] = field(default_factory=list)
    dataset_contracts: list[dict[str, Any]] = field(default_factory=list)
    cleaning_logs: list[dict[str, Any]] = field(default_factory=list)
    preview_digests: list[dict[str, Any]] = field(default_factory=list)
    route_proposals: list[dict[str, Any]] = field(default_factory=list)
    verification_reports: list[dict[str, Any]] = field(default_factory=list)
    pending_confirmations: list[dict[str, Any]] = field(default_factory=list)
    last_recommended_paths: list[dict[str, Any]] = field(default_factory=list)
    regression_history: list[dict[str, Any]] = field(default_factory=list)
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
            analysis_plan=data.get("analysis_plan") or data.get("analysis_spec"),
            analysis_spec=data.get("analysis_spec"),
            evidence_records=list(data.get("evidence_records") or []),
            insight_records=list(data.get("insight_records") or []),
            dataset_contracts=list(data.get("dataset_contracts") or []),
            cleaning_logs=list(data.get("cleaning_logs") or []),
            preview_digests=list(data.get("preview_digests") or []),
            route_proposals=list(data.get("route_proposals") or []),
            verification_reports=list(data.get("verification_reports") or []),
            pending_confirmations=list(data.get("pending_confirmations") or []),
            last_recommended_paths=list(data.get("last_recommended_paths") or []),
            regression_history=list(data.get("regression_history") or []),
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
            "analysis_plan": self.analysis_plan,
            "analysis_spec": self.analysis_spec,
            "evidence_records": self.evidence_records,
            "insight_records": self.insight_records,
            "dataset_contracts": self.dataset_contracts,
            "cleaning_logs": self.cleaning_logs,
            "preview_digests": self.preview_digests,
            "route_proposals": self.route_proposals,
            "verification_reports": self.verification_reports,
            "pending_confirmations": self.pending_confirmations,
            "last_recommended_paths": self.last_recommended_paths,
            "regression_history": self.regression_history,
            "updated_at": self.updated_at,
        }

    def touch(self) -> None:
        self.updated_at = _now()

    def check_regression_triggers(self, tool_name: str, tool_result: str) -> str | None:
        """Check if a tool result signals need to regress to an earlier stage.

        Returns a regression message if regression occurred, None otherwise.
        """
        result_lower = (tool_result or "").lower()
        old_stage = self.stage

        # Data quality blocks → regress to scope
        if tool_name in ("detect_data_quality", "quick_profile"):
            if '"severity": "block"' in result_lower or '"severity":"block"' in result_lower:
                if self.stage in ("plan", "execute"):
                    self.stage = "scope"
                    self._record_regression(old_stage, "scope", "数据质量问题严重，需要重新定义分析范围", tool_name)
                    return "数据质量问题严重，需要重新定义分析范围"
            if "缺失率" in result_lower and ("80%" in result_lower or "90%" in result_lower):
                if self.stage in ("plan", "execute"):
                    self.stage = "scope"
                    self._record_regression(old_stage, "scope", "关键列缺失率过高，需要确认数据可用性", tool_name)
                    return "关键列缺失率过高，需要确认数据可用性"

        # Insufficient data for chosen method → regress to plan
        if any(kw in result_lower for kw in ("insufficient", "数据点太少", "not enough data", "样本不足")):
            if self.stage == "execute":
                self.stage = "plan"
                self._record_regression(old_stage, "plan", "数据不支持当前分析方法，需要调整分析计划", tool_name)
                return "数据不支持当前分析方法，需要调整分析计划"

        # Analysis result contradicts assumptions → regress to plan
        if tool_name in ("analyze_time_series", "correlation_analysis", "compare_periods"):
            if '"error"' in result_lower and self.stage == "execute":
                self.stage = "plan"
                self._record_regression(old_stage, "plan", "分析工具执行失败，需要重新规划分析方法", tool_name)
                return "分析工具执行失败，需要重新规划分析方法"

        return None

    def _record_regression(self, from_stage: str, to_stage: str, reason: str, trigger_tool: str) -> None:
        self.regression_history.append({
            "from_stage": from_stage,
            "to_stage": to_stage,
            "reason": reason,
            "trigger_tool": trigger_tool,
            "timestamp": _now(),
        })

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
        self.goal = item.get("goal") or self.goal
        self.stage = "plan"
        return item

    def set_analysis_plan(self, plan: dict[str, Any]) -> dict[str, Any]:
        item = dict(plan)
        item.setdefault("id", uuid.uuid4().hex[:10])
        item.setdefault("created_at", _now())
        self.analysis_plan = item
        self.analysis_spec = item
        self.goal = item.get("goal") or self.goal
        self.stage = "plan"
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
        self.stage = "execute"
        return item

    def _upsert_ref(self, collection: list[dict[str, Any]], ref: dict[str, Any]) -> dict[str, Any]:
        item = dict(ref)
        item.setdefault("id", uuid.uuid4().hex[:10])
        item.setdefault("created_at", _now())
        item_id = item.get("id")
        if item_id is not None:
            for index, existing in enumerate(collection):
                if existing.get("id") == item_id:
                    collection[index] = item
                    return item
        collection.append(item)
        return item

    def add_dataset_contract_ref(self, ref: dict[str, Any]) -> dict[str, Any]:
        self.data_state = "data_loaded"
        return self._upsert_ref(self.dataset_contracts, ref)

    def add_cleaning_log_ref(self, ref: dict[str, Any]) -> dict[str, Any]:
        return self._upsert_ref(self.cleaning_logs, ref)

    def add_preview_digest_ref(self, ref: dict[str, Any]) -> dict[str, Any]:
        return self._upsert_ref(self.preview_digests, ref)

    def add_route_proposal_ref(self, ref: dict[str, Any]) -> dict[str, Any]:
        return self._upsert_ref(self.route_proposals, ref)

    def add_verification_report_ref(self, ref: dict[str, Any]) -> dict[str, Any]:
        return self._upsert_ref(self.verification_reports, ref)

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
        f"- has_analysis_plan: {bool(state.analysis_plan)}",
        f"- has_analysis_spec: {bool(state.analysis_spec)}",
        f"- evidence_records: {len(state.evidence_records)}",
        f"- insight_records: {len(state.insight_records)}",
        f"- dataset_contracts: {len(state.dataset_contracts)}",
        f"- cleaning_logs: {len(state.cleaning_logs)}",
        f"- preview_digests: {len(state.preview_digests)}",
        f"- route_proposals: {len(state.route_proposals)}",
        f"- verification_reports: {len(state.verification_reports)}",
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
    if state.regression_history:
        last = state.regression_history[-1]
        lines.append(f"- last_regression: {last.get('from_stage')} → {last.get('to_stage')} ({last.get('reason')})")
    return "\n".join(lines)


def analysis_completeness_summary(state: AnalysisSessionState | None, require_charts: bool = False) -> dict[str, Any]:
    """Compatibility summary for older callers.

    ``require_charts`` is intentionally ignored. Chart presence is no longer a
    hard quality gate; use ``analysis_quality_summary`` for the expert flow.
    """
    if state is None:
        return {"status": "incomplete", "missing": ["analysis_state"], "counts": {}}

    records = list(state.evidence_records or [])
    missing: list[str] = []

    if not records:
        missing.append("evidence_records")
    if any(record.get("statistical_detail_status") == "missing" for record in records):
        missing.append("statistical_details")

    return {
        "status": "complete" if not missing else "incomplete",
        "missing": sorted(set(missing)),
        "counts": {
            "evidence_records": len(records),
        },
    }


def analysis_quality_summary(state: AnalysisSessionState | None) -> dict[str, Any]:
    """Evaluate whether the analysis is ready for expert-facing output."""
    if state is None:
        return {"status": "incomplete_can_continue", "missing": ["analysis_state"], "counts": {}}

    missing: list[str] = []
    plan = state.analysis_plan or state.analysis_spec or {}
    evidence = list(state.evidence_records or [])

    if not evidence:
        missing.append("evidence_records")

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

    status = "complete"
    unique_missing = sorted(set(missing))
    if unique_missing:
        status = "incomplete_can_continue"

    return {
        "status": status,
        "missing": unique_missing,
        "counts": {
            "analysis_plan": 1 if plan else 0,
            "evidence_records": len(evidence),
        },
    }
