"""Atomic replacement tolerant of short-lived Windows reader locks."""
from __future__ import annotations

from pathlib import Path
import time
import uuid


def write_text_atomic(destination: Path, content: str) -> None:
    """Publish a complete UTF-8 snapshot using a unique sibling temporary file."""
    temporary = destination.with_name(".atomic-" + uuid.uuid4().hex[:16] + ".tmp")
    try:
        temporary.write_text(content, encoding="utf-8")
        replace_file(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def replace_file(source: Path, destination: Path, *, attempts: int = 40) -> None:
    """Commit an already written snapshot, or propagate the failure.

    Windows reports access denied as well as sharing/lock violations when a
    reader did not grant delete sharing. Retry only replacement (never the
    operation that produced the snapshot); a permanent denial remains fatal.
    The previous destination stays intact until the atomic rename succeeds.
    """
    if attempts < 1:
        raise ValueError("replacement attempts must be positive")
    for attempt in range(attempts):
        try:
            source.replace(destination)
            return
        except PermissionError as exc:
            if getattr(exc, "winerror", None) not in {5, 32, 33} or attempt + 1 == attempts:
                raise
            time.sleep(0.025)
