"""P0-3 objective scenario auditor: deterministic five-dimension verdicts.

Every check reads only persisted artifacts (session dirs, ledger, reports).
Semantic impressions never decide a blocking verdict; open-class items are
advisory only.  Each mechanical oracle must cite the plan principle it
enforces, so oracle drift from the approved principles is detectable.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.testing.p08_scenario_audit import (
    MECHANICAL_ORACLES,
    _detect_scenario_from,
    audit_run_dir,
    audit_session,
    oracle_contract_is_consistent,
)


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _make_session(
    run_dir: Path,
    sid: str,
    *,
    summary: str,
    status: str = "completed",
    messages: list | None = None,
    reports: dict[str, str] | None = None,
    confirmations: dict | None = None,
) -> Path:
    sdir = run_dir / "sessions" / sid
    _write_json(sdir / "meta.json", {"session_id": sid, "summary": summary})
    _write_json(sdir / "run_state.json", {"turn_id": "t1", "status": status})
    _write_json(sdir / "conversation.json", messages or [
        {"role": "user", "content": summary},
        {"role": "assistant", "content": "12 条订单，合计 120。"},
    ])
    (sdir / "reports").mkdir(parents=True, exist_ok=True)
    for name, body in (reports or {}).items():
        (sdir / "reports" / name).write_text(body, encoding="utf-8")
    if confirmations is not None:
        _write_json(sdir / "confirmations" / "snapshot.json", confirmations)
    return sdir


def _make_ledger(run_dir: Path, calls: list[dict]) -> None:
    lines = [json.dumps(c, ensure_ascii=False) for c in calls]
    (run_dir / "provider-calls.jsonl").write_text("\n".join(lines), encoding="utf-8")


M01_SUMMARY = "请分析当前上传的销售订单数据，给出已验证的关键业务事实和有条件的行动建议。"
M01_EXPORT_REPORT = "conversation_Assistant_Reply_x.md"
M03_SUMMARY = "请分别比较当前六个来源"


class TestOracleContractConsistency:
    def test_every_mechanical_oracle_cites_a_principle_and_dimension(self):
        assert oracle_contract_is_consistent() == []
        for entry in MECHANICAL_ORACLES:
            assert entry["principle"], entry
            assert entry["dim"] in {"execution", "evidence", "value", "transfer", "declaration"}
            assert isinstance(entry["blocking"], bool)


class TestSessionVerdicts:
    def test_clean_session_passes_all_blocking_checks(self, tmp_path):
        sdir = _make_session(
            tmp_path, "s_clean", summary=M01_SUMMARY,
            reports={
                "conversation_Assistant_Reply_1.md": "12 条订单，合计 120",
                "publication_计算来源说明_pub_1.md": "12 条订单，合计 120",
            },
        )
        verdict = audit_session(sdir, scenario="M01", actions=["refresh"])
        blocking = [c["check"] for c in verdict["checks"] if c["blocking"] and not c["passed"]]
        assert blocking == []

    def test_export_missing_conversation_markdown_is_blocking(self, tmp_path):
        sdir = _make_session(
            tmp_path, "s_exp", summary=M01_SUMMARY,
            reports={"publication_计算来源说明_pub_1.md": "12 条订单，合计 120"},
        )
        verdict = audit_session(sdir, scenario="M01", actions=["refresh", "export_markdown"])
        failed = [c["check"] for c in verdict["checks"] if c["blocking"] and not c["passed"]]
        assert "export_dual_artifacts" in failed

    def test_unpaired_tool_message_is_blocking(self, tmp_path):
        msgs = [
            {"role": "user", "content": M01_SUMMARY},
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "call_a", "function": {"name": "preview_data", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "call_b", "content": "{}"},
        ]
        sdir = _make_session(tmp_path, "s_pair", summary=M01_SUMMARY, messages=msgs)
        verdict = audit_session(sdir, scenario="M01", actions=[])
        failed = [c["check"] for c in verdict["checks"] if c["blocking"] and not c["passed"]]
        assert "tool_pairing_closed" in failed

    def test_unauthorized_confirmation_type_is_blocking(self, tmp_path):
        conf = {"records": {"c1": {"confirmation_type": "data_quality_confirmation", "status": "resolved"}}}
        sdir = _make_session(tmp_path, "s_conf", summary=M01_SUMMARY, confirmations=conf)
        verdict = audit_session(sdir, scenario="M01", actions=[])
        failed = [c["check"] for c in verdict["checks"] if c["blocking"] and not c["passed"]]
        assert "confirmations_authorized" in failed

    def test_run_state_not_terminal_is_blocking(self, tmp_path):
        sdir = _make_session(tmp_path, "s_run", summary=M01_SUMMARY, status="running")
        verdict = audit_session(sdir, scenario="M01", actions=[])
        failed = [c["check"] for c in verdict["checks"] if c["blocking"] and not c["passed"]]
        assert "run_state_terminal_unique" in failed


class TestRunLevelVerdicts:
    def _base_run(self, tmp_path):
        _make_session(
            tmp_path, "s1", summary=M01_SUMMARY,
            reports={
                "conversation_Assistant_Reply_1.md": "12 条订单，合计 120",
                "publication_x.md": "12 条订单，合计 120",
            },
        )
        _make_ledger(tmp_path, [
            {"at": 1.0, "event": "started", "call_number": 1},
            {"at": 2.0, "event": "dispatched", "call_number": 1},
            {"at": 3.0, "event": "completed", "call_number": 1},
        ])

    def test_ledger_unclosed_is_blocking(self, tmp_path):
        self._base_run(tmp_path)
        _make_ledger(tmp_path, [
            {"at": 1.0, "event": "started", "call_number": 1},
            {"at": 2.0, "event": "started", "call_number": 2},
        ])
        report = audit_run_dir(tmp_path)
        assert any(
            c["check"] == "ledger_closed" and c["blocking"] and not c["passed"]
            for c in report["run_checks"]
        )

    def test_ledger_duration_over_deadline_is_blocking(self, tmp_path):
        self._base_run(tmp_path)
        _make_ledger(tmp_path, [
            {"at": 1.0, "event": "started", "call_number": 1},
            {"at": 700.0, "event": "dispatched", "call_number": 1},
        ])
        report = audit_run_dir(tmp_path)
        assert any(
            c["check"] == "ledger_max_duration" and c["blocking"] and not c["passed"]
            for c in report["run_checks"]
        )

    def test_mechanically_clean_run_remains_incomplete_without_claim_oracle(self, tmp_path):
        self._base_run(tmp_path)
        report = audit_run_dir(tmp_path)
        blocking = [c for c in report["run_checks"] if c["blocking"] and not c["passed"]]
        scenarios_blocking = {
            sid: [c for c in v["checks"] if c["blocking"] and not c["passed"]]
            for sid, v in report["sessions"].items()
        }
        assert blocking == []
        assert all(v == [] for v in scenarios_blocking.values())
        assert report["verdict"] == "incomplete"
        assert report["required_unassessed"] == ["numeric_claim_consistency"]

    def test_multiturn_numbers_are_not_judged_by_last_reply_tokens(self, tmp_path):
        sdir = _make_session(tmp_path, "s_multiturn", summary=M01_SUMMARY, messages=[
            {"role": "user", "content": M01_SUMMARY},
            {"role": "assistant", "content": "12 条订单，金额 120；单位未知。"},
            {"role": "user", "content": "请比较下一窗口"},
            {"role": "assistant", "content": "下一窗口尚未观测。"},
        ])
        verdict = audit_session(sdir, scenario="M01", actions=[])
        assert verdict["required_assessments"]["numeric_claim_consistency"]["status"] == "unassessed"
        assert not any(c["check"] == "answer_numeric_oracles" for c in verdict["checks"])

    def test_first_turn_failure_survives_later_completed_session_state(self, tmp_path):
        self._base_run(tmp_path)
        _write_json(tmp_path / "freeze.json", {
            "matrix": ["M01"], "scenario_inputs": {"M01": {"prompts": ["first", "second"]}},
        })
        rows = [
            {"scenario": "M01", "turn": 1, "session_id": "s1", "terminal": "failed",
             "run_state": {"session_id": "s1", "status": "failed"}},
            {"scenario": "M01", "turn": 2, "session_id": "s1", "terminal": "completed",
             "run_state": {"session_id": "s1", "status": "completed"}},
        ]
        (tmp_path / "http-matrix.jsonl").write_text(
            "\n".join(json.dumps(row) for row in rows), encoding="utf-8",
        )
        report = audit_run_dir(tmp_path)
        outcome = next(item for item in report["run_checks"]
                       if item["check"] == "matrix_turn_outcomes")
        assert outcome["passed"] is False
        assert "M01/1" in outcome["detail"]
        assert report["verdict"] == "failed"


class TestAdvisoryOnlySemantics:
    def test_open_class_items_are_never_blocking(self, tmp_path):
        sdir = _make_session(tmp_path, "s_soft", summary=M01_SUMMARY, messages=[
            {"role": "user", "content": M01_SUMMARY},
            {"role": "assistant", "content": "这数据像是样例数据；合计约 120 块。"},
        ])
        verdict = audit_session(sdir, scenario="M01", actions=[])
        soft = [c for c in verdict["checks"] if not c["passed"]]
        assert soft
        assert all(not c["blocking"] for c in soft), soft


class TestRulerCalibrationGaps:
    """Three gaps found by calibrating against the real R21/R19 batches."""

    def test_failed_run_state_is_a_blocking_scenario_failure(self, tmp_path):
        sdir = _make_session(tmp_path, "s_failed", summary=M01_SUMMARY, status="failed")
        verdict = audit_session(sdir, scenario="M01", actions=[])
        failed = [c["check"] for c in verdict["checks"] if c["blocking"] and not c["passed"]]
        assert "run_state_completed" in failed

    def test_compressed_summary_session_is_still_mapped_to_scenario(self, tmp_path):
        sdir = _make_session(
            tmp_path, "s_comp", summary="[Context compressed at turn boundary]\n## 结构化摘要",
            messages=[
                {"role": "user", "content": M01_SUMMARY},
                {"role": "assistant", "content": "12 条订单，合计 120。"},
            ],
        )
        assert _detect_scenario_from(sdir) == "M01"

    def test_fully_compressed_session_maps_via_unique_fixture_prefix(self, tmp_path):
        sdir = _make_session(
            tmp_path, "s_comp2", summary="[Context compressed at turn boundary]\n## 摘要",
            messages=[{"role": "user", "content": "# 结构化摘要，原始提示词已被压缩替换"}],
        )
        upload_dir = sdir / "uploads" / "abc123"
        upload_dir.mkdir(parents=True)
        _write_json(upload_dir / "upload.json", {"filename": "M03-source-2.csv", "status": "loaded"})
        assert _detect_scenario_from(sdir) == "M03"

    def test_m06_cost_scope_question_is_authorized_but_data_nature_question_is_not(self, tmp_path):
        cost_scope = {"records": {"c1": {
            "operation": "direct_user_question", "answer_mode": "single_select",
            "question": "计算「促销净收益」时，成本口径采用哪一种？"}}}
        data_nature = {"records": {"c1": {
            "operation": "direct_user_question", "answer_mode": "single_select",
            "question": "这份 M01-sales 数据的性质是？"}}}
        m06 = _make_session(tmp_path, "s_m6", summary="请分析名为 missing_orders", confirmations=cost_scope)
        m01 = _make_session(tmp_path, "s_m1c", summary=M01_SUMMARY, confirmations=data_nature)
        v6 = audit_session(m06, scenario="M06", actions=[])
        v1 = audit_session(m01, scenario="M01", actions=[])
        assert all(c["passed"] for c in v6["checks"] if c["check"] == "confirmations_authorized")
        failed = [c["check"] for c in v1["checks"] if c["blocking"] and not c["passed"]]
        assert "confirmations_authorized" in failed


class TestYoyReceiptBinding:
    """P1-6：同比标签的跨年判定来自 compare_periods 回执，不再挖散文年份。"""

    _SAME_YEAR = {
        "period_a": {"label": "本期", "range": ["2026-09-01", "2026-09-02"]},
        "period_b": {"label": "对比期", "range": ["2026-09-08", "2026-09-09"]},
    }
    _CROSS_YEAR = {
        "period_a": {"label": "去年同周", "range": ["2025-09-01", "2025-09-07"]},
        "period_b": {"label": "本周", "range": ["2026-09-01", "2026-09-07"]},
    }

    def _m03_session(self, tmp_path, sid, final_text, receipt):
        sdir = _make_session(tmp_path, sid, summary=M03_SUMMARY, messages=[
            {"role": "user", "content": M03_SUMMARY},
            {"role": "assistant", "content": final_text},
        ])
        _write_json(sdir / "tool_outputs" / "compare_periods_1.json", receipt)
        return sdir

    def test_sameyear_receipt_with_yoy_label_is_blocking_even_with_prose_years(self, tmp_path):
        """R16 通路收口：散文出现两个年份不再放行，判定只认回执。"""
        sdir = self._m03_session(
            tmp_path, "s_yoy_r",
            "2025 与 2026 两个年度口径合并后六来源合计 210 与 231，金额同比增长 10%。",
            self._SAME_YEAR,
        )
        verdict = audit_session(sdir, scenario="M03", actions=[])
        failed = [c["check"] for c in verdict["checks"] if c["blocking"] and not c["passed"]]
        assert "yoy_requires_crossyear_receipt" in failed

    def test_crossyear_receipt_supports_yoy_label_without_prose_years(self, tmp_path):
        sdir = self._m03_session(
            tmp_path, "s_yoy_ok",
            "六来源合计 210 与 231；金额同比增长 10%。",
            self._CROSS_YEAR,
        )
        verdict = audit_session(sdir, scenario="M03", actions=[])
        yoy = [c for c in verdict["checks"] if c["check"] == "yoy_requires_crossyear_receipt"][0]
        assert yoy["passed"]

    def test_same_proportional_wording_is_not_a_yoy_label(self, tmp_path):
        sdir = self._m03_session(
            tmp_path, "s_yoy_prop",
            "各来源同比例上升：合计 210 与 231。",
            self._SAME_YEAR,
        )
        verdict = audit_session(sdir, scenario="M03", actions=[])
        yoy = [c for c in verdict["checks"] if c["check"] == "yoy_requires_crossyear_receipt"][0]
        assert yoy["passed"]


M06_SUMMARY = "请分析名为 missing_orders 的数据集"


@pytest.mark.parametrize("defect",[None,"missing","sha","session","check","unassessed","failed"])
def test_browser_assessment_requires_bound_current_visual_receipt(tmp_path,defect):
    import hashlib
    from scripts.testing.p08_scenario_audit import _browser_assessments
    freeze={"matrix":["M06"],"operator_protocol":{"visual_checkpoint":"closed_ledger_stdin_v2",
        "visual_checks":{"scenario_end":["answer","workbench","refresh"],"confirmation":["confirmation"]}},
        "scenario_inputs":{"M06":{"actions":["export_markdown"],"confirmations":{"2":{}}}}}
    receipt={"scenario":"M06","session_id":"s1","checkpoint":"scenario_end","status":"passed",
        "checks":{k:"passed" for k in ("answer","workbench","refresh","exports")},"evidence":["actual-screen.png"]}
    if defect=="session":receipt["session_id"]="other"
    if defect=="check":receipt["checks"].pop("exports")
    if defect in {"unassessed","failed"}:receipt["status"]=defect
    _write_json(tmp_path/"visual.json",receipt)
    row={"scenario":"M06","session_id":"s1","checkpoint":"scenario_end","action":"visual_checkpoint_result",
        "visual_status":receipt["status"],"evidence_path":"visual.json",
        "evidence_sha256":"sha256:"+hashlib.sha256((tmp_path/"visual.json").read_bytes()).hexdigest()}
    if defect=="sha":row["evidence_sha256"]="sha256:"+"0"*64
    rows=[{"scenario":"M06","session_id":"s1","terminal":"completed"}]+([] if defect=="missing" else [row])
    (tmp_path/"http-matrix.jsonl").write_text("\n".join(json.dumps(r) for r in rows),encoding="utf-8")
    verdict=_browser_assessments(tmp_path,freeze)
    assert verdict["browser:M06:scenario_end"]["status"]==("passed" if defect is None else "unassessed" if defect in {"missing","unassessed"} else "failed")
    assert verdict["browser:M06:confirmation:2"]["status"]=="unassessed"


def test_frozen_http_mapping_ignores_snapshot_rows_and_pairs_each_resume(tmp_path):
    from scripts.testing.p08_scenario_audit import _http_turn_outcome_check
    _write_json(tmp_path/"freeze.json",{"matrix":["M06"],"scenario_inputs":{"M06":{
        "prompts":["consultation first","second"],"confirmations":{"1":{},"2":{}}}}})
    rows=[]
    for index in (1,2):
        rows.extend([
            {"scenario":"M06","turn":index,"session_id":"fresh","terminal":"suspended","run_state":{"status":"suspended","session_id":"fresh"}},
            {"scenario":"M06","turn":index,"action":"current_publication_snapshot","session_id":"fresh"},
            {"scenario":"M06","turn":"resume","parent_turn":index,"session_id":"fresh","terminal":"completed","run_state":{"status":"completed","session_id":"fresh"}},
        ])
    (tmp_path/"http-matrix.jsonl").write_text("\n".join(json.dumps(row) for row in rows),encoding="utf-8")
    assert _http_turn_outcome_check(tmp_path)["passed"]
    _make_session(tmp_path,"fresh",summary="[Context compressed at turn boundary] unrelated",messages=[])
    report=audit_run_dir(tmp_path)
    assert report["sessions"]["fresh"]["scenario"]=="M06"


class TestSingleNextStepAdvisory:
    """P2-2：M06"唯一下一步"进价值维软检查。

    RED 素材为 r1 批次 M06 终稿："下一步（单一动作）：请提供……"——把
    单一路径写成排他式唯一下一步。按治理分层，这是价值维开放语义：
    召回式软检查（advisory，永不阻断），条件式指引（触发/停止条件）不计。
    """

    def _m06_session(self, tmp_path, sid, final_text):
        return _make_session(tmp_path, sid, summary=M06_SUMMARY, messages=[
            {"role": "user", "content": M06_SUMMARY},
            {"role": "assistant", "content": final_text},
        ])

    def test_exclusive_next_step_is_advisory_value_finding(self, tmp_path):
        sdir = self._m06_session(
            tmp_path, "s_m06_single",
            "缺失字段使净收益不可算；合计 120 条订单可确认。\n"
            "下一步（单一动作）：请提供含 voucher_cost 与 channel_cost 的数据文件。",
        )
        verdict = audit_session(sdir, scenario="M06", actions=[])
        check = [c for c in verdict["checks"] if c["check"] == "single_next_step_advisory"][0]
        assert not check["passed"]
        # 软检查永不阻断
        assert not check["blocking"]

    def test_conditional_guidance_without_exclusive_framing_passes(self, tmp_path):
        sdir = self._m06_session(
            tmp_path, "s_m06_cond",
            "合计 120 条订单可确认。条件性建议：若需净收益，触发条件是补充"
            "voucher_cost 字段；若不做成本核算，当前描述性结论已可交付，停止条件为数据不变。",
        )
        verdict = audit_session(sdir, scenario="M06", actions=[])
        check = [c for c in verdict["checks"] if c["check"] == "single_next_step_advisory"][0]
        assert check["passed"]
