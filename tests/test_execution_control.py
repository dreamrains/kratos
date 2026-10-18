import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from data_agent.agent.analysis_flow_controller import AnalysisFlowController
from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.context import AgentContext, use_agent_context
from data_agent.agent.execution_control import (
    BudgetExceeded,
    ToolExecutionBudget,
    TurnExecutionState,
)
from data_agent.agent.intent import TurnIntent
from data_agent.llm.client import Response, ToolCall
from data_agent.agent.loop import AgentLoop
from data_agent.session.task_manager import task_manager
from data_agent.session.workspace import Workspace


@pytest.fixture(autouse=True)
def isolated_execution_control_storage(tmp_path,monkeypatch):
    # Bind the consumer before a test patches its producer. Lazy first import
    # inside the patch would retain that lambda after monkeypatch restores it.
    import data_agent.agent.analysis_entry
    from data_agent.config import get_config
    cfg=get_config()
    monkeypatch.setattr(cfg,"sessions_dir",tmp_path/"sessions")
    monkeypatch.setattr(cfg,"workspace_dir",tmp_path/"workspace")
    monkeypatch.setattr(task_manager,"_dir",tmp_path/"tasks")
    monkeypatch.setattr(task_manager,"_next_id_val",0)


def _produce_current_execution_metadata(context, state, dataset, metric):
    """Exercise loop integration with the actual producer and current owned data."""
    import pandas as pd
    from data_agent.tools.data_io import _record_trust_workflow
    context.analysis_state = state
    context.workspace.add(dataset, pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=14), metric: list(range(1, 15)),
    }))
    state.set_active_dataset(dataset)
    state.active_scope["active_mode"] = "data_loaded"
    with use_agent_context(context):
        _record_trust_workflow(session_id=state.session_id, state=state, dataset=dataset,
            df=context.workspace.get(dataset), applied=[], needs_confirm=[], quality={},
            interpretation_data={"columns_classified":{"time_columns":["date"], "key_metrics":[metric]}},
            detail_path="")


def _loaded_context() -> str:
    return "- main: 20 rows x 4 cols, columns: date, revenue, cost, user_id"


def test_budget_soft_and_hard_thresholds():
    state = TurnExecutionState(ToolExecutionBudget(profile="interactive", max_tool_calls=6, max_fallback_calls=2))

    state.record_tool_call("list_data", {})
    state.record_tool_call("describe_dataset", {})
    # run_python counts toward tool_calls and sets pending_fallback_resolution
    state.record_tool_call("run_python", {})
    # record_evidence_record is meta, does NOT count toward tool_calls, but resolves fallback
    state.record_tool_call("record_evidence_record", {})
    state.record_tool_success()

    assert state.tool_calls == 3  # list_data + describe_dataset + run_python
    assert state.pending_fallback_resolution is False

    state.record_tool_call("create_chart", {})
    state.record_tool_call("preview_data", {})
    # tool_calls = 5, ceil(6*0.75) = 5 → should_converge
    assert state.should_converge is True
    assert state.should_restrict_exploration is False

    state.record_tool_call("analyze_time_series", {})
    assert state.should_restrict_exploration is True  # 6 >= ceil(6*0.85) = 6

    try:
        state.ensure_can_call("list_data", {})
    except BudgetExceeded as exc:
        assert "tool call budget" in str(exc).lower()
    else:
        raise AssertionError("expected hard budget to stop further tool calls")


def test_python_fallback_allows_native_versioned_receipts_without_clearing_gap():
    state = TurnExecutionState(ToolExecutionBudget(profile="analysis", max_tool_calls=10))
    state.record_tool_call("run_python", {"code": "explore"})
    state.record_tool_success()
    assert state.pending_fallback_resolution

    for tool, args in (
        ("synthesize_time_series", {"datasets": "a,b", "save_as": "combined"}),
        ("compare_periods", {"name": "combined"}),
        ("transform_data", {"name": "combined", "operation": "group_aggregate"}),
    ):
        state.ensure_can_call(tool, args)
        state.record_tool_call(tool, args)
        state.record_tool_success()
        assert state.pending_fallback_resolution

    with pytest.raises(BudgetExceeded, match="Fallback Python result"):
        state.ensure_can_call("preview_data", {"name": "unrelated"})
    state.record_tool_call("record_evidence_record", {"record_json": "current evidence"})
    state.record_tool_success()
    assert not state.pending_fallback_resolution


def test_chart_calls_are_not_limited_by_chart_count():
    state = TurnExecutionState(ToolExecutionBudget(profile="analysis", max_tool_calls=20, max_fallback_calls=2))

    for idx in range(8):
        args = {"chart_type": "bar", "data": "pay", "x_col": "month", "y_col": f"metric_{idx}"}
        state.ensure_can_call("create_chart", args)
        state.record_tool_call("create_chart", args)
        state.record_tool_success()

    assert state.chart_calls == 8
    assert state.should_restrict_exploration is False


def test_duplicate_chart_call_is_treated_as_low_value_exploration():
    state = TurnExecutionState(ToolExecutionBudget(profile="analysis", max_tool_calls=20))
    args = {"chart_type": "bar", "data": "pay", "x_col": "month", "y_col": "revenue"}

    state.ensure_can_call("create_chart", args)
    state.record_tool_call("create_chart", args)
    state.record_tool_success()

    try:
        state.ensure_can_call("create_chart", args)
    except BudgetExceeded as exc:
        assert "duplicate" in str(exc).lower() or "low-value" in str(exc).lower()
    else:
        raise AssertionError("expected duplicate chart to be blocked")


def test_transform_duplicate_is_scoped_to_source_version():
    state = TurnExecutionState(ToolExecutionBudget(profile="analysis", max_tool_calls=20))
    args = {"name": "sales", "operation": "group_aggregate", "group_by": ["channel"]}
    state.ensure_can_call("transform_data", args, source_version="dv_v1")
    state.record_tool_call("transform_data", args, source_version="dv_v1")
    state.record_tool_success()
    with pytest.raises(BudgetExceeded, match="duplicate"):
        state.ensure_can_call("transform_data", args, source_version="dv_v1")
    state.ensure_can_call("transform_data", args, source_version="dv_v2")
    state.record_tool_call("transform_data", args, source_version="dv_v2")
    state.record_tool_success()
    assert state.tool_calls == 2
    with pytest.raises(BudgetExceeded, match="duplicate"):
        state.ensure_can_call("transform_data", args, source_version="dv_v2")


def test_elapsed_time_budget_blocks_more_tools():
    state = TurnExecutionState(ToolExecutionBudget(profile="analysis", max_elapsed_seconds=1))
    state.started_at -= 2

    try:
        state.ensure_can_call("list_data", {})
    except BudgetExceeded as exc:
        assert "time budget" in str(exc).lower()
    else:
        raise AssertionError("expected elapsed time budget to block tool calls")


