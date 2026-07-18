import json

import pandas as pd

from data_agent.agent.data_lineage import frame_fingerprint
from data_agent.session.workspace import Workspace


def test_in_place_feature_derivation_promotes_copy_and_preserves_raw(monkeypatch):
    from data_agent.tools import derive_features

    store = Workspace()
    raw = pd.DataFrame({"revenue": [10.0, 20.0], "orders": [2.0, 4.0]})
    raw_info = store.register_raw_snapshot("sales", raw, frame_fingerprint(raw))
    first = store.promote_analysis_copy(
        "sales", raw, raw_info["dataset_id"], {"id": "prepare"}
    )
    monkeypatch.setattr(derive_features, "workspace", store)

    result = json.loads(
        derive_features.derive_features(
            "sales",
            feature_type="ratio_features",
            params='{"numerator": "revenue", "denominator": "orders"}',
        )
    )
    second = store.get_active_version_info("sales")

    assert "error" not in result
    assert second["version"] == 2
    assert second["dataset_id"] != first["dataset_id"]
    assert "revenue_div_orders" in store.get("sales").columns
    assert "revenue_div_orders" not in store.get_dataset_version(first["dataset_id"]).columns
    assert "revenue_div_orders" not in store.get_raw_snapshot(raw_info["dataset_id"]).columns


def test_time_features_keep_original_source_column_values(monkeypatch):
    from data_agent.tools import derive_features

    store = Workspace()
    raw = pd.DataFrame({"date": ["2026-01-01", "2026-01-02"]})
    raw_info = store.register_raw_snapshot("events", raw, frame_fingerprint(raw))
    store.promote_analysis_copy(
        "events", raw, raw_info["dataset_id"], {"id": "prepare"}
    )
    monkeypatch.setattr(derive_features, "workspace", store)

    result = json.loads(
        derive_features.derive_features(
            "events", feature_type="time_features", columns="date"
        )
    )

    assert "error" not in result
    assert store.get("events")["date"].tolist() == raw["date"].tolist()
    assert store.get("events")["date_year"].tolist() == [2026, 2026]
