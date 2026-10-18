"""Session CRUD, rewind, and export endpoints."""

from __future__ import annotations

import json
from pathlib import Path

from flask import Blueprint, Response, current_app, jsonify, request, send_file

from data_agent.session.history import (
    CanonicalHistoryConflict,
    delete_artifact,
    list_artifacts,
    list_sessions,
    load_session,
    load_canonical_history,
    save_session,
    delete_session,
    _session_dir,
)

sessions_bp = Blueprint("sessions", __name__)


@sessions_bp.get("/sessions")
def get_sessions():
    object_name = request.args.get("object_name", "")
    project_name = request.args.get("project_name", "")
    return jsonify(list_sessions(object_name=object_name, project_name=project_name))


@sessions_bp.get("/sessions/<session_id>")
def get_session(session_id: str):
    data = load_session(session_id)
    if not data:
        return jsonify({"error": "Session not found"}), 404

    from data_agent.agent.publication.runtime import is_read_only_session
    data["read_only"] = is_read_only_session(data)

    from data_agent.config import get_config
    from data_agent.llm.request_policy import request_budget_status
    cfg = get_config()
    manager = current_app.config["agent_manager"]
    loop = manager.get(session_id)
    data["token_usage"] = request_budget_status(cfg, loop.messages if loop else data.get("messages", []),
                    getattr(loop,"_request_budget_estimate",None) if loop else None)

    from data_agent.agent.confirmation.runtime import (
        build_action_registry,
        confirmation_session_state,
    )
    from data_agent.agent.confirmation.service import ConfirmationService

    service = ConfirmationService(
        cfg.sessions_resolved,
        action_registry=build_action_registry(),
    )
    if data["read_only"]:
        # Preserve old event/snapshot bytes; no resumable card in another protocol.
        data.update(active_confirmation=None, queued_confirmation_count=0, failed_confirmation_count=0)
    else:
        data.update(confirmation_session_state(service, session_id))
    runs = getattr(current_app.config["agent_manager"], "runs", None)
    data["run_state"] = runs.snapshot(session_id) if runs is not None else {}
    from data_agent.session.public_messages import public_messages
    data["messages"] = public_messages(data.get("messages", []), session_id)

    return jsonify(data)


@sessions_bp.post("/sessions/<session_id>/export-reply")
def export_reply(session_id: str):
    """Export only a persisted assistant reply and its own validated charts."""
    from data_agent.tools.report import export_assistant_reply
    body = request.get_json(force=True)
    result = export_assistant_reply(session_id, body.get("content"), body.get("format", "markdown"), reply_id=body.get("reply_id", ""))
    return jsonify(result), (400 if result.get("error") else 200)


@sessions_bp.get("/sessions/<session_id>/run-state")
def get_run_state(session_id):
    runs = getattr(current_app.config["agent_manager"], "runs", None)
    return jsonify(runs.snapshot(session_id) if runs is not None else {})


@sessions_bp.delete("/sessions/<session_id>")
def remove_session(session_id: str):
    ok = delete_session(session_id)
    manager = current_app.config["agent_manager"]
    manager.remove(session_id)
    return jsonify({"deleted": ok})


# ── Rewind ──────────────────────────────────────────────────


def _get_rounds(messages: list[dict]) -> list[dict]:
    """Group messages into conversation rounds for rewind UI."""
    rounds = []
    current = []
    for msg in messages:
        if msg.get("role") == "user" and current:
            rounds.append(current)
            current = [msg]
        else:
            current.append(msg)
    if current:
        rounds.append(current)
    return rounds


@sessions_bp.get("/sessions/<session_id>/rewind-info")
def rewind_info(session_id: str):
    """Return conversation rounds for rewind UI."""
    manager = current_app.config["agent_manager"]
    loop = manager.get(session_id)

    # Try in-memory loop first, fall back to persisted session
    if loop and loop.messages:
        messages = loop.messages
    else:
        data = load_session(session_id)
        if not data:
            return jsonify({"error": "Session not found"}), 404
        messages = data.get("messages", [])

    rounds = _get_rounds(messages)
    result = []
    for i, rnd in enumerate(rounds):
        user_text = ""
        assistant_summary = ""
        for msg in rnd:
            role = msg.get("role", "")
            if role == "user":
                content = msg.get("content", "")
                user_text = content[:100] if isinstance(content, str) else "(non-text)"
            elif role == "assistant" and not assistant_summary:
                content = msg.get("content", "")
                if isinstance(content, str) and content.strip():
                    assistant_summary = content[:80]

        result.append({
            "round": i + 1,
            "message_count": len(rnd),
            "user_text": user_text,
            "assistant_summary": assistant_summary,
        })

    return jsonify({"rounds": result, "total_messages": len(messages)})


