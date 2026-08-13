from __future__ import annotations

import math
from collections.abc import Iterable, Mapping

from data_agent.v2.models import (
    CLAIM_CLASS_RANK,
    AnswerBlock,
    AnswerBlockDraft,
    AnswerBlockType,
    CommitmentOutcome,
    CompiledAnswer,
    Finding,
)


class AnswerCompilationError(ValueError):
    pass


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


def _same_value(left: object, right: object) -> bool:
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return math.isclose(float(left), float(right), rel_tol=1e-9, abs_tol=1e-12)
    return str(left) == str(right)


def _validate_draft(
    draft: AnswerBlockDraft,
    finding_by_id: Mapping[str, Finding],
    outcomes: Mapping[str, CommitmentOutcome],
) -> None:
    if draft.block_type in _MATERIAL_BLOCKS and not draft.support_refs:
        raise AnswerCompilationError(f"block {draft.block_id} requires support_refs")

    supported_findings: list[Finding] = []
    for reference in draft.support_refs:
        if reference.startswith("outcome:"):
            commitment_id = reference.removeprefix("outcome:")
            if commitment_id not in outcomes:
                raise AnswerCompilationError(
                    f"block {draft.block_id} references unknown outcome {commitment_id}"
                )
            continue
        finding = finding_by_id.get(reference)
        if finding is None:
            raise AnswerCompilationError(
                f"block {draft.block_id} references unknown finding {reference}"
            )
        supported_findings.append(finding)

    if draft.claim_class is not None and supported_findings:
        ceiling = min(
            CLAIM_CLASS_RANK[item.maximum_claim_class]
            for item in supported_findings
        )
        if CLAIM_CLASS_RANK[draft.claim_class] > ceiling:
            raise AnswerCompilationError(
                f"block {draft.block_id} claim class exceeds finding ceiling"
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
                    f"block {draft.block_id} canonical value is not supported"
                )

    if "[[evidence:" in draft.narrative:
        raise AnswerCompilationError("internal evidence markers are not valid V2 answer content")


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
    for draft in draft_list:
        _validate_draft(draft, finding_by_id, outcomes)
        blocks.append(
            AnswerBlock(
                block_id=draft.block_id,
                block_type=draft.block_type,
                headline=draft.headline,
                narrative=draft.narrative,
                support_refs=draft.support_refs,
                claim_class=draft.claim_class,
                canonical_values=draft.canonical_values,
                limitations=draft.limitations,
                chart_refs=draft.chart_refs,
            )
        )
    block_tuple = tuple(blocks)
    return CompiledAnswer(blocks=block_tuple, markdown=_render_markdown(block_tuple))
