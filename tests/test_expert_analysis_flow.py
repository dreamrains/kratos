import json

from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.context import AgentContext, use_agent_context
from data_agent.agent.intent import plan_turn_intent
from data_agent.agent.method_playbooks import select_playbooks
from data_agent.config import get_config
from data_agent.session.workspace import Workspace
from data_agent.tools import report


def _loaded_context(columns: str = "user_id, revenue, cost, event_time, feature_used") -> str:
    return f"- main: 1000 rows x 5 cols, columns: {columns}"


def test_objective_classifies_general_business_goals():
    from data_agent.agent.analysis_objective import infer_analysis_objective

    cases = [
        ("analyze whether the new feature changed user payment behavior", "effect_evaluation", "feature", "high", True),
        ("analyze whether this marketing campaign was effective", "effect_evaluation", "campaign", "high", True),
        ("why did revenue decline last month", "diagnosis", "revenue", "medium", False),
        ("analyze user payment frequency and preference", "description", "user", "low", False),
        ("forecast next month revenue and decide budget", "forecast", "revenue", "high", False),
    ]

    for text, question_type, business_object, risk, counterfactual in cases:
        objective = infer_analysis_objective(text, _loaded_context())
        assert objective["question_type"] == question_type
        assert objective["business_object"] == business_object
        assert objective["decision_risk"] == risk
        assert objective["requires_counterfactual"] is counterfactual
        assert "recommendations" in objective["expected_outputs"]


def test_complete_analysis_plan_has_six_stage_flow_and_visualization_strategy():
    intent = plan_turn_intent("analyze whether the new feature changed payment and revenue", _loaded_context())
    selection = select_playbooks(
        "analyze whether the new feature changed payment and revenue",
        intent,
        AnalysisSessionState(session_id="plan_flow"),
        _loaded_context(),
    )

    plan = selection.analysis_spec

    assert plan is not None
    assert "analysis_objective" in plan
    assert "playbook_stack" in plan
    assert plan["workflow_stages"] == [
        "question_framing",
        "analysis_planning",
        "exploratory_analysis",
        "validation_analysis",
        "evidence_synthesis",
        "expert_output",
    ]
    assert "visualization_strategy" in plan
    assert "required_charts" not in plan
    assert "statistical_validation_plan" in plan
    assert "next_analysis_candidates" in plan


def test_visualization_strategy_does_not_require_chart_when_table_is_better():
    from data_agent.agent.analysis_state import analysis_quality_summary

    state = AnalysisSessionState(session_id="quality_no_chart")
    state.analysis_objective = {
        "question_type": "description",
        "business_object": "revenue",
        "decision_risk": "low",
        "analysis_depth": "standard",
        "requires_counterfactual": False,
        "expected_outputs": ["conclusions", "metrics", "recommendations", "next_analysis"],
    }
    state.analysis_plan = {
        "goal": "summarize revenue",
        "visualization_strategy": [{
            "needed": False,
            "purpose": "explanation",
            "reason": "A compact KPI table is clearer than a chart.",
            "chart_type": "none",
            "fallback_presentation": "metric_table",
        }],
    }
    state.exploratory_findings.append({
        "finding": "Revenue is concentrated in two channels.",
        "status": "completed",
    })
    state.validated_findings.append({
        "claim": "Revenue summary is descriptive and does not need statistical testing.",
        "validation_status": "not_applicable",
        "validation_method": "descriptive accounting",
        "statistical_explanation": "No inferential claim was made.",
        "limitations": "No causal conclusion.",
    })
    state.evidence_records.append({
        "id": "ev_1",
        "claim": "Revenue is concentrated in two channels.",
        "dataset": "main",
        "method": "groupby sum",
        "tool_calls": ["groupby"],
        "result_summary": "Top two channels contribute 82%.",
        "limitations": "Descriptive only.",
        "confidence": "high",
        "sample_size": 1000,
        "time_scope": "2026-04",
        "calculation_method": "sum revenue by channel",
        "method_detail": "Grouped by channel and sorted by revenue.",
        "statistical_detail_status": "complete",
    })
    state.expert_insights.append({
        "conclusion": "Revenue concentration is high.",
        "business_meaning": "Two channels dominate revenue and should be monitored separately.",
        "evidence_ids": ["ev_1"],
        "statistical_explanation": "Descriptive accounting; no hypothesis test needed.",
        "limitations": "No causal claim.",
        "recommendation": "Track channel concentration weekly.",
        "recommendation_confidence": "high",
        "next_analysis": ["Analyze margin by channel."],
        "presentation_sufficiency": "sufficient",
    })

    summary = analysis_quality_summary(state)

    assert summary["status"] == "complete"
    assert "charts" not in summary["missing"]
    assert "presentation_sufficiency" not in summary["missing"]


