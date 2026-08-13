from __future__ import annotations

import hashlib
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Iterator

import numpy as np

from data_agent.v2.answer import compile_answer
from data_agent.v2.dataset import DatasetRegistry, DatasetRole
from data_agent.v2.forecast_chart import build_forecast_chart
from data_agent.v2.forecasting import ForecastResult, ForecastSpec, forecast_time_series
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
)
from data_agent.v2.projection import project_run
from data_agent.v2.recommendation import (
    ActionRisk,
    RecommendationContext,
    RecommendationIntent,
    RecommendationMode,
    decide_recommendation,
)
from data_agent.v2.slice1 import RuntimeEvent, _load_frame
from data_agent.v2.store import V2FactStore
from data_agent.v2.time_series import TimeAggregation, TimeFrequency


FORECAST_CAPABILITY = "analysis.forecast_baseline"

_FREQUENCY_LABEL = {
    TimeFrequency.DAILY: "日",
    TimeFrequency.WEEKLY: "周",
    TimeFrequency.MONTHLY: "月",
}
_AGGREGATION_LABEL = {
    TimeAggregation.SUM: "求和",
    TimeAggregation.MEAN: "平均",
}
_METHOD_LABEL = {
    "naive_last": "上一周期基线",
    "drift": "漂移基线",
    "seasonal_naive": "季节朴素基线",
}


def _source_identity(path: Path) -> str:
    return f"upload:{path.name}:sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _number(value: float | None, digits: int = 3) -> str:
    if value is None or not np.isfinite(value):
        return "不可用"
    return f"{value:,.{digits}f}".rstrip("0").rstrip(".")


