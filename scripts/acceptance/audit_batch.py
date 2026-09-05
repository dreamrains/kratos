# scripts/acceptance/audit_batch.py
"""Deterministic, read-only, offline audit of a closed matrix batch (spec S8).

Replaces per-batch tmp/ audit scripts: every check consumes durable on-disk
evidence only (frozen batch manifest, batch ledger, per-case provider
receipts, session conversations, process-control proofs, export files) and
never contacts the Provider or the network.  Checks this runner cannot prove
offline are reported as observer gaps, not oracle failures.  The only write
is the single JSON report under docs/audit plus stdout lines.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.acceptance.matrix_oracles import (
    OBSERVER_GAP_CHECKS, ORACLE_VERSION, zero_semantics_violations,
)
from scripts.acceptance.real_provider_browser_batch import _inside, _locally_terminal
from scripts.acceptance.real_provider_browser_server import _normalized_file_hash

REPORT_SCHEMA = "matrix_batch_audit.v1"

# Integer-count export expectations the oracle may declare.  Anything else
# (boolean/string export semantics) is not a presence check and is skipped.
_EXPORT_SPECS = (("html_exports", "*.html"), ("md_exports", "*.md"),
                 ("markdown_exports", "*.md"))


def _messages(conversation: Path) -> list[dict]:
    """Read rotated conversation.json arrays or active conversation.jsonl."""
    text = conversation.read_text(encoding="utf-8")
    if text.lstrip().startswith("["):
        payload = json.loads(text)
        return payload if isinstance(payload, list) else []
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _case_messages(sessions_dir: Path) -> list[dict]:
    messages: list[dict] = []
    if not sessions_dir.is_dir():
        return messages
    for conversation in sorted(sessions_dir.glob("*/conversation.json*")):
        try:
            messages.extend(_messages(conversation))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            continue
    return messages


def _tool_names(messages: list[dict]) -> set[str]:
    """Tool names recovered from assistant tool_calls (tool rows carry none)."""
    names: set[str] = set()
    for message in messages:
        if message.get("role") != "assistant":
            continue
        for call in message.get("tool_calls") or []:
            name = (call.get("function") or {}).get("name")
            if name:
                names.add(name)
    return names


def _published_assistant_text(messages: list[dict]) -> str:
    """Concatenate published assistant replies, skipping rejected rewrites."""
    parts: list[str] = []
    for message in messages:
        if message.get("role") != "assistant":
            continue
        if message.get("publication_rejected") is True:
            continue  # internal rewrite drafts are not published claims
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            parts.append(content.strip())
    return "\n".join(parts)


def _containment_failures(receipt: dict, *, ledger_cap) -> list[str]:
    """Hard gate: receipt containment only, mirroring BatchLedger.finish."""
    failures: list[str] = []
    calls = receipt.get("calls")
    if not isinstance(calls, list):
        return ["receipt_calls_missing"]
    if any(not _locally_terminal(call, receipt) for call in calls):
        failures.append("non_terminal_calls")
    if [call.get("ordinal") for call in calls] != list(range(1, len(calls) + 1)):
        failures.append("ordinal_sequence")
    cap = receipt.get("call_cap")
    if not isinstance(cap, int) or isinstance(cap, bool) or cap < 1:
        failures.append("receipt_cap_missing")
    else:
        if len(calls) > cap:
            failures.append("cap_exceeded")
        if isinstance(ledger_cap, int) and not isinstance(ledger_cap, bool) and cap != ledger_cap:
            failures.append("cap_mismatch_vs_ledger")
    blocked = receipt.get("blocked_attempts")
    if not isinstance(blocked, int) or isinstance(blocked, bool):
        failures.append("blocked_attempts_missing")
    return failures


def audit_case(root: Path, case: dict, record: dict) -> dict:
    """Audit one closed case against its frozen candidate. Read-only."""
    writes = case["writes"]
    oracle = case.get("oracle") or {}
    failed_oracles: list[dict] = []
    # These checks are provable only by a live observer (spec S5), never by
    # offline evidence, so they can never appear as failed oracles.
    observer_gaps: set[str] = set(OBSERVER_GAP_CHECKS)
    checks: dict = {}

    receipt_path = _inside(root, writes["provider_receipt_path"])
    if receipt_path.is_file():
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            containment = _containment_failures(receipt, ledger_cap=record.get("call_cap"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            receipt, containment = None, ["receipt_unreadable"]
        pinned = record.get("receipt_sha256")
        if receipt is not None and pinned and pinned != _normalized_file_hash(receipt_path):
            containment.append("receipt_hash_mismatch_vs_ledger")
    else:
        containment = ["receipt_missing"]
    checks["containment"] = {"failures": containment}

    sessions_dir = _inside(root, writes["sessions_dir"])
    messages = _case_messages(sessions_dir)
    if not messages:
        observer_gaps.add("conversation_evidence_missing")

    required = oracle.get("required_tools") or []
    if isinstance(required, list) and required:
        if not messages:
            checks["required_tools"] = {"status": "observer_gap", "required": required}
        else:
            recovered = _tool_names(messages)
            missing = [tool for tool in required if tool not in recovered]
            checks["required_tools"] = {"status": "pass" if not missing else "fail",
                                        "required": required,
                                        "recovered": sorted(recovered), "missing": missing}
            if missing:
                failed_oracles.append({"check": "required_tools", "missing": missing})
    else:
        checks["required_tools"] = {"status": "skipped"}

    if messages:
        text = _published_assistant_text(messages)
        if not text:
            observer_gaps.add("published_replies_missing")
            checks["zero_semantics"] = {"status": "observer_gap"}
        else:
            violations = zero_semantics_violations(text)
            checks["zero_semantics"] = {"status": "fail" if violations else "pass",
                                        "violations": violations}
            for violation in violations:
                failed_oracles.append({"check": "zero_semantics", "violation": violation})
    else:
        checks["zero_semantics"] = {"status": "observer_gap"}

    exit_proof_path = _inside(root, writes["process_control_dir"]) / "process-exit.json"
    if exit_proof_path.is_file():
        try:
            proof = json.loads(exit_proof_path.read_text(encoding="utf-8"))
            graceful = proof.get("graceful_exit") is True
        except (json.JSONDecodeError, UnicodeDecodeError):
            graceful = False
            proof = {}
        checks["process_exit"] = {"status": "pass" if graceful else "fail",
                                  "exit_code": proof.get("exit_code"),
                                  "graceful_exit": graceful}
        if not graceful:
            failed_oracles.append({"check": "process_exit",
                                   "exit_code": proof.get("exit_code")})
    else:
        observer_gaps.add("process_exit_proof_missing")
        checks["process_exit"] = {"status": "observer_gap"}

    export_specs = {key: (oracle[key], pattern) for key, pattern in _EXPORT_SPECS
                    if isinstance(oracle.get(key), int) and not isinstance(oracle.get(key), bool)}
    if not export_specs:
        checks["exports"] = {"status": "skipped"}
    elif not sessions_dir.is_dir():
        observer_gaps.add("exports_evidence_missing")
        checks["exports"] = {"status": "observer_gap"}
    else:
        detail, failed = {}, False
        for key, (expected, pattern) in sorted(export_specs.items()):
            found = sum(1 for path in sessions_dir.rglob(pattern) if path.is_file())
            detail[key] = {"expected": expected, "found": found}
            failed = failed or found < expected
        checks["exports"] = {"status": "fail" if failed else "pass", **detail}
        if failed:
            failed_oracles.append({"check": "exports", **detail})

    return {"case_id": case["matrix_case_id"],
            "hard_gate": {"passed": not containment, "failures": containment},
            "failed_oracles": failed_oracles,
            "observer_gaps": sorted(observer_gaps),
            "checks": checks}


def audit_batch(root: Path, batch_path: Path) -> dict:
    """Audit every closed case of a batch; write docs/audit/<id>-audit-report.json."""
    root = Path(root).resolve()
    batch = json.loads(Path(batch_path).read_text(encoding="utf-8"))
    isolation = _inside(root, batch["isolation_root"])
    ledger = json.loads((isolation / "provider-batch.json").read_text(encoding="utf-8"))
    entries = {entry["id"]: entry for entry in batch["cases"]}
    results = []
    for record in ledger.get("cases", []):
        if record.get("status") != "closed":
            continue  # unclosed cases are the ledger's own accounting problem
        entry = entries.get(record.get("id"))
        case = (json.loads(_inside(root, entry["path"]).read_text(encoding="utf-8"))
                if entry is not None else None)
        if case is None:
            results.append({"case_id": record.get("id"),
                            "hard_gate": {"passed": False,
                                          "failures": ["case_missing_from_frozen_batch"]},
                            "failed_oracles": [{"check": "case_missing_from_frozen_batch"}],
                            "observer_gaps": sorted(OBSERVER_GAP_CHECKS),
                            "checks": {}})
            continue
        results.append(audit_case(root, case, record))
    summary = {
        "cases_closed_audited": len(results),
        "hard_gate_failures": [r["case_id"] for r in results if not r["hard_gate"]["passed"]],
        "cases_with_failed_oracles": [r["case_id"] for r in results if r["failed_oracles"]],
        "observer_gap_checks": sorted(OBSERVER_GAP_CHECKS),
    }
    report = {"schema_version": REPORT_SCHEMA,
              "batch_id": batch.get("batch_id"),
              "batch_sha256": _normalized_file_hash(Path(batch_path)),
              "oracle_version": ORACLE_VERSION,
              "cases": results,
              "summary": summary}
    report_path = root / "docs/audit" / f"{str(batch.get('batch_id', 'batch')).lower()}-audit-report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return {**report, "report_path": str(report_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline audit of a closed matrix batch")
    parser.add_argument("--root", default=".")
    parser.add_argument("--batch", required=True)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    batch = json.loads(Path(args.batch).read_text(encoding="utf-8"))
    ledger_path = _inside(root, batch["isolation_root"]) / "provider-batch.json"
    if not ledger_path.is_file():
        # Expected operator question before any case has closed, not a crash.
        raise SystemExit(f"batch ledger not found at {ledger_path}; no case has closed yet")
    report = audit_batch(root, Path(args.batch))
    for case in report["cases"]:
        gate = "PASS" if case["hard_gate"]["passed"] else "FAIL"
        print(f"{case['case_id']}: hard_gate={gate} "
              f"failed_oracles={len(case['failed_oracles'])} "
              f"observer_gaps={len(case['observer_gaps'])}")
    print(json.dumps({"audit_report": report["report_path"], "summary": report["summary"]},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
