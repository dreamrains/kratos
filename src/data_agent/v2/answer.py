from __future__ import annotations

import math
from collections.abc import Iterable, Mapping

from data_agent.v2.models import (
    CLAIM_CLASS_RANK,
    AnswerBlock,
    AnswerBlockDraft,
    AnswerBlockType,
    BlockCalibration,
    CalibrationAction,
    CommitmentOutcome,
    CompiledAnswer,
    Finding,
)


class AnswerCompilationError(ValueError):
    def __init__(self, message: str, *, reason_code: str = "invalid_block") -> None:
        super().__init__(message)
        self.reason_code = reason_code


_MATERIAL_BLOCKS = frozenset(
    {
        AnswerBlockType.EXECUTIVE_ANSWER,
        AnswerBlockType.KEY_FINDING,
        AnswerBlockType.COMPARISON,
        AnswerBlockType.CHART,
        AnswerBlockType.METHOD,
        AnswerBlockType.UNCERTAINTY,
        AnswerBlockType.LIMITATION,
        AnswerBlockType.RECOMMENDATION,
        AnswerBlockType.NEXT_INVESTIGATION,
    }
)

_OPTIONAL_BLOCKS = frozenset(
    {
        AnswerBlockType.CHART,
        AnswerBlockType.RECOMMENDATION,
        AnswerBlockType.NEXT_INVESTIGATION,
        AnswerBlockType.SUPPLEMENTAL,
    }
)


def _same_value(left: object, right: object) -> bool:
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return math.isclose(float(left), float(right), rel_tol=1e-9, abs_tol=1e-12)
    return str(left) == str(right)


def _validate_draft(
    draft: AnswerBlockDraft,
    finding_by_id: Mapping[str, Finding],
    outcomes: Mapping[str, CommitmentOutcome],
) -> None:
    if draft.block_type is AnswerBlockType.SUPPLEMENTAL:
        if draft.claim_class is not None or draft.canonical_values:
            raise AnswerCompilationError(
                "exploratory supplemental blocks cannot declare verified claims",
                reason_code="exploratory_claim_not_allowed",
            )
    if draft.block_type in _MATERIAL_BLOCKS and not draft.support_refs:
        raise AnswerCompilationError(
            f"block {draft.block_id} requires support_refs",
            reason_code="missing_support_refs",
        )

    supported_findings: list[Finding] = []
    for reference in draft.support_refs:
        if reference.startswith("outcome:"):
            commitment_id = reference.removeprefix("outcome:")
            if commitment_id not in outcomes:
                raise AnswerCompilationError(
                    f"block {draft.block_id} references unknown outcome {commitment_id}",
                    reason_code="unknown_outcome",
                )
            continue
        finding = finding_by_id.get(reference)
        if finding is None:
            raise AnswerCompilationError(
                f"block {draft.block_id} references unknown finding {reference}",
                reason_code="unknown_finding",
            )
        supported_findings.append(finding)

    if draft.claim_class is not None and supported_findings:
        ceiling = min(
            CLAIM_CLASS_RANK[item.maximum_claim_class]
            for item in supported_findings
        )
        if CLAIM_CLASS_RANK[draft.claim_class] > ceiling:
            raise AnswerCompilationError(
                f"block {draft.block_id} claim class exceeds finding ceiling",
                reason_code="claim_class_exceeds_ceiling",
            )

    if draft.canonical_values:
        supported_values: list[object] = [
            item.estimate
            for item in supported_findings
            if item.estimate is not None
        ]
        supported_values.extend(
            item.effective_sample
            for item in supported_findings
            if item.effective_sample is not None
        )
        for item in supported_findings:
            supported_values.extend(item.uncertainty.values())
        for value in draft.canonical_values:
            if not any(_same_value(value, supported) for supported in supported_values):
                raise AnswerCompilationError(
                    f"block {draft.block_id} canonical value is not supported",
                    reason_code="canonical_value_mismatch",
                )

    if "[[evidence:" in draft.narrative:
        raise AnswerCompilationError(
            "internal evidence markers are not valid V2 answer content",
            reason_code="internal_protocol_marker",
        )


