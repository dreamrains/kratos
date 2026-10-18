from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from data_agent.config import AgentConfig
from data_agent.llm import client as client_module


def _capture_completion(captured):
    def fake_completion(**kwargs):
        captured.update(kwargs)
        msg = SimpleNamespace(content="ok", tool_calls=None, reasoning_content="")
        return SimpleNamespace(choices=[SimpleNamespace(message=msg, finish_reason="stop")])

    return fake_completion


def test_max_tokens_defaults_to_none_and_the_request_omits_it(monkeypatch):
    monkeypatch.delenv("MAX_TOKENS", raising=False)
    cfg = AgentConfig(_env_file=None)
    assert cfg.max_tokens is None

    captured: dict = {}
    with patch.object(client_module, "completion", _capture_completion(captured)):
        with patch.object(client_module, "get_config", lambda: cfg):
            client = client_module.LLMClient(model_id="test/model")
            client.chat(messages=[{"role": "user", "content": "hi"}])
    assert client.max_tokens is None
    assert "max_tokens" not in captured


def test_explicit_max_tokens_still_overrides_and_is_sent(monkeypatch):
    cfg = AgentConfig(_env_file=None)
    captured: dict = {}
    with patch.object(client_module, "completion", _capture_completion(captured)):
        with patch.object(client_module, "get_config", lambda: cfg):
            client = client_module.LLMClient(model_id="test/model", max_tokens=2000)
            client.chat(messages=[{"role": "user", "content": "hi"}])
    assert client.max_tokens == 2000
    assert captured["max_tokens"] == 2000


def test_configured_max_tokens_env_override_is_sent(monkeypatch):
    monkeypatch.setenv("MAX_TOKENS", "6000")
    cfg = AgentConfig(_env_file=None)
    captured: dict = {}
    with patch.object(client_module, "completion", _capture_completion(captured)):
        with patch.object(client_module, "get_config", lambda: cfg):
            client_module.LLMClient(model_id="test/model").chat(messages=[{"role": "user", "content": "hi"}])
    assert captured["max_tokens"] == 6000


@pytest.mark.parametrize("bad", [50, 200000])
def test_explicit_max_tokens_out_of_range_is_rejected(monkeypatch, bad):
    monkeypatch.setenv("MAX_TOKENS", str(bad))
    with pytest.raises(Exception):
        AgentConfig(_env_file=None)


# Approved decision50: complete-request admission and observed usage.
from types import SimpleNamespace
import pytest
from data_agent.config import AgentConfig
from data_agent.llm import client as cm

def client(monkeypatch,context=1000,output=100):
    cfg=SimpleNamespace(**AgentConfig(_env_file=None).model_dump())
    cfg.model_context_tokens=context;cfg.model_max_input_tokens=context;cfg.model_max_output_tokens=output
    monkeypatch.setattr(cm,"get_config",lambda:cfg)
    calls=[]
    def transport(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="ok",tool_calls=None,reasoning_content=""),finish_reason="stop")],usage=SimpleNamespace(prompt_tokens=17,completion_tokens=3,prompt_tokens_details=SimpleNamespace(cached_tokens=9)))
    return cm.LLMClient(model_id="custom/budget-test",transport=transport,max_tokens=output),calls

@pytest.mark.parametrize("part",["system","tools","history"])
def test_complete_request_rejects_oversize_before_transport(monkeypatch,part):
    c,calls=client(monkeypatch)
    messages=[{"role":"user","content":"short"}];system="";tools=None
    if part=="system":system="中"*1000
    if part=="history":messages.insert(0,{"role":"user","content":"中"*1000})
    if part=="tools":tools=[{"name":"tool","description":"中"*1000,"parameters":{"type":"object","properties":{}}}]
    with pytest.raises(ValueError,match="request_context_capacity"):
        c.chat(messages,tools=tools,system=system)
    assert calls==[]

def test_chat_once_rechecks_explicit_output_override(monkeypatch):
    c,calls=client(monkeypatch,context=2000,output=1800)
    with pytest.raises(ValueError,match="request_context_capacity"):
        c.chat_once([{"role":"user","content":"中"*500}],max_tokens=1800)
    assert calls==[]

def test_response_keeps_actual_input_output_cache_without_inventing_usage(monkeypatch):
    c,calls=client(monkeypatch,context=20000,output=100)
    r=c.chat([{"role":"user","content":"short"}])
    assert r.prompt_tokens==17 and r.completion_tokens==3 and r.cached_tokens==9



