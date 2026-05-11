"""Lightweight controller for analysis flow routing."""

from __future__ import annotations

from data_agent.agent.analysis_state import (
    AnalysisSessionState,
    analysis_state_summary,
    load_analysis_state,
)
from data_agent.agent.intent import TurnIntent
from data_agent.agent.method_playbooks import apply_selection_to_state, select_playbooks


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
        state.save()

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
