from __future__ import annotations

import litellm

from data_agent.llm.client import LLMClient
from data_agent.llm.routing import model_context_window, normalize_model_id


def test_bare_deepseek_family_names_route_to_the_deepseek_provider():
    assert normalize_model_id("deepseek-v4-flash") == "deepseek/deepseek-v4-flash"
    assert normalize_model_id("deepseek-chat") == "deepseek/deepseek-chat"


def test_explicit_provider_prefixes_are_authoritative_and_unchanged():
    assert normalize_model_id("openai/deepseek-v4-flash") == "openai/deepseek-v4-flash"
    assert normalize_model_id("deepseek/deepseek-v4-flash") == "deepseek/deepseek-v4-flash"
    assert normalize_model_id("azure/gpt-4o") == "azure/gpt-4o"


def test_unknown_bare_names_stay_unchanged_and_keep_default_routing():
    assert normalize_model_id("mystery-model-x") == "mystery-model-x"
    assert normalize_model_id("gpt-4o") == "gpt-4o"


def test_normalized_route_resolves_without_network():
    model, provider, _, _ = litellm.get_llm_provider(normalize_model_id("deepseek-v4-flash"))
    assert model == "deepseek-v4-flash"
    assert provider == "deepseek"


def test_context_window_falls_back_across_equivalent_model_forms():
    assert model_context_window("openai/deepseek-chat") == 131072
    assert model_context_window("deepseek/deepseek-chat") == 131072
    assert model_context_window("deepseek-chat") == 131072


def test_context_window_is_none_when_no_form_has_metadata():
    assert model_context_window("openai/deepseek-v4-flash") is None


def test_llm_client_normalizes_the_configured_model_route():
    assert LLMClient(model_id="deepseek-v4-flash").model_id == "deepseek/deepseek-v4-flash"
    assert LLMClient(model_id="openai/deepseek-v4-flash").model_id == "openai/deepseek-v4-flash"
