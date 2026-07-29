"""Exact source identity shared by browser and live-provider release gates."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path, PurePosixPath


_GENERATED_RECEIPT_NAMES = frozenset(
    {
        "analysis_browser_gate.v1.json",
        "analysis_live_provider_gate.v1.json",
        "analysis_reliability_release.v1.json",
    }
)


def _is_release_source(relative_path: str) -> bool:
    path = PurePosixPath(relative_path)
    if "__pycache__" in path.parts or path.suffix == ".pyc":
        return False
    if path.name in _GENERATED_RECEIPT_NAMES or path.name.endswith(".receipt.json"):
        return False
    return True


def release_source_digest(root: Path) -> str:
    """Hash exact release-affecting paths and bytes in deterministic order."""

    root = Path(root).resolve()
    completed = subprocess.run(
        [
            "git",
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
            "--",
            "src",
            "scripts",
            "tests",
            "pyproject.toml",
        ],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    paths = {
        raw.decode("utf-8").replace("\\", "/")
        for raw in completed.stdout.split(b"\0")
        if raw
    }
    selected = sorted(path for path in paths if _is_release_source(path))

    digest = hashlib.sha256()
    for relative in selected:
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update((root / Path(*PurePosixPath(relative).parts)).read_bytes())
    return f"sha256:{digest.hexdigest()}"
