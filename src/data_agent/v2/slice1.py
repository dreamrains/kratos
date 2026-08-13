from __future__ import annotations

import hashlib
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterator

import pandas as pd

from data_agent.v2.answer import compile_answer
from data_agent.v2.chart import build_trend_chart, decide_chart
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
from data_agent.v2.store import V2FactStore
from data_agent.v2.tools import (
    DESCRIBE_NUMERIC_CONTRACT,
    DESCRIBE_TREND_CONTRACT,
    describe_numeric,
    describe_trend,
)


@dataclass(frozen=True, slots=True)
class RuntimeEvent:
    event: str
    data: dict[str, Any]


def _load_frame(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix == ".tsv":
        return pd.read_csv(path, sep="\t")
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    if suffix in {".json", ".jsonl"}:
        return pd.read_json(path, lines=suffix == ".jsonl")
    if suffix == ".parquet":
        return pd.read_parquet(path)
    raise ValueError(f"unsupported Slice 1 file type: {suffix}")


def _source_identity(path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return f"upload:{path.name}:sha256:{digest}"


def _number(value: float) -> str:
    if value.is_integer():
        return f"{int(value):,}"
    return f"{value:,.4f}".rstrip("0").rstrip(".")


class Slice1DescriptiveRuntime:
    """Minimal V2 vertical runtime for one explicit numeric description."""

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
        metric: str,
        question: str,
    ) -> Iterator[RuntimeEvent]:
        source_path = self._source_path(filename)
        metric_name = str(metric or "").strip()
        user_question = str(question or "").strip()
        if not metric_name or not user_question:
            raise ValueError("metric and question are required")

        run_id = f"run_{uuid.uuid4().hex}"
        commitment_id = f"commitment_{uuid.uuid4().hex}"
        tool_call_id = f"tool_{uuid.uuid4().hex}"
        computation_ref = f"computation:{uuid.uuid4().hex}"
        finding_id = f"finding_{uuid.uuid4().hex}"

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
            transform={"operation": "identity_analysis_copy", "lossless": True},
        )
        analysis_frame = datasets.get_frame(analysis_version.dataset_version_id)
        chart_decision = decide_chart(
            analysis_frame,
            metric=metric_name,
            question=user_question,
        )
        method_contract = (
            DESCRIBE_TREND_CONTRACT if chart_decision.warranted else DESCRIBE_NUMERIC_CONTRACT
        )
        tool_name = "describe_trend" if chart_decision.warranted else "describe_numeric"

        commitment = Commitment(
            commitment_id=commitment_id,
            priority=CommitmentPriority.CORE,
            question=user_question,
            target_semantics=metric_name,
            dataset_version_ids=(analysis_version.dataset_version_id,),
            accepted_result_kinds=(FindingKind.ESTIMATE, FindingKind.NULL_RESULT),
            accepted_method_capabilities=(method_contract.capability,),
            visualization_intent=(
                f"line:{chart_decision.x_field}:{metric_name}"
                if chart_decision.warranted
                else ""
            ),
        )
        store.write_commitments([commitment])
        yield RuntimeEvent(
            "commitment_snapshot",
            {"commitments": [asdict(commitment)]},
        )

        started = ExecutionEvent(
            event_id=f"event_{uuid.uuid4().hex}",
            run_id=run_id,
            commitment_id=commitment_id,
            event_type=EventType.TOOL_STARTED,
            tool_call_id=tool_call_id,
            tool_name=f"v2.{tool_name}",
            capability=method_contract.capability,
            dataset_version_ids=(analysis_version.dataset_version_id,),
        )
        store.append_event(started)
        yield RuntimeEvent(
            "tool_started",
            {
                "tool_call_id": tool_call_id,
                "name": tool_name,
                "capability": method_contract.capability,
            },
        )

        if chart_decision.warranted:
            result = describe_trend(
                analysis_frame,
                metric_name,
                chart_decision.x_field,
            )
        else:
            result = describe_numeric(analysis_frame, metric_name)
        succeeded = ExecutionEvent(
            event_id=f"event_{uuid.uuid4().hex}",
            run_id=run_id,
            commitment_id=commitment_id,
            event_type=EventType.TOOL_SUCCEEDED,
            tool_call_id=tool_call_id,
            tool_name=f"v2.{tool_name}",
            capability=method_contract.capability,
            dataset_version_ids=(analysis_version.dataset_version_id,),
            result_ref=computation_ref,
        )
        store.append_event(succeeded)
        has_observations = int(result["count"]) > 0
        if chart_decision.warranted:
            change = float(result["absolute_change"])
            finding = Finding(
                finding_id=finding_id,
                commitment_id=commitment_id,
                finding_kind=FindingKind.ESTIMATE,
                dataset_version_ids=(analysis_version.dataset_version_id,),
                metric_identity=f"column:{metric_name}.ordered_change",
                method_capability=method_contract.capability,
                estimate=change,
                direction=("increase" if change > 0 else "decrease" if change < 0 else "flat"),
                effective_sample=int(result["count"]),
                time_scope=f"{result['start_time']}..{result['end_time']}",
                uncertainty={
                    "start_time": result["start_time"],
                    "end_time": result["end_time"],
                    "start_value": result["start_value"],
                    "end_value": result["end_value"],
                    "absolute_change": result["absolute_change"],
                    "percent_change": result["percent_change"],
                    "missing": result["missing"],
                },
                limitations=method_contract.known_limitations,
                maximum_claim_class=method_contract.maximum_claim_class,
                computation_ref=computation_ref,
            )
        else:
            finding = Finding(
                finding_id=finding_id,
                commitment_id=commitment_id,
                finding_kind=(
                    FindingKind.ESTIMATE if has_observations else FindingKind.NULL_RESULT
                ),
                dataset_version_ids=(analysis_version.dataset_version_id,),
                metric_identity=f"column:{metric_name}.mean",
                method_capability=method_contract.capability,
                estimate=result["mean"] if has_observations else None,
                direction="level" if has_observations else "",
                effective_sample=int(result["count"]),
                uncertainty={
                    "minimum": result["minimum"],
                    "maximum": result["maximum"],
                    "missing": result["missing"],
                },
                limitations=method_contract.known_limitations,
                maximum_claim_class=method_contract.maximum_claim_class,
                computation_ref=computation_ref,
            )
        store.append_finding(finding)
        yield RuntimeEvent(
            "tool_finished",
            {
                "tool_call_id": tool_call_id,
                "name": tool_name,
                "status": "succeeded",
                "result_ref": computation_ref,
            },
        )

        artifact_ids: tuple[str, ...] = ()
        chart_unavailable = False
        if chart_decision.warranted:
            try:
                artifact, chart_html = build_trend_chart(
                    analysis_frame,
                    decision=chart_decision,
                    metric=metric_name,
                    dataset_version_id=analysis_version.dataset_version_id,
                    finding_refs=(finding_id,),
                    title=f"{metric_name} 趋势",
                )
                store.write_chart_artifact(artifact, chart_html)
                artifact_ids = (artifact.chart_id,)
                store.append_event(
                    ExecutionEvent(
                        event_id=f"event_{uuid.uuid4().hex}",
                        run_id=run_id,
                        commitment_id=commitment_id,
                        event_type=EventType.ARTIFACT_CREATED,
                        tool_name="v2.chart_renderer",
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
                chart_unavailable = True
                store.append_event(
                    ExecutionEvent(
                        event_id=f"event_{uuid.uuid4().hex}",
                        run_id=run_id,
                        commitment_id=commitment_id,
                        event_type=EventType.ARTIFACT_FAILED,
                        tool_name="v2.chart_renderer",
                        capability="visual.chart",
                        dataset_version_ids=(analysis_version.dataset_version_id,),
                        error_code=type(exc).__name__,
                        message="chart rendering failed",
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

        projection = project_run(
            store.read_commitments(),
            store.read_events(),
            store.read_findings(),
        )
        outcome = projection.outcomes[commitment_id]
        yield RuntimeEvent(
            "outcome_snapshot",
            {
                "publishable": projection.publishable,
                "outcomes": {commitment_id: asdict(outcome)},
            },
        )
        if not projection.publishable:
            raise RuntimeError("Slice 1 core commitment did not reach a publishable outcome")

        chart_refs: tuple[str, ...] = ()
        if chart_decision.warranted:
            chart_refs = artifact_ids
            start_value = _number(float(result["start_value"]))
            end_value = _number(float(result["end_value"]))
            change_value = float(result["absolute_change"])
            change_text = _number(abs(change_value))
            direction_text = "增加" if change_value > 0 else "减少" if change_value < 0 else "持平"
            percent_change = result["percent_change"]
            percent_text = (
                f"（{_number(abs(float(percent_change)))}%）"
                if percent_change is not None
                else ""
            )
            answer_narrative = (
                f"从 {result['start_time']} 的 {start_value} 到 {result['end_time']} 的 "
                f"{end_value}，{metric_name} {direction_text} {change_text}{percent_text}。"
            )
            answer_values = (
                float(result["start_value"]),
                float(result["end_value"]),
                change_value,
            ) + ((float(percent_change),) if percent_change is not None else ())
            overview_narrative = (
                f"趋势描述使用 {result['count']} 个有效时间点，"
                f"另有 {result['missing']} 条记录缺失时间或数值。"
            )
            overview_values = (int(result["count"]), int(result["missing"]))
            method_narrative = (
                "结果按可解析日期排序，比较当前观测区间的首尾数值。"
                + (
                    "图表生成不可用，因此仅发布结构化数值结论。"
                    if chart_unavailable
                    else "折线图展示全部有效点。"
                )
                + "它不构成长期趋势、显著性或因果结论。"
            )
        elif has_observations:
            mean_text = _number(float(result["mean"]))
            minimum_text = _number(float(result["minimum"]))
            maximum_text = _number(float(result["maximum"]))
            answer_narrative = (
                f"在当前数据范围内，{metric_name}的平均值为 {mean_text}。"
            )
            answer_values = (float(result["mean"]),)
            overview_narrative = (
                f"共有 {result['count']} 条有效记录；最小值为 {minimum_text}，"
                f"最大值为 {maximum_text}，缺失 {result['missing']} 条。"
            )
            overview_values = (
                int(result["count"]),
                float(result["minimum"]),
                float(result["maximum"]),
                int(result["missing"]),
            )
            method_narrative = (
                "结果来自当前分析副本的描述统计。它只概括这份数据，"
                "不表示变量之间存在因果关系，也不能自动推广到数据范围之外。"
            )
        else:
            answer_narrative = (
                f"当前数据范围内，{metric_name}没有可用于计算平均值的数值观测，"
                "因此无法给出平均值。"
            )
            answer_values = ()
            overview_narrative = (
                f"共有 0 条有效记录；{result['missing']} 条记录缺失或无法解析为数值。"
            )
            overview_values = (0, int(result["missing"]))
            method_narrative = (
                "结果来自当前分析副本的描述统计。它只概括这份数据，"
                "不表示变量之间存在因果关系，也不能自动推广到数据范围之外。"
            )

        drafts = [
            AnswerBlockDraft(
                block_id=f"block_{uuid.uuid4().hex}",
                block_type=AnswerBlockType.EXECUTIVE_ANSWER,
                support_refs=(finding_id,),
                headline="直接回答",
                narrative=answer_narrative,
                claim_class=ClaimClass.DESCRIPTIVE,
                canonical_values=answer_values,
                chart_refs=chart_refs,
            ),
            AnswerBlockDraft(
                block_id=f"block_{uuid.uuid4().hex}",
                block_type=AnswerBlockType.KEY_FINDING,
                support_refs=(finding_id,),
                headline="数据概况",
                narrative=overview_narrative,
                claim_class=ClaimClass.DESCRIPTIVE,
                canonical_values=overview_values,
            ),
            AnswerBlockDraft(
                block_id=f"block_{uuid.uuid4().hex}",
                block_type=AnswerBlockType.METHOD,
                support_refs=(finding_id,),
                headline="方法与局限",
                narrative=method_narrative,
                claim_class=ClaimClass.DESCRIPTIVE,
                limitations=(
                    method_contract.known_limitations
                    + (("图表生成失败，本答案仅保留结构化数值结论。",) if chart_unavailable else ())
                ),
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
                "metric": metric_name,
                "question": user_question,
                "analysis_kind": "descriptive",
            },
        )
        for block in compiled.blocks:
            yield RuntimeEvent(
                "final_block_delta",
                {"turn_id": turn_id, "block": asdict(block)},
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
