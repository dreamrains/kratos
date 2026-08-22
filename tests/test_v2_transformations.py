import pandas as pd
import pytest

from data_agent.v2.dataset import DatasetRegistry, DatasetRole
from data_agent.v2.transformation import (
    DateTransformDisposition,
    StaleTransformationProposal,
    TransformationDecision,
    TransformationConflict,
    TransformationOption,
    TransformationProposal,
    TransformationStore,
    apply_date_option,
    inspect_date_conversion,
)


def test_iso_date_conversion_is_safe_and_does_not_require_user_input():
    frame = pd.DataFrame(
        {"order_date": ["2026-01-02", "2026-02-03", None], "sales": [1, 2, 3]}
    )

    plan = inspect_date_conversion(frame, "order_date")

    assert plan.disposition is DateTransformDisposition.AUTO_APPLY
    assert plan.reason_code == "lossless_unambiguous_date"
    assert plan.options[0].option_key == "iso"
    assert plan.options[0].sensitivity.new_missing == 0
    converted = apply_date_option(frame, "order_date", plan.options[0])
    assert pd.api.types.is_datetime64_any_dtype(converted["order_date"])
    assert not pd.api.types.is_datetime64_any_dtype(frame["order_date"])


def test_iso_slash_date_conversion_is_safe_and_does_not_require_user_input():
    frame = pd.DataFrame(
        {"order_date": ["2026/01/02", "2026/02/03", None], "sales": [1, 2, 3]}
    )

    plan = inspect_date_conversion(frame, "order_date")

    assert plan.disposition is DateTransformDisposition.AUTO_APPLY
    assert plan.reason_code == "lossless_unambiguous_date"
    assert plan.options[0].option_key == "iso_slash"
    assert plan.options[0].sensitivity.new_missing == 0
    converted = apply_date_option(frame, "order_date", plan.options[0])
    assert pd.api.types.is_datetime64_any_dtype(converted["order_date"])


def test_ambiguous_day_month_values_require_structured_semantic_choice():
    frame = pd.DataFrame(
        {"order_date": ["01/02/2026", "03/04/2026", "10/11/2026"]}
    )

    plan = inspect_date_conversion(frame, "order_date")

    assert plan.disposition is DateTransformDisposition.NEEDS_INPUT
    assert plan.reason_code == "ambiguous_date_order"
    assert {item.option_key for item in plan.options} == {"dmy", "mdy"}
    assert all(item.sensitivity.new_missing == 0 for item in plan.options)
    assert all(item.sensitivity.divergent_values == 3 for item in plan.options)
    dmy = apply_date_option(
        frame,
        "order_date",
        next(item for item in plan.options if item.option_key == "dmy"),
    )
    mdy = apply_date_option(
        frame,
        "order_date",
        next(item for item in plan.options if item.option_key == "mdy"),
    )
    assert dmy.loc[0, "order_date"] == pd.Timestamp("2026-02-01")
    assert mdy.loc[0, "order_date"] == pd.Timestamp("2026-01-02")


def test_partial_parse_is_limited_instead_of_silently_creating_missing_values():
    frame = pd.DataFrame({"order_date": ["2026-01-02", "not-a-date"]})

    plan = inspect_date_conversion(frame, "order_date")

    assert plan.disposition is DateTransformDisposition.UNAVAILABLE
    assert plan.reason_code == "date_conversion_would_add_missing"
    assert plan.options == ()


def test_candidate_promotion_preserves_raw_and_records_two_step_lineage(tmp_path):
    registry = DatasetRegistry(tmp_path, "session_transform")
    raw_frame = pd.DataFrame({"order_date": ["01/02/2026", "03/04/2026"]})
    raw = registry.register_raw("orders", raw_frame, source_identity="upload:orders.csv")
    option = TransformationOption.for_format(
        raw_frame["order_date"], option_key="dmy", label="日/月/年", date_format="%d/%m/%Y"
    )
    candidate_frame = apply_date_option(raw_frame, "order_date", option)
    candidate = registry.derive(
        parent_version_id=raw.dataset_version_id,
        frame=candidate_frame,
        role=DatasetRole.CANDIDATE,
        transform={"operation": "parse_datetime", "column": "order_date", "option": "dmy"},
    )

    analysis = registry.promote_candidate(
        candidate.dataset_version_id,
        expected_parent_version_id=raw.dataset_version_id,
        proposal_id="proposal_orders_date",
        decision_id="decision_orders_date_dmy",
    )

    assert analysis.role is DatasetRole.ANALYSIS
    assert analysis.parent_version_id == candidate.dataset_version_id
    assert analysis.transform["proposal_id"] == "proposal_orders_date"
    assert not pd.api.types.is_datetime64_any_dtype(
        registry.get_frame(raw.dataset_version_id)["order_date"]
    )
    assert pd.api.types.is_datetime64_any_dtype(
        registry.get_frame(analysis.dataset_version_id)["order_date"]
    )