def test_effect_evaluation_requires_counterfactual_awareness():
    from data_agent.agent.analysis_objective import infer_analysis_objective
    from data_agent.agent.analysis_state import analysis_quality_summary

    state = AnalysisSessionState(session_id="effect_gate")
    state.analysis_objective = infer_analysis_objective("evaluate whether the campaign improved revenue", _loaded_context())
    state.analysis_plan = {
        "goal": "evaluate campaign",
        "visualization_strategy": [],
    }
    state.exploratory_findings.append({"finding": "Revenue increased after campaign."})
    state.validated_findings.append({
        "claim": "Revenue increased after campaign.",
        "validation_status": "validated",
        "validation_method": "before-after comparison",
        "statistical_explanation": "p=0.04",
        "limitations": "No control group was checked.",
    })
    state.evidence_records.append({
        "id": "ev_1",
        "claim": "Revenue increased after campaign.",
        "dataset": "main",
        "method": "before-after",
        "tool_calls": ["compare_periods"],
        "result_summary": "+12%",
        "limitations": "No control group was checked.",
        "confidence": "medium",
        "sample_size": 1000,
        "time_scope": "2026-04",
        "calculation_method": "post / pre - 1",
        "method_detail": "Before-after comparison.",
        "significance": {"p_value": 0.04},
        "statistical_detail_status": "complete",
    })
    state.expert_insights.append({
        "conclusion": "Campaign revenue increased.",
        "business_meaning": "Revenue improved after launch.",
        "evidence_ids": ["ev_1"],
        "statistical_explanation": "p=0.04",
        "limitations": "No control group was checked.",
        "recommendation": "Continue monitoring.",
        "recommendation_confidence": "medium",
        "next_analysis": ["Build a control group."],
        "presentation_sufficiency": "sufficient",
    })

    summary = analysis_quality_summary(state)

    assert summary["status"] == "incomplete_can_continue"
    assert "counterfactual_check" in summary["missing"]


def test_exploratory_finding_cannot_be_final_expert_insight_without_validation():
    from data_agent.agent.analysis_state import analysis_quality_summary

    state = AnalysisSessionState(session_id="exploratory_only")
    state.analysis_objective = {
        "question_type": "diagnosis",
        "business_object": "revenue",
        "decision_risk": "medium",
        "analysis_depth": "standard",
        "requires_counterfactual": False,
        "expected_outputs": ["conclusions", "validation", "recommendations", "next_analysis"],
    }
    state.analysis_plan = {"goal": "diagnose revenue", "visualization_strategy": []}
    state.exploratory_findings.append({"finding": "New users decreased."})
    state.expert_insights.append({
        "conclusion": "New users caused revenue decline.",
        "business_meaning": "Acquisition may be the main issue.",
        "evidence_ids": [],
        "statistical_explanation": "",
        "limitations": "",
        "recommendation": "Increase acquisition budget.",
        "recommendation_confidence": "medium",
        "next_analysis": ["Check channel-level acquisition."],
        "presentation_sufficiency": "sufficient",
    })

    summary = analysis_quality_summary(state)

    assert summary["status"] == "incomplete_can_continue"
    assert "validated_findings" in summary["missing"]


def test_record_expert_insight_requires_business_meaning_and_recommendation_confidence():
    from data_agent.tools.analysis_flow import record_expert_insight

    ctx = AgentContext(session_id="expert_insight", workspace=Workspace())
    ctx.analysis_state = AnalysisSessionState(session_id="expert_insight")
    payload = {
        "conclusion": "Feature did not prove payment lift.",
        "business_meaning": "The current evidence does not justify scaling the feature.",
        "evidence_ids": ["ev_1"],
        "statistical_explanation": "p=0.25, effect size is small.",
        "limitations": "No randomized control group.",
        "recommendation": "Run matched control analysis before rollout.",
        "recommendation_confidence": "medium",
        "next_analysis": ["DID with matched controls"],
    }

    with use_agent_context(ctx):
        result = json.loads(record_expert_insight(json.dumps(payload)))

    assert result["expert_insight_id"]
    assert ctx.analysis_state.expert_insights[0]["business_meaning"].startswith("The current evidence")
    assert ctx.analysis_state.expert_insights[0]["recommendation_confidence"] == "medium"


def test_formal_report_prioritizes_expert_insights_over_evidence_index(tmp_path):
    cfg = get_config()
    old_sessions = cfg.sessions_dir
    cfg.sessions_dir = tmp_path / "sessions"
    ctx = AgentContext(session_id="expert_report_v2", workspace=Workspace())
    ctx.analysis_state = AnalysisSessionState(session_id="expert_report_v2", goal="feature effect analysis")
    ctx.analysis_state.evidence_records.append({
        "id": "ev_1",
        "claim": "Feature did not prove payment lift.",
        "dataset": "orders",
        "method": "Mann-Whitney U",
        "tool_calls": ["ab_test"],
        "result_summary": "p=0.25, d=-0.22",
        "limitations": "No randomized control group.",
        "confidence": "medium",
        "sample_size": 123,
        "time_scope": "2026-04",
        "calculation_method": "compare feature users and baseline",
        "method_detail": "Mann-Whitney U on payment amount",
        "significance": {"p_value": 0.25},
        "statistical_detail_status": "complete",
    })
    ctx.analysis_state.expert_insights.append({
        "conclusion": "Feature did not prove payment lift.",
        "business_meaning": "The feature should not be scaled based on current evidence.",
        "evidence_ids": ["ev_1"],
        "statistical_explanation": "p=0.25, effect size is negative.",
        "limitations": "Observational comparison cannot prove causality.",
        "recommendation": "Run DID or matching before rollout.",
        "recommendation_confidence": "medium",
        "next_analysis": ["Build a matched control group."],
        "presentation_sufficiency": "sufficient",
    })

    try:
        with use_agent_context(ctx):
            result = json.loads(report.generate_formal_report(format="markdown"))
        content = (tmp_path / result["artifact_path"]).read_text(encoding="utf-8")
        assert content.index("Expert Insights") < content.index("Evidence `ev_1`")
        assert "Recommendation confidence: medium" in content
        assert "The feature should not be scaled" in content
    finally:
        cfg.sessions_dir = old_sessions
