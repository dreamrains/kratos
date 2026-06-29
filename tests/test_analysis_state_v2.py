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


def test_data_pool_and_bundle_round_trip():
    state = AnalysisSessionState(session_id="bundle_state")
    file_ref = state.add_data_pool_file({
        "file_id": "file_orders",
        "filename": "orders.xlsx",
        "dataset": "orders",
        "row_count": 10,
        "column_count": 3,
        "key_fields": ["user_id"],
        "time_range": {"start": "2026-04-01", "end": "2026-04-30"},
    })
    bundle = state.set_active_bundle({
        "bundle_id": "bundle_orders_v1",
        "label": "orders",
        "file_ids": [file_ref["file_id"]],
        "dataset_names": ["orders"],
        "version": 1,
        "relationship_status": "linked",
    })
    state.add_file_relationship({
        "relationship_id": "rel_orders",
        "file_ids": ["file_orders"],
        "status": "linked",
        "confidence": "high",
        "evidence": ["single file active bundle"],
    })

    restored = AnalysisSessionState.from_dict(state.to_dict(), "bundle_state")

    assert restored.data_pool[0]["file_id"] == "file_orders"
    assert restored.dataset_bundles[0]["bundle_id"] == "bundle_orders_v1"
    assert restored.active_bundle_id == bundle["bundle_id"]
    assert restored.active_bundle()["bundle_id"] == "bundle_orders_v1"
    assert restored.active_scope["active_dataset"] == "orders"
    assert restored.file_relationships[0]["status"] == "linked"


def test_bundle_helpers_upsert_by_stable_ids():
    state = AnalysisSessionState(session_id="bundle_state")

    state.add_data_pool_file({
        "id": "artifact_old",
        "file_id": "file_orders",
        "filename": "old.xlsx",
        "row_count": 10,
        "key_fields": ["user_id"],
    })
    state.add_data_pool_file({"id": "artifact_new", "file_id": "file_orders", "filename": "new.xlsx"})
    state.set_active_bundle({
        "id": "artifact_bundle_old",
        "bundle_id": "bundle_orders",
        "version": 1,
        "file_ids": ["file_orders"],
    })
    state.set_active_bundle({"id": "artifact_bundle_new", "bundle_id": "bundle_orders", "version": 2})
    state.add_file_relationship({
        "id": "artifact_rel_old",
        "relationship_id": "rel_orders",
        "status": "possibly_linked",
        "evidence": ["same user_id"],
    })
    state.add_file_relationship({"id": "artifact_rel_new", "relationship_id": "rel_orders", "status": "linked"})

    assert len(state.data_pool) == 1
    assert state.data_pool[0]["id"] == "file_orders"
    assert state.data_pool[0]["filename"] == "new.xlsx"
    assert state.data_pool[0]["row_count"] == 10
    assert state.data_pool[0]["key_fields"] == ["user_id"]
    assert len(state.dataset_bundles) == 1
    assert state.dataset_bundles[0]["id"] == "bundle_orders"
    assert state.dataset_bundles[0]["version"] == 2
    assert state.dataset_bundles[0]["file_ids"] == ["file_orders"]
    assert len(state.file_relationships) == 1
    assert state.file_relationships[0]["id"] == "rel_orders"
    assert state.file_relationships[0]["status"] == "linked"
    assert state.file_relationships[0]["evidence"] == ["same user_id"]


