"""Knowledge management tools.

Runtime knowledge injection is intentionally global + session scoped. Projects
organize work, but they are not a knowledge layer.
"""

from __future__ import annotations

from typing import Optional

from data_agent.knowledge.domain import DomainKnowledge, get_domain_knowledge
from data_agent.knowledge.experience import ExperienceLog, get_experience_log
from data_agent.knowledge.rules import ProjectRules, get_project_rules
from data_agent.tools.registry import registry

_project_rules: Optional[ProjectRules] = None
_domain_knowledge: Optional[DomainKnowledge] = None
_experience_log: Optional[ExperienceLog] = None
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


def get_knowledge_instances():
    _ensure_instances()
    return _project_rules, _domain_knowledge, _experience_log
