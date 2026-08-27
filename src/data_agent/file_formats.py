"""Single source of truth for file formats that work in the current runtime."""

from __future__ import annotations


DATA_EXTENSION_TO_FORMAT = {
    ".csv": "csv",
    ".tsv": "tsv",
    ".xlsx": "excel",
    ".json": "json",
    ".jsonl": "jsonl",
}

SUPPORTED_DATA_EXTENSIONS = frozenset(DATA_EXTENSION_TO_FORMAT)
SUPPORTED_DATA_FORMATS = frozenset(DATA_EXTENSION_TO_FORMAT.values())
