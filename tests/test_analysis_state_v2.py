"""Comprehensive tests for analysis_state.py."""

import json
import pytest
from data_agent.agent.analysis_state import (
    AnalysisSessionState,
    STAGES,
    DATA_STATES,
    analysis_state_summary,
    analysis_completeness_summary,
    analysis_quality_summary,
)


class TestAnalysisSessionState:
    """Test AnalysisSessionState dataclass and transitions."""

    def test_default_values(self):
        state = AnalysisSessionState(session_id="test")
        assert state.session_id == "test"
        assert state.project_name is None
        assert state.goal == ""
        assert state.stage == "discover"
        assert state.data_state == "unknown"
        assert state.data_requirements == []
        assert state.analysis_plan is None
        assert state.analysis_spec is None
        assert state.evidence_records == []
        assert state.insight_records == []
        assert state.pending_confirmations == []
        assert state.last_recommended_paths == []

    def test_to_dict_roundtrip(self):
        state = AnalysisSessionState(
            session_id="s1",
            project_name="proj",
            goal="test goal",
            stage="execute",
            data_state="data_loaded",
        )
        d = state.to_dict()
        restored = AnalysisSessionState.from_dict(d, "s1")
        assert restored.session_id == "s1"
        assert restored.project_name == "proj"
        assert restored.goal == "test goal"
        assert restored.stage == "execute"
        assert restored.data_state == "data_loaded"

    def test_from_dict_invalid_stage_defaults_to_discover(self):
        d = {"session_id": "s1", "stage": "invalid_stage"}
        state = AnalysisSessionState.from_dict(d, "s1")
        assert state.stage == "discover"

    def test_from_dict_invalid_data_state_defaults_to_unknown(self):
        d = {"session_id": "s1", "data_state": "invalid"}
        state = AnalysisSessionState.from_dict(d, "s1")
        assert state.data_state == "unknown"

    def test_from_dict_none_collections_become_empty_lists(self):
        d = {"session_id": "s1", "data_requirements": None, "evidence_records": None}
        state = AnalysisSessionState.from_dict(d, "s1")
        assert state.data_requirements == []
        assert state.evidence_records == []

    def test_from_dict_legacy_analysis_spec_alias(self):
        d = {"session_id": "s1", "analysis_spec": {"goal": "legacy"}}
        state = AnalysisSessionState.from_dict(d, "s1")
        assert state.analysis_plan == {"goal": "legacy"}

    def test_touch_updates_timestamp(self):
        state = AnalysisSessionState(session_id="s1")
        old_ts = state.updated_at
        state.touch()
        # Updated_at should be current time string
        assert state.updated_at is not None

    def test_valid_stages(self):
        assert STAGES == {"discover", "scope", "plan", "execute", "report", "follow_up"}

    def test_valid_data_states(self):
        assert DATA_STATES == {"no_data", "data_loaded", "insufficient_data", "unknown"}


class TestAddDataRequirement:
    def test_adds_requirement_and_transitions_to_scope(self):
        state = AnalysisSessionState(session_id="s1", stage="discover")
        req = state.add_data_requirement({"goal": "analyze revenue", "must_have_data": ["revenue"]})
        assert req["goal"] == "analyze revenue"
        assert req["id"]  # auto-generated
        assert req["created_at"]  # auto-generated
        assert len(state.data_requirements) == 1
        assert state.stage == "scope"
        assert state.goal == "analyze revenue"

    def test_preserves_existing_goal_if_requirement_has_none(self):
        state = AnalysisSessionState(session_id="s1", goal="existing goal")
        state.add_data_requirement({"must_have": "data"})
        assert state.goal == "existing goal"

    def test_updates_goal_from_requirement(self):
        state = AnalysisSessionState(session_id="s1", goal="old goal")
        state.add_data_requirement({"goal": "new goal"})
        assert state.goal == "new goal"


class TestSetAnalysisPlan:
    def test_sets_plan_and_transitions_to_plan_stage(self):
        state = AnalysisSessionState(session_id="s1", stage="scope")
        plan = state.set_analysis_plan({"goal": "analyze", "method_plan": []})
        assert state.stage == "plan"
        assert state.analysis_plan == plan
        assert state.analysis_spec == plan  # aliased

    def test_set_analysis_spec_same_behavior(self):
        state = AnalysisSessionState(session_id="s1", stage="scope")
        spec = state.set_analysis_spec({"goal": "analyze"})
        assert state.stage == "plan"
        assert state.analysis_spec == spec
        assert state.analysis_plan == spec


