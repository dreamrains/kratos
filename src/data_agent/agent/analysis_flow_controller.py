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
        if intent.intent_type in {"directed_analysis", "comprehensive_report", "intent_negotiation", "data_requirement"}:
            selection = select_playbooks(user_input, intent, state, dataset_profile)
            apply_selection_to_state(state, selection)
        if intent.intent_type == "directed_analysis" and state.analysis_spec:
            self.ensure_workflow_tasks(state)
            self.ensure_confirmation_task(state)
        state.save()

    def has_pending_confirmation(self, state: AnalysisSessionState) -> bool:
        return any(c.get("status", "pending") == "pending" for c in state.pending_confirmations)

    HIGH_RISK_CAPABILITIES = frozenset({
        "analysis.causal",
        "analysis.forecast",
        "analysis.experiment",
        "analysis.classification",
    })

    # Capabilities that must never be blocked — they are the escape hatch
    NEVER_BLOCK_CAPABILITIES = frozenset({
        "interaction.confirmation",  # ask_user_question
        "interaction.information",   # informational queries
    })

    # Tool categories that are always safe regardless of spec content
    SAFE_TOOL_CATEGORIES = frozenset({
        "data_view",     # list_data, quick_profile
        "data_load",     # load_data
        "confirmation",  # ask_user_question
    })

    def is_high_risk_capability(self, capability_id: str, spec: dict | None = None) -> bool:
        if capability_id in self.HIGH_RISK_CAPABILITIES:
            return True
        return False

    def is_capability_blocked_by_confirmation(self, state: AnalysisSessionState, capability_id: str) -> bool:
        if capability_id in self.NEVER_BLOCK_CAPABILITIES:
            return False
        spec = state.analysis_spec or {}
        policy = spec.get("confirmation_policy") or {}
        if not policy.get("requires_confirmation"):
            return False
        if not self.is_high_risk_capability(capability_id, spec):
            return False
        return self.has_pending_confirmation(state)

    def is_tool_blocked_by_confirmation(self, state: AnalysisSessionState, tool_name: str) -> bool:
        cap = registry.capability_for(tool_name)
        if not cap:
            return False
        capability_id = cap.get("capability_id", "")
        category = cap.get("category", "")
        if capability_id in self.NEVER_BLOCK_CAPABILITIES or category in self.SAFE_TOOL_CATEGORIES:
            return False
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
            and t.get("status") not in ("deleted", "archived", "superseded")
        ]
        if existing:
            return existing[0]
        pending = next((c for c in state.pending_confirmations if c.get("status", "pending") == "pending"), {})
        policy = spec.get("confirmation_policy") or {}
        project_name = self.project_name or state.project_name or ""
        plan_id = task_manager.get_active_plan_id(self.session_id, project_name)
        if not plan_id:
            plan = task_manager.create_plan(
                session_id=self.session_id,
                project_name=project_name,
                goal=spec.get("goal", state.goal),
                source="system_confirmation",
                analysis_spec_id=spec_id,
                workflow_id=workflow_id,
            )
            plan_id = plan["id"]
            plan_version = plan["version"]
        else:
            active_tasks = task_manager.list_active_for_scope(
                session_id=self.session_id,
                project_name=project_name,
            )
            plan_version = max([int(t.get("plan_version") or 1) for t in active_tasks], default=1)
        return task_manager.create(
            subject="Confirm analysis method and metric scope",
            description=pending.get("blocking_reason") or policy.get("blocking_reason") or "Confirmation required before high-risk analysis.",
            session_id=self.session_id,
            workflow_id=workflow_id,
            project_name=project_name,
            stage="plan",
            node_type="confirmation",
            analysis_spec_id=spec_id,
            confirmation_ids=[pending.get("id")] if pending.get("id") else [],
            confirmation_policy=policy or {"requires_confirmation": True},
            required_capability="interaction.confirmation",
            plan_id=plan_id,
            plan_version=plan_version,
            plan_status="active",
            task_kind="confirmation",
            source="system_confirmation",
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
        project_name = self.project_name or state.project_name or ""

        active_plan_id = task_manager.get_active_plan_id(self.session_id, project_name)
        active_tasks = (
            task_manager.list_active_for_scope(session_id=self.session_id, project_name=project_name)
            if active_plan_id else []
        )
        existing = [
            t for t in active_tasks
            if (spec_id and t.get("analysis_spec_id") == spec_id)
            or (workflow_id and t.get("workflow_id") == workflow_id)
        ]
        if existing:
            return {"created": 0, "task_ids": [t["id"] for t in existing]}

        plan = task_manager.create_plan(
            session_id=self.session_id,
            project_name=project_name,
            goal=spec.get("goal", state.goal),
            source="analysis_spec",
            analysis_spec_id=spec_id,
            workflow_id=workflow_id,
        )

        created = []
        reused = []
        for idx, step in enumerate(method_plan, 1):
            if isinstance(step, dict):
                subject = step.get("task") or step.get("step") or step.get("name") or step.get("title") or f"Analysis step {idx}"
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

            duplicate = task_manager.find_duplicate_task(
                session_id=self.session_id,
                plan_id=plan["id"],
                subject=subject,
                analysis_spec_id=spec_id,
            )
            if duplicate:
                reused.append(duplicate)
                continue

            created.append(task_manager.create(
                subject=subject,
                description=expected_output,
                session_id=self.session_id,
                workflow_id=workflow_id,
                project_name=project_name,
                stage="execute",
                node_type=node_type,
                analysis_spec_id=spec_id,
                required_data=spec.get("required_data") or [],
                expected_output=expected_output,
                required_capability=required_capability,
                evidence_requirements=evidence_requirements,
                confirmation_policy=confirmation_policy,
                plan_id=plan["id"],
                plan_version=plan.get("version", 1),
                plan_status="active",
                task_kind="plan_task",
                source="analysis_spec",
            ))

        return {
            "created": len(created),
            "reused": len(reused),
            "task_ids": [t["id"] for t in created + reused],
        }

    def activate_tool_groups(self, registry, intent: TurnIntent, state: AnalysisSessionState, user_input: str) -> set[str]:
        """Activate tool groups using intent/state first, data signals second, keywords as fallback."""
        registry.reset_groups()
        groups: set[str] = set()

        if intent.intent_type in ("simple_response", "knowledge_qa", "analysis_consultation", "result_followup"):
            groups.update({"conversation_query"})
        elif intent.intent_type in ("intent_negotiation", "data_requirement"):
            groups.update({"knowledge", "eda"})
        elif intent.intent_type == "directed_analysis":
            groups.update({"eda", "task", "knowledge"})
            if state.analysis_plan:
                groups.update({"stats", "ml"})
        elif intent.intent_type == "comprehensive_report":
            groups.update({"report", "task", "eda", "knowledge"})
            if not state.evidence_records:
                groups.update({"stats"})
        elif intent.intent_type == "data_operation":
            groups.update({"clean", "eda"})

        registry.activate_groups(groups)
        self._activate_capabilities_from_state(registry, state)

        # Activate based on data features in state (interpret_dataset results)
        self._activate_from_data_signals(registry, state)

        keyword_groups = registry.activate_groups_for_text(user_input)

        if intent.intent_type == "data_requirement":
            active = registry._get_active_groups()
            active.difference_update({"stats", "ml", "report", "task"})
        if intent.intent_type == "data_operation":
            registry._get_active_groups().discard("task")

        return groups | keyword_groups

    def _activate_from_data_signals(self, registry, state: AnalysisSessionState) -> None:
        """Activate tool groups based on data features stored in analysis state.

        Uses evidence_records and analysis_spec to detect data signals
        (time columns, dimensions, metrics, etc.) and proactively enable
        relevant tool groups.
        """
        spec = state.analysis_spec or {}
        evidence = state.evidence_records or []

        # Extract signal text from spec and recent evidence
        signal_parts = []
        for field in ("metrics", "dimensions", "time_scope"):
            val = spec.get(field)
            if isinstance(val, (list, str)) and val:
                signal_parts.extend(val if isinstance(val, list) else [val])
        for rec in evidence[-3:]:
            for field in ("claim", "method"):
                val = rec.get(field, "")
                if val:
                    signal_parts.append(str(val))

        if not signal_parts:
            return

        signal_text = " ".join(signal_parts).lower()

        # Time-related signals → activate eda tools for trend analysis
        time_signals = ("date", "time", "时间", "日期", "trend", "趋势", "周期", "seasonal")
        if any(s in signal_text for s in time_signals):
            registry.expand_from_tool_call("analyze_time_series")

        # Dimension signals → activate comparison tools
        dim_signals = ("channel", "region", "渠道", "地区", "维度", "segment", "分组", "对比")
        if any(s in signal_text for s in dim_signals):
            registry.expand_from_tool_call("compare_periods")
            registry.expand_from_tool_call("top_n")

        # Funnel/conversion signals
        funnel_signals = ("funnel", "conversion", "漏斗", "转化", "drop-off", "流失")
        if any(s in signal_text for s in funnel_signals):
            registry.expand_from_tool_call("funnel_analysis")
            registry.expand_from_tool_call("cohort_analysis")

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

    def check_tool_regression(self, state: AnalysisSessionState, tool_name: str, tool_result: str) -> str | None:
        """Check if a tool result should trigger stage regression. Delegates to state."""
        return state.check_regression_triggers(tool_name, tool_result)
