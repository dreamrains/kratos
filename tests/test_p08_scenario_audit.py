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

    def test_clean_run_passes(self, tmp_path):
        self._base_run(tmp_path)
        report = audit_run_dir(tmp_path)
        blocking = [c for c in report["run_checks"] if c["blocking"] and not c["passed"]]
        scenarios_blocking = {
            sid: [c for c in v["checks"] if c["blocking"] and not c["passed"]]
            for sid, v in report["sessions"].items()
        }
        assert blocking == []
        assert all(v == [] for v in scenarios_blocking.values())
        assert report["verdict"] == "passed"


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