class TestAddEvidenceRecord:
    def test_adds_record_and_transitions_to_execute(self):
        state = AnalysisSessionState(session_id="s1", stage="plan")
        rec = state.add_evidence_record({"claim": "revenue increased", "method": "trend"})
        assert len(state.evidence_records) == 1
        assert state.stage == "execute"
        assert rec["id"]
        assert rec["created_at"]

    def test_multiple_records(self):
        state = AnalysisSessionState(session_id="s1")
        state.add_evidence_record({"claim": "c1"})
        state.add_evidence_record({"claim": "c2"})
        assert len(state.evidence_records) == 2


class TestAddInsightRecord:
    def test_adds_insight_with_default_output_type(self):
        state = AnalysisSessionState(session_id="s1")
        rec = state.add_insight_record({"finding": "something interesting"})
        assert rec["output_type"] == "finding"
        assert state.stage == "execute"


class TestTrustworthyWorkflowRefs:
    def test_default_trust_refs_are_empty(self):
        state = AnalysisSessionState(session_id="s1")
        assert state.dataset_contracts == []
        assert state.cleaning_logs == []
        assert state.preview_digests == []
        assert state.route_proposals == []
        assert state.verification_reports == []

    def test_to_dict_roundtrip_trust_refs(self):
        state = AnalysisSessionState(session_id="s1")
        state.add_dataset_contract_ref({"id": "duc_main_001", "dataset": "main"})
        state.add_cleaning_log_ref({"id": "clean_main_001", "dataset": "main"})
        state.add_preview_digest_ref({"id": "preview_main_001", "dataset": "main"})
        state.add_route_proposal_ref({"id": "route_main_001", "direction": "trend"})
        state.add_verification_report_ref({"id": "verify_001", "overall_status": "pass"})

        restored = AnalysisSessionState.from_dict(state.to_dict(), "s1")

        assert restored.dataset_contracts[0]["id"] == "duc_main_001"
        assert restored.dataset_contracts[0]["dataset"] == "main"
        assert restored.dataset_contracts[0]["created_at"]
        assert restored.cleaning_logs[0]["id"] == "clean_main_001"
        assert restored.cleaning_logs[0]["dataset"] == "main"
        assert restored.cleaning_logs[0]["created_at"]
        assert restored.preview_digests[0]["id"] == "preview_main_001"
        assert restored.preview_digests[0]["dataset"] == "main"
        assert restored.preview_digests[0]["created_at"]
        assert restored.route_proposals[0]["id"] == "route_main_001"
        assert restored.route_proposals[0]["direction"] == "trend"
        assert restored.route_proposals[0]["created_at"]
        assert restored.verification_reports[0]["id"] == "verify_001"
        assert restored.verification_reports[0]["overall_status"] == "pass"
        assert restored.verification_reports[0]["created_at"]

    def test_summary_includes_trust_refs_counts(self):
        state = AnalysisSessionState(session_id="s1")
        state.add_dataset_contract_ref({"id": "duc_main_001", "dataset": "main"})
        state.add_cleaning_log_ref({"id": "clean_main_001", "dataset": "main"})
        state.add_preview_digest_ref({"id": "preview_main_001", "dataset": "main"})
        state.add_route_proposal_ref({"id": "route_main_001", "direction": "trend"})
        state.add_verification_report_ref({"id": "verify_001", "overall_status": "pass"})

        summary = analysis_state_summary(state)

        assert "dataset_contracts: 1" in summary
        assert "cleaning_logs: 1" in summary
        assert "preview_digests: 1" in summary
        assert "route_proposals: 1" in summary
        assert "verification_reports: 1" in summary


