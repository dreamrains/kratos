"""Count-bounded, no-retry preflight and executor for Route A Gate C.

The normal AgentLoop intentionally permits iterative tool use and the regular
LLM client retries transient transport failures.  Neither is suitable for a
real Provider authorization that must be exactly countable.  This module is a
separate measurement boundary: one non-streaming request per frozen scenario,
no tools, no fallback, and stop the entire batch on the first failure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from scripts.acceptance.real_data_manifest import REFERENCE_DATA, validate_reference_data
from scripts.acceptance.release_source import release_source_digest


MANIFEST_SCHEMA = "route_a_provider_candidates.v1"
SYSTEM_PROMPT = (
    "你是受审计的数据分析评审员。只能使用提供的冻结事实包，不得调用工具、"
    "不得补造数据或因果结论。只返回一个 JSON 对象，不要 Markdown、解释文字或省略字段。"
)
_DECISION_PLACEHOLDER = "基于冻结事实的有边界判断"
_LIMITATION_PLACEHOLDER = "至少一条来自冻结事实的限制"
_NEXT_ACTION_PLACEHOLDER = "可执行的下一步"


class ProviderPreflightError(ValueError):
    """Raised before any Provider request when a frozen batch is invalid."""


class ProviderResponseValidationError(ProviderPreflightError):
    """A sanitized, stable result-contract failure after one Provider call."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _read_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProviderPreflightError(f"invalid candidate manifest: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != MANIFEST_SCHEMA:
        raise ProviderPreflightError(f"manifest schema_version must be {MANIFEST_SCHEMA}")
    return payload


def _text(value: Any) -> str:
    return " ".join(value.split()) if isinstance(value, str) else ""


def _prompt_for(scenario: dict[str, Any]) -> str:
    packet = scenario.get("fact_packet")
    required_fact_ids = [item["id"] for item in packet]
    response_template = {
        "scenario_id": scenario["id"],
        "decision": _DECISION_PLACEHOLDER,
        "fact_ids_used": required_fact_ids,
        "method_limitations": [_LIMITATION_PLACEHOLDER],
        "prohibited_inference_acknowledged": True,
        "next_action": _NEXT_ACTION_PLACEHOLDER,
    }
    return "\n".join((
        f"场景：{scenario['id']}",
        f"问题：{scenario['question']}",
        "冻结事实包：",
        json.dumps(packet, ensure_ascii=False, sort_keys=True),
        "只返回以下 JSON 对象结构（不得 Markdown，不得删除、改名或留空任一字段）：",
        json.dumps(response_template, ensure_ascii=False),
        "约束：fact_ids_used 必须逐项包含全部冻结事实 ID；method_limitations 必须为非空字符串数组；"
        "prohibited_inference_acknowledged 必须是 JSON 布尔值 true；decision 必须引用事实包中至少一个原样数字；"
        "示例字符串仅示意字段类型，不能原样复述；不得给出因果结论或把缺失补造为数据。",
    ))


def _prompt_hash(scenario: dict[str, Any]) -> str:
    value = json.dumps({"system": SYSTEM_PROMPT, "user": _prompt_for(scenario)}, ensure_ascii=False, sort_keys=True)
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def _validate_scenario(scenario: Any, reference_hashes: dict[str, str]) -> list[str]:
    if not isinstance(scenario, dict):
        return ["scenario must be an object"]
    scenario_id = _text(scenario.get("id"))
    if not scenario_id:
        return ["scenario id is required"]
    errors: list[str] = []
    for field in ("question",):
        if not _text(scenario.get(field)):
            errors.append(f"{scenario_id}: {field} is required")
    if scenario.get("call_budget") != 1:
        errors.append(f"{scenario_id}: call_budget must be exactly 1")
    if scenario.get("tools_allowed") is not False:
        errors.append(f"{scenario_id}: tools_allowed must be false")
    data_ids = scenario.get("data_ids")
    if not isinstance(data_ids, list) or not data_ids or not all(isinstance(item, str) for item in data_ids):
        errors.append(f"{scenario_id}: data_ids must be a non-empty string list")
    elif missing := sorted(set(data_ids) - set(reference_hashes)):
        errors.append(f"{scenario_id}: unknown reference data ids: {missing}")
    facts = scenario.get("fact_packet")
    if not isinstance(facts, list) or not facts or not all(isinstance(item, dict) and _text(item.get("id")) and _text(item.get("value")) for item in facts):
        errors.append(f"{scenario_id}: fact_packet needs non-empty id/value facts")
    elif len([item["id"] for item in facts]) != len({item["id"] for item in facts}):
        errors.append(f"{scenario_id}: fact_packet ids must be unique")
    return errors


def _validate_request(request: Any) -> list[str]:
    if not isinstance(request, dict):
        return ["request must be an object"]
    errors: list[str] = []
    if request.get("temperature") != 0.0:
        errors.append("request.temperature must be exactly 0.0")
    if not isinstance(request.get("max_tokens"), int) or request["max_tokens"] <= 0:
        errors.append("request.max_tokens must be a positive integer")
    if not isinstance(request.get("timeout_seconds"), int) or request["timeout_seconds"] <= 0:
        errors.append("request.timeout_seconds must be a positive integer")
    if request.get("response_format") != {"type": "json_object"}:
        errors.append("request.response_format must be exactly {'type': 'json_object'}")
    return errors


