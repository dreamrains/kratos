from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError

import pytest

from data_agent.agent.analysis_state import AnalysisSessionState, analysis_state_summary
from data_agent.agent.data_understanding import (
    DATA_UNDERSTANDING_VERSION,
    BundleValidationResult,
    build_data_understanding_bundle,
    validate_data_understanding_bundle,
)


def _dataset(**overrides):
    dataset = {
        "dataset": "orders",
        "dataset_contract_id": "duc_orders_v1",
        "grain": "one row per order",
        "rows": 10,
        "columns": [
            {"name": "order_id", "type": "string"},
            {"name": "amount", "type": "number"},
        ],
    }
    dataset.update(overrides)
    return dataset


def _build(**overrides):
    arguments = {
        "datasets": [_dataset()],
        "quality_findings": [{"dataset": "orders", "finding": " no missing ids "}],
        "relationship_candidates": [
            {
                "id": "orders_customers",
                "status": "proposed",
                "left_dataset": "orders",
                "right_dataset": "customers",
            }
        ],
    }
    arguments.update(overrides)
    return build_data_understanding_bundle(**arguments)


def test_bundle_is_versioned_fingerprinted_and_valid():
    bundle = _build()

    assert DATA_UNDERSTANDING_VERSION == "data_understanding.v1"
    assert bundle["contract_version"] == DATA_UNDERSTANDING_VERSION
    assert bundle["data_fingerprint"].startswith("sha256:")
    assert bundle["id"].startswith("dub_")
    result = validate_data_understanding_bundle(bundle)
    assert result.ok is True
    assert result.bundle == bundle


def test_validation_result_is_immutable_and_defaults_are_not_shared():
    first = BundleValidationResult(True)
    second = BundleValidationResult(True)

    first.bundle["x"] = 1
    first.details["field"] = "datasets"

    assert second.bundle == {}
    assert second.details == {}
    with pytest.raises(FrozenInstanceError):
        first.ok = False


def test_identity_ignores_list_dict_order_and_harmless_whitespace():
    first = _build(
        datasets=[
            _dataset(),
            _dataset(
                dataset="customers",
                dataset_contract_id="duc_customers_v1",
                grain="one row per customer",
                columns=["customer_id", "segment"],
            ),
        ],
        quality_findings=[
            {"dataset": "orders", "finding": "no missing ids"},
            {"dataset": "customers", "finding": "segment complete"},
        ],
    )
    second = _build(
        datasets=[
            {
                "columns": [" segment ", "customer_id"],
                "rows": 10,
                "grain": " one   row per customer ",
                "dataset_contract_id": "duc_customers_v1",
                "dataset": " customers ",
            },
            _dataset(
                columns=[
                    {"type": "number", "name": "amount"},
                    {"type": "string", "name": "order_id"},
                ]
            ),
        ],
        quality_findings=[
            {"finding": " segment  complete ", "dataset": "customers"},
            {"finding": "no missing ids", "dataset": "orders"},
        ],
    )

    assert second == first
    assert second["data_fingerprint"] == first["data_fingerprint"]
    assert second["id"] == first["id"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("rows", 11),
        ("grain", "one row per order item"),
        ("columns", ["order_id", "net_amount"]),
    ],
)
def test_meaningful_dataset_mutation_changes_fingerprint(field, value):
    first = _build()
    second = _build(datasets=[_dataset(**{field: value})])

    assert second["data_fingerprint"] != first["data_fingerprint"]
    assert second["id"] != first["id"]


def test_quality_and_relationship_mutations_change_fingerprint():
    first = _build()
    changed_quality = _build(quality_findings=[{"dataset": "orders", "finding": "duplicate ids"}])
    changed_relationship = _build(
        relationship_candidates=[{"id": "orders_customers", "status": "rejected"}]
    )
    changed_relationship_identity = _build(
        relationship_candidates=[{
            "id": "orders_accounts",
            "status": "proposed",
            "left_dataset": "orders",
            "right_dataset": "customers",
        }]
    )

    assert changed_quality["data_fingerprint"] != first["data_fingerprint"]
    assert changed_relationship["data_fingerprint"] != first["data_fingerprint"]
    assert changed_relationship_identity["data_fingerprint"] != first["data_fingerprint"]


@pytest.mark.parametrize(
    ("mutation", "missing_field"),
    [
        ({"dataset": ""}, "dataset"),
        ({"dataset_contract_id": ""}, "dataset_contract_id"),
        ({"grain": ""}, "grain"),
        ({"rows": None}, "rows"),
        ({"columns": []}, "columns"),
    ],
)
def test_invalid_or_missing_dataset_understanding_is_rejected(mutation, missing_field):
    dataset = _dataset()
    dataset.update(mutation)

    result = validate_data_understanding_bundle({
        "contract_version": DATA_UNDERSTANDING_VERSION,
        "datasets": [dataset],
        "quality_findings": [],
        "relationship_candidates": [],
    })

    assert result.ok is False
    assert result.error_type == "invalid_dataset_understanding"
    assert missing_field in result.details["fields"]


