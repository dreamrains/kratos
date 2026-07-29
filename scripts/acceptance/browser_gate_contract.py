"""Fail-closed receipt contract for the actual in-app-browser release gate."""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


BROWSER_GATE_CONTRACT_VERSION = "analysis_browser_gate.v1"
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


@dataclass(frozen=True)
class ReceiptValidation:
    status: str
    reason_codes: tuple[str, ...]


def _is_nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


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
    if all(_is_nonnegative_int(value) for value in ordered) and ordered != sorted(
        ordered
    ):
        reasons.append("invalid_browser_observation_order")

    reasons.extend(_privacy_reason_codes(receipt))
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
    result = validate_browser_gate_receipt(
        receipt,
        expected_source_digest=expected,
    )
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
