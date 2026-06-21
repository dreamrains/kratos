"""Deterministic trigger policy for confirmation candidates."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from data_agent.agent.confirmation.models import (
    ConfirmationContractError,
    ConfirmationRecord,
    ConfirmationRequest,
    ConfirmationStatus,
    QuestionCandidate,
)


class RequestDisposition(str, Enum):
    CONFIRMATION = "confirmation"
    ADVISORY = "advisory"
    REUSED = "reused"
    REJECTED = "rejected"


@dataclass(frozen=True)
class PolicyResult:
    disposition: RequestDisposition
    reason: str
    request: ConfirmationRequest | None = None
    reused_confirmation_id: str = ""


class QuestionPolicy:
    """Accept only questions tied to material, answerable operations."""

    def evaluate(
        self,
        candidate: QuestionCandidate,
        *,
        existing: Iterable[ConfirmationRecord] = (),
        allow_advisory: bool = True,
    ) -> PolicyResult:
        reused = self._matching_resolution(candidate, existing)
        if reused is not None:
            return PolicyResult(
                disposition=RequestDisposition.REUSED,
                reason="A still-valid resolution already covers this decision.",
                reused_confirmation_id=reused.confirmation_id,
            )

        if candidate.safe_default:
            return self._nonblocking(
                "A documented safe default is available.",
                allow_advisory,
            )
        if not candidate.operation or not candidate.blocking_surfaces:
            return self._nonblocking(
                "The candidate is not tied to a blocked concrete operation.",
                allow_advisory,
            )

        try:
            request = ConfirmationRequest.from_candidate(candidate)
        except ConfirmationContractError as exc:
            return PolicyResult(RequestDisposition.REJECTED, str(exc))
        return PolicyResult(
            disposition=RequestDisposition.CONFIRMATION,
            reason="The decision materially blocks a concrete operation.",
            request=request,
        )

    @staticmethod
    def _nonblocking(reason: str, allow_advisory: bool) -> PolicyResult:
        disposition = (
            RequestDisposition.ADVISORY
            if allow_advisory
            else RequestDisposition.REJECTED
        )
        return PolicyResult(disposition=disposition, reason=reason)

    @staticmethod
    def _matching_resolution(
        candidate: QuestionCandidate,
        existing: Iterable[ConfirmationRecord],
    ) -> ConfirmationRecord | None:
        for record in existing:
            if record.status != ConfirmationStatus.RESOLVED:
                continue
            if record.decision_key != candidate.decision_key:
                continue
            if record.data_version != candidate.data_version:
                continue
            if record.spec_version != candidate.spec_version:
                continue
            return record
        return None