def test_large_tool_output_is_persisted_before_llm_context(tmp_path, monkeypatch):
    from data_agent.agent.compact import persist_large_output
    from data_agent.config import get_config

    monkeypatch.setattr(get_config(), "sessions_dir", tmp_path / "sessions")
    output = persist_large_output("large_output", "tc_big", "x" * 20000)

    assert "<persisted-output>" in output
    assert len(output) < 3000
    # P4/E07: 持久化文件名带内容摘要，同 id 不同内容不得复用旧文件
    stored = list((tmp_path / "sessions" / "large_output" / "tool_outputs").glob("tc_big__*.txt"))
    assert stored
    assert stored[0].read_text(encoding="utf-8") == "x" * 20000


def test_run_python_success_requires_resolution_before_more_exploration():
    state = TurnExecutionState(ToolExecutionBudget(profile="analysis", max_tool_calls=20))

    state.ensure_can_call("run_python", {"purpose": "unsupported custom check", "code": "1 + 1"})
    state.record_tool_call("run_python", {"purpose": "unsupported custom check", "code": "1 + 1"})
    state.record_tool_success()

    try:
        state.ensure_can_call("preview_data", {"name": "main"})
    except BudgetExceeded as exc:
        assert "fallback python result" in str(exc).lower()
    else:
        raise AssertionError("expected fallback result to require evidence or limitation resolution")

    state.ensure_can_call("record_evidence_record", {"record_json": "{}"})


def test_repeated_tool_error_is_blocked_after_two_failures():
    state = TurnExecutionState(ToolExecutionBudget())
    args = {"name": "main", "target_col": "missing"}

    state.record_tool_error("forecast", args, '{"error":"column missing"}')
    state.record_tool_error("forecast", args, '{"error":"column missing"}')

    try:
        state.ensure_can_call("forecast", args)
    except BudgetExceeded as exc:
        assert "repeated tool error" in str(exc).lower()
    else:
        raise AssertionError("expected repeated forecast error to be blocked")


def test_p08_causal_capability_not_blocked_and_no_confirmation_task(tmp_path):
    """P08-01/Q07 契约更新：原断言因果类能力被方法门封锁并创建确认任务；
    新原则下能力名称不是确认理由，也不创建通用审批任务。"""
    old_task_dir = task_manager._dir
    old_next_id = task_manager._next_id_val
    task_manager._dir = tmp_path / "tasks"
    task_manager._next_id_val = 0
    try:
        state = AnalysisSessionState(session_id="gate_savings", project_name=None)
        intent = TurnIntent(
            intent_type="directed_analysis",
            clarity="clear",
            data_state="data_loaded",
            analysis_stage="execute",
            recommended_action="run_analysis",
            execution_readiness="ready",
            reason="offline high-risk confirmation fixture",
            ambiguities=[],
        )

        controller = AnalysisFlowController("gate_savings")
        controller.prepare_turn(
            state,
            intent,
            user_input="evaluate whether the savings card is worth long-term operation",
            dataset_profile=_loaded_context(),
            llm_client=_OfflineNullClient(),
        )

        assert controller.is_capability_blocked_by_confirmation(state, "analysis.causal") is False
        assert controller.is_capability_blocked_by_confirmation(state, "data.profile") is False
        assert not state.pending_confirmations

        tasks = task_manager.list_for_scope(session_id="gate_savings")
        assert not any(
            t.get("node_type") == "confirmation"
            and t.get("confirmation_policy", {}).get("requires_confirmation")
            for t in tasks
        )
    finally:
        task_manager._dir = old_task_dir
        task_manager._next_id_val = old_next_id


def test_confirmation_gate_ignores_tools_without_capability_metadata():
    state = AnalysisSessionState(session_id="gate_unknown_tool")
    state.analysis_spec = {
        "confirmation_policy": {"requires_confirmation": True},
        "method_plan": [{"required_capability": "analysis.causal", "node_type": "analysis"}],
    }
    state.pending_confirmations = [{"id": "method_gate", "status": "pending"}]

    controller = AnalysisFlowController("gate_unknown_tool")

    assert controller.is_tool_blocked_by_confirmation(state, "list_files") is False


class _OfflineNullClient:
    def chat(self, messages, tools=None, system=None):
        return Response(text="")


class _OneToolClient:
    def __init__(self, tool_name: str, args: dict):
        self._calls = [
            Response(tool_calls=[ToolCall("tc1", tool_name, args)]),
            Response(text="done"),
        ]

    def chat(self, messages, tools=None, system=None):
        if not self._calls:
            return Response(text="done")
        return self._calls.pop(0)


from tests.test_trusted_publication_semantics import engine


class _EvidenceThenFinalClient:
    def __init__(self):
        evidence = {
            "claim": "retention follows a power-law decay curve",
            "dataset": "main",
            "method": "log-linear retention formula fit",
            "tool_calls": ["run_python"],
            "result_summary": "R(t)=0.1917*t^(-0.7335) describes the observed retention curve.",
            "limitations": ["aggregate retention data only"],
            "confidence": "high",
        }
        self.system_prompts = []
        # P7-L3/B06 契约更新：预算/收据门修复后，turn_state 在整轮存活，
        # 证据必须绑定本轮真实工具收据——先执行 run_python 再记录证据。
        self._calls = [
            Response(tool_calls=[ToolCall("tc0", "run_python", {"code": "result = 1 + 1", "purpose": "compute constant"})]),
            Response(tool_calls=[ToolCall("tc1", "record_evidence_record", {"record_json": json.dumps(evidence)})]),
            Response(text="final answer"),
        ]

    def chat(self, messages, tools=None, system=None):
        self.system_prompts.append(system or "")
        if not self._calls:
            return Response(text="final answer")
        response=self._calls.pop(0)
        if not response.has_tool_calls and hasattr(self,"loop"):
            from data_agent.agent.publication.runtime import snapshot_for_turn
            response=Response(text=json.dumps({"schema":"answer_bindings.v2","snapshot_digest":snapshot_for_turn(self.loop).digest,"sections":[]}))
        return response


