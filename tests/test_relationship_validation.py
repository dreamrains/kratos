from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError
from decimal import Decimal
import json
import math
from uuid import UUID

import numpy as np
import pandas as pd
import pytest

from data_agent.agent.data_understanding import build_data_understanding_bundle
from data_agent.agent.relationship_validation import (
    DEFAULT_MAX_JOIN_MULTIPLIER,
    DEFAULT_MAX_NULL_RATE,
    DEFAULT_MIN_ROW_COVERAGE,
    RelationshipValidation,
    validate_relationship,
)


def _validate(left_values, right_values, **kwargs):
    return validate_relationship(
        pd.DataFrame({"id": left_values}),
        pd.DataFrame({"id": right_values}),
        left_key="id",
        right_key="id",
        **kwargs,
    )


def _dataset(name):
    return {
        "dataset": name,
        "dataset_contract_id": f"duc_{name}_v1",
        "grain": f"one row per {name}",
        "rows": 3,
        "columns": ["id"],
    }


def test_plan_many_to_many_example_is_rejected():
    result = _validate([1, 1, 2], [1, 1, 3])

    assert result.cardinality == "many_to_many"
    assert result.status == "rejected"
    assert "many_to_many_join_explosion" in result.risks


def test_plan_two_thirds_one_to_one_overlap_is_validated():
    result = _validate([1, 2, 3], [1, 2, 4])

    assert result.status == "validated"
    assert result.cardinality == "one_to_one"
    assert result.left_row_coverage == pytest.approx(2 / 3)
    assert result.right_row_coverage == pytest.approx(2 / 3)
    assert result.left_distinct_key_coverage == pytest.approx(2 / 3)
    assert result.right_distinct_key_coverage == pytest.approx(2 / 3)


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        ([1, 2], [1, 2], "one_to_one"),
        ([1, 2], [1, 1, 2], "one_to_many"),
        ([1, 1, 2], [1, 2], "many_to_one"),
        ([1, 1, 2], [1, 1, 2], "many_to_many"),
    ],
)
def test_all_four_cardinalities(left, right, expected):
    assert _validate(left, right).cardinality == expected


def test_expected_join_rows_are_calculated_from_multiplicities():
    result = _validate([1, 1, 2, 8], [1, 1, 1, 2, 9])

    assert result.expected_inner_join_rows == 7
    assert result.join_row_baseline == 5
    assert result.row_multiplier == pytest.approx(1.4)


@pytest.mark.parametrize(
    ("left", "right", "left_key", "right_key", "risk"),
    [
        (pd.DataFrame({"id": [1]}), pd.DataFrame({"id": [1]}), "missing", "id", "missing_left_key"),
        (pd.DataFrame({"id": [1]}), pd.DataFrame({"id": [1]}), "id", "missing", "missing_right_key"),
        (pd.DataFrame(columns=["id"]), pd.DataFrame({"id": [1]}), "id", "id", "empty_left_data"),
        (pd.DataFrame({"id": [1]}), pd.DataFrame(columns=["id"]), "id", "id", "empty_right_data"),
    ],
)
def test_invalid_or_empty_inputs_fail_closed(left, right, left_key, right_key, risk):
    result = validate_relationship(left, right, left_key=left_key, right_key=right_key)

    assert result.status == "rejected"
    assert risk in result.risks


def test_non_dataframe_inputs_fail_closed():
    result = validate_relationship({"id": [1]}, pd.DataFrame({"id": [1]}), left_key="id", right_key="id")

    assert result.status == "rejected"
    assert result.risks == ("invalid_left_type",)


@pytest.mark.parametrize(
    ("left_key", "right_key", "risk"),
    [([], [], "empty_key"), (["a", "b"], ["a"], "key_arity_mismatch"), ("", "id", "empty_key")],
)
def test_key_shape_is_validated(left_key, right_key, risk):
    frame = pd.DataFrame({"a": [1], "b": [2], "id": [1]})

    result = validate_relationship(frame, frame, left_key=left_key, right_key=right_key)

    assert result.status == "rejected"
    assert risk in result.risks


