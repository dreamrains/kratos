from __future__ import annotations

import re


_STORAGE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


def require_storage_id(value: str, field_name: str) -> str:
    """Return a portable, path-safe identifier for persisted V2 records."""

    normalized = str(value or "").strip()
    if not _STORAGE_ID.fullmatch(normalized):
        raise ValueError(
            f"{field_name} must use 1-128 ASCII letters, numbers, underscores, or hyphens"
        )
    return normalized
