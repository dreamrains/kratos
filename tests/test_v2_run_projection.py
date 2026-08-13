from data_agent.v2.models import (
    ClaimClass,
    Commitment,
    CommitmentPriority,
    EventType,
    ExecutionEvent,
    Finding,
    FindingKind,
    OutcomeStatus,
)
from data_agent.v2.projection import project_run


def _core() -> Commitment:
    return Commitment(
        commitment_id="c_core",
        priority=CommitmentPriority.CORE,
        question="销售额的总体情况如何？",
        dataset_version_ids=("dv_sales",),
        accepted_result_kinds=(FindingKind.ESTIMATE, FindingKind.NULL_RESULT),
        accepted_method_capabilities=("analysis.describe",),
    )


def test_successful_tool_event_does_not_assert_completion():
    result = project_run(
        commitments=[_core()],
        events=[
            ExecutionEvent(
                event_id="ev_1",
                run_id="run_1",
                commitment_id="c_core",
                event_type=EventType.TOOL_SUCCEEDED,
                tool_name="describe_dataset",
                capability="analysis.describe",
                dataset_version_ids=("dv_sales",),
            )
        ],
        findings=[],
    )

    assert result.outcomes["c_core"].status is OutcomeStatus.RUNNING
    assert result.publishable is False

def test_matching_finding_computes_supported_outcome():
    result = project_run(
        commitments=[_core()],
        events=[],
        findings=[
            Finding(
                finding_id="f_sales_mean",
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
        ],
    )

    assert result.outcomes["c_core"].status is OutcomeStatus.SUPPORTED
    assert result.outcomes["c_core"].finding_ids == ("f_sales_mean",)
    assert result.publishable is True


def test_null_result_is_a_publishable_analysis_outcome():
    result = project_run(
        commitments=[_core()],
        events=[],
        findings=[
            Finding(
                finding_id="f_null",
                commitment_id="c_core",
                finding_kind=FindingKind.NULL_RESULT,
                dataset_version_ids=("dv_sales",),
                metric_identity="sales.group_difference",
                method_capability="analysis.describe",
                limitations=("当前样本未显示可辨认差异",),
                maximum_claim_class=ClaimClass.DESCRIPTIVE,
                computation_ref="comp_null",
            )
        ],
    )

    assert result.outcomes["c_core"].status is OutcomeStatus.NULL_RESULT
    assert result.publishable is True


def test_exhausted_declared_method_is_publishable_as_unavailable():
    result = project_run(
        commitments=[_core()],
        events=[
            ExecutionEvent(
                event_id="ev_fail",
                run_id="run_1",
                commitment_id="c_core",
                event_type=EventType.TOOL_FAILED,
                tool_name="describe_dataset",
                capability="analysis.describe",
                dataset_version_ids=("dv_sales",),
                error_code="dependency_unavailable",
            )
        ],
        findings=[],
    )

    assert result.outcomes["c_core"].status is OutcomeStatus.UNAVAILABLE
    assert result.publishable is True


def test_optional_chart_failure_does_not_block_supported_core():
    chart = Commitment(
        commitment_id="c_chart",
        priority=CommitmentPriority.OPTIONAL,
        question="绘制趋势图",
        dataset_version_ids=("dv_sales",),
        accepted_result_kinds=(FindingKind.ESTIMATE,),
        accepted_method_capabilities=("visual.chart",),
    )
    result = project_run(
        commitments=[_core(), chart],
        events=[
            ExecutionEvent(
                event_id="ev_chart_fail",
                run_id="run_1",
                commitment_id="c_chart",
                event_type=EventType.TOOL_FAILED,
                capability="visual.chart",
                error_code="render_failed",
            )
        ],
        findings=[
            Finding(
                finding_id="f_sales",
                commitment_id="c_core",
                finding_kind=FindingKind.ESTIMATE,
                dataset_version_ids=("dv_sales",),
                metric_identity="sales.mean",
                method_capability="analysis.describe",
                estimate=120.0,
                maximum_claim_class=ClaimClass.DESCRIPTIVE,
                computation_ref="comp_sales",
            )
        ],
    )

    assert result.publishable is True
    assert result.outcomes["c_chart"].status is OutcomeStatus.UNAVAILABLE


def test_process_language_has_no_effect_on_projection():
    event = ExecutionEvent(
        event_id="ev_commentary",
        run_id="run_1",
        commitment_id="c_core",
        event_type=EventType.TOOL_STARTED,
        message="最后生成两张支撑图表",
    )

    result = project_run([_core()], [event], [])

    assert result.outcomes["c_core"].status is OutcomeStatus.RUNNING
    assert result.publishable is False


def test_group_means_do_not_complete_group_comparison_commitment():
    commitment = Commitment(
        commitment_id="c_group",
        priority=CommitmentPriority.CORE,
        question="A 与 B 的收入是否不同？",
        dataset_version_ids=("dv_groups",),
        accepted_result_kinds=(
            FindingKind.GROUP_COMPARISON,
            FindingKind.NULL_RESULT,
            FindingKind.LIMITATION,
        ),
        accepted_method_capabilities=("analysis.group_comparison",),
    )
    group_mean = Finding(
        finding_id="f_group_a_mean",
        commitment_id="c_group",
        finding_kind=FindingKind.ESTIMATE,
        dataset_version_ids=("dv_groups",),
        metric_identity="revenue.mean",
        feature_identity="group:channel:A",
        method_capability="analysis.group_comparison",
        estimate=100,
        maximum_claim_class=ClaimClass.DESCRIPTIVE,
        computation_ref="comp_group",
    )
    succeeded = ExecutionEvent(
        event_id="ev_group_success",
        run_id="run_group",
        commitment_id="c_group",
        event_type=EventType.TOOL_SUCCEEDED,
        capability="analysis.group_comparison",
        dataset_version_ids=("dv_groups",),
    )

    result = project_run([commitment], [succeeded], [group_mean])

    assert result.outcomes["c_group"].status is OutcomeStatus.RUNNING
    assert result.publishable is False


def test_period_summary_does_not_complete_time_trend_commitment():
    commitment = Commitment(
        commitment_id="c_time",
        priority=CommitmentPriority.CORE,
        question="销售是否随时间变化？",
        dataset_version_ids=("dv_time",),
        accepted_result_kinds=(
            FindingKind.TIME_TREND,
            FindingKind.NULL_RESULT,
            FindingKind.LIMITATION,
        ),
        accepted_method_capabilities=("analysis.time_trend",),
    )
    period_summary = Finding(
        finding_id="f_period_mean",
        commitment_id="c_time",
        finding_kind=FindingKind.ESTIMATE,
        dataset_version_ids=("dv_time",),
        metric_identity="column:sales:period_summary",
        feature_identity="time:date:daily",
        method_capability="analysis.time_trend",
        estimate=100,
        maximum_claim_class=ClaimClass.DESCRIPTIVE,
        computation_ref="comp_time",
    )

    result = project_run([commitment], [], [period_summary])

    assert result.outcomes["c_time"].status is OutcomeStatus.PENDING
    assert result.publishable is False


def test_historical_summary_does_not_complete_forecast_commitment():
    commitment = Commitment(
        commitment_id="c_forecast",
        priority=CommitmentPriority.CORE,
        question="未来七天是多少？",
        dataset_version_ids=("dv_forecast",),
        accepted_result_kinds=(FindingKind.FORECAST, FindingKind.LIMITATION),
        accepted_method_capabilities=("analysis.forecast_baseline",),
    )
    history = Finding(
        finding_id="f_history",
        commitment_id="c_forecast",
        finding_kind=FindingKind.ESTIMATE,
        dataset_version_ids=("dv_forecast",),
        metric_identity="column:sales:historical_summary",
        method_capability="analysis.forecast_baseline",
        maximum_claim_class=ClaimClass.DESCRIPTIVE,
        computation_ref="comp_forecast",
    )

    result = project_run([commitment], [], [history])

    assert result.outcomes["c_forecast"].status is OutcomeStatus.PENDING
    assert result.publishable is False
