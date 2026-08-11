"""Tests for analysis_flow.py tools: record_data_requirement, record_analysis_spec,
record_analysis_plan, record_evidence_record."""

import json
import pytest
from unittest.mock import patch, MagicMock

from data_agent.agent.analysis_plan_contracts import (
    ANALYSIS_PLAN_CONTRACT_VERSION,
    STAGE3C0B_CONTRACT_VERSION,
    analysis_plan_tool_object_schema,
)
from data_agent.agent.analysis_execution import bind_tool_call_to_plan_step
from data_agent.agent.context import AgentContext, use_agent_context
from data_agent.session.workspace import Workspace


def _make_ctx(session_id="flow_test"):
    return AgentContext(session_id=session_id, project_name=None, workspace=Workspace())


def _stage3c0b_plan(depth=None):
    plan = {
        "contract_version": STAGE3C0B_CONTRACT_VERSION,
        "goal": "analyze banner performance",
        "method_plan": [
            {
                "step_id": "step_banner",
                "goal": "Analyze banner performance.",
                "dataset_inputs": ["banner"],
                "combination_mode": "independent",
                "expected_output": "Banner evidence",
                "evidence_requirements": ["metric"],
                "required_claim_keys": ["click_rate"],
            },
        ],
        "visualization_strategy": [],
    }
    if depth is not None:
        plan["depth"] = depth
    return plan


def _add_banner_contract(ctx):
    from data_agent.agent.analysis_state import AnalysisSessionState

    ctx.analysis_state = AnalysisSessionState(session_id=ctx.session_id, project_name=ctx.project_name)
    ctx.analysis_state.dataset_contracts.append({"dataset": "banner", "id": "contract_banner", "quality_status": "ready"})
    return ctx


