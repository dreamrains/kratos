from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _index_html() -> str:
    return (ROOT / "src/data_agent/web/templates/index.html").read_text(encoding="utf-8")


def _app_js() -> str:
    return (ROOT / "src/data_agent/web/static/js/app.js").read_text(encoding="utf-8")


def test_current_panel_uses_multifile_workbench_as_primary_surface():
    html = _index_html()

    assert "multifile-data-understanding" in html
    assert "multifile-relationships" in html
    assert "multifile-analysis-directions" in html
    assert "multifile-answer-coverage" in html
    assert "trustView.workbench.multifile_analysis" in html


def test_old_trust_technical_sections_are_not_primary_current_panel():
    html = _index_html()
    current_panel = html.split('x-show="sessionSidePanelTab === \'history\'"', 1)[0]

    assert 'data-testid="trust-hypotheses"' not in current_panel
    assert "trustView.risks" not in current_panel
    assert "trustView.history.routes" not in current_panel
    assert "workbench.current_context" not in current_panel


def test_multifile_workbench_helpers_read_new_view_model():
    js = _app_js()

    assert "multifileWorkbench()" in js
    assert "multifileDataUnderstanding()" in js
    assert "multifileRelationships()" in js
    assert "multifileAnalysisDirections()" in js
    assert "multifileAnswerCoverage()" in js
    assert "this.trustView?.workbench?.multifile_analysis" in js
