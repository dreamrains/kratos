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
                    try:
                        payload = json.loads(message.get("content") or "{}")
                    except json.JSONDecodeError:
                        continue
                    turns.append({"tool": message.get("name") or names.get(message.get("tool_call_id")) or "unknown",
                                  "structured_result": _sanitize(payload)})
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
