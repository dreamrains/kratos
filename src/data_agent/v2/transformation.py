from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, replace
from enum import StrEnum
from pathlib import Path
from typing import Any

import pandas as pd

from data_agent.v2.identity import require_storage_id


class DateTransformDisposition(StrEnum):
    AUTO_APPLY = "auto_apply"
    NEEDS_INPUT = "needs_input"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class DateSensitivity:
    source_non_null: int = 0
    parsed_non_null: int = 0
    new_missing: int = 0
    parse_rate: float = 0.0
    min_time: str = ""
    max_time: str = ""
    divergent_values: int = 0


@dataclass(frozen=True, slots=True)
class TransformationOption:
    option_key: str
    label: str
    date_format: str
    candidate_version_id: str = ""
    sensitivity: DateSensitivity = field(default_factory=DateSensitivity)

    @classmethod
    def for_format(
        cls,
        values: pd.Series,
        *,
        option_key: str,
        label: str,
        date_format: str,
    ) -> "TransformationOption":
        parsed = pd.to_datetime(values, errors="coerce", format=date_format)
        source_non_null = int(values.notna().sum())
        parsed_non_null = int(parsed.notna().sum())
        valid = parsed.dropna()
        sensitivity = DateSensitivity(
            source_non_null=source_non_null,
            parsed_non_null=parsed_non_null,
            new_missing=max(0, source_non_null - parsed_non_null),
            parse_rate=(parsed_non_null / source_non_null if source_non_null else 0.0),
            min_time=(valid.min().isoformat() if not valid.empty else ""),
            max_time=(valid.max().isoformat() if not valid.empty else ""),
        )
        return cls(
            option_key=str(option_key),
            label=str(label),
            date_format=str(date_format),
            sensitivity=sensitivity,
        )


@dataclass(frozen=True, slots=True)
class DateTransformPlan:
    disposition: DateTransformDisposition
    column: str
    reason_code: str
    options: tuple[TransformationOption, ...] = ()


def inspect_date_conversion(frame: pd.DataFrame, column: str) -> DateTransformPlan:
    field_name = str(column or "").strip()
    if not field_name or field_name not in frame.columns:
        raise KeyError(f"date column not found: {field_name}")
    values = frame[field_name]
    source_non_null = int(values.notna().sum())
    if source_non_null == 0:
        return DateTransformPlan(
            DateTransformDisposition.UNAVAILABLE,
            field_name,
            "date_column_has_no_values",
        )

    for option_key, label, date_format in (
        ("iso", "ISO 年-月-日", "%Y-%m-%d"),
        ("iso_slash", "ISO 年/月/日", "%Y/%m/%d"),
    ):
        iso = TransformationOption.for_format(
            values,
            option_key=option_key,
            label=label,
            date_format=date_format,
        )
        if iso.sensitivity.new_missing == 0:
            return DateTransformPlan(
                DateTransformDisposition.AUTO_APPLY,
                field_name,
                "lossless_unambiguous_date",
                (iso,),
            )

    dmy = TransformationOption.for_format(
        values,
        option_key="dmy",
        label="日/月/年",
        date_format="%d/%m/%Y",
    )
    mdy = TransformationOption.for_format(
        values,
        option_key="mdy",
        label="月/日/年",
        date_format="%m/%d/%Y",
    )
    complete = [item for item in (dmy, mdy) if item.sensitivity.new_missing == 0]
    if len(complete) == 1:
        return DateTransformPlan(
            DateTransformDisposition.AUTO_APPLY,
            field_name,
            "lossless_unambiguous_date",
            (complete[0],),
        )
    if len(complete) == 2:
        parsed_dmy = pd.to_datetime(values, errors="coerce", format=dmy.date_format)
        parsed_mdy = pd.to_datetime(values, errors="coerce", format=mdy.date_format)
        divergent = int(((parsed_dmy != parsed_mdy) & values.notna()).sum())
        if divergent == 0:
            return DateTransformPlan(
                DateTransformDisposition.AUTO_APPLY,
                field_name,
                "equivalent_date_interpretations",
                (dmy,),
            )
        options = tuple(
            replace(
                item,
                sensitivity=replace(item.sensitivity, divergent_values=divergent),
            )
            for item in (dmy, mdy)
        )
        return DateTransformPlan(
            DateTransformDisposition.NEEDS_INPUT,
            field_name,
            "ambiguous_date_order",
            options,
        )
    return DateTransformPlan(
        DateTransformDisposition.UNAVAILABLE,
        field_name,
        "date_conversion_would_add_missing",
    )


def apply_date_option(
    frame: pd.DataFrame,
    column: str,
    option: TransformationOption,
) -> pd.DataFrame:
    if column not in frame.columns:
        raise KeyError(f"date column not found: {column}")
    converted = frame.copy(deep=True)
    parsed = pd.to_datetime(converted[column], errors="coerce", format=option.date_format)
    if int(converted[column].notna().sum()) != int(parsed.notna().sum()):
        raise ValueError("date option would add missing values")
    converted[column] = parsed
    return converted


@dataclass(frozen=True, slots=True)
class TransformationProposal:
    proposal_id: str
    turn_id: str
    run_id: str
    commitment_id: str
    parent_version_id: str
    parent_content_fingerprint: str
    column: str
    target_type: str
    reason_code: str
    options: tuple[TransformationOption, ...]


