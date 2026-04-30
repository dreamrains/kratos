"""Skill 安装器：从本地路径或 URL 安装 SKILL.md 文件。"""

from __future__ import annotations

import shutil
import urllib.request
from pathlib import Path
from typing import Optional

from data_agent.utils.logging import get_logger

logger = get_logger("skills.installer")


class SkillInstaller:
    """管理 skill 的安装与卸载。"""

    def __init__(self, dirs: list[Path], scope: str = "project"):
        self._dirs = dirs
        self._scope = scope

    @property
    def _target_dir(self) -> Path:
        """根据 scope 返回目标目录。"""
        idx = 0 if self._scope == "global" else min(1, len(self._dirs) - 1)
        return self._dirs[idx]

    def install(self, source: str, name: str) -> str:
        """安装 skill。source 可以是本地路径或 URL。"""
        source_path = Path(source)

        if source_path.exists():
            return self.install_from_path(source_path, name)
        elif source.startswith(("http://", "https://")):
            return self.install_from_url(source, name)
        else:
            return f"无法安装 skill '{name}': 源 '{source}' 不是有效的本地路径或 URL"

    def install_from_path(self, source: Path, name: str) -> str:
        """从本地路径安装 SKILL.md。"""
        if source.is_dir():
            skill_file = source / "SKILL.md"
        elif source.is_file() and source.name == "SKILL.md":
            skill_file = source
        elif source.is_file():
            # 单个 .md 文件，包装为 SKILL.md
            skill_file = source
        else:
            return f"源路径不存在: {source}"

        if not skill_file.exists():
            return f"SKILL.md 不存在于: {source}"

        target_dir = self._target_dir / name
        target_dir.mkdir(parents=True, exist_ok=True)
        target_file = target_dir / "SKILL.md"

        shutil.copy2(skill_file, target_file)
        logger.info("Skill installed", extra={"extra_data": {"name": name, "path": str(target_file), "scope": self._scope}})

        # 如果源是目录且有辅助文件，一并复制
        if source.is_dir():
            for f in source.iterdir():
                if f.name != "SKILL.md" and f.is_file():
                    shutil.copy2(f, target_dir / f.name)

        return f"已安装 skill '{name}' 到 {self._scope} 级目录 ({target_dir})"

    def install_from_url(self, url: str, name: str) -> str:
        """从 URL 下载 SKILL.md 并安装。"""
        target_dir = self._target_dir / name
        target_dir.mkdir(parents=True, exist_ok=True)
        target_file = target_dir / "SKILL.md"

        try:
            urllib.request.urlretrieve(url, target_file)
        except Exception as e:
            return f"下载失败: {e}"

        # 验证下载的文件
        content = target_file.read_text(encoding="utf-8").strip()
        if not content:
            target_file.unlink()
            target_dir.rmdir()
            return f"下载的文件为空，已清理"

        logger.info("Skill installed from URL", extra={"extra_data": {"name": name, "url": url, "scope": self._scope}})
        return f"已从 URL 安装 skill '{name}' 到 {self._scope} 级目录"

    def uninstall(self, name: str) -> str:
        """卸载指定 skill。"""
        target_dir = self._target_dir / name

        if not target_dir.exists():
            # 尝试在另一个 scope 目录查找
            for d in self._dirs:
                alt = d / name
                if alt.exists():
                    target_dir = alt
                    break
            else:
                return f"skill '{name}' 不存在于任何目录"

        shutil.rmtree(target_dir)
        logger.info("Skill uninstalled", extra={"extra_data": {"name": name}})
        return f"已卸载 skill '{name}'"
