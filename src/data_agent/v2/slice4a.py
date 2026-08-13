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


GROUP_COMPARISON_CAPABILITY = "analysis.group_comparison"


def _source_identity(path: Path) -> str:
    return f"upload:{path.name}:sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _number(value: float | None, digits: int = 3) -> str:
    if value is None:
        return "不可用"
    return f"{value:,.{digits}f}".rstrip("0").rstrip(".")


def _p_value(value: float | None) -> str:
    if value is None:
        return "不可用"
    return "<0.001" if value < 0.001 else f"={_number(value)}"


class Slice4AGroupComparisonRuntime:
    """V2 two-group comparison with an independent recommendation policy."""

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
    def _comparison_finding(
        *,
        result: GroupComparisonResult,
        commitment_id: str,
        dataset_version_id: str,
        computation_ref: str,
        metric: str,
        group: str,
    ) -> Finding:
        kind = {
            "supported": FindingKind.GROUP_COMPARISON,
            "null_result": FindingKind.NULL_RESULT,
            "limited": FindingKind.LIMITATION,
        }[result.status]
        return Finding(
            finding_id=f"finding_{uuid.uuid4().hex}",
            commitment_id=commitment_id,
            finding_kind=kind,
            dataset_version_ids=(dataset_version_id,),
            metric_identity=f"column:{metric}",
            feature_identity=f"group:{group}",
            method_capability=GROUP_COMPARISON_CAPABILITY,
            maximum_claim_class=result.maximum_claim_class,
            computation_ref=computation_ref,
            estimate=result.difference,
            direction=(
                "positive" if result.difference is not None and result.difference > 0
                else "negative" if result.difference is not None and result.difference < 0
                else "none"
            ),
            effective_sample=result.effective_units,
            uncertainty={
                "confidence_low": result.confidence_low,
                "confidence_high": result.confidence_high,
                "p_value": result.p_value,
                "welch_degrees_of_freedom": result.welch_degrees_of_freedom,
                "hedges_g": result.hedges_g,
                "mann_whitney_p_value": result.mann_whitney_p_value,
                "group_order": list(result.group_order),
                "complete_case_rows": result.complete_case_rows,
                "dropped_rows": result.dropped_rows,
                "reason_code": result.reason_code,
                "group_summaries": [asdict(item) for item in result.groups],
            },
            assumption_results={
                "equal_variance_assumed": False,
                "independent_units": result.reason_code != "repeated_analysis_units",
                "alpha": result.alpha,
            },
            limitations=result.limitations,
        )

    def stream(
        self,
        *,
        session_id: str,
        turn_id: str,
        filename: str,
        metric: str,
        group: str,
        analysis_unit: str,
        question: str,
        recommendation_intent: RecommendationIntent,
        action_risk: ActionRisk,
        reversible: bool,
    ) -> Iterator[RuntimeEvent]:
        source_path = self._source_path(filename)
        spec = GroupComparisonSpec(metric, group, analysis_unit)
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
            transform={"operation": "identity_group_comparison_copy", "lossless": True},
        )
        commitment = Commitment(
            commitment_id=commitment_id,
            priority=CommitmentPriority.CORE,
            question=user_question,
            dataset_version_ids=(analysis.dataset_version_id,),
            accepted_result_kinds=(
                FindingKind.GROUP_COMPARISON,
                FindingKind.NULL_RESULT,
                FindingKind.LIMITATION,
            ),
            accepted_method_capabilities=(GROUP_COMPARISON_CAPABILITY,),
            target_semantics=f"{metric} by {group}",
            visualization_intent="conditional:group_boxplot",
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
                tool_name="v2.group_comparison",
                capability=GROUP_COMPARISON_CAPABILITY,
                dataset_version_ids=(analysis.dataset_version_id,),
            )
        )
        yield RuntimeEvent(
            "tool_started",
            {"name": "group_comparison", "capability": GROUP_COMPARISON_CAPABILITY},
        )
        result = analyze_group_comparison(
            datasets.get_frame(analysis.dataset_version_id), spec
        )
        store.append_event(
            ExecutionEvent(
                event_id=f"event_{uuid.uuid4().hex}",
                run_id=run_id,
                commitment_id=commitment_id,
                event_type=EventType.TOOL_SUCCEEDED,
                tool_call_id=tool_call_id,
                tool_name="v2.group_comparison",
                capability=GROUP_COMPARISON_CAPABILITY,
                dataset_version_ids=(analysis.dataset_version_id,),
                result_ref=computation_ref,
            )
        )
        findings: list[Finding] = []
        for summary in result.groups:
            findings.append(
                Finding(
                    finding_id=f"finding_{uuid.uuid4().hex}",
                    commitment_id=commitment_id,
                    finding_kind=FindingKind.ESTIMATE,
                    dataset_version_ids=(analysis.dataset_version_id,),
                    metric_identity=f"column:{metric}:mean",
                    feature_identity=f"group:{group}:{summary.group_value}",
                    method_capability=GROUP_COMPARISON_CAPABILITY,
                    maximum_claim_class=ClaimClass.DESCRIPTIVE,
                    computation_ref=computation_ref,
                    estimate=summary.mean,
                    effective_sample=summary.sample_size,
                    uncertainty={
                        "median": summary.median,
                        "standard_deviation": summary.standard_deviation,
                    },
                )
            )
        comparison = self._comparison_finding(
            result=result,
            commitment_id=commitment_id,
            dataset_version_id=analysis.dataset_version_id,
            computation_ref=computation_ref,
            metric=metric,
            group=group,
        )
        findings.append(comparison)
        for finding in findings:
            store.append_finding(finding)
        yield RuntimeEvent(
            "tool_finished",
            {"name": "group_comparison", "status": "succeeded", "result_status": result.status},
        )

        artifact_ids: tuple[str, ...] = ()
        chart_failed = False
        if result.status in {"supported", "null_result"} and len(result.group_order) == 2:
            try:
                artifact, html = build_group_distribution_chart(
                    datasets.get_frame(analysis.dataset_version_id),
                    metric=metric,
                    group=group,
                    group_order=(result.group_order[0], result.group_order[1]),
                    dataset_version_id=analysis.dataset_version_id,
                    finding_refs=tuple(item.finding_id for item in findings),
                    title=f"{metric} 的组间分布",
                )
                store.write_chart_artifact(artifact, html)
                artifact_ids = (artifact.chart_id,)
                store.append_event(
                    ExecutionEvent(
                        event_id=f"event_{uuid.uuid4().hex}",
                        run_id=run_id,
                        commitment_id=commitment_id,
                        event_type=EventType.ARTIFACT_CREATED,
                        tool_name="v2.group_chart_renderer",
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
                        tool_name="v2.group_chart_renderer",
                        capability="visual.chart",
                        dataset_version_ids=(analysis.dataset_version_id,),
                        error_code=type(exc).__name__,
                        message="group chart rendering failed",
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
            raise RuntimeError("Slice 4A commitment did not reach a publishable outcome")
        decision = decide_recommendation(
            RecommendationContext(
                intent=intent,
                outcome_status=outcome.status,
                finding_kind=comparison.finding_kind,
                maximum_claim_class=comparison.maximum_claim_class,
                action_risk=risk,
                reversible=bool(reversible),
            )
        )
        support_refs = (comparison.finding_id,)
        if result.status == "supported":
            first, second = result.groups
            narrative = (
                f"{second.group_value} 组 {metric} 均值为 {_number(second.mean)}，"
                f"{first.group_value} 组为 {_number(first.mean)}；按“{second.group_value} - "
                f"{first.group_value}”计算，均值差为 {_number(result.difference)}，"
                f"95% CI [{_number(result.confidence_low)}, {_number(result.confidence_high)}]，"
                f"Welch p{_p_value(result.p_value)}，Hedges g={_number(result.hedges_g)}。"
                "当前数据支持组间均值差异，但不支持因果解释。"
            )
            claim_class = ClaimClass.INFERENTIAL
        elif result.status == "null_result":
            first, second = result.groups
            narrative = (
                f"当前样本未检出可靠均值差异。按“{second.group_value} - {first.group_value}”"
                f"计算，差值为 {_number(result.difference)}，95% CI "
                f"[{_number(result.confidence_low)}, {_number(result.confidence_high)}]，"
                f"Welch p{_p_value(result.p_value)}。这不等于证明两组完全相同。"
            )
            claim_class = ClaimClass.INFERENTIAL
        else:
            messages = {
                "repeated_analysis_units": "分析单位存在重复观测，4A 没有把多行错误地当作独立样本，因此未发布组间推断。",
                "requires_exactly_two_groups": "当前字段不是恰好两个非空组，超出 4A 的双组比较范围。",
                "insufficient_group_degrees_of_freedom": "至少一个组缺少可估计组内变异所需的观测。",
                "zero_within_group_variance": "两组内部都没有可估计变异，无法构造可靠 Welch 不确定性。",
            }
            narrative = messages.get(result.reason_code, "当前数据条件不足，未发布可靠组间推断。")
            claim_class = ClaimClass.ASSOCIATIONAL
        method = (
            f"完整案例 {result.complete_case_rows}/{result.source_rows} 行，有效分析单位 "
            f"{result.effective_units} 个。主估计使用不假设等方差的 Welch 方法；"
            "同时记录 Mann–Whitney 分布敏感性诊断。"
        )
        if chart_failed:
            method += " 图表生成失败，但结构化文本结果仍可发布。"
        drafts = [
            AnswerBlockDraft(
                block_id=f"block_{uuid.uuid4().hex}",
                block_type=AnswerBlockType.EXECUTIVE_ANSWER,
                headline="直接回答",
                narrative=narrative,
                support_refs=support_refs,
                claim_class=claim_class,
                chart_refs=artifact_ids,
            ),
            AnswerBlockDraft(
                block_id=f"block_{uuid.uuid4().hex}",
                block_type=AnswerBlockType.METHOD,
                headline="方法与统计边界",
                narrative=method,
                support_refs=support_refs,
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
                    headline=(
                        "可执行建议"
                        if decision.mode is RecommendationMode.OPERATIONAL_ACTION
                        else "建议的验证步骤"
                    ),
                    narrative=decision.narrative,
                    support_refs=(comparison.finding_id,),
                    claim_class=comparison.maximum_claim_class,
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
                "metric": metric,
                "group": group,
                "analysis_unit": analysis_unit,
                "question": user_question,
                "analysis_kind": "group_comparison",
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
