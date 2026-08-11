"""Lightweight controller for analysis flow routing."""

from __future__ import annotations

from copy import deepcopy

from data_agent.agent.analysis_state import (
    AnalysisSessionState,
    analysis_state_summary,
    load_analysis_state,
)
from data_agent.agent.analysis_plan_contracts import (
    analysis_plan_id_from_mapping,
    validate_analysis_plan_contract,
)
from data_agent.agent.intent import TurnIntent
from data_agent.agent.confirmation_policy import is_actionable_pending_confirmation
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
        # Capture whether an explicit executable plan (e.g. from
        # ``record_analysis_plan``) was already in place before the auto
        # envelope runs. Workflow projection is only invoked for explicit
        # plans; the auto envelope exists to give computations plan/step
        # identity, not to commit the model to a workflow it never affirmed.
        explicit_executable_plan = bool(
            isinstance(state.analysis_plan, dict)
            and state.analysis_plan.get("review_status") == "executable"
        )
        if intent.intent_type in {"directed_analysis", "comprehensive_report"}:
            self.ensure_canonical_execution_envelope(state, intent, user_input)
        if intent.intent_type == "directed_analysis" and state.analysis_plan:
            if explicit_executable_plan:
                self.ensure_workflow_tasks(state)
                self.reconcile_replayable_computations(state)
            self.ensure_confirmation_task(state)
        self.restore_committed_run_artifacts(state)
        state.save()

    def restore_committed_run_artifacts(
        self,
        state: AnalysisSessionState,
    ) -> dict:
        """Regenerate session JSON views from the canonical run database."""

        coordinator = task_manager._analysis_run_coordinator(create=False)
        if coordinator is None:
            return {"computations": 0, "evidence_records": 0}
        run = coordinator.store.get_latest_run(self.session_id)
        if run is None:
            return {"computations": 0, "evidence_records": 0}
        before_computations = len(state.computation_refs)
        before_evidence = len(state.evidence_records)
        for item in coordinator.store.list_computations(
            run_id=run.run_id,
            session_id=self.session_id,
        ):
            payload = item.get("payload")
            if isinstance(payload, dict) and payload:
                state.upsert_computation_ref(payload)
        for record in coordinator.store.list_evidence_records(
            run_id=run.run_id,
            session_id=self.session_id,
        ):
            if record:
                state.upsert_evidence_record(record)
        restored_computations = max(
            0,
            len(state.computation_refs) - before_computations,
        )
        restored_evidence = max(0, len(state.evidence_records) - before_evidence)
        if restored_computations or restored_evidence:
            state.append_turn_diagnostic({
                "event": "analysis_run_artifacts_restored",
                "run_id": run.run_id,
                "computations": restored_computations,
                "evidence_records": restored_evidence,
            })
        return {
            "computations": restored_computations,
            "evidence_records": restored_evidence,
        }

    def reconcile_replayable_computations(
        self,
        state: AnalysisSessionState,
    ) -> dict:
        """Rebind committed computations after temporary plan/task desync.

        A successful tool result can outlive a momentary mismatch between the
        canonical AnalysisRun step and the semantic AnalysisPlan step.  The
        computation stays committed but cannot advance workflow state until
        the exact capability, dataset, claim, and requirement identities are
        available again.  This method performs that deterministic replay; it
        never infers a step from model prose or changes the original output.
        """

        coordinator = task_manager._analysis_run_coordinator(create=False)
        if coordinator is None:
            return {"reconciled": 0, "remaining": 0, "computation_ids": []}
        run = coordinator.store.get_active_run(self.session_id)
        if run is None:
            return {"reconciled": 0, "remaining": 0, "computation_ids": []}
        replayable = coordinator.store.list_replayable_computations(
            run_id=run.run_id,
            session_id=self.session_id,
        )
        if not replayable:
            return {"reconciled": 0, "remaining": 0, "computation_ids": []}

        from data_agent.agent.analysis_execution import bind_tool_call_to_plan_step
        from data_agent.agent.evidence_contracts import (
            analysis_plan_semantic_digest,
            analysis_step_semantic_digest,
            computation_ref_key,
            project_structured_computation_evidence,
            rebind_computation_ref,
        )
        from data_agent.config import get_config

        plan = state.analysis_plan if isinstance(state.analysis_plan, dict) else {}
        method_steps = {
            str(step.get("step_id") or ""): step
            for step in (plan.get("method_plan") or [])
            if isinstance(step, dict) and str(step.get("step_id") or "")
        }
        run_steps = {step.step_id: step for step in run.steps}
        reconciled_ids: list[str] = []
        diagnostics: list[dict] = []

        for item in replayable:
            computation_id = str(item.get("computation_id") or "")
            ref = dict(item.get("payload") or {})
            run_step = run_steps.get(str(item.get("step_id") or ""))
            external_step_id = (
                str(run_step.payload.get("external_step_id") or "")
                if run_step is not None
                else ""
            )
            semantic_step = method_steps.get(external_step_id)
            tool_name = str(ref.get("tool_name") or "")
            capability = registry.capability_for(tool_name)
            if semantic_step is None or not tool_name or capability is None:
                diagnostics.append({
                    "computation_id": computation_id,
                    "reason": "replay_binding_unavailable",
                    "step_id": external_step_id,
                })
                continue
            dataset_names = [
                str(name)
                for name in (semantic_step.get("dataset_inputs") or [])
                if str(name)
            ]
            binding = bind_tool_call_to_plan_step(
                plan=plan,
                tool_name=tool_name,
                capability=capability,
                dataset_names=dataset_names,
                preferred_step_id=external_step_id,
            )
            if not binding.ok or binding.step_id != external_step_id:
                diagnostics.append({
                    "computation_id": computation_id,
                    "reason": binding.error_type or "replay_binding_unavailable",
                    "step_id": external_step_id,
                })
                continue

            rebound_ref = rebind_computation_ref(
                ref,
                sessions_root=get_config().sessions_resolved,
                current_session_id=self.session_id,
                plan_id=binding.plan_id,
                plan_digest=analysis_plan_semantic_digest(plan),
                step_id=binding.step_id,
                step_digest=analysis_step_semantic_digest(semantic_step),
            )
            rebound_ref.update({
                "claim_key": binding.claim_key,
                "claim_keys": list(binding.claim_keys),
                "requirement_ids": list(binding.requirement_ids),
                "binding_error_type": "",
                "binding_candidate_step_ids": [],
                "projection_status": "projected",
                "reconciled_from_binding_error_type": str(
                    ref.get("binding_error_type") or ""
                ),
            })
            # The bound reference is a new semantic revision of the same
            # immutable computation row. Recompute its provenance key while
            # retaining the stable AnalysisRun computation_id.
            rebound_ref["computation_ref_id"] = computation_ref_key(rebound_ref)
            projection = project_structured_computation_evidence(
                computation_ref=rebound_ref,
                binding=binding,
                plan=plan,
                capability=capability,
                dataset_contracts=list(state.dataset_contracts or []),
                current_session_id=self.session_id,
                current_turn_id=str(rebound_ref.get("turn_id") or ""),
                sessions_root=get_config().sessions_resolved,
            )
            if not projection.projected:
                diagnostics.append({
                    "computation_id": computation_id,
                    "reason": projection.reason or "replay_projection_failed",
                    "diagnostics": list(projection.diagnostics or []),
                })
                continue

            records = [
                dict(record)
                for record in (projection.records or (projection.record,))
                if isinstance(record, dict)
            ]
            expected_claims = {str(value) for value in binding.claim_keys if str(value)}
            expected_requirements = {
                str(value) for value in binding.requirement_ids if str(value)
            }
            projected_claims = {
                str(record.get("claim_key") or "")
                for record in records
                if str(record.get("claim_key") or "")
            }
            projected_requirements = {
                str(requirement_id)
                for record in records
                for requirement_id in (record.get("requirement_ids") or [])
                if str(requirement_id)
            }
            complete_step = bool(expected_claims) and (
                expected_claims.issubset(projected_claims)
                and expected_requirements.issubset(projected_requirements)
            )
            receipt = task_manager.reconcile_analysis_computation_projection(
                session_id=self.session_id,
                binding={"run_id": run.run_id, "step_id": run_step.step_id},
                computation_id=computation_id,
                computation_ref=rebound_ref,
                evidence_records=records,
                complete_step=complete_step,
                idempotency_key=(
                    f"reconcile:{computation_id}:"
                    f"{rebound_ref['plan_digest']}:{binding.step_id}"
                ),
            )
            if receipt is None:
                diagnostics.append({
                    "computation_id": computation_id,
                    "reason": "replay_transaction_unavailable",
                })
                continue
            state.upsert_computation_ref(rebound_ref)
            for record in records:
                state.upsert_evidence_record(record)
            state.append_turn_diagnostic({
                "event": "computation_projection_reconciled",
                "computation_id": computation_id,
                "computation_ref_id": rebound_ref["computation_ref_id"],
                "plan_id": binding.plan_id,
                "step_id": binding.step_id,
                "evidence_ids": [str(record.get("id") or "") for record in records],
                "completed_task_ids": (
                    [int(receipt.get("legacy_task_id") or 0)]
                    if receipt.get("completed_step_id")
                    and int(receipt.get("legacy_task_id") or 0)
                    else []
                ),
            })
            reconciled_ids.append(computation_id)

        if reconciled_ids:
            state.save()
        remaining = len(replayable) - len(reconciled_ids)
        return {
            "reconciled": len(reconciled_ids),
            "remaining": remaining,
            "computation_ids": reconciled_ids,
            "diagnostics": diagnostics,
        }

    def ensure_canonical_execution_envelope(
        self,
        state: AnalysisSessionState,
        intent: TurnIntent,
        user_input: str,
    ):
        """Materialize the canonical executable plan before substantive calls.

        Called after route/playbook selection. When dataset contracts are
        available, the server owns the plan: it injects the active dataset
        identity into each analytical step and validates the plan as
        executable. Failures are recorded as bounded turn diagnostics so the
        turn cannot report completion against an unsupported plan.

        Returns the ``EnvelopeResult`` so callers can distinguish auto-envelope
        materialization from an existing explicit plan.
        """

        active_contracts = [
            contract
            for contract in (state.dataset_contracts or [])
            if isinstance(contract, dict)
        ]
        if not active_contracts:
            return None
        from data_agent.agent.analysis_execution import (
            ensure_canonical_execution_envelope as _ensure_envelope,
        )

        result = _ensure_envelope(
            state=state,
            intent=intent,
            user_input=user_input,
            active_dataset_contracts=active_contracts,
        )
        diagnostic = {
            "event": "execution_envelope",
            "ok": bool(result.ok),
            "error_type": result.error_type,
            "plan_id": (result.plan or {}).get("id", "") if isinstance(result.plan, dict) else "",
        }
        if result.details:
            diagnostic["details"] = result.details
        state.append_turn_diagnostic(diagnostic)
        return result

    def has_pending_confirmation(self, state: AnalysisSessionState) -> bool:
        return any(is_actionable_pending_confirmation(c) for c in state.pending_confirmations)

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

    # Tool categories that are always safe regardless of plan content
    SAFE_TOOL_CATEGORIES = frozenset({
        "data_view",     # list_data, quick_profile
        "data_load",     # load_data
        "confirmation",  # ask_user_question
    })

    def is_high_risk_capability(self, capability_id: str, plan: dict | None = None) -> bool:
        if capability_id in self.HIGH_RISK_CAPABILITIES:
            return True
        return False

    def is_capability_blocked_by_confirmation(self, state: AnalysisSessionState, capability_id: str) -> bool:
        if capability_id in self.NEVER_BLOCK_CAPABILITIES:
            return False
        plan = state.analysis_plan or {}
        policy = plan.get("confirmation_policy") or {}
        if not policy.get("requires_confirmation"):
            return False
        if not self.is_high_risk_capability(capability_id, plan):
            return False
        confirmation = plan.get("method_confirmation") or {}
        approved = (
            confirmation.get("status") == "approved"
            and analysis_plan_id_from_mapping(confirmation) == plan.get("id")
            and confirmation.get("playbook_id") == plan.get("playbook_id")
        )
        return not approved

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
        plan = state.analysis_plan or {}
        analysis_plan_id = plan.get("id", "")
        workflow_id = plan.get("workflow_id", "")
        existing = [
            t for t in task_manager.list_all()
            if t.get("session_id") == self.session_id
            and t.get("node_type") == "confirmation"
            and (not analysis_plan_id or analysis_plan_id_from_mapping(t) == analysis_plan_id)
            and t.get("status") not in ("deleted", "archived", "superseded")
        ]
        if existing:
            return existing[0]
        pending = next(
            (c for c in state.pending_confirmations if is_actionable_pending_confirmation(c)),
            {},
        )
        policy = plan.get("confirmation_policy") or {}
        project_name = self.project_name or state.project_name or ""
        task_plan_id = task_manager.get_active_plan_id(self.session_id, project_name)
        if not task_plan_id:
            plan_record = task_manager.create_plan(
                session_id=self.session_id,
                project_name=project_name,
                goal=plan.get("goal", state.goal),
                source="system_confirmation",
                analysis_spec_id=analysis_plan_id,
                workflow_id=workflow_id,
            )
            task_plan_id = plan_record["id"]
            plan_version = plan_record["version"]
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
            analysis_spec_id=analysis_plan_id,
            analysis_plan_id=analysis_plan_id,
            confirmation_ids=[pending.get("id")] if pending.get("id") else [],
            confirmation_policy=policy or {"requires_confirmation": True},
            required_capability="interaction.confirmation",
            plan_id=task_plan_id,
            plan_version=plan_version,
            plan_status="active",
            task_kind="confirmation",
            source="system_confirmation",
        )

    def resolve_confirmation_and_activate(
        self,
        state: AnalysisSessionState,
        *,
        confirmation_id: str,
        answer: str,
        intent: TurnIntent,
        user_input: str = "",
        related_plan_id: str = "",
    ) -> dict:
        """Resolve an analysis gate and reconcile it to one executable task.

        Confirmation state and the legacy task projection live in separate
        stores, so this entry point is deliberately idempotent: a retry
        reconciles the same resolved confirmation, executable plan, and
        ``AnalysisRun`` instead of creating a second workflow.  The run
        coordinator remains the authority for the unique current step.
        """

        confirmation = self._confirmation_for_resolution(
            state,
            confirmation_id=confirmation_id,
            related_plan_id=related_plan_id,
        )
        if confirmation is None:
            return {
                "ok": False,
                "error_type": "confirmation_not_found",
                "confirmation_id": confirmation_id,
            }

        working_state = deepcopy(state)
        working_confirmation = self._confirmation_for_resolution(
            working_state,
            confirmation_id=confirmation_id,
            related_plan_id=related_plan_id,
        )
        if working_confirmation is None:
            return {
                "ok": False,
                "error_type": "confirmation_not_found",
                "confirmation_id": confirmation_id,
            }

        state_confirmation_id = str(
            working_confirmation.get("id")
            or working_confirmation.get("suspension_id")
            or ""
        )
        state_updates = working_confirmation.get("state_updates")
        method_update = (
            state_updates.get("method_confirmation")
            if isinstance(state_updates, dict)
            else None
        )
        allowed_actions = (
            list(method_update.get("allowed_actions") or [])
            if isinstance(method_update, dict)
            else []
        )
        if allowed_actions and answer not in allowed_actions:
            return {
                "ok": False,
                "error_type": "invalid_confirmation_answer",
                "confirmation_id": state_confirmation_id,
            }
        resolved = working_state.resolve_confirmation(state_confirmation_id, answer)
        if resolved is None:
            return {
                "ok": False,
                "error_type": "confirmation_not_found",
                "confirmation_id": confirmation_id,
            }

        resolved_plan_id = (
            related_plan_id
            or str(working_confirmation.get("related_plan_id") or "")
            or str(working_confirmation.get("related_spec_id") or "")
        )

        # Scope clarification is a successful resolution of this gate, but it
        # intentionally creates another gate rather than executable work.
        if self.has_pending_confirmation(working_state):
            confirmation_task_ids = self._close_confirmation_tasks(
                working_state,
                confirmation_ids={confirmation_id, state_confirmation_id},
                answer=answer,
                related_plan_id=resolved_plan_id,
            )
            self._replace_state(state, working_state)
            state.save()
            return {
                "ok": True,
                "activated": False,
                "confirmation_id": state_confirmation_id,
                "confirmation_task_ids": confirmation_task_ids,
                "reason": "confirmation_still_required",
            }

        envelope = self.ensure_canonical_execution_envelope(
            working_state,
            intent,
            user_input or working_state.goal,
        )
        if envelope is None or not envelope.ok:
            return {
                "ok": False,
                "error_type": (
                    envelope.error_type
                    if envelope is not None
                    else "analysis_dataset_identity_missing"
                ),
                "confirmation_id": state_confirmation_id,
                "confirmation_task_ids": [],
            }

        projection = self.ensure_workflow_tasks(working_state)
        if projection.get("error") or projection.get("display_only"):
            return {
                "ok": False,
                "error_type": str(
                    projection.get("error_type")
                    or projection.get("error")
                    or projection.get("reason")
                    or "analysis_workflow_projection_failed"
                ),
                "confirmation_id": state_confirmation_id,
                "confirmation_task_ids": [],
                "projection": projection,
            }

        project_name = self.project_name or working_state.project_name or ""
        run_scope = task_manager.get_analysis_run_scope(
            self.session_id,
            project_name,
        )
        active_task_id = int((run_scope or {}).get("task_id") or 0)
        if not active_task_id:
            return {
                "ok": False,
                "error_type": "analysis_run_current_step_missing",
                "confirmation_id": state_confirmation_id,
                "confirmation_task_ids": [],
                "projection": projection,
            }

        confirmation_task_ids = self._close_confirmation_tasks(
            working_state,
            confirmation_ids={confirmation_id, state_confirmation_id},
            answer=answer,
            related_plan_id=resolved_plan_id,
        )
        self._replace_state(state, working_state)
        state.save()
        return {
            "ok": True,
            "activated": True,
            "confirmation_id": state_confirmation_id,
            "confirmation_task_ids": confirmation_task_ids,
            "analysis_plan_id": str(
                (working_state.analysis_plan or {}).get("id") or ""
            ),
            "active_task_id": active_task_id,
            "projection": projection,
        }

    @staticmethod
    def _replace_state(
        target: AnalysisSessionState,
        source: AnalysisSessionState,
    ) -> None:
        target.__dict__.clear()
        target.__dict__.update(deepcopy(source.__dict__))

    def _confirmation_for_resolution(
        self,
        state: AnalysisSessionState,
        *,
        confirmation_id: str,
        related_plan_id: str,
    ) -> dict | None:
        confirmations = [
            item
            for item in (state.pending_confirmations or [])
            if isinstance(item, dict)
        ]
        direct = next((
            item
            for item in confirmations
            if confirmation_id in {
                str(item.get("id") or ""),
                str(item.get("suspension_id") or ""),
            }
        ), None)
        if direct is not None:
            return direct

        # The durable confirmation service owns a generated confirmation ID,
        # while AnalysisSessionState historically retained the plan-bound ID.
        # Relate those identities only through the exact plan reference.
        if related_plan_id:
            matches = [
                item
                for item in confirmations
                if related_plan_id in {
                    str(item.get("related_plan_id") or ""),
                    str(item.get("related_spec_id") or ""),
                }
            ]
            if len(matches) == 1:
                return matches[0]
        return None

    def _close_confirmation_tasks(
        self,
        state: AnalysisSessionState,
        *,
        confirmation_ids: set[str],
        answer: str,
        related_plan_id: str,
    ) -> list[int]:
        project_name = self.project_name or state.project_name or ""
        normalized_ids = {item for item in confirmation_ids if item}
        closed: list[int] = []
        for task in task_manager.list_all(include_stale=True):
            if task.get("session_id") != self.session_id:
                continue
            if str(task.get("project_name") or "") != project_name:
                continue
            if task.get("task_kind") != "confirmation" and task.get("node_type") != "confirmation":
                continue
            task_confirmation_ids = {
                str(item)
                for item in (task.get("confirmation_ids") or [])
                if str(item)
            }
            plan_matches = bool(
                related_plan_id
                and analysis_plan_id_from_mapping(task) == related_plan_id
            )
            if not (normalized_ids.intersection(task_confirmation_ids) or plan_matches):
                continue
            task_id = int(task.get("id") or 0)
            if not task_id:
                continue
            if task.get("status") != "completed":
                task_manager.update(
                    task_id,
                    status="completed",
                    completed_by="confirmation",
                    confirmation_ids=sorted(task_confirmation_ids | normalized_ids),
                    result_summary=f"User confirmation resolved: {answer}",
                )
            closed.append(task_id)
        return sorted(set(closed))

    def ensure_workflow_tasks(self, state: AnalysisSessionState) -> dict:
        plan = state.analysis_plan or {}
        if not isinstance(plan, dict):
            return {"created": 0, "task_ids": []}
        validation = validate_analysis_plan_contract(
            plan,
            dataset_contracts=list(state.dataset_contracts or []),
        )
        if not validation.ok:
            return {
                "created": 0,
                "task_ids": [],
                "display_only": True,
                "reason": "analysis_plan_not_executable",
                "error_type": validation.error_type,
            }
        plan = validation.plan
        from data_agent.agent.workflow_projection import project_plan_to_workflow_tasks

        project_name = self.project_name or state.project_name or ""
        return project_plan_to_workflow_tasks(
            task_manager,
            plan,
            session_id=self.session_id,
            project_name=project_name,
            source="analysis_plan",
        )

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

        Uses evidence_records and the canonical analysis plan to detect data signals
        (time columns, dimensions, metrics, etc.) and proactively enable
        relevant tool groups.
        """
        plan = state.analysis_plan or {}
        evidence = state.evidence_records or []

        # Extract signal text from the plan and recent evidence
        signal_parts = []
        for field in ("metrics", "dimensions", "time_scope"):
            val = plan.get(field)
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
        """Expand tool visibility from AnalysisPlan method-plan capabilities."""
        plan = state.analysis_plan or {}
        method_plan = plan.get("method_plan") or []
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
