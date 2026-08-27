"""Offline journey replay for Route A Gate C (zero Provider requests).

The single-call Gate C batch validates grounded judgment on frozen fact
packets.  Journey-level Gate C must additionally validate the real tool loop
(upload -> question -> tool rounds -> final answer), and its authorization
needs the actual call structure first: rounds demanded, per-round prompt
digest, offered tool schemas, executed tool calls.  This module measures that
structure by driving the REAL AgentLoop, tool registry and data files with a
frozen per-round script -- no Provider is ever contacted.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from scripts.acceptance.real_data_manifest import REFERENCE_DATA, validate_reference_data
from scripts.acceptance.release_source import release_source_digest


JOURNEY_SCHEMA = "route_a_journey_replay.v1"
JOURNEY_CANDIDATE_SCHEMA = "route_a_journey_candidate.v1"
_REPORT_SCHEMA = "route_a_journey_replay_report.v1"
_EXECUTE_REPORT_SCHEMA = "route_a_journey_execute_report.v1"
_SESSION_PREFIX = "gate_c_journey"
_PUBLICATION_ACCEPTANCE = "publication"
_ROUTING_INTEGRITY_ACCEPTANCE = "routing_integrity"
_ACCEPTANCE_MODES = {_PUBLICATION_ACCEPTANCE, _ROUTING_INTEGRITY_ACCEPTANCE}


class JourneyStructureError(ValueError):
    """The real loop demanded a structure the frozen script does not cover."""


def _digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _file_digest(path: Path) -> str:
    """Return a checkout-portable digest for a frozen text replay reference.

    Git may materialize tracked JSON with CRLF on Windows even though the
    canonical blob uses LF.  Replay manifests are UTF-8 text contracts, so the
    frozen identity must not change solely because of checkout line endings.
    """
    canonical = path.read_bytes().replace(b"\r\n", b"\n")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def _read_dotted_path(payload: dict[str, Any], path: str) -> tuple[bool, Any]:
    """Read a scalar oracle field without allowing arbitrary expressions."""
    value: Any = payload
    for segment in path.split("."):
        if not segment or not isinstance(value, dict) or segment not in value:
            return False, None
        value = value[segment]
    return True, value


def _verify_tool_oracle(
    contract: dict[str, Any],
    tool_results: dict[str, list[dict[str, Any]]],
) -> tuple[list[str], list[dict[str, Any]]]:
    """Compare declared scalar facts with the real structured tool result.

    Final-answer anchors prove only what a model happened to say.  This
    contract instead freezes the product tool output that the answer must be
    grounded in, using simple dotted paths so both receipts and tests remain
    inspectable.
    """
    oracle = contract.get("tool_oracle")
    if oracle is None:
        return [], []
    if not isinstance(oracle, dict):
        return ["contract.tool_oracle must be an object"], []
    assertions = oracle.get("assertions")
    if not isinstance(assertions, list) or not assertions:
        return ["contract.tool_oracle.assertions must be a non-empty list"], []

    errors: list[str] = []
    observed: list[dict[str, Any]] = []
    for index, assertion in enumerate(assertions):
        if not isinstance(assertion, dict):
            errors.append(f"tool oracle assertion {index} must be an object")
            continue
        tool_name = assertion.get("tool")
        path = assertion.get("path")
        if not isinstance(tool_name, str) or not tool_name.strip() or not isinstance(path, str) or not path.strip() or "equals" not in assertion:
            errors.append(f"tool oracle assertion {index} needs tool, path, and equals")
            continue
        results = tool_results.get(tool_name, [])
        if not results:
            errors.append(f"tool oracle missing result for {tool_name}")
            continue
        found, actual = _read_dotted_path(results[-1], path)
        if not found:
            errors.append(f"tool oracle missing path {tool_name}.{path}")
            continue
        expected = assertion["equals"]
        observed.append({"tool": tool_name, "path": path, "actual": actual, "expected": expected})
        if actual != expected:
            errors.append(f"tool oracle mismatch {tool_name}.{path}: expected {expected!r}, got {actual!r}")
    return errors, observed


def _resolve_oracle_replay(path_value: Any) -> Path | None:
    if not isinstance(path_value, str) or not path_value.strip():
        return None
    candidate = (ROOT / path_value).resolve()
    try:
        candidate.relative_to(ROOT.resolve())
    except ValueError:
        return None
    return candidate


class ProviderNeutralAuxiliaryClient:
    """Exercise auxiliary routing hooks without constructing a Provider client."""

    provider_calls = 0

    def __init__(self):
        self.local_calls = 0

    def chat(self, messages, tools=None, system=None):
        from data_agent.llm.client import Response

        self.local_calls += 1
        return Response(text="", finish_reason="stop")


class ScriptedJourneyClient:
    """Replay frozen model rounds against the real AgentLoop.

    Records the structure of every round the loop requests -- the digest of
    (system, messages), the digest of the offered tool schemas, and which
    scripted round answered -- and refuses to serve more rounds than the
    frozen cap so a runaway loop fails the replay instead of silently
    succeeding.
    """

    def __init__(self, rounds: list[dict], round_cap: int | None = None):
        self._rounds = list(rounds)
        self._round_cap = int(round_cap or len(self._rounds))
        if self._round_cap < len(self._rounds):
            raise JourneyStructureError("round_cap below the scripted round count")
        self.rounds_served = 0
        self.structure: list[dict] = []

    def _serve(self, messages, tools, system):
        from data_agent.llm.client import Response, ToolCall

        self.rounds_served += 1
        if self.rounds_served > len(self._rounds) or self.rounds_served > self._round_cap:
            raise JourneyStructureError("round_cap_exceeded")
        script = self._rounds[self.rounds_served - 1]
        self.structure.append({
            "round": self.rounds_served,
            "prompt_sha256": _digest({"system": system or "", "messages": list(messages or [])}),
            "tools_count": len(tools or []),
            "tools_sha256": _digest(tools or []),
            "scripted_tool_calls": [item.get("name", "") for item in script.get("tool_calls", [])],
            "scripted_final_text": bool(script.get("text")),
        })
        tool_calls = [
            ToolCall(
                id=f"journey_r{self.rounds_served}_{index}",
                name=item["name"],
                arguments=dict(item.get("arguments", {})),
            )
            for index, item in enumerate(script.get("tool_calls", []))
        ]
        return Response(text=script.get("text", ""), tool_calls=tool_calls)

    def chat(self, messages, tools=None, system=None):
        return self._serve(messages, tools, system)

    def stream_chat_structured(self, messages, tools=None, system=None):
        from data_agent.llm.client import StreamComplete, StreamTextDelta

        response = self._serve(messages, tools, system)
        # A real Provider streams visible text as deltas before completing;
        # the loop publishes the final answer from those delta events.
        if response.text:
            yield StreamTextDelta(text=response.text)
        yield StreamComplete(response=response)


def _read_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise JourneyStructureError(f"invalid journey manifest: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != JOURNEY_SCHEMA:
        raise JourneyStructureError(f"manifest schema_version must be {JOURNEY_SCHEMA}")
    return payload


def _perform_uploads(uploads: list) -> tuple[list[dict], list[str]]:
    """Place frozen reference files into the workspace inbox before a turn.

    The plan defines journeys as starting from an upload; performing it via
    the product's own inbox path makes "the uploaded data" a true premise
    instead of an ambiguity the model has to resolve by luck.
    """
    import hashlib

    from data_agent.config import get_config

    from scripts.acceptance.real_data_manifest import REFERENCE_DATA

    errors: list[str] = []
    placed: list[dict] = []
    inbox = get_config().inbox_dir
    inbox.mkdir(parents=True, exist_ok=True)
    for item in uploads or []:
        data_id = str(item.get("data_id", ""))
        reference = REFERENCE_DATA.by_id.get(data_id)
        if reference is None:
            errors.append(f"unknown upload data id: {data_id}")
            continue
        name = str(item.get("as") or reference.filename)
        if not name.strip():
            errors.append(f"upload 'as' must be a non-empty filename for {data_id}")
            continue
        source = REFERENCE_DATA.path(data_id)
        if hashlib.sha256(source.read_bytes()).hexdigest() != reference.sha256:
            errors.append(f"upload source hash mismatch for {data_id}")
            continue
        shutil.copyfile(source, inbox / name)
        placed.append({"as": name, "sha256": f"sha256:{reference.sha256}"})
    return placed, errors


def run_journey_replay(
    manifest_path: Path,
    *,
    source_digest: Callable[[Path], str] = release_source_digest,
) -> dict[str, Any]:
    """Drive the real AgentLoop with the frozen script; never contact a Provider."""
    from data_agent.tools import discover_tools

    discover_tools()

    receipt: dict[str, Any] = {
        "schema_version": _REPORT_SCHEMA,
        "mode": "replay",
        "provider_calls": 0,
        "source_digest": source_digest(ROOT),
    }
    try:
        manifest = _read_manifest(Path(manifest_path))
    except JourneyStructureError as exc:
        receipt.update({"journey_id": "", "status": "failed", "errors": [str(exc)]})
        return receipt
    receipt["journey_id"] = manifest.get("journey_id", "")

    errors: list[str] = list(validate_reference_data())
    reference_hashes = {item.id: item.sha256 for item in REFERENCE_DATA.files}
    for item in manifest.get("data", []):
        expected = reference_hashes.get(item.get("id"))
        if expected is None:
            errors.append(f"unknown reference data id: {item.get('id')}")
        elif item.get("sha256") != expected:
            errors.append(f"data hash mismatch for {item.get('id')}")
    session_id = str(manifest.get("session_id", ""))
    if not session_id.startswith(_SESSION_PREFIX):
        errors.append(f"session_id must be dedicated to journeys (prefix {_SESSION_PREFIX})")
    if not str(manifest.get("question", "")).strip():
        errors.append("question is required")
    if errors:
        receipt.update({"status": "failed", "errors": errors})
        return receipt

    from data_agent.config import get_config

    session_dir = get_config().sessions_resolved / session_id
    if session_dir.exists():
        shutil.rmtree(session_dir)

    uploads_placed, upload_errors = _perform_uploads(manifest.get("uploads", []))
    if upload_errors:
        receipt.update({"status": "failed", "errors": upload_errors, "uploads": uploads_placed})
        return receipt

    script = manifest.get("script", {})
    client = ScriptedJourneyClient(script.get("rounds", []), script.get("round_cap"))
    auxiliary_client = ProviderNeutralAuxiliaryClient()

    from data_agent.agent.loop import AgentLoop

    loop = AgentLoop(
        client=client,
        auxiliary_llm_client=auxiliary_client,
        session_id=session_id,
    )
    tool_calls_executed: list[str] = []
    tool_results: dict[str, list[dict[str, Any]]] = {}
    error_events: list[str] = []
    final_text_parts: list[str] = []
    try:
        for event in loop.stream_turn(str(manifest["question"])):
            kind = event.get("type")
            if kind == "text_delta":
                final_text_parts.append(str(event.get("text", "")))
            elif kind == "tool_call":
                tool_calls_executed.append(str(event.get("name", "")))
            elif kind == "tool_result":
                tool_name = str(event.get("name", ""))
                web = event.get("web")
                data = web.get("data") if isinstance(web, dict) else None
                if tool_name and isinstance(data, dict):
                    tool_results.setdefault(tool_name, []).append(data)
            elif kind == "error":
                error_events.append(str(event.get("message", "")))
    except JourneyStructureError as exc:
        receipt.update({
            "status": "failed",
            "errors": [f"structure: {exc}"],
            "rounds_used": client.rounds_served,
            "rounds_scripted": len(script.get("rounds", [])),
            "structure": client.structure,
            "tool_calls_executed": tool_calls_executed,
        })
        return receipt

    contract = manifest.get("contract", {})
    required_tools = [str(item) for item in contract.get("required_tool_calls", [])]
    anchors = [str(item) for item in contract.get("final_answer_numeric_anchors", [])]
    tool_oracle_errors, tool_oracle_observed = _verify_tool_oracle(contract, tool_results)
    final_text = "".join(final_text_parts)
    verdicts = {
        "required_tools_present": all(tool in tool_calls_executed for tool in required_tools),
        "final_answer_numeric_anchors_present": all(anchor in final_text for anchor in anchors),
        "tool_oracle_matches": not tool_oracle_errors,
        "no_error_events": not error_events,
        "rounds_match_script": client.rounds_served == len(script.get("rounds", [])),
    }
    receipt.update({
        "status": "passed" if all(verdicts.values()) else "failed",
        "errors": (error_events + tool_oracle_errors)[:10],
        "rounds_used": client.rounds_served,
        "rounds_scripted": len(script.get("rounds", [])),
        "structure": client.structure,
        "tool_calls_executed": tool_calls_executed,
        "contract_verdicts": verdicts,
        "tool_oracle": {"observed": tool_oracle_observed, "errors": tool_oracle_errors},
        "data": manifest.get("data", []),
        "uploads": uploads_placed,
        "auxiliary_llm": {
            "mode": "provider_neutral",
            "provider_calls": auxiliary_client.provider_calls,
            "local_calls": auxiliary_client.local_calls,
        },
    })
    return receipt


class CountableJourneyClient:
    """Drive the real AgentLoop with exactly-countable Provider requests.

    Main loop rounds perform non-retrying requests through the injected
    ``once_client`` and climb the frozen ladder only on
    ``finish_reason=length``.  Intent, playbook, compaction, and requirement
    helpers use a separate one-shot view backed by the same counter and an
    explicit auxiliary cap.  Sync fallback is disabled for this client.
    Receipts contain hashes, rungs, outcomes, and length buckets only -- never
    Provider text.
    """

    allow_stream_sync_fallback = False

    class _AuxiliaryClient:
        def __init__(self, owner: "CountableJourneyClient"):
            self._owner = owner

        def chat(self, messages, tools=None, system=None):
            return self._owner._serve_auxiliary(messages, tools, system)

    def __init__(
        self,
        *,
        round_cap: int,
        ladder: list[int],
        once_client,
        response_format=None,
        auxiliary_max_tokens: int = 300,
        auxiliary_call_cap: int = 0,
        auxiliary_response_format=None,
    ):
        self._once = once_client
        self._round_cap = int(round_cap)
        self._ladder = [int(value) for value in ladder]
        self._response_format = response_format
        self._auxiliary_max_tokens = int(auxiliary_max_tokens)
        self._auxiliary_call_cap = int(auxiliary_call_cap)
        self._auxiliary_response_format = auxiliary_response_format
        if self._round_cap < 1:
            raise JourneyStructureError("round_cap must be a positive integer")
        if not self._ladder:
            raise JourneyStructureError("max_tokens_ladder must not be empty")
        self.calls_made = 0
        self.main_calls_made = 0
        self.auxiliary_calls_made = 0
        self.rounds_served = 0
        self._terminated = False
        self._auxiliary_failure = ""
        self.structure: list[dict] = []
        self.round_receipts: list[list[dict]] = []
        self.auxiliary_receipts: list[dict] = []
        self.on_round = None
        self.on_auxiliary_call = None
        self.auxiliary_client = self._AuxiliaryClient(self)

    def _serve(self, messages, tools, system):
        from scripts.acceptance.route_a_provider_preflight import _content_length_bucket

        # Sticky refusal: the loop's sync fallback re-invokes the client after
        # a streaming failure; a terminated journey must reject again without
        # inflating the round count or consuming another slot.
        if self._auxiliary_failure:
            raise JourneyStructureError(self._auxiliary_failure)
        if self._terminated:
            raise JourneyStructureError("round_cap_exceeded")
        if self.rounds_served >= self._round_cap:
            self._terminated = True
            raise JourneyStructureError("round_cap_exceeded")
        self.rounds_served += 1
        self.structure.append({
            "round": self.rounds_served,
            "prompt_sha256": _digest({"system": system or "", "messages": list(messages or [])}),
            "tools_count": len(tools or []),
            "tools_sha256": _digest(tools or []),
        })
        attempts: list[dict] = []
        response = None
        for index, rung in enumerate(self._ladder):
            self.calls_made += 1
            self.main_calls_made += 1
            try:
                response = self._once.chat_once(
                    messages=messages,
                    tools=tools,
                    system=system,
                    response_format=self._response_format,
                    max_tokens=rung,
                )
            except Exception as exc:
                attempts.append({
                    "max_tokens": rung,
                    "outcome": f"error:{type(exc).__name__}",
                })
                self.round_receipts.append(attempts)
                if self.on_round is not None:
                    self.on_round()
                raise
            attempts.append({
                "max_tokens": rung,
                "outcome": "response",
                "finish_reason": getattr(response, "finish_reason", None) or "",
                "response_length_bucket": _content_length_bucket(getattr(response, "text", "")),
                "response_reasoning_length_bucket": _content_length_bucket(getattr(response, "reasoning_content", "")),
            })
            # A countable round is one non-streaming request whose body is
            # published only after it completes, so ANY finish_reason=length
            # response -- empty, partial text, or truncated tool calls -- can
            # be safely discarded and re-issued with a larger budget.
            truncated = getattr(response, "finish_reason", None) == "length"
            if not truncated or index == len(self._ladder) - 1:
                break
        self.round_receipts.append(attempts)
        if self.on_round is not None:
            self.on_round()
        return response

    def _serve_auxiliary(self, messages, tools, system):
        from scripts.acceptance.route_a_provider_preflight import _content_length_bucket

        if self._auxiliary_failure:
            raise JourneyStructureError(self._auxiliary_failure)
        if self.auxiliary_calls_made >= self._auxiliary_call_cap:
            self._auxiliary_failure = "auxiliary_call_cap_exceeded"
            raise JourneyStructureError(self._auxiliary_failure)

        self.calls_made += 1
        self.auxiliary_calls_made += 1
        receipt = {
            "call": self.auxiliary_calls_made,
            "prompt_sha256": _digest({"system": system or "", "messages": list(messages or [])}),
            "tools_count": len(tools or []),
            "tools_sha256": _digest(tools or []),
            "max_tokens": self._auxiliary_max_tokens,
        }
        try:
            response = self._once.chat_once(
                messages=messages,
                tools=tools,
                system=system,
                response_format=self._auxiliary_response_format,
                max_tokens=self._auxiliary_max_tokens,
            )
        except Exception as exc:
            receipt["outcome"] = f"error:{type(exc).__name__}"
            self.auxiliary_receipts.append(receipt)
            self._auxiliary_failure = "auxiliary_provider_request_failed"
            if self.on_auxiliary_call is not None:
                self.on_auxiliary_call()
            raise

        receipt.update({
            "outcome": "response",
            "finish_reason": getattr(response, "finish_reason", None) or "",
            "response_length_bucket": _content_length_bucket(getattr(response, "text", "")),
            "response_reasoning_length_bucket": _content_length_bucket(
                getattr(response, "reasoning_content", "")
            ),
        })
        self.auxiliary_receipts.append(receipt)
        if self.on_auxiliary_call is not None:
            self.on_auxiliary_call()
        return response

    def chat(self, messages, tools=None, system=None):
        return self._serve(messages, tools, system)

    def stream_chat_structured(self, messages, tools=None, system=None):
        from data_agent.llm.client import StreamComplete, StreamTextDelta

        response = self._serve(messages, tools, system)
        if response.text:
            yield StreamTextDelta(text=response.text)
        yield StreamComplete(response=response)


def _validate_candidate_request(request: Any) -> list[str]:
    if not isinstance(request, dict):
        return ["request must be an object"]
    errors: list[str] = []
    if not str(request.get("model_id", "")).strip():
        errors.append("request.model_id is required")
    if "temperature" in request and request["temperature"] != 0.0:
        errors.append("request.temperature must be 0.0 or omitted")
    timeout = request.get("timeout_seconds")
    if not isinstance(timeout, int) or isinstance(timeout, bool) or timeout <= 0:
        errors.append("request.timeout_seconds must be a positive integer")
    ladder = request.get("max_tokens_ladder")
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
    round_cap = request.get("round_cap")
    if not isinstance(round_cap, int) or isinstance(round_cap, bool) or round_cap < 1 or round_cap > 24:
        errors.append("request.round_cap must be a positive integer")
    auxiliary = request.get("auxiliary_llm")
    if not isinstance(auxiliary, dict):
        errors.append("request.auxiliary_llm must be an object")
    else:
        if auxiliary.get("mode") != "counted_once":
            errors.append("request.auxiliary_llm.mode must be counted_once")
        auxiliary_max_tokens = auxiliary.get("max_tokens")
        if (
            not isinstance(auxiliary_max_tokens, int)
            or isinstance(auxiliary_max_tokens, bool)
            or auxiliary_max_tokens < 100
            or auxiliary_max_tokens > 2000
        ):
            errors.append("request.auxiliary_llm.max_tokens must be an integer between 100 and 2000")
        auxiliary_call_cap = auxiliary.get("call_cap")
        if (
            not isinstance(auxiliary_call_cap, int)
            or isinstance(auxiliary_call_cap, bool)
            or auxiliary_call_cap < 1
            or auxiliary_call_cap > 24
        ):
            errors.append("request.auxiliary_llm.call_cap must be an integer between 1 and 24")
        if auxiliary.get("response_format") != {"type": "json_object"}:
            errors.append('request.auxiliary_llm.response_format must be {"type":"json_object"}')
    api_base = request.get("api_base")
    api_base_env = request.get("api_base_env")
    if api_base is not None and api_base_env is not None:
        errors.append("request.api_base and api_base_env are mutually exclusive")
    for field, value in (("api_base", api_base), ("api_base_env", api_base_env), ("api_key_env", request.get("api_key_env"))):
        if value is not None and (not isinstance(value, str) or not value.strip()):
            errors.append(f"request.{field} must be a non-empty string")
    return errors


def _read_manifest_with_schema(path: Path, expected_schema: str) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise JourneyStructureError(f"invalid journey manifest: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != expected_schema:
        raise JourneyStructureError(f"manifest schema_version must be {expected_schema}")
    return payload


def _acceptance_mode(contract: dict[str, Any]) -> str:
    """Return the frozen result contract, preserving publication as default.

    A routing journey measures tool reachability and execution integrity; it
    must not silently be interpreted as a publication-quality answer check.
    """
    value = contract.get("acceptance_mode", _PUBLICATION_ACCEPTANCE)
    return value.strip() if isinstance(value, str) else ""


def journey_preflight(
    manifest_path: Path,
    *,
    source_digest: Callable[[Path], str] = release_source_digest,
) -> dict[str, Any]:
    """Validate a countable journey candidate without contacting any Provider."""
    try:
        manifest = _read_manifest_with_schema(Path(manifest_path), JOURNEY_CANDIDATE_SCHEMA)
    except JourneyStructureError as exc:
        return {
            "schema_version": _EXECUTE_REPORT_SCHEMA,
            "mode": "preflight",
            "journey_id": "",
            "status": "failed",
            "errors": [str(exc)],
            "source_digest": source_digest(ROOT),
            "provider_calls": 0,
            "ready": False,
        }
    errors: list[str] = list(validate_reference_data())
    reference_hashes = {item.id: item.sha256 for item in REFERENCE_DATA.files}
    data_entries: list[dict] = []
    for item in manifest.get("data", []):
        expected = reference_hashes.get(item.get("id"))
        if expected is None:
            errors.append(f"unknown reference data id: {item.get('id')}")
        elif item.get("sha256") != expected:
            errors.append(f"data hash mismatch for {item.get('id')}")
        data_entries.append({"id": item.get("id", ""), "sha256": f"sha256:{expected}"} if expected else dict(item))
    session_id = str(manifest.get("session_id", ""))
    if not session_id.startswith(_SESSION_PREFIX):
        errors.append(f"session_id must be dedicated to journeys (prefix {_SESSION_PREFIX})")
    if not str(manifest.get("question", "")).strip():
        errors.append("question is required")
    errors.extend(_validate_candidate_request(manifest.get("request")))
    contract = manifest.get("contract")
    if not isinstance(contract, dict):
        errors.append("contract must be an object")
    else:
        acceptance_mode = _acceptance_mode(contract)
        if acceptance_mode not in _ACCEPTANCE_MODES:
            errors.append("contract.acceptance_mode must be publication or routing_integrity")
        if not all(isinstance(item, str) for item in contract.get("required_tool_calls", [])):
            errors.append("contract.required_tool_calls must be a string list")
        required_tools = contract.get("required_tool_calls", [])
        if acceptance_mode == _ROUTING_INTEGRITY_ACCEPTANCE and not required_tools:
            errors.append("routing_integrity requires at least one required_tool_call")
        anchors = contract.get("final_answer_numeric_anchors", [])
        if acceptance_mode == _PUBLICATION_ACCEPTANCE:
            if not isinstance(anchors, list) or not anchors or not all(str(item).strip() for item in anchors):
                errors.append("publication requires non-empty final_answer_numeric_anchors")
        elif anchors != []:
            errors.append("routing_integrity requires final_answer_numeric_anchors to be []")
        oracle_replay = contract.get("tool_oracle_replay")
        if oracle_replay is not None:
            if not isinstance(oracle_replay, dict):
                errors.append("contract.tool_oracle_replay must be an object")
            else:
                replay_path = _resolve_oracle_replay(oracle_replay.get("manifest"))
                expected_digest = oracle_replay.get("sha256")
                if replay_path is None or not replay_path.is_file():
                    errors.append("contract.tool_oracle_replay.manifest must name a tracked replay manifest")
                elif not isinstance(expected_digest, str) or expected_digest != _file_digest(replay_path):
                    errors.append("contract.tool_oracle_replay.sha256 does not match replay manifest")
                else:
                    replay = run_journey_replay(replay_path, source_digest=source_digest)
                    if replay.get("status") != "passed":
                        errors.append("contract.tool_oracle_replay did not pass: " + "; ".join(replay.get("errors", [])[:3]))
    from data_agent.config import get_config

    from scripts.acceptance.route_a_provider_preflight import _env_or_dotenv

    request = manifest.get("request") or {}
    for env_field in ("api_base_env", "api_key_env"):
        if request.get(env_field) and _env_or_dotenv(request[env_field]) is None:
            errors.append(f"environment variable {request[env_field]} is not set")
    ladder = request.get("max_tokens_ladder") if isinstance(request.get("max_tokens_ladder"), list) else []
    round_cap = request.get("round_cap") if isinstance(request.get("round_cap"), int) else 0
    auxiliary = request.get("auxiliary_llm") if isinstance(request.get("auxiliary_llm"), dict) else {}
    auxiliary_call_cap = auxiliary.get("call_cap") if isinstance(auxiliary.get("call_cap"), int) else 0
    for item in manifest.get("uploads", []) or []:
        if not isinstance(item, dict) or not str(item.get("data_id", "")).strip() or not str(item.get("as", "") or "").strip():
            errors.append("uploads entries need non-empty data_id and as")
    # Finalization can need two no-tools rounds: the first direct answer and
    # one bounded correction when a reasoning model emits tool markup as text.
    # The cap must reserve both after the wrap-up threshold.
    wrap_up = get_config().wrap_up_round
    if wrap_up and round_cap and round_cap < wrap_up + 2:
        errors.append(
            f"round_cap must leave two finalization rounds after the active wrap_up_round ({wrap_up})"
        )
    return {
        "schema_version": _EXECUTE_REPORT_SCHEMA,
        "mode": "preflight",
        "ready": not errors,
        "errors": errors,
        "source_digest": source_digest(ROOT),
        "provider_calls": 0,
        "journey_id": manifest.get("journey_id", ""),
        "model_id": str(request.get("model_id", "")),
        "request": request,
        "data": data_entries,
        "main_max_call_budget": (round_cap * len(ladder)) if ladder and round_cap else 0,
        "auxiliary_max_call_budget": auxiliary_call_cap,
        "max_call_budget": (
            (round_cap * len(ladder) if ladder and round_cap else 0)
            + auxiliary_call_cap
        ),
    }


def _evaluate_contract(
    contract: dict[str, Any],
    *,
    tool_calls_executed: list[str],
    final_text: str,
    error_events: list[str],
    rounds_used: int,
    round_cap: int,
) -> tuple[str, dict[str, Any]]:
    """Evaluate a frozen journey contract without interpreting model prose."""
    acceptance_mode = _acceptance_mode(contract)
    required_tools = [str(item) for item in contract.get("required_tool_calls", [])]
    anchors = [str(item) for item in contract.get("final_answer_numeric_anchors", [])]
    verdicts = {
        "acceptance_mode": acceptance_mode,
        "required_tools_present": all(tool in tool_calls_executed for tool in required_tools),
        "final_answer_numeric_anchors_present": (
            all(anchor in final_text for anchor in anchors)
            if acceptance_mode == _PUBLICATION_ACCEPTANCE
            else "not_required"
        ),
        "no_error_events": not error_events,
        "rounds_within_cap": rounds_used <= round_cap,
    }
    required_verdicts = [
        verdicts["required_tools_present"],
        verdicts["no_error_events"],
        verdicts["rounds_within_cap"],
    ]
    if acceptance_mode == _PUBLICATION_ACCEPTANCE:
        required_verdicts.append(verdicts["final_answer_numeric_anchors_present"])
    return ("passed" if all(required_verdicts) else "failed"), verdicts


def execute_authorized_journey(
    manifest_path: Path,
    *,
    authorized_source_digest: str,
    once_client=None,
    report_path: Path | None = None,
    source_digest: Callable[[Path], str] = release_source_digest,
) -> dict[str, Any]:
    """Run one authorized journey with exactly-countable Provider requests."""
    from data_agent.tools import discover_tools

    discover_tools()
    preflight = journey_preflight(manifest_path, source_digest=source_digest)
    if not preflight["ready"]:
        preflight.update({"mode": "executed", "status": "failed"})
        return preflight
    if authorized_source_digest != preflight["source_digest"]:
        preflight.update({
            "mode": "executed",
            "status": "failed",
            "errors": ["authorized source digest does not match current source"],
        })
        return preflight

    manifest = _read_manifest_with_schema(Path(manifest_path), JOURNEY_CANDIDATE_SCHEMA)
    request = manifest["request"]
    if once_client is None:
        from data_agent.llm.client import LLMClient

        from scripts.acceptance.route_a_provider_preflight import _env_or_dotenv

        api_base = request.get("api_base")
        if api_base is None and request.get("api_base_env"):
            api_base = _env_or_dotenv(request["api_base_env"])
        once_client = LLMClient(
            model_id=request["model_id"],
            temperature=request.get("temperature"),
            timeout=request["timeout_seconds"],
            api_base=api_base,
            api_key=_env_or_dotenv(request["api_key_env"]) if request.get("api_key_env") else None,
        )

    from data_agent.config import get_config

    session_dir = get_config().sessions_resolved / manifest["session_id"]
    if session_dir.exists():
        shutil.rmtree(session_dir)

    uploads_placed, upload_errors = _perform_uploads(manifest.get("uploads", []))
    if upload_errors:
        preflight.update({"mode": "executed", "status": "failed", "errors": upload_errors})
        return preflight

    auxiliary_request = request["auxiliary_llm"]
    client = CountableJourneyClient(
        round_cap=request["round_cap"],
        ladder=request["max_tokens_ladder"],
        once_client=once_client,
        auxiliary_max_tokens=auxiliary_request["max_tokens"],
        auxiliary_call_cap=auxiliary_request["call_cap"],
        auxiliary_response_format=auxiliary_request["response_format"],
    )

    def current_receipt(status: str, error_messages: list[str], verdicts=None) -> dict[str, Any]:
        return {
            **{key: value for key, value in preflight.items() if key not in {"ready", "errors"}},
            "mode": "executed",
            "status": status,
            "errors": error_messages[:10],
            "provider_calls": client.calls_made,
            "main_provider_calls": client.main_calls_made,
            "auxiliary_provider_calls": client.auxiliary_calls_made,
            "rounds_used": client.rounds_served,
            "round_cap": request["round_cap"],
            "structure": client.structure,
            "round_receipts": client.round_receipts,
            "auxiliary_receipts": client.auxiliary_receipts,
            "tool_calls_executed": tool_calls_executed,
            "contract_verdicts": verdicts or {},
            "uploads": uploads_placed,
            "in_flight_journey": True,
        }

    def persist(status: str, error_messages: list[str], verdicts=None, final: bool = True) -> dict[str, Any]:
        receipt = current_receipt(status, error_messages, verdicts)
        if final:
            receipt.pop("in_flight_journey", None)
        if report_path is not None:
            from scripts.acceptance.route_a_provider_preflight import write_execution_report

            write_execution_report(Path(report_path), receipt)
        return receipt

    tool_calls_executed: list[str] = []
    error_events: list[str] = []
    final_text_parts: list[str] = []

    from data_agent.agent.loop import AgentLoop

    loop = AgentLoop(
        client=client,
        auxiliary_llm_client=client.auxiliary_client,
        session_id=manifest["session_id"],
    )
    if report_path is not None:
        persist("in_progress", [])
    client.on_round = lambda: persist("in_progress", [])
    client.on_auxiliary_call = lambda: persist("in_progress", [])
    try:
        for event in loop.stream_turn(str(manifest["question"])):
            kind = event.get("type")
            if kind == "text_delta":
                final_text_parts.append(str(event.get("text", "")))
            elif kind == "tool_call":
                tool_calls_executed.append(str(event.get("name", "")))
            elif kind == "error":
                error_events.append(str(event.get("message", "")))
    except JourneyStructureError as exc:
        return persist("failed", [f"structure: {exc}"])
    except Exception as exc:  # a failed request still consumed its slot
        return persist("failed", [f"provider_request: {type(exc).__name__}"])

    status, verdicts = _evaluate_contract(
        manifest.get("contract", {}),
        tool_calls_executed=tool_calls_executed,
        final_text="".join(final_text_parts),
        error_events=error_events,
        rounds_used=client.rounds_served,
        round_cap=request["round_cap"],
    )
    return persist(status, error_events, verdicts)
