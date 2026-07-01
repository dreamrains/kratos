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
    assert result.thaw_bundle() == bundle


def test_validation_result_is_immutable_and_defaults_are_not_shared():
    source = {"datasets": [{"columns": ["order_id"]}]}
    first = BundleValidationResult(True, bundle=source, details={"fields": ["datasets"]})
    second = BundleValidationResult(True)

    with pytest.raises(TypeError):
        first.bundle["datasets"][0]["columns"][0] = "customer_id"
    with pytest.raises(TypeError):
        first.details["fields"] += ("grain",)
    source["datasets"][0]["columns"][0] = "mutated"

    assert first.bundle["datasets"][0]["columns"] == ("order_id",)
    assert first.details["fields"] == ("datasets",)
    assert dict(second.bundle) == {}
    assert dict(second.details) == {}
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
                "columns": ["customer_id", " segment "],
                "rows": 10,
                "grain": " one row per customer ",
                "dataset_contract_id": "duc_customers_v1",
                "dataset": " customers ",
            },
            _dataset(
                columns=[
                    {"type": "string", "name": "order_id"},
                    {"type": "number", "name": "amount"},
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


def test_supported_question_order_changes_identity():
    first = _build(supported_questions=["highest revenue", "lowest revenue"])
    reversed_questions = _build(supported_questions=["lowest revenue", "highest revenue"])

    assert reversed_questions["id"] != first["id"]


@pytest.mark.parametrize("field", ["steps", "fields"])
def test_nested_list_order_changes_identity(field):
    first = _build(quality_findings=[{"finding": "review", field: ["first", "second"]}])
    reversed_items = _build(quality_findings=[{"finding": "review", field: ["second", "first"]}])

    assert reversed_items["id"] != first["id"]


def test_schema_column_identifier_internal_whitespace_changes_identity():
    first = _build(datasets=[_dataset(columns=["order_id", "Total  Amount"])])
    collapsed = _build(datasets=[_dataset(columns=["order_id", "Total Amount"])])

    assert collapsed["id"] != first["id"]
    assert first["datasets"][0]["columns"][1] == "Total  Amount"


def test_dataset_identifier_internal_whitespace_changes_identity():
    first = _build(datasets=[_dataset(dataset="Sales  Orders")])
    collapsed = _build(datasets=[_dataset(dataset="Sales Orders")])

    assert collapsed["id"] != first["id"]
    assert first["datasets"][0]["dataset"] == "Sales  Orders"


@pytest.mark.parametrize(
    ("overrides", "expected_path"),
    [
        ({"datasets": [_dataset(grain="order  level")]}, ("datasets", 0, "grain")),
        ({"relationship_candidates": [{"id": "rel", "status": "proposed", "left_key": "customer  id", "right_key": "id"}]}, ("relationship_candidates", 0, "left_key")),
        ({"relationship_candidates": [{"id": "rel", "status": "proposed", "left_key": "id", "right_key": "customer  id"}]}, ("relationship_candidates", 0, "right_key")),
        ({"relationship_candidates": [{"id": "rel", "status": "proposed", "shared_columns": ["customer  id"]}]}, ("relationship_candidates", 0, "shared_columns", 0)),
        ({"relationship_candidates": [{"id": "rel", "status": "proposed", "key_mapping": {"customer  id": "account  id"}}]}, ("relationship_candidates", 0, "key_mapping", "customer  id")),
        ({"metrics": [{"column": "Total  Amount"}]}, ("metrics", 0, "column")),
        ({"dimensions": ["Customer  Segment"]}, ("dimensions", 0)),
        ({"entities": ["Sales  Order"]}, ("entities", 0)),
        ({"metrics": ["Order  Count"]}, ("metrics", 0)),
    ],
)
def test_contract_identifier_paths_preserve_internal_whitespace(overrides, expected_path):
    first = _build(**overrides)
    collapsed_overrides = deepcopy(overrides)
    cursor = collapsed_overrides
    for part in expected_path[:-1]:
        cursor = cursor[part]
    final = expected_path[-1]
    if isinstance(cursor[final], str):
        cursor[final] = cursor[final].replace("  ", " ")
    else:
        value = next(iter(cursor[final].values()))
        key = next(iter(cursor[final]))
        cursor[final] = {key.replace("  ", " "): value.replace("  ", " ")}
    collapsed = _build(**collapsed_overrides)

    assert collapsed["id"] != first["id"]


def test_relationship_key_mapping_identifier_keys_trim_edges_only():
    padded = _build(relationship_candidates=[{
        "id": "rel",
        "status": "proposed",
        "key_mapping": {" customer  id ": " account  id "},
    }])
    trimmed = _build(relationship_candidates=[{
        "id": "rel",
        "status": "proposed",
        "key_mapping": {"customer  id": "account  id"},
    }])
    collapsed = _build(relationship_candidates=[{
        "id": "rel",
        "status": "proposed",
        "key_mapping": {"customer id": "account id"},
    }])

    assert padded["id"] == trimmed["id"]
    assert collapsed["id"] != trimmed["id"]


def test_schema_column_prose_still_collapses_harmless_whitespace():
    first = _build(datasets=[_dataset(columns=[{
        "name": "amount",
        "type": "number",
        "description": "gross   order amount",
    }])])
    collapsed = _build(datasets=[_dataset(columns=[{
        "name": "amount",
        "type": "number",
        "description": "gross order amount",
    }])])

    assert collapsed["id"] == first["id"]


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


def test_created_at_schema_column_changes_fingerprint():
    base_schema = {
        "order_id": {"type": "string", "nullable": False},
        "amount": {"type": "number", "nullable": True},
    }
    first = _build(datasets=[_dataset(columns=base_schema)])
    second = _build(datasets=[_dataset(columns={
        **base_schema,
        "created_at": {"type": "timestamp", "nullable": False},
    })])

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


def test_nested_relationship_key_mapping_is_canonical_and_changes_identity():
    first = _build(relationship_candidates=[{
        "id": "orders_customers",
        "status": "proposed",
        "key_mapping": {
            "created_at": "customer_created_at",
            "customer_id": "id",
        },
        "validation": {"cardinality": " many_to_one ", "coverage": 0.95},
    }])
    reordered = _build(relationship_candidates=[{
        "validation": {"coverage": 0.95, "cardinality": "many_to_one"},
        "key_mapping": {
            "customer_id": "id",
            "created_at": " customer_created_at ",
        },
        "status": " proposed ",
        "id": "orders_customers",
    }])
    changed = _build(relationship_candidates=[{
        "id": "orders_customers",
        "status": "proposed",
        "key_mapping": {
            "created_at": "account_created_at",
            "customer_id": "id",
        },
        "validation": {"cardinality": "many_to_one", "coverage": 0.95},
    }])

    assert reordered["data_fingerprint"] == first["data_fingerprint"]
    assert reordered["id"] == first["id"]
    assert changed["data_fingerprint"] != first["data_fingerprint"]
    assert changed["id"] != first["id"]


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


@pytest.mark.parametrize("version", [None, "1", [1], True, 1.0, 2])
def test_validation_rejects_malformed_root_version(version):
    result = validate_data_understanding_bundle({
        "contract_version": DATA_UNDERSTANDING_VERSION,
        "version": version,
        "datasets": [_dataset()],
    })

    assert result.ok is False
    assert result.error_type == "invalid_bundle_version"


@pytest.mark.parametrize("grain", ["order", ["order"], 1])
def test_validation_rejects_non_object_root_grain(grain):
    result = validate_data_understanding_bundle({
        "contract_version": DATA_UNDERSTANDING_VERSION,
        "version": 1,
        "grain": grain,
        "datasets": [_dataset()],
    })

    assert result.ok is False
    assert result.error_type == "invalid_bundle_grain"


def test_bundle_root_timestamps_do_not_change_identity():
    first = _build()
    with_timestamps = deepcopy(first)
    with_timestamps["created_at"] = "2026-07-01 10:00:00"
    with_timestamps["updated_at"] = "2026-07-01 10:01:00"
    with_timestamps["generated_at"] = "2026-07-01 10:02:00"

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
        "data_fingerprint": "sha256:first",
        "path": "updated.json",
    })

    assert len(state.data_understanding_bundles) == 1
    assert updated["created_at"] == first["created_at"]
    assert updated["data_fingerprint"] == "sha256:first"
    assert updated["path"] == "updated.json"
    assert state.active_scope["active_dataset"] == "orders"
    assert state.active_scope["related_ref_ids"]["data_understanding_bundles"] == ["dub_orders"]

    restored = AnalysisSessionState.from_dict(state.to_dict(), "s1")
    assert restored.data_understanding_bundles == state.data_understanding_bundles
    assert "data_understanding_bundles: 1" in analysis_state_summary(restored)


