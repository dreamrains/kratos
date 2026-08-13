from data_agent.v2.answer import compile_answer
from data_agent.v2.models import (
    AnswerBlockDraft,
    AnswerBlockType,
    CalibrationAction,
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
    answer = compile_answer(
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

    assert answer.blocks[0].calibration is CalibrationAction.REPLACE_WITH_DIAGNOSTIC
    assert answer.calibrations[0].reason_code == "missing_support_refs"


def test_claim_class_cannot_exceed_finding_ceiling():
    answer = compile_answer(
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

    assert answer.blocks[0].calibration is CalibrationAction.REPLACE_WITH_DIAGNOSTIC
    assert answer.calibrations[0].reason_code == "claim_class_exceeds_ceiling"


def test_canonical_value_must_match_supported_finding():
    answer = compile_answer(
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

    assert answer.blocks[0].calibration is CalibrationAction.REPLACE_WITH_DIAGNOSTIC
    assert answer.calibrations[0].reason_code == "canonical_value_mismatch"


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


def test_invalid_material_block_is_replaced_without_deleting_supported_blocks():
    answer = compile_answer(
        drafts=[
            AnswerBlockDraft(
                block_id="b_valid",
                block_type=AnswerBlockType.EXECUTIVE_ANSWER,
                support_refs=("f_mean",),
                headline="直接回答",
                narrative="当前数据的平均销售额为 120 元。",
                claim_class=ClaimClass.DESCRIPTIVE,
                canonical_values=(120.0,),
            ),
            AnswerBlockDraft(
                block_id="b_overclaim",
                block_type=AnswerBlockType.KEY_FINDING,
                support_refs=("f_mean",),
                headline="未经支持的因果结论",
                narrative="提高投入将导致销售增长。",
                claim_class=ClaimClass.CAUSAL,
            ),
        ],
        findings=[_finding()],
        outcomes={},
    )

    assert [block.block_id for block in answer.blocks] == ["b_valid", "b_overclaim"]
    assert answer.blocks[0].calibration == CalibrationAction.SUPPORTED
    assert answer.blocks[1].calibration == CalibrationAction.REPLACE_WITH_DIAGNOSTIC
    assert "证据等级" in answer.blocks[1].narrative
    assert answer.calibrations[1].reason_code == "claim_class_exceeds_ceiling"


def test_invalid_optional_chart_block_is_omitted_without_blocking_answer():
    answer = compile_answer(
        drafts=[
            AnswerBlockDraft(
                block_id="b_valid",
                block_type=AnswerBlockType.EXECUTIVE_ANSWER,
                support_refs=("f_mean",),
                headline="直接回答",
                narrative="当前数据的平均销售额为 120 元。",
                claim_class=ClaimClass.DESCRIPTIVE,
                canonical_values=(120.0,),
            ),
            AnswerBlockDraft(
                block_id="b_chart",
                block_type=AnswerBlockType.CHART,
                headline="无支撑图表",
                narrative="图表显示销售额变化。",
            ),
        ],
        findings=[_finding()],
        outcomes={},
    )

    assert [block.block_id for block in answer.blocks] == ["b_valid"]
    assert answer.calibrations[1].action is CalibrationAction.OMIT_OPTIONAL
