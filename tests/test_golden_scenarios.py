"""Golden scenario harness for consulting-style analysis flows.

These tests use a deterministic fake LLM client to drive the real AgentLoop and
real lightweight tools. They assert structured artifacts instead of snapshotting
free-form text.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from unittest.mock import patch
from pathlib import Path
from typing import Any

import pandas as pd

from data_agent.agent.context import use_agent_context
from data_agent.agent.intent import plan_turn_intent
from data_agent.agent.loop import AgentLoop
from data_agent.agent.analysis_state import AnalysisSessionState, load_analysis_state
from data_agent.agent.method_playbooks import select_playbooks
from data_agent.llm.client import Response, ToolCall
from data_agent.session.task_manager import task_manager
from data_agent.session.workspace import workspace
from data_agent.tools.registry import registry

# Import only lightweight tools needed by the harness. This registers the tools
# without requiring the full analytics dependency stack.
from data_agent.tools import analysis_flow as _analysis_flow  # noqa: F401
from data_agent.tools import task_tools as _task_tools  # noqa: F401


@dataclass
class ScenarioCase:
    name: str
    user_input: str
    responses: list[Response]
    datasets: dict[str, pd.DataFrame] = field(default_factory=dict)
    expected_intent: str = ""
    expected_playbook: str = ""


@dataclass
class ToolTrace:
    name: str
    params: dict[str, Any]
    summary: str = ""
    duration_ms: float = 0.0
    error: str = ""


@dataclass
class ScenarioResult:
    case: ScenarioCase
    final_text: str
    state: AnalysisSessionState
    tasks: list[dict[str, Any]]
    traces: list[ToolTrace]


class FakeLLMClient:
    def __init__(self, responses: list[Response]):
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def chat(self, messages, tools=None, system=None) -> Response:
        self.calls.append({"messages": messages, "tools": tools, "system": system})
        if not self._responses:
            raise AssertionError("FakeLLMClient exhausted responses")
        return self._responses.pop(0)


class ToolTraceRecorder:
    def __init__(self):
        self.enabled = False
        self.traces: list[ToolTrace] = []
        registry.add_before_hook(self._before)
        registry.add_after_hook(self._after)

    def __enter__(self):
        self.enabled = True
        return self

    def __exit__(self, exc_type, exc, tb):
        self.enabled = False

    def _before(self, name: str, params: dict) -> None:
        if self.enabled:
            self.traces.append(ToolTrace(name=name, params=dict(params)))

    def _after(self, name: str, params: dict, result, duration_ms: float) -> None:
        if not self.enabled:
            return
        for trace in reversed(self.traces):
            if trace.name == name and trace.params == dict(params) and not trace.summary:
                trace.summary = result.to_cli()
                trace.duration_ms = duration_ms
                if trace.summary.startswith('{"error"'):
                    trace.error = trace.summary
                return


def tc(name: str, arguments: dict[str, Any]) -> ToolCall:
    return ToolCall(id=f"tc_{name}_{abs(hash(json.dumps(arguments, sort_keys=True, ensure_ascii=False))) % 100000}", name=name, arguments=arguments)


def tool_response(*calls: ToolCall) -> Response:
    return Response(text="", tool_calls=list(calls))


def text_response(text: str) -> Response:
    return Response(text=text)


def run_scenario(case: ScenarioCase, tmp_path: Path) -> ScenarioResult:
    from data_agent import config
    from data_agent.config import AgentConfig

    old_cfg = config._config
    old_task_dir = task_manager._dir
    old_next_id = task_manager._next_id_val

    config._config = AgentConfig(PROJECT_DIR=tmp_path / case.name / "project", SESSIONS_DIR=tmp_path / case.name / "sessions")
    task_manager._dir = tmp_path / case.name / "tasks"
    task_manager._next_id_val = 0

    try:
        loop = AgentLoop(client=FakeLLMClient(case.responses), session_id=f"{case.name}_session", project_name=case.name)
        # The golden harness validates AgentLoop/tool/state behavior, not prompt
        # template rendering. Keeping the system prompt empty also avoids loading
        # optional heavy tool modules in the minimal test environment.
        loop._get_system_prompt = lambda: ""
        with use_agent_context(loop.context):
            for name, df in case.datasets.items():
                workspace.add(name, df)

        recorder = ToolTraceRecorder()
        with recorder:
            final_text = loop.run_turn(case.user_input)

        state = load_analysis_state(loop.session_id, case.name)
        tasks = task_manager.list_for_scope(session_id=loop.session_id, project_name=case.name)
        return ScenarioResult(case=case, final_text=final_text, state=state, tasks=tasks, traces=recorder.traces)
    finally:
        config._config = old_cfg
        task_manager._dir = old_task_dir
        task_manager._next_id_val = old_next_id


def assert_intent(case: ScenarioCase):
    context = "\n".join(
        f"- {name}: {len(df)} rows x {len(df.columns)} cols, columns: {', '.join(map(str, df.columns))}"
        for name, df in case.datasets.items()
    )
    intent = plan_turn_intent(case.user_input, context)
    assert intent.intent_type == case.expected_intent
    if case.expected_playbook:
        selection = select_playbooks(case.user_input, intent, None, context)
        assert selection.primary_playbook_id == case.expected_playbook


def assert_state(result: ScenarioResult, *, has_requirement=False, has_spec=False, min_evidence=0):
    if has_requirement:
        assert result.state.data_requirements, "expected at least one DataRequirement"
    if has_spec:
        assert result.state.analysis_plan is not None, "expected AnalysisPlan"
    assert len(result.state.evidence_records) >= min_evidence


def assert_task_workflow(result: ScenarioResult, *, min_tasks: int, node_types: set[str] | None = None):
    workflow_tasks = [t for t in result.tasks if t.get("workflow_id") or t.get("node_type")]
    assert len(workflow_tasks) >= min_tasks
    if node_types:
        present = {t.get("node_type") for t in workflow_tasks}
        assert node_types <= present


def assert_adapter_plan_is_display_only(result: ScenarioResult):
    assert result.state.analysis_plan is not None
    assert result.state.analysis_plan["contract_version"] == "analysis_plan.v1"
    assert result.state.analysis_plan["review_status"] == "display_only"
    workflow_tasks = [t for t in result.tasks if t.get("workflow_id") or t.get("node_type")]
    assert workflow_tasks == []


def assert_tool_trace(result: ScenarioResult, *, includes: set[str]):
    names = {trace.name for trace in result.traces}
    assert includes <= names


def assert_evidence_contains(result: ScenarioResult, required_terms: list[str], confidence: str | None = None):
    evidence_text = json.dumps(result.state.evidence_records, ensure_ascii=False).lower()
    for term in required_terms:
        assert term.lower() in evidence_text
    if confidence:
        assert f'"confidence": "{confidence}"' in evidence_text


def assert_final_boundary(result: ScenarioResult, required_terms: list[str]):
    text = result.final_text.lower()
    for term in required_terms:
        assert term.lower() in text
    forbidden = ["proves causality", "definitely caused", "guaranteed"]
    assert not any(term in text for term in forbidden)


def savings_card_case() -> ScenarioCase:
    requirement = {
        "goal": "evaluate whether the savings card should operate long term",
        "must_have_data": ["card purchase records", "orders", "subsidy cost", "comparable non-card users"],
        "recommended_data": ["channel", "city", "user tenure", "retention"],
        "optional_data": ["survey feedback"],
        "missing_limitations": ["without a comparable control group, the conclusion is not causal"],
        "minimum_viable_analysis": "compare card users before/after purchase and benchmark against non-card users",
    }
    confirmation_task = {
        "subject": "confirm evaluation method",
        "description": "Confirm whether to use before-after comparison plus a non-card control group.",
        "workflow_id": "wf_savings_card",
        "stage": "plan",
        "node_type": "confirmation",
        "expected_output": "confirmed method scope",
    }
    return ScenarioCase(
        name="golden_savings_card",
        user_input="I want to evaluate whether a savings card should keep operating. What data do I need?",
        expected_intent="data_requirement",
        expected_playbook="evaluation_causal",
        responses=[
            tool_response(
                tc("record_data_requirement", {"requirement_json": json.dumps(requirement)}),
                tc("task_create", confirmation_task),
            ),
            text_response(
                "Use card purchase, orders, subsidy cost, and a comparable non-card group. "
                "Limitation: without a comparable control group this is not causal. Confidence is medium until data is provided."
            ),
        ],
    )


def revenue_decline_case() -> ScenarioCase:
    df = pd.DataFrame({
        "month": ["2026-01", "2026-02", "2026-03", "2026-04"],
        "channel": ["organic", "organic", "paid", "paid"],
        "revenue": [1200, 1180, 900, 620],
        "users": [100, 98, 85, 70],
    })
    spec = {
        "goal": "explain revenue decline",
        "question_type": "diagnostic",
        "metrics": ["revenue", "users", "arpu"],
        "dimensions": ["month", "channel"],
        "time_scope": "monthly",
        "required_data": ["revenue by month and channel"],
        "method_plan": [
            {"step": "compare revenue before and after the decline", "node_type": "analysis", "required_capability": "analysis.period_compare", "expected_output": "overall revenue delta"},
            {"step": "decompose revenue by channel", "node_type": "analysis", "required_capability": "analysis.dimension_decomposition", "expected_output": "channel contribution"},
            {"step": "exclude candidate factors with weak contribution", "node_type": "evidence", "required_capability": "artifact.evidence_record", "expected_output": "bounded driver conclusion"},
        ],
        "limitations": ["synthetic sample; attribution is descriptive, not causal"],
    }
    evidence = {
        "claim": "paid channel is the main contributor to the decline",
        "dataset": "main",
        "method": "period comparison and channel decomposition",
        "tool_calls": ["record_analysis_spec"],
        "result_summary": "paid revenue fell from 900 to 620 while organic was nearly stable; price/user mix still needs validation",
        "limitations": ["descriptive attribution only", "small synthetic sample"],
        "confidence": "medium",
    }
    return ScenarioCase(
        name="golden_revenue_decline",
        user_input="为什么收入下降",
        datasets={"main": df},
        expected_intent="directed_analysis",
        expected_playbook="driver_decomposition",
        responses=[
            tool_response(
                tc("record_analysis_spec", {"spec_json": json.dumps(spec)}),
                tc("record_evidence_record", {"record_json": json.dumps(evidence)}),
            ),
            text_response(
                "Conclusion: paid channel appears to be the largest contributor. "
                "Limitation: this is descriptive attribution, not proof of causality. Confidence: medium."
            ),
            text_response(
                "Conclusion: paid channel appears to be the largest contributor. "
                "Limitation: no additional structured computation was completed, so this remains "
                "descriptive attribution rather than proof of causality. Confidence: exploratory."
            ),
        ],
    )


def funnel_case() -> ScenarioCase:
    df = pd.DataFrame({
        "step": ["visit", "signup", "trial", "pay"],
        "count": [1000, 620, 300, 120],
    })
    spec = {
        "goal": "identify the largest funnel drop",
        "question_type": "diagnostic",
        "metrics": ["step_conversion", "overall_conversion"],
        "dimensions": [],
        "time_scope": "current sample",
        "required_data": ["funnel step counts"],
        "method_plan": [
            {"subject": "run funnel_analysis on step counts", "node_type": "analysis", "required_capability": "analysis.funnel", "expected_output": "largest drop step"},
            {"subject": "record funnel evidence", "node_type": "evidence", "required_capability": "artifact.evidence_record", "expected_output": "conversion limitation"},
        ],
        "limitations": ["aggregate counts do not prove user-level journey order"],
    }
    evidence = {
        "claim": "the largest drop is signup to trial",
        "dataset": "main",
        "method": "planned funnel_analysis on aggregate step counts",
        "tool_calls": ["record_analysis_spec"],
        "result_summary": "signup to trial keeps 300/620 users, lower than visit to signup; pay conversion also needs cohort validation",
        "limitations": ["aggregate data lacks user-level sequencing"],
        "confidence": "medium",
    }
    return ScenarioCase(
        name="golden_funnel_conversion",
        user_input="分析转化漏斗哪里流失最大",
        datasets={"main": df},
        expected_intent="directed_analysis",
        expected_playbook="funnel_conversion",
        responses=[
            tool_response(
                tc("record_analysis_spec", {"spec_json": json.dumps(spec)}),
                tc("record_evidence_record", {"record_json": json.dumps(evidence)}),
            ),
            text_response(
                "The largest visible drop is signup to trial. Limitation: aggregate counts do not prove user-level paths. Confidence: medium."
            ),
            text_response(
                "The largest visible drop is signup to trial. Limitation: no additional structured "
                "computation was completed and aggregate counts do not prove user-level paths. "
                "Confidence: exploratory."
            ),
        ],
    )


def test_golden_savings_card_effect_evaluation(tmp_path):
    case = savings_card_case()
    assert_intent(case)
    result = run_scenario(case, tmp_path)

    assert_state(result, has_requirement=True)
    assert_task_workflow(result, min_tasks=1, node_types={"confirmation"})
    assert_tool_trace(result, includes={"record_data_requirement", "task_create"})
    requirement_text = json.dumps(result.state.data_requirements, ensure_ascii=False).lower()
    for term in ("control", "cost", "retention", "causal"):
        assert term in requirement_text
    assert_final_boundary(result, ["limitation", "confidence"])


@patch("data_agent.agent.llm_playbook.select_playbook_llm", lambda *a, **k: None)
def test_feature_effect_goal_selects_business_playbook_stack():
    from data_agent.agent.intent import plan_turn_intent
    from data_agent.agent.method_playbooks import select_playbooks

    ctx = (
        "- orders: 7206 rows x 8 cols, columns: user_id, payment, pay_time, user_type\n"
        "- feature_orders: 71 rows x 5 cols, columns: user_id, product_name, price, pay_time"
    )
    user_input = "分析某个产品功能对用户付费行为的影响，包含收益、付费前后变化，并告诉我还能分析哪些维度"
    intent = plan_turn_intent(user_input, ctx)

    selection = select_playbooks(user_input, intent, dataset_profile=ctx)
    ids = [selection.primary_playbook_id] + selection.supporting_playbook_ids

    assert "product_feature_analysis" in ids or "effect_evaluation" in ids
    assert "revenue_profitability" in ids
    assert "user_behavior_analysis" in ids


@patch("data_agent.agent.llm_playbook.select_playbook_llm", lambda *a, **k: None)
def test_marketing_campaign_goal_selects_business_playbook_stack():
    from data_agent.agent.intent import plan_turn_intent
    from data_agent.agent.method_playbooks import select_playbooks

    ctx = "- campaign_orders: 5000 rows x 9 cols, columns: user_id, campaign_id, revenue, cost, order_time, channel, is_exposed"
    user_input = "分析这次营销活动是否有效，包含收入、成本、用户行为变化，并给出还能继续分析的方向"
    intent = plan_turn_intent(user_input, ctx)

    selection = select_playbooks(user_input, intent, dataset_profile=ctx)
    ids = [selection.primary_playbook_id] + selection.supporting_playbook_ids

    assert "effect_evaluation" in ids
    assert "revenue_profitability" in ids
    assert "user_behavior_analysis" in ids
    assert "growth_opportunity" in ids


def test_golden_revenue_decline_attribution(tmp_path):
    case = revenue_decline_case()
    assert_intent(case)
    result = run_scenario(case, tmp_path)

    assert_state(result, has_spec=True, min_evidence=1)
    assert_adapter_plan_is_display_only(result)
    assert_tool_trace(result, includes={"record_analysis_spec", "record_evidence_record"})
    assert_evidence_contains(result, ["paid channel", "descriptive attribution"], confidence="medium")
    method_capabilities = {
        str(step.get("required_capability") or "")
        for step in result.state.analysis_plan["method_plan"]
        if isinstance(step, dict)
    }
    assert {
        "analysis.period_compare",
        "analysis.dimension_decomposition",
    } <= method_capabilities
    forbidden_claims = result.state.analysis_plan["evidence_policy"]["forbidden_claims"]
    assert any("causal" in str(claim).lower() for claim in forbidden_claims)
    assert_final_boundary(result, ["limitation", "confidence"])


def test_golden_funnel_conversion_analysis(tmp_path):
    case = funnel_case()
    assert_intent(case)
    result = run_scenario(case, tmp_path)

    assert_state(result, has_spec=True, min_evidence=1)
    assert_adapter_plan_is_display_only(result)
    assert_tool_trace(result, includes={"record_analysis_spec", "record_evidence_record"})
    assert_evidence_contains(result, ["signup to trial", "aggregate"], confidence="medium")
    task_text = json.dumps(result.state.analysis_plan, ensure_ascii=False).lower()
    assert "analysis.funnel" in task_text
    assert_final_boundary(result, ["limitation", "confidence"])
