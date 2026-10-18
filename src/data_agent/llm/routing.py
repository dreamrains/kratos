"""Model-name routing normalization for provider-agnostic configuration.

Bare model names that litellm cannot route (its ``get_llm_provider`` raises
``BadRequestError`` for e.g. ``deepseek-v4-flash``) are mapped onto the
verified native provider path.  Explicit ``provider/`` prefixes are always
authoritative and never rewritten.  Only families verified against the
installed litellm are listed; unknown bare names keep litellm's default
routing instead of being guessed into a provider.
"""

from __future__ import annotations

from typing import Optional

# Bare-name family prefixes -> litellm provider key.  Every entry must resolve
# offline via litellm.get_llm_provider before it is added here.
_PROVIDER_FAMILIES: dict[str, str] = {
    "deepseek-": "deepseek",
}


def normalize_model_id(model_id: str) -> str:
    """Return a litellm-routable model id for a user-configured name."""
    if not isinstance(model_id, str) or not model_id.strip():
        return model_id
    name = model_id.strip()
    if "/" in name:
        return name
    for family_prefix, provider in _PROVIDER_FAMILIES.items():
        if name.startswith(family_prefix):
            return f"{provider}/{name}"
    return name


def _candidate_forms(model_id: str) -> list[str]:
    forms = [model_id]
    stripped = model_id.split("/", 1)[-1]
    if stripped != model_id:
        forms.append(stripped)
    normalized = normalize_model_id(model_id)
    if normalized not in forms:
        forms.append(normalized)
    return forms


def model_context_window(model_id: str) -> Optional[int]:
    """Compatibility projection of the one local capacity catalogue."""
    return model_token_limits(model_id)["input"]


from functools import lru_cache


@lru_cache(maxsize=1)
def _bundled_model_limits():
    from importlib import resources
    import json, litellm
    return json.loads(resources.files(litellm).joinpath("model_prices_and_context_window_backup.json").read_text(encoding="utf-8"))


def model_token_limits(model_id: str) -> dict:
    """Read bundled metadata only; endpoint configuration may override it.

    When no distinct total context is published, max_input_tokens is also
    used as a conservative shared-context bound. It is never added to output.
    """
    catalogue = _bundled_model_limits()
    for form in _candidate_forms(model_id):
        info = catalogue.get(form)
        if isinstance(info, dict):
            incoming = info.get("max_input_tokens") or info.get("max_tokens")
            if incoming:
                return {"input": int(incoming), "context": int(incoming),
                        "output": int(info["max_output_tokens"]) if info.get("max_output_tokens") else None,
                        "source": "bundled_model_metadata:" + form}
    return {"input": None, "context": None, "output": None, "source": "unknown"}
