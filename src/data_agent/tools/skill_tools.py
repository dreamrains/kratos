"""Skill management tools."""

from __future__ import annotations

import json

from data_agent.tools.registry import registry


def _loader():
    from data_agent.agent.loop import get_skill_loader

    loader = get_skill_loader()
    if loader is not None:
        return loader

    from data_agent.config_resolver import resolve_skills_dirs
    from data_agent.skills.loader import SkillLoader

    loader = SkillLoader(resolve_skills_dirs())
    loader.discover()
    return loader


@registry.register(
    name="load_skill",
    description="Load an enabled global skill into the current agent context.",
    parameters={
        "type": "object",
        "properties": {"name": {"type": "string", "description": "Skill name"}},
        "required": ["name"],
    },
)
def load_skill(name: str) -> str:
    return _loader().load(name)


@registry.register(
    name="unload_skill",
    description="Unload a skill from the current agent context without deleting it.",
    parameters={
        "type": "object",
        "properties": {"name": {"type": "string", "description": "Skill name"}},
        "required": ["name"],
    },
)
def unload_skill(name: str) -> str:
    return _loader().unload(name)


@registry.register(
    name="list_skills",
    description="List installed global skills and their enabled/loaded state.",
    parameters={"type": "object", "properties": {}},
)
def list_skills() -> str:
    loader = _loader()
    available = [
        {
            "name": skill.name,
            "description": skill.description,
            "enabled": skill.enabled,
            "loaded": skill.name in loader._loaded,
            "scope": skill.scope,
        }
        for skill in loader.list_available()
    ]
    return json.dumps({"skills": available}, ensure_ascii=False, indent=2)


@registry.register(
    name="enable_skill",
    description="Enable an installed global skill.",
    parameters={
        "type": "object",
        "properties": {"name": {"type": "string", "description": "Skill name"}},
        "required": ["name"],
    },
)
def enable_skill(name: str) -> str:
    return _loader().set_enabled(name, True)


@registry.register(
    name="disable_skill",
    description="Disable an installed global skill and unload it if active.",
    parameters={
        "type": "object",
        "properties": {"name": {"type": "string", "description": "Skill name"}},
        "required": ["name"],
    },
)
def disable_skill(name: str) -> str:
    return _loader().set_enabled(name, False)


@registry.register(
    name="delete_skill",
    description="Delete an installed global skill.",
    parameters={
        "type": "object",
        "properties": {"name": {"type": "string", "description": "Skill name"}},
        "required": ["name"],
    },
)
def delete_skill(name: str) -> str:
    return _loader().uninstall(name)