def test_schema_can_supply_columns_contract():
    dataset = _dataset()
    dataset.pop("columns")
    dataset["schema"] = {
        "order_id": {"type": "string", "nullable": False},
        "amount": {"type": "number", "nullable": True},
    }

    bundle = _build(datasets=[dataset])

    assert bundle["datasets"][0]["schema"] == {
        "amount": {"nullable": True, "type": "number"},
        "order_id": {"nullable": False, "type": "string"},
    }


@pytest.mark.parametrize("field", ["dataset", "dataset_contract_id", "grain"])
def test_non_scalar_dataset_text_fields_are_rejected(field):
    dataset = _dataset(**{field: {"unexpected": "object"}})

    result = validate_data_understanding_bundle({
        "contract_version": DATA_UNDERSTANDING_VERSION,
        "datasets": [dataset],
        "quality_findings": [],
        "relationship_candidates": [],
    })

    assert result.ok is False
    assert result.error_type == "invalid_dataset_understanding"
    assert field in result.details["fields"]


@pytest.mark.parametrize("status", ["proposed", "validating", "validated", "rejected", "needs_confirmation"])
def test_canonical_relationship_statuses_are_preserved_as_hypotheses(status):
    bundle = _build(relationship_candidates=[{"id": "rel", "status": status}])

    assert bundle["relationship_candidates"][0]["status"] == status


def test_relationship_status_normalizes_harmless_whitespace():
    bundle = _build(relationship_candidates=[{"id": "rel", "status": " proposed "}])

    assert bundle["relationship_candidates"][0]["status"] == "proposed"


def test_invalid_relationship_status_is_rejected():
    result = validate_data_understanding_bundle({
        "contract_version": DATA_UNDERSTANDING_VERSION,
        "datasets": [_dataset()],
        "quality_findings": [],
        "relationship_candidates": [{"id": "rel", "status": "possibly_linked"}],
    })

    assert result.ok is False
    assert result.error_type == "invalid_relationship_candidate"


def test_validation_rejects_wrong_version_and_empty_datasets():
    wrong_version = validate_data_understanding_bundle({
        "contract_version": "data_understanding.v0",
        "datasets": [_dataset()],
    })
    empty = validate_data_understanding_bundle({
        "contract_version": DATA_UNDERSTANDING_VERSION,
        "datasets": [],
    })

    assert wrong_version.error_type == "unsupported_contract_version"
    assert empty.error_type == "invalid_datasets"


def test_bundle_timestamps_do_not_change_identity():
    first = _build()
    with_timestamps = deepcopy(first)
    with_timestamps["created_at"] = "2026-07-01 10:00:00"
    with_timestamps["quality_findings"][0]["updated_at"] = "2026-07-01 10:01:00"

    result = validate_data_understanding_bundle(with_timestamps)

    assert result.ok is True
    assert result.bundle["id"] == first["id"]
    assert result.bundle["data_fingerprint"] == first["data_fingerprint"]


def test_validation_rejects_stale_identity_after_meaningful_mutation():
    bundle = _build()
    bundle["datasets"][0]["rows"] += 1

    result = validate_data_understanding_bundle(bundle)

    assert result.ok is False
    assert result.error_type == "bundle_identity_mismatch"


def test_analysis_state_bundle_ref_round_trip_upsert_summary_and_active_tracking():
    state = AnalysisSessionState(session_id="s1")
    first = state.add_data_understanding_bundle_ref({
        "id": "dub_orders",
        "dataset": "orders",
        "data_fingerprint": "sha256:first",
    })
    updated = state.add_data_understanding_bundle_ref({
        "id": "dub_orders",
        "dataset": "orders",
        "data_fingerprint": "sha256:second",
    })

    assert len(state.data_understanding_bundles) == 1
    assert updated["created_at"] == first["created_at"]
    assert updated["data_fingerprint"] == "sha256:second"
    assert state.active_scope["active_dataset"] == "orders"
    assert state.active_scope["related_ref_ids"]["data_understanding_bundles"] == ["dub_orders"]

    restored = AnalysisSessionState.from_dict(state.to_dict(), "s1")
    assert restored.data_understanding_bundles == state.data_understanding_bundles
    assert "data_understanding_bundles: 1" in analysis_state_summary(restored)


def test_old_analysis_state_defaults_bundle_refs_to_empty_list():
    restored = AnalysisSessionState.from_dict({"session_id": "legacy"}, "legacy")

    assert restored.data_understanding_bundles == []
    assert restored.to_dict()["data_understanding_bundles"] == []
