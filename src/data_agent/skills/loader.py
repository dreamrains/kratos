"""Global skill discovery and runtime loading."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

from data_agent.utils.logging import get_logger

logger = get_logger("skills")


@dataclass
class SkillDef:
    name: str
    description: str
    version: str
    trigger_keywords: list[str]
    tools_required: list[str]
    depends: list[str]
    task_template: list[dict]
    instructions: str
    path: Path
    scope: str = "global"
    enabled: bool = True


class SkillLoader:
    """Scan global skill directories and inject enabled, loaded skills."""

    def __init__(self, skills_dirs: list[Path] | Path):
        if isinstance(skills_dirs, Path):
            skills_dirs = [skills_dirs]
        self._dirs = skills_dirs
        self._skills: dict[str, SkillDef] = {}
        self._loaded: set[str] = set()

    def discover(self) -> list[SkillDef]:
        self._skills.clear()
        found: list[SkillDef] = []

        for skills_dir in self._dirs:
            if not skills_dir.exists():
                logger.info("Skills directory not found", extra={"extra_data": {"path": str(skills_dir)}})
                continue

            for skill_file in sorted(skills_dir.rglob("SKILL.md")):
                try:
                    skill = self._parse_skill(skill_file)
                    if skill is None:
                        continue
                    self._skills[skill.name] = skill
                    found.append(skill)
                    logger.info(
                        "Discovered skill",
                        extra={"extra_data": {"name": skill.name, "path": str(skill_file), "enabled": skill.enabled}},
                    )
                except Exception as exc:
                    logger.warning(
                        "Failed to parse skill file",
                        extra={"extra_data": {"path": str(skill_file), "error": str(exc)}},
                    )

        self._loaded.intersection_update({name for name, skill in self._skills.items() if skill.enabled})
        return found

    def _parse_skill(self, path: Path) -> Optional[SkillDef]:
        text = path.read_text(encoding="utf-8")
        meta: dict = {}
        body = text

        match = re.match(r"^---\n(.*?)\n---\n(.*)", text, re.DOTALL)
        if match:
            meta = self._parse_frontmatter(match.group(1))
            body = match.group(2).strip()

        name = meta.get("name", path.parent.name)
        description = meta.get("description", "")

        raw_keywords = meta.get("trigger_keywords", "")
        if isinstance(raw_keywords, str):
            trigger_keywords = [k.strip() for k in re.split(r"[,\s]+", raw_keywords) if k.strip()]
        elif isinstance(raw_keywords, list):
            trigger_keywords = [str(k).strip() for k in raw_keywords if str(k).strip()]
        else:
            trigger_keywords = []

        raw_tools = meta.get("tools_required", "")
        if isinstance(raw_tools, str):
            tools_required = [t.strip() for t in raw_tools.split(",") if t.strip()]
        elif isinstance(raw_tools, list):
            tools_required = [str(t).strip() for t in raw_tools if str(t).strip()]
        else:
            tools_required = []

        raw_depends = meta.get("depends", "")
        if isinstance(raw_depends, str):
            depends = [t.strip() for t in raw_depends.split(",") if t.strip()]
        elif isinstance(raw_depends, list):
            depends = [str(t).strip() for t in raw_depends if str(t).strip()]
        else:
            depends = []

        enabled = bool(meta.get("enabled", True))
        task_template = meta.get("task_template_parsed") or self._parse_task_template(body)

        return SkillDef(
            name=name,
            description=description,
            version=str(meta.get("version", "1.0")),
            trigger_keywords=trigger_keywords,
            tools_required=tools_required,
            depends=depends,
            task_template=task_template,
            instructions=body,
            path=path,
            enabled=enabled,
        )

    def _parse_frontmatter(self, frontmatter_text: str) -> dict:
        try:
            meta = yaml.safe_load(frontmatter_text)
            if isinstance(meta, dict):
                task_template_parsed = [item for item in meta.get("task_template", []) if isinstance(item, dict)]
                if task_template_parsed:
                    meta["task_template_parsed"] = task_template_parsed
                return meta
        except Exception:
            pass
        return {}

    def _parse_task_template(self, body: str) -> list[dict]:
        template: list[dict] = []
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

            match = re.match(r"^\d+\.\s*\[?\w+\]?\s*(.+?)(?:\s*->\s*(\w+))?\s*(?:\(depends:\s*([\d,]+)\))?\s*$", stripped)
            if match:
                deps_str = match.group(3) or ""
                template.append(
                    {
                        "subject": match.group(1).strip(),
                        "tool": match.group(2) or "",
                        "depends_on_indices": [int(d.strip()) for d in deps_str.split(",") if d.strip()],
                    }
                )
        return template

    def load(self, name: str) -> str:
        if name in self._loaded:
            return f"Skill '{name}' already loaded."

        skill = self._skills.get(name)
        if not skill:
            available = ", ".join(self._skills.keys()) if self._skills else "(none)"
            return f"Unknown skill '{name}'. Available skills: {available}"
        if not skill.enabled:
            return f"Skill '{name}' is disabled."

        if skill.depends:
            from data_agent.tools.registry import registry

            missing = [tool for tool in skill.depends if tool not in registry.tool_names]
            if missing:
                logger.warning("Skill has missing tool dependencies", extra={"extra_data": {"name": name, "missing": missing}})

        self._loaded.add(name)
        logger.info("Loaded skill", extra={"extra_data": {"name": name}})
        return f"Loaded skill '{name}': {skill.description}"

    def unload(self, name: str) -> str:
        if name not in self._loaded:
            return f"Skill '{name}' is not loaded."
        self._loaded.discard(name)
        logger.info("Unloaded skill", extra={"extra_data": {"name": name}})
        return f"Unloaded skill '{name}'."

    def get(self, name: str) -> Optional[SkillDef]:
        return self._skills.get(name)

    def list_available(self) -> list[SkillDef]:
        return list(self._skills.values())

    def list_loaded(self) -> list[SkillDef]:
        return [self._skills[name] for name in self._loaded if name in self._skills]

    def descriptions(self) -> str:
        enabled = [skill for skill in self._skills.values() if skill.enabled]
        if not enabled:
            return "(no enabled skills)"
        return "\n".join(f"  - {skill.name}: {skill.description or '-'}" for skill in enabled)

    def get_prompt_injections(self) -> str:
        if not self._loaded:
            return ""

        parts = []
        for name in sorted(self._loaded):
            skill = self._skills.get(name)
            if skill and skill.enabled:
                parts.append(f'<skill name="{skill.name}">\n{skill.instructions}\n</skill>')
        return "\n\n".join(parts)

    def get_task_template(self, name: str) -> Optional[list[dict]]:
        skill = self._skills.get(name)
        if skill and skill.task_template:
            return skill.task_template
        return None

    def install(self, source: str, name: str, scope: str = "global") -> str:
        from data_agent.skills.installer import SkillInstaller

        installer = SkillInstaller(self._dirs, "global")
        result = installer.install(source, name)
        self.discover()
        return result

    def uninstall(self, name: str, scope: str = "global") -> str:
        from data_agent.skills.installer import SkillInstaller

        self._loaded.discard(name)
        installer = SkillInstaller(self._dirs, "global")
        result = installer.uninstall(name)
        self.discover()
        return result

    def list_installed(self) -> dict[str, str]:
        return {name: skill.scope for name, skill in self._skills.items()}

    def set_enabled(self, name: str, enabled: bool) -> str:
        skill = self._skills.get(name)
        if skill is None:
            return f"Skill '{name}' not found."

        self._set_frontmatter_enabled(skill.path, enabled)
        if not enabled:
            self._loaded.discard(name)
        self.discover()
        return f"Skill '{name}' {'enabled' if enabled else 'disabled'}."

    def _set_frontmatter_enabled(self, path: Path, enabled: bool) -> None:
        text = path.read_text(encoding="utf-8")
        match = re.match(r"^---\n(.*?)\n---\n(.*)", text, re.DOTALL)
        if match:
            meta = self._parse_frontmatter(match.group(1))
            body = match.group(2)
        else:
            meta = {}
            body = text
        meta["enabled"] = enabled
        path.write_text(f"---\n{yaml.safe_dump(meta, allow_unicode=True, sort_keys=False)}---\n{body.lstrip()}", encoding="utf-8")

    def format_list(self) -> str:
        if not self._skills:
            return "No skills found. Add SKILL.md files under the global skills directory."

        lines = ["Available skills:"]
        for name, skill in sorted(self._skills.items()):
            state = "enabled" if skill.enabled else "disabled"
            loaded = ", loaded" if name in self._loaded else ""
            lines.append(f"  - {name}: {skill.description or '-'} [{state}{loaded}]")
            if skill.trigger_keywords:
                lines.append(f"    triggers: {', '.join(skill.trigger_keywords)}")
        return "\n".join(lines)