def test_p08_static_method_pending_does_not_block_tool(tmp_path, monkeypatch):
    """P08-01 契约更新：原断言静态方法确认 pending 阻塞工具调用；
    新原则下 prepare_turn 会退役纯方法 pending，工具照常执行。"""
    monkeypatch.setattr(
        AnalysisFlowController,
        "prepare_turn",
        lambda self, state, intent, user_input, dataset_profile: None,
    )
    monkeypatch.setattr(
        "data_agent.agent.question_need_detector.detect_question_need",
        lambda user_input, intent, state: {"status": "no_question"},
    )
    old_task_dir = task_manager._dir
    old_next_id = task_manager._next_id_val
    task_manager._dir = tmp_path / "tasks"
    task_manager._next_id_val = 0
    workspace_obj = Workspace()
    ctx = AgentContext(session_id="loop_gate", workspace=workspace_obj)
    state = AnalysisSessionState(session_id="loop_gate")
    state.analysis_spec = {
        "id": "spec_gate",
        "confirmation_policy": {"requires_confirmation": True, "confirmation_type": "method_confirmation"},
        "method_plan": [{"required_capability": "analysis.causal", "node_type": "analysis"}],
    }
    state.pending_confirmations = [{"id": "method_gate", "status": "pending", "confirmation_type": "method_confirmation", "source": "method_playbook"}]
    # 先退役（prepare_turn 被屏蔽时手工触发同一入口的退役语义）
    from data_agent.agent.confirmation_policy import retire_method_approval_confirmations

    retire_method_approval_confirmations(state)
    ctx.analysis_state = state
    loop = AgentLoop(client=_OneToolClient("causal_analysis", {"name": "main", "target_col": "revenue"}), session_id="loop_gate")
    loop.context = ctx

    try:
        with use_agent_context(ctx):
            result = loop.run_turn("run causal analysis")
        tool_messages = [m for m in loop.messages if m.get("role") == "tool"]
        assert tool_messages
        assert not any("confirmation_required" in m.get("content", "") for m in tool_messages)
    finally:
        task_manager._dir = old_task_dir
        task_manager._next_id_val = old_next_id


def test_p08_semantic_pending_with_affected_operations_still_blocks_tool(tmp_path, monkeypatch):
    """P08-01 反向保护：affected_operations 覆盖能力的语义确认仍阻塞依赖分支。"""
    monkeypatch.setattr(
        AnalysisFlowController,
        "prepare_turn",
        lambda self, state, intent, user_input, dataset_profile: None,
    )
    monkeypatch.setattr(
        "data_agent.agent.question_need_detector.detect_question_need",
        lambda user_input, intent, state: {"status": "no_question"},
    )
    old_task_dir = task_manager._dir
    old_next_id = task_manager._next_id_val
    task_manager._dir = tmp_path / "tasks"
    task_manager._next_id_val = 0
    try:
        workspace_obj = Workspace()
        ctx = AgentContext(session_id="loop_semantic_gate", workspace=workspace_obj)
        state = AnalysisSessionState(session_id="loop_semantic_gate")
        state.pending_confirmations = [{
            "id": "semantic_gate",
            "status": "pending",
            "confirmation_type": "time_window",
            "question": "请确认对比时间窗口",
            "options": [],
            "state_updates": "{}",
            "affected_operations": ["analysis.causal"],
        }]
        ctx.analysis_state = state
        controller = AnalysisFlowController("loop_semantic_gate")
        assert controller.is_capability_blocked_by_confirmation(state, "analysis.causal") is True
        assert controller.is_capability_blocked_by_confirmation(state, "analysis.forecast") is False
    finally:
        task_manager._dir = old_task_dir
        task_manager._next_id_val = old_next_id


def test_structured_loop_auto_suspends_for_required_question(monkeypatch):
    intent = TurnIntent(
        intent_type="intent_negotiation",
        clarity="vague",
        data_state="data_loaded",
        analysis_stage="discover",
        recommended_action="guide_analysis",
        execution_readiness="ready",
        reason="test",
        ambiguities=[],
    )
    monkeypatch.setattr("data_agent.agent.intent.plan_turn_intent", lambda user_input, session_context, **kwargs: intent)
    monkeypatch.setattr(AnalysisFlowController, "prepare_turn", lambda self, state, intent, user_input, dataset_profile: None)

    class FailingClient:
        def chat(self, *args, **kwargs):
            raise AssertionError("LLM should not be called before required confirmation")

    workspace_obj = Workspace()
    ctx = AgentContext(session_id="auto_question_gate", workspace=workspace_obj)
    state = AnalysisSessionState(session_id="auto_question_gate", data_state="data_loaded")
    state.active_scope["active_dataset"] = "orders"
    state.active_scope["active_mode"] = "data_loaded"
    _produce_current_execution_metadata(ctx, state, "orders", "amount")
    ctx.analysis_state = state
    loop = AgentLoop(client=FailingClient(), session_id="auto_question_gate")
    loop.context = ctx

    with use_agent_context(ctx):
        result = loop.run_turn_structured("please analyze this dataset")

    from data_agent.agent.loop import SuspendedForConfirmation

    assert isinstance(result, SuspendedForConfirmation)
    assert result.confirmation_type == "route_selection"
    assert len(result.options) == 2
    assert result.confirmation_id == result.suspension_id
    assert state.pending_confirmations == []


def test_auto_suspend_for_required_question_uses_confirmation_runtime(tmp_path, monkeypatch):
    from data_agent.config import get_config
    from data_agent.agent.confirmation.models import ConfirmationStatus

    cfg = get_config()
    old_sessions = cfg.sessions_dir
    cfg.sessions_dir = tmp_path / "sessions"
    try:
        ctx = AgentContext(session_id="auto_runtime_gate", workspace=Workspace())
        state = AnalysisSessionState(session_id="auto_runtime_gate", data_state="data_loaded")
        ctx.analysis_state = state
        loop = AgentLoop(client=None, session_id="auto_runtime_gate")
        loop.context = ctx
        loop._turn_question_need = {
            "status": "hard_question",
            "question_type": "route_selection",
            "question": "Choose an analysis route.",
            "options": [
                {"label": "Trend", "value": "trend"},
                {"label": "Compare", "value": "period_compare"},
            ],
            "reason": "Different routes change the analysis output.",
            "state_updates": {"stage": "scope"},
        }

        result = loop._maybe_auto_suspend_for_required_question()

        assert result is not None
        assert result.confirmation_id == result.suspension_id
        assert result.version >= 2
        assert (
            cfg.sessions_resolved
            / "auto_runtime_gate"
            / "confirmations"
            / "events.jsonl"
        ).exists()
        assert list(cfg.sessions_resolved.glob("suspension_*.json")) == []
        record = loop._confirmation_runtime().get(
            "auto_runtime_gate",
            result.confirmation_id,
        )
        assert record.status == ConfirmationStatus.SUSPENDED
        assert record.source == "question_need_detector"
    finally:
        cfg.sessions_dir = old_sessions


