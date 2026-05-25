from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml

from data_agent.config import get_config
from data_agent.utils.logging import get_logger

logger = get_logger("project_manager")


class ProjectManager:
    """Manage user-facing analysis projects.

    Projects are organization containers. They do not own long-term knowledge;
    global knowledge and session context handle that separately.
    """

    def __init__(self, projects_dir: Optional[Path] = None):
        cfg = get_config()
        self._projects_dir = projects_dir or cfg.projects_dir

    def create(self, name: str, description: str = "") -> dict:
        project_dir = self._projects_dir / name
        if project_dir.exists():
            raise FileExistsError(f"Project '{name}' already exists: {project_dir}")

        project_dir.mkdir(parents=True, exist_ok=True)
        (project_dir / "data").mkdir(exist_ok=True)
        (project_dir / "tasks").mkdir(exist_ok=True)

        meta = {
            "name": name,
            "description": description,
            "created": datetime.now().strftime("%Y-%m-%d"),
            "status": "active",
            "sessions": [],
            "tags": [],
        }
        self._save_meta(name, meta)
        logger.info("Project created", extra={"extra_data": {"name": name}})
        return meta

    def list_projects(self, status: str = "") -> list[dict]:
        results = []
        if not self._projects_dir.exists():
            return results
        for child in sorted(self._projects_dir.iterdir()):
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

    def list_objects(self, status: str = "") -> list[dict]:
        """Compatibility alias for pre-release CLI code."""
        return self.list_projects(status=status)

    def get(self, name: str) -> Optional[dict]:
        meta_path = self._projects_dir / name / "meta.yaml"
        if not meta_path.exists():
            return None
        return yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}

    def get_dir(self, name: str) -> Optional[Path]:
        project_dir = self._projects_dir / name
        if project_dir.is_dir():
            return project_dir
        return None

    def get_data_dir(self, name: str) -> Optional[Path]:
        project_dir = self.get_dir(name)
        if project_dir:
            data_dir = project_dir / "data"
            data_dir.mkdir(exist_ok=True)
            return data_dir
        return None

    def extract_session_knowledge(self, name: str, session_id: str) -> dict:
        """Compatibility stub: projects no longer aggregate session knowledge."""
        return {
            "project": name,
            "session_id": session_id,
            "experience_entries": 0,
            "has_domain": False,
            "has_rules": False,
        }

    def rename(self, old_name: str, new_name: str) -> Optional[dict] | str:
        old_dir = self._projects_dir / old_name
        new_dir = self._projects_dir / new_name

        if not old_dir.is_dir():
            return None
        if new_dir.exists():
            return f"error: Project '{new_name}' already exists"

        old_dir.rename(new_dir)
        meta = yaml.safe_load((new_dir / "meta.yaml").read_text(encoding="utf-8")) or {}
        meta["name"] = new_name
        self._save_meta(new_name, meta)

        logger.info("Project renamed", extra={"extra_data": {"from": old_name, "to": new_name}})
        return meta

    def archive(self, name: str) -> Optional[dict]:
        return self._update_status(name, "archived")

    def reactivate(self, name: str) -> Optional[dict]:
        return self._update_status(name, "active")

    def delete(self, name: str) -> bool:
        project_dir = self._projects_dir / name
        if not project_dir.is_dir():
            return False

        meta = self.get(name)
        unbound_count = 0
        if meta:
            for session_id in meta.get("sessions", []):
                try:
                    from data_agent.session.history import update_session_meta

                    update_session_meta(session_id, {"project_name": None})
                    unbound_count += 1
                except Exception:
                    pass

        shutil.rmtree(project_dir)
        logger.info(
            "Project deleted",
            extra={"extra_data": {"name": name, "unbound_sessions": unbound_count}},
        )
        return True

    def bind_session(self, name: str, session_id: str) -> Optional[dict]:
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
        cfg = get_config()
        src = cfg.inbox_dir / filename
        if not src.exists():
            raise FileNotFoundError(f"Inbox file not found: {filename}")

        meta = self.get(name)
        if meta is None:
            meta = self.create(name, description=f"Imported from inbox: {filename}")

        data_dir = self.get_data_dir(name)
        if data_dir is None:
            return None
        shutil.move(str(src), str(data_dir / filename))
        logger.info(
            "File migrated to project",
            extra={"extra_data": {"file": filename, "project": name}},
        )
        return meta

    def _update_status(self, name: str, status: str) -> Optional[dict]:
        meta = self.get(name)
        if meta is None:
            return None
        meta["status"] = status
        self._save_meta(name, meta)
        return meta

    def _save_meta(self, name: str, meta: dict) -> None:
        meta_path = self._projects_dir / name / "meta.yaml"
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(
            yaml.dump(meta, allow_unicode=True, default_flow_style=False),
            encoding="utf-8",
        )


_project_manager: Optional[ProjectManager] = None


def get_project_manager() -> ProjectManager:
    global _project_manager
    cfg = get_config()
    if _project_manager is None or _project_manager._projects_dir != cfg.projects_dir:
        _project_manager = ProjectManager(projects_dir=cfg.projects_dir)
    return _project_manager
