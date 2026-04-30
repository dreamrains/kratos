"""技能相关工具：load_skill, list_skills。"""

from __future__ import annotations

import json

from data_agent.tools.registry import registry


@registry.register(
    name="load_skill",
    description="加载一个技能模块以增强分析能力。加载后技能指令将注入到你的上下文中，"
                "提供专门的分析流程和方法指导。",
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "技能名称"},
        },
        "required": ["name"],
    },
)
def load_skill(name: str) -> str:
    """加载技能模块（参考 s_full.py load_skill handler）。"""
    from data_agent.agent.loop import get_skill_loader
    loader = get_skill_loader()
    if loader is None:
        return json.dumps({"error": "Skill system not initialized"}, ensure_ascii=False)
    return loader.load(name)


@registry.register(
    name="list_skills",
    description="列出所有可用的技能模块及其加载状态。",
    parameters={"type": "object", "properties": {}},
)
def list_skills() -> str:
    """列出所有可用和已加载的技能。"""
    from data_agent.agent.loop import get_skill_loader
    loader = get_skill_loader()

    if loader is None:
        try:
            from data_agent.config_resolver import resolve_skills_dirs
            from data_agent.skills.loader import SkillLoader
            dirs = resolve_skills_dirs()
            loader = SkillLoader(dirs)
            loader.discover()
        except Exception:
            return json.dumps({"skills": [], "note": "Skill system not fully initialized"}, ensure_ascii=False)

    available = [
        {"name": s.name, "description": s.description, "loaded": s.name in loader._loaded}
        for s in loader.list_available()
    ]
    return json.dumps({"skills": available}, ensure_ascii=False, indent=2)
