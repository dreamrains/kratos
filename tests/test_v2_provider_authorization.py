from __future__ import annotations

import pytest

from data_agent.v2.provider_authorization import (
    ProviderAuthorizationConflict,
    ProviderAuthorizationStatus,
    ProviderAuthorizationStore,
)


def _issue(store: ProviderAuthorizationStore, **overrides):
    values = {
        "client_action_id": "action_plan_once",
        "purpose": "analysis_planning",
        "filename": "sales.csv",
        "source_fingerprint": "sha256:" + "a" * 64,
        "question": "What is average sales?",
        "provider_calls_authorized": 1,
        "confirm_provider_call": True,
    }
    values.update(overrides)
    return store.issue(**values)


def test_authorization_is_server_issued_and_idempotent_by_explicit_action(tmp_path):
    store = ProviderAuthorizationStore(tmp_path, "session_auth")

    first = _issue(store)
    repeated = _issue(store)

    assert first == repeated
    assert first.authorization_id.startswith("provider_auth_")
    assert first.status is ProviderAuthorizationStatus.ISSUED
    assert first.provider_calls_authorized == 1
    assert first.consumer_request_id == ""


def test_authorization_requires_exact_confirmation_and_one_call(tmp_path):
    store = ProviderAuthorizationStore(tmp_path, "session_auth_exact")

    with pytest.raises(ValueError, match="confirm_provider_call"):
        _issue(store, confirm_provider_call=False)
    with pytest.raises(ValueError, match="provider_calls_authorized"):
        _issue(store, provider_calls_authorized=2)
    with pytest.raises(ValueError, match="provider_calls_authorized"):
        _issue(store, provider_calls_authorized=True)


def test_authorization_is_bound_and_can_only_fund_one_client_request(tmp_path):
    store = ProviderAuthorizationStore(tmp_path, "session_auth_consume")
    issued = _issue(store)

    consumed = store.consume(
        issued.authorization_id,
        client_request_id="client_plan_one",
        purpose="analysis_planning",
        filename="sales.csv",
        source_fingerprint="sha256:" + "a" * 64,
        question="What is average sales?",
    )
    repeated = store.consume(
        issued.authorization_id,
        client_request_id="client_plan_one",
        purpose="analysis_planning",
        filename="sales.csv",
        source_fingerprint="sha256:" + "a" * 64,
        question="What is average sales?",
    )

    assert consumed == repeated
    assert consumed.status is ProviderAuthorizationStatus.CONSUMED
    assert consumed.consumer_request_id == "client_plan_one"
    with pytest.raises(ProviderAuthorizationConflict, match="different request"):
        store.consume(
            issued.authorization_id,
            client_request_id="client_plan_two",
            purpose="analysis_planning",
            filename="sales.csv",
            source_fingerprint="sha256:" + "a" * 64,
            question="What is average sales?",
        )


def test_authorization_rejects_changed_question_or_dataset(tmp_path):
    store = ProviderAuthorizationStore(tmp_path, "session_auth_binding")
    issued = _issue(store)

    with pytest.raises(ProviderAuthorizationConflict, match="different request content"):
        store.consume(
            issued.authorization_id,
            client_request_id="client_plan_changed",
            purpose="analysis_planning",
            filename="sales.csv",
            source_fingerprint="sha256:" + "a" * 64,
            question="What is maximum sales?",
        )
    with pytest.raises(ProviderAuthorizationConflict, match="different request content"):
        store.consume(
            issued.authorization_id,
            client_request_id="client_plan_changed",
            purpose="analysis_planning",
            filename="sales.csv",
            source_fingerprint="sha256:" + "b" * 64,
            question="What is average sales?",
        )
