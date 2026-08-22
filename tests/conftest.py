"""Pytest configuration — exclude legacy scripts that use custom test() runner."""

collect_ignore = [
    "test_comparability.py",
    "test_sse_reactivity.py",
    "test_tools_comprehensive.py",
    "test_v10_new.py",
    "test_v91.py",
    "test_web_gui.py",
]
