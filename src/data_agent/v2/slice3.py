from __future__ import annotations

import hashlib
import uuid
from dataclasses import asdict, replace
from pathlib import Path
from typing import Iterator

from data_agent.v2.answer import compile_answer
from data_agent.v2.dataset import DatasetRegistry, DatasetRole, DatasetVersion
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
from data_agent.v2.transformation import (
    DateTransformDisposition,
    DateTransformPlan,
    TransformationDecision,
    TransformationOption,
    TransformationProposal,
    TransformationStore,
    apply_date_option,
    inspect_date_conversion,
)


DATE_TRANSFORM_CAPABILITY = "data.transform.datetime"


def _source_identity(path: Path) -> str:
    return f"upload:{path.name}:sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


class Slice3TransformationRuntime:
    """V2 vertical runtime for safe date conversion and semantic choice."""

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
    def _commitment(
        *, commitment_id: str, question: str, raw: DatasetVersion, date_column: str
    ) -> Commitment:
        return Commitment(
            commitment_id=commitment_id,
            priority=CommitmentPriority.CORE,
            question=question,
            dataset_version_ids=(raw.dataset_version_id,),
            accepted_result_kinds=(
                FindingKind.TRANSFORMATION,
                FindingKind.LIMITATION,
            ),
            accepted_method_capabilities=(DATE_TRANSFORM_CAPABILITY,),
            target_semantics=f"column:{date_column}:datetime",
        )

    @staticmethod
    def _event(
        *,
        run_id: str,
        commitment_id: str,
        event_type: EventType,
        dataset_version_ids: tuple[str, ...],
        result_ref: str = "",
        error_code: str = "",
        message: str = "",
    ) -> ExecutionEvent:
        return ExecutionEvent(
            event_id=f"event_{uuid.uuid4().hex}",
            run_id=run_id,
            commitment_id=commitment_id,
            event_type=event_type,
            tool_call_id=f"tool_{uuid.uuid4().hex}",
            tool_name="v2.date_transform",
            capability=DATE_TRANSFORM_CAPABILITY,
            dataset_version_ids=dataset_version_ids,
            result_ref=result_ref,
            error_code=error_code,
            message=message,
        )

    @staticmethod
    def _sensitivity(option: TransformationOption) -> dict[str, object]:
        return asdict(option.sensitivity)

    def _finish(
        self,
        *,
        store: V2FactStore,
        datasets: DatasetRegistry,
        commitment: Commitment,
        finding: Finding,
        turn_id: str,
        run_id: str,
        request_context: dict[str, str],
        headline: str,
        narrative: str,
        method_narrative: str,
    ) -> Iterator[RuntimeEvent]:
        store.append_finding(finding)
        projection = project_run(
            store.read_commitments(), store.read_events(), store.read_findings()
        )
        outcome = projection.outcomes[commitment.commitment_id]
        yield RuntimeEvent(
            "outcome_snapshot",
            {
                "publishable": projection.publishable,
                "outcomes": {commitment.commitment_id: asdict(outcome)},
            },
        )
        if not projection.publishable:
            raise RuntimeError("Slice 3 commitment did not reach a publishable outcome")
        support_refs = (finding.finding_id,)
        drafts = [
            AnswerBlockDraft(
                block_id=f"block_{uuid.uuid4().hex}",
                block_type=AnswerBlockType.EXECUTIVE_ANSWER,
                headline=headline,
                narrative=narrative,
                support_refs=support_refs,
                claim_class=ClaimClass.DESCRIPTIVE,
            ),
            AnswerBlockDraft(
                block_id=f"block_{uuid.uuid4().hex}",
                block_type=AnswerBlockType.METHOD,
                headline="转换依据与血缘",
                narrative=method_narrative,
                support_refs=support_refs,
                claim_class=ClaimClass.DESCRIPTIVE,
                limitations=finding.limitations,
            ),
        ]
        compiled = compile_answer(drafts, store.read_findings(), {commitment.commitment_id: outcome})
        store.write_turn_blocks(
            turn_id,
            list(compiled.blocks),
            status="finalized",
            request_context=request_context,
        )
        for block in compiled.blocks:
            yield RuntimeEvent(
                "final_block_delta", {"turn_id": turn_id, "block": asdict(block)}
            )
        yield RuntimeEvent(
            "turn_completed",
            {
                "turn_id": turn_id,
                "run_id": run_id,
                "status": "completed",
                "answer_markdown": compiled.markdown,
            },
        )

    def _finding(
        self,
        *,
        commitment: Commitment,
        raw: DatasetVersion,
        analysis: DatasetVersion | None,
        column: str,
        plan: DateTransformPlan,
        option: TransformationOption | None,
        mode: str,
        computation_ref: str,
    ) -> Finding:
        if analysis is None:
            return Finding(
                finding_id=f"finding_{uuid.uuid4().hex}",
                commitment_id=commitment.commitment_id,
                finding_kind=FindingKind.LIMITATION,
                dataset_version_ids=(raw.dataset_version_id,),
                metric_identity=f"column:{column}",
                method_capability=DATE_TRANSFORM_CAPABILITY,
                maximum_claim_class=ClaimClass.DESCRIPTIVE,
                computation_ref=computation_ref,
                effective_sample=raw.row_count,
                uncertainty={"reason_code": plan.reason_code},
                limitations=("转换会新增缺失值，因此没有静默修改分析数据。",),
            )
        return Finding(
            finding_id=f"finding_{uuid.uuid4().hex}",
            commitment_id=commitment.commitment_id,
            finding_kind=FindingKind.TRANSFORMATION,
            dataset_version_ids=(raw.dataset_version_id,),
            metric_identity=f"column:{column}",
            method_capability=DATE_TRANSFORM_CAPABILITY,
            maximum_claim_class=ClaimClass.DESCRIPTIVE,
            computation_ref=computation_ref,
            estimate=analysis.dataset_version_id,
            effective_sample=analysis.row_count,
            uncertainty=(self._sensitivity(option) if option else {}),
            assumption_results={
                "mode": mode,
                "source_version_id": raw.dataset_version_id,
                "analysis_version_id": analysis.dataset_version_id,
                "column": column,
                "date_format": option.date_format if option else "",
            },
                limitations=("原始数据保持不变；后续分析应使用新的分析版本。",),
        )

    def start(
        self,
        *,
        session_id: str,
        turn_id: str,
        filename: str,
        date_column: str,
        question: str,
    ) -> Iterator[RuntimeEvent]:
        source_path = self._source_path(filename)
        field_name = str(date_column or "").strip()
        user_question = str(question or "").strip()
        if not field_name or not user_question:
            raise ValueError("date_column and question are required")
        run_id = f"run_{uuid.uuid4().hex}"
        commitment_id = f"commitment_{uuid.uuid4().hex}"
        computation_ref = f"computation:{uuid.uuid4().hex}"
        store = V2FactStore(self.sessions_root, session_id)
        datasets = DatasetRegistry(self.sessions_root, session_id)
        transforms = TransformationStore(self.sessions_root, session_id)
        yield RuntimeEvent(
            "turn_started", {"session_id": session_id, "turn_id": turn_id, "run_id": run_id}
        )
        raw_frame = _load_frame(source_path)
        raw = datasets.register_raw(
            source_path.stem, raw_frame, source_identity=_source_identity(source_path)
        )
        commitment = self._commitment(
            commitment_id=commitment_id,
            question=user_question,
            raw=raw,
            date_column=field_name,
        )
        store.write_commitments([commitment])
        yield RuntimeEvent("commitment_snapshot", {"commitments": [asdict(commitment)]})
        started = self._event(
            run_id=run_id,
            commitment_id=commitment_id,
            event_type=EventType.TOOL_STARTED,
            dataset_version_ids=(raw.dataset_version_id,),
        )
        store.append_event(started)
        yield RuntimeEvent(
            "tool_started",
            {"name": "date_transform", "capability": DATE_TRANSFORM_CAPABILITY},
        )
        plan = inspect_date_conversion(raw_frame, field_name)
        context = {
            "filename": filename,
            "date_column": field_name,
            "question": user_question,
            "analysis_kind": "date_transformation",
        }

        if plan.disposition is DateTransformDisposition.NEEDS_INPUT:
            options: list[TransformationOption] = []
            for option in plan.options:
                candidate_frame = apply_date_option(raw_frame, field_name, option)
                candidate = datasets.derive(
                    parent_version_id=raw.dataset_version_id,
                    frame=candidate_frame,
                    role=DatasetRole.CANDIDATE,
                    transform={
                        "operation": "parse_datetime",
                        "column": field_name,
                        "option_key": option.option_key,
                        "date_format": option.date_format,
                        "reason_code": plan.reason_code,
                    },
                )
                options.append(replace(option, candidate_version_id=candidate.dataset_version_id))
            proposal = TransformationProposal(
                proposal_id=f"proposal_{uuid.uuid4().hex}",
                turn_id=turn_id,
                run_id=run_id,
                commitment_id=commitment_id,
                parent_version_id=raw.dataset_version_id,
                parent_content_fingerprint=raw.content_fingerprint,
                column=field_name,
                target_type="datetime",
                reason_code=plan.reason_code,
                options=tuple(options),
            )
            transforms.append_proposal(proposal)
            waiting = self._event(
                run_id=run_id,
                commitment_id=commitment_id,
                event_type=EventType.USER_INPUT_REQUIRED,
                dataset_version_ids=(raw.dataset_version_id,),
                result_ref=proposal.proposal_id,
                error_code=plan.reason_code,
                message="date order requires user semantic choice",
            )
            store.append_event(waiting)
            projection = project_run(
                store.read_commitments(), store.read_events(), store.read_findings()
            )
            outcome = projection.outcomes[commitment_id]
            context["proposal_id"] = proposal.proposal_id
            store.write_turn_blocks(turn_id, [], status="draft", request_context=context)
            yield RuntimeEvent(
                "outcome_snapshot",
                {"publishable": False, "outcomes": {commitment_id: asdict(outcome)}},
            )
            yield RuntimeEvent("user_input_required", asdict(proposal))
            return

        if plan.disposition is DateTransformDisposition.AUTO_APPLY:
            option = plan.options[0]
            converted = apply_date_option(raw_frame, field_name, option)
            analysis = datasets.derive(
                parent_version_id=raw.dataset_version_id,
                frame=converted,
                role=DatasetRole.ANALYSIS,
                transform={
                    "operation": "parse_datetime",
                    "column": field_name,
                    "option_key": option.option_key,
                    "date_format": option.date_format,
                    "lossless": True,
                    "automatic": True,
                },
            )
            succeeded = self._event(
                run_id=run_id,
                commitment_id=commitment_id,
                event_type=EventType.TOOL_SUCCEEDED,
                dataset_version_ids=(raw.dataset_version_id, analysis.dataset_version_id),
                result_ref=computation_ref,
            )
            store.append_event(succeeded)
            yield RuntimeEvent(
                "tool_finished",
                {"status": "succeeded", "analysis_version_id": analysis.dataset_version_id},
            )
            finding = self._finding(
                commitment=commitment,
                raw=raw,
                analysis=analysis,
                column=field_name,
                plan=plan,
                option=option,
                mode="automatic",
                computation_ref=computation_ref,
            )
            narrative = (
                f"{field_name} 已按 {option.label} 无损转换为日期字段；"
                f"{option.sensitivity.parsed_non_null} 个非空值全部解析成功，未请求额外许可。"
            )
            method = (
                "原始上传版本保持不变；系统创建新的分析版本，并在服务端记录"
                "父版本、日期格式和无损转换标记。"
            )
            yield from self._finish(
                store=store,
                datasets=datasets,
                commitment=commitment,
                finding=finding,
                turn_id=turn_id,
                run_id=run_id,
                request_context=context,
                headline="日期转换已完成",
                narrative=narrative,
                method_narrative=method,
            )
            return

        failed = self._event(
            run_id=run_id,
            commitment_id=commitment_id,
            event_type=EventType.TOOL_SUCCEEDED,
            dataset_version_ids=(raw.dataset_version_id,),
            result_ref=computation_ref,
            message=plan.reason_code,
        )
        store.append_event(failed)
        yield RuntimeEvent(
            "tool_finished", {"status": "limited", "reason_code": plan.reason_code}
        )
        finding = self._finding(
            commitment=commitment,
            raw=raw,
            analysis=None,
            column=field_name,
            plan=plan,
            option=None,
            mode="not_applied",
            computation_ref=computation_ref,
        )
        yield from self._finish(
            store=store,
            datasets=datasets,
            commitment=commitment,
            finding=finding,
            turn_id=turn_id,
            run_id=run_id,
            request_context=context,
            headline="日期转换未执行",
            narrative="当前转换会新增缺失值，因此系统没有静默修改数据。",
            method_narrative="原始上传版本保持不变，也没有生成带新增缺失的分析版本。",
        )

    def resolve(
        self,
        *,
        session_id: str,
        turn_id: str,
        proposal_id: str,
        option_key: str,
        expected_parent_version_id: str,
        expected_parent_content_fingerprint: str,
    ) -> Iterator[RuntimeEvent]:
        store = V2FactStore(self.sessions_root, session_id)
        datasets = DatasetRegistry(self.sessions_root, session_id)
        transforms = TransformationStore(self.sessions_root, session_id)
        proposal = transforms.get_proposal(proposal_id)
        if proposal.turn_id != turn_id:
            raise ValueError("proposal does not belong to this turn")
        parent = datasets.get_version(proposal.parent_version_id)
        decision_identity = hashlib.sha256(
            f"{proposal.proposal_id}:{option_key}".encode("utf-8")
        ).hexdigest()[:24]
        decision = TransformationDecision(
            decision_id=f"decision_{decision_identity}",
            proposal_id=proposal.proposal_id,
            option_key=str(option_key or "").strip(),
            expected_parent_version_id=str(expected_parent_version_id or "").strip(),
            expected_parent_content_fingerprint=str(
                expected_parent_content_fingerprint or ""
            ).strip(),
        )
        transforms.append_decision(
            decision,
            active_parent_version_id=parent.dataset_version_id,
            active_parent_content_fingerprint=parent.content_fingerprint,
        )
        option = next(item for item in proposal.options if item.option_key == decision.option_key)
        analysis = datasets.promote_candidate(
            option.candidate_version_id,
            expected_parent_version_id=proposal.parent_version_id,
            proposal_id=proposal.proposal_id,
            decision_id=decision.decision_id,
        )
        commitment = next(
            item
            for item in store.read_commitments()
            if item.commitment_id == proposal.commitment_id
        )
        yield RuntimeEvent(
            "turn_started",
            {
                "session_id": session_id,
                "turn_id": turn_id,
                "run_id": proposal.run_id,
                "resumed": True,
            },
        )
        succeeded = self._event(
            run_id=proposal.run_id,
            commitment_id=proposal.commitment_id,
            event_type=EventType.TOOL_SUCCEEDED,
            dataset_version_ids=(proposal.parent_version_id, analysis.dataset_version_id),
            result_ref=analysis.dataset_version_id,
            message=f"confirmed option {option.option_key}",
        )
        store.append_event(succeeded)
        yield RuntimeEvent(
            "tool_finished",
            {
                "status": "succeeded",
                "mode": "confirmed",
                "analysis_version_id": analysis.dataset_version_id,
            },
        )
        finding = self._finding(
            commitment=commitment,
            raw=parent,
            analysis=analysis,
            column=proposal.column,
            plan=DateTransformPlan(
                DateTransformDisposition.NEEDS_INPUT,
                proposal.column,
                proposal.reason_code,
                proposal.options,
            ),
            option=option,
            mode="user_confirmed",
            computation_ref=analysis.dataset_version_id,
        )
        context = V2FactStore(self.sessions_root, session_id).read_turn_blocks(turn_id)[
            "request_context"
        ]
        narrative = (
            f"已按你选择的“{option.label}”解释 {proposal.column}；"
            f"{option.sensitivity.parsed_non_null} 个非空值全部转换成功。"
        )
        method = (
            "该选择已绑定到当前原始数据及其内容指纹；所选候选被提升为新的"
            "分析版本，未选择的候选保留作敏感性记录，原始版本未修改。"
        )
        yield from self._finish(
            store=store,
            datasets=datasets,
            commitment=commitment,
            finding=finding,
            turn_id=turn_id,
            run_id=proposal.run_id,
            request_context=context,
            headline="日期语义已确认并应用",
            narrative=narrative,
            method_narrative=method,
        )