@sessions_bp.post("/sessions/<session_id>/rewind")
def rewind_session(session_id: str):
    """Rewind session to the state before a specific round.

    Removes the selected round and all subsequent rounds, returning
    the user message from that round so the caller can populate an
    input for re-editing (ChatGPT/Claude style).
    """
    data = request.get_json(force=True)
    round_num = data.get("round")

    if not round_num or round_num < 1:
        return jsonify({"error": "Invalid round number"}), 400

    manager = current_app.config["agent_manager"]
    loop = manager.get(session_id)

    # Rewind is an explicit truncation, but its input is still the canonical
    # persisted snapshot rather than a potentially stale manager cache.
    snapshot = load_canonical_history(session_id)
    if snapshot.message_count == 0:
        return jsonify({"error": "Session not found"}), 404
    messages = snapshot.messages

    rounds = _get_rounds(messages)
    if round_num > len(rounds):
        return jsonify({"error": f"Round {round_num} exceeds total rounds ({len(rounds)})"}), 400

    # Extract user message from the target round for re-editing
    target_round = rounds[round_num - 1]
    user_message_text = ""
    for msg in target_round:
        if msg.get("role") == "user":
            content = msg.get("content", "")
            user_message_text = content if isinstance(content, str) else ""
            break

    # Keep everything BEFORE the selected round
    messages_to_keep = sum(len(r) for r in rounds[: round_num - 1])
    removed = len(messages) - messages_to_keep

    if removed == 0 and round_num == 1:
        # Special case: rewinding round 1 with no prior messages
        pass
    elif removed == 0:
        return jsonify({"message": "Already at the latest state", "removed": 0})

    # Save snapshot for undo
    from datetime import datetime
    snapshots_dir = _session_dir(session_id) / "rewind_snapshots"
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    snapshot_path = snapshots_dir / f"rewind_{ts}.json"
    snapshot_path.write_text(
        json.dumps({"messages": messages, "rewound_at": ts}, default=str, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    truncated = messages[:messages_to_keep]

    # Persist the authorized truncation only if no new message arrived after
    # the rewind view was computed.
    try:
        save_session(
            truncated,
            session_id,
            merge_protect=False,
            expected_history_revision=snapshot.revision,
            expected_history_sha256=snapshot.sha256,
        )
    except CanonicalHistoryConflict:
        return jsonify({
            "error": "canonical_history_conflict",
            "message": "回退期间会话已有新消息，已保留最新历史。",
        }), 409

    written = load_canonical_history(session_id)
    if loop is not None:
        loop.messages = written.messages
        loop._last_jsonl_idx = len(written.messages)
        loop.invalidate_prompt_cache()

    return jsonify({
        "message": f"Rewound to before round {round_num}, removed {removed} messages",
        "removed": removed,
        "round": round_num,
        "user_message": user_message_text,
        "history_revision": written.revision,
    })


# ── Export ──────────────────────────────────────────────────


@sessions_bp.get("/sessions/<session_id>/export")
def export_session(session_id: str):
    """Export session analysis results as HTML or Markdown file."""
    from data_agent.agent.context import AgentContext, use_agent_context
    from data_agent.session.workspace import Workspace
    from data_agent.tools.report import export_conversation
    fmt = request.args.get("format", "html").lower()
    if not load_session(session_id):
        return jsonify({"error":"Session not found"}), 404
    with use_agent_context(AgentContext(session_id=session_id, workspace=Workspace())):
        result = json.loads(export_conversation(format=fmt))
    return jsonify(result), (400 if result.get("error_type") == "unsupported_export_format" else 500 if result.get("error") else 200)


def _analysis_state_payload(state) -> dict:
    from data_agent.web.event_bus import _json_safe
    pending = [c for c in state.pending_confirmations if c.get("status") == "pending"]
    return {
        "state": _json_safe(state.to_dict()),
        "summary": {
            "goal": state.goal,
            "stage": state.stage,
            "data_state": state.data_state,
            "requirements": len(state.data_requirements),
            "has_spec": bool(state.analysis_spec),
            "evidence_records": len(state.evidence_records),
            "insight_records": len(state.insight_records),
            "pending_confirmations": 0,
            "workflow_notes": len(pending),
            "recommended_paths": len(state.last_recommended_paths),
        },
    }


@sessions_bp.get("/sessions/<session_id>/analysis")
def get_analysis_state(session_id: str):
    """Return the session-scoped analysis state for Web workbench panels."""
    from data_agent.agent.analysis_state import load_analysis_state

    state = load_analysis_state(session_id)
    return jsonify(_analysis_state_payload(state))


@sessions_bp.get("/sessions/<session_id>/trust")
def get_session_trust_view(session_id: str):
    """Return the bounded, read-only Workbench view for a session."""
    from data_agent.agent.analysis_state import load_analysis_state
    from data_agent.agent.trust_view import build_trust_view
    from data_agent.config import get_config

    state_path = get_config().sessions_resolved / session_id / "analysis_state.json"
    state = load_analysis_state(session_id) if state_path.exists() else None
    return jsonify(build_trust_view(state, session_id=session_id))


@sessions_bp.post("/sessions/<session_id>/analysis/reset")
def reset_session_analysis_state(session_id: str):
    """Reset analysis state without deleting conversation, datasets, or artifacts."""
    from data_agent.agent.analysis_state import load_analysis_state, reset_analysis_state

    project_name = load_analysis_state(session_id).project_name
    state = reset_analysis_state(session_id, project_name=project_name)
    return jsonify(_analysis_state_payload(state))


# ── Session Artifacts ───────────────────────────────────────


@sessions_bp.get("/sessions/<session_id>/artifacts-list")
def session_artifacts(session_id: str):
    """List artifacts for a specific session."""
    return jsonify(list_artifacts(session_id))


@sessions_bp.delete("/sessions/<session_id>/artifacts/<int:artifact_index>")
def remove_artifact(session_id: str, artifact_index: int):
    """Delete an artifact by its index in the session's manifest."""
    ok = delete_artifact(session_id, artifact_index)
    if not ok:
        return jsonify({"error": "Artifact not found"}), 404
    return jsonify({"deleted": True})