def _natural_language_plan():
    return {
        "goal": "完整分析 banner 数据",
        "method_plan": [
            {
                "step_id": "step_quality",
                "goal": "检查数据质量",
                "dataset_inputs": ["banner"],
                "combination_mode": "independent",
                "expected_output": "缺失值、重复值和样本量",
            },
            {
                "step_id": "step_relationship",
                "goal": "分析收入与成本的相关关系",
                "dataset_inputs": ["banner"],
                "combination_mode": "independent",
                "expected_output": "Pearson 相关系数和 p 值",
            },
            {
                "step_id": "step_synthesis",
                "goal": "综合结论",
                "dataset_inputs": ["banner"],
                "combination_mode": "synthesis",
                "expected_output": "建议和局限",
            },
        ],
    }


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
    def test_legacy_spec_is_display_only_and_does_not_replace_active_plan(self):
        from data_agent.agent.analysis_state import AnalysisSessionState
        from data_agent.tools.analysis_flow import record_analysis_spec
        ctx = _make_ctx("spec_test")
        original_plan = {
            "id": "plan_existing",
            "contract_version": ANALYSIS_PLAN_CONTRACT_VERSION,
            "goal": "existing canonical plan",
        }
        ctx.analysis_state = AnalysisSessionState(
            session_id=ctx.session_id,
            analysis_plan=dict(original_plan),
        )
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
        assert result["analysis_plan_id"] == result["analysis_spec_id"]
        assert result["deprecated_adapter"] == "record_analysis_spec"
        assert ctx.analysis_state.analysis_plan == original_plan

    def test_legacy_spec_is_display_only_and_does_not_create_workflow(self, monkeypatch):
        from data_agent.tools.analysis_flow import record_analysis_spec
        from data_agent.tools import task_tools

        def fail_if_called(_payload):
            raise AssertionError("legacy specs must not create workflow tasks")

        monkeypatch.setattr(task_tools, "create_workflow_tasks_from_spec", fail_if_called)

        ctx = _make_ctx("legacy_spec_display_only")
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

        assert result["workflow"] == {
            "created": 0,
            "task_ids": [],
            "display_only": True,
            "reason": "deprecated_analysis_spec_adapter_display_only",
        }

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
        ctx = _add_banner_contract(_make_ctx("plan_test"))
        with use_agent_context(ctx):
            result = json.loads(record_analysis_plan(_stage3c0b_plan()))

        assert result["type"] == "analysis_plan"
        assert result["analysis_plan_id"]
        assert ctx.analysis_state.analysis_plan["contract_version"] == ANALYSIS_PLAN_CONTRACT_VERSION
        assert ctx.analysis_state.analysis_plan["migrated_from_contract_version"] == STAGE3C0B_CONTRACT_VERSION

    def test_llm_shorthand_plan_binds_the_unique_current_dataset(self):
        from data_agent.tools.analysis_flow import record_analysis_plan

        ctx = _add_banner_contract(_make_ctx("plan_unique_dataset_enrichment"))
        with patch(
            "data_agent.tools.task_tools.create_workflow_tasks_from_plan",
            return_value={"created": 1, "task_ids": [1]},
        ), use_agent_context(ctx):
            result = json.loads(record_analysis_plan({
                "goal": "Analyze banner performance",
                "method_plan": [{
                    "step": 1,
                    "task": "Check banner quality",
                    "method": "detect_data_quality",
                    "output": "Quality findings",
                    "evidence_requirements": ["缺失率", "异常值情况"],
                }],
            }))

        assert "error" not in result
        step = ctx.analysis_state.analysis_plan["method_plan"][0]
        assert step["goal"] == "Check banner quality"
        assert step["expected_output"] == "Quality findings"
        assert step["dataset_inputs"] == ["banner"]
        assert step["dataset_contract_ids"] == ["contract_banner"]
        assert ctx.analysis_state.analysis_plan["visualization_strategy"] == []

    def test_unique_dataset_replaces_unresolvable_generic_alias(self):
        from data_agent.tools.analysis_flow import record_analysis_plan

        ctx = _add_banner_contract(_make_ctx("plan_unique_alias_enrichment"))
        with patch(
            "data_agent.tools.task_tools.create_workflow_tasks_from_plan",
            return_value={"created": 1, "task_ids": [1]},
        ), use_agent_context(ctx):
            result = json.loads(record_analysis_plan({
                "goal": "Analyze banner performance",
                "method_plan": [{
                    "task": "Check banner quality",
                    "method": "detect_data_quality",
                    "expected_output": "Quality findings",
                    "dataset_inputs": ["main"],
                }],
            }))

        assert "error" not in result
        assert ctx.analysis_state.analysis_plan["method_plan"][0]["dataset_inputs"] == ["banner"]

    def test_natural_language_steps_infer_capabilities_and_clear_synthesis_inputs(self):
        """A missing inference or synthesis normalization recreates Gate F's
        unbound computations and avoidable first tool failure."""
        from data_agent.tools.analysis_flow import record_analysis_plan

        ctx = _add_banner_contract(_make_ctx("plan_natural_language_enrichment"))
        with patch(
            "data_agent.tools.task_tools.create_workflow_tasks_from_plan",
            return_value={"created": 3, "task_ids": [1, 2, 3]},
        ), use_agent_context(ctx):
            result = json.loads(record_analysis_plan(_natural_language_plan()))

        assert "error" not in result
        steps = {
            step["step_id"]: step
            for step in ctx.analysis_state.analysis_plan["method_plan"]
        }
        assert steps["step_quality"]["required_capability"] == "data.quality"
        assert steps["step_relationship"]["required_capability"] == "analysis.correlation"
        assert steps["step_quality"]["required_claim_keys"] == ["data.quality"]
        assert steps["step_relationship"]["required_claim_keys"] == [
            "analysis.correlation"
        ]
        assert steps["step_synthesis"]["dataset_inputs"] == []
        assert len(steps["step_synthesis"]["requirement_ids"]) == 1
        assert steps["step_synthesis"]["requirement_ids"][0].endswith("_limitations")

        item_properties = analysis_plan_tool_object_schema()["properties"]["method_plan"]["items"]["properties"]
        assert "method" in item_properties
        assert "required_capability" in item_properties

    def test_provider_cannot_bypass_synthesis_normalization_with_review_status(self):
        """Provider-authored review metadata is not compiler authority.

        A live run labelled its final step ``synthesis`` while leaving the
        step in independent/raw-dataset mode and supplied ``review_status``.
        That recreated raw-data scope and method/sample-size obligations for
        a step that should only consume prior evidence.
        """
        from data_agent.tools.analysis_flow import record_analysis_plan

        plan = _natural_language_plan()
        synthesis = plan["method_plan"][-1]
        synthesis["required_capability"] = "synthesis"
        synthesis["combination_mode"] = "independent"
        synthesis["evidence_requirements"] = [
            "method",
            "sample_size",
            "limitations",
        ]
        plan["review_status"] = "executable"

        ctx = _add_banner_contract(_make_ctx("plan_provider_synthesis_review"))
        with patch(
            "data_agent.tools.task_tools.create_workflow_tasks_from_plan",
            return_value={"created": 3, "task_ids": [1, 2, 3]},
        ), use_agent_context(ctx):
            result = json.loads(record_analysis_plan(plan))

        assert "error" not in result
        compiled = ctx.analysis_state.analysis_plan["method_plan"][-1]
        assert compiled["required_capability"] == "synthesis"
        assert compiled["combination_mode"] == "synthesis"
        assert compiled["dataset_inputs"] == []
        assert compiled["evidence_requirements"] == ["limitations"]
        assert compiled["required_claim_keys"] == ["synthesis"]

    def test_provider_cannot_turn_raw_data_steps_into_synthesis(self):
        """Capability semantics override a copied provider combination mode.

        A live provider marked every plan step as ``synthesis``.  The compiler
        then stripped every dataset binding and the execution scope rejected
        all profiling and analysis tools.  Only the actual synthesis
        capability may consume evidence instead of a raw dataset.
        """
        from data_agent.tools.analysis_flow import record_analysis_plan

        plan = _natural_language_plan()
        for step in plan["method_plan"]:
            step["combination_mode"] = "synthesis"
        plan["method_plan"][0]["required_capability"] = "data_quality"
        plan["method_plan"][1]["required_capability"] = "correlation"
        plan["method_plan"][2]["required_capability"] = "synthesis"
        plan["review_status"] = "executable"

        ctx = _add_banner_contract(_make_ctx("plan_provider_all_synthesis"))
        with patch(
            "data_agent.tools.task_tools.create_workflow_tasks_from_plan",
            return_value={"created": 3, "task_ids": [1, 2, 3]},
        ), use_agent_context(ctx):
            result = json.loads(record_analysis_plan(plan))

        assert "error" not in result
        steps = {
            step["step_id"]: step
            for step in ctx.analysis_state.analysis_plan["method_plan"]
        }
        assert steps["step_quality"]["combination_mode"] == "independent"
        assert steps["step_quality"]["dataset_inputs"] == ["banner"]
        assert steps["step_relationship"]["combination_mode"] == "independent"
        assert steps["step_relationship"]["dataset_inputs"] == ["banner"]
        assert steps["step_synthesis"]["combination_mode"] == "synthesis"
        assert steps["step_synthesis"]["dataset_inputs"] == []

    def test_provider_capability_shorthand_is_normalized_before_binding(self):
        """Provider-authored capability labels are not a second hidden enum.

        The live provider used ``data_quality`` and ``correlation`` even
        though the tool registry exposes ``data.quality`` and
        ``analysis.correlation``.  Keeping the shorthand verbatim makes every
        real computation look unrelated to its own plan step.
        """
        from data_agent.tools.analysis_flow import record_analysis_plan

        plan = _natural_language_plan()
        plan["method_plan"][0]["required_capability"] = "data_quality"
        plan["method_plan"][1]["required_capability"] = "correlation"
        ctx = _add_banner_contract(_make_ctx("plan_provider_capability_alias"))
        with patch(
            "data_agent.tools.task_tools.create_workflow_tasks_from_plan",
            return_value={"created": 3, "task_ids": [1, 2, 3]},
        ), use_agent_context(ctx):
            result = json.loads(record_analysis_plan(plan))

        assert "error" not in result
        steps = {
            step["step_id"]: step
            for step in ctx.analysis_state.analysis_plan["method_plan"]
        }
        assert steps["step_quality"]["required_capability"] == "data.quality"
        assert steps["step_relationship"]["required_capability"] == "analysis.correlation"

        binding = bind_tool_call_to_plan_step(
            ctx.analysis_state.analysis_plan,
            tool_name="correlation_analysis",
            capability={"capability_id": "analysis.correlation"},
            dataset_names=["banner"],
        )
        assert binding.ok is True
        assert binding.step_id == "step_relationship"

    def test_provider_tool_and_quality_check_capability_aliases_are_canonical(self):
        """Common provider spellings must bind to executable capabilities.

        A live provider emitted ``quality_check`` while naming the other
        steps after their tools.  Leaving those values as a parallel enum
        hides the missing data-quality execution from the completion guard.
        """
        from data_agent.tools.analysis_flow import record_analysis_plan

        plan = _natural_language_plan()
        plan["method_plan"] = [
            {
                "step_id": "quality",
                "goal": "check missingness and duplicates",
                "required_capability": "quality_check",
                "dataset_inputs": ["banner"],
                "expected_output": "quality findings",
            },
            {
                "step_id": "distribution",
                "goal": "describe distributions",
                "required_capability": "distribution_analysis",
                "dataset_inputs": ["banner"],
                "expected_output": "distribution findings",
            },
            {
                "step_id": "ranking",
                "goal": "rank groups",
                "required_capability": "top_n",
                "dataset_inputs": ["banner"],
                "expected_output": "ranking findings",
            },
            {
                "step_id": "relationship",
                "goal": "measure correlation",
                "required_capability": "correlation_analysis",
                "dataset_inputs": ["banner"],
                "expected_output": "relationship findings",
            },
            {
                "step_id": "synthesis",
                "goal": "synthesize findings",
                "required_capability": "synthesis",
                "dataset_inputs": ["banner"],
                "expected_output": "recommendations and limitations",
            },
        ]
        ctx = _add_banner_contract(_make_ctx("plan_provider_tool_aliases"))
        with patch(
            "data_agent.tools.task_tools.create_workflow_tasks_from_plan",
            return_value={"created": 5, "task_ids": [1, 2, 3, 4, 5]},
        ), use_agent_context(ctx):
            result = json.loads(record_analysis_plan(plan))

        assert "error" not in result
        capabilities = {
            step["step_id"]: step["required_capability"]
            for step in ctx.analysis_state.analysis_plan["method_plan"]
        }
        assert capabilities == {
            "quality": "data.quality",
            "distribution": "analysis.distribution",
            "ranking": "analysis.top_n",
            "relationship": "analysis.correlation",
            "synthesis": "synthesis",
        }

    def test_inferred_relationship_step_binds_correlation_tool(self):
        """Natural-language plans must create the exact binding required by
        automatic evidence projection, without a preferred-step hint."""
        from data_agent.tools.analysis_flow import record_analysis_plan

        ctx = _add_banner_contract(_make_ctx("plan_natural_language_binding"))
        with patch(
            "data_agent.tools.task_tools.create_workflow_tasks_from_plan",
            return_value={"created": 3, "task_ids": [1, 2, 3]},
        ), use_agent_context(ctx):
            result = json.loads(record_analysis_plan(_natural_language_plan()))

        assert "error" not in result
        binding = bind_tool_call_to_plan_step(
            ctx.analysis_state.analysis_plan,
            tool_name="correlation_analysis",
            capability={"capability_id": "analysis.correlation"},
            dataset_names=["banner"],
        )
        assert binding.ok is True
        assert binding.step_id == "step_relationship"

    def test_real_provider_relationship_wording_prefers_correlation_over_auxiliary_ols(self):
        """The live provider described one primary correlation step with OLS
        as a secondary check; classifying it as regression loses the observed
        correlation tool binding."""
        from data_agent.tools.analysis_flow import record_analysis_plan

        plan = _natural_language_plan()
        relationship = plan["method_plan"][1]
        relationship["goal"] = "收入、成本、订单、退货之间的关系分析"
        relationship["expected_output"] = "数值列间相关性矩阵 + OLS 关联检验（明确相关性非因果）"
        ctx = _add_banner_contract(_make_ctx("plan_live_relationship_wording"))
        with patch(
            "data_agent.tools.task_tools.create_workflow_tasks_from_plan",
            return_value={"created": 3, "task_ids": [1, 2, 3]},
        ), use_agent_context(ctx):
            result = json.loads(record_analysis_plan(plan))

        assert "error" not in result
        steps = {
            step["step_id"]: step
            for step in ctx.analysis_state.analysis_plan["method_plan"]
        }
        assert steps["step_relationship"]["required_capability"] == "analysis.correlation"

    def test_missing_fields(self):
        from data_agent.tools.analysis_flow import record_analysis_plan
        ctx = _make_ctx()
        with use_agent_context(ctx):
            result = json.loads(record_analysis_plan({"goal": "test"}))
        assert "error" in result

    def test_invalid_depth(self):
        from data_agent.tools.analysis_flow import record_analysis_plan
        ctx = _add_banner_contract(_make_ctx())
        with use_agent_context(ctx):
            plan = _stage3c0b_plan(depth="invalid_depth")
            result = json.loads(record_analysis_plan(plan))
        assert "error" in result
        assert "invalid_depth" in result.get("error_type", "")

    def test_valid_depth_values(self):
        from data_agent.tools.analysis_flow import record_analysis_plan
        for depth in ("lightweight", "standard", "comprehensive"):
            ctx = _add_banner_contract(_make_ctx(f"depth_{depth}"))
            with use_agent_context(ctx):
                plan = _stage3c0b_plan(depth=depth)
                result = json.loads(record_analysis_plan(plan))
            assert "error" not in result

    def test_executable_record_uses_active_route_compiler_inputs(self):
        from data_agent.tools.analysis_flow import record_analysis_plan

        ctx = _add_banner_contract(_make_ctx("plan_route_requirements"))
        ctx.analysis_state.active_scope["active_route"] = "trend"
        ctx.analysis_state.route_proposals = [{
            "id": "route_trend",
            "direction": "trend",
            "evidence_requirements": ["time_scope"],
        }]
        plan = _stage3c0b_plan()
        plan["method_plan"][0]["evidence_requirements"] = ["sample_size"]
        compiled = ctx.analysis_state.set_analysis_plan(plan)
        compiled["analysis_requirements"]["step_banner"] = [
            item
            for item in compiled["analysis_requirements"]["step_banner"]
            if item["name"] != "time_scope"
        ]

        with use_agent_context(ctx):
            result = json.loads(record_analysis_plan(compiled))

        assert result["error_type"] == "missing_compiled_hard_requirement"
        assert result["details"]["missing_requirement_ids"] == ["req_step_banner_time_scope"]


