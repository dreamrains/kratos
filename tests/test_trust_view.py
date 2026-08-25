"""Unit contract for the conclusion-only Workbench."""

import json

from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.trust_view import build_trust_view
from data_agent.agent.trust_workflow_runtime import _evidence_fingerprint


def test_empty_trust_view_is_only_an_empty_conclusion_contract() -> None:
    view = build_trust_view(None, session_id="missing")
    assert view == {"status": "empty", "session_id": "missing", "updated_at": "", "workbench": {"verified_conclusions": []}}


def test_workbench_projects_only_current_fingerprinted_verified_evidence() -> None:
    state = AnalysisSessionState(session_id="verified", data_state="data_loaded")
    state.evidence_records = [
        {"id": "high", "claim": "High conclusion", "confidence": "high", "result_summary": "100", "dataset": "orders"},
        {"id": "low", "claim": "Low conclusion", "confidence": "low", "result_summary": "ignore", "dataset": "orders"},
    ]
    state.verification_reports = [{"passed_evidence_ids": ["high", "low"], "evidence_fingerprint": _evidence_fingerprint(state, state.evidence_records)}]
    before = state.to_dict()

    view = build_trust_view(state)

    assert state.to_dict() == before
    assert view["status"] == "ready"
    assert view["workbench"]["verified_conclusions"] == [{"id": "high", "claim": "High conclusion", "summary": "100", "confidence": "high", "dataset": "orders"}]
    rendered = json.dumps(view)
    assert "scope" not in rendered and "confirmation" not in rendered and "artifact_path" not in rendered


def test_stale_verification_cannot_project_old_conclusion() -> None:
    state = AnalysisSessionState(session_id="stale")
    state.evidence_records = [{"id": "ev", "claim": "Changed", "confidence": "medium", "result_summary": "new"}]
    state.verification_reports = [{"passed_evidence_ids": ["ev"], "evidence_fingerprint": "sha256:stale"}]
    assert build_trust_view(state)["workbench"] == {"verified_conclusions": []}
