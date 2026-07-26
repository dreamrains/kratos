"""Session-scoped analysis workflow state.

The state in this module is intentionally lightweight. It gives the agent a
stable memory for analysis planning artifacts without replacing the chat
history or the task system.
"""

from __future__ import annotations

import hashlib
import json
import re
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


def _analysis_requirement_inputs(
    plan: Any,
    *,
    dataset_contracts: list[dict[str, Any]],
    route_proposals: list[dict[str, Any]],
    active_scope: dict[str, Any],
    goal: str,
) -> dict[str, Any]:
    plan_value = plan if isinstance(plan, dict) else {}
    route_name = _text(plan_value.get("route")) or _text(active_scope.get("active_route"))
    route: dict[str, Any] | str | None = route_name or None
    for proposal in route_proposals:
        if not isinstance(proposal, dict):
            continue
        direction = _text(proposal.get("direction") or proposal.get("route"))
        proposal_id = _text(proposal.get("id"))
        if route_name and route_name in {direction, proposal_id}:
            route = proposal
            break

    playbook = None
    playbook_id = _text(plan_value.get("playbook_id"))
    if playbook_id:
        from data_agent.agent.method_playbooks import get_playbook

        playbook = get_playbook(playbook_id)
    return {
        "dataset_contracts": list(dataset_contracts or []),
        "route": route,
        "playbook": playbook,
        "user_intent": plan_value.get("goal") or goal,
    }


def _state_path(session_id: str) -> Path:
    return get_config().sessions_resolved / session_id / "analysis_state.json"