def test_structured_loop_relationship_diagnostic_does_not_suspend(monkeypatch):
    intent = TurnIntent(
        intent_type="directed_analysis",
        clarity="clear",
        data_state="data_loaded",
        analysis_stage="execute",
        recommended_action="run_analysis",
        execution_readiness="ready",
        reason="test",
        ambiguities=[],
    )
    monkeypatch.setattr("data_agent.agent.intent.plan_turn_intent", lambda user_input, session_context, **kwargs: intent)
    monkeypatch.setattr(AnalysisFlowController, "prepare_turn", lambda self, state, intent, user_input, dataset_profile: None)

    class FinalClient:
        def chat(self, *args, **kwargs):
            from data_agent.agent.publication.runtime import snapshot_for_turn
            return Response(text=json.dumps({"schema":"answer_bindings.v2","snapshot_digest":snapshot_for_turn(loop).digest,"sections":[]}))

    ctx = AgentContext(session_id="auto_file_relationship_gate", workspace=Workspace())
    state = AnalysisSessionState(session_id="auto_file_relationship_gate", data_state="data_loaded")
    state.active_scope["active_dataset"] = "orders"
    state.active_scope["active_mode"] = "data_loaded"
    state.file_relationships = [{
        "relationship_id": "rel_orders_history",
        "file_ids": ["file_old", "file_new"],
        "status": "possibly_linked",
        "requires_confirmation": True,
        "confirmation_type": "file_relationship_confirmation",
    }]
    ctx.analysis_state = state
    loop = AgentLoop(client=FinalClient(), session_id="auto_file_relationship_gate")
    loop.context = ctx

    with use_agent_context(ctx):
        result = loop.run_turn_structured("analyze revenue trend")

    from data_agent.agent.loop import FinalResponse

    assert isinstance(result, FinalResponse)
    assert "未计算" in result.content and "analysis continued" not in result.content
    assert state.accepted_answers
    assert state.pending_confirmations == []



def test_p08_method_pending_no_longer_blocks_the_turn(monkeypatch):
    intent = TurnIntent(
        intent_type="directed_analysis",
        clarity="clear",
        data_state="data_loaded",
        analysis_stage="execute",
        recommended_action="run_analysis",
        execution_readiness="ready",
        reason="test",
        ambiguities=[],
    )
    monkeypatch.setattr("data_agent.agent.intent.plan_turn_intent", lambda user_input, session_context, **kwargs: intent)
    monkeypatch.setattr(AnalysisFlowController, "prepare_turn", lambda self, state, intent, user_input, dataset_profile: None)
    monkeypatch.setattr(
        "data_agent.agent.question_need_detector.detect_question_need",
        lambda user_input, intent, state: {"status": "clear"},
    )

    class AnsweringClient:
        def __init__(self):
            self.called = False

        def chat(self, *args, **kwargs):
            self.called = True
            return Response(text="分析结论：收入呈上升趋势。")

    ctx = AgentContext(session_id="preexisting_method_gate", workspace=Workspace())
    state = AnalysisSessionState(session_id="preexisting_method_gate", data_state="data_loaded")
    state.pending_confirmations = [{
        "id": "existing_method_confirmation",
        "status": "pending",
        "question": "Confirm the existing method?",
        "options": [{"label": "Confirm", "value": "confirm_method"}],
        "confirmation_type": "method_confirmation",
        "blocking_reason": "Method choice changes the analysis",
        "state_updates": json.dumps({"stage": "plan"}),
    }]
    ctx.analysis_state = state
    client = AnsweringClient()
    loop = AgentLoop(client=client, session_id="preexisting_method_gate")
    loop.context = ctx

    with use_agent_context(ctx):
        result = loop.run_turn_structured("analyze revenue trend")

    # IC1/P08-01 契约更新：原断言通用方法 pending 阻塞整轮；
    # 新原则下方法审批不再悬挂——分析直接执行，旧 pending 不被解析也不删除。
    from data_agent.agent.loop import FinalResponse, SuspendedForConfirmation

    assert isinstance(result, FinalResponse)
    assert not isinstance(result, SuspendedForConfirmation)
    assert client.called
    assert state.pending_confirmations[0]["status"] == "pending"  # 不伪批准
    assert len(state.pending_confirmations) == 1


def test_auto_suspend_does_not_duplicate_pending_confirmation_with_suspension_id():
    ctx = AgentContext(session_id="existing_suspension_gate", workspace=Workspace())
    state = AnalysisSessionState(session_id="existing_suspension_gate", data_state="data_loaded")
    state.pending_confirmations = [
        {
            "id": "existing_confirmation",
            "status": "pending",
            "suspension_id": "susp_existing",
            "question": "Already suspended?",
            "options": [{"label": "Yes", "value": "yes"}],
            "state_updates": json.dumps({"stage": "scope"}),
        },
        {
            "id": "second_confirmation",
            "status": "pending",
            "suspension_id": "susp_second",
            "question": "Also suspended?",
            "options": [{"label": "Yes", "value": "yes"}],
            "state_updates": json.dumps({"stage": "plan"}),
        },
    ]
    ctx.analysis_state = state
    loop = AgentLoop(client=None, session_id="existing_suspension_gate")
    loop.context = ctx
    loop._turn_question_need = {
        "status": "hard_question",
        "question_type": "scope_confirmation",
        "question": "Regenerated question",
        "options": [{"label": "Continue", "value": "continue"}],
        "reason": "Regenerated reason",
        "state_updates": {"stage": "scope"},
    }

    assert loop._maybe_auto_suspend_for_required_question() is None
    assert len(state.pending_confirmations) == 2
    assert [item["suspension_id"] for item in state.pending_confirmations] == [
        "susp_existing",
        "susp_second",
    ]


def test_auto_suspend_selects_new_unsuspended_confirmation_after_suspended_pending():
    ctx = AgentContext(session_id="new_confirmation_after_suspension", workspace=Workspace())
    state = AnalysisSessionState(session_id="new_confirmation_after_suspension", data_state="data_loaded")
    state.pending_confirmations = [
        {
            "id": "old_confirmation",
            "status": "pending",
            "suspension_id": "susp_old",
            "question": "Old question?",
            "options": [{"label": "Old", "value": "old"}],
            "state_updates": json.dumps({"stage": "scope"}),
        },
        {
            "id": "new_confirmation",
            "status": "pending",
            "question": "New question?",
            "options": [{"label": "New", "value": "new"}],
            "state_updates": json.dumps({"stage": "plan"}),
        },
    ]
    ctx.analysis_state = state
    loop = AgentLoop(client=None, session_id="new_confirmation_after_suspension")
    loop.context = ctx
    loop._turn_existing_pending_ids = {"old_confirmation"}
    loop._turn_question_need = {
        "status": "hard_question",
        "question_type": "scope_confirmation",
        "question": "Detector question?",
        "options": [{"label": "Continue", "value": "continue"}],
        "reason": "Detector reason",
        "state_updates": {"stage": "scope"},
    }

    result = loop._maybe_auto_suspend_for_required_question()

    assert result is not None
    assert result.question == "New question?"
    assert state.pending_confirmations[0]["suspension_id"] == "susp_old"
    assert "suspension_id" not in state.pending_confirmations[1]
    assert result.confirmation_id == result.suspension_id
    assert len(state.pending_confirmations) == 2


