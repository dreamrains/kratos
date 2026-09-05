# scripts/acceptance/extract_replay_shapes.py
"""Extract sanitized real-model shapes from closed batch sessions.

Offline replay aims to stop each real batch discovering a new contract
layer: recorded tool-result shapes must pass evidence projection before
any new real batch is authorized.
"""
from __future__ import annotations

import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_SOURCES = ("tmp/real-provider-browser-matrix-a05r2-diag", "tmp/real-provider-browser-matrix-a04-diag")
_TARGET = _ROOT / "tests/replay/fixtures"
_TRUNCATE = 200


def _sanitize(value):
    if isinstance(value, str):
        return value[:_TRUNCATE]
    if isinstance(value, dict):
        return {key: _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value[:50]]
    return value


def _messages(conversation: Path) -> list[dict]:
    """Read rotated conversation.json arrays or active conversation.jsonl."""
    text = conversation.read_text(encoding="utf-8")
    if text.lstrip().startswith("["):
        payload = json.loads(text)
        return payload if isinstance(payload, list) else []
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _tool_names(messages: list[dict]) -> dict:
    """Map tool_call_id to function name; tool messages carry no name key."""
    names: dict = {}
    for message in messages:
        if message.get("role") != "assistant":
            continue
        for call in message.get("tool_calls") or []:
            names[call.get("id")] = (call.get("function") or {}).get("name")
    return names


def _receipt_names(session_dir: Path) -> dict:
    """Map tool_outputs detail filenames to tool names via session receipts."""
    state_file = session_dir / "analysis_state.json"
    if not state_file.is_file():
        return {}
    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    from data_agent.tools._utils import sanitize_filename
    names = {}
    for receipt in state.get("tool_receipts") or []:
        call_id = str(receipt.get("tool_call_id") or "")
        tool = receipt.get("tool_name")
        if call_id and tool:
            names[sanitize_filename(call_id) + "_detail.json"] = tool
    return names


def _detail_turns(sessions_dir: Path) -> list[dict]:
    """Harvest tool_outputs detail payloads, the shapes load_result_reference serves.

    These carry the structured results (analysis methods, sandbox outputs,
    error shapes such as sandbox/chart_validation failures) that evidence
    projection actually consumes; conversation messages only page at them.
    """
    turns = []
    for session_dir in sorted(path for path in sessions_dir.glob("*/") if path.is_dir()):
        receipts = _receipt_names(session_dir)
        calls: dict = {}
        for conversation in sorted(session_dir.glob("conversation.json*")):
            try:
                calls.update(_tool_names(_messages(conversation)))
            except json.JSONDecodeError:
                continue
        for detail in sorted((session_dir / "tool_outputs").glob("*_detail.json")):
            try:
                payload = json.loads(detail.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            stem = detail.name[: -len("_detail.json")]
            stems = [stem, stem[: -len("_summary")]] if stem.endswith("_summary") else [stem]
            tool = None
            for candidate in stems:
                tool = receipts.get(candidate + "_detail.json") or calls.get(candidate)
                if tool:
                    break
            turns.append({"tool": tool or "structured_detail",
                          "structured_result": _sanitize(payload)})
    return turns


def extract() -> int:
    written = 0
    for source in _SOURCES:
        base = _ROOT / source
        if not base.is_dir():
            continue
        for case_dir in sorted(base.glob("M0*")):
            turns = []
            for conversation in sorted((case_dir / "sessions").glob("*/conversation.json*")):
                messages = _messages(conversation)
                names = _tool_names(messages)
                for message in messages:
                    if message.get("role") != "tool":
                        continue
                    # JSON tool content is recorded as-is: this also captures
                    # error shapes (error/error_type keys) bound through the
                    # projection path instead of being skipped as prose.
                    try:
                        payload = json.loads(message.get("content") or "{}")
                    except json.JSONDecodeError:
                        continue
                    turns.append({"tool": message.get("name") or names.get(message.get("tool_call_id")) or "unknown",
                                  "structured_result": _sanitize(payload)})
            turns.extend(_detail_turns(case_dir / "sessions"))
            if not turns:
                continue
            target = _TARGET / f"{base.name}_{case_dir.name}.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(
                {"case": case_dir.name, "batch": base.name, "turns": turns},
                ensure_ascii=False, indent=1), encoding="utf-8")
            written += 1
    return written


if __name__ == "__main__":
    print(json.dumps({"fixtures_written": extract()}))
