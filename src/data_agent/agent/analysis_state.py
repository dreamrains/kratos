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

from data_agent.agent.analysis_plan_contracts import (
    analysis_plan_id_from_mapping,
    normalize_analysis_plan_contract,
)
from data_agent.config import get_config


STAGES = {"discover", "scope", "plan", "execute", "report", "follow_up"}
DATA_STATES = {"no_data", "data_loaded", "insufficient_data", "unknown"}
ACTIVE_MODES = {"consulting", "data_loaded", "analysis", "artifact_review"}
DEFAULT_ACTIVE_SCOPE = {
    "active_dataset": "",
    "active_route": "",
    "active_goal": "",
    "active_mode": "consulting",
    "active_turn_id": "",
    "related_ref_ids": {},
    "updated_at": "",
}


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _normalize_active_scope(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    scope = {
        "active_dataset": "",
        "active_route": "",
        "active_goal": "",
        "active_mode": "consulting",
        "active_turn_id": "",
        "related_ref_ids": {},
        "updated_at": "",
    }
    for key in ("active_dataset", "active_route", "active_goal", "active_turn_id", "updated_at"):
        item = source.get(key)
        if isinstance(item, str):
            scope[key] = item
    mode = source.get("active_mode")
    if mode in ACTIVE_MODES:
        scope["active_mode"] = mode
    related_ref_ids = source.get("related_ref_ids")
    if isinstance(related_ref_ids, dict):
        scope["related_ref_ids"] = {
            key: [item for item in value if isinstance(item, str) and item]
            for key, value in related_ref_ids.items()
            if isinstance(key, str) and isinstance(value, list)
        }
    return scope


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, (int, float, bool)):
        return str(value)
    return ""


def _material_request_identity(value: Any) -> str:
    return " ".join(_text(value).casefold().split())


def _text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        if isinstance(item, dict):
            text = _text(item.get("file_id") or item.get("id") or item.get("filename") or item.get("name"))
        else:
            text = _text(item)
        if text:
            result.append(text)
    return result


