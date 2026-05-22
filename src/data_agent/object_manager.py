from __future__ import annotations

from data_agent.project_manager import ProjectManager, get_project_manager


ObjectManager = ProjectManager


def get_object_manager() -> ProjectManager:
    return get_project_manager()
