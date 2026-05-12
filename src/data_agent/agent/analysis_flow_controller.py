"""Lightweight controller for analysis flow routing."""

from __future__ import annotations

import uuid

from data_agent.agent.analysis_state import (
    AnalysisSessionState,
    analysis_state_summary,
    load_analysis_state,
)
from data_agent.agent.intent import TurnIntent
from data_agent.agent.method_playbooks import apply_selection_to_state, select_playbooks
from data_agent.session.task_manager import task_manager
from data_agent.tools.registry import registry


class AnalysisFlowController:
    """Coordinates turn intent, analysis state, and tool routing."""

    def __init__(self, session_id: str, project_name: str | None = None):
        self.session_id = session_id
        self.project_name = project_name

    def load_state(self) -> AnalysisSessionState:
        return load_analysis_state(self.session_id, self.project_name)

    def prepare_turn(self, state: AnalysisSessionState, intent: TurnIntent, user_input: str = "", dataset_profile: str = "") -> None:
        state.data_state = intent.data_state
        if intent.analysis_stage in {"discover", "scope", "plan", "execute", "report", "follow_up"}:
            if state.stage in ("discover", "follow_up") or intent.analysis_stage != "discover":
                state.stage = intent.analysis_stage
        if intent.intent_type in {"data_requirement", "analysis_guidance", "direct_analysis", "report"}:
            selection = select_playbooks(user_input, intent, state, dataset_profile)
            apply_selection_to_state(state, selection)
        if intent.intent_type == "direct_analysis" and state.analysis_spec:
            self.ensure_workflow_tasks(state)
            self.ensure_confirmation_task(state)
        state.save()

    def has_pending_confirmation(self, state: AnalysisSessionState) -> bool:
        return any(c.get("status", "pending") == "pending" for c in state.pending_confirmations)

    def is_high_risk_capability(self, capability_id: str, spec: dict | None = None) -> bool:
        high_risk = {
            "analysis.causal",
            "analysis.forecast",
            "analysis.experiment",
            "analysis.classification",
        }
        if capability_id in high_risk:
            return True
        text = " ".join(str(v).lower() for v in (spec or {}).values() if isinstance(v, (str, int, float)))
        return any(term in text for term in ("roi", "what-if", "decision", "决策", "投入产出"))

    def is_capability_blocked_by_confirmation(self, state: AnalysisSessionState, capability_id: str) -> bool:
        spec = state.analysis_spec or {}
        policy = spec.get("confirmation_policy") or {}
        if not policy.get("requires_confirmation") and not self.is_high_risk_capability(capability_id, spec):
            return False
        if not self.is_high_risk_capability(capability_id, spec):
            return False
        return self.has_pending_confirmation(state)

    def is_tool_blocked_by_confirmation(self, state: AnalysisSessionState, tool_name: str) -> bool:
        cap = registry.capability_for(tool_name)
        if not cap:
            return False
        capability_id = cap.get("capability_id", "")
        return self.is_capability_blocked_by_confirmation(state, capability_id)

    def ensure_confirmation_task(self, state: AnalysisSessionState) -> dict | None:
        if not self.has_pending_confirmation(state):
            return None
        spec = state.analysis_spec or {}
        spec_id = spec.get("id", "")
        workflow_id = spec.get("workflow_id", "")
        existing = [
            t for t in task_manager.list_all()
            if t.get("session_id") == self.session_id
            and t.get("node_type") == "confirmation"
            and (not spec_id or t.get("analysis_spec_id") == spec_id)
        ]
        if existing:
            return existing[0]
        pending = next((c for c in state.pending_confirmations if c.get("status", "pending") == "pending"), {})
        policy = spec.get("confirmation_policy") or {}
        return task_manager.create(
            subject="Confirm analysis method and metric scope",
            description=pending.get("blocking_reason") or policy.get("blocking_reason") or "Confirmation required before high-risk analysis.",
            session_id=self.session_id,
            workflow_id=workflow_id,
            project_name=self.project_name or state.project_name or "",
            stage="plan",
            node_type="confirmation",
            analysis_spec_id=spec_id,
            confirmation_ids=[pending.get("id")] if pending.get("id") else [],
            confirmation_policy=policy or {"requires_confirmation": True},
            required_capability="interaction.confirmation",
        )

    def ensure_workflow_tasks(self, state: AnalysisSessionState) -> dict:
        """Create workflow tasks for the current AnalysisSpec once per session.

        The LLM may still call task_create explicitly, but core workflow task
        creation should not depend on it remembering to do so.
        """
        spec = state.analysis_spec or {}
        method_plan = spec.get("method_plan") or []
        if not isinstance(method_plan, list) or not method_plan:
            return {"created": 0, "task_ids": []}

        spec_id = spec.get("id") or uuid.uuid4().hex[:10]
        spec["id"] = spec_id
        workflow_id = spec.get("workflow_id") or f"wf_{uuid.uuid4().hex[:8]}"
        spec["workflow_id"] = workflow_id
        state.analysis_spec = spec

        existing = [
            t for t in task_manager.list_all()
            if t.get("session_id") == self.session_id
            and (
                (spec_id and t.get("analysis_spec_id") == spec_id)
                or (workflow_id and t.get("workflow_id") == workflow_id)
            )
        ]
        if existing:
            return {"created": 0, "task_ids": [t["id"] for t in existing]}

        created = []
        for idx, step in enumerate(method_plan, 1):
            if isinstance(step, dict):
                subject = step.get("step") or step.get("name") or f"Analysis step {idx}"
                expected_output = step.get("expected_output", "")
                node_type = step.get("node_type", "analysis")
                required_capability = step.get("required_capability", "")
                evidence_requirements = step.get("evidence_requirements") or []
                confirmation_policy = step.get("confirmation_policy") or spec.get("confirmation_policy") or {}
            else:
                subject = str(step)
                expected_output = ""
                node_type = "analysis"
                required_capability = ""
                evidence_requirements = []
                confirmation_policy = spec.get("confirmation_policy") or {}

            created.append(task_manager.create(
                subject=subject,
                description=expected_output,
                session_id=self.session_id,
                workflow_id=workflow_id,
                project_name=self.project_name or state.project_name or "",
                stage="execute",
                node_type=node_type,
                analysis_spec_id=spec_id,
                required_data=spec.get("required_data") or [],
                expected_output=expected_output,
                required_capability=required_capability,
                evidence_requirements=evidence_requirements,
                confirmation_policy=confirmation_policy,
            ))

        return {"created": len(created), "task_ids": [t["id"] for t in created]}

    def activate_tool_groups(self, registry, intent: TurnIntent, state: AnalysisSessionState, user_input: str) -> set[str]:
        """Activate tool groups using intent/state first, keywords as fallback."""
        registry.reset_groups()
        groups: set[str] = set()

        if intent.intent_type == "data_requirement":
            groups.update({"knowledge"})
        elif intent.intent_type == "analysis_guidance":
            groups.update({"eda", "clean", "knowledge"})
        elif intent.intent_type == "direct_analysis":
            groups.update({"eda", "task", "knowledge"})
            if state.analysis_spec:
                groups.update({"stats", "ml"})
        elif intent.intent_type == "report":
            groups.update({"report", "task", "eda", "knowledge"})
            if not state.evidence_records:
                groups.update({"stats"})
        elif intent.intent_type == "operation":
            groups.update({"clean"})

        registry.activate_groups(groups)
        self._activate_capabilities_from_state(registry, state)
        keyword_groups = registry.activate_groups_for_text(user_input)

        if intent.intent_type == "data_requirement":
            active = registry._get_active_groups()
            active.difference_update({"stats", "ml", "report", "task"})
        if intent.intent_type == "operation":
            registry._get_active_groups().discard("task")

        return groups | keyword_groups

    def _activate_capabilities_from_state(self, registry, state: AnalysisSessionState) -> None:
        """Expand tool visibility from AnalysisSpec method-plan capabilities."""
        spec = state.analysis_spec or {}
        method_plan = spec.get("method_plan") or []
        if not isinstance(method_plan, list):
            return
        for step in method_plan:
            if not isinstance(step, dict):
                continue
            capability = step.get("required_capability")
            if not capability:
                continue
            for tool_name in registry.tools_for_capability(capability):
                registry.expand_from_tool_call(tool_name)

    def prompt_context(self, state: AnalysisSessionState) -> str:
        summary = analysis_state_summary(state)
        if not summary:
            return ""
        return "<analysis_state>\n" + summary + "\n</analysis_state>"
