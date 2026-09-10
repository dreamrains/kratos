"""P08-01/P08-03: confirmation converges to real business semantic gaps.

Covers issue-record acceptance Q13 (D7/D30 request must not be gated by
method/forecast keywords) and Q14 (explicit competing-hypotheses request must
not be bounced to internal route selection), plus the legacy retirement
contract L01–L03.
"""

import json

from data_agent.agent.analysis_entry import decide_analysis_entry
from data_agent.agent.analysis_flow_controller import AnalysisFlowController
from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.confirmation_policy import (
    is_actionable_pending_confirmation,
    pending_confirmation_gate,
    retire_method_approval_confirmations,
)
from data_agent.agent.intent import TurnIntent
from data_agent.agent.method_playbooks import apply_selection_to_state, choose_playbook
from data_agent.agent.question_need_detector import detect_question_need, explicit_task_reason


def _retention_state() -> AnalysisSessionState:
    state = AnalysisSessionState(session_id="p08_retention", data_state="data_loaded")
    state.dataset_contracts = [{
        "id": "duc_retention",
        "dataset": "retention",
        "quality": {"status": "ready"},
        "field_roles": {"date": ["day"], "metrics": ["retention_rate"]},
        "supported_analyses": ["trend"],
        "unsupported_analyses": [],
    }]
    state.route_proposals = [{
        "id": "route_trend",
        "dataset": "retention",
        "direction": "trend",
        "limitations": ["Descriptive trend only"],
        "evidence_requirements": ["day", "metric"],
    }]
    return state


def _intent(intent_type="directed_analysis", **overrides):
    values = {
        "intent_type": intent_type,
        "clarity": "clear",
        "data_state": "data_loaded",
        "analysis_stage": "execute",
        "recommended_action": "run_analysis",
        "execution_readiness": "ready",
        "reason": "test",
        "ambiguities": [],
    }
    values.update(overrides)
    return TurnIntent(**values)


Q13_INPUT = (
    "请计算并解释 D7 留存；判断当前数据是否可以预测 D30。"
    "若不能，请明确说明缺失证据与下一步。"
)


class TestQ13RetentionBoundaryRequest:

    def test_q13_playbook_selection_requires_no_confirmation(self):
        selection = choose_playbook(Q13_INPUT, _intent(), has_data=True)

        assert selection.requires_confirmation is False

    def test_q13_detector_does_not_gate_on_forecast_or_d30(self):
        gate = detect_question_need(Q13_INPUT, _intent(), _retention_state())

        assert gate.get("question_type") != "method_confirmation"
        assert gate["status"] in {"clear", "no_question"}

    def test_q13_entry_does_not_method_clarify(self):
        decision = decide_analysis_entry(Q13_INPUT, _intent(), _retention_state())

        gate_type = (decision.get("confirmation_gate") or {}).get("confirmation_type", "")
        assert gate_type != "method_confirmation"
        assert decision["required_user_action"] not in {"ask_user_question", "confirm_method"}


class TestQ14CompetingHypotheses:

    def test_q14_explicit_task_reason_recognized(self):
        assert explicit_task_reason("请提出并检验至少两种竞争性假设") == "hypothesis_task"
        assert explicit_task_reason("对收入下降提出竞争性假设并验证") == "competing_hypotheses"
        assert explicit_task_reason("载入新版本后，请重新判断哪些关系已失效、哪些仍未决") == "evidence_reassessment"
        # 泛化指令不算明确任务
        assert explicit_task_reason("帮我看看这数据") == ""

    def test_q14_detector_skips_route_selection_for_explicit_task(self):
        state = _retention_state()
        state.route_proposals.append({
            "id": "route_compare",
            "dataset": "retention",
            "direction": "period_compare",
            "limitations": [],
            "evidence_requirements": ["day", "metric"],
        })
        vague = _intent("intent_negotiation", clarity="vague", analysis_stage="discover", recommended_action="guide_analysis")

        gate = detect_question_need("请提出并检验至少两种竞争性假设", vague, state)

        assert gate.get("question_type") != "route_selection"

    def test_q14_new_version_reassessment_skips_internal_route_confirmation(self):
        state = _retention_state()
        state.route_proposals.append({
            "id": "route_compare",
            "dataset": "retention",
            "direction": "period_compare",
            "limitations": [],
            "evidence_requirements": ["day", "metric"],
        })
        vague = _intent("intent_negotiation", clarity="vague", analysis_stage="discover", recommended_action="guide_analysis")
        request = (
            "现在把新文件作为同一业务对象的新数据版本载入。"
            "请保留旧版假设与证据审计，重新判断哪些关系已失效、哪些仍未决。"
        )

        gate = detect_question_need(request, vague, state)
        decision = decide_analysis_entry(request, vague, state)

        assert gate.get("question_type") != "route_selection"
        assert decision["required_user_action"] != "choose_analysis_route"
        assert decision["decision"] == "direct_analysis"

    def test_q14_entry_chooses_internal_route_not_user_route_pick(self):
        state = _retention_state()
        state.route_proposals.append({
            "id": "route_compare",
            "dataset": "retention",
            "direction": "period_compare",
            "limitations": [],
            "evidence_requirements": ["day", "metric"],
        })
        vague = _intent("intent_negotiation", clarity="vague", analysis_stage="discover", recommended_action="guide_analysis")

        decision = decide_analysis_entry("请提出并检验至少两种竞争性假设", vague, state)

        # 不把技术路线选择交给用户；内部默认路线带记录理由
        assert decision["required_user_action"] != "choose_analysis_route"
        assert decision["decision"] == "direct_analysis"
        assert decision["route"] in {"trend", "period_compare"}
        assert "explicit task" in decision["reason"]

    def test_q14_vague_request_without_explicit_task_still_clarifies(self):
        state = _retention_state()
        state.route_proposals.append({
            "id": "route_compare",
            "dataset": "retention",
            "direction": "period_compare",
            "limitations": [],
            "evidence_requirements": ["day", "metric"],
        })
        vague = _intent("intent_negotiation", clarity="vague", analysis_stage="discover", recommended_action="guide_analysis")

        decision = decide_analysis_entry("帮我看看这数据", vague, state)

        assert decision["required_user_action"] == "choose_analysis_route"


