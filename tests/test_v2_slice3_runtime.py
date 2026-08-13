import json

import pandas as pd
import pytest

from data_agent.v2.dataset import DatasetRegistry, DatasetRole
from data_agent.v2.models import FindingKind
from data_agent.v2.slice3 import Slice3TransformationRuntime
from data_agent.v2.store import V2FactStore
from data_agent.v2.transformation import StaleTransformationProposal, TransformationStore


def test_slice3_auto_applies_lossless_iso_date_without_asking(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    pd.DataFrame(
        {"order_date": ["2026-01-02", "2026-02-03"], "sales": [10, 20]}
    ).to_csv(inbox / "iso.csv", index=False)
    runtime = Slice3TransformationRuntime(tmp_path / "sessions", inbox)

    events = list(
        runtime.start(
            session_id="session_iso",
            turn_id="turn_iso",
            filename="iso.csv",
            date_column="order_date",
            question="把日期列转换为可分析日期。",
        )
    )

    names = [item.event for item in events]
    assert "user_input_required" not in names
    assert names[-1] == "turn_completed"
    versions = DatasetRegistry(tmp_path / "sessions", "session_iso").list_versions()
    assert [item.role for item in versions] == [DatasetRole.RAW, DatasetRole.ANALYSIS]
    assert any(
        item.finding_kind is FindingKind.TRANSFORMATION
        for item in V2FactStore(tmp_path / "sessions", "session_iso").read_findings()
    )


def test_slice3_ambiguous_date_pauses_then_promotes_selected_candidate(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    pd.DataFrame(
        {"order_date": ["01/02/2026", "03/04/2026"], "sales": [10, 20]}
    ).to_csv(inbox / "ambiguous.csv", index=False)
    runtime = Slice3TransformationRuntime(tmp_path / "sessions", inbox)

    first = list(
        runtime.start(
            session_id="session_ambiguous",
            turn_id="turn_ambiguous",
            filename="ambiguous.csv",
            date_column="order_date",
            question="把日期列转换为可分析日期。",
        )
    )
    required = next(item.data for item in first if item.event == "user_input_required")
    assert [item.event for item in first][-1] == "user_input_required"
    assert required["reason_code"] == "ambiguous_date_order"
    assert {item["option_key"] for item in required["options"]} == {"dmy", "mdy"}
    pending = TransformationStore(
        tmp_path / "sessions", "session_ambiguous"
    ).find_by_turn("turn_ambiguous")
    assert pending.status == "pending"

    resumed = list(
        runtime.resolve(
            session_id="session_ambiguous",
            turn_id="turn_ambiguous",
            proposal_id=required["proposal_id"],
            option_key="dmy",
            expected_parent_version_id=required["parent_version_id"],
            expected_parent_content_fingerprint=required["parent_content_fingerprint"],
        )
    )

    assert resumed[-1].event == "turn_completed"
    turn = V2FactStore(tmp_path / "sessions", "session_ambiguous").read_turn_blocks(
        "turn_ambiguous"
    )
    assert turn["status"] == "finalized"
    assert "日/月/年" in json.dumps(turn, ensure_ascii=False)
    rendered = json.dumps(turn["blocks"], ensure_ascii=False)
    assert "proposal_" not in rendered
    assert "dv_" not in rendered
    versions = DatasetRegistry(tmp_path / "sessions", "session_ambiguous").list_versions()
    assert [item.role for item in versions] == [
        DatasetRole.RAW,
        DatasetRole.CANDIDATE,
        DatasetRole.CANDIDATE,
        DatasetRole.ANALYSIS,
    ]
    analysis = versions[-1]
    assert DatasetRegistry(tmp_path / "sessions", "session_ambiguous").get_frame(
        analysis.dataset_version_id
    ).loc[0, "order_date"] == pd.Timestamp("2026-02-01")


def test_slice3_rejects_confirmation_with_stale_parent_binding(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    pd.DataFrame({"order_date": ["01/02/2026", "03/04/2026"]}).to_csv(
        inbox / "ambiguous.csv", index=False
    )
    runtime = Slice3TransformationRuntime(tmp_path / "sessions", inbox)
    first = list(
        runtime.start(
            session_id="session_stale_runtime",
            turn_id="turn_stale_runtime",
            filename="ambiguous.csv",
            date_column="order_date",
            question="转换日期。",
        )
    )
    required = next(item.data for item in first if item.event == "user_input_required")

    with pytest.raises(StaleTransformationProposal):
        list(
            runtime.resolve(
                session_id="session_stale_runtime",
                turn_id="turn_stale_runtime",
                proposal_id=required["proposal_id"],
                option_key="dmy",
                expected_parent_version_id="dv_wrong_parent",
                expected_parent_content_fingerprint="sha256:wrong",
            )
        )

    assert TransformationStore(
        tmp_path / "sessions", "session_stale_runtime"
    ).project(required["proposal_id"]).status == "pending"
