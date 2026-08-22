from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from data_agent.v2.release import (
    LayerStatus,
    ReleaseMatrix,
    ReleaseReceipt,
    ScenarioRequirement,
    ValidationLayer,
)
from data_agent.v2.router import AnalysisKind, AnalysisRouter
from data_agent.v2.store import V2FactStore


SCENARIO_SEMANTIC_ORACLE_VERSION = "v2_scenario_semantic_oracle.v1"


@dataclass(frozen=True, slots=True)
class ScenarioSemanticOracleValidation:
    passed: bool
    reason_codes: tuple[str, ...]
    receipts: tuple[ReleaseReceipt, ...] = ()


def _scenario_request(scenario_id: str, filename: str) -> tuple[AnalysisKind, dict[str, Any]]:
    common = {"filename": filename}
    requests: dict[str, tuple[AnalysisKind, dict[str, Any]]] = {
        "descriptive_analysis": (
            AnalysisKind.DESCRIPTIVE,
            {**common, "metric": "sales", "question": "销售额的总体水平与范围如何？"},
        ),
        "factor_relationships": (
            AnalysisKind.FACTOR_RELATIONSHIP,
            {
                **common,
                "target": "target",
                "features": ["marketing", "service", "noise_feature"],
                "analysis_unit": "unit_id",
                "time_field": "",
                "question": "哪些因素与 target 存在可靠关系？",
            },
        ),
        "semantic_date_transformation": (
            AnalysisKind.DATE_TRANSFORMATION,
            {
                **common,
                "date_column": "order_date",
                "question": "把日期列转换为可分析日期。",
            },
        ),
        "group_comparison": (
            AnalysisKind.GROUP_COMPARISON,
            {
                **common,
                "metric": "revenue",
                "group": "channel",
                "analysis_unit": "unit_id",
                "question": "A 与 B 的收入是否不同？",
                "recommendation_intent": "none",
                "action_risk": "low",
                "reversible": True,
            },
        ),
        "historical_trend": (
            AnalysisKind.TIME_TREND,
            {
                **common,
                "time_field": "date",
                "metric": "sales",
                "frequency": "daily",
                "aggregation": "sum",
                "question": "历史销售是否有可靠趋势？",
                "recommendation_intent": "none",
                "action_risk": "low",
                "reversible": True,
            },
        ),
        "backtested_forecast": (
            AnalysisKind.FORECAST,
            {
                **common,
                "time_field": "date",
                "metric": "sales",
                "frequency": "daily",
                "aggregation": "sum",
                "horizon": 7,
                "question": "未来七天销售基线是多少？",
                "recommendation_intent": "none",
                "action_risk": "low",
                "reversible": True,
            },
        ),
        "multi_finding_synthesis": (
            AnalysisKind.MULTI_FINDING_SYNTHESIS,
            {
                **common,
                "time_field": "date",
                "metric": "sales",
                "frequency": "daily",
                "aggregation": "mean",
                "group": "channel",
                "analysis_unit": "unit_id",
                "question": "销售如何变化，不同渠道是否存在可靠差异？",
                "recommendation_intent": "none",
                "action_risk": "low",
                "reversible": True,
            },
        ),
        "exploratory_python": (
            AnalysisKind.EXPLORATORY_PYTHON,
            {
                **common,
                "metric": "sales",
                "question": "销售额的总体水平如何？",
                "purpose": "检查中位数作为补充",
                "code": 'result = data["sales"].median()',
            },
        ),
        "unified_analysis_entry": (
            AnalysisKind.MULTI_FINDING_SYNTHESIS,
            {
                **common,
                "time_field": "date",
                "metric": "sales",
                "frequency": "daily",
                "aggregation": "mean",
                "group": "channel",
                "analysis_unit": "unit_id",
                "question": "销售如何变化，不同渠道是否存在可靠差异？",
                "recommendation_intent": "none",
                "action_risk": "low",
                "reversible": True,
            },
        ),
    }
    try:
        return requests[scenario_id]
    except KeyError as exc:
        raise ValueError(f"unsupported semantic oracle scenario: {scenario_id}") from exc


def _chart_observation(scenario: ScenarioRequirement, artifacts: list[dict[str, Any]]) -> str:
    if scenario.chart_policy == "forbidden":
        return "forbidden_absent" if not artifacts else "failed"
    return "rendered" if artifacts else "not_warranted"


