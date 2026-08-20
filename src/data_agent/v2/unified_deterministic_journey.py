from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from data_agent.v2.dataset import DatasetRegistry, DatasetRole
from data_agent.v2.execution_control import ActiveRunRegistry
from data_agent.v2.models import (
    AnswerBlockDraft,
    AnswerBlockType,
    ClaimClass,
    Finding,
)
from data_agent.v2.projection import project_run
from data_agent.v2.release import (
    LayerStatus,
    ReleaseReceipt,
    ScenarioRequirement,
    ValidationLayer,
)
from data_agent.v2.router import AnalysisKind, AnalysisRouter
from data_agent.v2.slice1 import RuntimeEvent
from data_agent.v2.store import TurnPublicationBlocked, V2FactStore


DETERMINISTIC_JOURNEY_VERSION = "v2_unified_deterministic_journey.v1"
UNIFIED_DATASET_FIXTURE = "tests/fixtures/v2_slice4d_combined.csv"

OWNER_OBSERVATIONS = (
    "immutable_dataset_versions",
    "findings_bound_to_commitments",
    "completion_computed_from_ledger",
    "published_blocks_bound_to_findings",
    "charts_bound_to_findings",
    "run_state_matches_publication",
)

INCIDENT_OBSERVATIONS = (
    "unsupported_finding_did_not_publish",
    "stop_won_before_publication",
    "interrupted_turn_persisted",
    "final_after_interrupt_blocked",
    "session_isolation_preserved",
)

INTERRUPTED_REQUIRED_EVENTS = (
    "turn_started",
    "commitment_snapshot",
    "tool_started",
    "outcome_snapshot",
    "turn_interrupted",
)


@dataclass(frozen=True, slots=True)
class DeterministicJourneyValidation:
    passed: bool
    reason_codes: tuple[str, ...]
    receipts: tuple[ReleaseReceipt, ...] = ()


def _ordered(events: list[str], names: tuple[str, ...]) -> bool:
    try:
        positions = [events.index(name) for name in names]
    except ValueError:
        return False
    return positions == sorted(positions) and len(set(positions)) == len(positions)


