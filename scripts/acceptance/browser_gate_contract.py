"""Fail-closed receipt contract for the actual in-app-browser release gate."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


BROWSER_GATE_CONTRACT_VERSION = "analysis_browser_gate.v1"
BROWSER_USER_JOURNEY_CONTRACT_VERSION = "analysis_browser_user_journey.v2"
FIXTURE_ID = "web_sse_fixture_v1"
REQUIRED_OBSERVATIONS = frozenset(
    {
        "upload_starts_analysis",
        "progress_before_answer",
        "first_chunk_before_second",
        "complete_answer_before_turn_end",
        "markdown_table_and_limitation_rendered",
        "persisted_after_refresh",
        "retained_after_session_switch",
        "suspend_resume_nonblank",
        "interruption_nonblank",
        "error_nonblank",
    }
)
_PRE_TURN_END_OBSERVATIONS = (
    "progress_before_answer",
    "first_chunk_before_second",
    "complete_answer_before_turn_end",
)
_NORMAL_STREAM_OBSERVATIONS = (
    "upload_starts_analysis",
    *_PRE_TURN_END_OBSERVATIONS,
    "markdown_table_and_limitation_rendered",
    "persisted_after_refresh",
    "retained_after_session_switch",
)
_TOP_LEVEL_FIELDS = frozenset(
    {
        "contract_version",
        "status",
        "observer",
        "fixture_id",
        "source_digest",
        "source_commit",
        "url",
        "observations",
    }
)
_OBSERVATION_FIELDS = frozenset(
    {
        "name",
        "observed_text",
        "browser_ms",
        "server_event_ms",
        "turn_end_browser_ms",
    }
)
_V2_TOP_LEVEL_FIELDS = frozenset({
    "contract_version",
    "status",
    "observer",
    "entrypoint",
    "scenario_id",
    "source_digest",
    "source_commit",
    "fixture_digest",
    "prompt_digest",
    "oracle_digest",
    "url",
    "session_id",
    "tasks",
    "computations",
    "evidence",
    "oracle_assertions",
    "answer",
    "refresh",
    "session_isolation",
    "elapsed_ms",
    "first_failure_stage",
})
_V2_TASK_FIELDS = frozenset({
    "total",
    "completed",
    "terminal",
    "max_in_progress",
    "monotonic",
})
_V2_COMPUTATION_FIELDS = frozenset({"bound", "orphan"})
_V2_EVIDENCE_FIELDS = frozenset({"bound", "orphan", "legacy_unbound"})
_V2_ORACLE_FIELDS = frozenset({
    "name",
    "expected",
    "observed",
    "tolerance",
    "passed",
})
_V2_ANSWER_FIELDS = frozenset({
    "useful",
    "complete_before_turn_end",
    "forbidden_markers",
    "empty_structures",
    "progress_visible",
    "content_digest",
})
_V2_REFRESH_FIELDS = frozenset({
    "session_id",
    "task_total",
    "task_completed",
    "evidence_bound",
    "answer_restored",
    "answer_digest",
})
_V2_ISOLATION_FIELDS = frozenset({"passed"})
_FIXED_OBSERVED_TEXT = {
    "upload_starts_analysis": frozenset({"browser_fixture.csv"}),
    "progress_before_answer": frozenset(
        {
            "正在分析字段质量",
            "分析方案已准备",
            "正在执行分析步骤",
            "正在运行分析工具",
            "分析步骤已完成",
            "正在按约定尝试恢复",
            "正在整理可支持的结论",
            "正在校验最终结论",
            "正在评估变量关系",
            "正在检查颗粒度与缺失",
            "正在执行单变量分析",
            "正在尝试多变量方法",
            "正在整理局限说明",
        }
    ),
    "first_chunk_before_second": frozenset({"第一段"}),
    "complete_answer_before_turn_end": frozenset({"第一段第二段"}),
    "markdown_table_and_limitation_rendered": frozenset({"局限"}),
    "persisted_after_refresh": frozenset({"第一段第二段"}),
    "retained_after_session_switch": frozenset({"第一段第二段"}),
    "suspend_resume_nonblank": frozenset({"恢复后内容"}),
    "interruption_nonblank": frozenset({"已中断验收"}),
    "error_nonblank": frozenset({"synthetic_acceptance_error"}),
}
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{1,127}$")


@dataclass(frozen=True)
class ReceiptValidation:
    status: str
    reason_codes: tuple[str, ...]


def _is_nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _is_bounded_oracle_scalar(value: Any) -> bool:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return True
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _v2_privacy_reason_codes(receipt: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if set(receipt) - _V2_TOP_LEVEL_FIELDS:
        reasons.append("unsafe_user_journey_field")
    nested_fields = (
        (receipt.get("tasks"), _V2_TASK_FIELDS),
        (receipt.get("computations"), _V2_COMPUTATION_FIELDS),
        (receipt.get("evidence"), _V2_EVIDENCE_FIELDS),
        (receipt.get("answer"), _V2_ANSWER_FIELDS),
        (receipt.get("refresh"), _V2_REFRESH_FIELDS),
        (receipt.get("session_isolation"), _V2_ISOLATION_FIELDS),
    )
    if any(isinstance(value, dict) and set(value) - allowed for value, allowed in nested_fields):
        reasons.append("unsafe_user_journey_field")
    for assertion in receipt.get("oracle_assertions") or []:
        if not isinstance(assertion, dict):
            continue
        if set(assertion) - _V2_ORACLE_FIELDS or any(
            key in assertion and not _is_bounded_oracle_scalar(assertion[key])
            for key in ("expected", "observed", "tolerance")
        ):
            reasons.append("unsafe_user_journey_oracle_field")
    return reasons


def _privacy_reason_codes(receipt: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if set(receipt) - _TOP_LEVEL_FIELDS:
        reasons.append("unsafe_browser_receipt_field")
    for item in receipt.get("observations") or []:
        if not isinstance(item, dict):
            continue
        if set(item) - _OBSERVATION_FIELDS:
            reasons.append("unsafe_browser_receipt_field")
        name = item.get("name")
        allowed = _FIXED_OBSERVED_TEXT.get(name)
        if allowed is None:
            reasons.append("unsafe_browser_observation_name")
        elif item.get("observed_text") not in allowed:
            reasons.append("unsafe_browser_observed_text")
    return reasons


def validate_browser_gate_receipt(
    receipt: Any,
    *,
    expected_source_digest: str,
) -> ReceiptValidation:
    """Validate browser provenance, completeness, timing, and safe contents."""

    if not isinstance(receipt, dict):
        return ReceiptValidation("FAIL", ("invalid_browser_receipt",))

    reasons: list[str] = []
    if receipt.get("contract_version") != BROWSER_GATE_CONTRACT_VERSION:
        reasons.append("invalid_browser_contract_version")
    if receipt.get("status") != "PASS":
        reasons.append("invalid_browser_status")
    if receipt.get("observer") != "in_app_browser":
        reasons.append("invalid_browser_observer")
    if receipt.get("fixture_id") != FIXTURE_ID:
        reasons.append("invalid_browser_fixture")
    source_digest = receipt.get("source_digest")
    if not isinstance(source_digest, str) or not _SHA256_RE.fullmatch(source_digest):
        reasons.append("invalid_browser_source_digest")
    if source_digest != expected_source_digest:
        reasons.append("stale_browser_receipt")
    source_commit = receipt.get("source_commit")
    if not isinstance(source_commit, str) or not _COMMIT_RE.fullmatch(source_commit):
        reasons.append("invalid_browser_source_commit")
    url = receipt.get("url")
    if not isinstance(url, str) or not re.fullmatch(
        r"http://127\.0\.0\.1:\d{1,5}", url
    ):
        reasons.append("invalid_browser_fixture_url")

    raw_observations = receipt.get("observations")
    if not isinstance(raw_observations, list):
        raw_observations = []
        reasons.append("invalid_browser_observations")
    observations: dict[str, dict[str, Any]] = {}
    duplicate_names = False
    for item in raw_observations:
        if not isinstance(item, dict):
            reasons.append("invalid_browser_observation")
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name:
            reasons.append("invalid_browser_observation")
            continue
        if name in observations:
            duplicate_names = True
        observations[name] = item
        if not all(
            _is_nonnegative_int(item.get(field))
            for field in ("browser_ms", "server_event_ms", "turn_end_browser_ms")
        ):
            reasons.append("invalid_browser_timing")
    if duplicate_names:
        reasons.append("duplicate_browser_observations")
    if not REQUIRED_OBSERVATIONS.issubset(observations):
        reasons.append("missing_browser_observations")

    for name in _PRE_TURN_END_OBSERVATIONS:
        item = observations.get(name)
        if item and not (
            _is_nonnegative_int(item.get("browser_ms"))
            and _is_nonnegative_int(item.get("turn_end_browser_ms"))
            and item["browser_ms"] < item["turn_end_browser_ms"]
        ):
            reasons.append("not_observed_before_turn_end")

    ordered = [
        observations.get(name, {}).get("browser_ms")
        for name in _PRE_TURN_END_OBSERVATIONS
    ]
    if all(_is_nonnegative_int(value) for value in ordered) and not all(
        earlier < later for earlier, later in zip(ordered, ordered[1:])
    ):
        reasons.append("invalid_browser_observation_order")
    normal_turn_ends = [
        observations.get(name, {}).get("turn_end_browser_ms")
        for name in _NORMAL_STREAM_OBSERVATIONS
    ]
    if (
        all(_is_nonnegative_int(value) for value in normal_turn_ends)
        and len(set(normal_turn_ends)) != 1
    ):
        reasons.append("inconsistent_normal_stream_turn_end")

    reasons.extend(_privacy_reason_codes(receipt))
    return ReceiptValidation(
        "PASS" if not reasons else "FAIL",
        tuple(dict.fromkeys(reasons)),
    )


def validate_browser_user_journey_receipt(
    receipt: Any,
    *,
    expected_source_digest: str,
) -> ReceiptValidation:
    """Validate Gate E v2 by user-visible lifecycle outcomes, not strings.

    The v1 browser contract remains a Web/SSE transport regression. This v2
    contract is the product gate: a receipt cannot pass unless one browser
    journey owns a consistent session, finishes its tasks, binds computation
    and evidence, satisfies independent oracles, and survives refresh.
    """

    if not isinstance(receipt, dict):
        return ReceiptValidation("FAIL", ("invalid_user_journey_receipt",))

    reasons: list[str] = []
    if receipt.get("contract_version") != BROWSER_USER_JOURNEY_CONTRACT_VERSION:
        reasons.append("invalid_user_journey_contract_version")
    if receipt.get("status") != "PASS":
        reasons.append("invalid_user_journey_status")
    if receipt.get("observer") != "in_app_browser":
        reasons.append("invalid_user_journey_observer")
    if receipt.get("entrypoint") != "web":
        reasons.append("invalid_user_journey_entrypoint")

    scenario_id = receipt.get("scenario_id")
    if not isinstance(scenario_id, str) or not _SAFE_ID_RE.fullmatch(scenario_id):
        reasons.append("invalid_user_journey_scenario")
    for field in ("source_digest", "fixture_digest", "prompt_digest", "oracle_digest"):
        value = receipt.get(field)
        if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
            reasons.append(f"invalid_user_journey_{field}")
    if receipt.get("source_digest") != expected_source_digest:
        reasons.append("stale_user_journey_receipt")
    if not isinstance(receipt.get("source_commit"), str) or not _COMMIT_RE.fullmatch(
        receipt.get("source_commit", "")
    ):
        reasons.append("invalid_user_journey_source_commit")
    if not isinstance(receipt.get("url"), str) or not re.fullmatch(
        r"http://127\.0\.0\.1:\d{1,5}", receipt.get("url", "")
    ):
        reasons.append("invalid_user_journey_url")

    session_id = receipt.get("session_id")
    if not isinstance(session_id, str) or not _SAFE_ID_RE.fullmatch(session_id):
        reasons.append("invalid_user_journey_session")

    tasks = receipt.get("tasks")
    if not isinstance(tasks, dict):
        tasks = {}
        reasons.append("invalid_user_journey_tasks")
    task_int_fields = ("total", "completed", "terminal", "max_in_progress")
    if not all(_is_nonnegative_int(tasks.get(field)) for field in task_int_fields):
        reasons.append("invalid_user_journey_tasks")
    else:
        total = tasks["total"]
        if (
            total <= 0
            or tasks["completed"] != total
            or tasks["terminal"] != total
            or tasks["max_in_progress"] > 1
            or tasks.get("monotonic") is not True
        ):
            reasons.append("incomplete_user_journey_tasks")

    computations = receipt.get("computations")
    if not isinstance(computations, dict) or not all(
        _is_nonnegative_int(computations.get(field)) for field in ("bound", "orphan")
    ):
        reasons.append("invalid_user_journey_computations")
    else:
        if computations["bound"] < 1:
            reasons.append("missing_bound_user_journey_computation")
        if computations["orphan"]:
            reasons.append("orphan_user_journey_computation")

    evidence = receipt.get("evidence")
    if not isinstance(evidence, dict) or not all(
        _is_nonnegative_int(evidence.get(field))
        for field in ("bound", "orphan", "legacy_unbound")
    ):
        reasons.append("invalid_user_journey_evidence")
    else:
        if evidence["bound"] < 1:
            reasons.append("missing_bound_user_journey_evidence")
        if evidence["orphan"]:
            reasons.append("orphan_user_journey_evidence")
        if evidence["legacy_unbound"]:
            reasons.append("legacy_unbound_user_journey_evidence")

    oracle_assertions = receipt.get("oracle_assertions")
    if not isinstance(oracle_assertions, list) or len(oracle_assertions) < 2:
        reasons.append("missing_user_journey_oracles")
        oracle_assertions = []
    oracle_names: set[str] = set()
    for assertion in oracle_assertions:
        if not isinstance(assertion, dict):
            reasons.append("invalid_user_journey_oracle")
            continue
        name = assertion.get("name")
        if not isinstance(name, str) or not _SAFE_ID_RE.fullmatch(name) or name in oracle_names:
            reasons.append("invalid_user_journey_oracle")
        else:
            oracle_names.add(name)
        if assertion.get("passed") is not True:
            reasons.append("failed_user_journey_oracle")

    answer = receipt.get("answer")
    if not isinstance(answer, dict):
        answer = {}
        reasons.append("invalid_user_journey_answer")
    markers = answer.get("forbidden_markers")
    if not isinstance(markers, list) or any(not isinstance(item, str) for item in markers):
        reasons.append("invalid_user_journey_answer")
        markers = ["invalid_marker_payload"]
    if (
        answer.get("useful") is not True
        or answer.get("progress_visible") is not True
        or answer.get("complete_before_turn_end") is not True
        or answer.get("empty_structures") != 0
        or markers
    ):
        reasons.append("unusable_user_journey_answer")
    answer_digest = answer.get("content_digest")
    if not isinstance(answer_digest, str) or not _SHA256_RE.fullmatch(answer_digest):
        reasons.append("invalid_user_journey_answer_digest")

    refresh = receipt.get("refresh")
    if not isinstance(refresh, dict):
        refresh = {}
        reasons.append("invalid_user_journey_refresh")
    expected_total = tasks.get("total") if isinstance(tasks, dict) else None
    expected_completed = tasks.get("completed") if isinstance(tasks, dict) else None
    expected_evidence = evidence.get("bound") if isinstance(evidence, dict) else None
    if (
        refresh.get("session_id") != session_id
        or refresh.get("task_total") != expected_total
        or refresh.get("task_completed") != expected_completed
        or refresh.get("evidence_bound") != expected_evidence
        or refresh.get("answer_restored") is not True
        or refresh.get("answer_digest") != answer_digest
    ):
        reasons.append("refresh_user_journey_mismatch")

    isolation = receipt.get("session_isolation")
    if not isinstance(isolation, dict) or isolation.get("passed") is not True:
        reasons.append("user_journey_session_isolation_failed")
    if not _is_nonnegative_int(receipt.get("elapsed_ms")):
        reasons.append("invalid_user_journey_elapsed_ms")
    if receipt.get("first_failure_stage") != "":
        reasons.append("user_journey_reports_failure_stage")

    reasons.extend(_v2_privacy_reason_codes(receipt))

    return ReceiptValidation(
        "PASS" if not reasons else "FAIL",
        tuple(dict.fromkeys(reasons)),
    )


def write_browser_gate_receipt(
    path: Path,
    receipt: Any,
    *,
    expected_source_digest: str,
) -> Path:
    """Validate then atomically persist the privacy-bounded browser receipt."""

    result = validate_browser_gate_receipt(
        receipt,
        expected_source_digest=expected_source_digest,
    )
    if result.status != "PASS":
        raise ValueError(",".join(result.reason_codes))

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)
    return path


def write_browser_user_journey_receipt(
    path: Path,
    receipt: Any,
    *,
    expected_source_digest: str,
) -> Path:
    """Validate and atomically persist a Gate E/F v2 browser journey."""

    result = validate_browser_user_journey_receipt(
        receipt,
        expected_source_digest=expected_source_digest,
    )
    if result.status != "PASS":
        raise ValueError(",".join(result.reason_codes))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)
    return path


def _release_source_digest(root: Path) -> str:
    try:
        from scripts.acceptance.release_source import release_source_digest
    except ModuleNotFoundError:  # Direct ``python browser_gate_contract.py``.
        from release_source import release_source_digest

    return release_source_digest(root)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate an actual-browser Gate E receipt."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate")
    validate.add_argument("--receipt", type=Path, required=True)
    validate.add_argument("--root", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
    expected = _release_source_digest(args.root)
    validator = (
        validate_browser_user_journey_receipt
        if receipt.get("contract_version") == BROWSER_USER_JOURNEY_CONTRACT_VERSION
        else validate_browser_gate_receipt
    )
    result = validator(receipt, expected_source_digest=expected)
    print(
        json.dumps(
            {
                "status": result.status,
                "reason_codes": result.reason_codes,
                "source_digest": expected,
            },
            ensure_ascii=False,
        )
    )
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