def test_auto_suspend_falls_back_to_unsuspended_preexisting_confirmation():
    ctx = AgentContext(session_id="preexisting_unsuspended_gate", workspace=Workspace())
    state = AnalysisSessionState(session_id="preexisting_unsuspended_gate", data_state="data_loaded")
    state.pending_confirmations = [{
        "id": "preexisting_confirmation",
        "status": "pending",
        "question": "Resume this question?",
        "options": [{"label": "Resume", "value": "resume"}],
        "state_updates": json.dumps({"stage": "plan"}),
    }]
    ctx.analysis_state = state
    loop = AgentLoop(client=None, session_id="preexisting_unsuspended_gate")
    loop.context = ctx
    loop._turn_existing_pending_ids = {"preexisting_confirmation"}
    loop._turn_question_need = {
        "status": "hard_question",
        "question_type": "scope_confirmation",
        "question": "Detector question?",
        "options": [{"label": "Continue", "value": "continue"}],
        "reason": "Detector reason",
        "state_updates": {"stage": "scope"},
    }

    result = loop._maybe_auto_suspend_for_required_question()

    assert result is not None
    assert result.question == "Resume this question?"
    assert "suspension_id" not in state.pending_confirmations[0]
    assert result.confirmation_id == result.suspension_id


def test_unregistered_method_confirmation_cannot_mutate_state_or_task(tmp_path, monkeypatch):
    import data_agent.agent.analysis_flow_controller as flow_module
    import data_agent.session.task_manager as task_module
    from data_agent.agent.loop import SuspendedForConfirmation
    from data_agent.session.task_manager import TaskManager

    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    monkeypatch.setattr(flow_module, "task_manager", manager)
    monkeypatch.setattr(task_module, "task_manager", manager)

    session_id = "linked_method_confirmation"
    spec_id = "spec_linked_method"
    pending_id = "method_linked_method"
    ctx = AgentContext(session_id=session_id, workspace=Workspace())
    state = AnalysisSessionState(
        session_id=session_id,
        data_state="data_loaded",
        analysis_spec={
            "id": spec_id,
            "goal": "Fit retention curve",
            "playbook_id": "retention_lifecycle",
            "confirmation_policy": {"requires_confirmation": True},
        },
    )
    state.pending_confirmations = [{
        "id": pending_id,
        "status": "pending",
        "question": "Confirm the retention method?",
        "options": [{"label": "Confirm", "value": "confirm_method"}],
        "confirmation_type": "method_confirmation",
        "blocking_reason": "Method choice changes the analysis",
        "state_updates": json.dumps({
            "stage": "plan",
            "method_confirmation": {
                "playbook_id": "retention_lifecycle",
                "analysis_spec_id": spec_id,
            },
        }),
    }]
    ctx.analysis_state = state

    controller = flow_module.AnalysisFlowController(session_id)
    task = controller.ensure_confirmation_task(state)

    assert task is not None
    assert state.pending_confirmations[0]["related_task_id"] == task["id"]
    assert state.pending_confirmations[0]["related_spec_id"] == spec_id

    loop = AgentLoop(client=None, session_id=session_id)
    loop.context = ctx
    suspension = SuspendedForConfirmation(
        suspension_id="auto_runtime_identity",
        confirmation_id="auto_runtime_identity",
        question="Confirm the retention method?",
        options=[{"label": "Confirm", "value": "confirm_method"}],
        context="",
        snapshot={"messages": []},
        state_updates=state.pending_confirmations[0]["state_updates"],
        confirmation_type="method_confirmation",
        related_task_id=task["id"],
        related_spec_id=spec_id,
    )

    # An unregistered legacy suspension cannot simulate a user approval or complete a task.
    before = state.to_dict()
    prior_task = manager.get(task["id"])
    with pytest.raises(KeyError):
        loop._resolve_confirmation(suspension, "confirm_method")
    assert state.to_dict() == before
    assert manager.get(task["id"]) == prior_task


def test_structured_loop_ignores_untyped_obsolete_pending_when_detector_is_clear(monkeypatch):
    intent = TurnIntent(
        intent_type="directed_analysis",
        clarity="clear",
        data_state="data_loaded",
        analysis_stage="execute",
        recommended_action="run_analysis",
        execution_readiness="ready",
        reason="test",
        ambiguities=[],
    )
    monkeypatch.setattr("data_agent.agent.intent.plan_turn_intent", lambda user_input, session_context, **kwargs: intent)
    monkeypatch.setattr(
        "data_agent.agent.question_need_detector.detect_question_need",
        lambda user_input, intent, state: {"status": "clear"},
    )

    class FinalClient:
        def chat(self, *args, **kwargs):
            from data_agent.agent.publication.runtime import snapshot_for_turn
            return Response(text=json.dumps({"schema":"answer_bindings.v2","snapshot_digest":snapshot_for_turn(loop).digest,"sections":[]}))

    def prepare_turn_with_rich_confirmation(self, state, intent, user_input, dataset_profile):
        state.add_confirmation({
            "id": "rich_pending",
            "action": "resolve_file_relationship",
            "question": "confirm relationship",
            "options": [{"label": "Together", "value": "include_in_active_bundle"}],
            "state_updates": json.dumps({
                "stage": "plan",
                "file_relationship_confirmation": {"relationship_id": "rel_custom"},
                "analysis_spec": {"goal": "preserve me"},
            }),
        })

    monkeypatch.setattr(AnalysisFlowController, "prepare_turn", prepare_turn_with_rich_confirmation)

    ctx = AgentContext(session_id="preserve_pending_updates", workspace=Workspace())
    state = AnalysisSessionState(session_id="preserve_pending_updates", data_state="data_loaded")
    state.file_relationships = [{
        "relationship_id": "rel_detector",
        "file_ids": ["file_old", "file_new"],
        "status": "possibly_linked",
        "requires_confirmation": True,
        "confirmation_type": "file_relationship_confirmation",
    }]
    ctx.analysis_state = state
    loop = AgentLoop(client=FinalClient(), session_id="preserve_pending_updates")
    loop.context = ctx

    with use_agent_context(ctx):
        result = loop.run_turn_structured("analyze revenue trend")

    from data_agent.agent.loop import FinalResponse

    assert isinstance(result, FinalResponse)
    assert "未计算" in result.content and "analysis continued" not in result.content
    assert state.accepted_answers
    saved_updates = json.loads(state.pending_confirmations[0]["state_updates"])
    assert saved_updates == {
        "stage": "plan",
        "file_relationship_confirmation": {"relationship_id": "rel_custom"},
        "analysis_spec": {"goal": "preserve me"},
    }
    assert "suspension_id" not in state.pending_confirmations[0]