def _evidence_ref(evidence: dict[str, Any]) -> str:
    canonical = json.dumps(
        evidence, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "deterministic:unified:sha256:" + hashlib.sha256(canonical).hexdigest()


def _owner_observations(
    *,
    sessions_root: Path,
    session_id: str,
    turn_id: str,
    run_id: str,
    final_block_delta_count: int,
) -> dict[str, bool]:
    registry = DatasetRegistry(sessions_root, session_id)
    versions = registry.list_versions()
    raw = next((item for item in versions if item.role is DatasetRole.RAW), None)
    analysis = next(
        (item for item in versions if item.role is DatasetRole.ANALYSIS), None
    )
    immutable_versions = bool(
        raw
        and analysis
        and analysis.parent_version_id == raw.dataset_version_id
        and registry.get_frame(raw.dataset_version_id).shape[0] == raw.row_count
        and registry.get_frame(analysis.dataset_version_id).shape[0]
        == analysis.row_count
    )

    store = V2FactStore(sessions_root, session_id)
    commitments, events, findings = store.read_run_facts(run_id)
    by_commitment = {item.commitment_id: item for item in commitments}
    findings_bound = bool(findings) and all(
        finding.commitment_id in by_commitment
        and finding.finding_kind
        in by_commitment[finding.commitment_id].accepted_result_kinds
        and finding.method_capability
        in by_commitment[finding.commitment_id].accepted_method_capabilities
        and set(finding.dataset_version_ids)
        == set(by_commitment[finding.commitment_id].dataset_version_ids)
        for finding in findings
    )
    projection = project_run(commitments, events, findings)
    completion_computed = bool(commitments and findings and projection.publishable)

    turn = store.read_turn_blocks(turn_id)
    finding_ids = {item.finding_id for item in findings}
    blocks_bound = bool(turn["blocks"]) and all(
        set(block.get("support_refs") or ()) <= finding_ids
        and "[[evidence:" not in str(block.get("narrative") or "")
        for block in turn["blocks"]
    )
    artifact_ids = set(turn["artifact_ids"])
    chart_refs = {
        chart_id
        for block in turn["blocks"]
        for chart_id in block.get("chart_refs") or ()
    }
    charts_bound = bool(turn["artifacts"]) and chart_refs == artifact_ids and all(
        set(artifact.get("finding_refs") or ()) <= finding_ids
        for artifact in turn["artifacts"]
    )
    run_state_matches = bool(
        turn["status"] == "finalized"
        and projection.publishable
        and len(turn["blocks"]) == final_block_delta_count
    )
    return {
        "immutable_dataset_versions": immutable_versions,
        "findings_bound_to_commitments": findings_bound,
        "completion_computed_from_ledger": completion_computed,
        "published_blocks_bound_to_findings": blocks_bound,
        "charts_bound_to_findings": charts_bound,
        "run_state_matches_publication": run_state_matches,
    }


def _incident_and_interrupted_sse(
    *,
    sessions_root: Path,
    base_session_id: str,
    base_run_id: str,
) -> tuple[dict[str, bool], list[str]]:
    store = V2FactStore(sessions_root, base_session_id)
    commitments, _, findings = store.read_run_facts(base_run_id)
    base_commitment = commitments[0]
    base_finding = findings[0]
    unsupported: Finding = replace(
        base_finding,
        finding_id="finding_incident_unsupported",
        method_capability="analysis.unsupported",
    )
    unsupported_projection = project_run([base_commitment], [], [unsupported])

    run_id = "run_incident_stop"
    turn_id = "turn_incident_stop"
    commitment = replace(
        base_commitment,
        commitment_id="commitment_incident_stop",
        question="停止后不得发布最终答案。",
    )
    store.append_commitments(run_id, turn_id, [commitment])
    advanced: list[str] = []

    def source():
        yield RuntimeEvent(
            "turn_started",
            {"session_id": base_session_id, "turn_id": turn_id, "run_id": run_id},
        )
        yield RuntimeEvent(
            "commitment_snapshot", {"commitments": [asdict(commitment)]}
        )
        yield RuntimeEvent("tool_started", {"name": "incident_probe"})
        advanced.append("publication_advanced")
        yield RuntimeEvent("final_block_delta", {"block": {"block_id": "late"}})
        yield RuntimeEvent("turn_completed", {"status": "completed"})

    registry = ActiveRunRegistry()
    active = registry.register(
        store=store,
        session_id=base_session_id,
        turn_id=turn_id,
        request_context={"analysis_kind": "multi_finding_synthesis"},
    )
    controlled = active.stream(source())
    prefix = [next(controlled) for _ in range(3)]
    stop_receipt = registry.request_stop(base_session_id, turn_id)
    suffix = list(controlled)
    interrupted_events = [item.event for item in (*prefix, *suffix)]
    interrupted_turn = store.read_turn_blocks(turn_id)
    blocked = False
    try:
        store.write_turn_blocks(
            turn_id,
            [
                AnswerBlockDraft(
                    block_id="block_late_publication",
                    block_type=AnswerBlockType.EXECUTIVE_ANSWER,
                    headline="不应发布",
                    narrative="停止后不得写入。",
                    support_refs=(base_finding.finding_id,),
                    claim_class=ClaimClass.DESCRIPTIVE,
                )
            ],
            status="finalized",
        )
    except TurnPublicationBlocked:
        blocked = True

    isolation = V2FactStore(sessions_root, "session_incident_isolation")
    isolation_preserved = not (
        isolation.read_commitments()
        or isolation.read_events()
        or isolation.read_findings()
    )
    observations = {
        "unsupported_finding_did_not_publish": not unsupported_projection.publishable,
        "stop_won_before_publication": bool(
            stop_receipt.status == "interrupted"
            and advanced == []
            and "final_block_delta" not in interrupted_events
            and "turn_completed" not in interrupted_events
        ),
        "interrupted_turn_persisted": bool(
            interrupted_turn["status"] == "interrupted"
            and interrupted_turn["blocks"] == []
        ),
        "final_after_interrupt_blocked": blocked,
        "session_isolation_preserved": isolation_preserved,
    }
    return observations, interrupted_events


def collect_unified_deterministic_evidence(
    state_root: Path | str,
    *,
    fixture_path: Path | str,
    source_digest: str,
) -> dict[str, Any]:
    """Run the real V2 owners and collect structured facts for three layers."""

    root = Path(state_root)
    sessions_root = root / "sessions"
    inbox_root = root / "workspace" / "inbox"
    inbox_root.mkdir(parents=True, exist_ok=True)
    fixture = Path(fixture_path)
    fixture_name = fixture.name
    shutil.copyfile(fixture, inbox_root / fixture_name)

    session_id = "session_unified_deterministic"
    turn_id = "turn_unified_deterministic"
    router = AnalysisRouter(sessions_root, inbox_root)
    completed = list(
        router.stream(
            analysis_kind=AnalysisKind.MULTI_FINDING_SYNTHESIS,
            session_id=session_id,
            turn_id=turn_id,
            payload={
                "filename": fixture_name,
                "time_field": "date",
                "metric": "sales",
                "frequency": "daily",
                "aggregation": "mean",
                "group": "channel",
                "analysis_unit": "unit_id",
                "question": "销售如何变化，不同渠道是否存在可靠差异？",
            },
        )
    )
    completed_events = [item.event for item in completed]
    run_id = str(completed[0].data.get("run_id") or "")
    final_block_delta_count = completed_events.count("final_block_delta")
    owner = _owner_observations(
        sessions_root=sessions_root,
        session_id=session_id,
        turn_id=turn_id,
        run_id=run_id,
        final_block_delta_count=final_block_delta_count,
    )
    incidents, interrupted_events = _incident_and_interrupted_sse(
        sessions_root=sessions_root,
        base_session_id=session_id,
        base_run_id=run_id,
    )
    required_order = _ordered(
        completed_events,
        (
            "turn_started",
            "commitment_snapshot",
            "tool_started",
            "tool_finished",
            "outcome_snapshot",
            "final_block_delta",
            "turn_completed",
        ),
    )
    return {
        "version": DETERMINISTIC_JOURNEY_VERSION,
        "source_digest": source_digest,
        "scenario_id": "unified_analysis_entry",
        "fixture_path": fixture.as_posix(),
        "provider_calls": 0,
        "owner_observations": owner,
        "incident_observations": incidents,
        "sse_observations": {
            "completed_events": completed_events,
            "interrupted_events": interrupted_events,
            "final_block_delta_count": final_block_delta_count,
            "required_order": required_order,
            "completed_terminal_exclusive": bool(
                completed_events[-1:] == ["turn_completed"]
                and "turn_interrupted" not in completed_events
            ),
            "interrupted_terminal_exclusive": bool(
                interrupted_events[-1:] == ["turn_interrupted"]
                and "turn_completed" not in interrupted_events
            ),
        },
    }


def validate_unified_deterministic_evidence(
    evidence: Any,
    *,
    scenario: ScenarioRequirement,
    expected_source_digest: str,
) -> DeterministicJourneyValidation:
    if not isinstance(evidence, dict):
        return DeterministicJourneyValidation(False, ("invalid_deterministic_journey",))
    reasons: list[str] = []
    if evidence.get("version") != DETERMINISTIC_JOURNEY_VERSION:
        reasons.append("invalid_deterministic_journey_version")
    if evidence.get("source_digest") != expected_source_digest:
        reasons.append("stale_deterministic_journey")
    if evidence.get("scenario_id") != scenario.scenario_id:
        reasons.append("invalid_deterministic_scenario")
    if scenario.scenario_id != "unified_analysis_entry":
        reasons.append("invalid_release_scenario")
    if (
        evidence.get("fixture_path") != UNIFIED_DATASET_FIXTURE
        or scenario.fixture.replace("\\", "/") != UNIFIED_DATASET_FIXTURE
    ):
        reasons.append("wrong_deterministic_dataset_fixture")
    if evidence.get("provider_calls") != 0:
        reasons.append("provider_call_in_deterministic_journey")

    owner = evidence.get("owner_observations")
    if not isinstance(owner, dict):
        reasons.append("invalid_owner_observations")
        owner = {}
    for name in OWNER_OBSERVATIONS:
        if owner.get(name) is not True:
            reasons.append(f"missing_owner_observation:{name}")

    incidents = evidence.get("incident_observations")
    if not isinstance(incidents, dict):
        reasons.append("invalid_incident_observations")
        incidents = {}
    for name in INCIDENT_OBSERVATIONS:
        if incidents.get(name) is not True:
            reasons.append(f"missing_incident_observation:{name}")

    sse = evidence.get("sse_observations")
    if not isinstance(sse, dict):
        reasons.append("invalid_sse_observations")
        sse = {}
    completed_events = sse.get("completed_events")
    interrupted_events = sse.get("interrupted_events")
    if not isinstance(completed_events, list):
        completed_events = []
        reasons.append("invalid_completed_sse_events")
    if not isinstance(interrupted_events, list):
        interrupted_events = []
        reasons.append("invalid_interrupted_sse_events")
    for event in scenario.required_semantic_events:
        required_stream = interrupted_events if event == "turn_interrupted" else completed_events
        if event not in required_stream:
            reasons.append(f"missing_required_sse_event:{event}")
    for event in INTERRUPTED_REQUIRED_EVENTS:
        if event not in interrupted_events:
            reasons.append(f"missing_interrupted_sse_event:{event}")
    if sse.get("required_order") is not True:
        reasons.append("invalid_sse_event_order")
    if sse.get("completed_terminal_exclusive") is not True:
        reasons.append("completed_sse_terminal_not_exclusive")
    if sse.get("interrupted_terminal_exclusive") is not True:
        reasons.append("interrupted_sse_terminal_not_exclusive")
    if not isinstance(sse.get("final_block_delta_count"), int) or sse.get(
        "final_block_delta_count"
    ) < 1:
        reasons.append("incremental_final_blocks_not_observed")

    unique_reasons = tuple(dict.fromkeys(reasons))
    if unique_reasons:
        return DeterministicJourneyValidation(False, unique_reasons)

    evidence_ref = _evidence_ref(evidence)
    identity = evidence_ref.rsplit(":", 1)[-1][:16]
    common = {
        "source_digest": expected_source_digest,
        "scenario_id": scenario.scenario_id,
        "status": LayerStatus.PASS,
        "evidence_refs": (evidence_ref,),
        "oracle_identity": "v2_unified_deterministic_oracle.v1",
    }
    receipts = (
        ReleaseReceipt(
            receipt_id=f"receipt_unified_owner_{identity}",
            layer=ValidationLayer.OWNER_CONTRACT,
            **common,
        ),
        ReleaseReceipt(
            receipt_id=f"receipt_unified_incident_{identity}",
            layer=ValidationLayer.INCIDENT_REPLAY,
            **common,
        ),
        ReleaseReceipt(
            receipt_id=f"receipt_unified_sse_{identity}",
            layer=ValidationLayer.SSE_TRANSPORT_CONTRACT,
            observed_semantic_events=tuple(scenario.required_semantic_events),
            **common,
        ),
    )
    return DeterministicJourneyValidation(True, (), receipts)