def test_null_keys_do_not_distort_cardinality_and_reduce_row_coverage():
    result = _validate([1, 2, None, None], [1, 2, None, None])

    assert result.cardinality == "one_to_one"
    assert result.expected_inner_join_rows == 2
    assert result.left_row_coverage == 0.5
    assert result.left_null_rate == 0.5
    assert "high_left_null_rate" in result.risks
    assert result.status == "needs_confirmation"


def test_pandas_missing_scalar_is_treated_as_a_null_key():
    left = pd.DataFrame({"id": pd.Series([1, pd.NA], dtype="Int64")})
    right = pd.DataFrame({"id": pd.Series([1, 2], dtype="Int64")})

    result = validate_relationship(left, right, left_key="id", right_key="id", min_row_coverage=0.0)

    assert result.left_null_rate == 0.5
    assert result.expected_inner_join_rows == 1


@pytest.mark.parametrize("side", ["left", "right"])
def test_all_null_keys_are_rejected(side):
    left = [None, None] if side == "left" else [1, 2]
    right = [None, None] if side == "right" else [1, 2]

    result = _validate(left, right)

    assert result.status == "rejected"
    assert f"all_null_{side}_key" in result.risks


def test_composite_keys_use_tuple_semantics():
    left = pd.DataFrame({"tenant": ["a", "a", "b"], "id": [1, 2, 1]})
    right = pd.DataFrame({"tenant_id": ["a", "b", "b"], "item_id": [1, 1, 2]})

    result = validate_relationship(
        left,
        right,
        left_key=("tenant", "id"),
        right_key=["tenant_id", "item_id"],
    )

    assert result.normalized_left_key == ("tenant", "id")
    assert result.normalized_right_key == ("tenant_id", "item_id")
    assert result.expected_inner_join_rows == 2
    assert result.cardinality == "one_to_one"


def test_duplicate_left_key_label_is_rejected_without_raising():
    left = pd.DataFrame([[1, 10], [2, 20]], columns=["id", "id"])
    right = pd.DataFrame({"id": [1, 2]})

    result = validate_relationship(left, right, left_key="id", right_key="id")

    assert result.status == "rejected"
    assert result.risks == ("ambiguous_key_column",)


def test_duplicate_right_key_label_is_rejected_without_raising():
    left = pd.DataFrame({"id": [1, 2]})
    right = pd.DataFrame([[1, 10], [2, 20]], columns=["id", "id"])

    result = validate_relationship(left, right, left_key="id", right_key="id")

    assert result.status == "rejected"
    assert result.risks == ("ambiguous_key_column",)


def test_duplicate_label_in_composite_key_is_rejected_without_raising():
    left = pd.DataFrame(
        [["a", 1, 10], ["b", 2, 20]],
        columns=["tenant", "id", "id"],
    )
    right = pd.DataFrame({"tenant": ["a", "b"], "id": [1, 2]})

    result = validate_relationship(
        left,
        right,
        left_key=("tenant", "id"),
        right_key=("tenant", "id"),
    )

    assert result.status == "rejected"
    assert result.risks == ("ambiguous_key_column",)


def test_duplicate_non_key_label_does_not_invalidate_relationship():
    left = pd.DataFrame([[1, 10, 100], [2, 20, 200]], columns=["id", "value", "value"])
    right = pd.DataFrame({"id": [1, 2]})

    result = validate_relationship(left, right, left_key="id", right_key="id")

    assert result.status == "validated"


@pytest.mark.parametrize("side", ["left", "right"])
def test_multiindex_columns_are_rejected_without_raising(side):
    unusual = pd.DataFrame(
        [[1, 10], [2, 20]],
        columns=pd.MultiIndex.from_tuples([("id", "primary"), ("id", "secondary")]),
    )
    ordinary = pd.DataFrame({"id": [1, 2]})
    left, right = (unusual, ordinary) if side == "left" else (ordinary, unusual)

    result = validate_relationship(left, right, left_key="id", right_key="id")

    assert result.status == "rejected"
    assert result.risks == ("unsupported_column_index",)


