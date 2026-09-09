"""Fail-closed defaults shared by the normal offline pytest suite."""
from __future__ import annotations

import os

import pytest


os.environ.update({
    "API_BASE": "http://127.0.0.1:9",
    "API_KEY": "data-agent-offline-no-provider",
    "GOLDEN_LIVE_SMOKE": "0",
    "DATA_AGENT_REAL_PROVIDER_NETWORK_ENABLED": "0",
})


@pytest.fixture(autouse=True)
def forbid_unmocked_provider_requests(monkeypatch):
    """Make accidental LLM calls fail immediately instead of waiting on I/O."""
    from data_agent.llm import client

    def forbidden_provider_call(*args, **kwargs):
        raise RuntimeError("Offline pytest forbids unmocked Provider requests")

    monkeypatch.setattr(client, "completion", forbidden_provider_call)
