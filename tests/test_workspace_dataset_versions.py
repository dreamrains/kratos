from pathlib import Path

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from data_agent.agent.data_lineage import frame_fingerprint
from data_agent.session.workspace import Workspace


def test_raw_snapshot_is_hidden_immutable_and_distinct_from_active_copy():
    store = Workspace()
    raw = pd.DataFrame({"rate": ["10%", "20%"]})
    raw_info = store.register_raw_snapshot("orders", raw, frame_fingerprint(raw))
    prepared = pd.DataFrame({"rate": [0.1, 0.2]})
    active_info = store.promote_analysis_copy(
        "orders",
        prepared,
        raw_info["dataset_id"],
        {
            "id": "transform_prepare",
            "parent_dataset_id": raw_info["dataset_id"],
            "information_loss": False,
        },
    )

    raw.iloc[0, 0] = "99%"
    prepared.iloc[0, 0] = 9.9

    listed = store.list_datasets()
    assert set(listed) == {"orders"}
    assert listed["orders"]["dataset_id"] == active_info["dataset_id"]
    assert store.get_metadata("orders", "_raw_dataset_id") == raw_info["dataset_id"]
    assert store.get_metadata("orders", "_active_dataset_id") == active_info["dataset_id"]
    assert (
        store.get_metadata("orders", "_transformation_record")["derived_dataset_id"]
        == active_info["dataset_id"]
    )
    assert_frame_equal(
        store.get_raw_snapshot(raw_info["dataset_id"]),
        pd.DataFrame({"rate": ["10%", "20%"]}),
    )
    assert_frame_equal(store.get("orders"), pd.DataFrame({"rate": [0.1, 0.2]}))


def test_raw_and_version_accessors_return_defensive_copies():
    store = Workspace()
    raw = pd.DataFrame({"x": [1, 2]})
    raw_info = store.register_raw_snapshot("orders", raw, frame_fingerprint(raw))
    active_info = store.promote_analysis_copy(
        "orders", raw, raw_info["dataset_id"], {"id": "prepare"}
    )

    raw_copy = store.get_raw_snapshot(raw_info["dataset_id"])
    version_copy = store.get_dataset_version(active_info["dataset_id"])
    raw_copy.loc[0, "x"] = 100
    version_copy.loc[0, "x"] = 200

    assert store.get_raw_snapshot(raw_info["dataset_id"]).loc[0, "x"] == 1
    assert store.get_dataset_version(active_info["dataset_id"]).loc[0, "x"] == 1


def test_raw_registration_validates_identity_and_is_idempotent():
    store = Workspace()
    raw = pd.DataFrame({"x": [1, 2]})
    fingerprint = frame_fingerprint(raw)

    first = store.register_raw_snapshot("orders", raw, fingerprint)
    repeated = store.register_raw_snapshot("orders", raw.copy(), fingerprint)

    assert repeated == first
    with pytest.raises(ValueError, match="source_fingerprint"):
        store.register_raw_snapshot(
            "orders",
            pd.DataFrame({"x": [9, 9]}),
            fingerprint,
        )
    assert_frame_equal(store.get_raw_snapshot(first["dataset_id"]), raw)


def test_promoting_second_copy_preserves_first_version():
    store = Workspace()
    raw = pd.DataFrame({"x": [1, 2, None]})
    raw_info = store.register_raw_snapshot("orders", raw, frame_fingerprint(raw))
    first = store.promote_analysis_copy(
        "orders", raw.copy(), raw_info["dataset_id"], {"id": "prepare"}
    )
    second_frame = raw.fillna({"x": 0})
    second = store.promote_analysis_copy(
        "orders", second_frame, raw_info["dataset_id"], {"id": "fill"}
    )

    assert first["dataset_id"] != second["dataset_id"]
    assert store.get_dataset_version(first["dataset_id"])["x"].isna().sum() == 1
    assert store.get("orders")["x"].isna().sum() == 0
    assert [item["version"] for item in store.list_dataset_versions("orders")] == [1, 2]


def test_legacy_add_cannot_overwrite_versioned_logical_dataset():
    store = Workspace()
    raw = pd.DataFrame({"x": [1, 2]})
    raw_info = store.register_raw_snapshot("orders", raw, frame_fingerprint(raw))
    active_info = store.promote_analysis_copy(
        "orders", raw, raw_info["dataset_id"], {"id": "prepare"}
    )

    result = store.add("orders", pd.DataFrame({"x": [999]}))

    assert result == "Error: versioned_dataset_requires_promotion"
    assert store.get_active_version_info("orders") == active_info
    assert_frame_equal(store.get("orders"), raw)
    assert_frame_equal(store.get_raw_snapshot(raw_info["dataset_id"]), raw)


def test_remove_deletes_raw_and_all_versions_for_logical_dataset():
    store = Workspace()
    raw = pd.DataFrame({"x": [1]})
    raw_info = store.register_raw_snapshot("orders", raw, frame_fingerprint(raw))
    active_info = store.promote_analysis_copy(
        "orders", raw, raw_info["dataset_id"], {"id": "prepare"}
    )

    assert store.remove("orders") == "数据集 'orders' 已删除"
    assert store.get_raw_snapshot(raw_info["dataset_id"]) is None
    assert store.get_dataset_version(active_info["dataset_id"]) is None
    assert store.list_dataset_versions("orders") == []


def test_persist_dataset_writes_distinct_raw_and_active_backups(tmp_path, monkeypatch):
    import data_agent.session.history as history

    monkeypatch.setattr(history, "_session_dir", lambda _session_id: tmp_path)
    store = Workspace()
    raw = pd.DataFrame({"rate": ["10%", "20%"]})
    raw_info = store.register_raw_snapshot("orders", raw, frame_fingerprint(raw))
    store.promote_analysis_copy(
        "orders",
        pd.DataFrame({"rate": [0.1, 0.2]}),
        raw_info["dataset_id"],
        {"id": "prepare"},
    )

    active_path = Path(store.persist_dataset("session", "orders"))
    raw_candidates = list((tmp_path / "data").glob("orders__raw.*"))

    assert active_path.exists()
    assert len(raw_candidates) == 1
    if raw_candidates[0].suffix == ".parquet":
        restored_raw = pd.read_parquet(raw_candidates[0])
    else:
        restored_raw = pd.read_pickle(raw_candidates[0])
    assert_frame_equal(restored_raw, raw)


def test_parquet_persistence_preserves_nonconsecutive_index(tmp_path, monkeypatch):
    import data_agent.session.history as history

    monkeypatch.setattr(history, "_session_dir", lambda _session_id: tmp_path)
    parquet_index_arguments = []

    def fake_to_parquet(frame, path, *, index):
        parquet_index_arguments.append(index)
        frame.to_pickle(path)

    monkeypatch.setattr(pd.DataFrame, "to_parquet", fake_to_parquet)
    store = Workspace()
    raw = pd.DataFrame({"x": [1, 2, 3]}, index=[10, 20, 40])
    raw_info = store.register_raw_snapshot("orders", raw, frame_fingerprint(raw))
    active = raw.drop(index=20)
    active_info = store.promote_analysis_copy(
        "orders", active, raw_info["dataset_id"], {"id": "drop_row"}
    )

    path = store.persist_dataset("session", "orders")
    restored = pd.read_pickle(path)

    assert parquet_index_arguments == [True, True]
    assert_frame_equal(restored, active)
    assert frame_fingerprint(restored) == active_info["frame_fingerprint"]
