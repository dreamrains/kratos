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
            if message.get("answer_ref"):
                current = None


def _expanded_public_history(messages: list[dict], session_id: str, visited=None) -> list[dict]:
    """Restore display history, never use the generated context summary as a reply."""
    from data_agent.session.history import read_canonical_prefix
    visited = set() if visited is None else visited
    for index, message in enumerate(messages):
        reference = message.get("canonical_transcript")
        if not reference:
            continue
        try:
            identity = (reference["filename"], reference["sha256"])
            if identity in visited or len(visited) >= 32:
                raise ValueError("Canonical transcript cycle or budget exceeded")
            visited.add(identity)
            archived = read_canonical_prefix(session_id, reference, message)
            inherited = message.get("inherited_from")
            if inherited:
                archived = [dict(item) for item in archived]
                for item in archived:
                    item.setdefault("inherited_from", inherited)
                    if item.get("answer_ref"):
                        item["inherited_answer_ref"] = dict(item.pop("answer_ref"), session_id=inherited)
                        for key in ("answer_id", "answer_sha256"):
                            item.pop(key, None)
            start = index + 2 if index + 1 < len(messages) and _is_compaction_ack(messages, index + 1) else index + 1
            recent = messages[start:]
            return messages[:index] + _expanded_public_history(archived, session_id, visited) + _expanded_public_history(recent, session_id, visited)
        except (ValueError, OSError, KeyError, TypeError, UnicodeError):
            start = index + 2 if index + 1 < len(messages) and _is_compaction_ack(messages, index + 1) else index + 1
            return messages[:index] + [{"role": "assistant", "content": "历史归档不可核，原答案暂不可展示。"}] + messages[start:]
    return messages


def public_messages(messages: list[dict], session_id: str = "") -> list[dict]:
    messages = _expanded_public_history(messages, session_id) if session_id else messages
    projected = []
    current_reply = None
    accepted_replies = set()
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
            stored_reply = item.get("reply_id")
            if item.get("answer_ref") and stored_reply:
                current_reply = stored_reply
            else:
                current_reply = current_reply or (stored_reply if stored_reply not in accepted_replies else None) or "legacy_" + hashlib.sha256(anchor.encode()).hexdigest()
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
        if item.get("role") == "assistant" and item.get("answer_ref"):
            accepted_replies.add(item["reply_id"])
            current_reply = None
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
            if current is None or current["reply_id"] != message["reply_id"]:
                current = {"content": "", "chart_paths": [], "reply_id": message["reply_id"]}
                replies.append(current)
            if isinstance(content, str) and content.strip():
                current["content"] = "\n\n".join(filter(None, [current["content"], content.strip()]))
            # A reply may contain intermediate assistant messages followed by
            # one accepted terminal message.  Keep the server-owned terminal
            # publication binding with the grouped reply; exports must never
            # guess it from the latest packet in the session.
            if message.get("answer_ref"):
                current["answer_id"] = message["answer_id"]
                current["answer_ref"] = dict(message["answer_ref"])
                current["answer_sha256"] = message["answer_sha256"]
                # One accepted terminal body owns the export, never pre-tool prose.
                current["content"] = message["content"]
        elif role == "tool" and current is not None and isinstance(content, str):
            current["chart_paths"].extend(re.findall(r"Chart saved:\s*(sessions/\S+\.html)", content))
    return replies
