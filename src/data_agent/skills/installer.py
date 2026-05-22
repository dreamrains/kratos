"""Install and remove global skills."""

from __future__ import annotations

import shutil
import urllib.request
from pathlib import Path

from data_agent.utils.logging import get_logger

logger = get_logger("skills.installer")


class SkillInstaller:
    """Manage skills in the global skills directory."""

    def __init__(self, dirs: list[Path], scope: str = "global"):
        self._dirs = dirs
        self._scope = "global"

    @property
    def _target_dir(self) -> Path:
        return self._dirs[0]

    def install(self, source: str, name: str) -> str:
        source_path = Path(source)
        if source_path.exists():
            return self.install_from_path(source_path, name)
        if source.startswith(("http://", "https://")):
            return self.install_from_url(source, name)
        return f"Cannot install skill '{name}': source '{source}' is not a valid local path or URL"

    def install_from_path(self, source: Path, name: str) -> str:
        if source.is_dir():
            skill_file = source / "SKILL.md"
        elif source.is_file():
            skill_file = source
        else:
            return f"Source path does not exist: {source}"

        if not skill_file.exists():
            return f"SKILL.md not found at: {source}"

        target_dir = self._target_dir / name
        target_dir.mkdir(parents=True, exist_ok=True)
        target_file = target_dir / "SKILL.md"
        shutil.copy2(skill_file, target_file)

        if source.is_dir():
            for file_path in source.iterdir():
                if file_path.name != "SKILL.md" and file_path.is_file():
                    shutil.copy2(file_path, target_dir / file_path.name)

        logger.info("Skill installed", extra={"extra_data": {"name": name, "path": str(target_file), "scope": "global"}})
        return f"Installed skill '{name}' to global directory ({target_dir})"

    def install_from_url(self, url: str, name: str) -> str:
        target_dir = self._target_dir / name
        target_dir.mkdir(parents=True, exist_ok=True)
        target_file = target_dir / "SKILL.md"

        try:
            urllib.request.urlretrieve(url, target_file)
        except Exception as exc:
            return f"Download failed: {exc}"

        content = target_file.read_text(encoding="utf-8").strip()
        if not content:
            target_file.unlink(missing_ok=True)
            target_dir.rmdir()
            return "Downloaded file is empty; cleaned up."

        logger.info("Skill installed from URL", extra={"extra_data": {"name": name, "url": url, "scope": "global"}})
        return f"Installed skill '{name}' from URL to global directory"

    def uninstall(self, name: str) -> str:
        target_dir = self._target_dir / name
        if not target_dir.exists():
            return f"Skill '{name}' does not exist in the global directory"

        shutil.rmtree(target_dir)
        logger.info("Skill uninstalled", extra={"extra_data": {"name": name}})
        return f"Uninstalled skill '{name}'"
