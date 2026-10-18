"""Runtime glue for trustworthy analysis workflow integration."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from data_agent.agent.intent import TurnIntent
from data_agent.agent.intent_refinement import refine_intent_with_data
from data_agent.utils.logging import get_logger


logger = get_logger("trust_workflow_runtime")


def refine_turn_intent_with_state(user_input: str, intent: TurnIntent, state: Any) -> TurnIntent:
    """Refine a turn intent using trustworthy state refs without breaking the loop."""

    try:
        scope = getattr(state, "active_scope", None)
        active_dataset = str(scope.get("active_dataset") or "") if isinstance(scope, dict) else ""
        return refine_intent_with_data(
            user_input=user_input,
            intent=intent,
            dataset_contracts=_list_attr(state, "dataset_contracts"),
            route_proposals=_list_attr(state, "route_proposals"),
            active_dataset=active_dataset,
        )
    except Exception as exc:
        logger.warning(
            "Trust workflow intent refinement skipped",
            extra={"extra_data": {"error": str(exc)}},
        )
        return intent




def _workspace_data_identities() -> dict[str, dict]:
    """Current dataset identities from the active workspace, or {} offline."""
    try:
        from data_agent.session.workspace import workspace as workspace_obj

        identities: dict[str, dict] = {}
        for name in (workspace_obj.list_datasets() or {}):
            identity = workspace_obj.get_data_identity(name)
            if isinstance(identity, dict) and identity.get("fingerprint"):
                identities[str(name)] = identity
        return identities
    except Exception:
        return {}


def _split_evidence_by_data_freshness(
    records: list[dict[str, Any]],
    current_identities: dict[str, dict],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split evidence into (fresh, exclusions) by dataset version.

    Only a positive fingerprint mismatch on a dataset that currently exists
    excludes a record; absent datasets, missing bindings, or identity-free
    records stay fresh (cannot judge → stay conservative). Excluded records
    are not deleted — they stop backing hypotheses and the exclusion is
    recorded with both fingerprints for audit (P7-L3/B04).
    """
    fresh: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    for record in records:
        stale: dict[str, Any] | None = None
        bindings = record.get("result_bindings") if isinstance(record, dict) else None
        if isinstance(bindings, list):
            for binding in bindings:
                if not isinstance(binding, dict) or stale:
                    break
                for name, bound in (binding.get("data_identities") or {}).items():
                    current = current_identities.get(str(name))
                    if current is None:
                        continue
                    bound_fingerprint = str((bound or {}).get("fingerprint") or "")
                    current_fingerprint = str(current.get("fingerprint") or "")
                    if bound_fingerprint and bound_fingerprint != current_fingerprint:
                        stale = {
                            "dataset": str(name),
                            "bound_fingerprint": bound_fingerprint,
                            "current_fingerprint": current_fingerprint,
                        }
                        break
        if stale is not None:
            exclusions.append({
                "evidence_id": str(record.get("id") or ""),
                "reason": "data_version_changed",
                **stale,
            })
        else:
            fresh.append(record)
    return fresh, exclusions