def _legacy_method_pending(**overrides):
    item = {
        "id": "method_retention_lifecycle_spec_1",
        "confirmation_type": "method_confirmation",
        "question": "当前问题适合按「留存与生命周期」方法继续。请确认……",
        "options": [],
        "blocking_reason": "predictive retention modeling needs confirmation",
        "related_spec_id": "spec_1",
        "state_updates": json.dumps({
            "stage": "plan",
            "method_confirmation": {
                "playbook_id": "retention_lifecycle",
                "analysis_spec_id": "spec_1",
                "allowed_actions": ["confirm_method", "clarify_method_scope"],
            },
        }, ensure_ascii=False),
        "source": "method_playbook",
        "status": "pending",
    }
    item.update(overrides)
    return item


class TestLegacyRetirement:

    def test_l01_pure_method_pending_retired_idempotently_and_blocks_no_more(self):
        state = AnalysisSessionState(session_id="p08_l01")
        state.pending_confirmations = [_legacy_method_pending()]

        first = retire_method_approval_confirmations(state)
        second = retire_method_approval_confirmations(state)

        assert first == 1
        assert second == 0  # 幂等
        item = state.pending_confirmations[0]
        assert item["status"] == "retired"
        assert item["retired_reason"] == "policy_retired"
        assert item["status"] != "approved"  # 不伪造成用户批准
        assert item["question"]  # 原记录保留供审计
        assert not is_actionable_pending_confirmation(item)
        assert pending_confirmation_gate(state) is None

    def test_l02_semantic_method_pending_is_preserved(self):
        state = AnalysisSessionState(session_id="p08_l02")
        state.pending_confirmations = [_legacy_method_pending(
            missing_value="复购的分母（全部用户 vs 购卡用户）",
            affected_operations=["analysis.retention"],
        )]

        retired = retire_method_approval_confirmations(state)

        assert retired == 0
        assert state.pending_confirmations[0]["status"] == "pending"

    def test_l03_unknown_provenance_without_semantics_is_not_auto_retired(self):
        state = AnalysisSessionState(session_id="p08_l03")
        item = _legacy_method_pending()
        item.pop("source")
        item.pop("state_updates")
        state.pending_confirmations = [item]

        retired = retire_method_approval_confirmations(state)

        assert retired == 0
        assert state.pending_confirmations[0]["status"] == "pending"

    def test_l01_prepare_turn_retires_detector_sourced_method_pending(self):
        state = AnalysisSessionState(session_id="p08_l01_prepare", data_state="data_loaded")
        state.pending_confirmations = [_legacy_method_pending(
            id="detector_gate", source="question_need_detector",
        )]
        state.pending_confirmations[0].pop("state_updates")

        controller = AnalysisFlowController("p08_l01_prepare")
        controller.prepare_turn(
            state,
            _intent(),
            user_input="analyze retention",
            dataset_profile="- retention: 7 rows x 2 cols",
        )

        assert state.pending_confirmations[0]["status"] == "retired"


class TestP08NoDataRecovery:

    def test_no_data_prompt_gets_short_recovery_instruction(self, tmp_path, monkeypatch):
        """P08-05：无数据时提示词注入最短恢复约束（不列路线菜单、不追问背景）。"""
        from data_agent.session.workspace import workspace as workspace_obj

        # 全量套件中进程级 workspace 单例可能残留先前测试的数据集；
        # 显式置空保证本用例与执行顺序无关。
        monkeypatch.setattr(workspace_obj, "list_datasets", lambda: {})
        from data_agent.agent.loop import AgentLoop

        loop = AgentLoop(client=None, session_id="p08_no_data")
        loop.messages = [{"role": "user", "content": "missing_orders"}]

        prompt = loop._build_system_prompt()

        assert "<no_data_recovery>" in prompt
        assert "缺少数据" in prompt or "没有可分析的数据" in prompt
        assert "不要列举未来分析路线菜单" in prompt

    def test_with_data_no_recovery_block(self, tmp_path, monkeypatch):
        from data_agent.session.workspace import workspace as workspace_obj

        monkeypatch.setattr(workspace_obj, "list_datasets", lambda: {"sales": {"rows": 5, "columns": 2, "column_names": []}})
        from data_agent.agent.loop import AgentLoop

        loop = AgentLoop(client=None, session_id="p08_with_data")
        loop.messages = [{"role": "user", "content": "分析 sales"}]

        prompt = loop._build_system_prompt()

        assert "<no_data_recovery>" not in prompt
