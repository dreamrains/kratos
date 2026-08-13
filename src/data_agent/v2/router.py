from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Iterator

from data_agent.v2.recommendation import ActionRisk, RecommendationIntent
from data_agent.v2.slice1 import RuntimeEvent, Slice1DescriptiveRuntime
from data_agent.v2.slice2 import Slice2FactorRuntime
from data_agent.v2.slice3 import Slice3TransformationRuntime
from data_agent.v2.slice4a import Slice4AGroupComparisonRuntime
from data_agent.v2.slice4b import Slice4BTimeSeriesRuntime
from data_agent.v2.slice4c import Slice4CForecastRuntime
from data_agent.v2.slice4d import Slice4DMultiFindingRuntime
from data_agent.v2.slice4e import Slice4EExploratoryRuntime
from data_agent.v2.time_series import TimeAggregation, TimeFrequency


class AnalysisKind(StrEnum):
    DESCRIPTIVE = "descriptive"
    FACTOR_RELATIONSHIP = "factor_relationship"
    DATE_TRANSFORMATION = "date_transformation"
    GROUP_COMPARISON = "group_comparison"
    TIME_TREND = "time_trend"
    FORECAST = "forecast"
    MULTI_FINDING_SYNTHESIS = "multi_finding_synthesis"
    EXPLORATORY_PYTHON = "exploratory_python"


def _text(payload: dict[str, Any], key: str, *, required: bool = True) -> str:
    value = str(payload.get(key) or "").strip()
    if required and not value:
        raise ValueError(f"{key} is required")
    return value


def _enum(payload: dict[str, Any], key: str, enum_type, default: str):
    raw = str(payload.get(key) or default)
    try:
        return enum_type(raw)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in enum_type)
        raise ValueError(f"{key} must be one of: {allowed}") from exc


def _boolean(payload: dict[str, Any], key: str, default: bool = True) -> bool:
    value = payload.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a boolean")
    return value


def _recommendation(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "recommendation_intent": _enum(
            payload, "recommendation_intent", RecommendationIntent, "none"
        ),
        "action_risk": _enum(payload, "action_risk", ActionRisk, "low"),
        "reversible": _boolean(payload, "reversible"),
    }


@dataclass(slots=True)
class PreparedAnalysis:
    runtime: Any
    entrypoint: str
    kwargs: dict[str, Any]

    def stream(self) -> Iterator[RuntimeEvent]:
        yield from getattr(self.runtime, self.entrypoint)(**self.kwargs)


