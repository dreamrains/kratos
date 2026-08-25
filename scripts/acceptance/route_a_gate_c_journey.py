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


class JourneyStructureError(ValueError):
    """The real loop demanded a structure the frozen script does not cover."""


def _digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


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

    script = manifest.get("script", {})
    client = ScriptedJourneyClient(script.get("rounds", []), script.get("round_cap"))

    from data_agent.agent.loop import AgentLoop

    loop = AgentLoop(client=client, session_id=session_id)
    tool_calls_executed: list[str] = []
    error_events: list[str] = []
    final_text_parts: list[str] = []
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
    final_text = "".join(final_text_parts)
    verdicts = {
        "required_tools_present": all(tool in tool_calls_executed for tool in required_tools),
        "final_answer_numeric_anchors_present": all(anchor in final_text for anchor in anchors),
        "no_error_events": not error_events,
        "rounds_match_script": client.rounds_served == len(script.get("rounds", [])),
    }
    receipt.update({
        "status": "passed" if all(verdicts.values()) else "failed",
        "errors": error_events[:10],
        "rounds_used": client.rounds_served,
        "rounds_scripted": len(script.get("rounds", [])),
        "structure": client.structure,
        "tool_calls_executed": tool_calls_executed,
        "contract_verdicts": verdicts,
        "data": manifest.get("data", []),
    })
    return receipt


class CountableJourneyClient:
    """Drive the real AgentLoop with exactly-countable Provider requests.

    Each loop round performs single non-retrying requests through the
    injected ``once_client`` (``chat_once`` semantics: no retry, no fallback,
    no client-side escalation).  A round climbs the frozen per-round budget
    ladder only on the silent truncation shape (``finish_reason=length``
    with zero visible text) and stops at the first non-truncated response.
    Every request is counted; per-round receipts carry rung, finish reason
    and length buckets only -- never Provider text.
    """

    def __init__(self, *, round_cap: int, ladder: list[int], once_client, response_format=None):
        self._once = once_client
        self._round_cap = int(round_cap)
        self._ladder = [int(value) for value in ladder]
        self._response_format = response_format
        if self._round_cap < 1:
            raise JourneyStructureError("round_cap must be a positive integer")
        if not self._ladder:
            raise JourneyStructureError("max_tokens_ladder must not be empty")
        self.calls_made = 0
        self.rounds_served = 0
        self._terminated = False
        self.structure: list[dict] = []
        self.round_receipts: list[list[dict]] = []
        self.on_round = None

    def _serve(self, messages, tools, system):
        from scripts.acceptance.route_a_provider_preflight import _content_length_bucket

        # Sticky refusal: the loop's sync fallback re-invokes the client after
        # a streaming failure; a terminated journey must reject again without
        # inflating the round count or consuming another slot.
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
            response = self._once.chat_once(
                messages=messages,
                tools=tools,
                system=system,
                response_format=self._response_format,
                max_tokens=rung,
            )
            attempts.append({
                "max_tokens": rung,
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
        if not all(isinstance(item, str) for item in contract.get("required_tool_calls", [])):
            errors.append("contract.required_tool_calls must be a string list")
        anchors = contract.get("final_answer_numeric_anchors", [])
        if not isinstance(anchors, list) or not anchors or not all(str(item).strip() for item in anchors):
            errors.append("contract.final_answer_numeric_anchors must be a non-empty list")
    from data_agent.config import get_config

    from scripts.acceptance.route_a_provider_preflight import _env_or_dotenv

    request = manifest.get("request") or {}
    for env_field in ("api_base_env", "api_key_env"):
        if request.get(env_field) and _env_or_dotenv(request[env_field]) is None:
            errors.append(f"environment variable {request[env_field]} is not set")
    ladder = request.get("max_tokens_ladder") if isinstance(request.get("max_tokens_ladder"), list) else []
    round_cap = request.get("round_cap") if isinstance(request.get("round_cap"), int) else 0
    for item in manifest.get("uploads", []) or []:
        if not isinstance(item, dict) or not str(item.get("data_id", "")).strip() or not str(item.get("as", "") or "").strip():
            errors.append("uploads entries need non-empty data_id and as")
    # Structural trap observed on the R09 run: with round_cap equal to the
    # wrap-up threshold, the nudge arrives for a round the cap already refuses.
    wrap_up = get_config().wrap_up_round
    if wrap_up and round_cap and round_cap <= wrap_up:
        errors.append(
            f"round_cap must exceed the active wrap_up_round ({wrap_up}) so the wrap-up nudge gets at least one round"
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
        "max_call_budget": (round_cap * len(ladder)) if ladder and round_cap else 0,
    }


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

    client = CountableJourneyClient(
        round_cap=request["round_cap"],
        ladder=request["max_tokens_ladder"],
        once_client=once_client,
    )

    def current_receipt(status: str, error_messages: list[str], verdicts=None) -> dict[str, Any]:
        return {
            **{key: value for key, value in preflight.items() if key not in {"ready", "errors"}},
            "mode": "executed",
            "status": status,
            "errors": error_messages[:10],
            "provider_calls": client.calls_made,
            "rounds_used": client.rounds_served,
            "round_cap": request["round_cap"],
            "structure": client.structure,
            "round_receipts": client.round_receipts,
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

    loop = AgentLoop(client=client, session_id=manifest["session_id"])
    if report_path is not None:
        persist("in_progress", [])
    client.on_round = lambda: persist("in_progress", [])
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

    contract = manifest.get("contract", {})
    required_tools = [str(item) for item in contract.get("required_tool_calls", [])]
    anchors = [str(item) for item in contract.get("final_answer_numeric_anchors", [])]
    final_text = "".join(final_text_parts)
    verdicts = {
        "required_tools_present": all(tool in tool_calls_executed for tool in required_tools),
        "final_answer_numeric_anchors_present": all(anchor in final_text for anchor in anchors),
        "no_error_events": not error_events,
        "rounds_within_cap": client.rounds_served <= request["round_cap"],
    }
    status = "passed" if all(verdicts.values()) else "failed"
    return persist(status, error_events, verdicts)
