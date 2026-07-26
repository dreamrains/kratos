import importlib
import inspect
import io
import logging

import pytest

from data_agent.utils.logging import build_console_handler
from data_agent.utils.unicode_io import ReplacementSafeTextStream


def _record(msg: str) -> logging.LogRecord:
    return logging.LogRecord(
        name="data_agent.test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg=msg,
        args=(),
        exc_info=None,
    )


def test_replacement_safe_stream_survives_emoji_and_variation_selector():
    raw = io.BytesIO()
    cp936 = io.TextIOWrapper(raw, encoding="cp936", errors="strict")
    safe = ReplacementSafeTextStream(cp936)
    safe.write("分析中 ⚠️ 中文标点：完成")
    safe.flush()
    assert raw.getvalue()


def test_logger_captured_before_reconfigure_cannot_abort_turn():
    raw = io.BytesIO()
    captured = io.TextIOWrapper(raw, encoding="cp936", errors="strict")
    handler = build_console_handler(stream=captured)
    handler.emit(_record("进度 ⚠️"))
    assert raw.getvalue()


@pytest.mark.parametrize("module_name", [
    "data_agent.main",
    "data_agent.web.entry",
    "data_agent.agent.repl",
])
def test_supported_launcher_uses_shared_utf8_helper(module_name):
    source = inspect.getsource(importlib.import_module(module_name))
    assert "configure_utf8_stdio" in source
