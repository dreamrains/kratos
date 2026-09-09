"""Static regression checks for the conclusion-only Workbench UI."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _html() -> str:
    return (ROOT / "src/data_agent/web/templates/index.html").read_text(encoding="utf-8")


def _js() -> str:
    return (ROOT / "src/data_agent/web/static/js/app.js").read_text(encoding="utf-8")


def test_workbench_has_one_verified_conclusions_primary_surface() -> None:
    html = _html()
    assert 'data-testid="workbench-verified-conclusions"' in html
    # P6/U02：主表面仍是唯一的已验证结论区；新增的待验证发现为独立默认折叠入口。
    assert html.count("trust-section") == 2
    assert 'data-testid="workbench-pending-findings"' in html
    assert "<details" in html  # 默认折叠
    for removed in ("action-board", "workbench-scope", "multifile-data-understanding", "multifile-relationships", "workbench-full-answer"):
        assert removed not in html


def test_workbench_helpers_consume_only_verified_conclusions() -> None:
    js = _js()
    assert "verifiedConclusions()" in js
    assert "workbench?.verified_conclusions" in js
    for removed in ("actionBoard()", "fullAnswer()", "workbenchScope()", "workbenchConfirmation()", "multifileWorkbench()"):
        assert removed not in js