@dataclass
class AnalysisSessionState:
    session_id: str
    project_name: Optional[str] = None
    goal: str = ""
    explicit_user_requirements: str = ""
    stage: str = "discover"
    data_state: str = "unknown"
    data_requirements: list[dict[str, Any]] = field(default_factory=list)
    data_pool: list[dict[str, Any]] = field(default_factory=list)
    dataset_bundles: list[dict[str, Any]] = field(default_factory=list)
    file_relationships: list[dict[str, Any]] = field(default_factory=list)
    active_bundle_id: str = ""
    analysis_plan: dict[str, Any] | None = None
    computation_refs: list[dict[str, Any]] = field(default_factory=list)
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
    budget_diagnostics: dict[str, Any] = field(default_factory=dict)
    last_recommended_paths: list[dict[str, Any]] = field(default_factory=list)
    regression_history: list[dict[str, Any]] = field(default_factory=list)
    active_scope: dict[str, Any] = field(default_factory=lambda: _normalize_active_scope(None))
    updated_at: str = field(default_factory=_now)
    turn_diagnostics: list[dict[str, Any]] = field(default_factory=list)

    def append_turn_diagnostic(self, diagnostic: dict[str, Any], *, limit: int = 20) -> None:
        """Record a bounded provenance diagnostic for the current turn.

        Each entry captures envelope/binding/failure identity only — no raw
        rows or unbounded tool output — to keep memory bounded for replay.
        """

        if not isinstance(diagnostic, dict):
            return
        merged = list(self.turn_diagnostics or [])
        merged.append(dict(diagnostic))
        self.turn_diagnostics = merged[-limit:]

    @property
    def analysis_spec(self) -> dict[str, Any] | None:
        """Deprecated read-only projection of the canonical analysis plan."""
        return self.analysis_plan

    @classmethod
    def from_dict(cls, data: dict[str, Any], session_id: str) -> "AnalysisSessionState":
        stage = data.get("stage") if data.get("stage") in STAGES else "discover"
        data_state = data.get("data_state") if data.get("data_state") in DATA_STATES else "unknown"
        dataset_contracts = list(data.get("dataset_contracts") or [])
        route_proposals = list(data.get("route_proposals") or [])
        active_scope = _normalize_active_scope(data.get("active_scope"))
        raw_plan = data.get("analysis_plan") or data.get("analysis_spec")
        plan_result = normalize_analysis_plan_contract(
            raw_plan,
            require_executable=False,
            _legacy_saved_plan_loading=True,
            **_analysis_requirement_inputs(
                raw_plan,
                dataset_contracts=dataset_contracts,
                route_proposals=route_proposals,
                active_scope=active_scope,
                goal=data.get("goal", ""),
            ),
        )
        analysis_plan = plan_result.plan if plan_result.ok else None
        evidence_records = []
        for raw_record in data.get("evidence_records") or []:
            if not isinstance(raw_record, dict):
                continue
            record = dict(raw_record)
            if record.get("contract_version") != "evidence_record.v2":
                record["provenance_status"] = "legacy_unbound"
                record["verification_level"] = "legacy_unbound"
            evidence_records.append(record)
        return cls(
            session_id=data.get("session_id") or session_id,
            project_name=data.get("project_name"),
            goal=data.get("goal", ""),
            explicit_user_requirements=_text(data.get("explicit_user_requirements")),
            stage=stage,
            data_state=data_state,
            data_requirements=list(data.get("data_requirements") or []),
            data_pool=list(data.get("data_pool") or []),
            dataset_bundles=list(data.get("dataset_bundles") or []),
            file_relationships=list(data.get("file_relationships") or []),
            active_bundle_id=data.get("active_bundle_id") or "",
            analysis_plan=analysis_plan,
            computation_refs=_dict_list_or_empty(data.get("computation_refs")),
            evidence_records=evidence_records,
            insight_records=list(data.get("insight_records") or []),
            dataset_contracts=dataset_contracts,
            data_understanding_bundles=_dict_list_or_empty(data.get("data_understanding_bundles")),
            cleaning_logs=list(data.get("cleaning_logs") or []),
            preview_digests=list(data.get("preview_digests") or []),
            route_proposals=route_proposals,
            verification_reports=list(data.get("verification_reports") or []),
            hypothesis_sets=list(data.get("hypothesis_sets") or []),
            pending_confirmations=list(data.get("pending_confirmations") or []),
            budget_diagnostics=(
                dict(data.get("budget_diagnostics"))
                if isinstance(data.get("budget_diagnostics"), dict)
                else {}
            ),
            last_recommended_paths=list(data.get("last_recommended_paths") or []),
            regression_history=list(data.get("regression_history") or []),
            active_scope=active_scope,
            updated_at=data.get("updated_at") or _now(),
            turn_diagnostics=[
                dict(item)
                for item in (data.get("turn_diagnostics") or [])
                if isinstance(item, dict)
            ],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "project_name": self.project_name,
            "goal": self.goal,
            "explicit_user_requirements": self.explicit_user_requirements,
            "stage": self.stage,
            "data_state": self.data_state,
            "data_requirements": self.data_requirements,
            "data_pool": self.data_pool,
            "dataset_bundles": self.dataset_bundles,
            "file_relationships": self.file_relationships,
            "active_bundle_id": self.active_bundle_id,
            "analysis_plan": self.analysis_plan,
            "computation_refs": self.computation_refs,
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
            "budget_diagnostics": self.budget_diagnostics,
            "last_recommended_paths": self.last_recommended_paths,
            "regression_history": self.regression_history,
            "active_scope": _normalize_active_scope(self.active_scope),
            "updated_at": self.updated_at,
            "turn_diagnostics": self.turn_diagnostics,
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
        result = normalize_analysis_plan_contract(
            plan,
            require_executable=False,
            **self.analysis_requirement_inputs(plan),
        )
        if not result.ok:
            raise ValueError(result.message)
        item = result.plan
        self.analysis_plan = item
        self.goal = item.get("goal") or self.goal
        self.stage = "plan"
        return item

    def analysis_requirement_inputs(self, plan: dict[str, Any]) -> dict[str, Any]:
        """Resolve state artifacts that are inputs to the canonical compiler."""

        return _analysis_requirement_inputs(
            plan,
            dataset_contracts=self.dataset_contracts,
            route_proposals=self.route_proposals,
            active_scope=self.active_scope,
            goal=self.goal,
        )

    def add_evidence_record(self, record: dict[str, Any]) -> dict[str, Any]:
        item = dict(record)
        item.setdefault("id", uuid.uuid4().hex[:10])
        item.setdefault("created_at", _now())
        self.evidence_records.append(item)
        self.stage = "execute"
        return item

    def upsert_computation_ref(self, ref: dict[str, Any]) -> dict[str, Any]:
        """Keep one compact, server-produced reference per turn/tool call."""
        item = dict(ref)
        identity = (str(item.get("turn_id") or ""), str(item.get("tool_call_id") or ""))
        for index, existing in enumerate(self.computation_refs):
            existing_identity = (
                str(existing.get("turn_id") or ""),
                str(existing.get("tool_call_id") or ""),
            )
            if existing_identity == identity:
                self.computation_refs[index] = item
                return item
        self.computation_refs.append(item)
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


def _capsule_text(value: Any, max_chars: int = 1_200) -> str:
    text = _text(value)
    return text if len(text) <= max_chars else text[: max_chars - 1] + "…"


def _capsule_identity(value: Any, max_chars: int = 320) -> str:
    """Keep ordinary IDs exact and retain an exact digest identity for pathological values."""

    text = _text(value)
    if len(text) <= max_chars:
        return text
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _capsule_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return sorted({_text(item) for item in value if _text(item)})
    text = _text(value)
    return [text] if text else []


def _flatten_plan_requirements(plan: dict[str, Any]) -> list[dict[str, Any]]:
    grouped = plan.get("analysis_requirements")
    if not isinstance(grouped, dict):
        return []
    return [
        dict(item)
        for step_id in sorted(grouped)
        for item in (grouped.get(step_id) or [])
        if isinstance(item, dict)
    ]


def _dataset_capsule_entries(
    state: AnalysisSessionState,
    active_datasets: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    collections = (
        state.data_pool,
        state.dataset_contracts,
        state.data_understanding_bundles,
        active_datasets or [],
    )
    for collection in collections:
        for item in collection or []:
            if not isinstance(item, dict):
                continue
            candidates = item.get("datasets") if isinstance(item.get("datasets"), list) else [item]
            for candidate in candidates:
                if not isinstance(candidate, dict):
                    continue
                name = _text(
                    candidate.get("dataset")
                    or candidate.get("dataset_name")
                    or candidate.get("name")
                )
                raw_fingerprint = _text(
                    candidate.get("raw_fingerprint") or candidate.get("data_fingerprint")
                )
                source_fingerprint = _text(candidate.get("source_fingerprint"))
                raw_dataset_id = _text(candidate.get("raw_dataset_id"))
                versions = _capsule_list(
                    candidate.get("dataset_versions")
                    or candidate.get("dataset_version_ids")
                    or candidate.get("dataset_version_id")
                    or candidate.get("data_version")
                    or candidate.get("dataset_id")
                )
                if not any((name, versions, raw_fingerprint, source_fingerprint)):
                    continue
                key = (name, raw_fingerprint, source_fingerprint)
                entry = grouped.setdefault(key, {
                    "name": name,
                    "version_ids": [],
                    "raw_fingerprint": raw_fingerprint,
                    "source_fingerprint": source_fingerprint,
                })
                if raw_dataset_id:
                    entry["raw_dataset_id"] = raw_dataset_id
                entry["version_ids"] = sorted(set(entry["version_ids"]) | set(versions))
    return [grouped[key] for key in sorted(grouped)]


def _computation_digests(record: dict[str, Any]) -> list[str]:
    digests: set[str] = set()
    refs = record.get("computation_refs")
    if isinstance(refs, list):
        for ref in refs:
            if not isinstance(ref, dict):
                continue
            digest = _text(
                ref.get("output_digest")
                or ref.get("artifact_digest")
                or ref.get("envelope_digest")
                or ref.get("digest")
            )
            if digest:
                digests.add(digest)
    return sorted(digests)


def _active_confirmation_capsule(
    state: AnalysisSessionState,
    override: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    from data_agent.agent.confirmation_policy import is_actionable_pending_confirmation

    if isinstance(override, dict) and override:
        item = override
    else:
        pending = [
            item for item in state.pending_confirmations
            if is_actionable_pending_confirmation(item)
        ]
        if not pending:
            return None
        item = pending[-1]
    proposal = item.get("proposal_ref")
    if not isinstance(proposal, dict):
        proposal = item.get("resolution_params")
    if not isinstance(proposal, dict):
        proposal = {}
    return {
        "id": _text(item.get("confirmation_id") or item.get("id") or item.get("suspension_id")),
        "version": item.get("version"),
        "proposal_id": _text(proposal.get("proposal_id") or item.get("proposal_id")),
        "candidate_fingerprint": _text(
            proposal.get("candidate_fingerprint") or item.get("candidate_fingerprint")
        ),
        "data_version": _text(proposal.get("data_version") or item.get("data_version")),
        "spec_version": _text(proposal.get("spec_version") or item.get("spec_version")),
    }


def _latest_audit_capsule(state: AnalysisSessionState) -> dict[str, Any] | None:
    ref = next((
        item for item in reversed(state.verification_reports)
        if isinstance(item, dict)
        and item.get("contract_version") == "final_answer_audit.v1"
    ), None)
    if ref is None:
        return None
    audit = ref
    if ref.get("artifact_path"):
        try:
            from data_agent.agent.trust_workflow_runtime import hydrate_final_answer_audit_ref

            hydrated = hydrate_final_answer_audit_ref(ref)
            if isinstance(hydrated, dict):
                audit = hydrated
        except Exception:
            pass
    blockers: set[str] = set()
    actions: list[dict[str, Any]] = []
    for check in audit.get("claim_checks") or []:
        if not isinstance(check, dict) or check.get("status") not in {"failed", "downgraded"}:
            continue
        blockers.update(_capsule_list(check.get("reason_codes")))
        action = check.get("safe_action")
        if isinstance(action, dict):
            selected_keys = [
                key for key in ("action", "target_claim_class", "required_disclosure")
                if key in action
            ] or [key for key, _ in sorted(action.items())[:1]]
            bounded_action = {
                str(key): _text(action.get(key))
                for key in selected_keys
                for value in [action.get(key)]
                if isinstance(value, (str, int, float, bool)) and _text(value)
            }
            if bounded_action and bounded_action not in actions:
                actions.append(bounded_action)
    return {
        "id": _text(ref.get("id") or audit.get("id")),
        "status": _text(ref.get("status") or audit.get("status") or "blocked"),
        "blockers": sorted(blockers),
        "permitted_downgrade_actions": actions,
    }


def render_trust_capsule(capsule: dict[str, Any]) -> str:
    """Return the canonical compact JSON representation used in prompts."""

    return json.dumps(capsule, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def build_trust_capsule(
    state: AnalysisSessionState | None,
    *,
    user_requirements: str = "",
    active_confirmation: dict[str, Any] | None = None,
    active_datasets: list[dict[str, Any]] | None = None,
    max_items_per_component: int = 24,
    max_chars: int = 8_000,
) -> dict[str, Any]:
    """Build bounded deterministic identity memory for assurance-critical state."""

    if state is None:
        body: dict[str, Any] = {
            "contract_version": "trust_capsule.v1",
            "goal": "",
            "explicit_user_requirements": _capsule_text(user_requirements),
            "plan": {"id": "", "contract_version": ""},
            "datasets": [],
            "unresolved_hard_requirements": [],
            "evidence_bindings": [],
            "active_confirmation": None,
            "latest_audit": None,
            "truncation": {},
        }
    else:
        plan = state.analysis_plan if isinstance(state.analysis_plan, dict) else {}
        hard_requirements = [
            {
                "id": _text(item.get("id")),
                "unmet_action": _text(item.get("unmet_action")),
            }
            for item in _flatten_plan_requirements(plan)
            if item.get("status") != "satisfied"
            and item.get("necessity") == "required"
            and item.get("unmet_action") in {"block_analysis", "block_claim"}
            and _text(item.get("id"))
        ]
        evidence_bindings = [
            {
                "id": _text(item.get("id")),
                "verification_level": _text(item.get("verification_level")),
                "computation_ref_digests": _computation_digests(item),
            }
            for item in state.evidence_records
            if isinstance(item, dict) and _text(item.get("id"))
        ]
        body = {
            "contract_version": "trust_capsule.v1",
            "goal": _text(state.goal),
            "explicit_user_requirements": _text(
                user_requirements or state.explicit_user_requirements
            ),
            "plan": {
                "id": _text(plan.get("id")),
                "contract_version": _text(plan.get("contract_version")),
            },
            "datasets": _dataset_capsule_entries(state, active_datasets),
            "unresolved_hard_requirements": sorted(hard_requirements, key=lambda item: item["id"]),
            "evidence_bindings": sorted(evidence_bindings, key=lambda item: item["id"]),
            "active_confirmation": _active_confirmation_capsule(state, active_confirmation),
            "latest_audit": _latest_audit_capsule(state),
            "truncation": {},
        }

    encoded_body = render_trust_capsule(body)
    body_digest = hashlib.sha256(encoded_body.encode("utf-8")).hexdigest()
    result = {**body, "status": "ready", "digest": body_digest}
    maximum = int(max_chars)
    if maximum < 1_000:
        raise ValueError("trust_capsule_minimum_budget_too_small")
    limit = max(1, int(max_items_per_component))
    component_overflow = any(
        len(body[key]) > limit
        for key in ("datasets", "unresolved_hard_requirements", "evidence_bindings")
    )
    if not component_overflow and len(render_trust_capsule(result)) <= maximum:
        return result

    manifest_ref = _persist_trust_capsule_manifest(state, body, body_digest)
    confirmation = body.get("active_confirmation")
    confirmation_digest = ""
    confirmation_version = None
    if isinstance(confirmation, dict):
        confirmation_digest = hashlib.sha256(
            render_trust_capsule(confirmation).encode("utf-8")
        ).hexdigest()
        confirmation_version = confirmation.get("version")
    overflow_body = {
        "contract_version": "trust_capsule.v1",
        "status": "requires_hydration" if manifest_ref else "blocked",
        "goal": _capsule_text(body.get("goal"), 160),
        "explicit_user_requirements": _capsule_text(
            body.get("explicit_user_requirements"), 200
        ),
        "plan": body.get("plan"),
        "identity_counts": {
            key: len(body[key])
            for key in ("datasets", "unresolved_hard_requirements", "evidence_bindings")
        },
        "active_confirmation": (
            {
                key: (
                    confirmation.get(key)
                    if key == "version"
                    else _capsule_identity(confirmation.get(key))
                )
                for key in (
                    "id",
                    "version",
                    "proposal_id",
                    "candidate_fingerprint",
                    "data_version",
                    "spec_version",
                )
            }
            if isinstance(confirmation, dict)
            else None
        ),
        "active_confirmation_identity_digest": confirmation_digest,
        "active_confirmation_version": confirmation_version,
        "latest_audit_id": _capsule_text(
            (body.get("latest_audit") or {}).get("id")
            if isinstance(body.get("latest_audit"), dict)
            else "",
            160,
        ),
        "trust_manifest": manifest_ref,
        "required_action": "hydrate_or_downgrade",
    }
    overflow_digest = hashlib.sha256(
        render_trust_capsule(overflow_body).encode("utf-8")
    ).hexdigest()
    overflow = {**overflow_body, "digest": overflow_digest}
    if len(render_trust_capsule(overflow)) > maximum:
        overflow["goal"] = ""
        overflow["explicit_user_requirements"] = ""
        overflow["plan"] = {
            "id": hashlib.sha256(
                _text((body.get("plan") or {}).get("id")).encode("utf-8")
            ).hexdigest(),
            "contract_version": _capsule_text(
                (body.get("plan") or {}).get("contract_version"), 80
            ),
        }
        unsigned = {key: value for key, value in overflow.items() if key != "digest"}
        overflow["digest"] = hashlib.sha256(
            render_trust_capsule(unsigned).encode("utf-8")
        ).hexdigest()
    if len(render_trust_capsule(overflow)) > maximum:
        raise ValueError("trust_capsule_minimum_budget_too_small")
    return overflow


def _persist_trust_capsule_manifest(
    state: AnalysisSessionState | None,
    body: dict[str, Any],
    body_digest: str,
) -> dict[str, Any] | None:
    if state is None or not _text(state.session_id):
        return None
    payload = {
        "contract_version": "trust_capsule_manifest.v1",
        "session_id": state.session_id,
        "body_digest": body_digest,
        "body": body,
    }
    try:
        safe_session_id = re.sub(
            r"[^A-Za-z0-9_.-]+", "_", state.session_id
        ).strip("._") or "session"
        directory = get_config().sessions_resolved / safe_session_id / "assurance"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"trust_capsule_manifest_{body_digest[:20]}.json"
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if not path.exists():
            path.write_text(raw, encoding="utf-8")
        artifact_digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    except (OSError, UnicodeError):
        return None
    return {
        "contract_version": "trust_capsule_manifest.v1",
        "artifact_path": str(path),
        "artifact_digest": artifact_digest,
        "body_digest": body_digest,
    }


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
        f"- computation_refs: {len(state.computation_refs)}",
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
