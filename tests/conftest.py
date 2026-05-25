"""Pytest configuration — exclude legacy scripts that use custom test() runner."""

collect_ignore = [
    "test_comparability.py",
    "test_tools_comprehensive.py",
    "test_v10_new.py",
]