class Slice4CForecastRuntime:
    """V2 baseline forecast runtime with ordered out-of-time validation."""

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

    @staticmethod
    def _core_finding(
        result: ForecastResult,
        *,
        commitment_id: str,
        dataset_version_id: str,
        computation_ref: str,
    ) -> Finding:
        supported = result.status == "supported"
        return Finding(
            finding_id=f"finding_{uuid.uuid4().hex}",
            commitment_id=commitment_id,
            finding_kind=FindingKind.FORECAST if supported else FindingKind.LIMITATION,
            dataset_version_ids=(dataset_version_id,),
            metric_identity=f"column:{result.metric}",
            feature_identity=(
                f"forecast:{result.time_field}:{result.frequency.value}:h{result.horizon}"
            ),
            method_capability=FORECAST_CAPABILITY,
            maximum_claim_class=result.maximum_claim_class,
            computation_ref=computation_ref,
            estimate=result.forecast_values[-1] if supported else None,
            direction="future_baseline" if supported else "none",
            effective_sample=result.observed_periods,
            time_scope=(
                f"{result.historical_times[0]}/{result.forecast_times[-1]}"
                if supported
                else (
                    f"{result.historical_times[0]}/{result.historical_times[-1]}"
                    if result.historical_times
                    else ""
                )
            ),
            uncertainty={
                "forecast_times": result.forecast_times,
                "forecast_values": result.forecast_values,
                "interval_low": result.interval_low,
                "interval_high": result.interval_high,
                "validation_points": result.validation_points,
                "mae": result.mae,
                "rmse": result.rmse,
                "mase": result.mase,
                "skill_vs_naive": result.skill_vs_naive,
                "error_to_level_ratio": result.error_to_level_ratio,
                "reason_code": result.reason_code,
            },
            assumption_results={
                "frequency": result.frequency.value,
                "aggregation": result.aggregation.value,
                "horizon": result.horizon,
                "selected_method": result.selected_method,
                "candidate_methods": result.candidate_methods,
                "backtest_scheme": result.backtest_scheme,
                "interval_method": result.interval_method,
                "imputed_periods": result.imputed_periods,
            },
            limitations=result.limitations,
        )

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
        horizon: int,
        question: str,
        recommendation_intent: RecommendationIntent,
        action_risk: ActionRisk,
        reversible: bool,
    ) -> Iterator[RuntimeEvent]:
        source_path = self._source_path(filename)
        spec = ForecastSpec(time_field, metric, frequency, aggregation, horizon)
        user_question = str(question or "").strip()
        if not user_question:
            raise ValueError("question is required")
        intent = RecommendationIntent(recommendation_intent)
        risk = ActionRisk(action_risk)
        run_id = f"run_{uuid.uuid4().hex}"
        commitment_id = f"commitment_{uuid.uuid4().hex}"
        tool_call_id = f"tool_{uuid.uuid4().hex}"
        computation_ref = f"computation:{uuid.uuid4().hex}"
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
            transform={"operation": "identity_forecast_copy", "lossless": True},
        )
        commitment = Commitment(
            commitment_id=commitment_id,
            priority=CommitmentPriority.CORE,
            question=user_question,
            dataset_version_ids=(analysis.dataset_version_id,),
            accepted_result_kinds=(FindingKind.FORECAST, FindingKind.LIMITATION),
            accepted_method_capabilities=(FORECAST_CAPABILITY,),
            target_semantics=f"{metric} forecast over {time_field} for {spec.horizon} periods",
            visualization_intent="conditional:forecast_line_interval",
        )
        store.append_commitments(run_id, turn_id, [commitment])
        yield RuntimeEvent("commitment_snapshot", {"commitments": [asdict(commitment)]})
        store.append_event(
            ExecutionEvent(
                event_id=f"event_{uuid.uuid4().hex}",
                run_id=run_id,
                commitment_id=commitment_id,
                event_type=EventType.TOOL_STARTED,
                tool_call_id=tool_call_id,
                tool_name="v2.forecast_baseline",
                capability=FORECAST_CAPABILITY,
                dataset_version_ids=(analysis.dataset_version_id,),
            )
        )
        yield RuntimeEvent(
            "tool_started", {"name": "forecast_baseline", "capability": FORECAST_CAPABILITY}
        )
        result = forecast_time_series(datasets.get_frame(analysis.dataset_version_id), spec)
        store.append_event(
            ExecutionEvent(
                event_id=f"event_{uuid.uuid4().hex}",
                run_id=run_id,
                commitment_id=commitment_id,
                event_type=EventType.TOOL_SUCCEEDED,
                tool_call_id=tool_call_id,
                tool_name="v2.forecast_baseline",
                capability=FORECAST_CAPABILITY,
                dataset_version_ids=(analysis.dataset_version_id,),
                result_ref=computation_ref,
            )
        )
        findings: list[Finding] = []
        if result.historical_values:
            findings.append(
                Finding(
                    finding_id=f"finding_{uuid.uuid4().hex}",
                    commitment_id=commitment_id,
                    finding_kind=FindingKind.ESTIMATE,
                    dataset_version_ids=(analysis.dataset_version_id,),
                    metric_identity=f"column:{metric}:historical_summary",
                    feature_identity=f"time:{time_field}:{spec.frequency.value}",
                    method_capability=FORECAST_CAPABILITY,
                    maximum_claim_class=ClaimClass.DESCRIPTIVE,
                    computation_ref=computation_ref,
                    estimate=float(np.mean(result.historical_values)),
                    effective_sample=result.observed_periods,
                    time_scope=(
                        f"{result.historical_times[0]}/{result.historical_times[-1]}"
                    ),
                )
            )
        core = self._core_finding(
            result,
            commitment_id=commitment_id,
            dataset_version_id=analysis.dataset_version_id,
            computation_ref=computation_ref,
        )
        findings.append(core)
        for finding in findings:
            store.append_finding(finding)
        yield RuntimeEvent(
            "tool_finished",
            {"name": "forecast_baseline", "status": "succeeded", "result_status": result.status},
        )
        artifact_ids: tuple[str, ...] = ()
        chart_failed = False
        if result.status == "supported":
            try:
                artifact, html = build_forecast_chart(
                    result,
                    dataset_version_id=analysis.dataset_version_id,
                    finding_refs=tuple(item.finding_id for item in findings),
                    title=f"{metric} 的{spec.horizon}期基线预测",
                )
                store.write_chart_artifact(artifact, html)
                artifact_ids = (artifact.chart_id,)
                store.append_event(
                    ExecutionEvent(
                        event_id=f"event_{uuid.uuid4().hex}",
                        run_id=run_id,
                        commitment_id=commitment_id,
                        event_type=EventType.ARTIFACT_CREATED,
                        tool_name="v2.forecast_chart_renderer",
                        capability="visual.chart",
                        dataset_version_ids=(analysis.dataset_version_id,),
                        result_ref=artifact.chart_id,
                    )
                )
                yield RuntimeEvent("artifact_created", {"artifact": asdict(artifact)})
            except Exception as exc:
                chart_failed = True
                store.append_event(
                    ExecutionEvent(
                        event_id=f"event_{uuid.uuid4().hex}",
                        run_id=run_id,
                        commitment_id=commitment_id,
                        event_type=EventType.ARTIFACT_FAILED,
                        tool_name="v2.forecast_chart_renderer",
                        capability="visual.chart",
                        dataset_version_ids=(analysis.dataset_version_id,),
                        error_code=type(exc).__name__,
                        message="forecast chart rendering failed",
                    )
                )
                yield RuntimeEvent("artifact_failed", {"error_code": type(exc).__name__})
        projection = project_run(*store.read_run_facts(run_id))
        outcome = projection.outcomes[commitment_id]
        yield RuntimeEvent(
            "outcome_snapshot",
            {"publishable": projection.publishable, "outcomes": {commitment_id: asdict(outcome)}},
        )
        if not projection.publishable:
            raise RuntimeError("Slice 4C commitment did not reach a publishable outcome")
        decision = decide_recommendation(
            RecommendationContext(
                intent=intent,
                outcome_status=outcome.status,
                finding_kind=core.finding_kind,
                maximum_claim_class=core.maximum_claim_class,
                action_risk=risk,
                reversible=bool(reversible),
            )
        )
        period_label = _FREQUENCY_LABEL[spec.frequency]
        aggregation_label = _AGGREGATION_LABEL[spec.aggregation]
        if result.status == "supported":
            narrative = (
                f"在历史规律延续的基线假设下，未来 {result.horizon} 个{period_label}周期的"
                f"{metric} {aggregation_label}预测从 {_number(result.forecast_values[0])} 变化到 "
                f"{_number(result.forecast_values[-1])}；最后一期经验预测区间为 "
                f"[{_number(result.interval_low[-1])}, {_number(result.interval_high[-1])}]。"
                "这不是预算承诺，也不表示任何干预会产生该结果。"
            )
            method = (
                f"比较了 {', '.join(_METHOD_LABEL[item] for item in result.candidate_methods)}，"
                f"使用 {result.validation_points} 个严格按时间顺序的 expanding-window 时间外验证点，"
                f"选择{_METHOD_LABEL[result.selected_method]}。验证 MAE={_number(result.mae)}，"
                f"RMSE={_number(result.rmse)}，MASE={_number(result.mase)}，"
                f"相对上一周期基线 skill={_number(result.skill_vs_naive)}。"
                "经验预测区间来自时间外绝对误差并随步长扩张。"
            )
            claim_class = ClaimClass.PREDICTIVE
        else:
            messages = {
                "backtest_quality_below_threshold": (
                    f"当前基线的时间外回测质量不足（MASE={_number(result.mase)}，"
                    f"误差/典型量级={_number(result.error_to_level_ratio)}），因此未发布未来点预测。"
                ),
                "forecast_horizon_too_long": "请求的预测期相对历史长度过长，因此未发布未来点预测。",
                "insufficient_forecast_history": "历史周期不足以同时形成训练窗口和时间外验证，因此未发布未来点预测。",
                "missing_time_intervals": "规范时间序列存在缺失周期；系统没有补零或插值，因此未发布未来点预测。",
                "date_semantics_require_confirmation": "时间字段存在多种无损日期解释，需要先确认日期语义。",
                "time_field_not_losslessly_parseable": "时间字段无法无损解析，因此未发布未来点预测。",
                "no_valid_time_metric_rows": "没有可用于预测的有效时间与指标记录。",
            }
            narrative = messages.get(
                result.reason_code, "当前数据不足以支持可用的基线预测，未发布未来点预测。"
            )
            method = (
                f"源数据 {result.source_rows} 行，形成 {result.observed_periods} 个规范{period_label}周期，"
                f"聚合口径为{aggregation_label}；限制原因：{result.reason_code}。"
            )
            claim_class = ClaimClass.ASSOCIATIONAL
        if chart_failed:
            method += " 图表生成失败，但结构化文本预测仍已发布。"
        drafts = [
            AnswerBlockDraft(
                block_id=f"block_{uuid.uuid4().hex}",
                block_type=AnswerBlockType.EXECUTIVE_ANSWER,
                headline="直接回答",
                narrative=narrative,
                support_refs=(core.finding_id,),
                claim_class=claim_class,
                chart_refs=artifact_ids,
            ),
            AnswerBlockDraft(
                block_id=f"block_{uuid.uuid4().hex}",
                block_type=AnswerBlockType.METHOD,
                headline="回测方法与预测边界",
                narrative=method,
                support_refs=(core.finding_id,),
                claim_class=claim_class,
                limitations=result.limitations,
            ),
        ]
        if decision.mode is not RecommendationMode.NONE:
            drafts.append(
                AnswerBlockDraft(
                    block_id=f"block_{uuid.uuid4().hex}",
                    block_type=(
                        AnswerBlockType.RECOMMENDATION
                        if decision.mode is RecommendationMode.OPERATIONAL_ACTION
                        else AnswerBlockType.NEXT_INVESTIGATION
                    ),
                    headline="建议的使用方式",
                    narrative=decision.narrative,
                    support_refs=(core.finding_id,),
                    claim_class=core.maximum_claim_class,
                )
            )
        compiled = compile_answer(drafts, findings, {commitment_id: outcome})
        store.write_turn_blocks(
            turn_id,
            list(compiled.blocks),
            status="finalized",
            artifact_ids=artifact_ids,
            request_context={
                "filename": filename,
                "time_field": spec.time_field,
                "metric": spec.metric,
                "frequency": spec.frequency.value,
                "aggregation": spec.aggregation.value,
                "horizon": str(spec.horizon),
                "question": user_question,
                "analysis_kind": "forecast",
                "recommendation_intent": intent.value,
                "action_risk": risk.value,
                "reversible": str(bool(reversible)).lower(),
                "recommendation_mode": decision.mode.value,
            },
        )
        for block in compiled.blocks:
            yield RuntimeEvent("final_block_delta", {"turn_id": turn_id, "block": asdict(block)})
        yield RuntimeEvent(
            "turn_completed",
            {
                "session_id": session_id,
                "turn_id": turn_id,
                "run_id": run_id,
                "status": "completed",
                "answer_markdown": compiled.markdown,
            },
        )
