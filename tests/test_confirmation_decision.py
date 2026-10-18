"""IC1: the unified decision policy for confirmation candidates.

Covers the acceptance-matrix policy layer: Q04/Q05 (real cost-scope gap asks
and its already-answered reuse), Q12 (model-claimed safe defaults and scopes
are never trusted), and the reuse semantics R01–R05.
"""

from data_agent.agent.confirmation.decision import (
    decision_context_from_candidate,
    is_method_approval_shaped,
    normalized_business_scope,
    represents_business_gap,
    stable_decision_key,
)
from data_agent.agent.confirmation.models import ConfirmationStatus
from data_agent.agent.confirmation.policy import QuestionPolicy, RequestDisposition
from data_agent.agent.confirmation.runtime import build_direct_question_candidate


def _candidate(request, *, session_id="s1", turn_id="t1", message_version=2, **overrides):
    payload = dict(request)
    payload.update(overrides)
    return build_direct_question_candidate(
        session_id=session_id,
        turn_id=turn_id,
        message_version=message_version,
        request=payload,
    )


COST_SCOPE_ASK = {
    "question": "净收益的成本是否包含券成本？",
    "options": [
        {"label": "包含券成本", "value": "include_coupon"},
        {"label": "不包含券成本", "value": "exclude_coupon"},
    ],
    "confirmation_type": "metric_definition",
    "missing_value": "净收益的成本范围",
    "affected_operations": ["net_revenue_calculation", "roi_summary"],
    "blocking_reason": "两种成本口径会得到方向相反的净收益结论",
}

METHOD_ASK = {
    "question": "是否使用留存方法继续分析？",
    "options": [{"label": "按此方法继续", "value": "confirm_method"}],
    "confirmation_type": "method_confirmation",
}

MISLABELED_COST_SCOPE_ASK = {
    "question": "评估促销净收益时，成本口径采用哪一种？（即净收益 = 促销收入 − 哪些成本）",
    "options": [
        {"label": "仅扣代金券成本", "value": "voucher_only"},
        {"label": "代金券成本及渠道成本", "value": "voucher_and_channel"},
    ],
    "confirmation_type": "method_confirmation",
    "blocking_reason": "成本口径直接改变净收益结果，需用户先定义口径。",
}


class TestDecisionContract:

    def test_q04_real_cost_scope_gap_confirms(self):
        result = QuestionPolicy().evaluate(_candidate(COST_SCOPE_ASK))

        assert result.disposition is RequestDisposition.CONFIRMATION
        assert result.request is not None

    def test_q09_method_approval_ask_downgrades_to_advisory(self):
        result = QuestionPolicy().evaluate(_candidate(METHOD_ASK))

        assert result.disposition is RequestDisposition.ADVISORY
        assert "方法" in result.reason or "内部决策" in result.reason

    def test_q04_cost_scope_mislabeled_as_method_is_recovered_as_business_gap(self):
        candidate = _candidate(MISLABELED_COST_SCOPE_ASK)
        result = QuestionPolicy().evaluate(candidate)

        assert decision_context_from_candidate(candidate)["decision_kind"] == "metric_definition"
        assert candidate.resolution_params["confirmation_type"] == "metric_definition"
        assert not is_method_approval_shaped(candidate)
        assert result.disposition is RequestDisposition.CONFIRMATION

    def test_q09_explicit_method_permission_is_not_promoted_by_cost_words(self):
        request = dict(METHOD_ASK)
        request["question"] = "是否使用 ROI 模型继续分析渠道成本？"
        result = QuestionPolicy().evaluate(_candidate(request))

        assert result.disposition is RequestDisposition.ADVISORY

    def test_candidate_without_semantic_kind_is_not_a_business_gap(self):
        # 无语义类型（decision_kind 为空）的候选不是业务缺口——问题文本再具体
        # 也不得只凭自由文本悬挂用户。
        request = dict(COST_SCOPE_ASK)
        request["confirmation_type"] = ""
        request.pop("missing_value")
        request.pop("affected_operations")

        result = QuestionPolicy().evaluate(_candidate(request))

        assert result.disposition is not RequestDisposition.CONFIRMATION

    def test_q12_model_claimed_safe_default_is_not_an_advisory_basis(self):
        request = dict(COST_SCOPE_ASK)
        request_with_claim = dict(request)
        # 模型自报 safe_default（无 default_origin 或 origin=model_claim）
        result = QuestionPolicy().evaluate(_candidate(request_with_claim, safe_default="默认包含券成本"))

        assert result.disposition is RequestDisposition.CONFIRMATION, (
            "模型自报默认值不能把真实业务缺口降为 advisory"
        )

    def test_q12_direct_origin_label_does_not_prove_a_host_default(self):
        # The original fixture was a direct model request carrying a label,
        # not a host-verified source. Actual host-producer policy controls remain.
        request = dict(COST_SCOPE_ASK)

        result = QuestionPolicy().evaluate(_candidate(
            request,
            safe_default="默认包含券成本",
            default_origin="user_request",
        ))

        assert result.disposition is RequestDisposition.CONFIRMATION

    def test_business_scope_normalization_keeps_negation_and_numbers(self):
        assert normalized_business_scope(" 包含  券成本 ") != normalized_business_scope("不包含券成本")
        assert normalized_business_scope("窗口 30 天") != normalized_business_scope("窗口 7 天")
        assert normalized_business_scope("窗口  30 天") == normalized_business_scope("窗口 30 天")


