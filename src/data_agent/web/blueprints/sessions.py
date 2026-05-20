"""Session CRUD, rewind, and export endpoints."""

from __future__ import annotations

import json
from pathlib import Path

from flask import Blueprint, Response, current_app, jsonify, request, send_file

from data_agent.session.history import (
    delete_artifact,
    list_artifacts,
    list_sessions,
    load_session,
    delete_session,
    _session_dir,
)

sessions_bp = Blueprint("sessions", __name__)


def _get_model_context_window(model_id: str) -> int | None:
    """Try to get the actual context window (max_input_tokens) for the model."""
    try:
        import litellm
        info = litellm.get_model_info(model_id)
        return info.get("max_input_tokens") or info.get("max_tokens")
    except Exception:
        return None


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

    # Attach token usage — use real model context window when available
    from data_agent.agent.compact import estimate_tokens
    from data_agent.config import get_config

    cfg = get_config()
    context_window = _get_model_context_window(cfg.model_id)

    if context_window is not None:
        manager = current_app.config["agent_manager"]
        loop = manager.get(session_id)
        if loop and loop.messages:
            used = estimate_tokens(loop.messages)
        else:
            messages = data.get("messages", [])
            used = estimate_tokens(messages) if messages else 0

        data["token_usage"] = {
            "used": used,
            "threshold": context_window,
            "pct": min(round(used / max(context_window, 1) * 100), 100),
        }
    else:
        data["token_usage"] = None

    return jsonify(data)


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

    # Try in-memory loop first, fall back to loading from disk
    if loop and loop.messages:
        messages = loop.messages
    else:
        data = load_session(session_id)
        if not data:
            return jsonify({"error": "Session not found"}), 404
        messages = data.get("messages", [])

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
    snapshots_dir = Path(session_id) / "rewind_snapshots"
    if not snapshots_dir.is_absolute():
        from data_agent.config import get_config
        snapshots_dir = get_config().sessions_resolved / session_id / "rewind_snapshots"
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    snapshot_path = snapshots_dir / f"rewind_{ts}.json"
    snapshot_path.write_text(
        json.dumps({"messages": messages, "rewound_at": ts}, default=str, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    truncated = messages[:messages_to_keep]

    if loop and loop.messages:
        loop.messages = truncated

    # Persist the truncated history
    from data_agent.session.history import save_session
    save_session(truncated, session_id)

    return jsonify({
        "message": f"Rewound to before round {round_num}, removed {removed} messages",
        "removed": removed,
        "round": round_num,
        "user_message": user_message_text,
    })


# ── Export ──────────────────────────────────────────────────


@sessions_bp.get("/sessions/<session_id>/export")
def export_session(session_id: str):
    """Export session analysis results as HTML or Markdown file."""
    fmt = request.args.get("format", "html").lower()
    if fmt == "pdf":
        return jsonify({
            "error": "PDF conversation export is not supported",
            "error_type": "unsupported_export_format",
            "supported_formats": ["html", "markdown"],
        }), 400
    if fmt in ("html", "markdown", "md"):
        from data_agent.agent.context import AgentContext, use_agent_context
        from data_agent.session.workspace import Workspace
        from data_agent.tools.report import export_conversation

        ctx = AgentContext(session_id=session_id, workspace=Workspace())
        with use_agent_context(ctx):
            return jsonify(json.loads(export_conversation(format=fmt)))

    if fmt not in ("html", "markdown", "md"):
        fmt = "html"

    data = load_session(session_id)
    if not data:
        return jsonify({"error": "Session not found"}), 404

    messages = data.get("messages", [])

    # Extract assistant analysis content (filter tool calls, keep text responses >30 chars)
    analysis_blocks = []
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content", "")
        if not isinstance(content, str) or not content.strip():
            continue
        if len(content.strip()) > 30:
            analysis_blocks.append(content.strip())

    if not analysis_blocks:
        return jsonify({"error": "No analysis results to export"}), 400

    from datetime import datetime
    from jinja2 import Template

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    title = data.get("summary", "Analysis Export") or "Analysis Export"
    ts_file = datetime.now().strftime("%Y%m%d_%H%M%S")

    if fmt in ("markdown", "md"):
        md_lines = [f"# {title}", f"\n_Generated: {timestamp}_\n"]
        for i, block in enumerate(analysis_blocks, 1):
            md_lines.append(f"## Analysis {i}\n")
            md_lines.append(block)
            md_lines.append("")
        filename = f"export_{ts_file}.md"
        content_type = "text/markdown"
        content_bytes = "\n".join(md_lines).encode("utf-8")
    else:
        # HTML export with inline styles
        def _md_to_html(text):
            import re
            text = re.sub(r'^### (.+)$', r'<h3>\1</h3>', text, flags=re.M)
            text = re.sub(r'^## (.+)$', r'<h2>\1</h2>', text, flags=re.M)
            text = re.sub(r'^# (.+)$', r'<h1>\1</h1>', text, flags=re.M)
            text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
            text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
            text = re.sub(r'`(.+?)`', r'<code>\1</code>', text)
            text = re.sub(r'\n', '<br>\n', text)
            return text

        rendered = [f'<div class="analysis-block">{_md_to_html(b)}</div>' for b in analysis_blocks]
        html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><title>{title}</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','Microsoft YaHei',sans-serif;max-width:960px;margin:0 auto;padding:40px 20px;color:#333;line-height:1.7}}
h1{{color:#1a1a2e;border-bottom:3px solid #16213e;padding-bottom:12px}}
h2{{color:#16213e;border-bottom:1px solid #e0e0e0;padding-bottom:8px;margin-top:36px}}
.metadata{{color:#999;font-size:13px;margin-bottom:24px}}
.analysis-block{{margin:20px 0;padding:16px 20px;background:#fafafa;border-left:3px solid #16213e;border-radius:4px}}
code{{background:#f0f0f0;padding:2px 6px;border-radius:3px;font-size:0.9em}}
</style></head><body><h1>{title}</h1><div class="metadata">Generated: {timestamp}</div>{"".join(rendered)}</body></html>"""
        filename = f"export_{ts_file}.html"
        content_type = "text/html"
        content_bytes = html.encode("utf-8")

    return Response(
        content_bytes,
        mimetype=content_type,
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
        },
    )


@sessions_bp.get("/sessions/<session_id>/report")
def generate_session_report(session_id: str):
    """Deprecated brief/formal report endpoint.

    Current-session report needs are handled through chat synthesis and
    conversation export. Keep the route for a clear transition response.
    """
    report_type = request.args.get("type", "brief").lower()
    fmt = request.args.get("format", "html").lower()

    if report_type in {"conversation", "export"}:
        from data_agent.agent.context import AgentContext, use_agent_context
        from data_agent.session.workspace import Workspace
        from data_agent.tools.report import export_conversation

        ctx = AgentContext(session_id=session_id, workspace=Workspace())
        with use_agent_context(ctx):
            payload = export_conversation(format=fmt)
        return jsonify(json.loads(payload))

    return jsonify({
        "error": "Brief and formal report artifacts are deprecated",
        "error_type": "report_artifact_deprecated",
        "report_type": report_type,
        "supported_actions": ["chat_synthesis", "export_conversation"],
        "message": (
            "Ask the agent to synthesize the current session in chat, or use "
            "/api/sessions/<session_id>/export?format=markdown|html for a file."
        ),
    }), 410


def _analysis_state_payload(state) -> dict:
    pending = [c for c in state.pending_confirmations if c.get("status") == "pending"]
    return {
        "state": state.to_dict(),
        "summary": {
            "goal": state.goal,
            "stage": state.stage,
            "data_state": state.data_state,
            "requirements": len(state.data_requirements),
            "has_spec": bool(state.analysis_spec),
            "evidence_records": len(state.evidence_records),
            "insight_records": len(state.insight_records),
            "pending_confirmations": len(pending),
            "recommended_paths": len(state.last_recommended_paths),
        },
    }


@sessions_bp.get("/sessions/<session_id>/analysis")
def get_analysis_state(session_id: str):
    """Return the session-scoped analysis state for Web workbench panels."""
    from data_agent.agent.analysis_state import load_analysis_state

    state = load_analysis_state(session_id)
    return jsonify(_analysis_state_payload(state))


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
