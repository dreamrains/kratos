import json

import pandas as pd

from data_agent.agent.data_lineage import frame_fingerprint
from data_agent.session.workspace import Workspace


def _versioned_store(frame=None):
    store = Workspace()
    raw = frame if frame is not None else pd.DataFrame(
        {"x": [1.0, None, 100.0], "id": [1, 2, 3]}
    )
    raw_info = store.register_raw_snapshot("orders", raw, frame_fingerprint(raw))
    active_info = store.promote_analysis_copy(
        "orders", raw.copy(), raw_info["dataset_id"], {"id": "prepare"}
    )
    return store, raw_info, active_info


def test_unconfirmed_imputation_does_not_promote_candidate(monkeypatch):
    from data_agent.tools import data_clean

    store, raw_info, active_info = _versioned_store()
    monkeypatch.setattr(data_clean, "workspace", store)

    result = json.loads(data_clean.clean_data("orders", missing_strategy="fill_median"))
    repeated = json.loads(data_clean.clean_data("orders", missing_strategy="fill_median"))

    assert result["status"] == "confirmation_required"
    assert result["transformation_record"]["id"] == repeated["transformation_record"]["id"]
    assert store.get_active_version_info("orders")["dataset_id"] == active_info["dataset_id"]
    assert store.get("orders")["x"].isna().sum() == 1
    assert store.get_raw_snapshot(raw_info["dataset_id"])["x"].isna().sum() == 1


def test_confirmed_imputation_promotes_new_version_and_preserves_parent(monkeypatch):
    from data_agent.tools import data_clean

    store, _, first = _versioned_store()
    monkeypatch.setattr(data_clean, "workspace", store)

    result = json.loads(
        data_clean.clean_data("orders", missing_strategy="fill_median", confirmed=True)
    )
    second = store.get_active_version_info("orders")

    assert result["status"] == "applied"
    assert result["parent_dataset_id"] == first["dataset_id"]
    assert second["dataset_id"] != first["dataset_id"]
    assert store.get_dataset_version(first["dataset_id"])["x"].isna().sum() == 1
    assert store.get("orders")["x"].isna().sum() == 0
    metadata = store.get_metadata("orders")
    assert metadata["_active_dataset_id"] == second["dataset_id"]
    assert metadata["_raw_dataset_id"] == second["raw_dataset_id"]
    assert metadata["_transformation_record"] == second["transformation_record"]


def test_legacy_dataset_is_initialized_before_unconfirmed_cleaning(monkeypatch):
    from data_agent.tools import data_clean

    store = Workspace()
    legacy = pd.DataFrame({"x": [1.0, None, 3.0]})
    store.add("orders", legacy)
    monkeypatch.setattr(data_clean, "workspace", store)

    result = json.loads(data_clean.clean_data("orders", missing_strategy="fill_mean"))
    active = store.get_active_version_info("orders")

    assert result["status"] == "confirmation_required"
    assert active["version"] == 1
    assert len(store.list_dataset_versions("orders")) == 1
    assert store.get("orders")["x"].isna().sum() == 1
    assert store.get_raw_snapshot(active["raw_dataset_id"])["x"].isna().sum() == 1


def test_high_confidence_lossless_type_conversion_promotes_without_confirmation(monkeypatch):
    from data_agent.tools import data_clean

    store, _, first = _versioned_store(pd.DataFrame({"rate": ["10%", "20%"]}))
    monkeypatch.setattr(data_clean, "workspace", store)

    result = json.loads(
        data_clean.apply_type_conversion(
            "orders", column="rate", target_type="percentage_to_float"
        )
    )

    assert result["status"] == "applied"
    assert result["parent_dataset_id"] == first["dataset_id"]
    assert store.get("orders")["rate"].tolist() == [0.1, 0.2]
    assert store.get_dataset_version(first["dataset_id"])["rate"].tolist() == ["10%", "20%"]


