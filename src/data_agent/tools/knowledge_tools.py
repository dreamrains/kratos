"""知识管理工具：通过对话管理三层知识体系，支持对象级和会话级隔离。"""

from __future__ import annotations

from typing import Optional

from data_agent.knowledge.rules import ProjectRules, get_project_rules
from data_agent.knowledge.domain import DomainKnowledge, get_domain_knowledge
from data_agent.knowledge.experience import ExperienceLog, get_experience_log
from data_agent.tools.registry import registry

_project_rules: Optional[ProjectRules] = None
_domain_knowledge: Optional[DomainKnowledge] = None
_experience_log: Optional[ExperienceLog] = None

# 当前活跃对象名（由 workspace set_object/clear_object 驱动）
_active_object: Optional[str] = None

# 当前活跃会话 ID
_active_session_id: Optional[str] = None


def set_active_object(object_name: Optional[str]) -> None:
    """切换活跃对象，影响知识加载的合并行为。"""
    global _active_object
    _active_object = object_name


def set_active_session(session_id: Optional[str]) -> None:
    """设置当前活跃会话 ID。"""
    global _active_session_id
    _active_session_id = session_id


def get_active_object() -> Optional[str]:
    return _active_object


def get_active_session_id() -> Optional[str]:
    return _active_session_id


def _ensure_instances():
    """确保知识实例已初始化。"""
    global _project_rules, _domain_knowledge, _experience_log
    if _project_rules is None:
        _project_rules = get_project_rules()
        _domain_knowledge = get_domain_knowledge()
        _experience_log = get_experience_log()


@registry.register(
    name="show_project_rules",
    description="显示当前项目规则。",
)
def show_project_rules() -> str:
    _ensure_instances()
    return _project_rules.get_rules_for_prompt(
        object_name=_active_object, session_id=_active_session_id
    )


@registry.register(
    name="update_project_rules",
    description="更新项目规则内容。提供完整的新规则文本。",
)
def update_project_rules(content: str) -> str:
    _ensure_instances()
    if _active_object:
        return _project_rules.update_object_rules(_active_object, content)
    return _project_rules.update(content)


@registry.register(
    name="show_domain_knowledge",
    description="显示当前领域知识。",
)
def show_domain_knowledge() -> str:
    import yaml
    _ensure_instances()
    data = _domain_knowledge.get_merged(
        object_name=_active_object, session_id=_active_session_id
    )
    return yaml.dump(data, allow_unicode=True, default_flow_style=False)


@registry.register(
    name="set_domain",
    description="切换领域知识包。domain_name: ecommerce/gaming/general。",
)
def set_domain(domain_name: str) -> str:
    _ensure_instances()
    return _domain_knowledge.set_domain(domain_name, object_name=_active_object)


@registry.register(
    name="show_experience_log",
    description="显示经验日志。",
)
def show_experience_log() -> str:
    import json
    _ensure_instances()
    entries = _experience_log.get_merged_entries(
        object_name=_active_object, session_id=_active_session_id
    )
    if not entries:
        return "经验日志为空。"
    return json.dumps(entries, ensure_ascii=False, indent=2)


@registry.register(
    name="confirm_experience",
    description="确认一条经验。将 draft 状态的经验标记为 confirmed。",
)
def confirm_experience(entry_id: str) -> str:
    _ensure_instances()
    result = _experience_log.confirm(entry_id)
    if result:
        return f"经验 {entry_id} 已确认。"
    return f"未找到经验 {entry_id}。"


def get_knowledge_instances():
    """返回知识管理实例，供 Agent Loop 注入提示词。"""
    _ensure_instances()
    return _project_rules, _domain_knowledge, _experience_log