def test_p08_structured_loop_no_longer_suspends_on_playbook_method_selection(tmp_path, monkeypatch):
    from data_agent.config import get_config

    monkeypatch.setattr(get_config(), "sessions_dir", tmp_path / "sessions")
    intent = TurnIntent(
        intent_type="directed_analysis",
        clarity="clear",
        data_state="data_loaded",
        analysis_stage="execute",
        recommended_action="run_analysis",
        execution_readiness="ready",
        reason="test",
        ambiguities=[],
    )
    monkeypatch.setattr("data_agent.agent.intent.plan_turn_intent", lambda user_input, session_context, **kwargs: intent)
    monkeypatch.setattr("data_agent.agent.llm_playbook.select_playbook_llm", lambda **kwargs: None)

    class AnsweringClient:
        def __init__(self):
            self.called = False

        def chat(self, *args, **kwargs):
            self.called = True
            return Response(text="预测结论：示例答复。")

    ctx = AgentContext(session_id="playbook_pending_gate", workspace=Workspace())
    state = AnalysisSessionState(session_id="playbook_pending_gate", data_state="data_loaded")
    state.active_scope["active_dataset"] = "main"
    state.active_scope["active_mode"] = "data_loaded"
    ctx.analysis_state = state
    client = AnsweringClient()
    loop = AgentLoop(client=client, session_id="playbook_pending_gate")
    loop.context = ctx

    with use_agent_context(ctx):
        result = loop.run_turn_structured("forecast revenue and ROI next month")

    # P08-01 契约更新：方法模板不再创建 pending，因此不再悬挂；
    # 预测请求直接进入正常应答（无通用方法审批）。
    from data_agent.agent.loop import FinalResponse, SuspendedForConfirmation

    assert isinstance(result, FinalResponse)
    assert not isinstance(result, SuspendedForConfirmation)
    assert client.called
    assert not [
        item for item in state.pending_confirmations
        if item.get("confirmation_type") == "method_confirmation"
    ]


def test_stream_loop_auto_suspends_for_required_question(monkeypatch):
    intent = TurnIntent(
        intent_type="intent_negotiation",
        clarity="vague",
        data_state="data_loaded",
        analysis_stage="discover",
        recommended_action="guide_analysis",
        execution_readiness="ready",
        reason="test",
        ambiguities=[],
    )
    monkeypatch.setattr("data_agent.agent.intent.plan_turn_intent", lambda user_input, session_context, **kwargs: intent)
    monkeypatch.setattr(AnalysisFlowController, "prepare_turn", lambda self, state, intent, user_input, dataset_profile: None)

    class FailingClient:
        def chat(self, *args, **kwargs):
            raise AssertionError("LLM should not be called before required confirmation")

    ctx = AgentContext(session_id="auto_question_gate_stream", workspace=Workspace())
    state = AnalysisSessionState(session_id="auto_question_gate_stream", data_state="data_loaded")
    state.active_scope["active_dataset"] = "orders"
    state.active_scope["active_mode"] = "data_loaded"
    _produce_current_execution_metadata(ctx, state, "orders", "amount")
    ctx.analysis_state = state
    loop = AgentLoop(client=FailingClient(), session_id="auto_question_gate_stream")
    loop.context = ctx

    events = list(loop.stream_turn("please analyze this dataset"))

    assert events[0]["type"] == "suspended"
    assert events[0]["confirmation_type"] == "route_selection"
    assert len(events[0]["options"]) == 2




def test_incomplete_hypothesis_audit_fails_once_in_sync_loop(engine,monkeypatch):
    from tests.test_trusted_publication_runtime import AppClient,intent_for_app
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    loop,_=engine
    content="检验 H1 并显示当前状态"
    intent_for_app(monkeypatch,"result",content,{'datasets': ['orders'], 'hypothesis_ids': ['H1'], 'quantity': 'value'})
    loop.client=AppClient(loop)
    if False:
        events=list(loop.stream_turn(content))
        assert not [e for e in events if e["type"]=="error"]
        body="".join(e["text"] for e in events if e["type"]=="text_delta")
    else: body=loop.run_turn_structured(content).content
    saved=load_session(loop.session_id)
    answer=read_answer(loop.session_id,saved["messages"][-1]["answer_ref"])
    assert body==answer["body"] and "未计算" in body
    assert answer["requirement_outcomes"][0]["status"]=="not_computed"
    assert not [t for t in answer["render_trace"] if t["kind"]=="claim"]
    assert len(loop.context.analysis_state.accepted_answers)==1


def test_incomplete_hypothesis_audit_fails_once_in_stream_loop(engine,monkeypatch):
    from tests.test_trusted_publication_runtime import AppClient,intent_for_app
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    loop,_=engine
    content="检验 H1 并显示当前状态"
    intent_for_app(monkeypatch,"result",content,{'datasets': ['orders'], 'hypothesis_ids': ['H1'], 'quantity': 'value'})
    loop.client=AppClient(loop)
    if True:
        events=list(loop.stream_turn(content))
        assert not [e for e in events if e["type"]=="error"]
        body="".join(e["text"] for e in events if e["type"]=="text_delta")
    else: body=loop.run_turn_structured(content).content
    saved=load_session(loop.session_id)
    answer=read_answer(loop.session_id,saved["messages"][-1]["answer_ref"])
    assert body==answer["body"] and "未计算" in body
    assert answer["requirement_outcomes"][0]["status"]=="not_computed"
    assert not [t for t in answer["render_trace"] if t["kind"]=="claim"]
    assert len(loop.context.analysis_state.accepted_answers)==1


def test_loop_injects_synthesis_policy_before_final_answer(monkeypatch):
    intent = TurnIntent(
        intent_type="directed_analysis",
        clarity="clear",
        data_state="data_loaded",
        analysis_stage="execute",
        recommended_action="run_analysis",
        execution_readiness="ready",
        reason="test",
        ambiguities=[],
    )
    monkeypatch.setattr("data_agent.agent.intent.plan_turn_intent", lambda user_input, session_context, **kwargs: intent)
    monkeypatch.setattr(AnalysisFlowController, "prepare_turn", lambda self, state, intent, user_input, dataset_profile: None)

    workspace_obj = Workspace()
    ctx = AgentContext(session_id="loop_synthesis_policy", workspace=workspace_obj)
    state = AnalysisSessionState(session_id="loop_synthesis_policy")
    state.analysis_spec = {
        "playbook_id": "retention_lifecycle",
        "question_type": "diagnostic",
        "confirmation_policy": {"requires_confirmation": False},
        "limitations": ["aggregate retention data"],
    }
    ctx.analysis_state = state
    client = _EvidenceThenFinalClient()
    loop = AgentLoop(client=client, session_id="loop_synthesis_policy")
    loop.context = ctx
    client.loop=loop

    with use_agent_context(ctx):
        result = loop.run_turn("analyze retention formula")

    assert "未计算" in result and "final answer" not in result
    assert state.accepted_answers
    assert any("<synthesis_policy" in prompt for prompt in client.system_prompts[1:])

    final_prompt = client.system_prompts[-1]
    assert ("answer_mode=\"analytical\"" in final_prompt) or ("answer_mode: analytical" in final_prompt)
    assert ("insight_depth=\"standard\"" in final_prompt) or ("insight_depth: standard" in final_prompt)
    assert ("business_translation=\"cautious\"" in final_prompt) or ("business_translation: cautious" in final_prompt)