def test_non_scalar_column_index_is_rejected_without_raising():
    columns = pd.Index([("id", "primary")], tupleize_cols=False)
    left = pd.DataFrame([[1]], columns=columns)

    result = validate_relationship(
        left,
        pd.DataFrame({"id": [1]}),
        left_key="id",
        right_key="id",
    )

    assert result.status == "rejected"
    assert result.risks == ("unsupported_column_index",)


@pytest.mark.parametrize("side", ["left", "right"])
def test_duplicate_component_in_supplied_composite_key_is_rejected(side):
    frame = pd.DataFrame({"id": [1, 2]})
    left_key = ["id", "id"] if side == "left" else ["id"]
    right_key = ["id", "id"] if side == "right" else ["id"]

    result = validate_relationship(
        frame,
        frame,
        left_key=left_key,
        right_key=right_key,
    )

    assert result.status == "rejected"
    assert result.risks == (f"duplicate_{side}_key_component",)


def test_type_family_mismatch_needs_confirmation():
    result = _validate([1, 2], ["1", "2"])

    assert result.status == "needs_confirmation"
    assert "key_type_family_mismatch" in result.risks


@pytest.mark.parametrize(
    ("left_values", "right_values"),
    [
        (
            pd.Series(pd.Categorical(pd.to_timedelta(["1 day", "2 days"]))),
            pd.Series(pd.to_timedelta(["1 day", "2 days"])),
        ),
        (pd.Series(pd.Categorical([1, 2])), pd.Series([1, 2], dtype="Int64")),
        (pd.Series(pd.Categorical(["a", "b"])), pd.Series(["a", "b"], dtype="string")),
        (
            pd.Series(pd.Categorical(pd.date_range("2024-01-01", periods=2, tz="UTC"))),
            pd.Series(pd.date_range("2023-12-31 19:00", periods=2, tz="US/Eastern")),
        ),
        (
            pd.Series(pd.Categorical(pd.period_range("2024-01", periods=2, freq="M"))),
            pd.Series(pd.period_range("2024-01", periods=2, freq="M")),
        ),
        (
            pd.Series(pd.Categorical(pd.arrays.IntervalArray.from_breaks([0, 1, 2]))),
            pd.Series(pd.arrays.IntervalArray.from_breaks([0.0, 1.0, 2.0])),
        ),
    ],
    ids=[
        "categorical-timedelta",
        "categorical-nullable-integer",
        "categorical-nullable-string",
        "timezone-aware-datetime",
        "period",
        "interval",
    ],
)
def test_equivalent_extension_dtype_families_are_compatible(left_values, right_values):
    result = validate_relationship(
        pd.DataFrame({"id": left_values}),
        pd.DataFrame({"id": right_values}),
        left_key="id",
        right_key="id",
    )

    assert "key_type_family_mismatch" not in result.risks
    assert result.status == "validated"


def test_low_coverage_threshold_is_inclusive_at_boundary():
    at_boundary = _validate([1, 2], [1, 3], min_row_coverage=0.5)
    below_boundary = _validate([1, 2, 3], [1, 4, 5], min_row_coverage=0.5)

    assert at_boundary.status == "validated"
    assert "low_left_row_coverage" not in at_boundary.risks
    assert below_boundary.status == "needs_confirmation"
    assert "low_left_row_coverage" in below_boundary.risks


def test_null_and_multiplier_thresholds_are_inclusive_at_boundary():
    null_boundary = _validate([1, None], [1, 2], max_null_rate=0.5, min_row_coverage=0.0)
    multiplier_boundary = _validate(
        [1, 1],
        [1, 1],
        max_join_multiplier=2.0,
        min_row_coverage=0.0,
    )

    assert "high_left_null_rate" not in null_boundary.risks
    assert "excessive_row_multiplier" not in multiplier_boundary.risks
    assert DEFAULT_MIN_ROW_COVERAGE < 2 / 3
    assert DEFAULT_MAX_NULL_RATE == 0.2
    assert DEFAULT_MAX_JOIN_MULTIPLIER == 1.0