class TestReuse:

    def _resolved_record(self, candidate, answer="include_coupon"):
        request = QuestionPolicy().evaluate(candidate).request
        record = type(
            "Record",
            (),
            {
                "confirmation_id": "rec_1",
                "status": ConfirmationStatus.RESOLVED,
                "decision_key": candidate.decision_key,
                "data_version": candidate.data_version,
                "spec_version": candidate.spec_version,
            },
        )()
        return record

    def test_r01_same_decision_rephrased_display_reuses(self):
        first = _candidate(COST_SCOPE_ASK)
        # 换显示文案：问题措辞变化、选项标签变化但业务范围与选项值不变
        rephrased = dict(COST_SCOPE_ASK)
        rephrased["question"] = "请确认净收益成本口径（含券/不含券）"
        rephrased["options"] = [
            {"label": "含券", "value": "include_coupon"},
            {"label": "不含券", "value": "exclude_coupon"},
        ]
        second = _candidate(rephrased, turn_id="t9", message_version=88)

        assert first.decision_key == second.decision_key
        result = QuestionPolicy().evaluate(second, existing=[self._resolved_record(first)])
        assert result.disposition is RequestDisposition.REUSED
        assert result.reused_confirmation_id == "rec_1"

    def test_r02_message_count_never_changes_the_key(self):
        first = _candidate(COST_SCOPE_ASK, message_version=2)
        second = _candidate(COST_SCOPE_ASK, turn_id="t7", message_version=57)

        assert first.decision_key == second.decision_key

    def test_r04_scope_change_does_not_reuse_conflicting_answer(self):
        first = _candidate(COST_SCOPE_ASK)
        changed = dict(COST_SCOPE_ASK)
        changed["missing_value"] = "净收益的成本范围（不含券）"

        second = _candidate(changed, turn_id="t5", message_version=30)

        assert first.decision_key != second.decision_key
        result = QuestionPolicy().evaluate(second, existing=[self._resolved_record(first)])
        assert result.disposition is RequestDisposition.CONFIRMATION

    def test_r05_relevant_data_version_change_blocks_reuse(self):
        second = _candidate(COST_SCOPE_ASK, turn_id="t3", message_version=20, scope_data_version="fp_v2")
        record_v1 = type("Record", (), {
            "confirmation_id": "rec_2",
            "status": ConfirmationStatus.RESOLVED,
            "decision_key": second.decision_key,
            "data_version": "fp_v1",
            "spec_version": second.spec_version,
        })()

        result = QuestionPolicy().evaluate(second, existing=[record_v1])

        assert result.disposition is RequestDisposition.CONFIRMATION

    def test_r05_unrelated_file_change_keeps_reuse_when_scope_unversioned(self):
        first = _candidate(COST_SCOPE_ASK)
        second = _candidate(COST_SCOPE_ASK, turn_id="t4", message_version=44)

        result = QuestionPolicy().evaluate(second, existing=[self._resolved_record(first)])

        assert result.disposition is RequestDisposition.REUSED

    def test_r08_only_resolved_records_are_reusable(self):
        first = _candidate(COST_SCOPE_ASK)
        for status in (ConfirmationStatus.SKIPPED, ConfirmationStatus.CANCELLED, ConfirmationStatus.EXPIRED):
            record = type("Record", (), {
                "confirmation_id": f"rec_{status.value}",
                "status": status,
                "decision_key": first.decision_key,
                "data_version": first.data_version,
                "spec_version": first.spec_version,
            })()
            result = QuestionPolicy().evaluate(first, existing=[record])
            assert result.disposition is RequestDisposition.CONFIRMATION, status

    def test_unstructured_candidates_keep_per_occurrence_keys(self):
        vague = {
            "question": "顺便确认一下整体方向？",
            "options": [],
            "confirmation_type": "",
        }
        first = _candidate(vague, turn_id="t1", message_version=2)
        second = _candidate(vague, turn_id="t2", message_version=3)

        # 没有语义范围的结构不明候选不得进入稳定复用键
        assert first.decision_key != second.decision_key
        assert not represents_business_gap(first)