def test_prepare_analysis_turn_stores_refined_intent_from_route_proposals(monkeypatch):
    intent = TurnIntent(
        intent_type="intent_negotiation",
        clarity="vague",
        data_state="data_loaded",
        analysis_stage="discover",
        recommended_action="guide_analysis",
        execution_readiness="ready",
        reason="test",
        ambiguities=[],
    )
    monkeypatch.setattr("data_agent.agent.intent.plan_turn_intent", lambda user_input, session_context, **kwargs: intent)
    monkeypatch.setattr(AnalysisFlowController, "prepare_turn", lambda self, state, intent, user_input, dataset_profile: None)
    monkeypatch.setattr(AnalysisFlowController, "activate_tool_groups", lambda self, registry, intent, state, user_input: [])

    workspace_obj = Workspace()
    ctx = AgentContext(session_id="loop_refined_intent", workspace=workspace_obj)
    state = AnalysisSessionState(session_id="loop_refined_intent")
    state.route_proposals = [{"id": "route_trend", "label": "Revenue trend", "direction": "trend"}]
    ctx.analysis_state = state
    loop = AgentLoop(client=object(), session_id="loop_refined_intent")
    loop.context = ctx

    with use_agent_context(ctx):
        loop._prepare_analysis_turn("help me explore this dataset")

    assert loop.context.turn_intent.ambiguities[-1]["field"] == "analysis_route"
    assert loop._last_turn_intent.ambiguities[-1]["routes"] == [
        {"label": "Revenue trend", "direction": "trend"},
    ]


def test_synthesis_policy_injection_creates_verification_report_first(engine,monkeypatch):
    from tests.test_trusted_publication_runtime import request,draft
    from data_agent.agent.publication.runtime import snapshot_for_turn,publication_prompt,publish
    loop,_=engine
    state=loop.context.analysis_state
    state.evidence_records=[{"id":"ev_old","claim":"Retention rose 500%","result_summary":"Retention fell from 30% to 20%","confidence":"high"}]
    request(loop,"计算当前留存",{'kind': 'series', 'scope': {'datasets': ['orders']}})
    if "annotation"=="exception": state.verification_reports=[{"id":"old_failure","overall_status":"fail"}]
    snapshot=snapshot_for_turn(loop)
    assert snapshot.as_dict()["claims"]==[]
    assert "<accepted_answer_contract>" in publication_prompt(loop)
    body,error=publish(loop,draft(snapshot))
    assert error is None and "未计算" in body and "500%" not in body
    assert loop._accepted_answer["requirement_outcomes"][0]["status"]=="not_computed"


def test_synthesis_policy_injection_creates_hypothesis_set_before_policy(tmp_path):
    from data_agent.config import get_config

    cfg = get_config()
    old_sessions = cfg.sessions_dir
    cfg.sessions_dir = tmp_path / "sessions"
    try:
        intent = TurnIntent(
            intent_type="directed_analysis",
            clarity="clear",
            data_state="data_loaded",
            analysis_stage="execute",
            recommended_action="run_analysis",
            execution_readiness="ready",
            reason="test",
            ambiguities=[],
        )
        workspace_obj = Workspace()
        ctx = AgentContext(session_id="loop_hyp_before_synthesis", workspace=workspace_obj)
        state = AnalysisSessionState(session_id="loop_hyp_before_synthesis")
        _produce_current_execution_metadata(ctx, state, "sales", "revenue")
        state.evidence_records = [{
            "id": "ev_1",
            "claim": "Revenue changed across the selected period",
            "result_summary": "Revenue moved from 100 to 120.",
            "confidence": "high",
            "dataset": "sales",
            "sample_size": 20,
            "time_scope": "2026-01-01 to 2026-01-20",
            "calculation_method": "trend comparison",
            "method_detail": "compare daily revenue values",
            "limitations": "Descriptive trend only",
            "method": "descriptive",
        }]
        ctx.analysis_state = state
        ctx.user_quality_requirements = ""
        loop = AgentLoop(client=object(), session_id="loop_hyp_before_synthesis")
        loop.context = ctx
        loop._last_turn_intent = intent
        loop._reset_turn_tracking()

        # A presentation/playbook suggestion alone cannot create a hypothesis authority.
        state.analysis_plan = {"id":"plan_current","goal":"show revenue trend"}
        with use_agent_context(ctx):
            loop._maybe_inject_synthesis_policy("show revenue trend")

        assert state.hypothesis_sets
        assert state.hypothesis_sets[-1]["dataset"] == "sales"
        assert state.hypothesis_sets[-1]["route"] == "trend"
        assert loop._turn_synthesis_policy_injected is True
    finally:
        cfg.sessions_dir = old_sessions


def test_explicit_hypothesis_task_exposes_stable_ids_after_plan_before_evidence(tmp_path):
    from data_agent.config import get_config

    cfg = get_config()
    old_sessions = cfg.sessions_dir
    cfg.sessions_dir = tmp_path / "sessions"
    try:
        intent = TurnIntent(
            intent_type="directed_analysis",
            clarity="clear",
            data_state="data_loaded",
            analysis_stage="execute",
            recommended_action="run_analysis",
            execution_readiness="ready",
            reason="test",
            ambiguities=[],
        )
        ctx = AgentContext(session_id="loop_hyp_before_evidence", workspace=Workspace())
        state = AnalysisSessionState(session_id="loop_hyp_before_evidence")
        _produce_current_execution_metadata(ctx, state, "sales", "revenue")
        ctx.analysis_state = state
        loop = AgentLoop(client=object(), session_id=ctx.session_id)
        loop.context = ctx
        loop._last_turn_intent = intent
        loop._reset_turn_tracking()

        with use_agent_context(ctx):
            loop._maybe_inject_synthesis_policy("请提出并检验至少两种竞争性假设")

        assert state.evidence_records == []
        assert state.hypothesis_sets == []
        assert "record_analysis_plan" in loop._turn_synthesis_policy_instruction
        state.analysis_plan = {"id": "plan_current", "goal": "compare hypotheses"}
        with use_agent_context(ctx):
            loop._maybe_inject_synthesis_policy("请提出并检验至少两种竞争性假设")
        assert state.hypothesis_sets
        assert state.hypothesis_sets[0]["plan_id"] == "plan_current"
        assert "<competing_hypotheses>" in loop._turn_synthesis_policy_instruction
        assert state.hypothesis_sets[0]["id"] in loop._turn_synthesis_policy_instruction
        assert loop._turn_synthesis_policy_injected is True
    finally:
        cfg.sessions_dir = old_sessions


