import pytest

from data_agent.v2.answer import AnswerCompilationError, compile_answer
from data_agent.v2.models import (
    AnswerBlockDraft,
    AnswerBlockType,
    ClaimClass,
    CommitmentOutcome,
    Finding,
    FindingKind,
    OutcomeStatus,
)


def _finding() -> Finding:
    return Finding(
        finding_id="f_mean",
        commitment_id="c_core",
        finding_kind=FindingKind.ESTIMATE,
        dataset_version_ids=("dv_sales",),
        metric_identity="sales.mean",
        method_capability="analysis.describe",
        estimate=120.0,
        unit="CNY",
        maximum_claim_class=ClaimClass.DESCRIPTIVE,
        computation_ref="comp_1",
    )


def test_material_block_requires_support_reference():
    with pytest.raises(AnswerCompilationError, match="support_refs"):
        compile_answer(
            drafts=[
                AnswerBlockDraft(
                    block_id="b1",
                    block_type=AnswerBlockType.KEY_FINDING,
                    headline="核心发现",
                    narrative="平均销售额为 120 元。",
                    claim_class=ClaimClass.DESCRIPTIVE,
                )
            ],
            findings=[_finding()],
            outcomes={},
        )


def test_claim_class_cannot_exceed_finding_ceiling():
    with pytest.raises(AnswerCompilationError, match="claim class"):
        compile_answer(
            drafts=[
                AnswerBlockDraft(
                    block_id="b1",
                    block_type=AnswerBlockType.KEY_FINDING,
                    support_refs=("f_mean",),
                    headline="核心发现",
                    narrative="提高投入将导致销售增长。",
                    claim_class=ClaimClass.CAUSAL,
                )
            ],
            findings=[_finding()],
            outcomes={},
        )


def test_canonical_value_must_match_supported_finding():
    with pytest.raises(AnswerCompilationError, match="canonical value"):
        compile_answer(
            drafts=[
                AnswerBlockDraft(
                    block_id="b1",
                    block_type=AnswerBlockType.KEY_FINDING,
                    support_refs=("f_mean",),
                    headline="核心发现",
                    narrative="平均销售额为 1,200 元。",
                    claim_class=ClaimClass.DESCRIPTIVE,
                    canonical_values=(1200.0,),
                )
            ],
            findings=[_finding()],
            outcomes={},
        )


def test_valid_finding_block_compiles_without_internal_markers():
    answer = compile_answer(
        drafts=[
            AnswerBlockDraft(
                block_id="b1",
                block_type=AnswerBlockType.EXECUTIVE_ANSWER,
                support_refs=("f_mean",),
                headline="直接回答",
                narrative="该数据中的平均销售额为 120 元。",
                claim_class=ClaimClass.DESCRIPTIVE,
                canonical_values=(120.0,),
            )
        ],
        findings=[_finding()],
        outcomes={},
    )

    assert answer.blocks[0].support_refs == ("f_mean",)
    assert "[[evidence:" not in answer.markdown
    assert "平均销售额为 120 元" in answer.markdown


def test_unavailable_outcome_can_compile_complete_diagnostic_answer():
    outcome = CommitmentOutcome(
        commitment_id="c_core",
        status=OutcomeStatus.UNAVAILABLE,
        reason_code="dependency_unavailable",
    )
    answer = compile_answer(
        drafts=[
            AnswerBlockDraft(
                block_id="b_limit",
                block_type=AnswerBlockType.LIMITATION,
                support_refs=("outcome:c_core",),
                headline="当前无法完成该估计",
                narrative="统计依赖不可用，因此目前不能可靠给出估计值。",
            )
        ],
        findings=[],
        outcomes={"c_core": outcome},
    )

    assert answer.blocks[0].support_refs == ("outcome:c_core",)
    assert "不能可靠给出估计值" in answer.markdown
