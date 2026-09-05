from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from data_agent import config as config_module
from data_agent import lifecycle as lifecycle_module
from data_agent.llm import client as llm_client
from data_agent.web import app as web_app_module
from scripts.acceptance import real_provider_browser_server as server
from scripts.acceptance.strict_provider_guard import ProviderJourneyHalted, ProviderPolicyViolation


def _prepare(tmp_path, monkeypatch):
    data_path = tmp_path / "data.bin"
    data_path.write_bytes(b"frozen-data")
    launcher_path = tmp_path / "launcher.py"
    launcher_path.write_text("# frozen launcher\n", encoding="utf-8")
    candidate_path = tmp_path / "candidate.json"
    candidate = {
        "schema_version": 1,
        "candidate_id": "browser-test",
        "source_digest": "sha256:source",
        "model": "provider/model",
        "data": [
            {
                "id": "data",
                "path": "data.bin",
                "sha256": server._sha256_bytes(data_path.read_bytes()),
            }
        ],
        "prompt": "frozen prompt",
        "oracle": {"answer": 1},
        "provider_policy": {
            "call_cap": 3,
            "temperature": 0.0,
            "timeout_seconds": 120,
            "initial_max_tokens": 8000,
            "auxiliary_max_tokens": [300, 800],
            "silent_length_ladder": [8000],
        },
        "writes": {
            "workspace_dir": "workspace",
            "sessions_dir": "sessions",
            "provider_receipt_path": "provider-calls.json",
            "report_path": "report.json",
        },
    }
    candidate_path.write_text(json.dumps(candidate, ensure_ascii=False, indent=2), encoding="utf-8")
    config = SimpleNamespace(
        model_id="provider/model",
        max_tokens=8000,
        quality_judge_model="provider/model",
        mcp_enabled=False,
        api_base="https://provider.invalid/v1",
        api_key="secret-not-printed",
        workspace_dir=tmp_path / "workspace",
        sessions_dir=tmp_path / "sessions",
    )
    monkeypatch.setattr(config_module, "get_config", lambda: config)
    monkeypatch.setattr(server, "release_source_digest", lambda root: "sha256:source")
    monkeypatch.setenv("AUTHORIZED_SOURCE_DIGEST", "sha256:source")
    monkeypatch.setenv("AUTHORIZED_CANDIDATE_SHA256", server._normalized_file_hash(candidate_path))
    monkeypatch.setenv("AUTHORIZED_LAUNCHER_SHA256", server._normalized_file_hash(launcher_path))
    monkeypatch.setenv("AUTHORIZED_PROMPT_SHA256", server._sha256_bytes(candidate["prompt"].encode("utf-8")))
    monkeypatch.setenv("AUTHORIZED_ORACLE_SHA256", server._canonical_json_hash(candidate["oracle"]))
    return candidate_path, launcher_path


def test_zero_call_preflight_checks_frozen_inputs_without_creating_output_paths(tmp_path, monkeypatch, capsys):
    candidate_path, launcher_path = _prepare(tmp_path, monkeypatch)
    monkeypatch.setenv("DATA_AGENT_PREFLIGHT_ONLY", "1")

    server.run_authorized_browser_server(
        root=tmp_path,
        candidate_path=candidate_path,
        launcher_path=launcher_path,
    )

    output = json.loads(capsys.readouterr().out)
    assert output["ready"] is True
    assert output["call_cap"] == 3
    assert output["api_base_present"] is True
    assert output["api_key_present"] is True
    assert not (tmp_path / "workspace").exists()
    assert not (tmp_path / "sessions").exists()
    assert not (tmp_path / "provider-calls.json").exists()
    assert not (tmp_path / "report.json").exists()


def test_real_run_requires_the_frozen_network_execution_ack_before_runtime_start(tmp_path, monkeypatch):
    candidate_path, launcher_path = _prepare(tmp_path, monkeypatch)
    monkeypatch.delenv("DATA_AGENT_PREFLIGHT_ONLY", raising=False)
    monkeypatch.delenv("DATA_AGENT_REAL_PROVIDER_NETWORK_ENABLED", raising=False)

    with pytest.raises(ProviderPolicyViolation, match="network_enabled_execution_not_acknowledged"):
        server.run_authorized_browser_server(
            root=tmp_path,
            candidate_path=candidate_path,
            launcher_path=launcher_path,
        )

    assert not (tmp_path / "provider-calls.json").exists()