class AnalysisRouter:
    """Deterministic adapter from an explicit analysis kind to one V2 runtime."""

    def __init__(self, sessions_root: Path | str, inbox_root: Path | str) -> None:
        self.sessions_root = Path(sessions_root)
        self.inbox_root = Path(inbox_root)

    @staticmethod
    def parse_kind(value: str | AnalysisKind) -> AnalysisKind | None:
        if isinstance(value, AnalysisKind):
            return value
        normalized = str(value or "").strip()
        if not normalized:
            return None
        try:
            return AnalysisKind(normalized)
        except ValueError as exc:
            raise ValueError(f"unknown analysis_kind: {normalized}") from exc

    def prepare(
        self,
        *,
        analysis_kind: AnalysisKind,
        session_id: str,
        turn_id: str,
        payload: dict[str, Any],
    ) -> PreparedAnalysis:
        if not isinstance(payload, dict):
            raise ValueError("request body must be a JSON object")
        common = {
            "session_id": _text({"session_id": session_id}, "session_id"),
            "turn_id": _text({"turn_id": turn_id}, "turn_id"),
            "filename": _text(payload, "filename"),
            "question": _text(payload, "question"),
        }
        runtime_args = (self.sessions_root, self.inbox_root)

        if analysis_kind is AnalysisKind.DESCRIPTIVE:
            return PreparedAnalysis(
                Slice1DescriptiveRuntime(*runtime_args), "stream",
                {**common, "metric": _text(payload, "metric")},
            )
        if analysis_kind is AnalysisKind.FACTOR_RELATIONSHIP:
            raw_features = payload.get("features")
            if not isinstance(raw_features, list):
                raise ValueError("features must be a JSON array")
            features = tuple(str(item or "").strip() for item in raw_features if str(item or "").strip())
            if not features:
                raise ValueError("features must contain at least one column")
            return PreparedAnalysis(
                Slice2FactorRuntime(*runtime_args), "stream",
                {
                    **common,
                    "target": _text(payload, "target"),
                    "features": features,
                    "analysis_unit": _text(payload, "analysis_unit"),
                    "time_field": _text(payload, "time_field", required=False),
                },
            )
        if analysis_kind is AnalysisKind.DATE_TRANSFORMATION:
            return PreparedAnalysis(
                Slice3TransformationRuntime(*runtime_args), "start",
                {**common, "date_column": _text(payload, "date_column")},
            )
        if analysis_kind is AnalysisKind.GROUP_COMPARISON:
            return PreparedAnalysis(
                Slice4AGroupComparisonRuntime(*runtime_args), "stream",
                {
                    **common,
                    "metric": _text(payload, "metric"),
                    "group": _text(payload, "group"),
                    "analysis_unit": _text(payload, "analysis_unit"),
                    **_recommendation(payload),
                },
            )
        if analysis_kind is AnalysisKind.TIME_TREND:
            return PreparedAnalysis(
                Slice4BTimeSeriesRuntime(*runtime_args), "stream",
                {
                    **common,
                    "time_field": _text(payload, "time_field"),
                    "metric": _text(payload, "metric"),
                    "frequency": _enum(payload, "frequency", TimeFrequency, "daily"),
                    "aggregation": _enum(payload, "aggregation", TimeAggregation, "sum"),
                    **_recommendation(payload),
                },
            )
        if analysis_kind is AnalysisKind.FORECAST:
            horizon = payload.get("horizon", 7)
            if isinstance(horizon, bool) or not isinstance(horizon, int):
                raise ValueError("horizon must be an integer")
            if not 1 <= horizon <= 30:
                raise ValueError("horizon must be between 1 and 30")
            return PreparedAnalysis(
                Slice4CForecastRuntime(*runtime_args), "stream",
                {
                    **common,
                    "time_field": _text(payload, "time_field"),
                    "metric": _text(payload, "metric"),
                    "frequency": _enum(payload, "frequency", TimeFrequency, "daily"),
                    "aggregation": _enum(payload, "aggregation", TimeAggregation, "sum"),
                    "horizon": horizon,
                    **_recommendation(payload),
                },
            )
        if analysis_kind is AnalysisKind.MULTI_FINDING_SYNTHESIS:
            return PreparedAnalysis(
                Slice4DMultiFindingRuntime(*runtime_args), "stream",
                {
                    **common,
                    "time_field": _text(payload, "time_field"),
                    "metric": _text(payload, "metric"),
                    "frequency": _enum(payload, "frequency", TimeFrequency, "daily"),
                    "aggregation": _enum(payload, "aggregation", TimeAggregation, "mean"),
                    "group": _text(payload, "group"),
                    "analysis_unit": _text(payload, "analysis_unit"),
                    **_recommendation(payload),
                },
            )
        if analysis_kind is AnalysisKind.EXPLORATORY_PYTHON:
            return PreparedAnalysis(
                Slice4EExploratoryRuntime(*runtime_args), "stream",
                {
                    **common,
                    "metric": _text(payload, "metric"),
                    "purpose": _text(payload, "purpose"),
                    "code": _text(payload, "code"),
                },
            )
        raise ValueError(f"unsupported analysis_kind: {analysis_kind.value}")

    def stream(
        self,
        *,
        analysis_kind: AnalysisKind,
        session_id: str,
        turn_id: str,
        payload: dict[str, Any],
    ) -> Iterator[RuntimeEvent]:
        yield from self.prepare(
            analysis_kind=analysis_kind,
            session_id=session_id,
            turn_id=turn_id,
            payload=payload,
        ).stream()
