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

    def __init__(self, code: str, diagnostics: dict[str, str] | None = None):
        self.code = code
        self.diagnostics = diagnostics or {}
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


def _finish_reason_bucket(response: Any) -> str:
    value = getattr(response, "finish_reason", None)
    return value if value in {"stop", "length", "tool_calls", "content_filter"} else "missing_or_other"


def _content_length_bucket(raw: Any) -> str:
    if not isinstance(raw, str) or not raw:
        return "empty_or_non_string"
    length = len(raw)
    if length <= 256:
        return "1_to_256"
    if length <= 1024:
        return "257_to_1024"
    if length <= 4096:
        return "1025_to_4096"
    return "over_4096"


def _transport_diagnostics(response: Any, raw: Any, shape: str) -> dict[str, str]:
    """Return response-shape evidence without retaining Provider-controlled text."""
    return {
        "response_shape": shape,
        "response_length_bucket": _content_length_bucket(raw),
        "response_reasoning_length_bucket": _content_length_bucket(getattr(response, "reasoning_content", "") or ""),
        "response_finish_reason": _finish_reason_bucket(response),
    }


def _response_error(response: Any, raw: Any, code: str, shape: str) -> ProviderResponseValidationError:
    return ProviderResponseValidationError(code, _transport_diagnostics(response, raw, shape))


