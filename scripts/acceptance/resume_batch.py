# scripts/acceptance/resume_batch.py
"""Mechanically derive a resume batch after a global-fatal batch stop.

A resume batch reuses the original frozen source digest, data, prompts,
oracles and per-case caps.  Cases closed by a global-fatal provider
error are voided (their receipts stay archived) and re-attempted once;
completed cases are not re-run.  Any source change forces a brand-new
batch instead.
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts.acceptance.real_provider_browser_batch import _GLOBAL_FATAL_CLASSES
from scripts.acceptance.real_provider_browser_server import (
    _canonical_json_hash, _normalized_file_hash,
)
from scripts.acceptance.release_source import release_source_digest


def _inside(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if path == root or not path.is_relative_to(root):
        raise ValueError("frozen path escapes repository")
    return path


def derive_resume_batch(root: Path, batch_path: Path, ledger_path: Path, *,
                        new_batch_id: str, new_isolation_root: str) -> dict:
    root = root.resolve()
    batch = json.loads(Path(batch_path).read_text(encoding="utf-8"))
    ledger = json.loads(Path(ledger_path).read_text(encoding="utf-8"))
    if release_source_digest(root) != batch["source_digest"]:
        raise ValueError("source digest changed; a resume batch is not allowed")
    closed = {}
    for record in ledger["cases"]:
        if record.get("status") != "closed":
            raise ValueError("cannot resume a batch with an unclosed case: " + str(record.get("id")))
        closed[record["id"]] = record
    original_hash = _normalized_file_hash(Path(batch_path))
    if ledger.get("batch_sha256") != original_hash:
        raise ValueError("ledger does not match the original batch receipt")

    completed, voided, remaining = [], [], []
    for entry in batch["cases"]:
        case_id = entry["id"]
        record = closed.get(case_id)
        if record is None:
            remaining.append(entry)
            continue
        error_class = (record.get("terminal_failure") or {}).get("error_class")
        (voided if error_class in _GLOBAL_FATAL_CLASSES else completed).append(entry)

    new_entries, new_caps = [], 0
    for entry in voided + remaining:
        case = json.loads(_inside(root, entry["path"]).read_text(encoding="utf-8"))
        suffix = case["matrix_case_id"][1:]
        case["writes"] = {
            key: value.replace(f"tmp/{batch['isolation_root'].split('/', 1)[-1]}/",
                               f"{new_isolation_root}/")
            for key, value in case["writes"].items()
        }
        case["writes"]["report_path"] = \
            f"docs/audit/{new_batch_id.lower()}-{case['matrix_case_id'].lower()}-report.json"
        case["candidate_id"] = case["candidate_id"] + "_resume"
        new_name = f"{new_batch_id.lower()}-{case['matrix_case_id'].lower()}-candidate.json"
        new_path = root / "docs/audit" / new_name
        new_path.write_text(json.dumps(case, ensure_ascii=False, indent=2), encoding="utf-8")
        new_entries.append({"id": case["matrix_case_id"],
                            "path": str(new_path.relative_to(root)).replace("\\", "/"),
                            "sha256": _normalized_file_hash(new_path)})
        new_caps += int(case["provider_policy"]["call_cap"])

    new_batch = dict(batch)
    new_batch.update({
        "batch_id": new_batch_id,
        "cases": new_entries,
        "call_cap": new_caps,
        "isolation_root": new_isolation_root,
        "resumes_from": {"batch_id": batch["batch_id"], "batch_sha256": original_hash,
                         "completed_cases": [e["id"] for e in completed],
                         "voided_cases": [e["id"] for e in voided]},
    })
    new_batch_path = root / "docs/audit" / f"{new_batch_id.lower()}-batch.json"
    new_batch_path.write_text(json.dumps(new_batch, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "batch_id": new_batch_id,
        "batch_sha256": _normalized_file_hash(new_batch_path),
        "batch_path": str(new_batch_path),
        "case_paths": [e["path"] for e in new_entries],
        "resumes_from": new_batch["resumes_from"],
        "authorization_required": "AUTHORIZED_BATCH_SHA256",
    }
