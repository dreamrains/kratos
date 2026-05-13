"""Tests for analysis_flow.py tools: record_data_requirement, record_analysis_spec,
record_analysis_plan, record_evidence_record."""

import json
import pytest
from unittest.mock import patch, MagicMock

from data_agent.agent.context import AgentContext, use_agent_context
from data_agent.session.workspace import Workspace


def _make_ctx(session_id="flow_test"):
    return AgentContext(session_id=session_id, project_name=None, workspace=Workspace())


class TestRecordDataRequirement:
    def test_valid_requirement(self):
        from data_agent.tools.analysis_flow import record_data_requirement
        ctx = _make_ctx()
        with use_agent_context(ctx):
            req = {
                "goal": "analyze revenue",
                "must_have_data": ["revenue column"],
                "recommended_data": ["time column"],
                "optional_data": ["channel"],
                "missing_limitations": ["no causal claims"],
                "minimum_viable_analysis": "describe revenue distribution",
            }
            result = json.loads(record_data_requirement(json.dumps(req)))

        assert result["type"] == "data_requirement"
        assert result["saved"].startswith("sessions/")
        assert result["requirement_id"]

    def test_missing_required_fields(self):
        from data_agent.tools.analysis_flow import record_data_requirement
        ctx = _make_ctx()
        with use_agent_context(ctx):
            result = json.loads(record_data_requirement(json.dumps({"goal": "test"})))

        assert "error" in result
        assert "缺少字段" in result["error"]

    def test_invalid_json(self):
        from data_agent.tools.analysis_flow import record_data_requirement
        result = json.loads(record_data_requirement("not json"))
        assert "error" in result

    def test_no_session_context(self):
        """Without agent context, should still return an error gracefully."""
        from data_agent.tools.analysis_flow import record_data_requirement
        # Don't set context — should fail gracefully
        result = json.loads(record_data_requirement(json.dumps({
            "goal": "test",
            "must_have_data": ["x"],
            "recommended_data": [],
            "optional_data": [],
            "missing_limitations": [],
            "minimum_viable_analysis": "describe",
        })))
        # Either saves or returns error about no session
        assert "error" in result or "saved" in result


class TestRecordAnalysisSpec:
    def test_valid_spec(self):
        from data_agent.tools.analysis_flow import record_analysis_spec
        ctx = _make_ctx("spec_test")
        with use_agent_context(ctx):
            spec = {
                "goal": "evaluate savings card",
                "question_type": "evaluation",
                "metrics": ["revenue", "retention"],
                "dimensions": ["channel"],
                "required_data": ["orders"],
                "method_plan": [
                    {"step": "profile data", "node_type": "data_check",
                     "required_capability": "data.profile", "expected_output": "summary",
                     "evidence_requirements": ["schema"]},
                ],
                "limitations": ["non-randomized"],
            }
            result = json.loads(record_analysis_spec(json.dumps(spec)))

        assert result["type"] == "analysis_spec"
        assert result["analysis_spec_id"]

    def test_missing_fields(self):
        from data_agent.tools.analysis_flow import record_analysis_spec
        ctx = _make_ctx()
        with use_agent_context(ctx):
            result = json.loads(record_analysis_spec(json.dumps({"goal": "test"})))
        assert "error" in result

    def test_invalid_json(self):
        from data_agent.tools.analysis_flow import record_analysis_spec
        result = json.loads(record_analysis_spec("invalid"))
        assert "error" in result


class TestRecordAnalysisPlan:
    def test_valid_plan(self):
        from data_agent.tools.analysis_flow import record_analysis_plan
        ctx = _make_ctx("plan_test")
        with use_agent_context(ctx):
            plan = {
                "goal": "analyze trends",
                "method_plan": [
                    {"step": "trend analysis", "required_capability": "analysis.time_series"},
                ],
                "visualization_strategy": [],
            }
            result = json.loads(record_analysis_plan(json.dumps(plan)))

        assert result["type"] == "analysis_plan"
        assert result["analysis_plan_id"]

    def test_missing_fields(self):
        from data_agent.tools.analysis_flow import record_analysis_plan
        ctx = _make_ctx()
        with use_agent_context(ctx):
            result = json.loads(record_analysis_plan(json.dumps({"goal": "test"})))
        assert "error" in result

    def test_invalid_depth(self):
        from data_agent.tools.analysis_flow import record_analysis_plan
        ctx = _make_ctx()
        with use_agent_context(ctx):
            plan = {
                "goal": "test",
                "method_plan": [{"step": "x"}],
                "visualization_strategy": [],
                "depth": "invalid_depth",
            }
            result = json.loads(record_analysis_plan(json.dumps(plan)))
        assert "error" in result
        assert "invalid_depth" in result.get("error_type", "")

    def test_valid_depth_values(self):
        from data_agent.tools.analysis_flow import record_analysis_plan
        for depth in ("lightweight", "standard", "comprehensive"):
            ctx = _make_ctx(f"depth_{depth}")
            with use_agent_context(ctx):
                plan = {
                    "goal": "test",
                    "method_plan": [{"step": "x"}],
                    "visualization_strategy": [],
                    "depth": depth,
                }
                result = json.loads(record_analysis_plan(json.dumps(plan)))
            assert "error" not in result


