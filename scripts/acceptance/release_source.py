"""Checkout-portable source identity for deterministic release evidence."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path, PurePosixPath


RELEASE_PATHS = (
    "src",
    "scripts",
    "tests",
    "main.py",
    "pyproject.toml",
    "uv.lock",
    "start.bat",
    "start.sh",
)

_GENERATED_RECEIPT_NAMES = frozenset(
    {
        "analysis_browser_gate.v1.json",
        "analysis_live_provider_gate.v1.json",
        "analysis_reliability_release.v1.json",
    }
)
_HASH_OBJECT_BATCH_ARGUMENT_CHARS = 20_000


def _is_release_source(relative_path: str) -> bool:
    path = PurePosixPath(relative_path)
    if "__pycache__" in path.parts or path.suffix == ".pyc":
        return False
    if path.name in _GENERATED_RECEIPT_NAMES or path.name.endswith(".receipt.json"):
        return False
    return True


def release_source_inventory(root: Path) -> tuple[str, ...]:
    """Return sorted tracked and untracked release-source paths."""

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
            *RELEASE_PATHS,
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
    return tuple(
        sorted(
            path
            for path in paths
            if _is_release_source(path) and (root / path).is_file()
        )
    )


def _git_filtered_blob_ids(root: Path, paths: tuple[str, ...]) -> dict[str, bytes]:
    """Return current-worktree blob IDs after configured Git clean filters."""

    blob_ids: dict[str, bytes] = {}
    batch: list[str] = []
    batch_argument_chars = 0

    def flush() -> None:
        nonlocal batch, batch_argument_chars
        if not batch:
            return
        completed = subprocess.run(
            ["git", "hash-object", "--", *batch],
            cwd=root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        values = completed.stdout.splitlines()
        if len(values) != len(batch) or any(
            len(value) not in {40, 64}
            or any(byte not in b"0123456789abcdef" for byte in value)
            for value in values
        ):
            raise RuntimeError("git hash-object returned invalid blob identities")
        blob_ids.update(zip(batch, values))
        batch = []
        batch_argument_chars = 0

    for relative in paths:
        argument_chars = len(relative) + 1
        if batch and (
            len(batch) >= 128
            or batch_argument_chars + argument_chars > _HASH_OBJECT_BATCH_ARGUMENT_CHARS
        ):
            flush()
        batch.append(relative)
        batch_argument_chars += argument_chars
    flush()
    return blob_ids


def release_source_digest(root: Path) -> str:
    """Hash release paths and Git-canonical current content deterministically."""

    root = Path(root).resolve()
    selected = release_source_inventory(root)
    blob_ids = _git_filtered_blob_ids(root, selected)

    digest = hashlib.sha256()
    for relative in selected:
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(blob_ids[relative])
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"
