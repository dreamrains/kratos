# tests/test_run_batch.py
from __future__ import annotations

import json
import sys

from scripts.acceptance import real_provider_browser_batch as browser_batch
from scripts.acceptance import run_batch
from scripts.acceptance.run_batch import run_probe


class _ProbeCompletion:
    def __init__(self, responses):
        self._responses = list(responses)

    def __call__(self, **kwargs):
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _probe_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_AGENT_API_BASE", "https://example.invalid/v1")
    monkeypatch.setenv("DATA_AGENT_API_KEY", "sk-test")
    return tmp_path / "probe-receipt.json"


def test_probe_reports_quota_as_global_fatal(tmp_path, monkeypatch):
    receipt = _probe_env(monkeypatch, tmp_path)

    class _Quota(Exception):
        status_code = 400

        def __str__(self):
            return "Error code: 400 - Insufficient Balance"

    result = run_probe(tmp_path, model="provider/model", api_base="https://example.invalid/v1",
                       api_key="sk-test", receipt_path=receipt,
                       completion=_ProbeCompletion([_Quota()]), backoff_seconds=0.0)
    assert result["ok"] is False
    assert result["error_class"] == "quota_exhausted"
    assert result["global_fatal"] is True
    saved = json.loads(receipt.read_text(encoding="utf-8"))
    assert saved["calls"][0]["error_class"] == "quota_exhausted"


def test_probe_success_returns_ok(tmp_path, monkeypatch):
    receipt = _probe_env(monkeypatch, tmp_path)
    result = run_probe(tmp_path, model="provider/model", api_base="https://example.invalid/v1",
                       api_key="sk-test", receipt_path=receipt,
                       completion=_ProbeCompletion([object()]), backoff_seconds=0.0)
    assert result["ok"] is True and result["error_class"] is None
    saved = json.loads(receipt.read_text(encoding="utf-8"))
    assert saved["candidate_id"] == "batch_probe"
    assert saved["call_cap"] == 1
    assert saved["calls"][0]["status"] == "completed"


def _frozen_batch(tmp_path, monkeypatch):
    """Task 5 fixture pattern: one fully verifiable six-case batch under tmp_path."""
    from scripts.acceptance.real_provider_browser_server import (
        _canonical_json_hash as canonical, _normalized_file_hash as digest,
    )
    monkeypatch.setattr(browser_batch, "release_source_digest", lambda _: "source")
    data = tmp_path / "data.bin"
    data.write_bytes(b"data")
    data_item = {"id": "data", "path": "data.bin", "sha256": digest(data)}
    launcher = tmp_path / "launcher.py"
    launcher.write_text("# launcher", encoding="utf-8")
    supervisor = tmp_path / "supervisor.py"
    supervisor.write_text("# supervisor", encoding="utf-8")
    retry_policy = {
        "max_retry_attempts": 1,
        "backoff_seconds": 20,
        "retry_error_classes": ["rate_limited", "network_transient", "server_error"],
    }
    cases = []
    for i in range(1, 7):
        cid = f"M{i:02d}"
        cases.append({
            "matrix_case_id": cid, "source_digest": "source", "model": "model",
            "data": [data_item], "prompt": "analyze", "prompts": ["analyze"],
            "oracle": {"test": True},
            "provider_policy": {
                "temperature": 0, "timeout_seconds": 120, "initial_max_tokens": 8000,
                "auxiliary_initial_max_tokens": 300, "auxiliary_max_tokens": [300, 800],
                "silent_length_ladder": [8000], "num_retries": 0,
                "retry_policy": json.loads(json.dumps(retry_policy)),
                "stream_sync_fallback": False, "model_fallback": False,
                "supplementary_run": False, "web_journeys": 1, "analysis_turns": 1,
                "call_cap": 2,
            },
            "writes": {"workspace_dir": f"tmp/run/{cid}/workspace",
                       "sessions_dir": f"tmp/run/{cid}/sessions",
                       "process_control_dir": f"tmp/run/{cid}/process-control",
                       "provider_receipt_path": f"tmp/run/{cid}/calls.json",
                       "report_path": f"docs/audit/{cid}.json"},
        })
    entries = []
    for case in cases:
        path = tmp_path / f"{case['matrix_case_id']}.json"
        path.write_text(json.dumps(case), encoding="utf-8")
        entries.append({"id": case["matrix_case_id"], "path": path.name, "sha256": digest(path)})
    frozen = {
        "schema_version": "real_provider_browser_batch.v1", "batch_id": "B001",
        "source_digest": "source", "model": "model",
        "call_cap": 12, "isolation_root": "tmp/run", "report_path": "docs/audit/batch.json",
        "supervisor_path": supervisor.name, "supervisor_sha256": digest(supervisor),
        "launcher_sha256": digest(launcher), "data_bundle_sha256": canonical([data_item]),
        "prompt_bundle_sha256": canonical({c["matrix_case_id"]: c["prompts"] for c in cases}),
        "oracle_bundle_sha256": canonical({c["matrix_case_id"]: c["oracle"] for c in cases}),
        "cases": entries,
    }
    batch_path = tmp_path / "batch-candidate.json"
    batch_path.write_text(json.dumps(frozen), encoding="utf-8")
    return batch_path, launcher, digest(batch_path)


def test_main_without_authorized_prints_digest_and_launches_nothing(tmp_path, monkeypatch, capsys):
    batch_path, launcher, batch_digest = _frozen_batch(tmp_path, monkeypatch)
    monkeypatch.setenv("AUTHORIZED_BATCH_SHA256", batch_digest)
    launched = []
    monkeypatch.setattr(run_batch, "run_case", lambda *args, **kwargs: launched.append((args, kwargs)))
    monkeypatch.setattr(sys, "argv", [
        "run_batch", "--root", str(tmp_path), "--batch", str(batch_path), "--launcher", str(launcher),
    ])
    run_batch.main()
    summary = json.loads(capsys.readouterr().out)
    assert summary["batch_id"] == "B001"
    assert summary["authorize_with"] == "AUTHORIZED_BATCH_SHA256=" + batch_digest
    assert summary["cases"] == [f"M{i:02d}" for i in range(1, 7)]
    assert launched == []