def test_analysis_state_rejects_bundle_id_fingerprint_collision():
    state = AnalysisSessionState(session_id="s1")
    state.add_data_understanding_bundle_ref({
        "id": "dub_orders",
        "data_fingerprint": "sha256:first",
    })

    with pytest.raises(ValueError, match="different data_fingerprint"):
        state.add_data_understanding_bundle_ref({
            "id": "dub_orders",
            "data_fingerprint": "sha256:second",
        })


@pytest.mark.parametrize("malformed", [None, "", 123, ["sha256:first"]])
def test_analysis_state_rejects_malformed_incoming_bundle_fingerprint(malformed):
    state = AnalysisSessionState(session_id="s1")
    state.add_data_understanding_bundle_ref({
        "id": "dub_orders",
        "data_fingerprint": "sha256:first",
    })

    with pytest.raises(ValueError, match="non-empty string data_fingerprint"):
        state.add_data_understanding_bundle_ref({
            "id": "dub_orders",
            "data_fingerprint": malformed,
        })


@pytest.mark.parametrize("malformed", [None, "", 123, ["sha256:first"]])
def test_analysis_state_rejects_corrupted_existing_bundle_fingerprint(malformed):
    state = AnalysisSessionState(session_id="s1")
    state.data_understanding_bundles.append({
        "id": "dub_orders",
        "data_fingerprint": malformed,
    })

    with pytest.raises(ValueError, match="non-empty string data_fingerprint"):
        state.add_data_understanding_bundle_ref({
            "id": "dub_orders",
            "data_fingerprint": "sha256:first",
        })


def test_old_analysis_state_defaults_bundle_refs_to_empty_list():
    restored = AnalysisSessionState.from_dict({"session_id": "legacy"}, "legacy")

    assert restored.data_understanding_bundles == []
    assert restored.to_dict()["data_understanding_bundles"] == []