def test_identifier_internal_whitespace_is_preserved():
    left = pd.DataFrame({"customer  id": [1, 2]})
    right = pd.DataFrame({"account  id": [1, 2]})

    result = validate_relationship(
        left,
        right,
        left_key=" customer  id ",
        right_key=" account  id ",
    )

    assert result.status == "validated"
    assert result.normalized_left_key == ("customer  id",)
    assert result.normalized_right_key == ("account  id",)


def test_result_is_immutable_deterministic_and_does_not_mutate_inputs():
    left = pd.DataFrame({"id": [2, 1, None], "value": ["b", "a", "n"]})
    right = pd.DataFrame({"id": [1, 2, 3]})
    left_before = left.copy(deep=True)
    right_before = right.copy(deep=True)

    first = validate_relationship(left, right, left_key="id", right_key="id")
    second = validate_relationship(left, right, left_key="id", right_key="id")

    assert first == second
    assert first.to_record() == second.to_record()
    assert first.relationship_id == second.relationship_id
    pd.testing.assert_frame_equal(left, left_before)
    pd.testing.assert_frame_equal(right, right_before)
    with pytest.raises(FrozenInstanceError):
        first.status = "validated"
    mutable_record = first.to_record()
    mutable_record["risks"].append("changed")
    assert "changed" not in first.risks


def test_meaningful_changes_change_relationship_identity():
    base = _validate([1, 2, 3], [1, 2, 4])
    changed_metric = _validate([1, 2, 3], [1, 4, 5])
    changed_key = validate_relationship(
        pd.DataFrame({"id": [1], "other": [1]}),
        pd.DataFrame({"id": [1], "other": [1]}),
        left_key="other",
        right_key="other",
    )

    assert base.relationship_id != changed_metric.relationship_id
    assert base.relationship_id != changed_key.relationship_id


def test_source_fingerprints_distinguish_equal_aggregate_outcomes_without_exposing_values():
    secret = "customer-secret-1"
    first = _validate([secret, "customer-secret-2", "customer-secret-3"], [secret, "customer-secret-2", "x"])
    second = _validate(["account-10", "account-20", "account-30"], ["account-10", "account-20", "y"])

    assert first.status == second.status == "validated"
    assert first.left_row_coverage == second.left_row_coverage
    assert first.relationship_id != second.relationship_id
    assert first.left_source_key_fingerprint != second.left_source_key_fingerprint
    assert secret not in json.dumps(first.to_record())


def test_source_fingerprint_is_stable_for_missing_timestamp_and_extension_values():
    left = pd.DataFrame(
        {
            "tenant": pd.Series(["a", "private-null-row"], dtype="string"),
            "id": pd.Series([1, pd.NA], dtype="Int64"),
            "occurred_at": pd.Series(
                [pd.Timestamp("2024-01-01", tz="UTC"), pd.NaT],
                dtype="datetime64[ns, UTC]",
            ),
        }
    )
    right = left.copy(deep=True)
    keys = ["tenant", "id", "occurred_at"]

    first = validate_relationship(left, right, left_key=keys, right_key=keys)
    repeated = validate_relationship(left.copy(deep=True), right.copy(deep=True), left_key=keys, right_key=keys)
    changed = left.copy(deep=True)
    changed.loc[1, "tenant"] = "different-null-row"
    changed_result = validate_relationship(changed, right, left_key=keys, right_key=keys)

    assert first.relationship_id == repeated.relationship_id
    assert first.left_source_key_fingerprint == repeated.left_source_key_fingerprint
    assert first.left_source_key_fingerprint != changed_result.left_source_key_fingerprint
    assert "private-null-row" not in json.dumps(first.to_record())


