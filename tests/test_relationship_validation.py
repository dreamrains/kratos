from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError

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


def test_type_family_mismatch_needs_confirmation():
    result = _validate([1, 2], ["1", "2"])

    assert result.status == "needs_confirmation"
    assert "key_type_family_mismatch" in result.risks


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
