"""Slice 6 replacement guard: no legacy Workbench surfaces remain."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_current_analysis_has_only_verified_conclusions_and_exports() -> None:
    html = (ROOT / "src/data_agent/web/templates/index.html").read_text(encoding="utf-8")
    js = (ROOT / "src/data_agent/web/static/js/app.js").read_text(encoding="utf-8")
    assert 'data-testid="workbench-verified-conclusions"' in html
    assert "verifiedConclusions()" in js
    assert "exportSession" in js
    for removed in ("action-board", "multifile-data-understanding", "multifile-relationships", "workbench-breakdown", "workbench-full-answer"):
        assert removed not in html


def test_current_workbench_removes_old_helpers_and_hidden_entrypoints() -> None:
    js = (ROOT / "src/data_agent/web/static/js/app.js").read_text(encoding="utf-8")
    for removed in ("actionBoard", "fullAnswer", "workbenchScope", "workbenchConfirmation", "multifileWorkbench", "multifileDataUnderstanding", "multifileRelationships"):
        assert removed not in js
