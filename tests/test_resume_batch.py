# tests/test_resume_batch.py
import json
from pathlib import Path

import pytest

from scripts.acceptance import real_provider_browser_batch as batch_module
from scripts.acceptance.real_provider_browser_batch import preflight
from scripts.acceptance.real_provider_browser_server import _canonical_json_hash
from scripts.acceptance.resume_batch import derive_resume_batch

_MATRIX_IDS = ("M01", "M02", "M03", "M04", "M05", "M06")

_STRICT_POLICY = {
    "temperature": 0, "timeout_seconds": 120, "initial_max_tokens": 8000,
    "auxiliary_initial_max_tokens": 300, "auxiliary_max_tokens": [300, 800],
    "silent_length_ladder": [8000], "num_retries": 0,
    "stream_sync_fallback": False, "model_fallback": False,
    "supplementary_run": False, "web_journeys": 1,
    "retry_policy": {
        "max_retry_attempts": 1,
        "backoff_seconds": 20,
        "retry_error_classes": ["rate_limited", "network_transient", "server_error"],
    },
}


def _write_minimal_batch(root: Path, tmp: Path):
    """构造 M01-M06 冻结矩阵批次：M01 正常关闭、M02 quota 作废、M03-M06 未跑。"""
    (root / "scripts/acceptance").mkdir(parents=True)
    # No trailing newline: preflight hashes the launcher with the
    # newline-normalized digest while this fixture hashes raw bytes.
    (root / "scripts/acceptance/x.py").write_text("# launcher", encoding="utf-8")
    (root / "tmp").mkdir()
    data_file = root / "tmp" / "d1.csv"
    data_file.write_bytes(b"matrix-data")
    data_item = {"id": "D1", "path": "tmp/d1.csv", "sha256": _file_hash(data_file)}
    source_digest = "sha256:" + "a" * 64
    case_defs = {}
    for case_id in _MATRIX_IDS:
        policy = json.loads(json.dumps(_STRICT_POLICY))
        policy["call_cap"] = 4
        policy["analysis_turns"] = 1
        case_defs[case_id] = {
            "schema_version": 1, "candidate_id": f"c_{case_id}", "matrix_case_id": case_id,
            "source_digest": source_digest, "model": "provider/model", "port": 7100,
            "data": [data_item], "prompt": f"p-{case_id}", "prompts": [f"p-{case_id}"],
            "provider_policy": policy,
            "oracle": {"required_tools": []},
            "writes": {
                "workspace_dir": f"tmp/orig/{case_id}/workspace",
                "sessions_dir": f"tmp/orig/{case_id}/sessions",
                "provider_receipt_path": f"tmp/orig/{case_id}/provider-calls.json",
                "report_path": f"docs/audit/orig-{case_id}-report.json",
                "process_control_dir": f"tmp/orig/{case_id}/process-control",
            },
        }
    case_paths = []
    for case_id in _MATRIX_IDS:
        path = root / "docs/audit" / f"orig-{case_id}-candidate.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(case_defs[case_id], ensure_ascii=False), encoding="utf-8")
        case_paths.append({"id": case_id, "path": str(path.relative_to(root)).replace("\\", "/"),
                           "sha256": _file_hash(path)})
    batch = {"schema_version": "real_provider_browser_batch.v1", "batch_id": "ORIG",
             "source_digest": source_digest, "model": "provider/model",
             "cases": case_paths, "call_cap": 24,
             "isolation_root": "tmp/orig", "report_path": "docs/audit/orig-report.json",
             "launcher_path": "scripts/acceptance/x.py", "launcher_sha256": _file_hash(root / "scripts/acceptance/x.py"),
             "supervisor_path": "scripts/acceptance/x.py", "supervisor_sha256": _file_hash(root / "scripts/acceptance/x.py"),
             "data_bundle_sha256": _canonical_json_hash([data_item]),
             "prompt_bundle_sha256": _canonical_json_hash(
                 {cid: [f"p-{cid}"] for cid in _MATRIX_IDS}),
             "oracle_bundle_sha256": _canonical_json_hash(
                 {cid: {"required_tools": []} for cid in _MATRIX_IDS})}
    batch_path = root / "docs/audit/orig-batch.json"
    batch_path.write_text(json.dumps(batch, ensure_ascii=False), encoding="utf-8")
    ledger = {"schema_version": 2, "batch_sha256": _file_hash(batch_path),
              "cases": [
                  {"id": "M01", "status": "closed",
                   "terminal_failure": {"code": "acceptance_server_closed"}, "real_calls": 2},
                  {"id": "M02", "status": "closed",
                   "terminal_failure": {"code": "provider_request_failed", "error_class": "quota_exhausted"},
                   "real_calls": 1},
              ], "real_calls": 3, "calls_started_observed": 3, "blocked_attempts": 0}
    ledger_path = root / "tmp/orig/provider-batch.json"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(json.dumps(ledger), encoding="utf-8")
    return batch_path, ledger_path, source_digest


def _file_hash(path: Path) -> str:
    import hashlib
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _derive(root, batch_path, ledger_path, source_digest,
            new_batch_id="RESUME-1", new_isolation_root="tmp/resume-1", monkeypatch=None):
    if monkeypatch is not None:
        monkeypatch.setattr("scripts.acceptance.resume_batch.release_source_digest",
                            lambda r: source_digest)
    return derive_resume_batch(root, batch_path, ledger_path,
                               new_batch_id=new_batch_id, new_isolation_root=new_isolation_root)