def maybe_create_hypothesis_set(user_input: str, intent: TurnIntent, state: Any) -> dict[str, Any] | None:
    """Create one compact hypothesis set for a runnable analysis route."""

    try:
        from data_agent.agent.question_need_detector import explicit_task_reason

        # Explicit hypothesis audits use stable IDs scoped to a real plan.
        # A pre-plan set would become historical as soon as the model records
        # its plan, leaving earlier relation proposals attached to the wrong
        # identity. Ordinary exploratory sets may still be created without one.
        if explicit_task_reason(user_input) in {
            "hypothesis_task", "competing_hypotheses", "evidence_reassessment",
        }:
            plan = getattr(state, "analysis_plan", None)
            if not isinstance(plan, dict) or not str(plan.get("id") or "").strip():
                return None
        from data_agent.agent.analysis_entry import decide_analysis_entry
        from data_agent.agent.hypotheses import (
            build_hypothesis_set,
            hydrate_hypothesis_refs,
            persist_hypothesis_set,
            receipt_verified_descriptive_directions,
            receipt_verified_hypothesis_measurements,
            update_hypotheses_from_evidence,
        )

        decision = decide_analysis_entry(user_input, intent, state)
        if decision.get("decision") not in {"direct_analysis", "exploratory_only", "request_data"}:
            return None

        evidence_records = _list_attr(state, "evidence_records")
        # Data-version gate (P7-L3/B04): evidence bound to an older version of
        # a still-loaded dataset stops backing hypotheses; decided hypotheses
        # then transition to stale instead of keeping their verdict.
        fresh_evidence, exclusions = _split_evidence_by_data_freshness(
            evidence_records, _workspace_data_identities(),
        )
        verified_measurements = receipt_verified_hypothesis_measurements(state, fresh_evidence)
        verified_directions = receipt_verified_descriptive_directions(state, fresh_evidence)
        hypothesis_set = build_hypothesis_set(user_input, decision, state)
        dataset = str(hypothesis_set.get("dataset") or "")
        route = str(hypothesis_set.get("route") or "")
        plan_id = str(hypothesis_set.get("plan_id") or "")
        # A new plan on the same dataset must not leave a decided historical
        # set looking current after its underlying version has changed.
        stale_record_ids = {str(item.get("evidence_id") or "") for item in exclusions
                            if item.get("dataset") == dataset}
        if stale_record_ids:
            records_by_id = {str(item.get("id") or ""): item for item in evidence_records}
            for prior_ref in list(_list_attr(state, "hypothesis_sets")):
                if (prior_ref.get("dataset") != dataset
                        or prior_ref.get("id") == hypothesis_set.get("id")):
                    continue
                prior_plan = str(prior_ref.get("plan_id") or "")
                prior_exclusions = [item for item in exclusions
                                    if str(item.get("evidence_id") or "") in stale_record_ids
                                    and str(records_by_id.get(str(item.get("evidence_id") or ""), {}).get("plan_id") or "") == prior_plan]
                if not prior_exclusions:
                    continue
                hydrated_prior = hydrate_hypothesis_refs([prior_ref])
                if not hydrated_prior:
                    continue
                refreshed_prior = update_hypotheses_from_evidence(
                    hydrated_prior[0], fresh_evidence, verified_measurements=verified_measurements,
                    verified_directions=verified_directions,
                )
                refreshed_prior["evidence_exclusions"] = prior_exclusions
                prior_stored = persist_hypothesis_set(str(getattr(state, "session_id", "")), refreshed_prior)
                if prior_ref.get("created_at"):
                    prior_stored["created_at"] = prior_ref["created_at"]
                state.add_hypothesis_set_ref(prior_stored)
        existing_ref = _find_hypothesis_set_ref(state, dataset, route, plan_id)
        if existing_ref:
            hydrated = hydrate_hypothesis_refs([existing_ref])
            if not hydrated:
                return None
            decided = any(
                hypothesis.get("supporting_evidence_ids")
                or hypothesis.get("conflicting_evidence_ids")
                or hypothesis.get("evidence_relations")
                for hypothesis in hydrated[0].get("hypotheses") or []
                if isinstance(hypothesis, dict)
            )
            # An undecided set with no evidence stays as-is (dedupe); a
            # decided set must be recomputed even when its evidence is gone,
            # so it can become stale instead of silently keeping its verdict.
            if not fresh_evidence and not decided:
                return None
            hypothesis_set = update_hypotheses_from_evidence(
                hydrated[0], fresh_evidence, verified_measurements=verified_measurements,
                verified_directions=verified_directions,
            )
        elif fresh_evidence:
            hypothesis_set = update_hypotheses_from_evidence(
                hypothesis_set, fresh_evidence, verified_measurements=verified_measurements,
                verified_directions=verified_directions,
            )
        if exclusions:
            hypothesis_set["evidence_exclusions"] = exclusions

        ref = persist_hypothesis_set(str(getattr(state, "session_id", "")), hypothesis_set)
        if existing_ref and existing_ref.get("created_at"):
            ref["created_at"] = existing_ref["created_at"]
        add_ref = getattr(state, "add_hypothesis_set_ref", None)
        if callable(add_ref):
            stored = add_ref(ref)
        else:
            refs = getattr(state, "hypothesis_sets", None)
            if isinstance(refs, list):
                refs.append(ref)
            stored = ref

        save = getattr(state, "save", None)
        if callable(save):
            save()
        return stored
    except Exception as exc:
        logger.warning(
            "Hypothesis set creation skipped",
            extra={"extra_data": {"error": str(exc), "user_input": (user_input or "")[:200]}},
        )
        return None


def _find_hypothesis_set_ref(
    state: Any,
    dataset: str,
    route: str,
    plan_id: str = "",
) -> dict[str, Any] | None:
    """Reuse only a set bound to the same plan; other plans stay as history."""
    for ref in _list_attr(state, "hypothesis_sets"):
        if str(ref.get("dataset") or "") != dataset:
            continue
        if str(ref.get("route") or "") != route:
            continue
        if str(ref.get("plan_id") or "") != plan_id:
            continue
        return ref
    return None


def _list_attr(state: Any, name: str) -> list[dict[str, Any]]:
    value = getattr(state, name, None)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]