def _valid_support_refs(
    draft: AnswerBlockDraft,
    finding_by_id: Mapping[str, Finding],
    outcomes: Mapping[str, CommitmentOutcome],
) -> tuple[str, ...]:
    valid: list[str] = []
    for reference in draft.support_refs:
        if reference in finding_by_id:
            valid.append(reference)
        elif reference.startswith("outcome:") and reference.removeprefix("outcome:") in outcomes:
            valid.append(reference)
    return tuple(valid)


def _diagnostic_narrative(reason_code: str) -> str:
    messages = {
        "claim_class_exceeds_ceiling": (
            "该结论的证据等级超过当前分析结果可支持范围，因此未按原表述发布。"
        ),
        "canonical_value_mismatch": (
            "该结论中的数值与结构化计算结果不一致，因此未按原表述发布。"
        ),
        "internal_protocol_marker": (
            "该结论包含内部协议内容，因此未按原表述发布。"
        ),
    }
    return messages.get(
        reason_code,
        "该结论缺少可验证的支撑来源，因此未按原表述发布。",
    )


def _supported_block(draft: AnswerBlockDraft) -> AnswerBlock:
    return AnswerBlock(
        block_id=draft.block_id,
        block_type=draft.block_type,
        headline=draft.headline,
        narrative=draft.narrative,
        support_refs=draft.support_refs,
        claim_class=draft.claim_class,
        canonical_values=draft.canonical_values,
        limitations=draft.limitations,
        chart_refs=draft.chart_refs,
        calibration=(
            CalibrationAction.EXPLORATORY
            if draft.block_type is AnswerBlockType.SUPPLEMENTAL
            else CalibrationAction.SUPPORTED
        ),
    )


def _render_markdown(blocks: Iterable[AnswerBlock]) -> str:
    sections: list[str] = []
    for block in blocks:
        body = block.narrative.strip()
        if block.limitations:
            body += "\n\n" + "\n".join(f"- {item}" for item in block.limitations)
        sections.append(f"## {block.headline}\n\n{body}")
    return "\n\n".join(sections).strip()


def compile_answer(
    drafts: Iterable[AnswerBlockDraft],
    findings: Iterable[Finding],
    outcomes: Mapping[str, CommitmentOutcome],
) -> CompiledAnswer:
    """Validate typed drafts and render canonical Markdown.

    The compiler never invents findings, changes run outcomes, or performs
    fuzzy evidence attachment.
    """

    finding_by_id = {item.finding_id: item for item in findings}
    draft_list = list(drafts)
    if not draft_list:
        raise AnswerCompilationError("at least one answer block is required")
    if len({item.block_id for item in draft_list}) != len(draft_list):
        raise AnswerCompilationError("answer block ids must be unique")

    blocks: list[AnswerBlock] = []
    calibrations: list[BlockCalibration] = []
    for draft in draft_list:
        try:
            _validate_draft(draft, finding_by_id, outcomes)
        except AnswerCompilationError as exc:
            if draft.block_type in _OPTIONAL_BLOCKS:
                calibrations.append(
                    BlockCalibration(
                        block_id=draft.block_id,
                        action=CalibrationAction.OMIT_OPTIONAL,
                        reason_code=exc.reason_code,
                        message=str(exc),
                    )
                )
                continue
            valid_refs = _valid_support_refs(draft, finding_by_id, outcomes)
            blocks.append(
                AnswerBlock(
                    block_id=draft.block_id,
                    block_type=(
                        AnswerBlockType.LIMITATION
                        if valid_refs
                        else AnswerBlockType.SUPPLEMENTAL
                    ),
                    headline="结论已校准",
                    narrative=_diagnostic_narrative(exc.reason_code),
                    support_refs=valid_refs,
                    calibration=CalibrationAction.REPLACE_WITH_DIAGNOSTIC,
                )
            )
            calibrations.append(
                BlockCalibration(
                    block_id=draft.block_id,
                    action=CalibrationAction.REPLACE_WITH_DIAGNOSTIC,
                    reason_code=exc.reason_code,
                    message=str(exc),
                )
            )
            continue
        block = _supported_block(draft)
        blocks.append(block)
        calibrations.append(
            BlockCalibration(
                block_id=draft.block_id,
                action=block.calibration,
            )
        )
    if not blocks:
        raise AnswerCompilationError("no publishable answer blocks remain")
    block_tuple = tuple(blocks)
    return CompiledAnswer(
        blocks=block_tuple,
        markdown=_render_markdown(block_tuple),
        calibrations=tuple(calibrations),
    )
