"""Pre-release migration helpers."""

from __future__ import annotations

import shutil
from pathlib import Path

from data_agent.config import get_config


def collect_legacy_project_knowledge_for_review() -> dict:
    """Copy legacy object-level knowledge files to a review area.

    The new runtime does not inject project/object knowledge. This helper keeps
    old files available for human review without silently promoting them into
    global memory.
    """
    cfg = get_config()
    sources = [cfg.objects_dir, cfg.projects_dir]
    review_root = cfg.workspace_resolved / "migration-review" / "project-knowledge"
    copied: list[str] = []

    for source_root in sources:
        if not source_root.exists():
            continue
        for knowledge_dir in source_root.glob("*/knowledge"):
            if not knowledge_dir.is_dir():
                continue
            project_name = knowledge_dir.parent.name
            target_dir = review_root / source_root.name / project_name
            target_dir.mkdir(parents=True, exist_ok=True)
            for file_path in knowledge_dir.iterdir():
                if file_path.is_file():
                    target = target_dir / file_path.name
                    shutil.copy2(file_path, target)
                    copied.append(str(target))

    return {
        "review_dir": str(review_root),
        "copied": copied,
        "copied_count": len(copied),
    }
