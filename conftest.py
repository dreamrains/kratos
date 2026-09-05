"""Repository-root pytest bootstrap.

``uv run pytest tests/test_run_batch.py`` (console entry) does not put the
repository root on sys.path the way ``python -m pytest`` does, so test
modules importing ``scripts.acceptance`` fail at collection.  Insert the
root once, idempotently, for both invocation styles.
"""
from __future__ import annotations

import pathlib
import sys

_ROOT = str(pathlib.Path(__file__).resolve().parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
