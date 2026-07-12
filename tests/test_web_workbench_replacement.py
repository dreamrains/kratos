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
    assert html.count("workbench-primary-section") == 4


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
    assert "this.trustView?.workbench?.multifile_analysis" in js


def test_workbench_keeps_validation_helpers_without_legacy_history_routes():
    html = _index_html()
    js = _app_js()

    assert "workbenchScope()" in js
    assert "workbenchConfirmation()" in js
    assert "sessionSidePanelTab === 'details'" not in html
    assert "workbenchDetails()" not in js
    assert "workbenchVerification()" not in js
    assert "trustView.history" not in html
    assert "selectTrustRoute" not in js
    assert "historyRoutes" not in html


def test_workbench_removes_trust_inspector_residue_and_raw_artifact_text():
    html = _index_html()

    assert "trust-inspector-panel" not in html
    assert "Trust Inspector" not in html
    assert 'x-text="art.path"' not in html
    assert "art.description || art.type || '产出物'" in html


def test_action_board_is_primary_surface_with_helpers():
    html = _index_html()
    js = _app_js()
    assert 'data-testid="action-board"' in html
    assert 'data-testid="action-board-confirmed"' in html
    assert 'data-testid="action-board-uncertain"' in html
    assert 'data-testid="action-board-next-steps"' in html
    assert "actionBoard()" in js and "workbench?.action_board" in js


def test_full_answer_block_uses_markdown_render():
    html = _index_html()
    js = _app_js()
    assert 'data-testid="workbench-full-answer"' in html
    assert "fullAnswer()" in js and "workbench?.full_answer" in js
    assert "renderMarkdown(fullAnswer()" in html


def test_two_sections_in_drill_down():
    html = _index_html()
    assert 'data-testid="workbench-breakdown"' in html
    for testid in ("multifile-data-understanding", "multifile-relationships"):
        assert f'data-testid="{testid}"' in html
    assert 'data-testid="multifile-analysis-directions"' not in html
    assert 'data-testid="multifile-answer-coverage"' not in html