class TestAnalysisFlowControllerLegacyCutover:
    def test_controller_keeps_legacy_spec_display_only(self):
        from data_agent.agent.analysis_flow_controller import AnalysisFlowController
        from data_agent.agent.analysis_state import AnalysisSessionState

        state = AnalysisSessionState(session_id="controller_legacy_cutover")
        state.set_analysis_plan({
            "goal": "legacy trend analysis",
            "method_plan": [{"step": "trend analysis"}],
        })

        result = AnalysisFlowController("controller_legacy_cutover").ensure_workflow_tasks(state)

        assert result == {
            "created": 0,
            "task_ids": [],
            "display_only": True,
            "reason": "analysis_plan_not_executable",
            "error_type": "invalid_independent_binding",
        }


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

    def test_chinese_confidence_alias_is_normalized_to_canonical_value(self):
        """The Chinese-facing tool accepts the exact localized enum emitted
        by the live provider while persisting only the canonical value."""
        from data_agent.tools.analysis_flow import record_evidence_record

        ctx = _make_ctx("conf_chinese_high")
        with use_agent_context(ctx):
            evidence = {
                "claim": "test", "dataset": "main", "method": "trend",
                "tool_calls": [], "result_summary": "up", "limitations": "",
                "confidence": "高",
            }
            result = json.loads(record_evidence_record(json.dumps(
                evidence, ensure_ascii=False,
            )))

        assert "error" not in result
        stored = ctx.analysis_state.evidence_records[0]
        assert stored["confidence"] == "medium"
        assert stored["original_confidence"] == "high"

    def test_missing_required_fields(self):
        from data_agent.tools.analysis_flow import record_evidence_record
        ctx = _make_ctx()
        with use_agent_context(ctx):
            result = json.loads(record_evidence_record(json.dumps({"claim": "test"})))
        assert "error" in result
        assert "缺少字段" in result["error"]

    def test_unique_workspace_dataset_fills_legacy_evidence_dataset(self):
        """A unique current dataset is deterministic, not a model guess."""
        import pandas as pd

        from data_agent.tools.analysis_flow import record_evidence_record

        ctx = _make_ctx("evidence_unique_dataset")
        ctx.workspace.add("main", pd.DataFrame({"value": [1, 2, 3]}))
        evidence = {
            "claim": "Value summary is available",
            "method": "descriptive summary",
            "tool_calls": [{"name": "quick_profile"}],
            "result_summary": "Three values were inspected",
            "limitations": "Descriptive only",
            "confidence": "medium",
        }

        with use_agent_context(ctx):
            result = json.loads(record_evidence_record(json.dumps(evidence)))

        assert "error" not in result
        assert ctx.analysis_state.evidence_records[0]["dataset"] == "main"

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
                "time_frequency": "monthly",
                "missing_intervals": {"count": 0, "frequency": "monthly"},
                "window_comparability": {"status": "comparable"},
                "autocorrelation_awareness": {"status": "assessed", "lag_1": 0.2},
            }
            result = json.loads(record_evidence_record(json.dumps(evidence)))
        assert result["statistical_detail_status"] == "complete"
        assert result["statistical_detail_gaps"] == []

    @pytest.mark.parametrize(
        "significance",
        ["unknown", "unassessed", "not applicable"],
    )
    def test_explicit_significance_claim_requires_known_statistical_support(
        self,
        significance,
    ):
        from data_agent.tools.analysis_flow import record_evidence_record

        ctx = _make_ctx(f"unsupported_significance_{significance.replace(' ', '_')}")
        with use_agent_context(ctx):
            evidence = {
                "claim": "游戏B 1日留存显著高于7日留存",
                "dataset": "game_retention",
                "method": "descriptive retention analysis",
                "tool_calls": [{"name": "load_data"}],
                "result_summary": "weighted D1=42%, weighted D7=18%",
                "limitations": ["descriptive comparison only"],
                "confidence": "high",
                "significance": significance,
            }
            result = json.loads(record_evidence_record(json.dumps(evidence, ensure_ascii=False)))

        assert result["confidence_auto_downgraded"] is True
        assert any(
            "显著性表述" in warning
            for warning in result["calibration_warnings"]
        )
        assert any(
            "统计" in limitation
            for limitation in result["auto_generated_limitations"]
        )

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