def _dict_list_or_empty(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        return []
    return [dict(item) for item in value]


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


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
    data_pool: list[dict[str, Any]] = field(default_factory=list)
    dataset_bundles: list[dict[str, Any]] = field(default_factory=list)
    file_relationships: list[dict[str, Any]] = field(default_factory=list)
    active_bundle_id: str = ""
    analysis_plan: dict[str, Any] | None = None
    evidence_records: list[dict[str, Any]] = field(default_factory=list)
    insight_records: list[dict[str, Any]] = field(default_factory=list)
    dataset_contracts: list[dict[str, Any]] = field(default_factory=list)
    data_understanding_bundles: list[dict[str, Any]] = field(default_factory=list)
    cleaning_logs: list[dict[str, Any]] = field(default_factory=list)
    preview_digests: list[dict[str, Any]] = field(default_factory=list)
    route_proposals: list[dict[str, Any]] = field(default_factory=list)
    verification_reports: list[dict[str, Any]] = field(default_factory=list)
    hypothesis_sets: list[dict[str, Any]] = field(default_factory=list)
    pending_confirmations: list[dict[str, Any]] = field(default_factory=list)
    last_recommended_paths: list[dict[str, Any]] = field(default_factory=list)
    regression_history: list[dict[str, Any]] = field(default_factory=list)
    active_scope: dict[str, Any] = field(default_factory=lambda: _normalize_active_scope(None))
    updated_at: str = field(default_factory=_now)

    @property
    def analysis_spec(self) -> dict[str, Any] | None:
        """Deprecated read-only projection of the canonical analysis plan."""
        return self.analysis_plan

    @classmethod
    def from_dict(cls, data: dict[str, Any], session_id: str) -> "AnalysisSessionState":
        stage = data.get("stage") if data.get("stage") in STAGES else "discover"
        data_state = data.get("data_state") if data.get("data_state") in DATA_STATES else "unknown"
        plan_result = normalize_analysis_plan_contract(
            data.get("analysis_plan") or data.get("analysis_spec"),
            require_executable=False,
        )
        analysis_plan = plan_result.plan if plan_result.ok else None
        return cls(
            session_id=data.get("session_id") or session_id,
            project_name=data.get("project_name"),
            goal=data.get("goal", ""),
            stage=stage,
            data_state=data_state,
            data_requirements=list(data.get("data_requirements") or []),
            data_pool=list(data.get("data_pool") or []),
            dataset_bundles=list(data.get("dataset_bundles") or []),
            file_relationships=list(data.get("file_relationships") or []),
            active_bundle_id=data.get("active_bundle_id") or "",
            analysis_plan=analysis_plan,
            evidence_records=list(data.get("evidence_records") or []),
            insight_records=list(data.get("insight_records") or []),
            dataset_contracts=list(data.get("dataset_contracts") or []),
            data_understanding_bundles=_dict_list_or_empty(data.get("data_understanding_bundles")),
            cleaning_logs=list(data.get("cleaning_logs") or []),
            preview_digests=list(data.get("preview_digests") or []),
            route_proposals=list(data.get("route_proposals") or []),
            verification_reports=list(data.get("verification_reports") or []),
            hypothesis_sets=list(data.get("hypothesis_sets") or []),
            pending_confirmations=list(data.get("pending_confirmations") or []),
            last_recommended_paths=list(data.get("last_recommended_paths") or []),
            regression_history=list(data.get("regression_history") or []),
            active_scope=_normalize_active_scope(data.get("active_scope")),
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
            "data_pool": self.data_pool,
            "dataset_bundles": self.dataset_bundles,
            "file_relationships": self.file_relationships,
            "active_bundle_id": self.active_bundle_id,
            "analysis_plan": self.analysis_plan,
            "evidence_records": self.evidence_records,
            "insight_records": self.insight_records,
            "dataset_contracts": self.dataset_contracts,
            "data_understanding_bundles": self.data_understanding_bundles,
            "cleaning_logs": self.cleaning_logs,
            "preview_digests": self.preview_digests,
            "route_proposals": self.route_proposals,
            "verification_reports": self.verification_reports,
            "hypothesis_sets": self.hypothesis_sets,
            "pending_confirmations": self.pending_confirmations,
            "last_recommended_paths": self.last_recommended_paths,
            "regression_history": self.regression_history,
            "active_scope": _normalize_active_scope(self.active_scope),
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
        """Deprecated callable adapter; new code must call set_analysis_plan."""
        return self.set_analysis_plan(spec)

    def set_analysis_plan(self, plan: dict[str, Any]) -> dict[str, Any]:
        result = normalize_analysis_plan_contract(plan, require_executable=False)
        if not result.ok:
            raise ValueError(result.message)
        item = result.plan
        self.analysis_plan = item
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

    def upsert_evidence_record(self, record: dict[str, Any]) -> dict[str, Any]:
        item = dict(record)
        if not item.get("id"):
            try:
                from data_agent.agent.evidence_contracts import evidence_id_for

                if item.get("plan_id") and item.get("step_id") and item.get("claim_key"):
                    item["id"] = evidence_id_for(item.get("plan_id"), item.get("step_id"), item.get("claim_key"))
            except Exception:
                pass
        item.setdefault("id", uuid.uuid4().hex[:10])
        item_id = item.get("id")
        for index, existing in enumerate(self.evidence_records):
            if existing.get("id") == item_id:
                item.setdefault("created_at", existing.get("created_at") or _now())
                merged = dict(existing)
                merged.update(item)
                self.evidence_records[index] = merged
                self.stage = "execute"
                return merged
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

    def _upsert_ref_by_key(self, collection: list[dict[str, Any]], ref: dict[str, Any], key: str) -> dict[str, Any]:
        item = dict(ref)
        key_value = str(item.get(key) or item.get("id") or "")
        if key_value:
            item[key] = key_value
            item["id"] = key_value
        item.setdefault("id", uuid.uuid4().hex[:10])
        item.setdefault(key, item["id"])
        item.setdefault("created_at", _now())
        for index, existing in enumerate(collection):
            if existing.get(key) == item.get(key) or existing.get("id") == item.get("id"):
                merged = dict(existing)
                merged.update(item)
                collection[index] = merged
                return merged
        collection.append(item)
        return item

    def _active_related_refs(self) -> dict[str, list[str]]:
        related = self.active_scope.get("related_ref_ids")
        if not isinstance(related, dict):
            related = {}
        normalized: dict[str, list[str]] = {}
        for key, value in related.items():
            if isinstance(key, str) and isinstance(value, list):
                normalized[key] = [item for item in value if isinstance(item, str) and item]
        self.active_scope["related_ref_ids"] = normalized
        return normalized

    def _add_active_ref(self, key: str, ref_id: str | None) -> None:
        if not isinstance(ref_id, str) or not ref_id:
            return
        related = self._active_related_refs()
        refs = related.setdefault(key, [])
        if ref_id not in refs:
            refs.append(ref_id)

    def set_active_dataset(self, dataset: str, related_ref_id: str | None = None) -> None:
        self.active_scope = _normalize_active_scope(self.active_scope)
        self.active_scope["active_dataset"] = dataset
        self.active_scope["active_route"] = ""
        self.active_scope["active_mode"] = "data_loaded"
        self.active_scope["updated_at"] = _now()
        self._add_active_ref("dataset_contracts", related_ref_id)

    def set_active_route(
        self,
        route: str,
        goal: str = "",
        dataset: str = "",
        related_ref_id: str | None = None,
    ) -> None:
        self.active_scope = _normalize_active_scope(self.active_scope)
        if dataset:
            self.active_scope["active_dataset"] = dataset
        self.active_scope["active_route"] = route
        self.active_scope["active_goal"] = goal
        self.active_scope["active_mode"] = "analysis"
        self.active_scope["updated_at"] = _now()
        self._add_active_ref("route_proposals", related_ref_id)

    def set_consulting_mode(self, goal: str = "") -> None:
        self.active_scope = _normalize_active_scope(self.active_scope)
        self.active_scope["active_route"] = ""
        self.active_scope["active_goal"] = goal
        self.active_scope["active_mode"] = "consulting"
        self.active_scope["updated_at"] = _now()

    def add_dataset_contract_ref(self, ref: dict[str, Any]) -> dict[str, Any]:
        self.data_state = "data_loaded"
        item = self._upsert_ref(self.dataset_contracts, ref)
        dataset = item.get("dataset")
        if isinstance(dataset, str) and dataset:
            self.set_active_dataset(dataset, related_ref_id=item.get("id"))
        return item

    def add_data_understanding_bundle_ref(self, ref: dict[str, Any]) -> dict[str, Any]:
        item = dict(ref)
        item_id = item.get("id")
        if isinstance(item_id, str) and item_id:
            for index, existing in enumerate(self.data_understanding_bundles):
                if existing.get("id") == item_id:
                    existing_fingerprint = existing.get("data_fingerprint")
                    incoming_fingerprint = item.get("data_fingerprint")
                    if not (
                        isinstance(existing_fingerprint, str)
                        and existing_fingerprint.strip()
                        and isinstance(incoming_fingerprint, str)
                        and incoming_fingerprint.strip()
                    ):
                        raise ValueError(
                            f"Data understanding bundle {item_id!r} requires a non-empty string data_fingerprint on both records."
                        )
                    if existing_fingerprint != incoming_fingerprint:
                        raise ValueError(
                            f"Data understanding bundle {item_id!r} has a different data_fingerprint."
                        )
                    merged = dict(existing)
                    merged.update(item)
                    merged.setdefault("created_at", existing.get("created_at") or _now())
                    self.data_understanding_bundles[index] = merged
                    item = merged
                    break
            else:
                item.setdefault("created_at", _now())
                self.data_understanding_bundles.append(item)
        else:
            item = self._upsert_ref(self.data_understanding_bundles, item)

        self.data_state = "data_loaded"
        dataset = item.get("dataset")
        if isinstance(dataset, str) and dataset:
            self.set_active_dataset(dataset)
        else:
            self.active_scope = _normalize_active_scope(self.active_scope)
            self.active_scope["active_mode"] = "data_loaded"
            self.active_scope["updated_at"] = _now()
        self._add_active_ref("data_understanding_bundles", item.get("id"))
        return item

    def add_cleaning_log_ref(self, ref: dict[str, Any]) -> dict[str, Any]:
        return self._upsert_ref(self.cleaning_logs, ref)

    def add_preview_digest_ref(self, ref: dict[str, Any]) -> dict[str, Any]:
        return self._upsert_ref(self.preview_digests, ref)

    def add_data_pool_file(self, ref: dict[str, Any]) -> dict[str, Any]:
        item = self._upsert_ref_by_key(self.data_pool, ref, "file_id")
        item.setdefault("status", "available")
        return item

    def set_active_bundle(self, bundle: dict[str, Any]) -> dict[str, Any]:
        item = self._upsert_ref_by_key(self.dataset_bundles, bundle, "bundle_id")
        bundle_id = str(item.get("bundle_id") or item.get("id") or "")
        item["bundle_id"] = bundle_id
        self.active_bundle_id = bundle_id
        datasets = item.get("dataset_names") if isinstance(item.get("dataset_names"), list) else []
        if datasets:
            self.set_active_dataset(str(datasets[0]))
            self._add_active_ref("dataset_bundles", bundle_id)
        else:
            self.active_scope = _normalize_active_scope(self.active_scope)
            self.active_scope["active_dataset"] = ""
            self.active_scope["active_route"] = ""
            self.active_scope["active_goal"] = ""
            self.active_scope["active_mode"] = "data_loaded"
            self.active_scope["updated_at"] = _now()
            self._add_active_ref("dataset_bundles", bundle_id)
        return item

    def active_bundle(self) -> dict[str, Any] | None:
        for bundle in self.dataset_bundles:
            if bundle.get("bundle_id") == self.active_bundle_id or bundle.get("id") == self.active_bundle_id:
                return bundle
        return None

    def add_file_relationship(self, relationship: dict[str, Any]) -> dict[str, Any]:
        return self._upsert_ref_by_key(self.file_relationships, relationship, "relationship_id")

    def add_route_proposal_ref(self, ref: dict[str, Any]) -> dict[str, Any]:
        return self._upsert_ref(self.route_proposals, ref)

    def add_verification_report_ref(self, ref: dict[str, Any]) -> dict[str, Any]:
        return self._upsert_ref(self.verification_reports, ref)

    def add_hypothesis_set_ref(self, ref: dict[str, Any]) -> dict[str, Any]:
        return self._upsert_ref(self.hypothesis_sets, ref)

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
                self.apply_state_updates(item.get("state_updates"), answer=answer)
                return item
        return None

    def apply_state_updates(self, updates: Any, answer: Any = None) -> None:
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
        plan_update = updates.get("analysis_plan")
        if not isinstance(plan_update, dict):
            plan_update = updates.get("analysis_spec")
        if isinstance(plan_update, dict):
            resolved_stage = self.stage
            try:
                self.set_analysis_plan(plan_update)
            except ValueError:
                pass
            else:
                self.stage = resolved_stage
        if isinstance(updates.get("method_confirmation"), dict):
            self._apply_method_confirmation(updates["method_confirmation"], _text(answer))

    def _apply_method_confirmation(self, confirmation: dict[str, Any], action: str) -> None:
        plan = dict(self.analysis_plan) if isinstance(self.analysis_plan, dict) else {}
        analysis_plan_id = analysis_plan_id_from_mapping(confirmation)
        playbook_id = _text(confirmation.get("playbook_id"))
        if not analysis_plan_id or analysis_plan_id != _text(plan.get("id")):
            return

        resolution = {
            "analysis_plan_id": analysis_plan_id,
            "playbook_id": playbook_id,
            "request_identity": _material_request_identity(plan.get("goal")),
        }
        if action == "confirm_method":
            resolution["status"] = "approved"
            self.stage = "plan"
        elif action == "clarify_method_scope":
            resolution["status"] = "clarification_required"
            self.stage = "scope"
            clarification_id = f"method_scope_{playbook_id}_{analysis_plan_id}"
            if not any(
                item.get("id") == clarification_id and item.get("status", "pending") == "pending"
                for item in self.pending_confirmations
            ):
                self.add_confirmation({
                    "id": clarification_id,
                    "confirmation_type": "method_scope_clarification",
                    "question": "Please clarify the target metric, time window, or comparison scope, then confirm the method plan.",
                    "options": [
                        {
                            "label": "Use the clarified scope",
                            "value": "confirm_method",
                            "description": "Approve the current method plan with the clarified scope.",
                        },
                        {
                            "label": "Keep clarifying scope",
                            "value": "clarify_method_scope",
                            "description": "Keep analysis execution blocked while the scope is refined.",
                        },
                    ],
                    "blocking_reason": "method scope requires clarification before high-risk analysis",
                    "related_plan_id": analysis_plan_id,
                    # Compatibility for the existing suspension persistence schema.
                    "related_spec_id": analysis_plan_id,
                    "state_updates": {"method_confirmation": dict(confirmation)},
                    "source": "method_scope_clarification",
                })
        else:
            return
        plan["method_confirmation"] = resolution
        resolved_stage = self.stage
        self.set_analysis_plan(plan)
        self.stage = resolved_stage

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


def _compact_trust_refs(items: Any, fields: tuple[str, ...], limit: int = 3) -> list[str]:
    if not isinstance(items, list):
        return []
    lines: list[str] = []
    for index, item in enumerate([i for i in items if isinstance(i, dict)][-limit:], 1):
        parts = []
        for field_name in fields:
            value = item.get(field_name)
            if not isinstance(value, (str, int, float, bool)):
                continue
            if isinstance(value, str) and not value:
                continue
            parts.append(f"{field_name}={value}")
        if parts:
            lines.append(f"{index}. " + ", ".join(parts))
    return lines


def analysis_state_summary(state: AnalysisSessionState | None) -> str:
    if state is None:
        return ""
    from data_agent.agent.confirmation_policy import is_actionable_pending_confirmation

    pending = [
        item for item in state.pending_confirmations
        if is_actionable_pending_confirmation(item)
    ]
    active_scope = _normalize_active_scope(state.active_scope)
    try:
        from data_agent.agent.route_capabilities import build_route_capabilities
    except ImportError:
        recommendation_counts = {}
    else:
        recommendation_counts = build_route_capabilities(state).get("counts") or {}
    lines = [
        f"- session_id: {state.session_id}",
        f"- project_name: {state.project_name or '-'}",
        f"- goal: {state.goal or '-'}",
        f"- stage: {state.stage}",
        f"- data_state: {state.data_state}",
        (
            f"- active_scope: mode={active_scope.get('active_mode') or '-'}, "
            f"dataset={active_scope.get('active_dataset') or '-'}, "
            f"route={active_scope.get('active_route') or '-'}"
        ),
        (
            f"- recommendation_tracks: executable={recommendation_counts.get('executable', 0)}, "
            f"exploratory={recommendation_counts.get('exploratory', 0)}"
        ),
        f"- data_requirements: {len(state.data_requirements)}",
        f"- has_analysis_plan: {bool(state.analysis_plan)}",
        f"- evidence_records: {len(state.evidence_records)}",
        f"- insight_records: {len(state.insight_records)}",
        f"- dataset_contracts: {len(state.dataset_contracts)}",
        f"- data_understanding_bundles: {len(state.data_understanding_bundles)}",
        f"- cleaning_logs: {len(state.cleaning_logs)}",
        f"- preview_digests: {len(state.preview_digests)}",
        f"- route_proposals: {len(state.route_proposals)}",
        f"- verification_reports: {len(state.verification_reports)}",
        f"- hypothesis_sets: {len(state.hypothesis_sets)}",
        f"- pending_confirmations: {len(pending)}",
    ]
    try:
        from data_agent.agent.execution_scope import current_execution_scope
        from data_agent.session.task_manager import task_manager

        execution_scope = current_execution_scope(
            task_manager,
            state.session_id,
            state.project_name,
        )
        if execution_scope.active:
            datasets = ",".join(sorted(execution_scope.allowed_datasets)) or "-"
            lines.append(
                f"- current_task_scope: task_id={execution_scope.task_id}, "
                f"step_id={execution_scope.step_id or '-'}, "
                f"mode={execution_scope.combination_mode or '-'}, datasets={datasets}"
            )
    except Exception:
        pass
    contract_refs = _compact_trust_refs(
        state.dataset_contracts,
        ("id", "dataset", "quality_status"),
    )
    if contract_refs:
        lines.append("- recent_dataset_contracts:\n  " + "\n  ".join(contract_refs))
    route_refs = _compact_trust_refs(
        state.route_proposals,
        ("id", "direction", "budget_level"),
    )
    if route_refs:
        lines.append("- recent_route_proposals:\n  " + "\n  ".join(route_refs))
    verification_refs = _compact_trust_refs(
        state.verification_reports,
        ("id", "overall_status"),
    )
    if verification_refs:
        lines.append("- recent_verification_reports:\n  " + "\n  ".join(verification_refs))
    hypothesis_refs = _compact_trust_refs(
        state.hypothesis_sets,
        ("id", "dataset", "route", "count"),
    )
    if hypothesis_refs:
        lines.append("- recent_hypothesis_sets:\n  " + "\n  ".join(hypothesis_refs))
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
    plan = state.analysis_plan or {}
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
