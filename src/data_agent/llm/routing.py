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
    """Best-effort max input tokens across equivalent forms of one model."""
    import litellm

    for form in _candidate_forms(model_id):
        try:
            info = litellm.get_model_info(form)
        except Exception:
            continue
        if isinstance(info, dict):
            value = info.get("max_input_tokens") or info.get("max_tokens")
            if value:
                return int(value)
    return None
