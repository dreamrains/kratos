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
    analysis_spec: dict[str, Any] | None = None
    evidence_records: list[dict[str, Any]] = field(default_factory=list)
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
            analysis_spec=data.get("analysis_spec"),
            evidence_records=list(data.get("evidence_records") or []),
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
            "analysis_spec": self.analysis_spec,
            "evidence_records": self.evidence_records,
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
        f"- has_analysis_spec: {bool(state.analysis_spec)}",
        f"- evidence_records: {len(state.evidence_records)}",
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
