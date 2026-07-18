import json

import pandas as pd
import pytest

from data_agent.agent.data_lineage import frame_fingerprint
from data_agent.session.workspace import Workspace


def _store():
    store = Workspace()
    raw = pd.DataFrame({"amount": [1.0, None, 3.0], "segment": ["a", "a", "b"]})
    raw_info = store.register_raw_snapshot("orders", raw, frame_fingerprint(raw))
    active = store.promote_analysis_copy("orders", raw.copy(), raw_info["dataset_id"], {"id": "prepare"})
    return store, active


def test_material_cleaning_proposal_is_deterministic_and_has_bound_versions(monkeypatch, tmp_path):
    from data_agent.tools import data_clean

    store, active = _store()
    monkeypatch.setattr(data_clean, "workspace", store)
    monkeypatch.setattr(data_clean, "_proposal_sessions_root", lambda: tmp_path)
    monkeypatch.setattr(data_clean, "_data_clean_session_id", lambda _value="": "s1")

    first = json.loads(data_clean.clean_data("orders", missing_strategy="fill_median"))
    second = json.loads(data_clean.clean_data("orders", missing_strategy="fill_median"))

    assert first["status"] == "confirmation_required"
    assert first["proposal_ref"] == second["proposal_ref"]
    assert first["proposal_ref"]["data_version"] == f"dataset:{active['dataset_id']}:{active['source_fingerprint']}"
    assert first["proposal_ref"]["spec_version"].startswith("transformation:")
    assert first["proposal_ref"]["candidate_fingerprint"].startswith("sha256:")
    assert "transformation_record" not in first
    assert store.get_active_version_info("orders")["dataset_id"] == active["dataset_id"]


def test_confirmation_approval_applies_once_and_reject_or_skip_do_not_mutate(monkeypatch, tmp_path):
    from data_agent.agent.confirmation.runtime import build_action_registry
    from data_agent.agent.confirmation.service import ConfirmationService
    from data_agent.tools import data_clean

    store, active = _store()
    monkeypatch.setattr(data_clean, "workspace", store)
    monkeypatch.setattr(data_clean, "_proposal_sessions_root", lambda: tmp_path)
    monkeypatch.setattr(data_clean, "_data_clean_session_id", lambda _value="": "s1")
    pending = json.loads(data_clean.clean_data("orders", missing_strategy="fill_median"))
    service = ConfirmationService(tmp_path, action_registry=build_action_registry())
    record = service.get("s1", pending["confirmation_id"])
    restarted_service = ConfirmationService(tmp_path, action_registry=build_action_registry())
    resolved = restarted_service.respond("s1", record.confirmation_id, "approve", record.version, "answer_1")

    applied = data_clean.apply_confirmed_transformation(resolved.confirmation_id, session_id="s1")
    repeated = data_clean.apply_confirmed_transformation(resolved.confirmation_id, session_id="s1")

    assert applied["status"] == "applied"
    assert repeated["status"] == "applied"
    assert repeated["dataset_id"] == applied["dataset_id"]
    assert store.get_active_version_info("orders")["dataset_id"] != active["dataset_id"]
    assert store.get_dataset_version(active["dataset_id"])["amount"].isna().sum() == 1

    next_frame = store.get("orders")
    next_frame.loc[0, "amount"] = None
    current = store.get_active_version_info("orders")
    store.promote_analysis_copy("orders", next_frame, current["raw_dataset_id"], {"id": "test_fixture"})
    rejected = json.loads(data_clean.clean_data("orders", missing_strategy="fill_median"))
    rejection = service.get("s1", rejected["confirmation_id"])
    service.respond("s1", rejection.confirmation_id, "reject", rejection.version, "answer_2")
    with pytest.raises(ValueError, match="not approved"):
        data_clean.apply_confirmed_transformation(rejection.confirmation_id, session_id="s1")
    rejected_active = store.get_active_version_info("orders")["dataset_id"]
    skipped = json.loads(data_clean.clean_data("orders", missing_strategy="fill_mean"))
    skipped_record = service.get("s1", skipped["confirmation_id"])
    service.skip("s1", skipped_record.confirmation_id, skipped_record.version, "skip_1")
    assert store.get_active_version_info("orders")["dataset_id"] == rejected_active


def test_approved_proposal_cannot_apply_after_active_version_changes(monkeypatch, tmp_path):
    from data_agent.agent.confirmation.runtime import build_action_registry
    from data_agent.agent.confirmation.service import ConfirmationService
    from data_agent.tools import data_clean

    store, active = _store()
    monkeypatch.setattr(data_clean, "workspace", store)
    monkeypatch.setattr(data_clean, "_proposal_sessions_root", lambda: tmp_path)
    monkeypatch.setattr(data_clean, "_data_clean_session_id", lambda _value="": "s1")
    pending = json.loads(data_clean.clean_data("orders", missing_strategy="fill_median"))
    service = ConfirmationService(tmp_path, action_registry=build_action_registry())
    record = service.get("s1", pending["confirmation_id"])
    service.respond("s1", record.confirmation_id, "approve", record.version, "answer_1")
    store.promote_analysis_copy("orders", store.get("orders"), active["raw_dataset_id"], {"id": "intervening"})

    with pytest.raises(ValueError, match="stale active dataset version"):
        data_clean.apply_confirmed_transformation(record.confirmation_id, session_id="s1")


def test_approved_proposal_rejects_a_recomputed_candidate_with_a_new_fingerprint(monkeypatch, tmp_path):
    from data_agent.agent.confirmation.runtime import build_action_registry
    from data_agent.agent.confirmation.service import ConfirmationService
    from data_agent.tools import data_clean

    store = Workspace()
    raw = pd.DataFrame({"amount": ["10K", "20K"]})
    raw_info = store.register_raw_snapshot("orders", raw, frame_fingerprint(raw))
    store.promote_analysis_copy("orders", raw.copy(), raw_info["dataset_id"], {"id": "prepare"})
    monkeypatch.setattr(data_clean, "workspace", store)
    monkeypatch.setattr(data_clean, "_proposal_sessions_root", lambda: tmp_path)
    monkeypatch.setattr(data_clean, "_data_clean_session_id", lambda _value="": "s1")
    pending = json.loads(
        data_clean.apply_type_conversion(
            "orders", column="amount", target_type="numeric_with_suffix"
        )
    )
    service = ConfirmationService(tmp_path, action_registry=build_action_registry())
    record = service.get("s1", pending["confirmation_id"])
    service.respond("s1", record.confirmation_id, "approve", record.version, "answer_1")
    monkeypatch.setattr(
        data_clean,
        "apply_conversion",
        lambda series, _target: pd.Series([999.0] * len(series), index=series.index),
    )

    with pytest.raises(ValueError, match="candidate fingerprint changed"):
        data_clean.apply_confirmed_transformation(record.confirmation_id, session_id="s1")