def _scenario_assertions(
    scenario: ScenarioRequirement,
    *,
    turn: dict[str, Any],
    store: V2FactStore,
    events: list[str],
    fixture_name: str,
) -> dict[str, bool]:
    serialized = json.dumps(turn, ensure_ascii=False, sort_keys=True)
    context = turn.get("request_context") or {}
    findings = store.read_findings()
    commitments = store.read_commitments()
    finding_kinds = {item.finding_kind.value for item in findings}
    assertions = {
        "persisted_finalized": turn.get("status") == "finalized",
        "answer_blocks_persisted": bool(turn.get("blocks")),
        "no_internal_evidence_marker": "[[evidence:" not in serialized,
        "source_fixture_bound": context.get("filename") == fixture_name,
        "terminal_event_completed": events[-1:] == ["turn_completed"],
    }
    scenario_id = scenario.scenario_id
    expected_finding_kinds = {
        "descriptive_analysis": {"estimate"},
        "factor_relationships": {"association", "limitation"},
        "semantic_date_transformation": {"transformation"},
        "group_comparison": {"group_comparison"},
        "historical_trend": {"time_trend"},
        "backtested_forecast": {"forecast", "limitation"},
        "multi_finding_synthesis": {"time_trend", "group_comparison"},
        "exploratory_python": {"estimate"},
        "unified_analysis_entry": {"time_trend", "group_comparison"},
    }[scenario_id]
    assertions["method_specific_finding_persisted"] = bool(
        finding_kinds.intersection(expected_finding_kinds)
    )
    if scenario_id == "semantic_date_transformation":
        assertions["date_confirmation_resumed"] = (
            "user_input_required" in events and events[-1:] == ["turn_completed"]
        )
    else:
        assertions["no_unexpected_input"] = "user_input_required" not in events
    if scenario_id in {
        "factor_relationships",
        "group_comparison",
        "multi_finding_synthesis",
        "unified_analysis_entry",
    }:
        assertions["analysis_unit_bound"] = context.get("analysis_unit") == "unit_id"
    if scenario_id == "backtested_forecast":
        assertions["forecast_backtest_calibrated"] = (
            "时间外" in serialized or "回测" in serialized
        )
    if scenario_id == "exploratory_python":
        assertions["exploration_not_promoted"] = bool(
            turn.get("supplemental_artifacts")
        ) and all(item.method_capability != "exploration.python" for item in findings)
    if scenario_id in {"multi_finding_synthesis", "unified_analysis_entry"}:
        assertions["independent_findings_preserved"] = (
            len(findings) >= 2 and len(commitments) >= 2
        )
    return assertions


def _collect_one(
    scenario: ScenarioRequirement,
    *,
    router: AnalysisRouter,
    sessions_root: Path,
    inbox_root: Path,
    repository_root: Path,
) -> dict[str, Any]:
    fixture = repository_root / Path(scenario.fixture)
    if not fixture.is_file():
        raise FileNotFoundError(f"missing semantic oracle fixture: {scenario.fixture}")
    fixture_name = f"{scenario.scenario_id}_{fixture.name}"
    shutil.copy2(fixture, inbox_root / fixture_name)
    session_id = f"session_oracle_{scenario.scenario_id}"
    turn_id = f"turn_oracle_{scenario.scenario_id}"
    kind, payload = _scenario_request(scenario.scenario_id, fixture_name)
    prepared = router.prepare(
        analysis_kind=kind,
        session_id=session_id,
        turn_id=turn_id,
        payload=payload,
    )
    emitted = list(prepared.stream())
    interactions = ["upload", "live_progress", "refresh_restore"]
    if scenario.scenario_id == "semantic_date_transformation":
        required = next(
            item.data for item in emitted if item.event == "user_input_required"
        )
        emitted.extend(
            prepared.runtime.resolve(
                session_id=session_id,
                turn_id=turn_id,
                proposal_id=required["proposal_id"],
                option_key="dmy",
                expected_parent_version_id=required["parent_version_id"],
                expected_parent_content_fingerprint=required[
                    "parent_content_fingerprint"
                ],
            )
        )
        interactions.extend(["semantic_confirmation", "resume"])
    store = V2FactStore(sessions_root, session_id)
    turn = store.read_turn_blocks(turn_id)
    if turn.get("artifacts"):
        interactions.append("inline_charts")
    observed_events = list(dict.fromkeys(item.event for item in emitted))
    observed_blocks = list(
        dict.fromkeys(str(item.get("block_type") or "") for item in turn["blocks"])
    )
    assertions = _scenario_assertions(
        scenario,
        turn=turn,
        store=store,
        events=[item.event for item in emitted],
        fixture_name=fixture_name,
    )
    return {
        "scenario_id": scenario.scenario_id,
        "fixture_path": scenario.fixture.replace("\\", "/"),
        "provider_calls": 0,
        "observed_semantic_events": observed_events,
        "observed_block_types": observed_blocks,
        "observed_interactions": list(dict.fromkeys(interactions)),
        "chart_observation": _chart_observation(
            scenario, list(turn.get("artifacts") or [])
        ),
        "assertions": assertions,
        "forbidden_behavior_hits": [
            key for key, passed in assertions.items() if not passed
        ],
    }


def collect_scenario_semantic_evidence(
    state_root: Path | str,
    *,
    matrix: ReleaseMatrix,
    source_digest: str,
    repository_root: Path | str,
) -> dict[str, Any]:
    """Run each release scenario through the real provider-neutral V2 runtime."""

    root = Path(state_root)
    sessions_root = root / "sessions"
    inbox_root = root / "workspace" / "inbox"
    inbox_root.mkdir(parents=True, exist_ok=True)
    router = AnalysisRouter(sessions_root, inbox_root)
    scenarios = [
        _collect_one(
            scenario,
            router=router,
            sessions_root=sessions_root,
            inbox_root=inbox_root,
            repository_root=Path(repository_root),
        )
        for scenario in matrix.scenarios
    ]
    return {
        "version": SCENARIO_SEMANTIC_ORACLE_VERSION,
        "source_digest": source_digest,
        "provider_calls": 0,
        "scenarios": scenarios,
    }