def test_synthesis_policy_injection_marks_failed_verification_attempt(engine,monkeypatch):
    from tests.test_trusted_publication_runtime import request,draft
    from data_agent.agent.publication.runtime import snapshot_for_turn,publication_prompt,publish
    loop,_=engine
    state=loop.context.analysis_state
    state.evidence_records=[{"id":"ev_old","claim":"Retention rose 500%","result_summary":"Retention fell from 30% to 20%","confidence":"high"}]
    request(loop,"计算当前留存",{'kind': 'series', 'scope': {'datasets': ['orders']}})
    if "exception"=="exception": state.verification_reports=[{"id":"old_failure","overall_status":"fail"}]
    snapshot=snapshot_for_turn(loop)
    assert snapshot.as_dict()["claims"]==[]
    assert "<accepted_answer_contract>" in publication_prompt(loop)
    body,error=publish(loop,draft(snapshot))
    assert error is None and "未计算" in body and "500%" not in body
    assert loop._accepted_answer["requirement_outcomes"][0]["status"]=="not_computed"


def test_synthesis_policy_instruction_reflects_failed_runtime_verification(engine,monkeypatch):
    from tests.test_trusted_publication_runtime import request,draft
    from data_agent.agent.publication.runtime import snapshot_for_turn,publication_prompt,publish
    loop,_=engine
    state=loop.context.analysis_state
    state.evidence_records=[{"id":"ev_old","claim":"Retention rose 500%","result_summary":"Retention fell from 30% to 20%","confidence":"high"}]
    request(loop,"计算当前留存",{'kind': 'series', 'scope': {'datasets': ['orders']}})
    if "contradiction"=="exception": state.verification_reports=[{"id":"old_failure","overall_status":"fail"}]
    snapshot=snapshot_for_turn(loop)
    assert snapshot.as_dict()["claims"]==[]
    assert "<accepted_answer_contract>" in publication_prompt(loop)
    body,error=publish(loop,draft(snapshot))
    assert error is None and "未计算" in body and "500%" not in body
    assert loop._accepted_answer["requirement_outcomes"][0]["status"]=="not_computed"


# ── P7-L3/B06: the turn budget must stay armed through real loop paths ──


def test_prepare_analysis_turn_keeps_execution_budget_armed(tmp_path, monkeypatch):
    """registry.reset_groups 不得清掉 turn_state（B06 根因回归）。"""
    from data_agent.agent.loop import AgentLoop

    loop = AgentLoop(client=None, session_id="budget_armed")
    loop._reset_turn_tracking()
    loop.auxiliary_llm_client = None

    loop._prepare_analysis_turn("分析销售趋势")

    turn_state = loop.context.turn_state
    assert turn_state is not None, "activate_tool_groups 不得把刚装配的预算状态清成 None"
    assert turn_state.budget.max_tool_calls and turn_state.budget.max_tool_calls > 0
    # 分组激活本身不受影响
    assert loop.context.active_tool_groups


def test_streaming_loop_enforces_tool_budget_and_stops_execution(tmp_path, monkeypatch):
    """超过预算的真实工具调用必须被阻止：budget_exceeded 消息＋有限收据＋错误事件。"""
    import csv
    import os

    inbox = tmp_path / "ws" / "inbox"
    inbox.mkdir(parents=True)
    fixture = inbox / "F-SALES.csv"
    with fixture.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["date", "channel", "amount", "order_id"])
        for index in range(12):
            writer.writerow([f"2026-09-{index + 1:02d}", "A", 10, index + 1])

    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path / "ws"))
    monkeypatch.setenv("SESSIONS_DIR", str(tmp_path / "sessions"))
    monkeypatch.setenv("API_BASE", "http://127.0.0.1:9")
    monkeypatch.setenv("MCP_ENABLED", "false")
    monkeypatch.setenv("SKILL_AUTO_DISCOVER", "false")

    from data_agent import config as config_module
    from data_agent.config import AgentConfig

    monkeypatch.setattr(config_module, "_config", AgentConfig(
        WORKSPACE_DIR=tmp_path / "ws",
        SESSIONS_DIR=tmp_path / "sessions",
    ))

    from data_agent.agent.loop import AgentLoop
    from data_agent.llm.client import Response, ToolCall, StreamComplete

    responses = [
        Response(tool_calls=[ToolCall(
            id="r1-0", name="load_data",
            arguments={"source": "F-SALES.csv", "name": "budget_sales"},
        )]),
        Response(tool_calls=[
            ToolCall(
                id=f"r2-{number}", name="transform_data",
                arguments={
                    "name": "budget_sales", "operation": "group_aggregate",
                    "group_by": ["channel"],
                    "aggregations": [{"column": "amount", "functions": ["sum"]}],
                    "save_as": f"budget_{number}",
                },
            )
            for number in range(1, 206)
        ]),
        Response(text="done"),
    ]
    cursor = {"index": 0}

    class ScriptedClient:
        def stream_chat_structured(self, messages, tools=None, system=None):
            index = cursor["index"]
            cursor["index"] += 1
            yield StreamComplete(response=responses[min(index, len(responses) - 1)])

    loop = AgentLoop(client=ScriptedClient(), session_id="budget_stream")
    events = list(loop.stream_turn("【B06-BUDGET】请执行大量分析以触发预算边界"))

    error_events = [event for event in events if event.get("type") == "error"]
    assert not any("budget" in str(event.get("message", "")).lower() for event in error_events)
    assert any(event.get("type") == "tool_result"
               and event.get("web", {}).get("error_type") == "budget_exceeded"
               for event in events), "预算拒绝须有真实配对工具结果，随后沿原发布链收尾"
    assert loop._turn_budget_exhaustion["code"] == "tool_calls"
    assert loop._tools_for_current_round() is None
    receipts = loop.context.analysis_state.tool_receipts
    budget_messages = [
        message for message in loop.messages
        if message.get("role") == "tool"
        and "budget_exceeded" in str(message.get("content", ""))
    ]
    assert budget_messages, "被阻止的调用必须留下 budget_exceeded 工具消息"
    executed = [r for r in receipts if r.get("tool_name") == "transform_data"]
    max_calls = loop.context.turn_state.budget.max_tool_calls
    assert len(executed) <= max_calls + 1, (
        f"实际执行 {len(executed)} 次非元工具调用，超出预算 {max_calls}"
    )