class TestConfirmations:
    def test_add_and_resolve_confirmation(self):
        state = AnalysisSessionState(session_id="s1")
        state.add_confirmation({"id": "c1", "question": "confirm?"})
        assert len(state.pending_confirmations) == 1
        assert state.pending_confirmations[0]["status"] == "pending"

        result = state.resolve_confirmation("c1", "yes")
        assert result is not None
        assert result["status"] == "resolved"
        assert result["answer"] == "yes"
        assert result["resolved_at"]

    def test_resolve_nonexistent_returns_none(self):
        state = AnalysisSessionState(session_id="s1")
        assert state.resolve_confirmation("nonexistent", "yes") is None

    def test_resolve_by_suspension_id(self):
        state = AnalysisSessionState(session_id="s1")
        state.add_confirmation({"id": "c1", "suspension_id": "susp_123"})
        result = state.resolve_confirmation("susp_123", "confirmed")
        assert result is not None

    def test_resolve_applies_state_updates(self):
        state = AnalysisSessionState(session_id="s1")
        state.add_confirmation({
            "id": "c1",
            "state_updates": json.dumps({"goal": "new goal", "stage": "execute"}),
        })
        state.resolve_confirmation("c1", "yes")
        assert state.goal == "new goal"
        assert state.stage == "execute"

    def test_resolve_state_updates_invalid_json_ignored(self):
        state = AnalysisSessionState(session_id="s1", goal="original")
        state.add_confirmation({"id": "c1", "state_updates": "not json"})
        state.resolve_confirmation("c1", "yes")
        assert state.goal == "original"

    def test_resolve_state_updates_invalid_stage_ignored(self):
        state = AnalysisSessionState(session_id="s1", stage="plan")
        state.add_confirmation({
            "id": "c1",
            "state_updates": json.dumps({"stage": "invalid_stage"}),
        })
        state.resolve_confirmation("c1", "yes")
        assert state.stage == "plan"

    def test_resolve_state_updates_invalid_data_state_ignored(self):
        state = AnalysisSessionState(session_id="s1", data_state="data_loaded")
        state.add_confirmation({
            "id": "c1",
            "state_updates": json.dumps({"data_state": "invalid"}),
        })
        state.resolve_confirmation("c1", "yes")
        assert state.data_state == "data_loaded"

    def test_resolve_updates_analysis_spec(self):
        state = AnalysisSessionState(session_id="s1")
        state.add_confirmation({
            "id": "c1",
            "state_updates": json.dumps({"analysis_spec": {"goal": "updated spec"}}),
        })
        state.resolve_confirmation("c1", "yes")
        assert state.analysis_spec == {"goal": "updated spec"}

    def test_resolve_updates_last_recommended_paths(self):
        state = AnalysisSessionState(session_id="s1")
        paths = [{"title": "path1"}]
        state.add_confirmation({
            "id": "c1",
            "state_updates": json.dumps({"last_recommended_paths": paths}),
        })
        state.resolve_confirmation("c1", "yes")
        assert state.last_recommended_paths == paths


class TestAnalysisStateSummary:
    def test_none_state_returns_empty(self):
        assert analysis_state_summary(None) == ""

    def test_summary_includes_key_fields(self):
        state = AnalysisSessionState(
            session_id="s1",
            project_name="proj",
            goal="test goal",
            stage="execute",
            data_state="data_loaded",
        )
        summary = analysis_state_summary(state)
        assert "session_id: s1" in summary
        assert "project_name: proj" in summary
        assert "stage: execute" in summary
        assert "data_state: data_loaded" in summary

    def test_summary_includes_pending_confirmations_count(self):
        state = AnalysisSessionState(session_id="s1")
        state.add_confirmation({"id": "c1"})
        summary = analysis_state_summary(state)
        assert "pending_confirmations: 1" in summary

    def test_summary_includes_recommended_paths(self):
        state = AnalysisSessionState(session_id="s1")
        state.last_recommended_paths = [{"title": "Trend Analysis"}]
        summary = analysis_state_summary(state)
        assert "Trend Analysis" in summary


class TestAnalysisCompletenessSummary:
    def test_none_state(self):
        result = analysis_completeness_summary(None)
        assert result["status"] == "incomplete"
        assert "analysis_state" in result["missing"]

    def test_empty_evidence_records(self):
        state = AnalysisSessionState(session_id="s1")
        result = analysis_completeness_summary(state)
        assert result["status"] == "incomplete"
        assert "evidence_records" in result["missing"]

    def test_complete_with_evidence(self):
        state = AnalysisSessionState(session_id="s1")
        state.add_evidence_record({
            "claim": "test",
            "dataset": "main",
            "method": "trend",
            "tool_calls": [],
            "result_summary": "up",
            "limitations": "",
            "confidence": "high",
        })
        result = analysis_completeness_summary(state)
        assert result["status"] == "complete"
        assert result["counts"]["evidence_records"] == 1


class TestAnalysisQualitySummary:
    def test_none_state(self):
        result = analysis_quality_summary(None)
        assert result["status"] == "incomplete_can_continue"

    def test_missing_statistical_details(self):
        state = AnalysisSessionState(session_id="s1")
        state.add_evidence_record({
            "claim": "test", "dataset": "main", "method": "trend",
            "tool_calls": [], "result_summary": "up", "limitations": "", "confidence": "high",
        })
        result = analysis_quality_summary(state)
        assert result["status"] == "incomplete_can_continue"
        # Should have missing statistical detail fields
        assert len(result["missing"]) > 0

    def test_complete_with_full_details(self):
        state = AnalysisSessionState(session_id="s1")
        state.add_evidence_record({
            "claim": "test", "dataset": "main", "method": "trend",
            "tool_calls": [], "result_summary": "up", "limitations": "", "confidence": "high",
            "sample_size": "1000",
            "time_scope": "2024-01 to 2024-12",
            "calculation_method": "linear regression",
            "method_detail": "OLS",
        })
        result = analysis_quality_summary(state)
        assert result["status"] == "complete"
        assert result["counts"]["evidence_records"] == 1
