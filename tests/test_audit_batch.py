# tests/test_audit_batch.py
"""Offline audit runner tests: containment, oracles, observer gaps, wiring."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.acceptance import audit_batch as audit_module
from scripts.acceptance.audit_batch import audit_batch
from scripts.acceptance.matrix_oracles import ORACLE_VERSION


def _file_hash(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _call(ordinal, status="completed", stopped=True):
    return {"ordinal": ordinal, "model": "m", "stream": False, "max_tokens": 8000,
            "status": status, "started_at": "t0", "local_request_stopped": stopped}


def _receipt(calls, *, cap=4, blocked=0):
    return {"schema_version": 3, "candidate_id": "c", "source_digest": "sha256:s",
            "call_cap": cap, "calls": calls, "blocked_attempts": blocked,
            "terminal_failure": {"code": "acceptance_server_closed"}}


GOOD_EXIT_PROOF = {"schema_version": "browser_process_exit.v1", "pid": 11, "exit_code": 0,
                   "process_exited": True, "graceful_exit": True, "forced_termination": False,
                   "timeout_reached": False, "elapsed_after_stop_seconds": 0.2,
                   "stop_observed_at": "t"}

CLEAN_REPLY = "拟合完成；相关而非因果；未外推超出观测窗口。"


def _build_batch(root: Path, cases: dict) -> Path:
    """Synthesize ledger + frozen candidates + receipts + session evidence.

    ``cases[case_id]``: oracle, receipt, conversation messages, exit_proof,
    session_files, ledger_status, ledger_cap, receipt_sha256 override.
    """
    entries, ledger_records = [], []
    for case_id, spec in cases.items():
        writes = {
            "workspace_dir": f"tmp/run/{case_id}/workspace",
            "sessions_dir": f"tmp/run/{case_id}/sessions",
            "provider_receipt_path": f"tmp/run/{case_id}/provider-calls.json",
            "report_path": f"docs/audit/{case_id}-report.json",
            "process_control_dir": f"tmp/run/{case_id}/process-control",
        }
        case = {"matrix_case_id": case_id, "candidate_id": f"c_{case_id}",
                "oracle": spec.get("oracle", {}), "writes": writes}
        candidate_path = root / "docs/audit" / f"{case_id.lower()}-candidate.json"
        candidate_path.parent.mkdir(parents=True, exist_ok=True)
        candidate_path.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
        entries.append({"id": case_id,
                        "path": str(candidate_path.relative_to(root)).replace("\\", "/")})

        receipt_path = root / writes["provider_receipt_path"]
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(spec["receipt"], ensure_ascii=False), encoding="utf-8")

        sessions = root / writes["sessions_dir"] / "s1"
        sessions.mkdir(parents=True, exist_ok=True)
        (sessions / "conversation.jsonl").write_text(
            "\n".join(json.dumps(m, ensure_ascii=False) for m in spec.get("conversation", [])),
            encoding="utf-8")
        for relative in spec.get("session_files", []):
            target = sessions / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("export", encoding="utf-8")

        if spec.get("exit_proof") is not None:
            control = root / writes["process_control_dir"]
            control.mkdir(parents=True, exist_ok=True)
            (control / "process-exit.json").write_text(
                json.dumps(spec["exit_proof"]), encoding="utf-8")

        receipt_sha = spec.get("receipt_sha256", _file_hash(receipt_path))
        ledger_records.append({"id": case_id, "status": spec.get("ledger_status", "closed"),
                               "call_cap": spec.get("ledger_cap", 4),
                               "receipt_sha256": receipt_sha,
                               "terminal_failure": {"code": "acceptance_server_closed"}})

    ledger_path = root / "tmp/run/provider-batch.json"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(json.dumps(
        {"schema_version": 2, "batch_sha256": "sha256:ledger", "cases": ledger_records},
        ensure_ascii=False), encoding="utf-8")
    batch_path = root / "batch.json"
    batch_path.write_text(json.dumps(
        {"batch_id": "AUD-1", "isolation_root": "tmp/run", "cases": entries}), encoding="utf-8")
    return batch_path


def _audited(root, cases):
    return {case["case_id"]: case
            for case in audit_batch(root, _build_batch(root, cases))["cases"]}


def test_containment_pass_and_failures(tmp_path):
    cases = _audited(tmp_path, {
        "M01": {"receipt": _receipt([_call(1), _call(2)])},
        "M02": {"receipt": _receipt([_call(1), _call(3)])},  # ordinal gap
        "M03": {"receipt": _receipt([_call(1, status="started", stopped=False)])},
        "M04": {"receipt": _receipt([_call(1), _call(2)], cap=1)},  # cap exceeded
        "M05": {"receipt": {**_receipt([_call(1)]), "blocked_attempts": None}},
        "M06": {"receipt_sha256": "sha256:not-the-pinned-hash",
                "receipt": _receipt([_call(1)])},
    })
    assert cases["M01"]["hard_gate"]["passed"] is True
    assert cases["M01"]["hard_gate"]["failures"] == []
    assert "ordinal_sequence" in cases["M02"]["hard_gate"]["failures"]
    assert "non_terminal_calls" in cases["M03"]["hard_gate"]["failures"]
    assert "cap_exceeded" in cases["M04"]["hard_gate"]["failures"]
    assert "blocked_attempts_missing" in cases["M05"]["hard_gate"]["failures"]
    assert "receipt_hash_mismatch_vs_ledger" in cases["M06"]["hard_gate"]["failures"]
    for case_id in ("M02", "M03", "M04", "M05", "M06"):
        assert cases[case_id]["hard_gate"]["passed"] is False


def test_required_tools_hit_and_miss(tmp_path):
    conversation = [
        {"role": "user", "content": "analyze"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "t1", "function": {"name": "detect_data_quality"}}]},
        {"role": "assistant", "content": CLEAN_REPLY},
    ]
    cases = _audited(tmp_path, {
        "M01": {"oracle": {"required_tools": ["detect_data_quality"]},
                "receipt": _receipt([_call(1)]), "conversation": conversation},
        "M02": {"oracle": {"required_tools": ["detect_data_quality", "ab_test"]},
                "receipt": _receipt([_call(1)]), "conversation": conversation},
    })
    assert cases["M01"]["checks"]["required_tools"]["status"] == "pass"
    assert not any(o["check"] == "required_tools" for o in cases["M01"]["failed_oracles"])
    assert cases["M02"]["checks"]["required_tools"]["status"] == "fail"
    failures = [o for o in cases["M02"]["failed_oracles"] if o["check"] == "required_tools"]
    assert failures and failures[0]["missing"] == ["ab_test"]


def test_zero_semantics_violation_is_a_failed_oracle(tmp_path):
    cases = _audited(tmp_path, {
        "M01": {"receipt": _receipt([_call(1)]), "conversation": [
            {"role": "user", "content": "analyze"},
            {"role": "assistant", "content": "发放代金券导致付费提升 12%，因此应扩大投放。"},
        ]},
        "M02": {"receipt": _receipt([_call(1)]), "conversation": [
            {"role": "user", "content": "analyze"},
            {"role": "assistant", "content": CLEAN_REPLY},
        ]},
    })
    violations = [o for o in cases["M01"]["failed_oracles"] if o["check"] == "zero_semantics"]
    assert violations and "unqualified_causal" in violations[0]["violation"]
    assert cases["M01"]["checks"]["zero_semantics"]["status"] == "fail"
    assert cases["M02"]["checks"]["zero_semantics"]["status"] == "pass"
    assert not any(o["check"] == "zero_semantics" for o in cases["M02"]["failed_oracles"])


def test_publication_rejected_replies_are_excluded(tmp_path):
    cases = _audited(tmp_path, {
        "M01": {"receipt": _receipt([_call(1)]), "conversation": [
            {"role": "user", "content": "analyze"},
            # Rejected rewrite draft: its violation must not count as published.
            {"role": "assistant", "content": "折扣造成了流失。", "publication_rejected": True},
            {"role": "assistant", "content": CLEAN_REPLY},
        ]},
    })
    assert cases["M01"]["checks"]["zero_semantics"]["status"] == "pass"
    assert not any(o["check"] == "zero_semantics" for o in cases["M01"]["failed_oracles"])


def test_unprovable_offline_checks_are_observer_gaps_not_failures(tmp_path):
    cases = _audited(tmp_path, {
        "M01": {"receipt": _receipt([_call(1)]), "conversation": [
            {"role": "assistant", "content": CLEAN_REPLY}]},
    })
    case = cases["M01"]
    # Declared observer gap (live timing observation) plus the missing exit
    # proof are separated from failed oracles entirely.
    assert "within_30s_completion_observation" in case["observer_gaps"]
    assert "process_exit_proof_missing" in case["observer_gaps"]
    assert case["failed_oracles"] == []
    assert case["hard_gate"]["passed"] is True

    with_exit = _audited(tmp_path, {
        "M01": {"receipt": _receipt([_call(1)]), "exit_proof": GOOD_EXIT_PROOF,
                "conversation": [{"role": "assistant", "content": CLEAN_REPLY}]},
    })
    assert with_exit["M01"]["checks"]["process_exit"]["status"] == "pass"
    assert "process_exit_proof_missing" not in with_exit["M01"]["observer_gaps"]

    bad_exit = dict(GOOD_EXIT_PROOF, graceful_exit=False, exit_code=1)
    failed = _audited(tmp_path, {
        "M01": {"receipt": _receipt([_call(1)]), "exit_proof": bad_exit,
                "conversation": [{"role": "assistant", "content": CLEAN_REPLY}]},
    })
    assert failed["M01"]["checks"]["process_exit"]["status"] == "fail"
    assert any(o["check"] == "process_exit" for o in failed["M01"]["failed_oracles"])


def test_export_expectations_checked_when_declared(tmp_path):
    oracle = {"html_exports": 1}
    base = {"oracle": oracle, "receipt": _receipt([_call(1)]),
            "conversation": [{"role": "assistant", "content": CLEAN_REPLY}],
            "exit_proof": GOOD_EXIT_PROOF}
    cases = _audited(tmp_path, {
        "M01": {**base, "session_files": ["exports/reply.html"]},
        "M02": dict(base),
        "M03": {"receipt": _receipt([_call(1)]),
                "conversation": [{"role": "assistant", "content": CLEAN_REPLY}]},
    })
    assert cases["M01"]["checks"]["exports"]["status"] == "pass"
    assert cases["M01"]["checks"]["exports"]["html_exports"] == {"expected": 1, "found": 1}
    assert cases["M02"]["checks"]["exports"]["status"] == "fail"
    assert any(o["check"] == "exports" for o in cases["M02"]["failed_oracles"])
    assert cases["M03"]["checks"]["exports"]["status"] == "skipped"


def test_report_file_summary_and_unclosed_case_handling(tmp_path, monkeypatch, capsys):
    batch_path = _build_batch(tmp_path, {
        "M01": {"receipt": _receipt([_call(1)]), "exit_proof": GOOD_EXIT_PROOF,
                "conversation": [{"role": "assistant", "content": CLEAN_REPLY}]},
        "M02": {"ledger_status": "started", "receipt": _receipt([_call(1)])},
    })
    monkeypatch.setattr("sys.argv", ["audit_batch", "--root", str(tmp_path),
                                     "--batch", str(batch_path)])
    exit_code = audit_module.main()
    assert exit_code == 0
    report_path = tmp_path / "docs/audit/aud-1-audit-report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["oracle_version"] == ORACLE_VERSION
    assert [case["case_id"] for case in report["cases"]] == ["M01"]  # unclosed skipped
    assert report["summary"]["cases_closed_audited"] == 1
    assert report["summary"]["hard_gate_failures"] == []
    assert report["summary"]["cases_with_failed_oracles"] == []
    assert report["summary"]["observer_gap_checks"] == ["within_30s_completion_observation"]
    out = capsys.readouterr().out
    assert "M01: hard_gate=PASS" in out
    assert "audit_report" in out


def test_cli_missing_ledger_exits_with_a_clean_message(tmp_path, monkeypatch, capsys):
    """A pre-first-case invocation is expected operator behavior, not a
    traceback: the CLI must say the ledger does not exist yet."""
    batch_path = tmp_path / "batch.json"
    batch_path.write_text(json.dumps(
        {"batch_id": "AUD-2", "isolation_root": "tmp/run", "cases": []}), encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["audit_batch", "--root", str(tmp_path),
                                     "--batch", str(batch_path)])
    with pytest.raises(SystemExit, match=r"batch ledger not found at .*no case has closed yet"):
        audit_module.main()
    assert capsys.readouterr().out == ""
