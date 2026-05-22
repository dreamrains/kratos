"""Knowledge management tools.

Runtime knowledge injection is intentionally global + session scoped. Projects
organize work, but they are not a knowledge layer.
"""

from __future__ import annotations

from typing import Optional

from data_agent.knowledge.domain import DomainKnowledge, get_domain_knowledge
from data_agent.knowledge.experience import ExperienceLog, get_experience_log
from data_agent.knowledge.library import KnowledgeLibrary
from data_agent.knowledge.memory import MemoryStore
from data_agent.knowledge.models import KnowledgeItem, MemoryItem, MemoryType
from data_agent.knowledge.retrieval import KnowledgeRetrievalService
from data_agent.knowledge.rules import ProjectRules, get_project_rules
from data_agent.tools.registry import registry

_project_rules: Optional[ProjectRules] = None
_domain_knowledge: Optional[DomainKnowledge] = None
_experience_log: Optional[ExperienceLog] = None
_knowledge_library: KnowledgeLibrary | None = None
_memory_store: MemoryStore | None = None
_retrieval_service: KnowledgeRetrievalService | None = None
_active_session_id: Optional[str] = None


def set_active_object(object_name: Optional[str]) -> None:
    """Compatibility no-op: project/object scope is no longer knowledge scope."""
    return None


def set_active_session(session_id: Optional[str]) -> None:
    global _active_session_id
    _active_session_id = session_id


def get_active_object() -> Optional[str]:
    return None


def get_active_session_id() -> Optional[str]:
    try:
        from data_agent.agent.context import get_current_context

        ctx = get_current_context()
        if ctx is not None:
            return ctx.session_id
    except Exception:
        pass
    return _active_session_id


def _ensure_instances() -> None:
    global _project_rules, _domain_knowledge, _experience_log
    if _project_rules is None:
        _project_rules = get_project_rules()
        _domain_knowledge = get_domain_knowledge()
        _experience_log = get_experience_log()


def reset_knowledge_services_for_tests() -> None:
    global _knowledge_library, _memory_store, _retrieval_service
    _knowledge_library = None
    _memory_store = None
    _retrieval_service = None


def _library() -> KnowledgeLibrary:
    global _knowledge_library
    if _knowledge_library is None:
        _knowledge_library = KnowledgeLibrary()
    return _knowledge_library


def _memory() -> MemoryStore:
    global _memory_store
    if _memory_store is None:
        _memory_store = MemoryStore()
    return _memory_store


def _retrieval() -> KnowledgeRetrievalService:
    global _retrieval_service
    if _retrieval_service is None:
        _retrieval_service = KnowledgeRetrievalService()
    return _retrieval_service


def _knowledge_to_dict(item: KnowledgeItem) -> dict:
    return {
        "id": item.id,
        "title": item.title,
        "domain": item.domain,
        "summary": item.summary,
        "status": item.status.value,
        "tags": item.tags,
        "version": item.version,
        "updated_at": item.updated_at,
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
        "domain": item.domain,
        "tags": item.tags,
        "source_session_id": item.source_session_id,
        "project_id": item.project_id,
        "updated_at": item.updated_at,
    }


@registry.register(
    name="show_project_rules",
    description="Show global and current-session rules.",
)
def show_project_rules() -> str:
    _ensure_instances()
    return _project_rules.get_rules_for_prompt(session_id=get_active_session_id())


@registry.register(
    name="update_project_rules",
    description="Update global project rules content.",
)
def update_project_rules(content: str) -> str:
    _ensure_instances()
    return _project_rules.update(content)


@registry.register(
    name="show_domain_knowledge",
    description="Show global and current-session domain knowledge.",
)
def show_domain_knowledge() -> str:
    import yaml

    _ensure_instances()
    data = _domain_knowledge.get_merged(session_id=get_active_session_id())
    return yaml.dump(data, allow_unicode=True, default_flow_style=False)


@registry.register(
    name="set_domain",
    description="Switch the global active domain knowledge package.",
)
def set_domain(domain_name: str) -> str:
    _ensure_instances()
    return _domain_knowledge.set_domain(domain_name)


@registry.register(
    name="show_experience_log",
    description="Show global and current-session experience log entries.",
)
def show_experience_log() -> str:
    import json

    _ensure_instances()
    entries = _experience_log.get_merged_entries(session_id=get_active_session_id())
    if not entries:
        return "Experience log is empty."
    return json.dumps(entries, ensure_ascii=False, indent=2)


@registry.register(
    name="confirm_experience",
    description="Confirm a draft experience entry.",
)
def confirm_experience(entry_id: str) -> str:
    _ensure_instances()
    result = _experience_log.confirm(entry_id)
    if result:
        return f"Experience {entry_id} confirmed."
    return f"Experience {entry_id} not found."


@registry.register(
    name="create_knowledge_item",
    description="Create a user-confirmed formal knowledge item.",
)
def create_knowledge_item(
    title: str,
    domain: str,
    content: str,
    summary: str = "",
    tags: list[str] | None = None,
) -> dict:
    item = _library().create(title, domain, content, summary, tags or [])
    return _knowledge_to_dict(item)


@registry.register(
    name="search_knowledge",
    description="Search active formal knowledge by query and optional domain.",
)
def search_knowledge(query: str, domain: str = "", limit: int = 5) -> list[dict]:
    return [
        _knowledge_to_dict(item)
        for item in _library().search(query, domain=domain, limit=limit)
    ]


@registry.register(
    name="create_memory_candidate",
    description="Create a reviewable memory candidate from conversation evidence.",
)
def create_memory_candidate(
    text: str,
    summary: str = "",
    memory_type: str = "workflow_pattern",
    confidence: float = 0.6,
    domain: str = "general",
    tags: list[str] | None = None,
) -> dict:
    item = _memory().create_candidate(
        text=text,
        summary=summary,
        memory_type=MemoryType(memory_type),
        confidence=confidence,
        source_session_id=get_active_session_id() or "",
        domain=domain,
        tags=tags or [],
    )
    return _memory_to_dict(item)


@registry.register(
    name="confirm_memory",
    description="Confirm a memory candidate so it may be used as a low-priority memory hint.",
)
def confirm_memory(memory_id: str) -> dict:
    item = _memory().confirm(memory_id)
    return _memory_to_dict(item) if item else {"error": "memory not found"}


@registry.register(
    name="retrieve_knowledge_context",
    description="Retrieve dynamic knowledge and memory context for a task.",
)
def retrieve_knowledge_context(query: str, domain: str = "", project_id: str = "") -> str:
    context = _retrieval().retrieve(query, domain=domain, project_id=project_id)
    return _retrieval().compose_prompt_context(context)


def get_knowledge_instances():
    _ensure_instances()
    return _project_rules, _domain_knowledge, _experience_log