def preflight(
    manifest_path: Path,
    *,
    reference_hashes: dict[str, str] | None = None,
    current_model_id: str | None = None,
    source_digest: Callable[[Path], str] = release_source_digest,
) -> dict[str, Any]:
    """Validate all authorization-critical inputs without contacting a Provider."""
    manifest_path = Path(manifest_path).resolve()
    manifest = _read_manifest(manifest_path)
    if reference_hashes is None:
        reference_hashes = {item.id: item.sha256 for item in REFERENCE_DATA.files}
        data_errors = validate_reference_data()
    else:
        data_errors = []
    scenarios = manifest.get("scenarios")
    errors = list(data_errors)
    if not isinstance(scenarios, list) or not scenarios:
        errors.append("scenarios must be a non-empty list")
        scenarios = []
    scenario_ids = [_text(item.get("id")) for item in scenarios if isinstance(item, dict)]
    if len(scenario_ids) != len(set(scenario_ids)):
        errors.append("scenario ids must be unique")
    for scenario in scenarios:
        errors.extend(_validate_scenario(scenario, reference_hashes))
    total_budget = sum(item.get("call_budget", 0) for item in scenarios if isinstance(item, dict) and isinstance(item.get("call_budget"), int))
    if manifest.get("total_call_budget") != total_budget:
        errors.append("total_call_budget does not equal the sum of scenario budgets")
    model_id = _text(manifest.get("model_id"))
    if not model_id:
        errors.append("model_id is required")
    if current_model_id is not None and model_id != current_model_id:
        errors.append("configured model_id does not match frozen model_id")
    request = manifest.get("request")
    errors.extend(_validate_request(request))
    return {
        "schema_version": "route_a_provider_preflight.v1",
        "mode": "preflight",
        "ready": not errors,
        "errors": errors,
        "source_digest": source_digest(ROOT),
        "model_id": model_id,
        "request": request,
        "total_call_budget": total_budget,
        "scenarios": [
            {
                "id": _text(item.get("id")),
                "call_budget": item.get("call_budget"),
                "data": [{"id": data_id, "sha256": reference_hashes[data_id]} for data_id in item.get("data_ids", []) if data_id in reference_hashes],
                "prompt_sha256": _prompt_hash(item),
            }
            for item in scenarios
            if isinstance(item, dict)
        ],
    }


def _validate_response(scenario: dict[str, Any], response: Any) -> dict[str, Any]:
    if getattr(response, "tool_calls", None):
        raise ProviderResponseValidationError("tool_calls_disallowed")
    try:
        payload = json.loads(_text(getattr(response, "text", "")))
    except json.JSONDecodeError as exc:
        raise ProviderResponseValidationError("response_not_json") from exc
    if not isinstance(payload, dict) or payload.get("scenario_id") != scenario["id"]:
        raise ProviderResponseValidationError("scenario_id_mismatch")
    fact_ids = {str(item.get("id")) for item in scenario["fact_packet"]}
    used = {str(item) for item in payload.get("fact_ids_used", []) if isinstance(item, str)}
    if not fact_ids <= used:
        raise ProviderResponseValidationError("frozen_fact_ids_omitted")
    if payload.get("prohibited_inference_acknowledged") is not True:
        raise ProviderResponseValidationError("prohibited_inference_unacknowledged")
    for field in ("decision", "next_action"):
        if not _text(payload.get(field)):
            raise ProviderResponseValidationError(f"missing_{field}")
    decision = _text(payload["decision"])
    if decision == _DECISION_PLACEHOLDER:
        raise ProviderResponseValidationError("placeholder_decision")
    if _text(payload["next_action"]) == _NEXT_ACTION_PLACEHOLDER:
        raise ProviderResponseValidationError("placeholder_next_action")
    numeric_anchors = {
        match
        for fact in scenario["fact_packet"]
        for match in re.findall(r"\d+(?:\.\d+)?", fact["value"])
    }
    if numeric_anchors and not any(anchor in decision for anchor in numeric_anchors):
        raise ProviderResponseValidationError("decision_missing_frozen_numeric_anchor")
    if not isinstance(payload.get("method_limitations"), list) or not payload["method_limitations"]:
        raise ProviderResponseValidationError("missing_method_limitations")
    if any(_text(item) == _LIMITATION_PLACEHOLDER for item in payload["method_limitations"]):
        raise ProviderResponseValidationError("placeholder_method_limitations")
    return payload


def _response_summary(payload: dict[str, Any]) -> dict[str, Any]:
    """Return verification metadata only; never persist uncontrolled model text."""
    return {
        "fact_ids_used": payload["fact_ids_used"],
        "method_limitations_count": len(payload["method_limitations"]),
        "prohibited_inference_acknowledged": payload["prohibited_inference_acknowledged"],
        "decision_characters": len(_text(payload["decision"])),
        "next_action_characters": len(_text(payload["next_action"])),
    }