def test_set_active_bundle_records_bundle_ref_without_polluting_dataset_contracts():
    state = AnalysisSessionState(session_id="bundle_state")

    state.set_active_bundle({
        "bundle_id": "bundle_orders",
        "dataset_names": ["orders"],
    })

    related = state.active_scope["related_ref_ids"]
    assert related["dataset_bundles"] == ["bundle_orders"]
    assert "dataset_contracts" not in related
    assert state.active_scope["active_dataset"] == "orders"

    state.set_active_route("trend", goal="analyze trend", dataset="orders")
    state.set_active_bundle({"bundle_id": "bundle_unscoped"})

    assert state.active_scope["active_dataset"] == ""
    assert state.active_scope["active_route"] == ""
    assert state.active_scope["active_goal"] == ""
    assert state.active_scope["active_mode"] == "data_loaded"


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

    def test_active_scope_defaults_and_roundtrip(self):
        state = AnalysisSessionState(session_id="s1")

        assert state.active_scope == {
            "active_dataset": "",
            "active_route": "",
            "active_goal": "",
            "active_mode": "consulting",
            "active_turn_id": "",
            "related_ref_ids": {},
            "updated_at": "",
        }

        state.set_active_dataset("orders", related_ref_id="contract_orders")
        restored = AnalysisSessionState.from_dict(state.to_dict(), "s1")

        assert restored.active_scope["active_dataset"] == "orders"
        assert restored.active_scope["active_route"] == ""
        assert restored.active_scope["active_mode"] == "data_loaded"
        assert restored.active_scope["related_ref_ids"] == {
            "dataset_contracts": ["contract_orders"]
        }

    def test_active_scope_route_and_consulting_modes(self):
        state = AnalysisSessionState(session_id="s1")

        state.set_active_dataset("orders")
        state.set_active_route("cohort", goal="分析订单留存", related_ref_id="route_cohort")

        assert state.active_scope["active_dataset"] == "orders"
        assert state.active_scope["active_route"] == "cohort"
        assert state.active_scope["active_goal"] == "分析订单留存"
        assert state.active_scope["active_mode"] == "analysis"
        assert state.active_scope["related_ref_ids"]["route_proposals"] == ["route_cohort"]

        state.set_consulting_mode("讨论留存指标设计")

        assert state.active_scope["active_dataset"] == "orders"
        assert state.active_scope["active_route"] == ""
        assert state.active_scope["active_goal"] == "讨论留存指标设计"
        assert state.active_scope["active_mode"] == "consulting"

    def test_active_scope_related_refs_are_not_shared_between_instances(self):
        first = AnalysisSessionState(session_id="s1")
        second = AnalysisSessionState(session_id="s2")

        first.active_scope["related_ref_ids"]["dataset_contracts"] = ["contract_orders"]

        assert second.active_scope["related_ref_ids"] == {}

    def test_from_dict_normalizes_malformed_active_scope_related_refs(self):
        state = AnalysisSessionState.from_dict(
            {
                "session_id": "s1",
                "active_scope": {
                    "related_ref_ids": {
                        "bad": "not-list",
                        "ok": ["x", 1, ""],
                    },
                },
            },
            "s1",
        )

        assert state.active_scope["related_ref_ids"] == {"ok": ["x"]}

    def test_dataset_contract_with_non_string_id_does_not_add_active_ref(self):
        state = AnalysisSessionState(session_id="s1")

        state.add_dataset_contract_ref({"id": 123, "dataset": "orders"})

        assert state.active_scope["active_dataset"] == "orders"
        assert state.active_scope["related_ref_ids"] == {}

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

    def test_hypothesis_set_refs_round_trip_in_analysis_state(self):
        state = AnalysisSessionState(session_id="hyp_state")
        stored = state.add_hypothesis_set_ref({
            "id": "hyps_sales_trend",
            "dataset": "sales",
            "route": "trend",
            "count": 3,
            "status_summary": {"proposed": 3},
            "artifact_path": "sessions/hyp_state/tool_outputs/hypotheses_sales_trend.json",
        })

        assert stored["id"] == "hyps_sales_trend"

        restored = AnalysisSessionState.from_dict(state.to_dict(), "hyp_state")

        assert restored.hypothesis_sets == [{
            "id": "hyps_sales_trend",
            "dataset": "sales",
            "route": "trend",
            "count": 3,
            "status_summary": {"proposed": 3},
            "artifact_path": "sessions/hyp_state/tool_outputs/hypotheses_sales_trend.json",
            "created_at": stored["created_at"],
        }]

    def test_summary_includes_trust_refs_counts(self):
        state = AnalysisSessionState(session_id="s1")
        state.add_dataset_contract_ref({"id": "duc_main_001", "dataset": "main"})
        state.add_cleaning_log_ref({"id": "clean_main_001", "dataset": "main"})
        state.add_preview_digest_ref({"id": "preview_main_001", "dataset": "main"})
        state.add_route_proposal_ref({"id": "route_main_001", "direction": "trend"})
        state.add_verification_report_ref({"id": "verify_001", "overall_status": "pass"})
        state.add_hypothesis_set_ref({
            "id": "hyps_main_001",
            "dataset": "main",
            "route": "trend",
            "count": 3,
        })

        summary = analysis_state_summary(state)

        assert "dataset_contracts: 1" in summary
        assert "cleaning_logs: 1" in summary
        assert "preview_digests: 1" in summary
        assert "route_proposals: 1" in summary
        assert "verification_reports: 1" in summary
        assert "hypothesis_sets: 1" in summary
        assert "recent_hypothesis_sets:" in summary
        assert "id=hyps_main_001" in summary


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

    def test_legacy_relationship_update_does_not_mutate_bundle_or_diagnostic(self):
        state = AnalysisSessionState(session_id="s1")
        state.add_data_pool_file({"file_id": "file_old", "dataset": "orders_old"})
        state.add_data_pool_file({"file_id": "file_new", "dataset": "orders_new"})
        state.set_active_bundle({
            "bundle_id": "bundle_orders",
            "file_ids": ["file_old"],
            "dataset_names": ["orders_old"],
            "version": 1,
        })
        state.add_file_relationship({
            "relationship_id": "rel_orders",
            "file_ids": ["file_old", "file_new"],
            "status": "possibly_linked",
            "requires_confirmation": True,
        })
        state.add_confirmation({
            "id": "c1",
            "state_updates": json.dumps({
                "stage": "scope",
                "file_relationship_confirmation": {"relationship_id": "rel_orders"},
            }),
        })

        state.resolve_confirmation("c1", "include_in_active_bundle")

        assert state.active_bundle()["file_ids"] == ["file_old"]
        assert state.active_bundle()["dataset_names"] == ["orders_old"]
        rel = state.file_relationships[0]
        assert rel["status"] == "possibly_linked"
        assert rel["requires_confirmation"] is True
        assert "resolved" not in rel
        assert "relationship_mode" not in rel

    def test_legacy_relationship_diagnostics_survive_round_trip(self):
        original = AnalysisSessionState.from_dict({
            "session_id": "s1",
            "dataset_bundles": [{
                "bundle_id": "bundle_orders",
                "file_ids": ["file_old", "file_new"],
                "relationship_status": "possibly_linked",
            }],
            "active_bundle_id": "bundle_orders",
            "file_relationships": [{
                "relationship_id": "rel_orders",
                "file_ids": ["file_old", "file_new"],
                "status": "possibly_linked",
                "requires_confirmation": True,
            }],
        }, "s1")

        restored = AnalysisSessionState.from_dict(original.to_dict(), "s1")

        assert restored.active_bundle()["relationship_status"] == "possibly_linked"
        assert restored.file_relationships == original.file_relationships


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

    def test_summary_does_not_present_obsolete_confirmation_as_pending(self):
        state = AnalysisSessionState(session_id="s1")
        state.add_confirmation({
            "id": "legacy_relationship",
            "confirmation_type": "join_logic_confirmation",
        })

        summary = analysis_state_summary(state)

        assert "pending_confirmations: 0" in summary

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