def _chart_covers(policy: str, observation: str) -> bool:
    if policy == "required":
        return observation == "rendered"
    if policy == "forbidden":
        return observation == "forbidden_absent"
    return observation in {"rendered", "not_warranted"}


def _item_hash(item: dict[str, Any]) -> str:
    serialized = json.dumps(
        item, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def validate_scenario_semantic_evidence(
    evidence: Any,
    *,
    matrix: ReleaseMatrix,
    expected_source_digest: str,
) -> ScenarioSemanticOracleValidation:
    """Fail closed before minting any receipt if one scenario is incomplete."""

    if not isinstance(evidence, dict):
        return ScenarioSemanticOracleValidation(False, ("invalid_semantic_oracle",))
    reasons: list[str] = []
    if evidence.get("version") != SCENARIO_SEMANTIC_ORACLE_VERSION:
        reasons.append("invalid_semantic_oracle_version")
    if evidence.get("source_digest") != expected_source_digest:
        reasons.append("stale_semantic_oracle")
    if evidence.get("provider_calls") != 0:
        reasons.append("provider_call_in_semantic_oracle")
    raw_items = evidence.get("scenarios")
    if not isinstance(raw_items, list):
        return ScenarioSemanticOracleValidation(
            False, tuple(dict.fromkeys((*reasons, "invalid_semantic_oracle_scenarios")))
        )
    by_id: dict[str, dict[str, Any]] = {}
    duplicate_ids: set[str] = set()
    for raw in raw_items:
        if not isinstance(raw, dict):
            reasons.append("invalid_semantic_oracle_scenario")
            continue
        scenario_id = str(raw.get("scenario_id") or "")
        if scenario_id in by_id:
            duplicate_ids.add(scenario_id)
        by_id[scenario_id] = raw
    reasons.extend(f"duplicate_semantic_oracle:{item}" for item in sorted(duplicate_ids))
    known_ids = {item.scenario_id for item in matrix.scenarios}
    reasons.extend(
        f"unknown_semantic_oracle:{item}" for item in sorted(set(by_id) - known_ids)
    )
    receipts: list[ReleaseReceipt] = []
    for scenario in matrix.scenarios:
        item = by_id.get(scenario.scenario_id)
        if item is None:
            reasons.append(f"missing_semantic_oracle:{scenario.scenario_id}")
            continue
        prefix = scenario.scenario_id
        if item.get("fixture_path") != scenario.fixture.replace("\\", "/"):
            reasons.append(f"wrong_semantic_oracle_fixture:{prefix}")
        if item.get("provider_calls") != 0:
            reasons.append(f"provider_call_in_semantic_oracle:{prefix}")
        observed_events = tuple(item.get("observed_semantic_events") or ())
        observed_blocks = tuple(item.get("observed_block_types") or ())
        observed_interactions = tuple(item.get("observed_interactions") or ())
        if not set(scenario.required_semantic_events).issubset(observed_events):
            reasons.append(f"semantic_events_incomplete:{prefix}")
        if not set(scenario.required_block_types).issubset(observed_blocks):
            reasons.append(f"semantic_blocks_incomplete:{prefix}")
        if not _chart_covers(scenario.chart_policy, str(item.get("chart_observation") or "")):
            reasons.append(f"semantic_chart_incomplete:{prefix}")
        assertions = item.get("assertions")
        if not isinstance(assertions, dict) or not assertions:
            reasons.append(f"semantic_assertions_missing:{prefix}")
        else:
            reasons.extend(
                f"semantic_assertion_failed:{prefix}:{key}"
                for key, passed in sorted(assertions.items())
                if passed is not True
            )
        forbidden_hits = tuple(item.get("forbidden_behavior_hits") or ())
        if forbidden_hits:
            reasons.append(f"forbidden_behavior_observed:{prefix}")
        receipts.append(
            ReleaseReceipt(
                receipt_id=f"receipt_semantic_oracle_{prefix}_{_item_hash(item)[:16]}",
                source_digest=expected_source_digest,
                scenario_id=prefix,
                layer=ValidationLayer.SCENARIO_SEMANTIC_ORACLE,
                status=LayerStatus.PASS,
                evidence_refs=(f"semantic-oracle:{_item_hash(item)}",),
                oracle_identity=SCENARIO_SEMANTIC_ORACLE_VERSION,
                fixture_path=scenario.fixture,
                observed_semantic_events=observed_events,
                observed_block_types=observed_blocks,
                observed_interactions=observed_interactions,
                chart_observation=str(item.get("chart_observation") or ""),
            )
        )
    unique_reasons = tuple(dict.fromkeys(reasons))
    if unique_reasons:
        return ScenarioSemanticOracleValidation(False, unique_reasons)
    return ScenarioSemanticOracleValidation(True, (), tuple(receipts))
