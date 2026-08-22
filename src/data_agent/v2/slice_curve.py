from __future__ import annotations

import hashlib
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Iterator

from data_agent.v2.answer import compile_answer
from data_agent.v2.curve_chart import build_curve_fit_chart
from data_agent.v2.curve_fitting import (
    CurveFitResult,
    CurveFitSpec,
    analyze_curve_fit,
)
from data_agent.v2.dataset import DatasetRegistry, DatasetRole
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


CURVE_FITTING_CAPABILITY = "analysis.curve_fitting"


def _source_identity(path: Path) -> str:
    return f"upload:{path.name}:sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _number(value: float | None, digits: int = 4) -> str:
    if value is None:
        return "不可用"
    return f"{value:,.{digits}f}".rstrip("0").rstrip(".")


class SliceCurveFittingRuntime:
    """V2 deterministic curve fitting (descriptive model-family comparison)."""

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
        question: str,
        y_column: str = "",
        x_column: str = "",
        series_columns: tuple[str, ...] | list[str] = (),
        zero_values: str = "exclude",
    ) -> Iterator[RuntimeEvent]:
        source_path = self._source_path(filename)
        spec = CurveFitSpec(
            y_column=y_column,
            x_column=x_column,
            series_columns=tuple(series_columns),
            zero_values=zero_values,
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
            transform={"operation": "identity_curve_fitting_copy", "lossless": True},
        )
        commitment = Commitment(
            commitment_id=commitment_id,
            priority=CommitmentPriority.CORE,
            question=user_question,
            dataset_version_ids=(analysis.dataset_version_id,),
            accepted_result_kinds=(
                FindingKind.ESTIMATE,
                FindingKind.NULL_RESULT,
                FindingKind.LIMITATION,
            ),
            accepted_method_capabilities=(CURVE_FITTING_CAPABILITY,),
            target_semantics=(
                f"curve:{'+'.join(spec.series_columns) if spec.series_columns else spec.y_column}"
            ),
            visualization_intent="conditional:curve_overlay",
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
                tool_name="v2.curve_fitting",
                capability=CURVE_FITTING_CAPABILITY,
                dataset_version_ids=(analysis.dataset_version_id,),
            )
        )
        yield RuntimeEvent(
            "tool_started",
            {"name": "curve_fitting", "capability": CURVE_FITTING_CAPABILITY},
        )
        result = analyze_curve_fit(
            datasets.get_frame(analysis.dataset_version_id), spec
        )
        store.append_event(
            ExecutionEvent(
                event_id=f"event_{uuid.uuid4().hex}",
                run_id=run_id,
                commitment_id=commitment_id,
                event_type=EventType.TOOL_SUCCEEDED,
                tool_call_id=tool_call_id,
                tool_name="v2.curve_fitting",
                capability=CURVE_FITTING_CAPABILITY,
                dataset_version_ids=(analysis.dataset_version_id,),
                result_ref=computation_ref,
            )
        )
        kind = {
            "supported": FindingKind.ESTIMATE,
            "null_result": FindingKind.NULL_RESULT,
            "limited": FindingKind.LIMITATION,
        }[result.status]
        finding = Finding(
            finding_id=f"finding_{uuid.uuid4().hex}",
            commitment_id=commitment_id,
            finding_kind=kind,
            dataset_version_ids=(analysis.dataset_version_id,),
            metric_identity=result.metric,
            method_capability=CURVE_FITTING_CAPABILITY,
            maximum_claim_class=result.maximum_claim_class,
            computation_ref=computation_ref,
            effective_sample=len(result.points),
            uncertainty={
                "mode": result.mode,
                "x_label": result.x_label,
                "best_family": result.best_family,
                "fits": [
                    {
                        "family": fit.family,
                        "formula": fit.formula,
                        "params": fit.params,
                        "r_squared": fit.r_squared,
                        "sse": fit.sse,
                        "n_points": fit.n_points,
                        "mean_residual": fit.mean_residual,
                        "max_abs_residual": fit.max_abs_residual,
                    }
                    for fit in result.fits
                ],
                "excluded_families": dict(result.excluded_families),
                "points": [asdict(point) for point in result.points],
                "reason_code": result.reason_code,
            },
            limitations=result.limitations,
        )
        store.append_finding(finding)
        yield RuntimeEvent(
            "tool_finished",
            {"name": "curve_fitting", "status": "succeeded", "result_status": result.status},
        )

        artifact_ids: tuple[str, ...] = ()
        chart_failed = False
        if result.status in {"supported", "null_result"} and result.points:
            try:
                artifact, html = build_curve_fit_chart(
                    result,
                    dataset_version_id=analysis.dataset_version_id,
                    finding_refs=(finding.finding_id,),
                    title="模型族拟合对比（观测范围内）",
                )
                store.write_chart_artifact(artifact, html)
                artifact_ids = (artifact.chart_id,)
                store.append_event(
                    ExecutionEvent(
                        event_id=f"event_{uuid.uuid4().hex}",
                        run_id=run_id,
                        commitment_id=commitment_id,
                        event_type=EventType.ARTIFACT_CREATED,
                        tool_name="v2.curve_chart_renderer",
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
                        tool_name="v2.curve_chart_renderer",
                        capability="visual.chart",
                        dataset_version_ids=(analysis.dataset_version_id,),
                        error_code=type(exc).__name__,
                        message="curve chart rendering failed",
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
            raise RuntimeError("Curve fitting commitment did not reach a publishable outcome")

        support_refs = (finding.finding_id,)
        if result.status == "supported":
            best = result.fits[0]
            comparison = "；".join(
                f"{fit.formula} R²={_number(fit.r_squared, 3)}" for fit in result.fits
            )
            params_text = "，".join(
                f"{key}={_number(value)}" for key, value in best.params.items()
            )
            narrative = (
                f"最优模型族为{ {'power': '幂律', 'exponential': '指数', 'logarithmic': '对数'}.get(best.family, best.family)}："
                f"{best.formula}，其中 {params_text}，R²={_number(best.r_squared, 3)}（原始尺度）。"
                f"模型族对比：{comparison}。该拟合仅描述当前观测范围，不支持外推或因果解释。"
            )
            claim_class = ClaimClass.DESCRIPTIVE
        elif result.status == "null_result":
            narrative = (
                f"三种模型族均未能有效描述该序列（最优 R²={_number(result.fits[0].r_squared, 3) if result.fits else '不可用'}）；"
                "序列可能存在结构断点或非单调形态，未发布拟合公式。"
            )
            claim_class = ClaimClass.DESCRIPTIVE
        else:
            messages = {
                "insufficient_points": "可用拟合点不足（需要至少 5 个不同 x 值才能比较模型族）。",
                "no_applicable_family": "三种模型族的取值约束（x>0、对数族需 y>0）均不满足。",
            }
            narrative = messages.get(result.reason_code, "当前数据条件不足，未发布拟合结果。")
            claim_class = ClaimClass.DESCRIPTIVE
        if result.status in {"supported", "null_result"}:
            excluded_zeros = sum(point.n_excluded_zeros for point in result.points)
            zero_note = (
                f"宽表序列共 {len(result.points)} 个拟合点；零值按截断缺失排除 {excluded_zeros} 个观测。"
                if result.mode == "wide_series" and excluded_zeros
                else f"共 {len(result.points)} 个拟合点。"
            )
            method = (
                f"拟合模式为{'宽表列序列（各列均值）' if result.mode == 'wide_series' else 'x/y 列绑定'}；"
                f"x 口径：{result.x_label}。{zero_note}"
                "三族模型（幂律/指数/对数）经对数线性化最小二乘拟合，R² 在原始尺度比较；"
                "曲线仅在观测 x 范围内绘制。"
            )
        else:
            method = (
                "已执行：序列提取与模型族约束诊断；"
                "未执行：拟合——上述数据条件不满足模型族前提。"
            )
        if chart_failed:
            method += " 图表生成失败，但结构化拟合结果仍可发布。"
        if result.excluded_families:
            method += "不适用模型族：" + "、".join(
                f"{family}（{reason}）" for family, reason in result.excluded_families.items()
            ) + "。"
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
                headline="方法与边界",
                narrative=method,
                support_refs=support_refs,
                claim_class=claim_class,
                limitations=result.limitations,
            ),
        ]
        compiled = compile_answer(drafts, [finding], {commitment_id: outcome})
        store.write_turn_blocks(
            turn_id,
            list(compiled.blocks),
            status="finalized",
            artifact_ids=artifact_ids,
            request_context={
                "filename": filename,
                "series_columns": ",".join(spec.series_columns),
                "x_column": spec.x_column,
                "y_column": spec.y_column,
                "zero_values": spec.zero_values,
                "question": user_question,
                "analysis_kind": "curve_fitting",
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