@pytest.mark.parametrize(
    ("threshold", "changed_value"),
    [
        ("min_row_coverage", 0.6),
        ("max_null_rate", 0.3),
        ("max_join_multiplier", 1.5),
    ],
)
def test_every_threshold_changes_identity_even_when_outcome_is_unchanged(threshold, changed_value):
    base = _validate([1, 2, 3], [1, 2, 4])
    changed = _validate([1, 2, 3], [1, 2, 4], **{threshold: changed_value})

    assert base.status == changed.status == "validated"
    assert base.risks == changed.risks
    assert base.relationship_id != changed.relationship_id
    assert getattr(changed, threshold) == changed_value


@pytest.mark.parametrize("value", [0, 0.0, np.int64(0), Decimal("0")])
def test_equivalent_numeric_threshold_inputs_have_one_canonical_identity(value):
    result = _validate([1, 2], [1, 2], min_row_coverage=value)
    canonical = _validate([1, 2], [1, 2], min_row_coverage=0.0)

    assert result.status == "validated"
    assert result.min_row_coverage == 0.0
    assert type(result.min_row_coverage) is float
    assert result.relationship_id == canonical.relationship_id


@pytest.mark.parametrize("threshold", ["min_row_coverage", "max_null_rate", "max_join_multiplier"])
@pytest.mark.parametrize("signed_zero", [-0.0, np.float64(-0.0), Decimal("-0")])
def test_signed_zero_thresholds_use_positive_zero_records_and_identity(threshold, signed_zero):
    frame = pd.DataFrame({"id": [1, 2]})
    signed = validate_relationship(
        frame,
        frame,
        left_key="id",
        right_key="id",
        **{threshold: signed_zero},
    )
    positive = validate_relationship(
        frame,
        frame,
        left_key="id",
        right_key="id",
        **{threshold: 0.0},
    )

    record_value = signed.to_record()[threshold]
    assert type(record_value) is float
    assert record_value == 0.0
    assert math.copysign(1.0, record_value) == 1.0
    assert signed.relationship_id == positive.relationship_id


@pytest.mark.parametrize(
    ("threshold", "value"),
    [
        ("min_row_coverage", Decimal("0.5")),
        ("max_null_rate", np.float64(0.25)),
        ("max_join_multiplier", Decimal("1.5")),
    ],
)
def test_supported_numeric_threshold_scalars_are_normalized_to_native_float(threshold, value):
    result = _validate([1, 2], [1, 2], **{threshold: value})

    assert result.status == "validated"
    assert type(getattr(result, threshold)) is float
    json.dumps(result.to_record(), allow_nan=False)


@pytest.mark.parametrize(
    ("value", "expected_error"),
    [
        (True, "invalid_min_row_coverage"),
        (object(), "invalid_min_row_coverage"),
        ("0.5", "invalid_min_row_coverage"),
        (float("nan"), "invalid_min_row_coverage"),
        (float("inf"), "invalid_min_row_coverage"),
        (float("-inf"), "invalid_min_row_coverage"),
        (-0.1, "invalid_min_row_coverage"),
        (1.1, "invalid_min_row_coverage"),
    ],
    ids=["bool", "object", "string", "nan", "positive-inf", "negative-inf", "below-domain", "above-domain"],
)
def test_invalid_threshold_inputs_are_structured_stable_and_strict_json_safe(value, expected_error):
    result = _validate([1, 2], [1, 2], min_row_coverage=value)

    assert result.status == "rejected"
    assert result.risks == ("invalid_thresholds",)
    assert result.configuration_errors == (expected_error,)
    assert result.min_row_coverage is None
    json.dumps(result.to_record(), allow_nan=False)


def test_invalid_threshold_object_uses_stable_sentinel_instead_of_object_identity():
    first = _validate([1, 2], [1, 2], min_row_coverage=object())
    second = _validate([1, 2], [1, 2], min_row_coverage=object())

    assert first.relationship_id == second.relationship_id
    assert first.to_record() == second.to_record()