def test_unit_bearing_conversion_requires_confirmation_then_promotes(monkeypatch):
    from data_agent.tools import data_clean

    store, raw_info, first = _versioned_store(
        pd.DataFrame({"amount": ["10K", "20K", "30K"]})
    )
    monkeypatch.setattr(data_clean, "workspace", store)

    pending = json.loads(
        data_clean.apply_type_conversion(
            "orders", column="amount", target_type="numeric_with_suffix"
        )
    )

    assert pending["status"] == "confirmation_required"
    assert store.get_active_version_info("orders")["dataset_id"] == first["dataset_id"]
    assert store.get("orders")["amount"].tolist() == ["10K", "20K", "30K"]
    assert store.get_raw_snapshot(raw_info["dataset_id"])["amount"].tolist() == ["10K", "20K", "30K"]

    applied = json.loads(
        data_clean.apply_type_conversion(
            "orders",
            column="amount",
            target_type="numeric_with_suffix",
            confirmed=True,
        )
    )

    assert applied["status"] == "applied"
    assert applied["parent_dataset_id"] == first["dataset_id"]
    assert store.get("orders")["amount"].tolist() == [10_000.0, 20_000.0, 30_000.0]
    assert store.get_dataset_version(first["dataset_id"])["amount"].tolist() == ["10K", "20K", "30K"]


def test_cardinality_collapse_and_auto_conversion_are_confirmation_gated(monkeypatch):
    from data_agent.tools import data_clean

    store, _, first = _versioned_store(pd.DataFrame({"code": ["1", "01", "2"]}))
    monkeypatch.setattr(data_clean, "workspace", store)

    collapsed = json.loads(
        data_clean.apply_type_conversion("orders", column="code", target_type="numeric")
    )
    automatic = json.loads(data_clean.apply_type_conversion("orders", auto=True))

    assert collapsed["status"] == "confirmation_required"
    assert collapsed["transformation_record"]["information_loss"] is True
    assert automatic["status"] == "confirmation_required"
    assert store.get_active_version_info("orders")["dataset_id"] == first["dataset_id"]
    assert store.get("orders")["code"].tolist() == ["1", "01", "2"]


def test_category_conversion_is_not_a_silent_noop(monkeypatch):
    from data_agent.tools import data_clean

    store, _, first = _versioned_store(pd.DataFrame({"segment": [1, 1, 2]}))
    monkeypatch.setattr(data_clean, "workspace", store)

    pending = json.loads(
        data_clean.apply_type_conversion(
            "orders", column="segment", target_type="category"
        )
    )
    applied = json.loads(
        data_clean.apply_type_conversion(
            "orders", column="segment", target_type="category", confirmed=True
        )
    )

    assert pending["status"] == "confirmation_required"
    assert pending["converted"]["new_dtype"] == "category"
    assert applied["status"] == "applied"
    assert applied["parent_dataset_id"] == first["dataset_id"]
    assert isinstance(store.get("orders")["segment"].dtype, pd.CategoricalDtype)


def test_outlier_mark_records_audit_without_creating_empty_version(monkeypatch):
    from data_agent.tools import data_clean

    store, _, first = _versioned_store(pd.DataFrame({"x": [1, 2, 3, 4, 100]}))
    monkeypatch.setattr(data_clean, "workspace", store)

    result = json.loads(data_clean.clean_data("orders", outlier_strategy="mark"))

    assert result["status"] == "applied"
    assert result["dataset_id"] == first["dataset_id"]
    assert result["actions"][0]["action"] == "outlier_mark"
    assert len(store.list_dataset_versions("orders")) == 1


def test_confirmation_flags_are_boolean_in_registered_tool_schemas():
    from data_agent.tools import data_clean  # noqa: F401
    from data_agent.tools.registry import registry

    definitions = {item["name"]: item for item in registry.all_definitions()}

    clean_properties = definitions["clean_data"]["parameters"]["properties"]
    conversion_properties = definitions["apply_type_conversion"]["parameters"]["properties"]
    assert clean_properties["confirmed"]["type"] == "boolean"
    assert conversion_properties["confirmed"]["type"] == "boolean"
    assert conversion_properties["auto"]["type"] == "boolean"
