import json

from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.trust_view import build_trust_view
from data_agent.agent.trust_workflow_runtime import _evidence_fingerprint
from data_agent.web.app import create_app


def _verified_state():
    state = AnalysisSessionState(session_id="slice6", data_state="data_loaded")
    state.evidence_records = [{
        "id": "ev_1", "claim": "收入下降", "result_summary": "较前期下降 10%",
        "confidence": "high", "dataset": "orders",
    }]
    state.verification_reports = [{"passed_evidence_ids": ["ev_1"]}]
    state.verification_reports[0]["evidence_fingerprint"] = _evidence_fingerprint(state, state.evidence_records)
    return state


def test_workbench_exposes_only_current_verified_conclusions():
    view = build_trust_view(_verified_state())

    assert set(view["workbench"]) == {"verified_conclusions"}
    assert view["workbench"]["verified_conclusions"][0]["claim"] == "收入下降"


def test_stale_verification_never_projects_a_conclusion():
    state = _verified_state()
    state.evidence_records[0]["result_summary"] = "较前期下降 20%"

    assert build_trust_view(state)["workbench"]["verified_conclusions"] == []


def test_current_panel_has_no_removed_workbench_surfaces_and_keeps_output_export():
    client = create_app().test_client()
    html = client.get("/").get_data(as_text=True)
    js = client.get("/static/js/app.js").get_data(as_text=True)

    assert 'data-testid="workbench-verified-conclusions"' in html
    for removed in ("action-board", "workbench-scope", "workbench-full-answer", "workbench-breakdown", "multifile-data-understanding", "multifile-relationships"):
        assert removed not in html
    assert "exportConversation('html')" in html
    assert "exportConversation('markdown')" in html
    assert "sessionArtifacts" in html
    assert "verifiedConclusions()" in js
    for removed in (
        "actionBoard", "fullAnswer", "workbenchScope", "workbenchConfirmation",
        "multifileWorkbench", "multifileDataUnderstanding", "multifileRelationships",
    ):
        assert removed not in js


def test_workbench_scope_label_distinguishes_session_from_project_binding():
    client = create_app().test_client()
    html = client.get("/").get_data(as_text=True)

    assert "项目：" in html
    assert "会话：" in html
    assert "currentSessionId" in html
