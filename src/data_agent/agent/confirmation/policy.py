"""Deterministic trigger policy for confirmation candidates."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from data_agent.agent.confirmation.decision import (
    default_is_host_verified,
    is_data_nature_question,
    is_method_approval_shaped,
    represents_business_gap,
    stable_decision_key,
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
        reused = self._matching_resolution(candidate, existing)
        if reused is not None:
            return PolicyResult(
                disposition=RequestDisposition.REUSED,
                reason="A still-valid resolution already covers this decision.",
                reused_confirmation_id=reused.confirmation_id,
            )

        if is_method_approval_shaped(candidate):
            return self._nonblocking(
                "方法选择是系统内部决策，不构成需要用户确认的业务缺口。",
                allow_advisory,
            )

        if is_data_nature_question(candidate):
            # P1-5b：数据性质（示例/测试/真实/抽样）不由提问确立，也不改变
            # 任何已计算数值——来源状态由发布合同按"未经证实"渲染，转为
            # 条件式发布指引而不是挂起。
            return self._nonblocking(
                "数据性质（示例/测试/真实/抽样）不需要用户确认：请按来源未知"
                "直接以条件式指引发布——若为示例/测试数据则结论仅演示流程、"
                "不作业务解读；若为真实数据则先满足字段口径与时间窗等前提再"
                "扩展分析；发布包会按'未经证实'标注来源状态。",
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
        logical_key = stable_decision_key(candidate, session_id=candidate.session_id)
        for record in existing:
            if record.status != ConfirmationStatus.RESOLVED:
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
