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
_REPORT_SCHEMA = "route_a_journey_replay_report.v1"
_SESSION_PREFIX = "gate_c_journey_replay"


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
        errors.append("session_id must be dedicated to replay (prefix gate_c_journey_replay)")
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
