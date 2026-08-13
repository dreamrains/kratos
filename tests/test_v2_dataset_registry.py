import pandas as pd
import pytest

from data_agent.v2.dataset import DatasetRegistry, DatasetRole


def test_raw_registration_is_immutable_and_returns_copies(tmp_path):
    registry = DatasetRegistry(tmp_path, "session_1")
    source = pd.DataFrame({"date": ["2026-01-01"], "sales": [100]})

    raw = registry.register_raw("sales", source, source_identity="upload:sales.csv")
    source.loc[0, "sales"] = 999
    first_read = registry.get_frame(raw.dataset_version_id)
    first_read.loc[0, "sales"] = 777

    assert registry.get_frame(raw.dataset_version_id).loc[0, "sales"] == 100
    assert raw.role is DatasetRole.RAW
    assert raw.parent_version_id == ""


def test_derived_version_records_parent_and_transform(tmp_path):
    registry = DatasetRegistry(tmp_path, "session_1")
    raw = registry.register_raw(
        "sales",
        pd.DataFrame({"date": ["2026-01-01"], "sales": [100]}),
        source_identity="upload:sales.csv",
    )
    parsed = pd.DataFrame({"date": pd.to_datetime(["2026-01-01"]), "sales": [100]})

    analysis = registry.derive(
        parent_version_id=raw.dataset_version_id,
        frame=parsed,
        role=DatasetRole.ANALYSIS,
        transform={"operation": "parse_datetime", "column": "date", "lossless": True},
    )

    assert analysis.parent_version_id == raw.dataset_version_id
    assert analysis.logical_dataset_id == "sales"
    assert analysis.transform["operation"] == "parse_datetime"
    assert not pd.api.types.is_datetime64_any_dtype(
        registry.get_frame(raw.dataset_version_id)["date"]
    )
    assert pd.api.types.is_datetime64_any_dtype(
        registry.get_frame(analysis.dataset_version_id)["date"]
    )


def test_same_version_is_idempotent_and_conflicting_id_cannot_be_overwritten(tmp_path):
    registry = DatasetRegistry(tmp_path, "session_1")
    frame = pd.DataFrame({"sales": [100]})

    first = registry.register_raw("sales", frame, source_identity="upload:sales.csv")
    second = registry.register_raw("sales", frame.copy(), source_identity="upload:sales.csv")

    assert second == first
    with pytest.raises(ValueError, match="raw source identity"):
        registry.register_raw("sales", frame, source_identity="upload:other.csv")


def test_registry_round_trip_preserves_versions(tmp_path):
    registry = DatasetRegistry(tmp_path, "session_1")
    raw = registry.register_raw(
        "sales",
        pd.DataFrame({"sales": [100, 200]}),
        source_identity="upload:sales.csv",
    )
    analysis = registry.derive(
        parent_version_id=raw.dataset_version_id,
        frame=pd.DataFrame({"sales": [100, 200], "valid": [True, True]}),
        role=DatasetRole.ANALYSIS,
        transform={"operation": "add_quality_flag"},
    )

    restored = DatasetRegistry(tmp_path, "session_1")

    assert [item.dataset_version_id for item in restored.list_versions("sales")] == [
        raw.dataset_version_id,
        analysis.dataset_version_id,
    ]
    pd.testing.assert_frame_equal(
        restored.get_frame(analysis.dataset_version_id),
        pd.DataFrame({"sales": [100, 200], "valid": [True, True]}),
    )


@pytest.mark.parametrize("invalid_id", ["..", "session:1", "session 1", "a/b", "a\\b"])
def test_registry_rejects_nonportable_session_ids(tmp_path, invalid_id):
    with pytest.raises(ValueError, match="session_id"):
        DatasetRegistry(tmp_path, invalid_id)