@dataclass(frozen=True, slots=True)
class TransformationDecision:
    decision_id: str
    proposal_id: str
    option_key: str
    expected_parent_version_id: str
    expected_parent_content_fingerprint: str


@dataclass(frozen=True, slots=True)
class TransformationState:
    proposal: TransformationProposal
    status: str
    decision: TransformationDecision | None = None


class StaleTransformationProposal(RuntimeError):
    pass


class TransformationConflict(RuntimeError):
    pass


def _json_line(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


class TransformationStore:
    """Append-only transformation proposals and semantic decisions."""

    def __init__(self, sessions_root: Path | str, session_id: str) -> None:
        safe_session_id = require_storage_id(session_id, "session_id")
        self.root = Path(sessions_root) / safe_session_id / "v2" / "transformations"
        self.root.mkdir(parents=True, exist_ok=True)
        self._proposals = self.root / "proposals.jsonl"
        self._decisions = self.root / "decisions.jsonl"

    def _append(self, path: Path, id_field: str, value: dict[str, Any]) -> bool:
        identity = value[id_field]
        canonical = _json_line(value)
        for existing in _read_jsonl(path):
            if existing[id_field] != identity:
                continue
            if _json_line(existing) == canonical:
                return False
            raise TransformationConflict(f"immutable transformation conflict for {identity}")
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(canonical + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return True

    def append_proposal(self, proposal: TransformationProposal) -> bool:
        require_storage_id(proposal.proposal_id, "proposal_id")
        if not proposal.options:
            raise ValueError("transformation proposal options are required")
        return self._append(self._proposals, "proposal_id", asdict(proposal))

    @staticmethod
    def _option(value: dict[str, Any]) -> TransformationOption:
        sensitivity = value.get("sensitivity") or {}
        return TransformationOption(
            option_key=value["option_key"],
            label=value["label"],
            date_format=value["date_format"],
            candidate_version_id=value.get("candidate_version_id", ""),
            sensitivity=DateSensitivity(**sensitivity),
        )

    @classmethod
    def _proposal(cls, value: dict[str, Any]) -> TransformationProposal:
        return TransformationProposal(
            proposal_id=value["proposal_id"],
            turn_id=value["turn_id"],
            run_id=value["run_id"],
            commitment_id=value["commitment_id"],
            parent_version_id=value["parent_version_id"],
            parent_content_fingerprint=value["parent_content_fingerprint"],
            column=value["column"],
            target_type=value["target_type"],
            reason_code=value["reason_code"],
            options=tuple(cls._option(item) for item in value.get("options") or ()),
        )

    @staticmethod
    def _decision(value: dict[str, Any]) -> TransformationDecision:
        return TransformationDecision(**value)

    def get_proposal(self, proposal_id: str) -> TransformationProposal:
        for value in _read_jsonl(self._proposals):
            if value["proposal_id"] == proposal_id:
                return self._proposal(value)
        raise KeyError(f"unknown transformation proposal {proposal_id}")

    def find_by_turn(self, turn_id: str) -> TransformationState:
        matches = [
            self._proposal(value)
            for value in _read_jsonl(self._proposals)
            if value["turn_id"] == turn_id
        ]
        if len(matches) != 1:
            raise KeyError(f"transformation proposal not found for turn {turn_id}")
        return self.project(matches[0].proposal_id)

    def append_decision(
        self,
        decision: TransformationDecision,
        *,
        active_parent_version_id: str,
        active_parent_content_fingerprint: str,
    ) -> bool:
        proposal = self.get_proposal(decision.proposal_id)
        if decision.option_key not in {item.option_key for item in proposal.options}:
            raise ValueError("unknown transformation option")
        expected = (
            proposal.parent_version_id,
            proposal.parent_content_fingerprint,
        )
        supplied = (
            decision.expected_parent_version_id,
            decision.expected_parent_content_fingerprint,
        )
        active = (active_parent_version_id, active_parent_content_fingerprint)
        if supplied != expected or active != expected:
            raise StaleTransformationProposal(
                "transformation proposal parent version or fingerprint is stale"
            )
        prior = [
            self._decision(value)
            for value in _read_jsonl(self._decisions)
            if value["proposal_id"] == decision.proposal_id
        ]
        if prior:
            existing = prior[0]
            if (
                existing.option_key == decision.option_key
                and existing.expected_parent_version_id
                == decision.expected_parent_version_id
                and existing.expected_parent_content_fingerprint
                == decision.expected_parent_content_fingerprint
            ):
                return False
            raise TransformationConflict(
                "transformation proposal already has a different semantic decision"
            )
        return self._append(self._decisions, "decision_id", asdict(decision))

    def project(self, proposal_id: str) -> TransformationState:
        proposal = self.get_proposal(proposal_id)
        decisions = [
            self._decision(value)
            for value in _read_jsonl(self._decisions)
            if value["proposal_id"] == proposal_id
        ]
        if len(decisions) > 1:
            raise TransformationConflict("proposal has multiple semantic decisions")
        return TransformationState(
            proposal=proposal,
            status="resolved" if decisions else "pending",
            decision=(decisions[0] if decisions else None),
        )
