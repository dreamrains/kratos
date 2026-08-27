"""Guard the canonical test suite against silent exclusions and live-test drift."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
REMOVED_LEGACY_RUNNERS = {
    "regression_test.py",
    "test_sse_reactivity.py",
    "test_tools_comprehensive.py",
    "test_v10_new.py",
    "test_v91.py",
    "test_web_gui.py",
    "test_web_workbench_replacement.py",
}


def test_test_tree_has_no_silent_collection_exclusions() -> None:
    conftest = TESTS / "conftest.py"
    assert not conftest.exists() or "collect_ignore" not in conftest.read_text(encoding="utf-8")


def test_removed_legacy_runners_do_not_return() -> None:
    present = {path.name for path in TESTS.rglob("*.py")}
    assert REMOVED_LEGACY_RUNNERS.isdisjoint(present)


def test_every_python_test_asset_is_pytest_discoverable() -> None:
    undiscoverable = [
        path.relative_to(ROOT).as_posix()
        for path in TESTS.rglob("*.py")
        if not path.name.startswith("test_")
    ]
    assert undiscoverable == []


def test_test_modules_do_not_embed_repo_specific_absolute_paths_or_exit() -> None:
    offenders: list[str] = []
    for path in TESTS.rglob("*.py"):
        if path == Path(__file__):
            continue
        source = path.read_text(encoding="utf-8")
        if "D:\\\\Project\\\\Daily\\\\data-agent" in source or "sys.exit(" in source:
            offenders.append(path.relative_to(ROOT).as_posix())
    assert offenders == []


def test_testing_guide_exists() -> None:
    assert (TESTS / "TESTING.md").is_file()
