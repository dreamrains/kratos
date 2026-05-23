"""Web API for knowledge, memory, and session evidence management."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from data_agent.knowledge.evidence import EvidenceStore
from data_agent.knowledge.library import KnowledgeLibrary
from data_agent.knowledge.memory import MemoryStore
from data_agent.knowledge.models import EvidenceRecord, KnowledgeItem, MemoryItem, MemoryType

management_bp = Blueprint("management", __name__)


def _knowledge_to_dict(item: KnowledgeItem) -> dict:
    return {
        "id": item.id,
        "title": item.title,
        "domain": item.domain,
        "summary": item.summary,
        "status": item.status.value,
        "tags": item.tags,
        "source": item.source.value,
        "version": item.version,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
        "deprecated_at": item.deprecated_at,
        "supersedes": item.supersedes,
        "superseded_by": item.superseded_by,
        "content": item.content,
    }


def _memory_to_dict(item: MemoryItem) -> dict:
    return {
        "id": item.id,
        "type": item.type.value,
        "text": item.text,
        "summary": item.summary,
        "status": item.status.value,
        "confidence": item.confidence,
        "source_session_id": item.source_session_id,
        "source_message_ids": item.source_message_ids,
        "source_tool_call_ids": item.source_tool_call_ids,
        "project_id": item.project_id,
        "domain": item.domain,
        "tags": item.tags,
        "last_used_at": item.last_used_at,
        "hit_count": item.hit_count,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
        "promotion_target": item.promotion_target,
    }


def _evidence_to_dict(record: EvidenceRecord) -> dict:
    return {
        "id": record.id,
        "session_id": record.session_id,
        "project_id": record.project_id,
        "kind": record.kind.value,
        "content_ref": record.content_ref,
        "summary": record.summary,
        "content": record.content,
        "created_at": record.created_at,
        "tags": record.tags,
    }


@management_bp.get("/management/knowledge")
def list_knowledge():
    status = request.args.get("status", "")
    domain = request.args.get("domain", "")
    items = KnowledgeLibrary().list(domain=domain, status=status)
    return jsonify([_knowledge_to_dict(item) for item in items])


@management_bp.post("/management/knowledge")
def create_knowledge():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    content = data.get("content") or ""
    if not title or not content:
        return jsonify({"error": "title and content are required"}), 400
    try:
        item = KnowledgeLibrary().create(
            title=title,
            domain=(data.get("domain") or "general").strip(),
            content=content,
            summary=data.get("summary") or "",
            tags=data.get("tags") or [],
        )
    except (TypeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(_knowledge_to_dict(item))


@management_bp.get("/management/knowledge/search")
def search_knowledge():
    query = request.args.get("q", "")
    domain = request.args.get("domain", "")
    items = KnowledgeLibrary().search(query, domain=domain)
    return jsonify([_knowledge_to_dict(item) for item in items])


@management_bp.patch("/management/knowledge/<item_id>")
def update_knowledge(item_id: str):
    data = request.get_json(silent=True) or {}
    try:
        item = KnowledgeLibrary().update(
            item_id,
            content=data.get("content"),
            title=data.get("title"),
            summary=data.get("summary"),
            tags=data.get("tags"),
        )
    except (TypeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400
    if item is None:
        return jsonify({"error": "knowledge not found"}), 404
    return jsonify(_knowledge_to_dict(item))


@management_bp.post("/management/knowledge/<item_id>/deprecate")
def deprecate_knowledge(item_id: str):
    item = KnowledgeLibrary().deprecate(item_id)
    if item is None:
        return jsonify({"error": "knowledge not found"}), 404
    return jsonify(_knowledge_to_dict(item))


@management_bp.post("/management/knowledge/<item_id>/restore")
def restore_knowledge(item_id: str):
    item = KnowledgeLibrary().restore(item_id)
    if item is None:
        return jsonify({"error": "knowledge not found"}), 404
    return jsonify(_knowledge_to_dict(item))


@management_bp.delete("/management/knowledge/<item_id>")
def delete_knowledge(item_id: str):
    if not KnowledgeLibrary().delete(item_id):
        return jsonify({"error": "knowledge not found"}), 404
    return jsonify({"deleted": True})


@management_bp.get("/management/memory")
def list_memory():
    status = request.args.get("status", "")
    domain = request.args.get("domain", "")
    try:
        items = MemoryStore().list(status=status, domain=domain)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify([_memory_to_dict(item) for item in items])


@management_bp.post("/management/memory")
def create_memory():
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "text is required"}), 400
    try:
        item = MemoryStore().create_candidate(
            text=text,
            summary=data.get("summary") or "",
            memory_type=MemoryType(data.get("memory_type") or "workflow_pattern"),
            confidence=float(data.get("confidence") if data.get("confidence") is not None else 0.6),
            source_session_id=data.get("source_session_id") or "",
            source_message_ids=data.get("source_message_ids") or [],
            source_tool_call_ids=data.get("source_tool_call_ids") or [],
            project_id=data.get("project_id") or "",
            domain=data.get("domain") or "general",
            tags=data.get("tags") or [],
            promotion_target=data.get("promotion_target") or "none",
        )
    except (TypeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(_memory_to_dict(item))


@management_bp.post("/management/memory/<memory_id>/confirm")
def confirm_memory(memory_id: str):
    item = MemoryStore().confirm(memory_id)
    if item is None:
        return jsonify({"error": "memory not found or cannot be confirmed"}), 404
    return jsonify(_memory_to_dict(item))


@management_bp.post("/management/memory/<memory_id>/reject")
def reject_memory(memory_id: str):
    item = MemoryStore().reject(memory_id)
    if item is None:
        return jsonify({"error": "memory not found or cannot be rejected"}), 404
    return jsonify(_memory_to_dict(item))


@management_bp.post("/management/memory/<memory_id>/deprecate")
def deprecate_memory(memory_id: str):
    item = MemoryStore().deprecate(memory_id)
    if item is None:
        return jsonify({"error": "memory not found or cannot be deprecated"}), 404
    return jsonify(_memory_to_dict(item))


@management_bp.get("/management/evidence/search")
def search_evidence():
    query = request.args.get("q", "")
    project_id = request.args.get("project_id", "")
    records = EvidenceStore().search(query, project_id=project_id)
    return jsonify([_evidence_to_dict(record) for record in records])
