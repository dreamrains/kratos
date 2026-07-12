from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def _index_html() -> str:
    return (ROOT / "src/data_agent/web/templates/index.html").read_text(encoding="utf-8")


def _app_js() -> str:
    return (ROOT / "src/data_agent/web/static/js/app.js").read_text(encoding="utf-8")


def _app_css() -> str:
    return (ROOT / "src/data_agent/web/static/css/app.css").read_text(encoding="utf-8")


def test_workbench_has_expected_primary_sections() -> None:
    html = _index_html()

    # action-board + workbench-scope + data-understanding + relationships
    assert html.count("workbench-primary-section") == 4
    assert 'data-testid="action-board"' in html
    assert 'data-testid="workbench-scope"' in html
    assert 'data-testid="multifile-data-understanding"' in html
    assert 'data-testid="multifile-relationships"' in html
    assert 'data-testid="multifile-analysis-directions"' not in html
    assert 'data-testid="multifile-answer-coverage"' not in html


def test_primary_sections_surface_quality_constraints_and_limitations() -> None:
    html = _index_html()

    assert "multifileDataUnderstanding().quality_findings" in html
    assert "multifileDataUnderstanding().analysis_constraints" in html
    # limitations now surface inside the action board's uncertain block
    assert 'data-testid="action-board-uncertain"' in html


def test_workbench_does_not_leak_internal_ids_or_dead_helpers() -> None:
    html = _index_html()
    js = _app_js()

    assert "task_refs" not in html
    assert "evidence_signature" not in html
    assert "sessionSidePanelTab === 'details'" not in html
    assert "workbenchDetails()" not in js
    assert "workbenchVerification()" not in js
    assert "multifileAnalysisDirections()" not in js
    assert "multifileAnswerCoverage()" not in js


def test_legacy_trust_and_history_surfaces_are_removed() -> None:
    html = _index_html()
    js = _app_js()

    for stale in (
        "Trust Inspector",
        "trust-inspector-panel",
        "trustView.history",
        "historyRoutes",
        "selectTrustRoute",
        "workbenchDecisionStatus",
        "workbenchRelationshipDiagnostics",
    ):
        assert stale not in html
        assert stale not in js


def test_artifact_links_do_not_render_raw_paths_as_text() -> None:
    html = _index_html()

    assert 'artifactUrl(art.path)' in html
    assert 'x-text="art.path"' not in html
    assert "art.description || art.type || '产出物'" in html


def test_workbench_empty_states_hide_during_loading_or_error() -> None:
    html = _index_html()
    for label in (
        "No data understanding brief yet.",
        "No relationship signal yet.",
    ):
        match = re.search(
            rf'<p x-show="(?P<condition>[^"]+)"[^>]*>{re.escape(label)}</p>',
            html,
        )
        assert match, f"{label} empty state not found"
        assert "!trustLoading" in match.group("condition")
        assert "!trustError" in match.group("condition")


def test_workbench_helpers_read_only_the_current_contract() -> None:
    js = _app_js()

    assert "this.trustView?.workbench?.multifile_analysis" in js
    assert "this.trustView?.workbench?.details" in js
    assert "this.trustView?.workbench?.current_context" not in js
    assert "this.trustView?.workbench?.trust_evidence" not in js
    assert "this.trustView?.workbench?.relationship_diagnostics" not in js


def test_workbench_css_contract_remains_responsive_and_readable() -> None:
    css = _app_css()

    assert ".workbench-panel" in css
    assert ".workbench-primary-section" in css
    assert ".workbench-item" in css
    assert ".session-side-tabs" in css
    assert ".session-side-tab" in css
    assert "overflow-wrap: anywhere" in css
