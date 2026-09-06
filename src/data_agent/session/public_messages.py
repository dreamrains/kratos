"""Public conversation projection; the provider history remains unchanged."""
from __future__ import annotations

import re
import hashlib
import json
import uuid


def assign_reply_ids(messages: list[dict]) -> None:
    """Persist one server-owned identity per assistant reply across tool steps."""
    current = None
    for message in messages:
        if message.get("role") == "user":
            current = None
        elif message.get("role") == "assistant":
            current = current or message.get("reply_id") or "reply_" + uuid.uuid4().hex
            message["reply_id"] = current


def public_messages(messages: list[dict], session_id: str = "") -> list[dict]:
    projected = []
    current_reply = None
    for index, message in enumerate(messages):
        item = dict(message)
        if item.get("publication_rejected") is True:
            continue
        if item.get("role") == "user":
            current_reply = None
        elif item.get("role") == "assistant":
            # Read-only compatibility for old sessions; no migration writes.
            anchor = json.dumps([session_id, index, messages[:index + 1]], sort_keys=True, ensure_ascii=False, default=str)
            current_reply = current_reply or item.get("reply_id") or "legacy_" + hashlib.sha256(anchor.encode()).hexdigest()
            item["reply_id"] = current_reply
        content = item.get("content")
        if item.get("role") == "user" and isinstance(content, str):
            value = content.strip()
            if value.startswith("<confirmation_response ") and value.endswith("</confirmation_response>"):
                marker = "\nUser answered:"
                start, end = value.rfind(marker), value.rfind("\n</confirmation_response>")
                if start >= 0 and end > start:
                    item["content"] = value[start + len(marker):end].strip() or "已确认"
                    item["is_confirmation_response"] = True
        projected.append(item)
    return projected


def assistant_replies(messages: list[dict], session_id: str = "") -> list[dict]:
    """Match the UI's assistant grouping across tool messages in each user turn."""
    replies = []
    current = None
    for message in public_messages(messages, session_id):
        role, content = message.get("role"), message.get("content", "")
        if role == "user":
            current = None
        elif role == "assistant":
            if current is None:
                current = {"content": "", "chart_paths": [], "reply_id": message["reply_id"]}
                replies.append(current)
            if isinstance(content, str) and content.strip():
                current["content"] = "\n\n".join(filter(None, [current["content"], content.strip()]))
        elif role == "tool" and current is not None and isinstance(content, str):
            current["chart_paths"].extend(re.findall(r"Chart saved:\s*(sessions/\S+\.html)", content))
    return replies
