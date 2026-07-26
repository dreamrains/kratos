"""Unicode-safe process boundary for stdout/stderr and console logging.

Windows console sinks may default to a codepage (e.g. CP936/GBK) that cannot
encode every code point the agent emits (emoji, variation selectors). A
``UnicodeEncodeError`` raised mid-turn aborts the whole analysis. This module
consolidates the previously duplicated ``sys.stdout.reconfigure(...)`` blocks
from the three launchers (CLI ``main.py``, web ``entry.py``, REPL ``repl.py``)
behind one helper that:

1. Tries to reconfigure the stream to UTF-8 with ``errors="replace"`` when the
   stream supports it.
2. Falls back to wrapping the stream in :class:`ReplacementSafeTextStream`,
   which re-encodes only the offending write with ``errors="replace"`` so the
   turn survives even when the stream was captured early (e.g. by pytest) and
   cannot be reconfigured.
"""

from __future__ import annotations

import sys
from typing import Any, TextIO


class ReplacementSafeTextStream:
    """Wrap a text stream so an unrepresentable glyph never raises.

    ``write`` first attempts the write unchanged; on
    :class:`UnicodeEncodeError` it re-encodes the payload with
    ``errors="replace"`` using the wrapped stream's declared encoding (UTF-8 if
    none) and retries. All other attributes delegate to the underlying stream.
    """

    def __init__(self, stream: TextIO):
        self._stream = stream

    def write(self, text: str) -> int:
        try:
            return self._stream.write(text)
        except UnicodeEncodeError:
            encoding = getattr(self._stream, "encoding", None) or "utf-8"
            safe = text.encode(encoding, errors="replace").decode(encoding, errors="replace")
            return self._stream.write(safe)

    def flush(self) -> None:
        self._stream.flush()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._stream, name)


def configure_utf8_stdio(
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> tuple[TextIO, TextIO]:
    """Reconfigure stdio streams to UTF-8, falling back to a safe proxy.

    Each stream is reconfigured in place when possible; otherwise it is wrapped
    in :class:`ReplacementSafeTextStream`. Returns the (stdout, stderr) pair
    actually used, which callers may ignore for one-shot launcher setup.
    """
    configured = []
    for stream in (stdout or sys.stdout, stderr or sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
            configured.append(stream)
        except (AttributeError, OSError, ValueError):
            configured.append(ReplacementSafeTextStream(stream))
    return configured[0], configured[1]