def _proposal(parent_version_id: str, parent_fingerprint: str) -> TransformationProposal:
    return TransformationProposal(
        proposal_id="proposal_orders_date",
        turn_id="turn_orders_date",
        run_id="run_orders_date",
        commitment_id="commitment_orders_date",
        parent_version_id=parent_version_id,
        parent_content_fingerprint=parent_fingerprint,
        column="order_date",
        target_type="datetime",
        reason_code="ambiguous_date_order",
        options=(
            TransformationOption(
                option_key="dmy",
                label="日/月/年",
                date_format="%d/%m/%Y",
                candidate_version_id="dv_candidate_dmy",
            ),
            TransformationOption(
                option_key="mdy",
                label="月/日/年",
                date_format="%m/%d/%Y",
                candidate_version_id="dv_candidate_mdy",
            ),
        ),
    )


def test_transformation_decision_is_idempotent_and_rejects_stale_parent(tmp_path):
    store = TransformationStore(tmp_path, "session_transform")
    proposal = _proposal("dv_parent", "sha256:parent")
    store.append_proposal(proposal)
    decision = TransformationDecision(
        decision_id="decision_orders_date_dmy",
        proposal_id=proposal.proposal_id,
        option_key="dmy",
        expected_parent_version_id="dv_parent",
        expected_parent_content_fingerprint="sha256:parent",
    )

    assert store.append_decision(
        decision,
        active_parent_version_id="dv_parent",
        active_parent_content_fingerprint="sha256:parent",
    )
    assert not store.append_decision(
        decision,
        active_parent_version_id="dv_parent",
        active_parent_content_fingerprint="sha256:parent",
    )
    assert store.project(proposal.proposal_id).status == "resolved"

    stale_store = TransformationStore(tmp_path, "session_stale")
    stale_store.append_proposal(proposal)
    with pytest.raises(StaleTransformationProposal):
        stale_store.append_decision(
            decision,
            active_parent_version_id="dv_new_parent",
            active_parent_content_fingerprint="sha256:new",
        )
    assert stale_store.project(proposal.proposal_id).status == "pending"


def test_proposal_cannot_receive_two_different_semantic_decisions(tmp_path):
    store = TransformationStore(tmp_path, "session_conflict")
    proposal = _proposal("dv_parent", "sha256:parent")
    store.append_proposal(proposal)
    first = TransformationDecision(
        decision_id="decision_dmy",
        proposal_id=proposal.proposal_id,
        option_key="dmy",
        expected_parent_version_id="dv_parent",
        expected_parent_content_fingerprint="sha256:parent",
    )
    store.append_decision(
        first,
        active_parent_version_id="dv_parent",
        active_parent_content_fingerprint="sha256:parent",
    )
    retry = TransformationDecision(
        decision_id="decision_dmy_retry",
        proposal_id=proposal.proposal_id,
        option_key="dmy",
        expected_parent_version_id="dv_parent",
        expected_parent_content_fingerprint="sha256:parent",
    )
    assert not store.append_decision(
        retry,
        active_parent_version_id="dv_parent",
        active_parent_content_fingerprint="sha256:parent",
    )
    with pytest.raises(TransformationConflict):
        store.append_decision(
            TransformationDecision(
                decision_id="decision_mdy",
                proposal_id=proposal.proposal_id,
                option_key="mdy",
                expected_parent_version_id="dv_parent",
                expected_parent_content_fingerprint="sha256:parent",
            ),
            active_parent_version_id="dv_parent",
            active_parent_content_fingerprint="sha256:parent",
        )
