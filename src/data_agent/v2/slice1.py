from __future__ import annotations

import hashlib
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterator

import pandas as pd

from data_agent.v2.answer import compile_answer
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
from data_agent.v2.tools import DESCRIBE_NUMERIC_CONTRACT, describe_numeric


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

        commitment = Commitment(
            commitment_id=commitment_id,
            priority=CommitmentPriority.CORE,
            question=user_question,
            target_semantics=metric_name,
            dataset_version_ids=(analysis_version.dataset_version_id,),
            accepted_result_kinds=(FindingKind.ESTIMATE, FindingKind.NULL_RESULT),
            accepted_method_capabilities=(DESCRIBE_NUMERIC_CONTRACT.capability,),
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
            tool_name="v2.describe_numeric",
            capability=DESCRIBE_NUMERIC_CONTRACT.capability,
            dataset_version_ids=(analysis_version.dataset_version_id,),
        )
        store.append_event(started)
        yield RuntimeEvent(
            "tool_started",
            {
                "tool_call_id": tool_call_id,
                "name": "describe_numeric",
                "capability": DESCRIBE_NUMERIC_CONTRACT.capability,
            },
        )

        result = describe_numeric(
            datasets.get_frame(analysis_version.dataset_version_id),
            metric_name,
        )
        succeeded = ExecutionEvent(
            event_id=f"event_{uuid.uuid4().hex}",
            run_id=run_id,
            commitment_id=commitment_id,
            event_type=EventType.TOOL_SUCCEEDED,
            tool_call_id=tool_call_id,
            tool_name="v2.describe_numeric",
            capability=DESCRIBE_NUMERIC_CONTRACT.capability,
            dataset_version_ids=(analysis_version.dataset_version_id,),
            result_ref=computation_ref,
        )
        store.append_event(succeeded)
        has_observations = int(result["count"]) > 0
        finding = Finding(
            finding_id=finding_id,
            commitment_id=commitment_id,
            finding_kind=(FindingKind.ESTIMATE if has_observations else FindingKind.NULL_RESULT),
            dataset_version_ids=(analysis_version.dataset_version_id,),
            metric_identity=f"column:{metric_name}.mean",
            method_capability=DESCRIBE_NUMERIC_CONTRACT.capability,
            estimate=result["mean"] if has_observations else None,
            direction="level" if has_observations else "",
            effective_sample=int(result["count"]),
            uncertainty={
                "minimum": result["minimum"],
                "maximum": result["maximum"],
                "missing": result["missing"],
            },
            limitations=DESCRIBE_NUMERIC_CONTRACT.known_limitations,
            maximum_claim_class=DESCRIBE_NUMERIC_CONTRACT.maximum_claim_class,
            computation_ref=computation_ref,
        )
        store.append_finding(finding)
        yield RuntimeEvent(
            "tool_finished",
            {
                "tool_call_id": tool_call_id,
                "name": "describe_numeric",
                "status": "succeeded",
                "result_ref": computation_ref,
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

        if has_observations:
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

        drafts = [
            AnswerBlockDraft(
                block_id=f"block_{uuid.uuid4().hex}",
                block_type=AnswerBlockType.EXECUTIVE_ANSWER,
                support_refs=(finding_id,),
                headline="直接回答",
                narrative=answer_narrative,
                claim_class=ClaimClass.DESCRIPTIVE,
                canonical_values=answer_values,
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
                narrative=(
                    "结果来自当前分析副本的描述统计。它只概括这份数据，"
                    "不表示变量之间存在因果关系，也不能自动推广到数据范围之外。"
                ),
                claim_class=ClaimClass.DESCRIPTIVE,
                limitations=DESCRIBE_NUMERIC_CONTRACT.known_limitations,
            ),
        ]
        compiled = compile_answer(drafts, [finding], {commitment_id: outcome})
        store.write_turn_blocks(turn_id, list(compiled.blocks), status="finalized")
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
