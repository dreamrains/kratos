"""Skill 加载器：扫描、解析和加载 SKILL.md 技能文件。

支持全局 (~/.data-agent/skills/) + 项目级 (project/skills/) 两级目录。
项目级 skill 覆盖同名全局 skill。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from data_agent.utils.logging import get_logger

logger = get_logger("skills")


@dataclass
class SkillDef:
    """技能定义。"""
    name: str
    description: str
    version: str
    trigger_keywords: list[str]
    tools_required: list[str]
    depends: list[str]
    task_template: list[dict]
    instructions: str
    path: Path
    scope: str = "project"  # "global" 或 "project"


class SkillLoader:
    """扫描多个技能目录，解析 SKILL.md 文件，管理已加载技能。

    目录顺序：全局 → 项目级。同名 skill 项目级覆盖全局。
    """

    def __init__(self, skills_dirs: list[Path] | Path):
        if isinstance(skills_dirs, Path):
            skills_dirs = [skills_dirs]
        self._dirs = skills_dirs
        self._skills: dict[str, SkillDef] = {}
        self._loaded: set[str] = set()

    def discover(self) -> list[SkillDef]:
        """扫描所有 skills_dir 中的 SKILL.md 文件，解析并注册。"""
        self._skills.clear()

        found = []
        for idx, skills_dir in enumerate(self._dirs):
            scope = "global" if idx == 0 else "project"
            if not skills_dir.exists():
                logger.info("Skills directory not found", extra={"extra_data": {"path": str(skills_dir), "scope": scope}})
                continue

            for skill_file in sorted(skills_dir.rglob("SKILL.md")):
                try:
                    skill = self._parse_skill(skill_file, scope)
                    if skill:
                        self._skills[skill.name] = skill
                        found.append(skill)
                        logger.info("Discovered skill", extra={"extra_data": {"name": skill.name, "scope": scope, "path": str(skill_file)}})
                except Exception as e:
                    logger.warning(f"Failed to parse skill file: {skill_file}", extra={"extra_data": {"error": str(e)}})

        return found

    def _parse_skill(self, path: Path, scope: str = "project") -> Optional[SkillDef]:
        """解析 SKILL.md 文件，提取 frontmatter 和指令正文。"""
        text = path.read_text(encoding="utf-8")
        meta: dict = {}
        body = text

        match = re.match(r"^---\n(.*?)\n---\n(.*)", text, re.DOTALL)
        if match:
            meta = self._parse_frontmatter(match.group(1))
            body = match.group(2).strip()

        name = meta.get("name", path.parent.name)
        description = meta.get("description", "")

        # 解析 trigger_keywords: 逗号或空格分隔
        raw_keywords = meta.get("trigger_keywords", "")
        if isinstance(raw_keywords, str):
            trigger_keywords = [k.strip() for k in re.split(r"[,，\s]+", raw_keywords) if k.strip()]
        elif isinstance(raw_keywords, list):
            trigger_keywords = raw_keywords
        else:
            trigger_keywords = []

        # 解析 tools_required: 逗号分隔列表
        raw_tools = meta.get("tools_required", "")
        if isinstance(raw_tools, str):
            tools_required = [t.strip() for t in raw_tools.split(",") if t.strip()]
        elif isinstance(raw_tools, list):
            tools_required = raw_tools
        else:
            tools_required = []

        # 解析 depends: 工具依赖声明
        raw_depends = meta.get("depends", "")
        if isinstance(raw_depends, str):
            depends = [t.strip() for t in raw_depends.split(",") if t.strip()]
        else:
            depends = []

        # 解析 task_template: 优先从 frontmatter 提取，否则从正文 ## Task Template 段提取
        task_template = meta.get("task_template_parsed") or self._parse_task_template(body)

        return SkillDef(
            name=name,
            description=description,
            version=meta.get("version", "1.0"),
            trigger_keywords=trigger_keywords,
            tools_required=tools_required,
            depends=depends,
            task_template=task_template,
            instructions=body,
            path=path,
            scope=scope,
        )

    def _parse_frontmatter(self, frontmatter_text: str) -> dict:
        """解析 YAML frontmatter，支持简单值和列表块。"""
        import yaml
        try:
            meta = yaml.safe_load(frontmatter_text)
            if isinstance(meta, dict):
                # 解析 task_template 列表中的结构化步骤
                task_template_parsed = []
                for item in meta.get("task_template", []):
                    if isinstance(item, dict):
                        task_template_parsed.append(item)
                if task_template_parsed:
                    meta["task_template_parsed"] = task_template_parsed
                return meta
        except Exception:
            pass
        return {}

    def _parse_task_template(self, body: str) -> list[dict]:
        """从 SKILL.md 正文中解析 ## Task Template 段。

        格式示例:
        ## Task Template
        1. [pending] 数据质量评估 → assess_quality
        2. [pending] 描述性统计 → descriptive_stats (depends: 1)
        """
        template = []
        in_template = False
        for line in body.splitlines():
            stripped = line.strip()
            if stripped.lower() in ("## task template", "## task template:"):
                in_template = True
                continue
            if in_template and stripped.startswith("## ") and "task template" not in stripped.lower():
                in_template = False
                continue
            if not in_template or not stripped:
                continue

            # 解析 "1. [pending] 标题 → 工具 (depends: 1,2)"
            m = re.match(r'^\d+\.\s*\[?\w+\]?\s*(.+?)(?:\s*→\s*(\w+))?\s*(?:\(depends:\s*([\d,]+)\))?\s*$', stripped)
            if m:
                subject = m.group(1).strip()
                tool = m.group(2) or ""
                deps_str = m.group(3) or ""
                deps = [int(d.strip()) for d in deps_str.split(",") if d.strip()] if deps_str else []
                template.append({
                    "subject": subject,
                    "tool": tool,
                    "depends_on_indices": deps,
                })

        return template

    def load(self, name: str) -> str:
        """加载指定技能。验证工具依赖。返回状态消息。"""
        if name in self._loaded:
            return f"Skill '{name}' 已加载。"

        skill = self._skills.get(name)
        if not skill:
            available = ", ".join(self._skills.keys()) if self._skills else "(无可用技能)"
            return f"未知技能 '{name}'。可用技能: {available}"

        # 验证工具依赖
        if skill.depends:
            from data_agent.tools.registry import registry
            missing = [t for t in skill.depends if t not in registry.tool_names]
            if missing:
                logger.warning("Skill has missing tool dependencies",
                               extra={"extra_data": {"name": name, "missing": missing}})

        self._loaded.add(name)
        logger.info("Loaded skill", extra={"extra_data": {"name": name}})
        return f"已加载技能 '{name}': {skill.description}"

    def unload(self, name: str) -> str:
        """卸载指定技能。"""
        if name not in self._loaded:
            return f"技能 '{name}' 未加载。"
        self._loaded.discard(name)
        logger.info("Unloaded skill", extra={"extra_data": {"name": name}})
        return f"已卸载技能 '{name}'。"

    def get(self, name: str) -> Optional[SkillDef]:
        return self._skills.get(name)

    def list_available(self) -> list[SkillDef]:
        return list(self._skills.values())

    def list_loaded(self) -> list[SkillDef]:
        return [self._skills[n] for n in self._loaded if n in self._skills]

    def descriptions(self) -> str:
        """单行摘要（参考 s_full.py line 217）。"""
        if not self._skills:
            return "(无可用技能)"
        return "\n".join(
            f"  - {n}: {s.description or '-'}"
            for n, s in self._skills.items()
        )

    def get_prompt_injections(self) -> str:
        """返回已加载技能的 XML 包装指令，用于注入系统提示词。

        使用与 s_full.py line 223 相同的 <skill> 标签格式。
        """
        if not self._loaded:
            return ""

        parts = []
        for name in self._loaded:
            skill = self._skills.get(name)
            if skill:
                parts.append(
                    f'<skill name="{skill.name}">\n{skill.instructions}\n</skill>'
                )
        return "\n\n".join(parts)

    def get_task_template(self, name: str) -> Optional[list[dict]]:
        """获取技能的任务模板，可用于 Planner 直接生成 Task DAG。"""
        skill = self._skills.get(name)
        if skill and skill.task_template:
            return skill.task_template
        return None

    def install(self, source: str, name: str, scope: str = "project") -> str:
        """安装 skill。source 可以是本地路径或 URL。"""
        from data_agent.skills.installer import SkillInstaller
        installer = SkillInstaller(self._dirs, scope)
        result = installer.install(source, name)
        # 重新发现
        self.discover()
        return result

    def uninstall(self, name: str, scope: str = "project") -> str:
        """卸载 skill。"""
        from data_agent.skills.installer import SkillInstaller
        installer = SkillInstaller(self._dirs, scope)

        if name in self._loaded:
            self._loaded.discard(name)

        result = installer.uninstall(name)
        self.discover()
        return result

    def list_installed(self) -> dict[str, str]:
        """返回每个 skill 的来源 scope。"""
        return {name: skill.scope for name, skill in self._skills.items()}

    def format_list(self) -> str:
        """格式化输出所有技能的状态（用于 /skill 命令）。"""
        if not self._skills:
            return "无可用技能。将 SKILL.md 文件放入 project/skills/ 目录即可添加。"

        lines = ["可用技能:"]
        for name, skill in self._skills.items():
            loaded_marker = " [已加载]" if name in self._loaded else ""
            lines.append(f"  - {name}: {skill.description}{loaded_marker}")
            if skill.trigger_keywords:
                lines.append(f"    触发关键词: {', '.join(skill.trigger_keywords)}")
        return "\n".join(lines)
