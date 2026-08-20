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
        "model_id": "provider/model",
        "planning_context": {
            "model_id": "provider/model",
            "estimated_input_tokens": 100,
            "model_context_window_tokens": 1000,
            "reserved_output_tokens": 100,
            "available_input_tokens": 900,
            "fits": True,
        },
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
        model_id=issued.model_id,
        planning_context=issued.planning_context,
    )
    repeated = store.consume(
        issued.authorization_id,
        client_request_id="client_plan_one",
        purpose="analysis_planning",
        filename="sales.csv",
        source_fingerprint="sha256:" + "a" * 64,
        question="What is average sales?",
        model_id=issued.model_id,
        planning_context=issued.planning_context,
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
            model_id=issued.model_id,
            planning_context=issued.planning_context,
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
            model_id=issued.model_id,
            planning_context=issued.planning_context,
        )
    with pytest.raises(ProviderAuthorizationConflict, match="different request content"):
        store.consume(
            issued.authorization_id,
            client_request_id="client_plan_changed",
            purpose="analysis_planning",
            filename="sales.csv",
            source_fingerprint="sha256:" + "b" * 64,
            question="What is average sales?",
            model_id=issued.model_id,
            planning_context=issued.planning_context,
        )


def test_authorization_is_bound_to_one_planning_input(tmp_path):
    store = ProviderAuthorizationStore(tmp_path, "session_auth_input")
    issued = _issue(store, planning_input_id="planning_input_one")

    with pytest.raises(ProviderAuthorizationConflict, match="different request content"):
        store.consume(
            issued.authorization_id,
            client_request_id="client_plan_input",
            purpose="analysis_planning",
            filename="sales.csv",
            source_fingerprint="sha256:" + "a" * 64,
            question="What is average sales?",
            planning_input_id="planning_input_two",
            model_id=issued.model_id,
            planning_context=issued.planning_context,
        )

    consumed = store.consume(
        issued.authorization_id,
        client_request_id="client_plan_input",
        purpose="analysis_planning",
        filename="sales.csv",
        source_fingerprint="sha256:" + "a" * 64,
        question="What is average sales?",
        planning_input_id="planning_input_one",
        model_id=issued.model_id,
        planning_context=issued.planning_context,
    )
    assert consumed.planning_input_id == "planning_input_one"


@pytest.mark.parametrize(
    ("field", "changed"),
    [
        ("model_id", "provider/other-model"),
        ("estimated_input_tokens", 101),
        ("model_context_window_tokens", 2000),
        ("reserved_output_tokens", 200),
        ("available_input_tokens", 800),
    ],
)
def test_authorization_rejects_model_or_planning_context_drift_before_consumption(
    tmp_path, field, changed
):
    store = ProviderAuthorizationStore(tmp_path, f"session_auth_drift_{field}")
    issued = _issue(store)
    current_context = dict(issued.planning_context)
    current_model = issued.model_id
    if field == "model_id":
        current_model = changed
        current_context["model_id"] = changed
    else:
        current_context[field] = changed

    with pytest.raises(ProviderAuthorizationConflict, match="different"):
        store.consume(
            issued.authorization_id,
            client_request_id="client_plan_drift",
            purpose="analysis_planning",
            filename="sales.csv",
            source_fingerprint="sha256:" + "a" * 64,
            question="What is average sales?",
            model_id=current_model,
            planning_context=current_context,
        )

    assert store.get(issued.authorization_id).status is ProviderAuthorizationStatus.ISSUED
