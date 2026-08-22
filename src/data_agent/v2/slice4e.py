from __future__ import annotations

import hashlib
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Iterator

from data_agent.v2.answer import compile_answer
from data_agent.v2.dataset import DatasetRegistry, DatasetRole
from data_agent.v2.exploratory import build_exploratory_artifact, execute_exploratory_python
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
from data_agent.v2.tools import DESCRIBE_NUMERIC_CONTRACT, describe_numeric


CORE_CAPABILITY = "analysis.describe"
EXPLORATORY_CAPABILITY = "exploration.python"


def _source_identity(path: Path) -> str:
    return f"upload:{path.name}:sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _number(value: float) -> str:
    return f"{value:,.4f}".rstrip("0").rstrip(".")


class Slice4EExploratoryRuntime:
    """Structured descriptive answer plus non-promotable Python exploration."""

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
        purpose: str,
        code: str,
    ) -> Iterator[RuntimeEvent]:
        source_path = self._source_path(filename)
        metric_name = str(metric or "").strip()
        user_question = str(question or "").strip()
        exploration_purpose = str(purpose or "").strip()
        exploration_code = str(code or "").strip()
        if not metric_name or not user_question:
            raise ValueError("metric and question are required")
        if not exploration_purpose or not exploration_code:
            raise ValueError("purpose and code are required")

        run_id = f"run_{uuid.uuid4().hex}"
        commitment_id = f"commitment_{uuid.uuid4().hex}"
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
            transform={"operation": "identity_exploratory_copy", "lossless": True},
        )
        frame = datasets.get_frame(analysis.dataset_version_id)
        commitment = Commitment(
            commitment_id=commitment_id,
            priority=CommitmentPriority.CORE,
            question=user_question,
            dataset_version_ids=(analysis.dataset_version_id,),
            accepted_result_kinds=(FindingKind.ESTIMATE, FindingKind.NULL_RESULT),
            accepted_method_capabilities=(CORE_CAPABILITY,),
            target_semantics=metric_name,
        )
        store.append_commitments(run_id, turn_id, [commitment])
        yield RuntimeEvent("commitment_snapshot", {"commitments": [asdict(commitment)]})

        core_call_id = f"tool_{uuid.uuid4().hex}"
        core_ref = f"computation:{uuid.uuid4().hex}"
        store.append_event(
            ExecutionEvent(
                event_id=f"event_{uuid.uuid4().hex}", run_id=run_id,
                commitment_id=commitment_id, event_type=EventType.TOOL_STARTED,
                tool_call_id=core_call_id, tool_name="v2.describe_numeric",
                capability=CORE_CAPABILITY,
                dataset_version_ids=(analysis.dataset_version_id,),
            )
        )
        yield RuntimeEvent("tool_started", {"name": "describe_numeric", "capability": CORE_CAPABILITY})
        description = describe_numeric(frame, metric_name)
        store.append_event(
            ExecutionEvent(
                event_id=f"event_{uuid.uuid4().hex}", run_id=run_id,
                commitment_id=commitment_id, event_type=EventType.TOOL_SUCCEEDED,
                tool_call_id=core_call_id, tool_name="v2.describe_numeric",
                capability=CORE_CAPABILITY,
                dataset_version_ids=(analysis.dataset_version_id,), result_ref=core_ref,
            )
        )
        has_observations = int(description["count"]) > 0
        finding = Finding(
            finding_id=f"finding_{uuid.uuid4().hex}",
            commitment_id=commitment_id,
            finding_kind=FindingKind.ESTIMATE if has_observations else FindingKind.NULL_RESULT,
            dataset_version_ids=(analysis.dataset_version_id,),
            metric_identity=f"column:{metric_name}.mean",
            method_capability=CORE_CAPABILITY,
            maximum_claim_class=DESCRIBE_NUMERIC_CONTRACT.maximum_claim_class,
            computation_ref=core_ref,
            estimate=description["mean"] if has_observations else None,
            effective_sample=int(description["count"]),
            uncertainty={
                "minimum": description["minimum"], "maximum": description["maximum"],
                "missing": description["missing"],
            },
            limitations=DESCRIBE_NUMERIC_CONTRACT.known_limitations,
        )
        store.append_finding(finding)
        yield RuntimeEvent("tool_finished", {"name": "describe_numeric", "status": "succeeded"})

        projection = project_run(*store.read_run_facts(run_id))
        yield RuntimeEvent(
            "outcome_snapshot",
            {"publishable": projection.publishable,
             "outcomes": {key: asdict(value) for key, value in projection.outcomes.items()}},
        )
        if not projection.publishable:
            raise RuntimeError("Slice 4E core commitment did not reach a publishable outcome")

        exploratory_call_id = f"tool_{uuid.uuid4().hex}"
        store.append_event(
            ExecutionEvent(
                event_id=f"event_{uuid.uuid4().hex}", run_id=run_id,
                commitment_id=commitment_id, event_type=EventType.TOOL_STARTED,
                tool_call_id=exploratory_call_id, tool_name="v2.run_python",
                capability=EXPLORATORY_CAPABILITY,
                dataset_version_ids=(analysis.dataset_version_id,),
                input_digest=f"sha256:{hashlib.sha256(exploration_code.encode('utf-8')).hexdigest()}",
            )
        )
        yield RuntimeEvent("tool_started", {"name": "exploratory_python", "capability": EXPLORATORY_CAPABILITY})
        exploration = execute_exploratory_python(
            frame, code=exploration_code, purpose=exploration_purpose
        )
        artifact = build_exploratory_artifact(
            exploration,
            artifact_id=f"exploratory_{uuid.uuid4().hex}",
            dataset_version_id=analysis.dataset_version_id,
        )
        store.write_exploratory_artifact(artifact)
        event_type = EventType.TOOL_SUCCEEDED if exploration.status == "succeeded" else EventType.TOOL_FAILED
        store.append_event(
            ExecutionEvent(
                event_id=f"event_{uuid.uuid4().hex}", run_id=run_id,
                commitment_id=commitment_id, event_type=event_type,
                tool_call_id=exploratory_call_id, tool_name="v2.run_python",
                capability=EXPLORATORY_CAPABILITY,
                dataset_version_ids=(analysis.dataset_version_id,),
                result_ref=f"exploratory:{artifact.artifact_id}",
                error_code=exploration.error_code,
            )
        )
        yield RuntimeEvent(
            "tool_finished",
            {"name": "exploratory_python", "status": exploration.status,
             "error_code": exploration.error_code},
        )
        yield RuntimeEvent("supplemental_artifact_created", {"artifact": asdict(artifact)})

        if has_observations:
            direct = f"当前数据中 {metric_name} 的平均值为 {_number(float(description['mean']))}。"
            values = (float(description["mean"]),)
        else:
            direct = f"当前数据中 {metric_name} 没有可计算平均值的有效数值。"
            values = ()
        method = (
            f"核心回答来自 analysis.describe 的结构化描述统计，共 {description['count']} 条有效记录，"
            f"缺失 {description['missing']} 条。自由 Python 不在核心承诺接受的方法能力中。"
        )
        if exploration.status == "succeeded":
            fragments = []
            if exploration.output:
                fragments.append(f"stdout：{exploration.output.strip()}")
            if exploration.result:
                fragments.append(f"result：{exploration.result}")
            detail = "；".join(fragments) or "代码成功执行，但没有产生可展示输出。"
            supplement = (
                f"探索目的：{exploration_purpose}。{detail}。该输出未作为结论证据，"
                "也没有生成 verified Finding。"
            )
        else:
            supplement = (
                f"探索目的：{exploration_purpose}。代码未完成，状态为 {exploration.status}"
                f"（{exploration.error_code or 'unknown_error'}）。该失败未作为结论证据，"
                "且不影响上方结构化回答。"
            )
        drafts = [
            AnswerBlockDraft(
                block_id=f"block_{uuid.uuid4().hex}",
                block_type=AnswerBlockType.EXECUTIVE_ANSWER,
                headline="直接回答", narrative=direct,
                support_refs=(finding.finding_id,), claim_class=ClaimClass.DESCRIPTIVE,
                canonical_values=values,
            ),
            AnswerBlockDraft(
                block_id=f"block_{uuid.uuid4().hex}", block_type=AnswerBlockType.METHOD,
                headline="方法与证据边界", narrative=method,
                support_refs=(finding.finding_id,), claim_class=ClaimClass.DESCRIPTIVE,
                limitations=DESCRIBE_NUMERIC_CONTRACT.known_limitations,
            ),
            AnswerBlockDraft(
                block_id=f"block_{uuid.uuid4().hex}", block_type=AnswerBlockType.SUPPLEMENTAL,
                headline="探索性补充（不作为结论证据）", narrative=supplement,
                limitations=exploration.limitations,
            ),
        ]
        compiled = compile_answer(drafts, [finding], projection.outcomes)
        store.write_turn_blocks(
            turn_id, list(compiled.blocks), status="finalized",
            supplemental_artifact_ids=(artifact.artifact_id,),
            request_context={
                "filename": filename, "metric": metric_name, "question": user_question,
                "purpose": exploration_purpose, "analysis_kind": "exploratory_python",
            },
        )
        for block in compiled.blocks:
            yield RuntimeEvent("final_block_delta", {"turn_id": turn_id, "block": asdict(block)})
        yield RuntimeEvent(
            "turn_completed",
            {"session_id": session_id, "turn_id": turn_id, "run_id": run_id,
             "status": "completed", "answer_markdown": compiled.markdown},
        )
