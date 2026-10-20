"""Regression checks for the real-Provider P08 launcher controls."""
from __future__ import annotations

import importlib.util
import csv
import json
from pathlib import Path
import pytest

from data_agent.llm.request_policy import ONE_SHOT


def _launcher_module():
    path = Path(__file__).parents[1] / "scripts" / "testing" / "run_p08_real_matrix.py"
    spec = importlib.util.spec_from_file_location("p08_real_matrix_launcher", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _http_driver_module():
    path = Path(__file__).parents[1] / "scripts" / "testing" / "run_p08_http_matrix.py"
    spec = importlib.util.spec_from_file_location("p08_http_matrix_driver", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_acceptance_launcher_forces_one_physical_attempt_for_every_client():
    launcher = _launcher_module()

    class FakeClient:
        def __init__(self, *args, request_policy=None, **kwargs):
            self.request_policy = request_policy

    class FakeClientModule:
        LLMClient = FakeClient

    launcher._install_one_shot_request_policy(FakeClientModule)

    assert FakeClient().request_policy is ONE_SHOT
    assert FakeClient(request_policy=object()).request_policy is ONE_SHOT


def test_provider_ledger_distinguishes_stream_return_from_exhaustion(tmp_path):
    launcher = _launcher_module()
    ledger = launcher.ProviderLedger(tmp_path / "provider-calls.jsonl", 2)
    called = []

    def completion(**kwargs):
        called.append(kwargs["model"])
        return iter(["delta", "terminal"])

    stream = ledger.wrap(completion)(model="frozen-model", stream=True)
    events = [json.loads(line)["event"] for line in ledger.path.read_text().splitlines()]
    assert events == ["started", "dispatched"]
    assert list(stream) == ["delta", "terminal"]
    stream.close()
    events = [json.loads(line)["event"] for line in ledger.path.read_text().splitlines()]
    assert events == ["started", "dispatched", "stream_exhausted"]
    assert called == ["frozen-model"]


def test_provider_ledger_marks_early_close_and_stream_error(tmp_path):
    launcher = _launcher_module()
    ledger = launcher.ProviderLedger(tmp_path / "provider-calls.jsonl", 2)
    early = ledger.wrap(lambda **_kwargs: iter(["delta", "more"]))(stream=True)
    assert next(early) == "delta"
    early.close()

    def broken(**_kwargs):
        def chunks():
            yield "delta"
            raise ValueError("transport interrupted")
        return chunks()

    with pytest.raises(RuntimeError, match="provider_failure_latched"):
        ledger.wrap(broken)(stream=True)
    assert ledger.count == 1
    (tmp_path / "broken").mkdir()
    ledger = launcher.ProviderLedger(tmp_path / "broken" / "provider-calls.jsonl", 2)
    stream = ledger.wrap(broken)(stream=True)
    with pytest.raises(ValueError, match="transport interrupted"):
        list(stream)
    stream.close()
    events = [json.loads(line)["event"] for line in ledger.path.read_text().splitlines()]
    assert events == ["started", "dispatched", "stream_failed"]
    with pytest.raises(RuntimeError, match="provider_failure_latched"):
        ledger.wrap(broken)(stream=True)
    assert ledger.count == 1


def test_provider_ledger_write_fault_fails_closed_before_transport(tmp_path, monkeypatch):
    launcher = _launcher_module()
    ledger = launcher.ProviderLedger(tmp_path / "provider-calls.jsonl", 2)
    calls = []

    def broken_write(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(ledger, "_write", broken_write)
    audited = ledger.wrap(lambda **_kwargs: calls.append("sent"))
    with pytest.raises(RuntimeError, match="ledger write failed"):
        audited()
    with pytest.raises(RuntimeError, match="ledger is unavailable"):
        audited()
    assert calls == []


def test_provider_ledger_nonstream_completion_is_accounted(tmp_path):
    launcher = _launcher_module()
    ledger = launcher.ProviderLedger(tmp_path / "provider-calls.jsonl", 1)
    assert ledger.wrap(lambda **_kwargs: {"ok": True})() == {"ok": True}
    events = [json.loads(line)["event"] for line in ledger.path.read_text().splitlines()]
    assert events == ["started", "dispatched", "completed"]
    with pytest.raises(RuntimeError, match="call cap reached"):
        ledger.wrap(lambda **_kwargs: None)()


def test_http_reconciliation_rejects_returned_or_closed_stream(monkeypatch):
    driver = _http_driver_module()
    events = [{"event": "started", "call_number": 1},
              {"event": "dispatched", "call_number": 1}]

    class Response:
        status_code = 200

        def raise_for_status(self):
            pass

        @property
        def text(self):
            return "\n".join(json.dumps(item) for item in events)

    monkeypatch.setattr(driver.requests, "get", lambda *_args, **_kwargs: Response())
    with pytest.raises(RuntimeError, match="missing, failed"):
        driver._ledger_state("http://127.0.0.1:1", 2)
    events.append({"event": "stream_closed", "call_number": 1})
    with pytest.raises(RuntimeError, match="missing, failed"):
        driver._ledger_state("http://127.0.0.1:1", 2)
    events[-1] = {"event": "stream_exhausted", "call_number": 1}
    assert driver._ledger_state("http://127.0.0.1:1", 2) == {
        "started": 1, "dispatched": 1, "completed": 1,
        "failed": 0, "denied": 0,
    }


def test_semantic_trial_mode_is_an_exact_frozen_provider_setting(monkeypatch):
    launcher = _launcher_module()
    monkeypatch.delenv("DATA_AGENT_SEMANTIC_AUDIT_TRIAL", raising=False)
    assert launcher._semantic_review_mode() == "bounded_once"
    monkeypatch.setenv("DATA_AGENT_SEMANTIC_AUDIT_TRIAL", "0")
    assert launcher._semantic_review_mode() == "bounded_once"
    monkeypatch.setenv("DATA_AGENT_SEMANTIC_AUDIT_TRIAL", "1")
    with pytest.raises(SystemExit, match="retired"):
        launcher._semantic_review_mode()
    monkeypatch.setenv("DATA_AGENT_SEMANTIC_AUDIT_TRIAL", "unexpected")
    with pytest.raises(SystemExit, match="semantic audit trial mode"):
        launcher._semantic_review_mode()


def test_real_provider_freeze_rejects_uncommitted_source(monkeypatch, tmp_path):
    launcher = _launcher_module()

    class Result:
        stdout = " M src/data_agent/agent/loop.py\n"

    monkeypatch.setattr(launcher.subprocess, "run", lambda *_args, **_kwargs: Result())
    with pytest.raises(SystemExit, match="clean committed source tree"):
        launcher._require_clean_source(tmp_path)
    Result.stdout = ""
    launcher._require_clean_source(tmp_path)


def test_preflight_contract_freezes_complete_prompts_oracles_and_http_protocol():
    launcher = _launcher_module()
    root = Path(__file__).parents[1]

    contract = launcher._frozen_matrix_contract(root, 5215)

    assert contract["matrix"] == ["M01", "M02", "M03", "M04", "M05", "M06"]
    assert contract["operator_protocol"]["control_route"] == "combined_http_api_browser"
    assert contract["operator_protocol"]["visual_checkpoint"] == "closed_ledger_stdin_v2"
    assert contract["operator_protocol"]["service_port"] == 5215
    assert contract["http_driver_digest"].startswith("sha256:")
    assert contract["matrix_plan"]["sha256"].startswith("sha256:")
    assert contract["contract_file"]["sha256"].startswith("sha256:")
    assert set(contract["scenario_inputs"]) == set(contract["matrix"])
    for scenario in contract["scenario_inputs"].values():
        assert scenario["prompts"]
        assert scenario["hard_oracles"]
        assert scenario["actions"]

    m01 = contract["scenario_inputs"]["M01"]
    assert m01["upload_stages"] == [
        {"before_prompt": 3, "fixtures": ["M01-sales.csv"]},
        {"before_prompt": 4, "fixtures": ["M01-action.csv"], "same_session": True},
    ]
    assert "下一同口径七日" in m01["prompts"][3]
    assert "且成本每单不高于本期" in m01["prompts"][3]
    assert "否则暂停增加预算并复核" in m01["prompts"][3]


def test_m02_contract_accepts_only_disclosed_receipt_bound_fitted_scenarios():
    launcher = _launcher_module()
    contract = launcher._frozen_matrix_contract(Path(__file__).parents[1], 5215)

    prompt = contract["scenario_inputs"]["M02"]["prompts"][0]
    oracles = "\n".join(contract["scenario_inputs"]["M02"]["hard_oracles"])

    assert "拟合情景" in prompt
    assert "R²" in prompt
    assert "未做留出验证/回测/外部验证" in prompt
    assert "host-recomputed" in oracles
    assert "0.0005 on the raw source scale" in oracles
    assert "without an explicit scale confirmation" in oracles
    assert "raw 0.10" in oracles


def test_m01_action_fixture_matches_independent_two_window_oracle(tmp_path):
    launcher = _launcher_module()
    launcher._write_fixtures(tmp_path)
    with (tmp_path / "M01-action.csv").open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))

    assert len(rows) == 14
    assert all(int(row["net_contribution"]) == int(row["amount"]) - int(row["campaign_cost"])
               for row in rows)
    assert [row["date"] for row in rows] == [
        *(f"2026-09-{day:02d}" for day in range(7, 14)),
        *(f"2026-09-{day:02d}" for day in range(14, 21)),
    ]
    for window, expected in ((rows[:7], (700, 140, 560, 70)),
                             (rows[7:], (770, 175, 595, 77))):
        assert tuple(sum(int(row[key]) for row in window) for key in
                     ("amount", "campaign_cost", "net_contribution", "orders")) == expected


def test_preflight_stdout_is_ascii_safe_without_losing_unicode_content():
    launcher = _launcher_module()

    output = launcher._stdout_manifest("passed", {"label": "R² 拟合情景"})

    output.encode("ascii")
    assert json.loads(output) == {"preflight": "passed", "label": "R² 拟合情景"}


def test_real_batch_uses_explicit_64k_output_cap_without_changing_product_default(tmp_path, monkeypatch):
    launcher = _launcher_module()
    for name in ("WORKSPACE_DIR", "SESSIONS_DIR", "MCP_ENABLED", "SKILL_AUTO_DISCOVER",
                 "DATA_AGENT_REAL_PROVIDER_NETWORK_ENABLED", "MAX_TOKENS"):
        monkeypatch.setenv(name, "")
    launcher._configure_isolation(tmp_path)
    assert launcher.P08_OUTPUT_MAX_TOKENS == 65_536
    assert __import__("os").environ["MAX_TOKENS"] == "65536"
    assert __import__("os").environ["DATA_AGENT_REAL_PROVIDER_NETWORK_ENABLED"] == "0"
    launcher._configure_isolation(tmp_path, network_enabled=True)
    assert __import__("os").environ["DATA_AGENT_REAL_PROVIDER_NETWORK_ENABLED"] == "1"


def test_final_scenario_supplement_requires_a_complete_call_cap_stop(tmp_path):
    launcher = _launcher_module()
    root = tmp_path
    prior = root / "tmp" / "prior"
    prior.mkdir(parents=True)
    (prior / "freeze.json").write_text(json.dumps({
        "matrix": launcher.MATRIX_IDS,
        "operator_protocol": {"control_route": "local_http_api"},
        "source_commit": "prior-code", "call_cap": 2,
    }), encoding="utf-8")
    events = [
        {"event": "started", "call_number": 1},
        {"event": "dispatched", "call_number": 1},
        {"event": "stream_exhausted", "call_number": 1},
        {"event": "started", "call_number": 2},
        {"event": "dispatched", "call_number": 2},
        {"event": "stream_exhausted", "call_number": 2},
        {"event": "denied", "reason": "call_cap_reached", "cap": 2},
    ]
    ledger = prior / "provider-calls.jsonl"
    ledger.write_text("\n".join(json.dumps(item) for item in events) + "\n", encoding="utf-8")
    records = [
        *({"scenario": scenario, "action": "ledger_reconciled"}
          for scenario in launcher.MATRIX_IDS[:-1]),
        {"scenario": "M06", "action": "persisted_reload", "session_id": "old-m06",
         "run_state": {"status": "failed"}, "errors": ["resume: failed"]},
    ]
    (prior / "http-matrix.jsonl").write_text(
        "\n".join(json.dumps(item) for item in records) + "\n", encoding="utf-8")
    state = prior / "sessions" / "old-m06" / "analysis_state.json"
    state.parent.mkdir(parents=True)
    state.write_text('{"pending_confirmations": []}', encoding="utf-8")

    identity = launcher._supplement_identity(root, prior)
    assert identity["scenario"] == "M06"
    assert identity["prior_run"] == "tmp/prior"
    assert identity["prior_ledger_sha256"] == launcher._sha256(ledger)

    events[-1]["reason"] = "other_reason"
    ledger.write_text("\n".join(json.dumps(item) for item in events) + "\n", encoding="utf-8")
    import pytest
    with pytest.raises(SystemExit, match="clean call-cap stop"):
        launcher._supplement_identity(root, prior)


def test_provider_failure_latches_all_later_transport(tmp_path):
    launcher = _launcher_module()
    ledger = launcher.ProviderLedger(tmp_path / "provider-calls.jsonl", 3)
    calls = []
    def failed(**kwargs):
        calls.append(kwargs)
        raise TimeoutError("unknown remote outcome")
    audited = ledger.wrap(failed)
    with pytest.raises(TimeoutError): audited(model="primary")
    with pytest.raises(RuntimeError, match="provider_failure_latched"):
        audited(model="auxiliary")
    assert len(calls) == ledger.count == 1
    assert [json.loads(s)["event"] for s in ledger.path.read_text().splitlines()] == ["started", "failed", "denied"]


def test_unresolved_stream_blocks_transport_even_after_late_exhaustion(tmp_path):
    launcher = _launcher_module()
    ledger = launcher.ProviderLedger(tmp_path / "provider-calls.jsonl", 3)
    calls = []
    def completion(**kwargs):
        calls.append(kwargs)
        return iter(["late delta"])
    audited = ledger.wrap(completion)
    first = audited(stream=True)
    with pytest.raises(RuntimeError, match="in_flight_or_unknown"):
        audited(stream=True)
    assert list(first) == ["late delta"]
    with pytest.raises(RuntimeError, match="provider_failure_latched"):
        audited(stream=True)
    assert len(calls) == ledger.count == 1


def test_request_response_capture_binds_full_context_without_credential(tmp_path):
    launcher = _launcher_module()
    ledger = launcher.ProviderLedger(tmp_path / "provider-calls.jsonl", 1,
        model="openai/deepseek-flash", endpoint="https://api.deepseek.com")
    context = [{"role":"system", "content":"host contract"},
               {"role":"assistant", "tool_calls":[{"id":"a", "type":"function", "function":{"name":"load_data", "arguments":"{}"}}]},
               {"role":"tool", "tool_call_id":"a", "content":"receipt"}]
    tools = [{"type":"function", "function":{"name":"load_data", "parameters":{"type":"object"}}}]
    response = {"choices":[{"message":{"content":"accepted"}}]}
    ledger.wrap(lambda **kw: response)(model=ledger.model, api_base=ledger.endpoint,
        api_key="private-test-key", messages=context, tools=tools, max_tokens=65536, num_retries=0)
    events = [json.loads(s) for s in ledger.path.read_text().splitlines()]
    request = tmp_path / events[0]["request_path"]
    assert launcher._sha256(request) == events[0]["request_sha256"]
    payload = json.loads(request.read_text(encoding="utf-8"))
    assert payload["messages"] == context and payload["tools"] == tools
    assert "private-test-key" not in request.read_text(encoding="utf-8")
    returned = tmp_path / events[-1]["response_path"]
    assert launcher._sha256(returned) == events[-1]["response_sha256"]
    assert json.loads(returned.read_text()) == response


@pytest.mark.parametrize("changed", [
    {"model":"other"}, {"api_base":"https://other.invalid"},
    {"max_tokens":None}, {"max_tokens":65537}, {"num_retries":1},
])
def test_frozen_transport_mismatch_never_dispatches(tmp_path, changed):
    launcher = _launcher_module()
    ledger = launcher.ProviderLedger(tmp_path / "provider-calls.jsonl", 2,
        model="frozen", endpoint="https://api.deepseek.com")
    calls = []
    kwargs = {"model":"frozen", "api_base":ledger.endpoint,"max_tokens":65536,"num_retries":0}
    kwargs.update(changed)
    with pytest.raises(RuntimeError, match="frozen Provider request mismatch"):
        ledger.wrap(lambda **kw: calls.append(kw))(**kwargs)
    assert ledger.count == 0 and not calls


def test_request_capture_fault_prevents_transport_and_latches(tmp_path, monkeypatch):
    launcher = _launcher_module()
    ledger = launcher.ProviderLedger(tmp_path / "provider-calls.jsonl", 2)
    calls = []
    def fail(*args): raise OSError("disk full")
    monkeypatch.setattr(ledger, "_capture", fail)
    audited = ledger.wrap(lambda **kw: calls.append(kw))
    with pytest.raises(RuntimeError, match="capture failed before transport"): audited()
    with pytest.raises(RuntimeError, match="ledger is unavailable"): audited()
    assert not calls


def test_source_inventory_covers_ignored_browser_asset_and_detects_mutation(tmp_path):
    launcher = _launcher_module()
    asset = tmp_path / "src/data_agent/web/static/vendor/plotly.min.js"
    asset.parent.mkdir(parents=True)
    asset.write_bytes(b"frozen asset")
    (tmp_path / ".env").write_text("API_KEY=not-captured")
    original = launcher._source_inventory(tmp_path)
    assert set(original) == {"src/data_agent/web/static/vendor/plotly.min.js"}
    asset.write_bytes(b"changed asset")
    assert launcher._source_inventory(tmp_path) != original


def test_p5_cost_fixtures_match_independent_formula_and_version_oracles(tmp_path):
    launcher = _launcher_module()
    launcher._write_fixtures(tmp_path)
    for name, expected in (("M06-promo.csv",86),("M06-promo-v2.csv",96)):
        with (tmp_path/name).open(newline="", encoding="utf-8") as stream:
            rows=list(csv.DictReader(stream))
        assert len(rows)==4
        assert sum(int(r["incremental_revenue"])-int(r["coupon_cost"])-int(r["channel_cost"]) for r in rows)==expected


def test_host_deadline_latches_even_if_remote_worker_returns_later(tmp_path):
    import types
    from data_agent.llm.client import HardRequestTimeout
    launcher=_launcher_module()
    ledger=launcher.ProviderLedger(tmp_path/"provider-calls.jsonl",3)
    class Client:
        def __init__(self, **kwargs): pass
        def _request(self, kwargs): raise HardRequestTimeout("deadline")
    module=types.SimpleNamespace(LLMClient=Client,HardRequestTimeout=HardRequestTimeout)
    launcher._install_one_shot_request_policy(module,ledger)
    with pytest.raises(HardRequestTimeout): Client()._request({})
    calls=[]
    with pytest.raises(RuntimeError,match="provider_failure_latched"):
        ledger.wrap(lambda **kw:calls.append(kw))()
    assert not calls and ledger.count==0


def test_smaller_auxiliary_budget_uses_the_same_frozen_transport(tmp_path):
    launcher=_launcher_module()
    ledger=launcher.ProviderLedger(tmp_path/"provider-calls.jsonl",2,model="frozen",endpoint="https://api.deepseek.com")
    calls=[]
    result=ledger.wrap(lambda **kw:calls.append(kw))(model=ledger.model,api_base=ledger.endpoint,max_tokens=2048,num_retries=0)
    assert result is None and len(calls)==1 and ledger.count==1


def test_actual_primary_and_auxiliary_clients_share_deadline_failure_latch(tmp_path, monkeypatch):
    import threading
    import data_agent.llm.client as client_module
    from litellm import ModelResponse
    launcher=_launcher_module()
    ledger=launcher.ProviderLedger(tmp_path/"provider-calls.jsonl",3)
    cls=client_module.LLMClient
    monkeypatch.setattr(cls,"__init__",cls.__init__)
    monkeypatch.setattr(cls,"_request",cls._request)
    monkeypatch.setattr(cls,"_p08_one_shot_init_installed",False,raising=False)
    launcher._install_one_shot_request_policy(client_module,ledger)
    release=threading.Event()
    returned=threading.Event()
    calls=[]
    def transport(**kwargs):
        calls.append(kwargs)
        release.wait(1)
        returned.set()
        return ModelResponse(choices=[{"message":{"role":"assistant","content":"late"},"finish_reason":"stop"}])
    primary=cls(model_id="frozen",timeout=.02,transport=ledger.wrap(transport))
    try:
        with pytest.raises(client_module.HardRequestTimeout):primary.chat([{"role":"user","content":"one"}])
    finally:release.set()
    assert returned.wait(1)
    with pytest.raises(RuntimeError,match="provider_failure_latched"):
        primary.for_purpose(max_tokens=2048).chat([{"role":"user","content":"auxiliary"}])
    assert len(calls)==ledger.count==1


def test_current_batch_requires_browser_full_matrix_and_800_shared_cap(tmp_path,monkeypatch):
    import json
    launcher=_launcher_module()
    assert launcher.DEFAULT_CALL_CAP==800
    with pytest.raises(SystemExit,match="complete M01-M06"):launcher._prepare(tmp_path,tmp_path/"tmp/new",800,8904,tmp_path/"tmp/old")
    with pytest.raises(SystemExit,match="between 1 and 800"):launcher._prepare(tmp_path,tmp_path/"tmp/new",801,8904)
    root=Path(__file__).parents[1]
    contract=json.loads((root/launcher.MATRIX_CONTRACT_PATH).read_text('utf8'));contract['operator_protocol']['control_route']='local_http_api'
    path=tmp_path/launcher.MATRIX_CONTRACT_PATH;path.parent.mkdir(parents=True);path.write_text(json.dumps(contract))
    with pytest.raises(SystemExit,match="browser route"):launcher._frozen_matrix_contract(tmp_path,8904)
    inventory=launcher._source_inventory(root)
    assert 'AGENTS.md' in inventory and 'docs/testing/acceptance-control-routes.md' in inventory
