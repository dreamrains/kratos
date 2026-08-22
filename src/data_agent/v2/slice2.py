from __future__ import annotations

import hashlib
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Iterator

import pandas as pd

from data_agent.v2.answer import compile_answer
from data_agent.v2.dataset import DatasetRegistry, DatasetRole
from data_agent.v2.factor import FactorAnalysisSpec, analyze_factor_relationships
from data_agent.v2.factor_chart import build_factor_coefficient_chart
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
from data_agent.v2.slice1 import RuntimeEvent, _load_frame
from data_agent.v2.store import V2FactStore


FACTOR_RELATIONSHIP_CAPABILITY = "analysis.factor_relationship"


def _source_identity(path: Path) -> str:
    return f"upload:{path.name}:sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _number(value: float, digits: int = 3) -> str:
    return f"{value:,.{digits}f}".rstrip("0").rstrip(".")


def _p_value(value: float) -> str:
    return "<0.001" if value < 0.001 else f"={_number(value)}"


class Slice2FactorRuntime:
    """Deterministic V2 vertical runtime for continuous factor relationships."""

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
        target: str,
        features: tuple[str, ...],
        analysis_unit: str,
        time_field: str,
        question: str,
    ) -> Iterator[RuntimeEvent]:
        source_path = self._source_path(filename)
        spec = FactorAnalysisSpec(
            target=target,
            features=features,
            analysis_unit=analysis_unit,
            time_field=time_field,
        )
        user_question = str(question or "").strip()
        if not user_question:
            raise ValueError("question is required")

        run_id = f"run_{uuid.uuid4().hex}"
        commitment_id = f"commitment_{uuid.uuid4().hex}"
        tool_call_id = f"tool_{uuid.uuid4().hex}"
        computation_ref = f"computation:{uuid.uuid4().hex}"
        store = V2FactStore(self.sessions_root, session_id)
        datasets = DatasetRegistry(self.sessions_root, session_id)
        yield RuntimeEvent(
            "turn_started",
            {"session_id": session_id, "turn_id": turn_id, "run_id": run_id},
        )

        raw_frame = _load_frame(source_path)
        raw_version = datasets.register_raw(
            source_path.stem,
            raw_frame,
            source_identity=_source_identity(source_path),
        )
        analysis_version = datasets.derive(
            parent_version_id=raw_version.dataset_version_id,
            frame=raw_frame.copy(deep=True),
            role=DatasetRole.ANALYSIS,
            transform={"operation": "identity_factor_analysis_copy", "lossless": True},
        )
        commitment = Commitment(
            commitment_id=commitment_id,
            priority=CommitmentPriority.CORE,
            question=user_question,
            dataset_version_ids=(analysis_version.dataset_version_id,),
            accepted_result_kinds=(
                FindingKind.ASSOCIATION,
                FindingKind.NULL_RESULT,
                FindingKind.LIMITATION,
            ),
            accepted_method_capabilities=(FACTOR_RELATIONSHIP_CAPABILITY,),
            target_semantics=spec.target,
            visualization_intent="conditional:coefficient_interval",
        )
        store.append_commitments(run_id, turn_id, [commitment])
        yield RuntimeEvent("commitment_snapshot", {"commitments": [asdict(commitment)]})

        started = ExecutionEvent(
            event_id=f"event_{uuid.uuid4().hex}",
            run_id=run_id,
            commitment_id=commitment_id,
            event_type=EventType.TOOL_STARTED,
            tool_call_id=tool_call_id,
            tool_name="v2.factor_relationship",
            capability=FACTOR_RELATIONSHIP_CAPABILITY,
            dataset_version_ids=(analysis_version.dataset_version_id,),
        )
        store.append_event(started)
        yield RuntimeEvent(
            "tool_started",
            {
                "tool_call_id": tool_call_id,
                "name": "factor_relationship",
                "capability": FACTOR_RELATIONSHIP_CAPABILITY,
            },
        )
        result = analyze_factor_relationships(
            datasets.get_frame(analysis_version.dataset_version_id),
            spec,
        )
        store.append_event(
            ExecutionEvent(
                event_id=f"event_{uuid.uuid4().hex}",
                run_id=run_id,
                commitment_id=commitment_id,
                event_type=EventType.TOOL_SUCCEEDED,
                tool_call_id=tool_call_id,
                tool_name="v2.factor_relationship",
                capability=FACTOR_RELATIONSHIP_CAPABILITY,
                dataset_version_ids=(analysis_version.dataset_version_id,),
                result_ref=computation_ref,
            )
        )

        findings: list[Finding] = []
        if result.reliable_factors:
            for estimate in result.reliable_factors:
                findings.append(
                    Finding(
                        finding_id=f"finding_{uuid.uuid4().hex}",
                        commitment_id=commitment_id,
                        finding_kind=FindingKind.ASSOCIATION,
                        dataset_version_ids=(analysis_version.dataset_version_id,),
                        metric_identity=f"column:{spec.target}",
                        feature_identity=f"column:{estimate.feature}",
                        method_capability=FACTOR_RELATIONSHIP_CAPABILITY,
                        maximum_claim_class=ClaimClass.INFERENTIAL,
                        computation_ref=computation_ref,
                        estimate=estimate.coefficient,
                        direction=("positive" if estimate.coefficient > 0 else "negative"),
                        effective_sample=result.effective_units,
                        uncertainty={
                            "confidence_low": estimate.confidence_low,
                            "confidence_high": estimate.confidence_high,
                            "p_value": estimate.p_value,
                            "p_adjusted": estimate.p_adjusted,
                            "vif": estimate.vif,
                            "complete_case_rows": result.complete_case_rows,
                        },
                        assumption_results={
                            "covariance_method": result.covariance_method,
                            "time_controlled": result.time_controlled,
                            "alpha": result.alpha,
                        },
                        limitations=result.limitations,
                    )
                )
        else:
            kind = (
                FindingKind.LIMITATION if result.status == "limited" else FindingKind.NULL_RESULT
            )
            findings.append(
                Finding(
                    finding_id=f"finding_{uuid.uuid4().hex}",
                    commitment_id=commitment_id,
                    finding_kind=kind,
                    dataset_version_ids=(analysis_version.dataset_version_id,),
                    metric_identity=f"column:{spec.target}",
                    method_capability=FACTOR_RELATIONSHIP_CAPABILITY,
                    maximum_claim_class=(
                        ClaimClass.ASSOCIATIONAL
                        if kind is FindingKind.LIMITATION
                        else ClaimClass.INFERENTIAL
                    ),
                    computation_ref=computation_ref,
                    effective_sample=result.effective_units,
                    uncertainty={
                        "reason_code": result.reason_code,
                        "tested_features": list(result.tested_features),
                        "excluded_features": dict(result.excluded_features),
                        "unstable_features": list(result.unstable_features),
                        "bivariate_associations": [
                            {
                                "feature": item.feature,
                                "pearson_r": item.pearson_r,
                                "pearson_p_adjusted": item.pearson_p_adjusted,
                                "spearman_rho": item.spearman_rho,
                                "n_pairs": item.n_pairs,
                            }
                            for item in result.bivariate_associations
                        ],
                        "complete_case_rows": result.complete_case_rows,
                    },
                    limitations=result.limitations,
                )
            )
        for finding in findings:
            store.append_finding(finding)
        yield RuntimeEvent(
            "tool_finished",
            {
                "tool_call_id": tool_call_id,
                "name": "factor_relationship",
                "status": "succeeded",
                "result_ref": computation_ref,
                "result_status": result.status,
            },
        )

        artifact_ids: tuple[str, ...] = ()
        chart_failure = False
        if result.reliable_factors:
            try:
                artifact, html = build_factor_coefficient_chart(
                    result,
                    dataset_version_id=analysis_version.dataset_version_id,
                    finding_refs=tuple(item.finding_id for item in findings),
                    title=f"{spec.target} 的调整后因素关系",
                )
                store.write_chart_artifact(artifact, html)
                artifact_ids = (artifact.chart_id,)
                store.append_event(
                    ExecutionEvent(
                        event_id=f"event_{uuid.uuid4().hex}",
                        run_id=run_id,
                        commitment_id=commitment_id,
                        event_type=EventType.ARTIFACT_CREATED,
                        tool_name="v2.factor_chart_renderer",
                        capability="visual.chart",
                        dataset_version_ids=(analysis_version.dataset_version_id,),
                        result_ref=artifact.chart_id,
                    )
                )
                yield RuntimeEvent(
                    "artifact_created",
                    {"turn_id": turn_id, "artifact": asdict(artifact)},
                )
            except Exception as exc:
                chart_failure = True
                store.append_event(
                    ExecutionEvent(
                        event_id=f"event_{uuid.uuid4().hex}",
                        run_id=run_id,
                        commitment_id=commitment_id,
                        event_type=EventType.ARTIFACT_FAILED,
                        tool_name="v2.factor_chart_renderer",
                        capability="visual.chart",
                        dataset_version_ids=(analysis_version.dataset_version_id,),
                        error_code=type(exc).__name__,
                        message="factor chart rendering failed",
                    )
                )
                yield RuntimeEvent(
                    "artifact_failed",
                    {
                        "turn_id": turn_id,
                        "status": "unavailable",
                        "error_code": type(exc).__name__,
                    },
                )

        projection = project_run(*store.read_run_facts(run_id))
        outcome = projection.outcomes[commitment_id]
        yield RuntimeEvent(
            "outcome_snapshot",
            {
                "publishable": projection.publishable,
                "outcomes": {commitment_id: asdict(outcome)},
            },
        )
        if not projection.publishable:
            raise RuntimeError("Slice 2 core commitment did not reach a publishable outcome")

        support_refs = tuple(item.finding_id for item in findings)
        if result.reliable_factors:
            factor_summary = "、".join(
                f"{item.feature}（标准化系数 {_number(item.coefficient)}，"
                f"95% CI [{_number(item.confidence_low)}, {_number(item.confidence_high)}]，"
                f"Holm 校正 p{_p_value(item.p_adjusted)}）"
                for item in result.reliable_factors
            )
            answer_narrative = (
                f"在当前多变量模型和数据范围内，{factor_summary}与 {spec.target} "
                "存在调整后统计关联。该结果不能解释为因果影响。"
            )
            claim_class = ClaimClass.INFERENTIAL
        elif result.status == "limited":
            answer_narrative = (
                "当前无法可靠区分因素关系：分析单位存在重复观测，但没有提供时间字段，"
                "因此没有把每一行错误地当作独立样本。"
                if result.reason_code == "repeated_units_require_time_field"
                else "当前数据诊断显示模型条件不足，未发布可靠因素排序。"
            )
            claim_class = ClaimClass.ASSOCIATIONAL
        else:
            answer_narrative = (
                f"在当前模型、数据范围和 Holm 多重比较校正下，未发现与 {spec.target} "
                "存在可靠调整后统计关联的候选因素。"
            )
            claim_class = ClaimClass.INFERENTIAL

        exclusions = "；".join(
            f"{feature}: {reason}" for feature, reason in result.excluded_features.items()
        ) or "无"
        unstable = "、".join(result.unstable_features) or "无"
        method_narrative = (
            f"分析单位为 {spec.analysis_unit}；完整案例 {result.complete_case_rows} 行，"
            f"有效单位 {result.effective_units} 个；不确定性方法为 "
            f"{result.covariance_method or '未估计'}。候选因素使用标准化多变量 OLS，"
            "置信区间使用稳健标准误，p 值使用 Holm 校正。"
        )
        diagnostic_narrative = (
            f"排除因素：{exclusions}；高共线不稳定因素：{unstable}。"
        )
        if result.bivariate_associations:
            ranking_lines = "；".join(
                f"{item.feature} r={_number(item.pearson_r)}（Holm 校正 p{_p_value(item.pearson_p_adjusted)}）"
                for item in result.bivariate_associations[:8]
            )
            remaining = len(result.bivariate_associations) - min(
                8, len(result.bivariate_associations)
            )
            diagnostic_narrative += (
                "未调整双变量关联排序（描述性，未控制其他因素，不构成因果或多因素结论）："
                f"{ranking_lines}。"
                + (f"其余 {remaining} 个因素见结构化结果。" if remaining > 0 else "")
            )
        if chart_failure:
            diagnostic_narrative += " 图表生成失败，但结构化因素结论仍已发布。"

        drafts = [
            AnswerBlockDraft(
                block_id=f"block_{uuid.uuid4().hex}",
                block_type=AnswerBlockType.EXECUTIVE_ANSWER,
                headline="直接回答",
                narrative=answer_narrative,
                support_refs=support_refs,
                claim_class=claim_class,
                chart_refs=artifact_ids,
            ),
            AnswerBlockDraft(
                block_id=f"block_{uuid.uuid4().hex}",
                block_type=AnswerBlockType.METHOD,
                headline="方法与统计边界",
                narrative=method_narrative,
                support_refs=support_refs,
                claim_class=claim_class,
                limitations=result.limitations,
            ),
            AnswerBlockDraft(
                block_id=f"block_{uuid.uuid4().hex}",
                block_type=AnswerBlockType.LIMITATION,
                headline="数据与模型诊断",
                narrative=diagnostic_narrative,
                support_refs=support_refs,
                claim_class=claim_class,
            ),
        ]
        compiled = compile_answer(drafts, findings, {commitment_id: outcome})
        store.write_turn_blocks(
            turn_id,
            list(compiled.blocks),
            status="finalized",
            artifact_ids=artifact_ids,
            request_context={
                "filename": filename,
                "target": spec.target,
                "features": ",".join(spec.features),
                "analysis_unit": spec.analysis_unit,
                "time_field": spec.time_field,
                "question": user_question,
                "analysis_kind": "factor_relationship",
            },
        )
        for block in compiled.blocks:
            yield RuntimeEvent(
                "final_block_delta", {"turn_id": turn_id, "block": asdict(block)}
            )
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
