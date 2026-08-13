from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from data_agent.v2.models import (
    Commitment,
    CommitmentOutcome,
    CommitmentPriority,
    EventType,
    ExecutionEvent,
    Finding,
    FindingKind,
    OutcomeStatus,
    PUBLISHABLE_OUTCOMES,
    RunProjection,
)


def _matching_findings(commitment: Commitment, findings: Iterable[Finding]) -> list[Finding]:
    expected_versions = set(commitment.dataset_version_ids)
    return [
        finding
        for finding in findings
        if finding.commitment_id == commitment.commitment_id
        and finding.finding_kind in commitment.accepted_result_kinds
        and finding.method_capability in commitment.accepted_method_capabilities
        and set(finding.dataset_version_ids) == expected_versions
    ]


def _project_commitment(
    commitment: Commitment,
    events: list[ExecutionEvent],
    findings: list[Finding],
) -> CommitmentOutcome:
    matched = _matching_findings(commitment, findings)
    matched_ids = tuple(item.finding_id for item in matched)
    event_ids = tuple(item.event_id for item in events)

    if any(
        item.finding_kind
        in {FindingKind.ESTIMATE, FindingKind.ASSOCIATION, FindingKind.TRANSFORMATION}
        for item in matched
    ):
        return CommitmentOutcome(
            commitment_id=commitment.commitment_id,
            status=OutcomeStatus.SUPPORTED,
            finding_ids=matched_ids,
            event_ids=event_ids,
        )
    if any(item.finding_kind is FindingKind.NULL_RESULT for item in matched):
        return CommitmentOutcome(
            commitment_id=commitment.commitment_id,
            status=OutcomeStatus.NULL_RESULT,
            finding_ids=matched_ids,
            event_ids=event_ids,
        )
    if matched:
        return CommitmentOutcome(
            commitment_id=commitment.commitment_id,
            status=OutcomeStatus.LIMITED,
            finding_ids=matched_ids,
            reason_code="diagnostic_only",
            event_ids=event_ids,
        )

    if any(item.event_type is EventType.SYSTEM_FAILED for item in events):
        return CommitmentOutcome(
            commitment_id=commitment.commitment_id,
            status=OutcomeStatus.SYSTEM_FAILED,
            reason_code="system_failed",
            event_ids=event_ids,
        )
    if any(item.event_type is EventType.USER_INTERRUPTED for item in events):
        return CommitmentOutcome(
            commitment_id=commitment.commitment_id,
            status=OutcomeStatus.INTERRUPTED,
            reason_code="user_interrupted",
            event_ids=event_ids,
        )
    if any(item.event_type is EventType.USER_INPUT_REQUIRED for item in events):
        return CommitmentOutcome(
            commitment_id=commitment.commitment_id,
            status=OutcomeStatus.NEEDS_INPUT,
            reason_code="user_input_required",
            event_ids=event_ids,
        )

    accepted_capabilities = set(commitment.accepted_method_capabilities)
    relevant_failures = [
        item
        for item in events
        if item.event_type is EventType.TOOL_FAILED
        and item.capability in accepted_capabilities
    ]
    succeeded_capabilities = {
        item.capability
        for item in events
        if item.event_type is EventType.TOOL_SUCCEEDED
        and item.capability in accepted_capabilities
    }
    failed_capabilities = {item.capability for item in relevant_failures}
    if accepted_capabilities and failed_capabilities >= accepted_capabilities and not succeeded_capabilities:
        reason = relevant_failures[-1].error_code or "declared_methods_failed"
        return CommitmentOutcome(
            commitment_id=commitment.commitment_id,
            status=OutcomeStatus.UNAVAILABLE,
            reason_code=reason,
            event_ids=event_ids,
        )
    if any(item.event_type is EventType.BUDGET_EXHAUSTED for item in events):
        return CommitmentOutcome(
            commitment_id=commitment.commitment_id,
            status=OutcomeStatus.LIMITED,
            reason_code="budget_exhausted",
            event_ids=event_ids,
        )
    if events:
        return CommitmentOutcome(
            commitment_id=commitment.commitment_id,
            status=OutcomeStatus.RUNNING,
            event_ids=event_ids,
        )
    return CommitmentOutcome(
        commitment_id=commitment.commitment_id,
        status=OutcomeStatus.PENDING,
    )


def project_run(
    commitments: Iterable[Commitment],
    events: Iterable[ExecutionEvent],
    findings: Iterable[Finding],
) -> RunProjection:
    """Compute run state from immutable facts.

    This function deliberately exposes no mutation or completion API.  Reusing
    the same facts always yields the same projection.
    """

    commitment_list = list(commitments)
    event_groups: dict[str, list[ExecutionEvent]] = defaultdict(list)
    finding_list = list(findings)
    for event in events:
        event_groups[event.commitment_id].append(event)

    outcomes = {
        commitment.commitment_id: _project_commitment(
            commitment,
            event_groups.get(commitment.commitment_id, []),
            finding_list,
        )
        for commitment in commitment_list
    }
    core_ids = [
        item.commitment_id
        for item in commitment_list
        if item.priority is CommitmentPriority.CORE
    ]
    blocking = tuple(
        commitment_id
        for commitment_id in core_ids
        if outcomes[commitment_id].status not in PUBLISHABLE_OUTCOMES
    )
    return RunProjection(
        outcomes=outcomes,
        publishable=bool(core_ids) and not blocking,
        blocking_commitment_ids=blocking,
    )
