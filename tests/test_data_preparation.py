import pandas as pd
from pandas.testing import assert_frame_equal

from data_agent.agent.data_lineage import frame_fingerprint
from data_agent.tools.data_clean import prepare_analysis_copy


def test_prepare_analysis_copy_never_mutates_raw_frame():
    raw = pd.DataFrame({"rate": ["10%", "20%"], "label": ["A", "B"]})
    before = raw.copy(deep=True)

    prepared, record, applied, proposals = prepare_analysis_copy(
        raw,
        logical_name="orders",
        raw_dataset_id="raw_orders",
        source_fingerprint=frame_fingerprint(raw),
    )

    assert_frame_equal(raw, before)
    assert prepared is not raw
    assert prepared["rate"].tolist() == [0.1, 0.2]
    assert record["parent_dataset_id"] == "raw_orders"
    assert record["information_loss"] is False
    assert applied[0]["decision_policy"] == "auto_safe"
    assert proposals == []


def test_unit_bearing_numeric_conversion_is_proposed_not_applied():
    raw = pd.DataFrame({"amount": ["10K", "20K", "30K"]})

    prepared, record, applied, proposals = prepare_analysis_copy(
        raw,
        logical_name="orders",
        raw_dataset_id="raw_orders",
        source_fingerprint=frame_fingerprint(raw),
    )

    assert prepared["amount"].tolist() == raw["amount"].tolist()
    assert applied == []
    assert proposals
    assert proposals[0]["decision_policy"] == "confirmation_required"