def _decode_response_object(response: Any) -> tuple[dict[str, Any], str, dict[str, str]]:
    """Accept one unique JSON object, optionally wrapped by presentation text.

    Provider text is used transiently and never returned or persisted.  The
    structured object must still pass all semantic checks.  Diagnostics retain
    only shape, bounded length, and finish reason, never Provider text.
    """
    raw = getattr(response, "text", "") or ""
    if not isinstance(raw, str):
        raise _response_error(response, raw, "response_not_json", "non_string")
    candidate = raw.strip()
    if not candidate:
        raise _response_error(response, raw, "response_not_json", "empty")
    try:
        payload = json.loads(candidate)
        if not isinstance(payload, dict):
            raise _response_error(response, raw, "response_not_json_object", "direct_non_object")
        return payload, "direct", _transport_diagnostics(response, raw, "direct_object")
    except json.JSONDecodeError:
        fenced = re.fullmatch(r"```(?:json)?\s*(\{.*\})\s*```", candidate, flags=re.DOTALL | re.IGNORECASE)
        if fenced:
            try:
                payload = json.loads(fenced.group(1))
            except json.JSONDecodeError as exc:
                raise _response_error(response, raw, "response_not_json", "invalid_fenced_object") from exc
            if not isinstance(payload, dict):
                raise _response_error(response, raw, "response_not_json_object", "fenced_non_object")
            return payload, "fenced", _transport_diagnostics(response, raw, "fenced_object")

    # A JSON-object mode is advisory for some OpenAI-compatible gateways.  A
    # display prefix, suffix, or a brace in that display text must not hide one
    # valid structured object.  Multiple independent objects remain rejected:
    # selecting one would change the output semantics without a contract.
    decoded: list[tuple[int, int, dict[str, Any]]] = []
    decoder = json.JSONDecoder()
    for start, character in enumerate(candidate):
        if character != "{":
            continue
        try:
            value, end = decoder.raw_decode(candidate[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            decoded.append((start, start + end, value))
    top_level = [
        item for index, item in enumerate(decoded)
        if not any(
            other_index != index and other[0] <= item[0] and item[1] <= other[1]
            for other_index, other in enumerate(decoded)
        )
    ]
    if not top_level:
        shape = "no_json_object_start" if "{" not in candidate else "invalid_json_object"
        raise _response_error(response, raw, "response_not_json", shape)
    if len(top_level) != 1:
        raise _response_error(response, raw, "response_ambiguous_json_objects", "multiple_json_objects")
    _, _, payload = top_level[0]
    return payload, "embedded", _transport_diagnostics(response, raw, "embedded_unique_object")


def _validate_scenario(scenario: Any, reference_hashes: dict[str, str], expected_call_budget: int = 1) -> list[str]:
    if not isinstance(scenario, dict):
        return ["scenario must be an object"]
    scenario_id = _text(scenario.get("id"))
    if not scenario_id:
        return ["scenario id is required"]
    errors: list[str] = []
    for field in ("question",):
        if not _text(scenario.get(field)):
            errors.append(f"{scenario_id}: {field} is required")
    if scenario.get("call_budget") != expected_call_budget:
        detail = (
            "call_budget must equal the max_tokens_ladder length"
            if expected_call_budget != 1
            else "call_budget must be exactly 1"
        )
        errors.append(f"{scenario_id}: {detail}")
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


_REQUEST_KEYS = {"temperature", "max_tokens", "timeout_seconds", "response_format", "max_tokens_ladder", "api_base", "api_base_env", "api_key_env"}


def _env_or_dotenv(name: str, dotenv_path: Path | None = None) -> str | None:
    """Resolve a variable from the process environment, then the repo .env.

    pydantic-settings loads .env into the config object but not into
    os.environ, so manifest-declared credentials must fall back to parsing
    the .env file explicitly.
    """
    value = os.environ.get(name)
    if value:
        return value
    path = Path(dotenv_path) if dotenv_path is not None else ROOT / ".env"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return None
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, raw = stripped.partition("=")
        if key.strip() == name:
            return raw.strip().strip('"').strip("'") or None
    return None


def _validate_request(request: Any) -> list[str]:
    if not isinstance(request, dict):
        return ["request must be an object"]
    errors: list[str] = []
    if unsupported := sorted(set(request) - _REQUEST_KEYS):
        errors.append(f"request contains unsupported keys: {unsupported}")
    if request.get("temperature") != 0.0:
        errors.append("request.temperature must be exactly 0.0")
    ladder = request.get("max_tokens_ladder")
    has_scalar = "max_tokens" in request
    if has_scalar and ladder is not None:
        errors.append("request.max_tokens and max_tokens_ladder are mutually exclusive")
    if ladder is not None:
        if (
            not isinstance(ladder, list)
            or not 1 <= len(ladder) <= 3
            or not all(isinstance(value, int) and not isinstance(value, bool) for value in ladder)
        ):
            errors.append("request.max_tokens_ladder must be a list of 1 to 3 integer rungs")
        elif any(later <= earlier for earlier, later in zip(ladder, ladder[1:])):
            errors.append("request.max_tokens_ladder rungs must be strictly ascending")
        elif any(value < 100 or value > 128000 for value in ladder):
            errors.append("request.max_tokens_ladder rungs must be between 100 and 128000")
    elif not has_scalar or not isinstance(request.get("max_tokens"), int) or request["max_tokens"] <= 0:
        errors.append("request.max_tokens must be a positive integer")
    if not isinstance(request.get("timeout_seconds"), int) or request["timeout_seconds"] <= 0:
        errors.append("request.timeout_seconds must be a positive integer")
    if request.get("response_format") != {"type": "json_object"}:
        errors.append("request.response_format must be exactly {'type': 'json_object'}")
    api_base = request.get("api_base")
    api_base_env = request.get("api_base_env")
    if api_base is not None and api_base_env is not None:
        errors.append("request.api_base and api_base_env are mutually exclusive")
    for field, value in (("api_base", api_base), ("api_base_env", api_base_env), ("api_key_env", request.get("api_key_env"))):
        if value is not None and (not isinstance(value, str) or not value.strip()):
            errors.append(f"request.{field} must be a non-empty string")
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
    request = manifest.get("request")
    ladder = request.get("max_tokens_ladder") if isinstance(request, dict) else None
    expected_call_budget = len(ladder) if isinstance(ladder, list) and ladder else 1
    for scenario in scenarios:
        errors.extend(_validate_scenario(scenario, reference_hashes, expected_call_budget))
    total_budget = sum(item.get("call_budget", 0) for item in scenarios if isinstance(item, dict) and isinstance(item.get("call_budget"), int))
    if manifest.get("total_call_budget") != total_budget:
        errors.append("total_call_budget does not equal the sum of scenario budgets")
    model_id = _text(manifest.get("model_id"))
    if not model_id:
        errors.append("model_id is required")
    request = manifest.get("request")
    provider_declared = isinstance(request, dict) and any(
        key in request for key in ("api_base", "api_base_env", "api_key_env")
    )
    # A manifest-declared provider (heterogeneous batch) is intentionally not
    # bound to the configured main model.
    if current_model_id is not None and model_id != current_model_id and not provider_declared:
        errors.append("configured model_id does not match frozen model_id")
    errors.extend(_validate_request(request))
    if isinstance(request, dict):
        for env_field in ("api_base_env", "api_key_env"):
            name = request.get(env_field)
            if name and _env_or_dotenv(name) is None:
                errors.append(f"environment variable {name} is not set")
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
    raw = getattr(response, "text", "") or ""
    if getattr(response, "finish_reason", None) == "length":
        raise _response_error(response, raw, "response_truncated", "truncated_before_complete")
    if getattr(response, "tool_calls", None):
        raise _response_error(response, raw, "tool_calls_disallowed", "tool_calls")
    payload, envelope, diagnostics = _decode_response_object(response)
    try:
        if payload.get("scenario_id") != scenario["id"]:
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
    except ProviderResponseValidationError as exc:
        exc.diagnostics = {**diagnostics, **exc.diagnostics}
        raise
    payload["_gate_c_json_envelope"] = envelope
    payload["_gate_c_response_diagnostics"] = diagnostics
    return payload


def _response_summary(payload: dict[str, Any]) -> dict[str, Any]:
    """Return verification metadata only; never persist uncontrolled model text."""
    return {
        "fact_ids_used": payload["fact_ids_used"],
        "method_limitations_count": len(payload["method_limitations"]),
        "prohibited_inference_acknowledged": payload["prohibited_inference_acknowledged"],
        "decision_characters": len(_text(payload["decision"])),
        "next_action_characters": len(_text(payload["next_action"])),
        "json_envelope": payload["_gate_c_json_envelope"],
        **payload["_gate_c_response_diagnostics"],
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
    rungs = request.get("max_tokens_ladder") or [request["max_tokens"]]
    ladder_batch = len(rungs) > 1
    api_base = request.get("api_base")
    if api_base is None and request.get("api_base_env"):
        api_base = _env_or_dotenv(request["api_base_env"])
    api_key = _env_or_dotenv(request["api_key_env"]) if request.get("api_key_env") else None
    effective_client = client or LLMClient(
        model_id=report["model_id"],
        temperature=request["temperature"],
        timeout=request["timeout_seconds"],
        api_base=api_base,
        api_key=api_key,
    )
    results = []
    calls_made = 0

    def persisted_result(*, in_flight: str | None = None) -> dict[str, Any]:
        status = "passed" if results and len(results) == len(manifest["scenarios"]) and all(item["status"] == "passed" for item in results) else "in_progress"
        if len(results) == len(manifest["scenarios"]) and status != "passed":
            status = "completed_with_failures"
        value = {**report, "mode": "executed", "status": status, "calls_made": calls_made, "results": results}
        if in_flight is not None:
            value["in_flight_scenario_id"] = in_flight
        return value

    if report_path is not None:
        initialize_execution_report(report_path, persisted_result())
    for scenario in manifest["scenarios"]:
        if report_path is not None:
            write_execution_report(report_path, persisted_result(in_flight=scenario["id"]))
        attempts: list[dict[str, Any]] = []
        outcome: dict[str, Any] | None = None
        for rung in rungs:
            try:
                response = effective_client.chat_once(
                    messages=[{"role": "user", "content": _prompt_for(scenario)}],
                    tools=None,
                    system=SYSTEM_PROMPT,
                    response_format=request["response_format"],
                    max_tokens=rung,
                )
                payload = _validate_response(scenario, response)
            except ProviderResponseValidationError as exc:
                calls_made += 1
                attempts.append({"max_tokens": rung, "error_code": exc.code, **exc.diagnostics})
                if exc.code != "response_truncated":
                    # Only a truncated response climbs the ladder; semantic
                    # failures would fail identically at every rung.
                    outcome = {
                        "id": scenario["id"],
                        "status": "failed",
                        "failure_stage": "provider_response_validation",
                        "error_code": exc.code,
                        **({"max_tokens_attempts": attempts} if ladder_batch else {}),
                        **exc.diagnostics,
                    }
                    break
            except Exception as exc:
                calls_made += 1
                attempts.append({
                    "max_tokens": rung,
                    "error_code": "provider_request_error",
                    "exception_type": type(exc).__name__,
                })
                outcome = {
                    "id": scenario["id"],
                    "status": "failed",
                    "failure_stage": "provider_request",
                    "error_code": "provider_request_error",
                    "exception_type": type(exc).__name__,
                    **({"max_tokens_attempts": attempts} if ladder_batch else {}),
                }
                break
            else:
                calls_made += 1
                outcome = {
                    "id": scenario["id"],
                    "status": "passed",
                    **({"max_tokens_used": rung, "max_tokens_attempts": attempts} if ladder_batch else {}),
                    "response_summary": _response_summary(payload),
                }
                break
            if report_path is not None:
                write_execution_report(report_path, persisted_result(in_flight=scenario["id"]))
        if outcome is None:
            last = attempts[-1]
            outcome = {
                "id": scenario["id"],
                "status": "failed",
                "failure_stage": "provider_response_validation",
                "error_code": "response_truncated",
                "max_tokens_attempts": attempts,
                **{key: value for key, value in last.items() if key not in {"max_tokens", "error_code"}},
            }
        results.append(outcome)
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
