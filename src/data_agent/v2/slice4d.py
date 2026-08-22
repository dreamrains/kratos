from __future__ import annotations

import hashlib
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Iterator

from data_agent.v2.answer import compile_answer
from data_agent.v2.dataset import DatasetRegistry, DatasetRole
from data_agent.v2.group_chart import build_group_distribution_chart
from data_agent.v2.group_comparison import (
    GroupComparisonResult,
    GroupComparisonSpec,
    analyze_group_comparison,
)
from data_agent.v2.models import (
    AnswerBlockDraft,
    AnswerBlockType,
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
from data_agent.v2.recommendation import ActionRisk, RecommendationIntent
from data_agent.v2.slice1 import RuntimeEvent, _load_frame
from data_agent.v2.store import V2FactStore
from data_agent.v2.time_chart import build_time_series_chart
from data_agent.v2.time_series import (
    TimeAggregation,
    TimeFrequency,
    TimeSeriesResult,
    TimeSeriesSpec,
    analyze_time_series,
)


TIME_CAPABILITY = "analysis.time_trend"
GROUP_CAPABILITY = "analysis.group_comparison"

_FREQUENCY_LABEL = {
    TimeFrequency.DAILY: "日",
    TimeFrequency.WEEKLY: "周",
    TimeFrequency.MONTHLY: "月",
}
_AGGREGATION_LABEL = {
    TimeAggregation.SUM: "求和",
    TimeAggregation.MEAN: "平均",
}


def _source_identity(path: Path) -> str:
    return f"upload:{path.name}:sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _number(value: float | None, digits: int = 3) -> str:
    if value is None:
        return "不可用"
    return f"{value:,.{digits}f}".rstrip("0").rstrip(".")


def _p(value: float | None) -> str:
    if value is None:
        return "不可用"
    return "<0.001" if value < 0.001 else f"={_number(value)}"


def _time_finding(
    result: TimeSeriesResult,
    *,
    commitment_id: str,
    dataset_version_id: str,
    computation_ref: str,
) -> Finding:
    kind = {
        "supported": FindingKind.TIME_TREND,
        "null_result": FindingKind.NULL_RESULT,
        "limited": FindingKind.LIMITATION,
    }[result.status]
    return Finding(
        finding_id=f"finding_{uuid.uuid4().hex}",
        commitment_id=commitment_id,
        finding_kind=kind,
        dataset_version_ids=(dataset_version_id,),
        metric_identity=f"column:{result.metric}",
        feature_identity=f"time:{result.time_field}:{result.frequency.value}",
        method_capability=TIME_CAPABILITY,
        maximum_claim_class=result.maximum_claim_class,
        computation_ref=computation_ref,
        estimate=result.trend_per_period,
        direction=(
            "positive" if result.trend_per_period is not None and result.trend_per_period > 0
            else "negative" if result.trend_per_period is not None and result.trend_per_period < 0
            else "none"
        ),
        effective_sample=result.observed_periods,
        time_scope=f"{result.start_time}/{result.end_time}" if result.start_time else "",
        uncertainty={
            "confidence_low": result.confidence_low,
            "confidence_high": result.confidence_high,
            "p_value": result.p_value,
            "hac_max_lag": result.hac_max_lag,
            "incomplete_boundary_periods": result.incomplete_boundary_periods,
            "reason_code": result.reason_code,
        },
        assumption_results={
            "frequency": result.frequency.value,
            "aggregation": result.aggregation.value,
            "seasonality_control": result.seasonality_control,
            "historical_only": True,
        },
        limitations=result.limitations,
    )


def _group_finding(
    result: GroupComparisonResult,
    *,
    commitment_id: str,
    dataset_version_id: str,
    computation_ref: str,
    analysis_unit: str,
) -> Finding:
    kind = {
        "supported": FindingKind.GROUP_COMPARISON,
        "null_result": FindingKind.NULL_RESULT,
        "limited": FindingKind.LIMITATION,
        "descriptive_ranking": FindingKind.GROUP_COMPARISON,
    }[result.status]
    return Finding(
        finding_id=f"finding_{uuid.uuid4().hex}",
        commitment_id=commitment_id,
        finding_kind=kind,
        dataset_version_ids=(dataset_version_id,),
        metric_identity=f"column:{result.metric}",
        feature_identity=f"group:{result.group_field}",
        population_scope=f"analysis_unit:{analysis_unit}",
        method_capability=GROUP_CAPABILITY,
        maximum_claim_class=result.maximum_claim_class,
        computation_ref=computation_ref,
        estimate=result.difference,
        direction=(
            "second_higher" if result.difference is not None and result.difference > 0
            else "first_higher" if result.difference is not None and result.difference < 0
            else "none"
        ),
        effective_sample=result.effective_units,
        uncertainty={
            "confidence_low": result.confidence_low,
            "confidence_high": result.confidence_high,
            "p_value": result.p_value,
            "hedges_g": result.hedges_g,
            "group_order": result.group_order,
            "reason_code": result.reason_code,
        },
        assumption_results={
            "analysis_unit": analysis_unit,
            "complete_case_rows": result.complete_case_rows,
            "dropped_rows": result.dropped_rows,
        },
        limitations=result.limitations,
    )


class Slice4DMultiFindingRuntime:
    """One run, two commitments, one projection and one typed publisher."""

    def __init__(self, sessions_root: Path | str, inbox_root: Path | str) -> None:
        self.sessions_root = Path(sessions_root)
        self.inbox_root = Path(inbox_root)

    def _source_path(self, filename: str) -> Path:
        safe_name = str(filename or "").strip()
        if not safe_name or Path(safe_name).name != safe_name:
            raise ValueError("filename must be a plain uploaded filename")
        path = self.inbox_root / safe_name
        if not path.is_file():
            raise FileNotFoundError(f"uploaded file not found: {safe_name}")
        return path

    def stream(
        self,
        *,
        session_id: str,
        turn_id: str,
        filename: str,
        time_field: str,
        metric: str,
        frequency: TimeFrequency,
        aggregation: TimeAggregation,
        group: str,
        analysis_unit: str,
        question: str,
        recommendation_intent: RecommendationIntent,
        action_risk: ActionRisk,
        reversible: bool,
    ) -> Iterator[RuntimeEvent]:
        source_path = self._source_path(filename)
        time_spec = TimeSeriesSpec(time_field, metric, frequency, aggregation)
        group_spec = GroupComparisonSpec(metric, group, analysis_unit)
        user_question = str(question or "").strip()
        if not user_question:
            raise ValueError("question is required")
        intent = RecommendationIntent(recommendation_intent)
        risk = ActionRisk(action_risk)
        run_id = f"run_{uuid.uuid4().hex}"
        time_commitment_id = f"commitment_{uuid.uuid4().hex}"
        group_commitment_id = f"commitment_{uuid.uuid4().hex}"
        store = V2FactStore(self.sessions_root, session_id)
        datasets = DatasetRegistry(self.sessions_root, session_id)
        yield RuntimeEvent(
            "turn_started", {"session_id": session_id, "turn_id": turn_id, "run_id": run_id}
        )
        raw_frame = _load_frame(source_path)
        raw = datasets.register_raw(
            source_path.stem, raw_frame, source_identity=_source_identity(source_path)
        )
        analysis = datasets.derive(
            parent_version_id=raw.dataset_version_id,
            frame=raw_frame.copy(deep=True),
            role=DatasetRole.ANALYSIS,
            transform={"operation": "identity_multi_finding_copy", "lossless": True},
        )
        commitments = [
            Commitment(
                commitment_id=time_commitment_id,
                priority=CommitmentPriority.CORE,
                question=f"{metric} 在历史范围内是否存在可靠趋势？",
                dataset_version_ids=(analysis.dataset_version_id,),
                accepted_result_kinds=(
                    FindingKind.TIME_TREND, FindingKind.NULL_RESULT, FindingKind.LIMITATION
                ),
                accepted_method_capabilities=(TIME_CAPABILITY,),
                target_semantics=f"{metric} over {time_field}",
                visualization_intent="conditional:time_series_line",
            ),
            Commitment(
                commitment_id=group_commitment_id,
                priority=CommitmentPriority.CORE,
                question=f"{group} 的两个组在 {metric} 上是否存在可靠差异？",
                dataset_version_ids=(analysis.dataset_version_id,),
                accepted_result_kinds=(
                    FindingKind.GROUP_COMPARISON,
                    FindingKind.NULL_RESULT,
                    FindingKind.LIMITATION,
                ),
                accepted_method_capabilities=(GROUP_CAPABILITY,),
                target_semantics=f"{metric} by {group} at {analysis_unit}",
                visualization_intent="conditional:group_boxplot",
            ),
        ]
        store.append_commitments(run_id, turn_id, commitments)
        yield RuntimeEvent("commitment_snapshot", {"commitments": [asdict(item) for item in commitments]})

        findings: list[Finding] = []
        time_call_id = f"tool_{uuid.uuid4().hex}"
        time_ref = f"computation:{uuid.uuid4().hex}"
        store.append_event(
            ExecutionEvent(
                event_id=f"event_{uuid.uuid4().hex}", run_id=run_id,
                commitment_id=time_commitment_id, event_type=EventType.TOOL_STARTED,
                tool_call_id=time_call_id, tool_name="v2.time_trend",
                capability=TIME_CAPABILITY, dataset_version_ids=(analysis.dataset_version_id,),
            )
        )
        yield RuntimeEvent("tool_started", {"name": "time_trend", "capability": TIME_CAPABILITY})
        time_result = analyze_time_series(
            datasets.get_frame(analysis.dataset_version_id), time_spec
        )
        store.append_event(
            ExecutionEvent(
                event_id=f"event_{uuid.uuid4().hex}", run_id=run_id,
                commitment_id=time_commitment_id, event_type=EventType.TOOL_SUCCEEDED,
                tool_call_id=time_call_id, tool_name="v2.time_trend",
                capability=TIME_CAPABILITY, dataset_version_ids=(analysis.dataset_version_id,),
                result_ref=time_ref,
            )
        )
        time_finding = _time_finding(
            time_result, commitment_id=time_commitment_id,
            dataset_version_id=analysis.dataset_version_id, computation_ref=time_ref,
        )
        findings.append(time_finding)
        store.append_finding(time_finding)
        yield RuntimeEvent("tool_finished", {"name": "time_trend", "result_status": time_result.status})

        group_call_id = f"tool_{uuid.uuid4().hex}"
        group_ref = f"computation:{uuid.uuid4().hex}"
        store.append_event(
            ExecutionEvent(
                event_id=f"event_{uuid.uuid4().hex}", run_id=run_id,
                commitment_id=group_commitment_id, event_type=EventType.TOOL_STARTED,
                tool_call_id=group_call_id, tool_name="v2.group_comparison",
                capability=GROUP_CAPABILITY, dataset_version_ids=(analysis.dataset_version_id,),
            )
        )
        yield RuntimeEvent("tool_started", {"name": "group_comparison", "capability": GROUP_CAPABILITY})
        group_result = analyze_group_comparison(
            datasets.get_frame(analysis.dataset_version_id), group_spec
        )
        store.append_event(
            ExecutionEvent(
                event_id=f"event_{uuid.uuid4().hex}", run_id=run_id,
                commitment_id=group_commitment_id, event_type=EventType.TOOL_SUCCEEDED,
                tool_call_id=group_call_id, tool_name="v2.group_comparison",
                capability=GROUP_CAPABILITY, dataset_version_ids=(analysis.dataset_version_id,),
                result_ref=group_ref,
            )
        )
        group_finding = _group_finding(
            group_result, commitment_id=group_commitment_id,
            dataset_version_id=analysis.dataset_version_id, computation_ref=group_ref,
            analysis_unit=analysis_unit,
        )
        findings.append(group_finding)
        store.append_finding(group_finding)
        yield RuntimeEvent(
            "tool_finished", {"name": "group_comparison", "result_status": group_result.status}
        )

        time_chart_ids: tuple[str, ...] = ()
        group_chart_ids: tuple[str, ...] = ()
        if time_result.status in {"supported", "null_result"} and time_result.series_times:
            try:
                artifact, html = build_time_series_chart(
                    time_result,
                    dataset_version_id=analysis.dataset_version_id,
                    finding_refs=(time_finding.finding_id,),
                    title=f"{metric} 的历史{_FREQUENCY_LABEL[time_spec.frequency]}趋势",
                )
                store.write_chart_artifact(artifact, html)
                time_chart_ids = (artifact.chart_id,)
                store.append_event(
                    ExecutionEvent(
                        event_id=f"event_{uuid.uuid4().hex}", run_id=run_id,
                        commitment_id=time_commitment_id,
                        event_type=EventType.ARTIFACT_CREATED,
                        tool_name="v2.time_chart_renderer", capability="visual.chart",
                        dataset_version_ids=(analysis.dataset_version_id,),
                        result_ref=artifact.chart_id,
                    )
                )
                yield RuntimeEvent("artifact_created", {"artifact": asdict(artifact)})
            except Exception as exc:
                store.append_event(
                    ExecutionEvent(
                        event_id=f"event_{uuid.uuid4().hex}", run_id=run_id,
                        commitment_id=time_commitment_id,
                        event_type=EventType.ARTIFACT_FAILED,
                        tool_name="v2.time_chart_renderer", capability="visual.chart",
                        dataset_version_ids=(analysis.dataset_version_id,),
                        error_code=type(exc).__name__, message="time chart rendering failed",
                    )
                )
                yield RuntimeEvent("artifact_failed", {"analysis": "time_trend", "error_code": type(exc).__name__})
        if group_result.status in {"supported", "null_result"} and len(group_result.group_order) == 2:
            try:
                artifact, html = build_group_distribution_chart(
                    datasets.get_frame(analysis.dataset_version_id),
                    metric=metric, group=group,
                    group_order=(group_result.group_order[0], group_result.group_order[1]),
                    dataset_version_id=analysis.dataset_version_id,
                    finding_refs=(group_finding.finding_id,),
                    title=f"{metric} 的{group}双组分布",
                )
                store.write_chart_artifact(artifact, html)
                group_chart_ids = (artifact.chart_id,)
                store.append_event(
                    ExecutionEvent(
                        event_id=f"event_{uuid.uuid4().hex}", run_id=run_id,
                        commitment_id=group_commitment_id,
                        event_type=EventType.ARTIFACT_CREATED,
                        tool_name="v2.group_chart_renderer", capability="visual.chart",
                        dataset_version_ids=(analysis.dataset_version_id,),
                        result_ref=artifact.chart_id,
                    )
                )
                yield RuntimeEvent("artifact_created", {"artifact": asdict(artifact)})
            except Exception as exc:
                store.append_event(
                    ExecutionEvent(
                        event_id=f"event_{uuid.uuid4().hex}", run_id=run_id,
                        commitment_id=group_commitment_id,
                        event_type=EventType.ARTIFACT_FAILED,
                        tool_name="v2.group_chart_renderer", capability="visual.chart",
                        dataset_version_ids=(analysis.dataset_version_id,),
                        error_code=type(exc).__name__, message="group chart rendering failed",
                    )
                )
                yield RuntimeEvent("artifact_failed", {"analysis": "group_comparison", "error_code": type(exc).__name__})

        projection = project_run(*store.read_run_facts(run_id))
        yield RuntimeEvent(
            "outcome_snapshot",
            {"publishable": projection.publishable, "outcomes": {key: asdict(value) for key, value in projection.outcomes.items()}},
        )
        if not projection.publishable:
            raise RuntimeError("Slice 4D core commitments did not reach publishable outcomes")
        time_outcome = projection.outcomes[time_commitment_id]
        group_outcome = projection.outcomes[group_commitment_id]
        time_label = {
            OutcomeStatus.SUPPORTED: "历史趋势得到支持",
            OutcomeStatus.NULL_RESULT: "未检出可靠历史趋势",
            OutcomeStatus.LIMITED: "历史趋势受数据条件限制",
            OutcomeStatus.UNAVAILABLE: "历史趋势方法不可用",
        }[time_outcome.status]
        group_label = {
            OutcomeStatus.SUPPORTED: "双组差异得到支持",
            OutcomeStatus.NULL_RESULT: "未检出可靠双组差异",
            OutcomeStatus.LIMITED: "双组比较受数据条件限制",
            OutcomeStatus.UNAVAILABLE: "双组比较方法不可用",
        }[group_outcome.status]
        executive = (
            f"本轮从两个互补角度回答问题：{time_label}；{group_label}。"
            "两类证据分别描述时间变化和观察性组间差异，不证明渠道导致时间趋势，也不识别干预效果。"
        )
        period = _FREQUENCY_LABEL[time_spec.frequency]
        if time_result.status == "supported":
            direction = "上升" if (time_result.trend_per_period or 0) > 0 else "下降"
            time_narrative = (
                f"{metric} 在 {time_result.start_time[:10]} 至 {time_result.end_time[:10]} 呈可靠线性{direction}趋势："
                f"每个{period}周期变化 {_number(time_result.trend_per_period)}，95% CI "
                f"[{_number(time_result.confidence_low)}, {_number(time_result.confidence_high)}]，HAC p{_p(time_result.p_value)}。"
            )
            time_claim = ClaimClass.INFERENTIAL
        elif time_result.status == "null_result":
            time_narrative = (
                f"当前历史范围未检出可靠线性趋势；每个{period}周期变化 {_number(time_result.trend_per_period)}，"
                f"95% CI [{_number(time_result.confidence_low)}, {_number(time_result.confidence_high)}]。"
            )
            time_claim = ClaimClass.INFERENTIAL
        else:
            time_narrative = (
                "历史趋势暂不能可靠估计；"
                + {
                    "missing_time_intervals": "规范时间序列存在缺失周期，且系统未补零或插值。",
                    "incomplete_boundary_periods": "时间范围包含不完整边界周期，系统未将部分周期与完整周期直接比较。",
                    "date_semantics_require_confirmation": "时间字段存在多种无损日期解释。",
                    "insufficient_trend_degrees_of_freedom": "当前周期不足以支持稳健趋势规格。",
                }.get(time_result.reason_code, f"限制原因：{time_result.reason_code}。")
            )
            time_claim = ClaimClass.ASSOCIATIONAL
        if group_result.status == "supported":
            first, second = group_result.group_order
            group_narrative = (
                f"按 {analysis_unit} 为分析单位，{second} 相对 {first} 的 {metric} 均值差为 "
                f"{_number(group_result.difference)}，95% CI "
                f"[{_number(group_result.confidence_low)}, {_number(group_result.confidence_high)}]，"
                f"Welch p{_p(group_result.p_value)}，Hedges g={_number(group_result.hedges_g)}。"
            )
            group_claim = ClaimClass.INFERENTIAL
        elif group_result.status == "null_result":
            first, second = group_result.group_order
            group_narrative = (
                f"按 {analysis_unit} 为分析单位，未检出 {first} 与 {second} 的可靠均值差异；"
                f"差值 {_number(group_result.difference)}，Welch p{_p(group_result.p_value)}。"
            )
            group_claim = ClaimClass.INFERENTIAL
        elif group_result.status == "descriptive_ranking":
            ranking_lines = "；".join(
                f"{rank}. {summary.group_value}：均值 {_number(summary.mean)}"
                for rank, summary in enumerate(group_result.groups[:5], start=1)
            )
            remaining = len(group_result.groups) - min(5, len(group_result.groups))
            group_narrative = (
                f"分组字段 {group} 共 {len(group_result.groups)} 个非空组，超出双组比较范围。"
                f"按 {metric} 每组均值的描述性排序（降序，前 5）：{ranking_lines}。"
                + (f"其余 {remaining} 组见结构化结果。" if remaining > 0 else "")
                + "该排序未做组间统计推断。"
            )
            group_claim = ClaimClass.DESCRIPTIVE
        else:
            group_narrative = (
                "双组比较暂不能可靠估计；"
                + {
                    "requires_exactly_two_groups": "该方法要求字段中恰好两个组。",
                    "repeated_analysis_units": "分析单位存在重复，不能视为独立观测。",
                    "insufficient_group_degrees_of_freedom": "组内自由度不足。",
                }.get(group_result.reason_code, f"限制原因：{group_result.reason_code}。")
            )
            group_claim = ClaimClass.ASSOCIATIONAL
        time_scope = (
            f"{time_result.start_time[:10]} 至 {time_result.end_time[:10]}"
            if time_result.start_time and time_result.end_time
            else "未形成可用时间范围"
        )
        method = (
            f"数据范围为 {time_scope}；趋势基于 {time_result.observed_periods} 个已观测{period}周期"
            f"（源记录 {time_result.source_rows}，有效记录 {time_result.valid_rows}，"
            f"缺失周期 {time_result.missing_periods}，不完整边界周期 "
            f"{time_result.incomplete_boundary_periods}，插补周期 {time_result.imputed_periods}）；"
            f"组间比较基于 {group_result.effective_units} 个有效 {analysis_unit}"
            f"（完整记录 {group_result.complete_case_rows}，剔除 {group_result.dropped_rows}）。"
            f"适用总体限于当前上传数据中以 {analysis_unit} 定义且字段完整的观察单位，"
            "不自动外推到其他时间或总体。"
            f"趋势按{period}频{_AGGREGATION_LABEL[time_spec.aggregation]}聚合，使用 HAC 稳健标准误"
            f"（max lag={time_result.hac_max_lag}）；双组比较以 {analysis_unit} 为独立单位，"
            f"使用 Welch 区间并报告 Hedges g。两种方法共享同一不可变分析副本，但各自拥有独立 Commitment 和 Finding。"
        )
        drafts = [
            AnswerBlockDraft(
                block_id=f"block_{uuid.uuid4().hex}", block_type=AnswerBlockType.EXECUTIVE_ANSWER,
                headline="直接回答", narrative=executive,
                support_refs=(time_finding.finding_id, group_finding.finding_id),
                claim_class=ClaimClass.ASSOCIATIONAL,
            ),
            AnswerBlockDraft(
                block_id=f"block_{uuid.uuid4().hex}", block_type=AnswerBlockType.KEY_FINDING,
                headline="历史趋势", narrative=time_narrative,
                support_refs=(time_finding.finding_id,), claim_class=time_claim,
                chart_refs=time_chart_ids, limitations=time_result.limitations,
            ),
            AnswerBlockDraft(
                block_id=f"block_{uuid.uuid4().hex}", block_type=AnswerBlockType.COMPARISON,
                headline="双组比较", narrative=group_narrative,
                support_refs=(group_finding.finding_id,), claim_class=group_claim,
                chart_refs=group_chart_ids, limitations=group_result.limitations,
            ),
            AnswerBlockDraft(
                block_id=f"block_{uuid.uuid4().hex}", block_type=AnswerBlockType.METHOD,
                headline="方法与共同边界", narrative=method,
                support_refs=(time_finding.finding_id, group_finding.finding_id),
                claim_class=ClaimClass.ASSOCIATIONAL,
                limitations=(
                    "时间趋势与组间差异同时存在，不等于组别导致趋势。",
                    "观察性结果不能替代随机化或可信准实验的干预效果识别。",
                ),
            ),
        ]
        recommendation_mode = "none"
        if intent is not RecommendationIntent.NONE:
            recommendation_mode = "investigative_next_step"
            if OutcomeStatus.LIMITED in {time_outcome.status, group_outcome.status}:
                advice = "先解决受限分析对应的时间语义、组别数量、分析单位或数据充分性，再评估行动方案。"
            else:
                advice = (
                    "可进一步检查时间与组别构成的交互、同期外部事件和混杂因素，"
                    "并用低风险、可逆的验证设计检验可干预机制。"
                )
            drafts.append(
                AnswerBlockDraft(
                    block_id=f"block_{uuid.uuid4().hex}",
                    block_type=AnswerBlockType.NEXT_INVESTIGATION,
                    headline="建议的验证步骤", narrative=advice,
                    support_refs=(time_finding.finding_id, group_finding.finding_id),
                    claim_class=ClaimClass.ASSOCIATIONAL,
                )
            )
        compiled = compile_answer(drafts, findings, projection.outcomes)
        artifact_ids = time_chart_ids + group_chart_ids
        store.write_turn_blocks(
            turn_id, list(compiled.blocks), status="finalized", artifact_ids=artifact_ids,
            request_context={
                "filename": filename, "time_field": time_spec.time_field, "metric": metric,
                "frequency": time_spec.frequency.value, "aggregation": time_spec.aggregation.value,
                "group": group_spec.group, "analysis_unit": group_spec.analysis_unit,
                "question": user_question, "analysis_kind": "multi_finding_synthesis",
                "recommendation_intent": intent.value, "action_risk": risk.value,
                "reversible": str(bool(reversible)).lower(),
                "recommendation_mode": recommendation_mode,
            },
        )
        for block in compiled.blocks:
            yield RuntimeEvent("final_block_delta", {"turn_id": turn_id, "block": asdict(block)})
        yield RuntimeEvent(
            "turn_completed",
            {"session_id": session_id, "turn_id": turn_id, "run_id": run_id,
             "status": "completed", "answer_markdown": compiled.markdown},
        )