class TestRecordEvidenceRecord:
    def test_valid_evidence(self):
        from data_agent.tools.analysis_flow import record_evidence_record
        ctx = _make_ctx("evidence_test")
        with use_agent_context(ctx):
            evidence = {
                "claim": "Revenue increased by 15%",
                "dataset": "main",
                "method": "trend analysis",
                "tool_calls": [{"name": "analyze_time_series"}],
                "result_summary": "Revenue grew 15% YoY",
                "limitations": "Only covers 6 months",
                "confidence": "high",
            }
            result = json.loads(record_evidence_record(json.dumps(evidence)))

        assert result["type"] == "evidence_record"
        assert result["evidence_id"]
        assert result["statistical_detail_status"]

    def test_invalid_confidence(self):
        from data_agent.tools.analysis_flow import record_evidence_record
        ctx = _make_ctx()
        with use_agent_context(ctx):
            evidence = {
                "claim": "test", "dataset": "main", "method": "trend",
                "tool_calls": [], "result_summary": "up", "limitations": "",
                "confidence": "super_high",
            }
            result = json.loads(record_evidence_record(json.dumps(evidence)))
        assert "error" in result
        assert "invalid_confidence" in result.get("error_type", "")

    def test_valid_confidence_values(self):
        from data_agent.tools.analysis_flow import record_evidence_record
        for conf in ("high", "medium", "low", "speculative"):
            ctx = _make_ctx(f"conf_{conf}")
            with use_agent_context(ctx):
                evidence = {
                    "claim": "test", "dataset": "main", "method": "trend",
                    "tool_calls": [], "result_summary": "up", "limitations": "",
                    "confidence": conf,
                }
                result = json.loads(record_evidence_record(json.dumps(evidence)))
            assert "error" not in result

    def test_missing_required_fields(self):
        from data_agent.tools.analysis_flow import record_evidence_record
        ctx = _make_ctx()
        with use_agent_context(ctx):
            result = json.loads(record_evidence_record(json.dumps({"claim": "test"})))
        assert "error" in result
        assert "缺少字段" in result["error"]

    def test_invalid_json(self):
        from data_agent.tools.analysis_flow import record_evidence_record
        result = json.loads(record_evidence_record("not json"))
        assert "error" in result

    def test_statistical_detail_status_marked(self):
        from data_agent.tools.analysis_flow import record_evidence_record
        ctx = _make_ctx("stat_test")
        with use_agent_context(ctx):
            # Minimal evidence — should mark statistical details as missing
            evidence = {
                "claim": "test", "dataset": "main", "method": "trend",
                "tool_calls": [], "result_summary": "up", "limitations": "",
                "confidence": "medium",
            }
            result = json.loads(record_evidence_record(json.dumps(evidence)))
        assert result["statistical_detail_status"] == "missing"
        assert len(result["statistical_detail_gaps"]) > 0

    def test_statistical_detail_status_complete_with_all_fields(self):
        from data_agent.tools.analysis_flow import record_evidence_record
        ctx = _make_ctx("stat_complete")
        with use_agent_context(ctx):
            evidence = {
                "claim": "test", "dataset": "main", "method": "trend",
                "tool_calls": [], "result_summary": "up", "limitations": "",
                "confidence": "high",
                "metrics": {"revenue": "15% growth"},
                "sample_size": "10000",
                "time_scope": "2024-Q1 to Q4",
                "calculation_method": "YoY comparison",
                "method_detail": "year-over-year",
                "significance": "p < 0.05",
                "correlation": "0.8",
                "confidence_interval": "[12%, 18%]",
            }
            result = json.loads(record_evidence_record(json.dumps(evidence)))
        assert result["statistical_detail_status"] == "complete"
        assert result["statistical_detail_gaps"] == []

    def test_invalid_insight_type(self):
        from data_agent.tools.analysis_flow import record_evidence_record
        ctx = _make_ctx()
        with use_agent_context(ctx):
            evidence = {
                "claim": "test", "dataset": "main", "method": "trend",
                "tool_calls": [], "result_summary": "up", "limitations": "",
                "confidence": "high", "insight_type": "invalid_type",
            }
            result = json.loads(record_evidence_record(json.dumps(evidence)))
        assert "error" in result
        assert "invalid_insight_type" in result.get("error_type", "")

    def test_valid_insight_types(self):
        from data_agent.tools.analysis_flow import record_evidence_record
        for itype in ("trend", "anomaly", "contribution", "driver", "evaluation"):
            ctx = _make_ctx(f"itype_{itype}")
            with use_agent_context(ctx):
                evidence = {
                    "claim": "test", "dataset": "main", "method": "trend",
                    "tool_calls": [], "result_summary": "up", "limitations": "",
                    "confidence": "high", "insight_type": itype,
                }
                result = json.loads(record_evidence_record(json.dumps(evidence)))
            assert "error" not in result

    def test_competing_hypotheses_must_be_list(self):
        from data_agent.tools.analysis_flow import record_evidence_record
        ctx = _make_ctx()
        with use_agent_context(ctx):
            evidence = {
                "claim": "test", "dataset": "main", "method": "trend",
                "tool_calls": [], "result_summary": "up", "limitations": "",
                "confidence": "high", "competing_hypotheses": "not a list",
            }
            result = json.loads(record_evidence_record(json.dumps(evidence)))
        assert "error" in result

    def test_competing_hypotheses_valid_list(self):
        from data_agent.tools.analysis_flow import record_evidence_record
        ctx = _make_ctx()
        with use_agent_context(ctx):
            evidence = {
                "claim": "test", "dataset": "main", "method": "trend",
                "tool_calls": [], "result_summary": "up", "limitations": "",
                "confidence": "high",
                "competing_hypotheses": [{"hypothesis": "seasonality", "excluded": True}],
            }
            result = json.loads(record_evidence_record(json.dumps(evidence)))
        assert "error" not in result