def test_derive_resume_batch_voids_quota_case_and_keeps_completed(tmp_path, monkeypatch):
    root = tmp_path
    batch_path, ledger_path, source_digest = _write_minimal_batch(root, tmp_path)
    proposal = _derive(root, batch_path, ledger_path, source_digest, monkeypatch=monkeypatch)
    assert proposal["resumes_from"]["completed_cases"] == ["M01"]
    assert proposal["resumes_from"]["voided_cases"] == ["M02"]
    new_batch = json.loads(Path(proposal["batch_path"]).read_text(encoding="utf-8"))
    assert [c["id"] for c in new_batch["cases"]] == ["M02", "M03", "M04", "M05", "M06"]
    assert new_batch["resumes_from"]["batch_id"] == "ORIG"
    assert new_batch["call_cap"] == 20  # 仅 void+未跑场景的 caps
    for entry in new_batch["cases"]:
        candidate = json.loads((root / entry["path"]).read_text(encoding="utf-8"))
        assert "tmp/resume-1/" in candidate["writes"]["workspace_dir"]
        assert candidate["source_digest"] == source_digest


def test_derived_resume_batch_passes_zero_call_preflight(tmp_path, monkeypatch):
    root = tmp_path
    batch_path, ledger_path, source_digest = _write_minimal_batch(root, tmp_path)
    monkeypatch.setattr("scripts.acceptance.resume_batch.release_source_digest", lambda r: source_digest)
    monkeypatch.setattr(batch_module, "release_source_digest", lambda r: source_digest)
    proposal = derive_resume_batch(root, batch_path, ledger_path,
                                   new_batch_id="RESUME-1", new_isolation_root="tmp/resume-1")
    launcher_path = root / "scripts/acceptance/x.py"
    environment = {"AUTHORIZED_BATCH_SHA256": proposal["batch_sha256"]}
    derived, cases, checks = preflight(root, Path(proposal["batch_path"]), launcher_path,
                                       environment=environment)
    assert derived["batch_id"] == "RESUME-1"
    assert [c["matrix_case_id"] for c in cases] == ["M02", "M03", "M04", "M05", "M06"]
    original = json.loads(batch_path.read_text(encoding="utf-8"))
    # Bundle identities are recomputed over the re-emitted subset, not copied
    # from the original whole-matrix values.
    assert checks["PROMPT_BUNDLE_SHA256"] != original["prompt_bundle_sha256"]
    assert checks["DATA_BUNDLE_SHA256"] == original["data_bundle_sha256"]  # same shared data
    assert derived["prompt_bundle_sha256"] == checks["PROMPT_BUNDLE_SHA256"]
    assert derived["oracle_bundle_sha256"] == checks["ORACLE_BUNDLE_SHA256"]


def test_derive_resume_rejects_changed_source(tmp_path, monkeypatch):
    root = tmp_path
    batch_path, ledger_path, _ = _write_minimal_batch(root, tmp_path)
    monkeypatch.setattr("scripts.acceptance.resume_batch.release_source_digest",
                        lambda r: "sha256:" + "b" * 64)
    with pytest.raises(ValueError, match="source digest"):
        derive_resume_batch(root, batch_path, ledger_path,
                            new_batch_id="RESUME-1", new_isolation_root="tmp/resume-1")


def test_derive_resume_rejects_open_case(tmp_path, monkeypatch):
    root = tmp_path
    batch_path, ledger_path, source_digest = _write_minimal_batch(root, tmp_path)
    ledger = json.loads(ledger_path.read_text())
    ledger["cases"].append({"id": "M03", "status": "started"})
    ledger_path.write_text(json.dumps(ledger))
    monkeypatch.setattr("scripts.acceptance.resume_batch.release_source_digest", lambda r: source_digest)
    with pytest.raises(ValueError, match="closed"):
        derive_resume_batch(root, batch_path, ledger_path,
                            new_batch_id="RESUME-1", new_isolation_root="tmp/resume-1")


def test_derive_resume_rejects_reused_batch_id(tmp_path, monkeypatch):
    root = tmp_path
    batch_path, ledger_path, source_digest = _write_minimal_batch(root, tmp_path)
    monkeypatch.setattr("scripts.acceptance.resume_batch.release_source_digest", lambda r: source_digest)
    with pytest.raises(ValueError, match="batch id"):
        derive_resume_batch(root, batch_path, ledger_path,
                            new_batch_id="orig", new_isolation_root="tmp/resume-1")
    # The original batch manifest must not have been overwritten.
    assert json.loads(batch_path.read_text(encoding="utf-8"))["batch_id"] == "ORIG"


def test_derive_resume_rejects_reused_isolation_root(tmp_path, monkeypatch):
    root = tmp_path
    batch_path, ledger_path, source_digest = _write_minimal_batch(root, tmp_path)
    monkeypatch.setattr("scripts.acceptance.resume_batch.release_source_digest", lambda r: source_digest)
    with pytest.raises(ValueError, match="isolation root"):
        derive_resume_batch(root, batch_path, ledger_path,
                            new_batch_id="RESUME-1", new_isolation_root="tmp/orig")


def test_plain_batch_still_requires_all_six_cases_in_preflight(tmp_path, monkeypatch):
    root = tmp_path
    batch_path, ledger_path, source_digest = _write_minimal_batch(root, tmp_path)
    # A plain (non-resume) batch missing one case must still be rejected.
    batch_manifest = json.loads(batch_path.read_text(encoding="utf-8"))
    batch_manifest["cases"] = batch_manifest["cases"][:-1]
    batch_path.write_text(json.dumps(batch_manifest, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(batch_module, "release_source_digest", lambda r: source_digest)
    environment = {"AUTHORIZED_BATCH_SHA256": _file_hash(batch_path)}
    with pytest.raises(ValueError, match="M01-M06"):
        preflight(root, batch_path, root / "scripts/acceptance/x.py", environment)