@pytest.mark.parametrize("threshold", ["min_row_coverage", "max_null_rate", "max_join_multiplier"])
def test_boolean_is_rejected_for_every_threshold_field(threshold):
    result = _validate([1, 2], [1, 2], **{threshold: True})

    assert result.status == "rejected"
    assert result.configuration_errors == (f"invalid_{threshold}",)
    assert getattr(result, threshold) is None
    json.dumps(result.to_record(), allow_nan=False)


@pytest.mark.parametrize(
    ("side", "value"),
    [
        ("left", object()),
        ("left", ["orders"]),
        ("left", {"dataset": "orders"}),
        ("right", object()),
        ("right", ["customers"]),
        ("right", {"dataset": "customers"}),
    ],
    ids=["left-object", "left-list", "left-dict", "right-object", "right-list", "right-dict"],
)
def test_invalid_dataset_identifiers_are_rejected_and_strict_json_safe(side, value):
    kwargs = {f"{side}_dataset": value}
    result = validate_relationship(
        pd.DataFrame({"id": [1]}),
        pd.DataFrame({"id": [1]}),
        left_key="id",
        right_key="id",
        **kwargs,
    )

    assert result.status == "rejected"
    assert result.risks == (f"invalid_{side}_dataset",)
    assert result.configuration_errors == (f"invalid_{side}_dataset",)
    assert getattr(result, f"{side}_dataset") is None
    json.dumps(result.to_record(), allow_nan=False)


@pytest.mark.parametrize("side", ["left", "right"])
def test_whitespace_only_dataset_identifier_is_rejected_and_strict_json_safe(side):
    kwargs = {f"{side}_dataset": "  \t\r\n "}
    result = validate_relationship(
        pd.DataFrame({"id": [1]}),
        pd.DataFrame({"id": [1]}),
        left_key="id",
        right_key="id",
        **kwargs,
    )

    assert result.status == "rejected"
    assert result.risks == (f"invalid_{side}_dataset",)
    assert result.configuration_errors == (f"invalid_{side}_dataset",)
    assert getattr(result, f"{side}_dataset") is None
    json.dumps(result.to_record(), allow_nan=False)


def test_none_dataset_identifiers_remain_none_and_match_omitted_identity():
    frame = pd.DataFrame({"id": [1, 2]})
    explicit_none = validate_relationship(
        frame,
        frame,
        left_key="id",
        right_key="id",
        left_dataset=None,
        right_dataset=None,
    )
    omitted = validate_relationship(frame, frame, left_key="id", right_key="id")

    assert explicit_none.status == "validated"
    assert explicit_none.left_dataset is explicit_none.right_dataset is None
    assert explicit_none.relationship_id == omitted.relationship_id


def test_dataset_identifiers_are_trimmed_before_identity_while_internal_whitespace_is_preserved():
    frame = pd.DataFrame({"id": [1, 2]})
    clean = validate_relationship(
        frame,
        frame,
        left_key="id",
        right_key="id",
        left_dataset="sales history",
    )
    padded = validate_relationship(
        frame,
        frame,
        left_key="id",
        right_key="id",
        left_dataset="  sales history  ",
    )
    internal = validate_relationship(
        frame,
        frame,
        left_key="id",
        right_key="id",
        left_dataset="sales  history",
    )

    assert padded.left_dataset == "sales history"
    assert padded.relationship_id == clean.relationship_id
    assert internal.left_dataset == "sales  history"
    assert internal.relationship_id != clean.relationship_id


@pytest.mark.parametrize(
    "key_value",
    [UUID("12345678-1234-5678-1234-567812345678"), Decimal("123.4500")],
    ids=["uuid", "decimal"],
)
def test_common_typed_scalar_keys_fingerprint_deterministically(key_value):
    left = pd.DataFrame({"id": [key_value]})
    right = pd.DataFrame({"id": [key_value]})

    first = validate_relationship(left, right, left_key="id", right_key="id")
    repeated = validate_relationship(left.copy(deep=True), right.copy(deep=True), left_key="id", right_key="id")

    assert first.status == "validated"
    assert first.relationship_id == repeated.relationship_id
    assert str(key_value) not in json.dumps(first.to_record())


