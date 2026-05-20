"""Workbench capability matrix for Web/CLI parity."""

from __future__ import annotations

from flask import Blueprint, jsonify

capabilities_bp = Blueprint("capabilities", __name__)


@capabilities_bp.get("/capabilities")
def get_capabilities():
    """Return the local workbench capabilities exposed by CLI and Web."""
    return jsonify({
        "mode": {
            "profile": "local_personal_client",
            "local_execution": True,
            "multi_user": False,
            "llm_context_policy": "quality_first_current_session",
        },
        "privacy": {
            "default_host": "127.0.0.1",
            "data_execution": "local",
            "llm_role": "intent_planning_explanation",
            "payload_policy": "unchanged_from_agent_flow",
        },
        "terminology": {
            "primary_entity": "project",
            "legacy_aliases": ["object"],
            "session_project_relationship": "session may be unbound or optionally bound to a project",
        },
        "commands": [
            {
                "name": "project",
                "cli": ["/project", "/project bind", "/project unbind"],
                "api": ["/api/projects", "/api/projects/bind", "/api/projects/unbind"],
                "ui": ["project sidebar", "session project binding"],
                "variants": ["create", "bind", "unbind", "rename", "delete"],
            },
            {
                "name": "analysis",
                "cli": ["/analysis status", "/analysis requirements", "/analysis spec", "/analysis evidence", "/analysis reset"],
                "api": ["/api/sessions/<session_id>/analysis", "/api/sessions/<session_id>/analysis/reset"],
                "ui": ["analysis state panel"],
                "variants": ["status", "requirements", "spec", "evidence", "reset"],
            },
            {
                "name": "tasks",
                "cli": ["/tasks"],
                "api": ["/api/tasks", "/api/tasks/<task_id>"],
                "ui": ["workflow task panel"],
                "variants": ["list", "create", "update", "delete"],
            },
            {
                "name": "report",
                "cli": ["/report brief [format]", "/report formal [format]"],
                "api": ["/api/sessions/<session_id>/report?type=brief|formal&format=markdown|html|pdf"],
                "ui": ["brief report action", "formal report action"],
                "variants": ["brief", "formal"],
                "formats": ["markdown", "html", "pdf"],
            },
            {
                "name": "export",
                "cli": ["/export [markdown|html]"],
                "api": ["/api/sessions/<session_id>/export?format=markdown|html"],
                "ui": ["conversation export action"],
                "variants": ["conversation"],
                "formats": ["markdown", "html"],
            },
        ],
        "capabilities": [
            {"id": "data.profile", "category": "data", "web_visible": True},
            {"id": "data.describe", "category": "data", "web_visible": True},
            {"id": "analysis.period_compare", "category": "analysis", "web_visible": True},
            {"id": "analysis.dimension_decomposition", "category": "analysis", "web_visible": True},
            {"id": "analysis.funnel", "category": "analysis", "web_visible": True},
            {"id": "analysis.cohort", "category": "analysis", "web_visible": True},
            {"id": "analysis.causal", "category": "high_risk_analysis", "requires_confirmation": True},
            {"id": "analysis.forecast", "category": "high_risk_analysis", "requires_confirmation": True},
            {"id": "fallback.python", "category": "fallback", "preferred": False},
            {"id": "workflow.task_create", "category": "workflow", "web_visible": True},
            {"id": "artifact.evidence_record", "category": "artifact", "web_visible": True},
            {"id": "artifact.conversation_export", "category": "artifact", "web_visible": True},
            {"id": "artifact.analysis_brief", "category": "artifact", "web_visible": True},
            {"id": "artifact.formal_report", "category": "artifact", "web_visible": True},
            {"id": "interaction.confirmation", "category": "interaction", "web_visible": True},
        ],
        "endpoints": [
            "/api/chat",
            "/api/chat/resume",
            "/api/sessions",
            "/api/sessions/<session_id>",
            "/api/sessions/<session_id>/analysis",
            "/api/sessions/<session_id>/export",
            "/api/sessions/<session_id>/report",
            "/api/tasks",
            "/api/projects",
            "/api/uploads",
        ],
    })
