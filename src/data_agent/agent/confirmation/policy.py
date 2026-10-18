"""Deterministic trigger policy for confirmation candidates."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from data_agent.agent.confirmation.decision import (
    default_is_host_verified,
    is_method_approval_shaped,
    represents_business_gap,
    stable_decision_key,
    resolved_question_records,
)
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
    reused_question_id: str = ""


class QuestionPolicy:
    """Accept only questions tied to material, answerable operations.

    IC1 contract: only a real business semantic gap may suspend the user.
    Method approvals downgrade to advisory; a truthy safe_default alone is
    not an advisory basis unless its origin is host-verified (Q12).
    """

    def evaluate(
        self,
        candidate: QuestionCandidate,
        *,
        existing: Iterable[ConfirmationRecord] = (),
        allow_advisory: bool = True,
    ) -> PolicyResult:
        existing = tuple(existing)
        if candidate.resolution_params.get("question_bindings"):
            return self._evaluate_questions(candidate, existing=existing, allow_advisory=allow_advisory)
        if candidate.resolution_params.get("host_nonblocking_reason"):
            return self._nonblocking(candidate.resolution_params["host_nonblocking_reason"], allow_advisory)
        reused = self._matching_resolution(candidate, existing)
        if reused is not None:
            return PolicyResult(
                disposition=RequestDisposition.REUSED,
                reason="A still-valid resolution already covers this decision.",
                reused_confirmation_id=reused.confirmation_id,
                reused_question_id=getattr(reused, "resolution_params", {}).get("_question_id", ""),
            )

        if candidate.source == "host_measurement_mapping.v1" and any(
            record.status == ConfirmationStatus.SKIPPED
            and record.decision_key == candidate.decision_key
            and record.data_version == candidate.data_version
            and record.spec_version == candidate.spec_version
            for record in existing
        ):
            return self._nonblocking(
                "用户已跳过同版本的指标映射确认；保持该映射未评估。",
                allow_advisory,
            )

        if is_method_approval_shaped(candidate):
            return self._nonblocking(
                "方法选择是系统内部决策，不构成需要用户确认的业务缺口。",
                allow_advisory,
            )

        if (
            candidate.resolution_params.get("confirmation_type") == "data_quality_confirmation"
            and not self._has_host_field_risk(candidate)
        ):
            return self._nonblocking(
                "缺少宿主可核验的字段风险与计算依赖，不据此暂停。请保留已核实"
                "的观察，按来源和覆盖范围未经证实给出条件式指引；需要改变计算"
                "值的具体字段口径应由宿主风险证据支持后再确认。",
                allow_advisory,
            )

        if candidate.safe_default and default_is_host_verified(candidate):
            return self._nonblocking(
                "A documented safe default is available.",
                allow_advisory,
            )
        if not candidate.operation or not candidate.blocking_surfaces:
            return self._nonblocking(
                "The candidate is not tied to a blocked concrete operation.",
                allow_advisory,
            )
        if not represents_business_gap(candidate):
            return self._nonblocking(
                "The candidate does not name a concrete business decision, "
                "missing value, and affected operations.",
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

    def _evaluate_questions(self, candidate, *, existing, allow_advisory):
        from dataclasses import fields, replace
        import json
        bindings, visible = [], []
        for original in candidate.resolution_params["question_bindings"]:
            request = ConfirmationRequest.from_dict(original["request"])
            member = QuestionCandidate(**{field.name: getattr(request, field.name) for field in fields(QuestionCandidate)})
            result = self.evaluate(member, existing=existing, allow_advisory=allow_advisory)
            binding = dict(original, disposition=result.disposition.value, reason=result.reason)
            if result.disposition == RequestDisposition.REUSED:
                resolved = self._matching_resolution(member, existing)
                binding.update(answer=resolved.response, source_confirmation_id=resolved.confirmation_id,
                               source_question_id=result.reused_question_id)
            elif result.disposition == RequestDisposition.CONFIRMATION:
                visible.append(dict(original["input"], question_id=original["question_id"],
                                    options=[o.to_dict() for o in request.options]))
            bindings.append(binding)
        if not visible:
            return self._nonblocking("各题已逐项裁决：" + json.dumps([
                {"question": b["request"]["question"], "disposition": b["disposition"],
                 "answer": b.get("answer"), "reason": b["reason"]} for b in bindings
            ], ensure_ascii=False), allow_advisory)
        params = dict(candidate.resolution_params, question_bindings=bindings,
                      context=json.dumps(visible, ensure_ascii=False))
        request = ConfirmationRequest.from_candidate(replace(candidate,
            question="; ".join(q["question"] for q in visible), resolution_params=params))
        return PolicyResult(RequestDisposition.CONFIRMATION,
                            "Only unresolved material questions require an answer.", request=request)

    @staticmethod
    def _nonblocking(reason: str, allow_advisory: bool) -> PolicyResult:
        disposition = (
            RequestDisposition.ADVISORY
            if allow_advisory
            else RequestDisposition.REJECTED
        )
        return PolicyResult(disposition=disposition, reason=reason)

    @staticmethod
    def _has_host_field_risk(candidate: QuestionCandidate) -> bool:
        params = candidate.resolution_params
        return bool(
            candidate.source == "question_need_detector"
            and params.get("host_risk_fields")
            and params.get("host_affected_routes")
        )

    @staticmethod
    def _matching_resolution(
        candidate: QuestionCandidate,
        existing: Iterable[ConfirmationRecord],
    ) -> ConfirmationRecord | None:
        logical_key = stable_decision_key(candidate, session_id=candidate.session_id)
        for record in (item for original in existing for item in resolved_question_records(original)):
            if record.status != ConfirmationStatus.RESOLVED:
                continue
            reference = candidate.resolution_params.get("host_reuse_decision_id")
            if reference and reference != (record.resolution_params.get("_question_id") or record.confirmation_id):
                continue
            if record.decision_key != candidate.decision_key and (
                not logical_key or record.decision_key != logical_key
            ):
                continue
            if record.data_version != candidate.data_version:
                continue
            if record.spec_version != candidate.spec_version:
                continue
            return record
        return None