def test_zero_call_preflight_rejects_historical_hidden_output_escalation(tmp_path, monkeypatch):
    candidate_path, launcher_path = _prepare(tmp_path, monkeypatch)
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    candidate["provider_policy"]["silent_length_ladder"] = [8000, 32000, 128000]
    candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
    monkeypatch.setenv("AUTHORIZED_CANDIDATE_SHA256", server._normalized_file_hash(candidate_path))
    monkeypatch.setenv("DATA_AGENT_PREFLIGHT_ONLY", "1")
    with pytest.raises(SystemExit, match="output token escalation"):
        server.run_authorized_browser_server(root=tmp_path, candidate_path=candidate_path, launcher_path=launcher_path)
    assert not (tmp_path / "provider-calls.json").exists()
    assert not (tmp_path / "workspace").exists()


def test_server_bootstrap_shares_one_failure_latch_across_all_product_call_paths(tmp_path, monkeypatch):
    candidate_path, launcher_path = _prepare(tmp_path, monkeypatch)
    monkeypatch.delenv("DATA_AGENT_PREFLIGHT_ONLY", raising=False)
    monkeypatch.setenv("DATA_AGENT_REAL_PROVIDER_NETWORK_ENABLED", "1")
    underlying_calls = []
    lifecycle_events = []

    def failed_completion(**kwargs):
        underlying_calls.append(kwargs)
        raise RuntimeError("provider transport failed")

    class FakeLifecycle:
        def initialize(self):
            lifecycle_events.append("initialize")

        def shutdown(self):
            lifecycle_events.append("shutdown")

    class FakeApp:
        def __init__(self):
            self.config = {}

        def run(self, **kwargs):
            from scripts.acceptance.bounded_auxiliary_client import OneShotAuxiliaryClient

            manager = self.config["agent_manager"]
            auxiliary = manager._auxiliary_client_factory()
            assert isinstance(auxiliary, OneShotAuxiliaryClient)
            assert auxiliary.max_tokens == 300
            with pytest.raises(RuntimeError, match="provider transport failed"):
                auxiliary.chat([])
            with pytest.raises(ProviderJourneyHalted, match="provider_request_failed"):
                manager._client_factory().chat_once([])
            with pytest.raises(ProviderJourneyHalted, match="provider_request_failed"):
                llm_client.LLMClient(model_id="provider/model", max_tokens=8000).chat_once([])

    monkeypatch.setattr(llm_client, "completion", failed_completion)
    monkeypatch.setattr(lifecycle_module, "AgentLifecycle", FakeLifecycle)
    monkeypatch.setattr(web_app_module, "create_app", FakeApp)

    server.run_authorized_browser_server(
        root=tmp_path,
        candidate_path=candidate_path,
        launcher_path=launcher_path,
    )

    assert len(underlying_calls) == 1
    assert underlying_calls[0]["num_retries"] == 0
    assert lifecycle_events == ["initialize", "shutdown"]
    assert llm_client.completion is failed_completion
    receipt = json.loads((tmp_path / "provider-calls.json").read_text(encoding="utf-8"))
    assert len(receipt["calls"]) == 1
    assert receipt["calls"][0]["status"] == "failed"
    assert receipt["blocked_attempts"] == 2
    assert receipt["terminal_failure"]["code"] == "provider_request_failed"


def test_batch_shutdown_keeps_default_transport_closed(tmp_path, monkeypatch):
    candidate_path, launcher_path = _prepare(tmp_path, monkeypatch)
    monkeypatch.delenv("DATA_AGENT_PREFLIGHT_ONLY", raising=False)
    monkeypatch.setenv("DATA_AGENT_REAL_PROVIDER_NETWORK_ENABLED", "1")
    calls = []
    monkeypatch.setattr(llm_client, "completion", lambda **kwargs: calls.append(kwargs))
    monkeypatch.setattr(lifecycle_module, "AgentLifecycle", lambda: SimpleNamespace(initialize=lambda: None, shutdown=lambda: None))
    monkeypatch.setattr(web_app_module, "create_app", lambda: SimpleNamespace(config={}, run=lambda **kwargs: None))
    server.run_authorized_browser_server(root=tmp_path, candidate_path=candidate_path,
        launcher_path=launcher_path, keep_guard_installed=True)
    with pytest.raises(ProviderJourneyHalted, match="acceptance_server_closed"):
        llm_client.LLMClient(model_id="provider/model", max_tokens=8000).chat_once([])
    assert calls == []
    receipt = json.loads((tmp_path / "provider-calls.json").read_text(encoding="utf8"))
    assert receipt["calls"] == [] and receipt["blocked_attempts"] == 1
