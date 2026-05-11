"""分析对象管理器：创建、切换、归档、迁移分析对象。"""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml

from data_agent.config import get_config
from data_agent.utils.logging import get_logger

logger = get_logger("object_manager")


class ObjectManager:
    """管理分析对象（Object）的 CRUD 和迁移。"""

    def __init__(self, objects_dir: Optional[Path] = None):
        cfg = get_config()
        self._objects_dir = objects_dir or cfg.objects_dir

    def create(self, name: str, description: str = "") -> dict:
        """创建分析对象，返回 meta 信息。"""
        obj_dir = self._objects_dir / name
        if obj_dir.exists():
            raise FileExistsError(f"对象 '{name}' 已存在: {obj_dir}")

        obj_dir.mkdir(parents=True, exist_ok=True)
        (obj_dir / "data").mkdir(exist_ok=True)
        (obj_dir / "knowledge").mkdir(exist_ok=True)

        # 初始化知识文件（空文件，合并时使用）
        (obj_dir / "knowledge" / "project_rules.md").write_text("", encoding="utf-8")
        (obj_dir / "knowledge" / "domain_knowledge.yaml").write_text(
            yaml.dump({"domain": "general"}, allow_unicode=True, default_flow_style=False),
            encoding="utf-8",
        )
        (obj_dir / "knowledge" / "experience_log.yaml").write_text(
            "[]\n", encoding="utf-8"
        )

        meta = {
            "name": name,
            "description": description,
            "created": datetime.now().strftime("%Y-%m-%d"),
            "status": "active",
            "sessions": [],
            "tags": [],
        }
        (obj_dir / "meta.yaml").write_text(
            yaml.dump(meta, allow_unicode=True, default_flow_style=False),
            encoding="utf-8",
        )
        logger.info("Object created", extra={"extra_data": {"name": name}})
        return meta

    # ── Project terminology aliases (Phase 1 compatibility) ─────────────

    def create_project(self, name: str, description: str = "") -> dict:
        return self.create(name, description)

    def list_projects(self, status: str = "") -> list[dict]:
        return self.list_objects(status=status)

    def get_project(self, name: str) -> Optional[dict]:
        return self.get(name)

    def get_project_dir(self, name: str) -> Optional[Path]:
        return self.get_dir(name)

    def get_project_data_dir(self, name: str) -> Optional[Path]:
        return self.get_data_dir(name)

    def get_project_knowledge_dir(self, name: str) -> Optional[Path]:
        return self.get_knowledge_dir(name)

    def rename_project(self, old_name: str, new_name: str) -> Optional[dict]:
        return self.rename(old_name, new_name)

    def archive_project(self, name: str) -> Optional[dict]:
        return self.archive(name)

    def delete_project(self, name: str) -> bool:
        return self.delete(name)

    def bind_session_to_project(self, name: str, session_id: str) -> Optional[dict]:
        return self.bind_session(name, session_id)

    def unbind_session_from_project(self, name: str, session_id: str) -> Optional[dict]:
        return self.unbind_session(name, session_id)

    def list_objects(self, status: str = "") -> list[dict]:
        """列出所有对象。可选按 status 过滤。"""
        results = []
        if not self._objects_dir.exists():
            return results
        for child in sorted(self._objects_dir.iterdir()):
            if not child.is_dir():
                continue
            meta_path = child / "meta.yaml"
            if not meta_path.exists():
                continue
            meta = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
            if status and meta.get("status") != status:
                continue
            results.append(meta)
        return results

    def get(self, name: str) -> Optional[dict]:
        """获取对象 meta 信息。"""
        meta_path = self._objects_dir / name / "meta.yaml"
        if not meta_path.exists():
            return None
        return yaml.safe_load(meta_path.read_text(encoding="utf-8"))

    def get_dir(self, name: str) -> Optional[Path]:
        """获取对象目录路径。"""
        obj_dir = self._objects_dir / name
        if obj_dir.is_dir():
            return obj_dir
        return None

    def get_data_dir(self, name: str) -> Optional[Path]:
        """获取对象的数据目录路径。"""
        obj_dir = self.get_dir(name)
        if obj_dir:
            data_dir = obj_dir / "data"
            data_dir.mkdir(exist_ok=True)
            return data_dir
        return None

    def get_knowledge_dir(self, name: str) -> Optional[Path]:
        """获取对象的知识目录路径。"""
        obj_dir = self.get_dir(name)
        if obj_dir:
            return obj_dir / "knowledge"
        return None

    def rename(self, old_name: str, new_name: str) -> Optional[dict]:
        """Rename an object (directory + update meta)."""
        old_dir = self._objects_dir / old_name
        new_dir = self._objects_dir / new_name

        if not old_dir.is_dir():
            return None
        if new_dir.exists():
            return f"error: Object '{new_name}' already exists"

        old_dir.rename(new_dir)
        meta = yaml.safe_load((new_dir / "meta.yaml").read_text(encoding="utf-8")) or {}
        meta["name"] = new_name
        self._save_meta(new_name, meta)

        logger.info("Object renamed", extra={"extra_data": {"from": old_name, "to": new_name}})
        return meta

    def archive(self, name: str) -> Optional[dict]:
        """归档对象。"""
        return self._update_status(name, "archived")

    def reactivate(self, name: str) -> Optional[dict]:
        """重新激活已归档的对象。"""
        return self._update_status(name, "active")

    def delete(self, name: str) -> bool:
        """删除对象。同时解除所有关联会话的绑定。"""
        obj_dir = self._objects_dir / name
        if not obj_dir.is_dir():
            return False

        # Cascade unbind all sessions before deleting
        meta = self.get(name)
        unbound_count = 0
        if meta:
            for session_id in meta.get("sessions", []):
                try:
                    from data_agent.session.history import update_session_meta
                    update_session_meta(session_id, {"object_name": None})
                    unbound_count += 1
                except Exception:
                    pass

        shutil.rmtree(obj_dir)
        logger.info("Object deleted", extra={"extra_data": {"name": name, "unbound_sessions": unbound_count}})
        return True

    def bind_session(self, name: str, session_id: str) -> Optional[dict]:
        """关联会话到对象。"""
        meta = self.get(name)
        if meta is None:
            return None
        sessions = meta.get("sessions", [])
        if session_id not in sessions:
            sessions.append(session_id)
            meta["sessions"] = sessions
            self._save_meta(name, meta)
        return meta

    def unbind_session(self, name: str, session_id: str) -> Optional[dict]:
        """解除会话关联。"""
        meta = self.get(name)
        if meta is None:
            return None
        sessions = meta.get("sessions", [])
        if session_id in sessions:
            sessions.remove(session_id)
            meta["sessions"] = sessions
            self._save_meta(name, meta)
        return meta

    def migrate_from_inbox(self, name: str, filename: str) -> Optional[dict]:
        """将 inbox 中的文件迁移到对象。如果对象不存在则自动创建。"""
        cfg = get_config()
        src = cfg.inbox_dir / filename
        if not src.exists():
            raise FileNotFoundError(f"Inbox 中未找到文件: {filename}")

        meta = self.get(name)
        if meta is None:
            meta = self.create(name, description=f"从 inbox 迁移: {filename}")

        data_dir = self.get_data_dir(name)
        dst = data_dir / filename
        shutil.move(str(src), str(dst))
        logger.info(
            "File migrated to object",
            extra={"extra_data": {"file": filename, "object": name}},
        )
        return meta

    def extract_session_knowledge(self, name: str, session_id: str) -> dict:
        """从对象中提取指定会话产生的知识条目数量（用于信息展示）。

        返回各类知识的条目数。
        """
        import yaml

        result = {"experience_entries": 0, "has_domain": False, "has_rules": False}
        knowledge_dir = self.get_knowledge_dir(name)
        if not knowledge_dir:
            return result

        exp_path = knowledge_dir / "experience_log.yaml"
        if exp_path.exists():
            entries = yaml.safe_load(exp_path.read_text(encoding="utf-8")) or []
            result["experience_entries"] = sum(
                1 for e in entries
                if isinstance(e, dict) and e.get("source_session_id") == session_id
            )

        domain_path = knowledge_dir / "domain_knowledge.yaml"
        if domain_path.exists():
            data = yaml.safe_load(domain_path.read_text(encoding="utf-8")) or {}
            if data.get("domain", "general") != "general":
                result["has_domain"] = True

        rules_path = knowledge_dir / "project_rules.md"
        if rules_path.exists():
            text = rules_path.read_text(encoding="utf-8").strip()
            if text:
                result["has_rules"] = True

        return result

    def _update_status(self, name: str, status: str) -> Optional[dict]:
        meta = self.get(name)
        if meta is None:
            return None
        meta["status"] = status
        self._save_meta(name, meta)
        return meta

    def _save_meta(self, name: str, meta: dict) -> None:
        meta_path = self._objects_dir / name / "meta.yaml"
        meta_path.write_text(
            yaml.dump(meta, allow_unicode=True, default_flow_style=False),
            encoding="utf-8",
        )


_object_manager: Optional[ObjectManager] = None


def get_object_manager() -> ObjectManager:
    global _object_manager
    if _object_manager is None:
        _object_manager = ObjectManager()
    return _object_manager


def get_project_manager() -> ObjectManager:
    """User-facing alias backed by ObjectManager for Phase 1 compatibility."""
    return get_object_manager()