class TestDetectorGateContext:

    def test_internal_gate_payloads_satisfy_the_contract(self):
        # detector 的 time_window 门载荷：risk_fields/affected_routes 变成决策上下文
        gate_request = {
            "question": "请确认要对比的时间窗口",
            "options": [
                {"label": "最近 7 天对比前 7 天", "value": "win_7"},
                {"label": "活动前后各 15 天", "value": "win_15"},
            ],
            "confirmation_type": "time_window",
            "risk_fields": ["时间窗口"],
            "affected_routes": ["period_compare"],
            "blocking_reason": "期间对比依赖明确窗口",
        }
        candidate = _candidate(gate_request)

        context = decision_context_from_candidate(candidate)
        assert context["decision_kind"] == "time_window"
        assert context["missing_value"]
        assert context["affected_operations"]
        result = QuestionPolicy().evaluate(candidate)
        assert result.disposition is RequestDisposition.CONFIRMATION


class TestLoopDirectAskIntegration:
    """Q09/Q10 at the loop layer: advisory asks answer in-turn; real gaps suspend."""

    def test_q09_method_ask_returns_advisory_text_not_suspension(self, tmp_path, monkeypatch):
        import data_agent.agent.loop as loop_module
        from data_agent.agent.loop import AgentLoop, UserConfirmationRequired

        cfg = loop_module.get_config()
        monkeypatch.setattr(cfg, "sessions_dir", tmp_path)
        loop = AgentLoop(client=None, session_id="ic2_method_ask")

        ucc = UserConfirmationRequired(
            question="是否使用留存方法继续分析？",
            options=[{"label": "按此方法继续", "value": "confirm_method"}],
            confirmation_type="method_confirmation",
        )

        result = loop._suspend_for_confirmation_request(ucc, turn_id="ask_1")

        assert isinstance(result, str)
        assert "无需用户确认" in result

    def test_q10_real_semantic_ask_still_suspends(self, tmp_path, monkeypatch):
        import data_agent.agent.loop as loop_module
        from data_agent.agent.loop import AgentLoop, SuspendedForConfirmation, UserConfirmationRequired

        cfg = loop_module.get_config()
        monkeypatch.setattr(cfg, "sessions_dir", tmp_path)
        loop = AgentLoop(client=None, session_id="ic2_semantic_ask")

        ucc = UserConfirmationRequired(
            question="净收益的成本是否包含券成本？",
            options=[
                {"label": "包含券成本", "value": "include_coupon"},
                {"label": "不包含券成本", "value": "exclude_coupon"},
            ],
            confirmation_type="metric_definition",
            blocking_reason="两种成本口径会得到方向相反的净收益结论",
            decision_context={
                "decision_kind": "metric_definition",
                "missing_value": "净收益的成本范围",
                "affected_operations": ["net_revenue_calculation"],
            },
        )

        result = loop._suspend_for_confirmation_request(ucc, turn_id="ask_2")

        assert isinstance(result, SuspendedForConfirmation)

    def test_reused_answer_returns_prior_answer_text(self, tmp_path, monkeypatch):
        import data_agent.agent.loop as loop_module
        from data_agent.agent.loop import AgentLoop, UserConfirmationRequired
        from data_agent.agent.confirmation.decision import decision_context_from_payload

        from tests.test_confirmation_runtime import _s3_bound_question_fixture
        loop, _ = _s3_bound_question_fixture(tmp_path, monkeypatch, session_id="ic2_reuse_ask")
        service = loop._confirmation_runtime()

        ask = {
            "question": "净收益的成本是否包含券成本？",
            "options": [
                {"label": "包含券成本", "value": "include_coupon"},
                {"label": "不包含券成本", "value": "exclude_coupon"},
            ],
            "confirmation_type": "metric_definition",
            "missing_value": "净收益的成本范围",
            "affected_operations": ["net_revenue_calculation"],
            "blocking_reason": "两种成本口径会得到方向相反的净收益结论",
        }
        from data_agent.agent.confirmation.runtime import build_direct_question_candidate

        first = loop._suspend_for_confirmation_request(UserConfirmationRequired(
            question=ask["question"], options=ask["options"],
            confirmation_type=ask["confirmation_type"], blocking_reason=ask["blocking_reason"],
            decision_context={"decision_kind":"metric_definition", "missing_value":ask["missing_value"],
                              "affected_operations":ask["affected_operations"]}), turn_id="t1")
        assert first.confirmation_id
        active = service.checkpoint("ic2_reuse_ask")
        assert active is not None
        service.respond("ic2_reuse_ask", active.confirmation_id, "include_coupon", active.version, "ic1_reuse_answer_1")

        ucc = UserConfirmationRequired(
            question=ask["question"],
            options=ask["options"],
            confirmation_type=ask["confirmation_type"],
            blocking_reason=ask["blocking_reason"],
            decision_context={
                "decision_kind": "metric_definition",
                "missing_value": ask["missing_value"],
                "affected_operations": ask["affected_operations"],
            },
        )
        result = loop._suspend_for_confirmation_request(ucc, turn_id="t9")

        assert isinstance(result, str)
        assert "此前的回答仍然适用" in result
        assert "include_coupon" in result


class _Raiser:
    """Client stub whose chat raises; drives the UserConfirmationRequired path."""

    def __init__(self, inner):
        self._inner = inner

    def __getattr__(self, name):
        return getattr(self._inner, name)