@pytest.mark.parametrize("window,expected",[(200000,164000),(1000000,884000)])
def test_budget_large_context_keeps_output_and_margin_independently(window,expected):
    from data_agent.llm.request_policy import resolve_request_budget
    cfg=AgentConfig(_env_file=None,MODEL_CONTEXT_TOKENS=window,MODEL_MAX_INPUT_TOKENS=window,MODEL_MAX_OUTPUT_TOKENS=16000)
    budget=resolve_request_budget("private/alias",cfg,16000)
    assert budget.input_allowance==expected
    assert budget.output_reserved==16000 and budget.safety_tokens==window//10


def test_unknown_model_capacity_is_not_guessed_and_does_not_call_transport(monkeypatch):
    cfg=AgentConfig(_env_file=None,MODEL_CONTEXT_TOKENS=None,MODEL_MAX_INPUT_TOKENS=None,MODEL_MAX_OUTPUT_TOKENS=None)
    monkeypatch.setattr(cm,"get_config",lambda:cfg);calls=[]
    c=cm.LLMClient(model_id="private/unknown-capacity",transport=lambda **kw:calls.append(kw))
    with pytest.raises(ValueError,match="request_model_capacity_unknown"):c.chat([{"role":"user","content":"q"}])
    assert calls==[]


@pytest.mark.parametrize("mode",["once","stream"])
def test_all_client_interfaces_admit_complete_system_and_tools_before_transport(monkeypatch,mode):
    c,calls=client(monkeypatch)
    kwargs={"messages":[{"role":"user","content":"q"}],"system":"中"*5000,"tools":[{"name":"t","description":"中"*5000,"parameters":{"type":"object"}}]}
    with pytest.raises(ValueError,match="request_context_capacity"):
        if mode=="once":c.chat_once(**kwargs,response_format={"type":"json_object"})
        else:list(c.stream_chat_structured(**kwargs))
    assert calls==[]


def test_response_schema_and_input_only_limit_are_part_of_admission(monkeypatch):
    c,calls=client(monkeypatch,context=20000,output=100)
    c._budget_config.model_max_input_tokens=500
    with pytest.raises(ValueError,match="request_context_capacity"):
        c.chat_once([{"role":"user","content":"q"}],response_format={"type":"json_schema","schema":{"description":"中"*5000}})
    assert calls==[]


def test_output_retry_ladder_is_rechecked_without_dispatching_an_over_capacity_retry(monkeypatch):
    from data_agent.llm.request_policy import RequestPolicy
    c,calls=client(monkeypatch,context=4000,output=1000)
    c._budget_config.model_max_output_tokens=32000
    c.request_policy=RequestPolicy(max_attempts=2,output_token_limits=(8000,))
    def truncated(**kw):
        calls.append(kw);return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="",tool_calls=None,reasoning_content=""),finish_reason="length")])
    c.transport=truncated
    with pytest.raises(ValueError,match="request_context_capacity"):c.chat([{"role":"user","content":"q"}])
    assert len(calls)==1 and calls[0]["max_tokens"]==1000


def test_known_model_uses_bundled_capacity_when_endpoint_override_is_absent():
    from data_agent.llm.request_policy import resolve_request_budget
    from data_agent.llm.routing import model_token_limits
    cfg=AgentConfig(_env_file=None,MODEL_CONTEXT_TOKENS=None,MODEL_MAX_INPUT_TOKENS=None,MODEL_MAX_OUTPUT_TOKENS=None)
    known=model_token_limits("gpt-4o");budget=resolve_request_budget("gpt-4o",cfg)
    assert budget.context_tokens==known["context"] and budget.output_reserved==known["output"]
    assert budget.source.startswith("bundled_model_metadata:")


def test_unavailable_automatic_tokenizer_uses_explicit_conservative_count_without_network(monkeypatch):
    from data_agent.llm.request_policy import count_request_tokens
    import tiktoken
    monkeypatch.setattr(tiktoken,"get_encoding",lambda *a,**kw:(_ for _ in ()).throw(AssertionError("tokenizer download forbidden")))
    value=count_request_tokens("private/no-tokenizer",[{"role":"user","content":"中文"*100}])
    assert value["method"]=="utf8_conservative_estimate" and value["tokens"]>=600