def _assert_sanitized_report(value: Any) -> None:
    """Reject report payloads that could retain uncontrolled Provider content."""
    if isinstance(value, dict):
        forbidden = {"response", "text", "reasoning", "raw"} & set(value)
        if forbidden:
            raise ProviderPreflightError(f"report contains forbidden raw-response keys: {sorted(forbidden)}")
        for item in value.values():
            _assert_sanitized_report(item)
    elif isinstance(value, list):
        for item in value:
            _assert_sanitized_report(item)


def _audit_report_path(path: Path) -> Path:
    target = Path(path).resolve()
    audit_root = (ROOT / "docs" / "audit").resolve()
    if target.parent != audit_root or target.suffix != ".json":
        raise ProviderPreflightError("report path must be a .json file directly under docs/audit")
    return target


def write_execution_report(path: Path, report: dict[str, Any]) -> Path:
    """Atomically persist only the sanitized batch receipt under docs/audit."""
    target = _audit_report_path(path)
    _assert_sanitized_report(report)
    temporary = target.with_name(f".{target.name}.tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, target)
    return target


def initialize_execution_report(path: Path, report: dict[str, Any]) -> Path:
    """Reserve an empty audit receipt before any Provider request starts."""
    target = _audit_report_path(path)
    if target.exists():
        raise ProviderPreflightError("report path already exists; refusing to overwrite an audit receipt")
    return write_execution_report(target, report)


def execute_authorized_batch(
    manifest_path: Path,
    *,
    authorized_source_digest: str,
    client=None,
    report_path: Path | None = None,
) -> dict[str, Any]:
    """Execute every frozen scenario once; failures are recorded without retries.

    Preflight failures stop before any request.  Once an exact batch has been
    authorized, each independent scenario consumes at most one request so the
    caller receives one bounded diagnostic report instead of one failure per
    authorization cycle.
    """
    from data_agent.config import get_config
    from data_agent.llm.client import LLMClient

    report = preflight(manifest_path, current_model_id=get_config().model_id)
    if not report["ready"]:
        raise ProviderPreflightError(f"preflight failed: {report['errors']}")
    if authorized_source_digest != report["source_digest"]:
        raise ProviderPreflightError("authorized source digest does not match current source")
    manifest = _read_manifest(Path(manifest_path))
    request = manifest["request"]
    effective_client = client or LLMClient(
        model_id=report["model_id"],
        temperature=request["temperature"],
        max_tokens=request["max_tokens"],
        timeout=request["timeout_seconds"],
    )
    results = []

    def persisted_result(*, in_flight: str | None = None) -> dict[str, Any]:
        status = "passed" if results and len(results) == len(manifest["scenarios"]) and all(item["status"] == "passed" for item in results) else "in_progress"
        if len(results) == len(manifest["scenarios"]) and status != "passed":
            status = "completed_with_failures"
        value = {**report, "mode": "executed", "status": status, "calls_made": len(results), "results": results}
        if in_flight is not None:
            value["in_flight_scenario_id"] = in_flight
        return value

    if report_path is not None:
        initialize_execution_report(report_path, persisted_result())
    for scenario in manifest["scenarios"]:
        if report_path is not None:
            write_execution_report(report_path, persisted_result(in_flight=scenario["id"]))
        try:
            response = effective_client.chat_once(
                messages=[{"role": "user", "content": _prompt_for(scenario)}],
                tools=None,
                system=SYSTEM_PROMPT,
                response_format=request["response_format"],
            )
            payload = _validate_response(scenario, response)
        except ProviderResponseValidationError as exc:
            results.append({
                "id": scenario["id"],
                "status": "failed",
                "failure_stage": "provider_response_validation",
                "error_code": exc.code,
            })
        except Exception as exc:
            results.append({
                "id": scenario["id"],
                "status": "failed",
                "failure_stage": "provider_request",
                "error_code": "provider_request_error",
                "exception_type": type(exc).__name__,
            })
        else:
            results.append({"id": scenario["id"], "status": "passed", "response_summary": _response_summary(payload)})
        if report_path is not None:
            write_execution_report(report_path, persisted_result())
    return persisted_result()


def main() -> int:
    parser = argparse.ArgumentParser(description="Route A Gate C exact-call preflight")
    parser.add_argument("--manifest", type=Path, default=ROOT / "tests" / "acceptance" / "route_a_gate_c_candidates.json")
    parser.add_argument("--execute", action="store_true", help="make the frozen Provider calls; requires exact authorization")
    parser.add_argument("--authorized-source-digest", default="")
    parser.add_argument("--report-path", type=Path, help="sanitized JSON receipt required for --execute")
    args = parser.parse_args()
    from data_agent.config import get_config

    if not args.execute:
        result = preflight(args.manifest, current_model_id=get_config().model_id)
    else:
        if args.report_path is None:
            parser.error("--report-path is required with --execute before any Provider request")
        result = execute_authorized_batch(
            args.manifest,
            authorized_source_digest=args.authorized_source_digest,
            report_path=args.report_path,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if (result.get("status") == "passed" if args.execute else result.get("ready")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
