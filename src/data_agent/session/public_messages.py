"""Public conversation projection; the provider history remains unchanged."""
from __future__ import annotations

import re
import hashlib
import json
import uuid


_ACK_CONTENT = "好的，继续。"
_COMPACTED_MARKER = "[Context compressed at turn boundary"


def _is_compaction_ack(messages: list[dict], index: int) -> bool:
    """The synthetic compaction ACK adjacent to the compressed-context marker.

    compact_history inserts this assistant message right after the compressed
    user message.  It is machinery, not an assistant statement: left in the
    grouping it steals the reply-group identity (a fresh uuid propagated over
    the surviving messages' persisted ids) and prepends itself to the grouped
    content, so a client holding the pre-compaction turn identity can no
    longer match its reply (P1-6 item 4, real M03 export failures).
    """
    message = messages[index]
    if message.get("role") != "assistant":
        return False
    if str(message.get("content") or "").strip() != _ACK_CONTENT:
        return False
    if index == 0:
        return False
    previous = messages[index - 1]
    return (
        previous.get("role") == "user"
        and str(previous.get("content") or "").lstrip().startswith(_COMPACTED_MARKER)
    )


def drop_compaction_acks(messages: list[dict]) -> list[dict]:
    """Return the message list without the synthetic compaction ACK entries."""
    return [
        message for index, message in enumerate(messages)
        if not _is_compaction_ack(messages, index)
    ]


def assign_reply_ids(messages: list[dict]) -> None:
    """Persist one server-owned identity per assistant reply across tool steps."""
    current = None
    for index, message in enumerate(messages):
        if _is_compaction_ack(messages, index):
            continue
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
        if _is_compaction_ack(messages, index):
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
            # A reply may contain intermediate assistant messages followed by
            # one accepted terminal message.  Keep the server-owned terminal
            # publication binding with the grouped reply; exports must never
            # guess it from the latest packet in the session.
            for key in (
                "publication_packet_id", "publication_snapshot_digest",
                "answer_sha256", "publication_artifact_path",
            ):
                value = message.get(key)
                if isinstance(value, str) and value:
                    current[key] = value
        elif role == "tool" and current is not None and isinstance(content, str):
            current["chart_paths"].extend(re.findall(r"Chart saved:\s*(sessions/\S+\.html)", content))
    return replies