@pytest.mark.parametrize("missing",[False,True])
def test_stream_retains_usage_only_terminal_chunk_and_prices_only_known_counters(monkeypatch,missing):
    c,calls=client(monkeypatch,context=20000,output=100)
    c._budget_config.input_cost_per_million=2.;c._budget_config.output_cost_per_million=8.;c._budget_config.cached_input_cost_per_million=.5;c._budget_config.cost_currency="test-unit"
    def transport(**kwargs):
        calls.append(kwargs)
        terminal=SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="answer",tool_calls=None,reasoning_content=None),finish_reason="stop")])
        usage=SimpleNamespace(prompt_tokens=17,completion_tokens=3,prompt_tokens_details=SimpleNamespace(cached_tokens=9))
        return iter([terminal] if missing else [terminal,SimpleNamespace(choices=[],usage=usage)])
    c.transport=transport;r=list(c.stream_chat_structured([{"role":"user","content":"q"}]))[-1].response
    assert calls[0]["stream_options"]=={"include_usage":True}
    if missing:
        assert r.prompt_tokens is r.completion_tokens is r.cached_tokens is r.estimated_cost is None
    else:
        assert (r.prompt_tokens,r.completion_tokens,r.cached_tokens)==(17,3,9)
        assert r.estimated_cost["amount"]==pytest.approx(44.5/1000000) and r.estimated_cost["currency"]=="test-unit"


@pytest.mark.parametrize("key,value",[("model_context_tokens",0),("model_max_input_tokens",-1),("model_max_output_tokens",0),("publication_soft_tokens",0),("input_cost_per_million",float("inf")),("output_cost_per_million",-1)])
def test_request_budget_configuration_refuses_invalid_caps_or_prices(key,value):
    with pytest.raises(ValueError):AgentConfig(_env_file=None,**{key.upper():value})


def test_ui_request_budget_uses_complete_estimate_and_labels_history_fallback():
    from data_agent.llm.request_policy import resolve_request_budget,request_budget_status
    cfg=AgentConfig(_env_file=None,MODEL_CONTEXT_TOKENS=200000,MODEL_MAX_OUTPUT_TOKENS=16000,MAX_TOKENS=16000)
    policy=resolve_request_budget("private/alias",cfg,16000)
    complete=policy.estimate([{"role":"system","content":"rules"},{"role":"user","content":"q"}])
    current=request_budget_status(cfg,[],complete);fallback=request_budget_status(cfg,[{"role":"user","content":"q"}])
    assert current["used"]==complete["tokens"] and current["threshold"]==164000
    assert current["scope"]=="last_complete_request_estimate" and fallback["scope"]=="history_only_estimate"


@pytest.mark.parametrize("valid",[True,False])
def test_local_default_tokenizer_cache_is_verified_before_loading_without_download(tmp_path,monkeypatch,valid):
    import hashlib,os,tempfile,shutil,tiktoken,tiktoken.registry
    from pathlib import Path
    from data_agent.llm.request_policy import _local_encoder
    key=hashlib.sha1(b"https://openaipublic.blob.core.windows.net/encodings/o200k_base.tiktoken").hexdigest()
    installed=Path(os.environ["TIKTOKEN_CACHE_DIR"])/key
    cache=tmp_path/"data-gym-cache";cache.mkdir();asset=cache/key
    if valid:shutil.copyfile(installed,asset)
    else:asset.write_bytes(b"invalid local asset")
    monkeypatch.delenv("TIKTOKEN_CACHE_DIR");monkeypatch.delenv("DATA_GYM_CACHE_DIR",raising=False)
    monkeypatch.setattr(tempfile,"gettempdir",lambda:str(tmp_path))
    monkeypatch.setattr(tiktoken.registry,"ENCODINGS",{})
    import tiktoken.load
    monkeypatch.setattr(tiktoken.load,"read_file",lambda *a,**kw:(_ for _ in ()).throw(AssertionError("network asset read forbidden")))
    _local_encoder.cache_clear()
    try:
        encoder,method=_local_encoder("gpt-4o","tiktoken:o200k_base")
        assert (encoder is not None)==valid
        assert method==("local_tokenizer_estimate:o200k_base" if valid else "utf8_conservative_estimate")
        if valid:assert encoder("中文")>0
    finally:_local_encoder.cache_clear()
