"""Atomic replacement tolerant of short-lived Windows reader locks."""
from __future__ import annotations

from pathlib import Path
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar

_pending_writes = ContextVar("pending_atomic_writes", default=None)


@contextmanager
def rollback_atomic_writes():
    """Restore participating writes on a caught failure, within this context.

    This is an in-process transaction, not a crash recovery journal.
    """
    if _pending_writes.get() is not None:
        raise RuntimeError("nested disk transaction")
    before = {}
    token = _pending_writes.set(before)
    try:
        yield
    except BaseException as failure:
        _pending_writes.reset(token)
        token = None
        errors = []
        for path, original in reversed(tuple(before.items())):
            try:
                if original is None:
                    path.unlink(missing_ok=True)
                elif not path.exists() or path.read_bytes() != original:
                    write_bytes_atomic(path, original)
            except OSError as error:
                errors.append(error)
        if errors:
            raise RuntimeError("durable file rollback incomplete") from failure
        raise
    finally:
        if token is not None:
            _pending_writes.reset(token)


def _remember_destination(destination):
    before = _pending_writes.get()
    if before is not None:
        path = destination.resolve()
        if path not in before:
            before[path] = path.read_bytes() if path.exists() else None



def write_text_atomic(destination: Path, content: str) -> None:
    """Publish a complete UTF-8 snapshot using a unique sibling temporary file."""
    _remember_destination(destination)
    temporary = destination.with_name(".atomic-" + uuid.uuid4().hex[:16] + ".tmp")
    try:
        temporary.write_text(content, encoding="utf-8")
        replace_file(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def write_bytes_atomic(destination: Path, content: bytes) -> None:
    """Restore exact bytes without newline or encoding transformations."""
    _remember_destination(destination)
    temporary = destination.with_name(".atomic-" + uuid.uuid4().hex[:16] + ".tmp")
    try:
        temporary.write_bytes(content)
        replace_file(temporary,destination)
    finally:
        temporary.unlink(missing_ok=True)


def unlink_with_rollback(destination: Path) -> None:
    """Remove a file, retaining its bytes in the existing rollback context."""
    _remember_destination(destination)
    destination.unlink(missing_ok=True)


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