def test_dataset_identifiers_bind_identity_and_are_exposed_for_audit():
    frames = (pd.DataFrame({"id": [1, 2]}), pd.DataFrame({"id": [1, 2]}))
    first = validate_relationship(
        *frames,
        left_key="id",
        right_key="id",
        left_dataset="orders",
        right_dataset="customers",
    )
    changed = validate_relationship(
        *frames,
        left_key="id",
        right_key="id",
        left_dataset="archived_orders",
        right_dataset="customers",
    )

    assert first.relationship_id != changed.relationship_id
    assert first.to_record()["left_dataset"] == "orders"
    assert first.to_record()["right_dataset"] == "customers"


def test_row_and_distinct_coverage_use_their_documented_denominators():
    result = _validate([1] * 8 + [2, 3], [1], min_row_coverage=0.0, max_join_multiplier=10.0)

    assert result.left_row_coverage == pytest.approx(0.8)
    assert result.left_distinct_key_coverage == pytest.approx(1 / 3)


def test_composite_keys_with_nulls_and_duplicates_preserve_multiplicity_semantics():
    left = pd.DataFrame({"tenant": ["a", "a", "a", "b"], "id": [1, 1, None, 2]})
    right = pd.DataFrame({"tenant": ["a", "b", "b"], "id": [1, 2, 2]})

    result = validate_relationship(
        left,
        right,
        left_key=["tenant", "id"],
        right_key=["tenant", "id"],
    )

    assert result.cardinality == "many_to_many"
    assert result.left_non_null_key_rows == 3
    assert result.left_null_rate == 0.25
    assert result.expected_inner_join_rows == 4
    assert result.status == "rejected"


def test_zero_shared_keys_reports_zero_coverage_and_requires_confirmation():
    result = _validate([1, 2], [3, 4])

    assert result.expected_inner_join_rows == 0
    assert result.left_row_coverage == result.right_row_coverage == 0.0
    assert result.left_distinct_key_coverage == result.right_distinct_key_coverage == 0.0
    assert result.status == "needs_confirmation"


def test_many_to_many_rejection_precedes_above_threshold_multiplier_confirmation():
    result = _validate([1, 1], [1, 1], max_join_multiplier=1.0)

    assert result.row_multiplier == 2.0
    assert "excessive_row_multiplier" in result.risks
    assert result.status == "rejected"


def test_canonical_record_is_accepted_by_bundle_validator():
    relationship = _validate([1, 2, 3], [1, 2, 4]).to_record()

    bundle = build_data_understanding_bundle(
        datasets=[_dataset("left"), _dataset("right")],
        quality_findings=[],
        relationship_candidates=[relationship],
    )

    assert bundle["relationship_candidates"][0]["status"] == "validated"
    assert bundle["relationship_candidates"][0]["relationship_id"] == relationship["relationship_id"]


def test_bundle_preserves_internal_whitespace_in_canonical_normalized_keys():
    relationship = validate_relationship(
        pd.DataFrame({"customer  id": [1]}),
        pd.DataFrame({"account  id": [1]}),
        left_key="customer  id",
        right_key="account  id",
    ).to_record()

    bundle = build_data_understanding_bundle(
        datasets=[_dataset("left"), _dataset("right")],
        quality_findings=[],
        relationship_candidates=[relationship],
    )

    record = bundle["relationship_candidates"][0]
    assert record["normalized_left_key"] == ["customer  id"]
    assert record["normalized_right_key"] == ["account  id"]


def test_builder_does_not_promote_candidate_status():
    candidate = {"id": "candidate", "status": "proposed", "left_key": "id", "right_key": "id"}
    original = deepcopy(candidate)

    bundle = build_data_understanding_bundle(
        datasets=[_dataset("left"), _dataset("right")],
        quality_findings=[],
        relationship_candidates=[candidate],
    )

    assert bundle["relationship_candidates"][0]["status"] == "proposed"
    assert candidate == original
